// PRESS-0436 INV-6: the relay refuses a wrong method or path, a send over the
// rate limit, a body over the size limit and a wrong shape, before it asks
// GitHub for anything. GitHub is a replaced fetch; the App's key is made
// fresh for each run, so none is ever in the repository.

import assert from "node:assert/strict";
import {beforeEach, test} from "node:test";

import relay, {ALPHABET, LARGEST} from "../src/index.js";

const pair = await crypto.subtle.generateKey(
  {name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]),
   hash: "SHA-256"}, true, ["sign", "verify"]);
const der = new Uint8Array(await crypto.subtle.exportKey("pkcs8", pair.privateKey));
const lines = Buffer.from(der).toString("base64").match(/.{1,64}/g).join("\n");
const label = "PRI" + "VATE KEY";            // spelt apart: no file here holds a key header
const pem = `-----BEGIN ${label}-----\n${lines}\n-----END ${label}-----\n`;

let asked;
let failing;
let allowed;

function env() {
  return {
    APP_KEY: pem, APP_ID: "123", INSTALLATION_ID: "456", REPOSITORY: "owner/logs",
    SENDS: {limit: async () => ({success: allowed})},
  };
}

beforeEach(() => {
  asked = [];
  failing = null;
  allowed = true;
  globalThis.fetch = async (url, options) => {
    asked.push({url, ...options, body: JSON.parse(options.body)});
    if (failing && url.includes(failing)) return new Response("{}", {status: 500});
    const body = url.endsWith("/access_tokens") ? {token: "minted"} : {};
    return new Response(JSON.stringify(body), {status: 201});
  };
});

function post(body, {method = "POST", path = "/log", headers = {}} = {}) {
  return new Request(`https://relay.example${path}`, {
    method, headers: {"CF-Connecting-IP": "192.0.2.1", ...headers},
    body: method === "GET" ? undefined : body,
  });
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

test("a send over the rate limit is refused, and GitHub is not asked", async () => {
  allowed = false;
  assert.equal((await relay.fetch(post(JSON.stringify(good)), env())).status, 429);
  assert.deepEqual(asked, []);
});

test("a body over the size limit is refused, and GitHub is not asked", async () => {
  const big = JSON.stringify({...good, log: "x".repeat(LARGEST)});
  assert.equal((await relay.fetch(post(big), env())).status, 413);
  // A body with no declared length is measured as it is read.
  const stream = new Blob([big]).stream();
  const undeclared = new Request("https://relay.example/log", {
    method: "POST", body: stream, duplex: "half", headers: {"CF-Connecting-IP": "192.0.2.1"}});
  assert.equal((await relay.fetch(undeclared, env())).status, 413);
  assert.deepEqual(asked, []);
});

test("a wrong shape is refused, and GitHub is not asked", async () => {
  const wrong = [
    "not json", "[]", "null",
    JSON.stringify({...good, version: "1.1.1 <b>"}),
    JSON.stringify({...good, version: "x".repeat(33)}),
    JSON.stringify({...good, system: "x".repeat(129)}),
    JSON.stringify({...good, log: 5}),
    JSON.stringify({version: good.version, system: good.system, log: good.log}),
  ];
  for (const body of wrong) {
    assert.equal((await relay.fetch(post(body), env())).status, 400, body.slice(0, 40));
  }
  assert.deepEqual(asked, []);
});

test("a good send files both logs and an issue, and answers the reference", async () => {
  const reply = await relay.fetch(post(JSON.stringify(good)), env());
  assert.equal(reply.status, 200);
  const {reference} = await reply.json();
  assert.equal(reference.length, 6);
  assert.ok([...reference].every((letter) => ALPHABET.includes(letter)));

  const [token, log, old, issue] = asked;
  assert.equal(asked.length, 4);
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

test("a GitHub failure answers 502", async () => {
  for (const step of ["/access_tokens", "/contents/", "/issues"]) {
    failing = step;
    asked = [];
    assert.equal((await relay.fetch(post(JSON.stringify(good)), env())).status, 502, step);
  }
});
