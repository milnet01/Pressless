// PRESS-0436 INV-6: the relay refuses a wrong method or path, a send over the
// rate limit, a body over the size limit and a wrong shape, before it asks
// GitHub for anything. GitHub is a replaced fetch; the App's key is made
// fresh for each run, so none is ever in the repository.

import assert from "node:assert/strict";
import {beforeEach, test} from "node:test";

import relay, {LARGEST} from "../src/index.js";

const pair = await crypto.subtle.generateKey(
  {name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]),
   hash: "SHA-256"}, true, ["sign", "verify"]);
const der = new Uint8Array(await crypto.subtle.exportKey("pkcs8", pair.privateKey));
const lines = Buffer.from(der).toString("base64").match(/.{1,64}/g).join("\n");
const label = "PRI" + "VATE KEY";            // spelt apart: no file here holds a key header
const pem = `-----BEGIN ${label}-----\n${lines}\n-----END ${label}-----\n`;

const LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";   // written out: a change to the source must show here

let asked;
let failing;
let failStatus;
let deletesFail;
let collisions;
let throwing;
let allowed;
let keys;

function env() {
  return {
    APP_KEY: pem, APP_ID: "123", INSTALLATION_ID: "456", REPOSITORY: "owner/logs",
    SENDS: {limit: async ({key}) => { keys.push(key); return {success: allowed}; }},
  };
}

beforeEach(() => {
  asked = [];
  failing = null;
  failStatus = 500;
  deletesFail = false;
  collisions = 0;
  throwing = null;
  allowed = true;
  keys = [];
  globalThis.fetch = async (url, options) => {
    asked.push({url, ...options, body: JSON.parse(options.body)});
    if (throwing && url.includes(throwing)) throw new TypeError("network down");
    if (options.method === "PUT" && collisions > 0) {
      collisions -= 1;
      return new Response("{}", {status: 422});
    }
    if (options.method === "DELETE" && deletesFail) return new Response("{}", {status: 500});
    if (options.method !== "DELETE" && failing && url.includes(failing)) {
      return new Response("{}", {status: failStatus});
    }
    let body = {};
    if (url.endsWith("/access_tokens")) body = {token: "minted"};
    if (options.method === "PUT") body = {content: {sha: `sha:${url.split("/contents/")[1]}`}};
    return new Response(JSON.stringify(body), {status: 201});
  };
});

function post(body, {method = "POST", path = "/log", headers = {}} = {}) {
  return new Request(`https://relay.example${path}`, {
    method,
    headers: {"CF-Connecting-IP": "192.0.2.1", "Content-Type": "application/json", ...headers},
    body: method === "GET" ? undefined : body,
  });
}

// What the relay printed while it ran `run`.
async function printed(run) {
  const real = console.log;
  const lines = [];
  console.log = (...parts) => lines.push(parts.join(" "));
  try { await run(); } finally { console.log = real; }
  return lines;
}

const good = {version: "1.1.1", system: "Linux (openSUSE Tumbleweed)",
              log: "first\nsecond ``` fence\n", old: "older\n"};

test("a wrong method or path is not found, and GitHub is not asked", async () => {
  for (const request of [post(null, {method: "GET"}), post(JSON.stringify(good), {path: "/"}),
                         post(JSON.stringify(good), {path: "/log/x"})]) {
    assert.equal((await relay.fetch(request, env())).status, 404);
  }
  assert.deepEqual(asked, []);
});

test("a body not sent as JSON is refused before the limiter, and GitHub is not asked", async () => {
  for (const type of ["text/plain", "text/plain;charset=UTF-8", "application/x-www-form-urlencoded", ""]) {
    const headers = {"Content-Type": type};
    const reply = await relay.fetch(post(JSON.stringify(good), {headers}), env());
    assert.equal(reply.status, 415, type);
    assert.deepEqual(await reply.json(), {error: "not json"});
  }
  assert.deepEqual(keys, []);
  assert.deepEqual(asked, []);
});

test("JSON with a parameter or another case is accepted", async () => {
  for (const type of ["application/json; charset=utf-8", "Application/JSON"]) {
    asked = [];
    const reply = await relay.fetch(post(JSON.stringify(good), {headers: {"Content-Type": type}}), env());
    assert.equal(reply.status, 200, type);
  }
});

test("a send over the rate limit is refused, and GitHub is not asked", async () => {
  allowed = false;
  assert.equal((await relay.fetch(post(JSON.stringify(good)), env())).status, 429);
  assert.deepEqual(asked, []);
});

test("the limiter is keyed on the sender's address", async () => {
  await relay.fetch(post(JSON.stringify(good)), env());
  assert.deepEqual(keys, ["192.0.2.1"]);
  keys = [];
  const none = new Request("https://relay.example/log", {
    method: "POST", body: JSON.stringify(good), headers: {"Content-Type": "application/json"}});
  await relay.fetch(none, env());
  assert.deepEqual(keys, ["unknown"]);
});

test("an IPv6 sender is keyed on its /64, and an odd value whole", async () => {
  const cases = [
    ["2001:db8:1:2::5", "2001:db8:1:2::/64"],
    ["2001:0DB8:1:2:ffff::1", "2001:db8:1:2::/64"],
    ["2001:db8:1:2:3:4:5:6", "2001:db8:1:2::/64"],
    ["2001:db8:1:2:9:9:9:9", "2001:db8:1:2::/64"],
    ["2001:0db8:0000:0000:0:0:0:1", "2001:db8:0:0::/64"],
    ["::1", "0:0:0:0::/64"],
    ["::ffff:192.0.2.1", "::ffff:192.0.2.1"],
    ["2001:db8::zz", "2001:db8::zz"],
    ["1:2:3::4::5", "1:2:3::4::5"],
    ["198.51.100.7", "198.51.100.7"],
  ];
  for (const [address, key] of cases) {
    keys = [];
    await relay.fetch(post(JSON.stringify(good), {headers: {"CF-Connecting-IP": address}}), env());
    assert.deepEqual(keys, [key], address);
  }
});

test("a body over the size limit is refused, and GitHub is not asked", async () => {
  assert.equal(LARGEST, 2_306_867);
  const big = JSON.stringify({...good, log: "x".repeat(2_306_867)});
  assert.equal((await relay.fetch(post(big), env())).status, 413);
  // A body with no declared length is measured as it is read.
  const stream = new Blob([big]).stream();
  const undeclared = new Request("https://relay.example/log", {
    method: "POST", body: stream, duplex: "half",
    headers: {"CF-Connecting-IP": "192.0.2.1", "Content-Type": "application/json"}});
  assert.equal((await relay.fetch(undeclared, env())).status, 413);
  assert.deepEqual(asked, []);
});

test("a declared length over the limit is refused on the header alone", async () => {
  const headers = {"Content-Length": String(2_306_867 + 1)};
  assert.equal((await relay.fetch(post(JSON.stringify(good), {headers}), env())).status, 413);
  assert.deepEqual(asked, []);
});

test("a wrong shape is refused, and GitHub is not asked", async () => {
  const wrong = [
    "not json", "[]", "null",
    JSON.stringify({...good, version: "1.1.1 <b>"}),
    JSON.stringify({...good, version: "x".repeat(33)}),
    JSON.stringify({...good, version: 5}),
    JSON.stringify({...good, system: "x".repeat(129)}),
    JSON.stringify({...good, log: 5}),
    JSON.stringify({...good, old: 5}),
    JSON.stringify({version: good.version, system: good.system, log: good.log}),
  ];
  for (const body of wrong) {
    assert.equal((await relay.fetch(post(body), env())).status, 400, body.slice(0, 40));
  }
  assert.deepEqual(asked, []);
});

test("the longest version and system are accepted", async () => {
  // The system is counted in characters, as the app counts it: 128 emoji are 256 UTF-16 units.
  const systems = ["x".repeat(128), "\u{1F600}".repeat(128)];
  for (const system of systems) {
    asked = [];
    const body = JSON.stringify({...good, version: "v".repeat(32), system});
    assert.equal((await relay.fetch(post(body), env())).status, 200, system.slice(0, 4));
  }
  const over = JSON.stringify({...good, system: "\u{1F600}".repeat(129)});
  assert.equal((await relay.fetch(post(over), env())).status, 400);
});

test("a good send files both logs and an issue, and answers the reference", async () => {
  const reply = await relay.fetch(post(JSON.stringify(good)), env());
  assert.equal(reply.status, 200);
  const {reference} = await reply.json();
  assert.equal(reference.length, 6);
  assert.ok([...reference].every((letter) => LETTERS.includes(letter)));

  const [token, log, old, issue] = asked;
  assert.equal(asked.length, 4);
  assert.deepEqual(asked.map((request) => request.method), ["POST", "PUT", "PUT", "POST"]);
  assert.equal(token.url, "https://api.github.com/app/installations/456/access_tokens");
  assert.deepEqual(token.body.permissions, {contents: "write", issues: "write"});
  assert.deepEqual(token.body.repositories, ["logs"]);
  const [head, claims, signature] = token.headers.Authorization.slice(7).split(".");
  const signed = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5", pair.publicKey, Buffer.from(signature, "base64url"),
    new TextEncoder().encode(`${head}.${claims}`));
  assert.ok(signed);
  assert.equal(JSON.parse(Buffer.from(claims, "base64url")).iss, "123");

  assert.equal(log.url, `https://api.github.com/repos/owner/logs/contents/logs/${reference}/pressless.log`);
  assert.equal(Buffer.from(log.body.content, "base64").toString("utf8"), good.log);
  assert.equal(old.url, `https://api.github.com/repos/owner/logs/contents/logs/${reference}/pressless.log.1`);
  assert.equal(Buffer.from(old.body.content, "base64").toString("utf8"), good.old);
  assert.equal(log.headers.Authorization, "Bearer minted");
  assert.equal(old.headers.Authorization, "Bearer minted");
  assert.equal(issue.headers.Authorization, "Bearer minted");

  assert.equal(issue.url, "https://api.github.com/repos/owner/logs/issues");
  assert.equal(issue.body.title, `Log ${reference}: Pressless 1.1.1 on Linux (openSUSE Tumbleweed)`);
  assert.match(issue.body.body, /````text\nfirst\nsecond ``` fence\n````/);
});

test("the issue's excerpt fits an issue body", async () => {
  const long = Array.from({length: 300}, (_, line) => `${line} ${"y".repeat(2000)}`).join("\n");
  await relay.fetch(post(JSON.stringify({...good, log: long})), env());
  const body = asked[3].body.body;
  assert.ok(body.length < 65_536);
  assert.ok(body.includes(`299 ${"y".repeat(2000)}`));
});

test("the excerpt keeps the last 100 lines", async () => {
  const many = Array.from({length: 300}, (_, line) => `line ${line}`).join("\n");
  await relay.fetch(post(JSON.stringify({...good, log: many})), env());
  const body = asked[3].body.body;
  assert.ok(!body.includes("line 199\n"));
  assert.ok(body.includes("\nline 200\n"));
  assert.ok(body.includes("\nline 299\n"));
});

test("a log of nothing but backticks still gives an issue body that fits", async () => {
  const ticks = "`".repeat(60_000);
  assert.equal((await relay.fetch(post(JSON.stringify({...good, log: ticks})), env())).status, 200);
  const body = asked[3].body.body;
  assert.ok(body.length < 65_536, String(body.length));
  assert.ok(body.includes("`".repeat(100)));
});

test("a GitHub failure answers 502, and nothing is filed after it", async () => {
  for (const step of ["/access_tokens", "/contents/", "/issues"]) {
    failing = step;
    asked = [];
    assert.equal((await relay.fetch(post(JSON.stringify(good)), env())).status, 502, step);
  }
  failing = "/contents/";
  asked = [];
  await relay.fetch(post(JSON.stringify(good)), env());
  assert.ok(!asked.some((request) => request.url.endsWith("/issues")));
  assert.deepEqual(asked.map((request) => request.method), ["POST", "PUT"]);
});

test("a fetch that throws answers 502, and the log is never printed", async () => {
  const secret = "SECRET-LOG-TEXT";
  const sent = JSON.stringify({...good, log: `${secret} one\n`, old: `${secret} two\n`});
  throwing = "/contents/";
  let reply;
  const lines = await printed(async () => { reply = await relay.fetch(post(sent), env()); });
  assert.equal(reply.status, 502);
  assert.deepEqual(lines, ["failed: TypeError"]);
  assert.ok(!lines.join("\n").includes(secret));
});

test("a GitHub failure prints the status, never the answer", async () => {
  failing = "/issues";
  const lines = await printed(() => relay.fetch(post(JSON.stringify(good)), env()));
  assert.deepEqual(lines, ["issue answered 500"]);
});

test("a failed issue withdraws both files, each with its own sha", async () => {
  failing = "/issues";
  assert.equal((await relay.fetch(post(JSON.stringify(good)), env())).status, 502);
  const puts = asked.filter((request) => request.method === "PUT");
  const deletes = asked.filter((request) => request.method === "DELETE");
  assert.equal(deletes.length, 2);
  for (const [at, put] of puts.entries()) {
    assert.equal(deletes[at].url, put.url);
    const path = put.url.split("/contents/")[1];
    assert.equal(deletes[at].body.sha, `sha:${path}`);
    assert.match(deletes[at].body.message, /^Log [A-Z2-9]{6}: withdrawn$/);
    assert.equal(deletes[at].headers.Authorization, "Bearer minted");
  }
});

test("a failed second file withdraws the first", async () => {
  failing = "/pressless.log.1";
  assert.equal((await relay.fetch(post(JSON.stringify(good)), env())).status, 502);
  const deletes = asked.filter((request) => request.method === "DELETE");
  assert.equal(deletes.length, 1);
  assert.ok(deletes[0].url.endsWith("/pressless.log"));
  assert.equal(deletes[0].body.sha, `sha:${deletes[0].url.split("/contents/")[1]}`);
  assert.ok(!asked.some((request) => request.url.endsWith("/issues")));
});

test("a failed withdrawal is named in the log, and the client still gets 502", async () => {
  failing = "/issues";
  deletesFail = true;
  let reply;
  const lines = await printed(async () => {
    reply = await relay.fetch(post(JSON.stringify(good)), env());
  });
  assert.equal(reply.status, 502);
  const [put] = asked.filter((request) => request.method === "PUT");
  const folder = put.url.split("/contents/")[1].split("/").slice(0, 2).join("/");
  assert.deepEqual(lines, [`issue answered 500; ${folder} left behind`]);
  assert.equal(asked.filter((request) => request.method === "DELETE").length, 2);
});

test("a reference already in use is replaced once", async () => {
  collisions = 1;
  const reply = await relay.fetch(post(JSON.stringify(good)), env());
  assert.equal(reply.status, 200);
  const {reference} = await reply.json();
  const puts = asked.filter((request) => request.method === "PUT");
  assert.equal(puts.length, 3);
  assert.ok(puts[0].url.endsWith("/pressless.log") && puts[1].url.endsWith("/pressless.log"));
  assert.notEqual(puts[0].url, puts[1].url);
  assert.ok(puts[1].url.includes(`/logs/${reference}/`));
  assert.ok(puts[2].url.includes(`/logs/${reference}/`));
});

test("a second collision, or another first-file failure, is a 502", async () => {
  collisions = 2;
  assert.equal((await relay.fetch(post(JSON.stringify(good)), env())).status, 502);
  assert.equal(asked.filter((request) => request.method === "PUT").length, 2);
  asked = [];
  collisions = 0;
  failing = "/contents/";
  failStatus = 409;
  assert.equal((await relay.fetch(post(JSON.stringify(good)), env())).status, 502);
  assert.equal(asked.filter((request) => request.method === "PUT").length, 1);
});

test("a collision on the second file is not retried", async () => {
  failing = "/pressless.log.1";
  failStatus = 422;
  assert.equal((await relay.fetch(post(JSON.stringify(good)), env())).status, 502);
  assert.equal(asked.filter((request) => request.method === "PUT").length, 2);
});
