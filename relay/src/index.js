// The log relay (PRESS-0436 § 4.3): takes a log Pressless's Send my log
// posts, and files it as an issue in a private repository, reaching GitHub as
// a GitHub App. Pressless holds no key this checks; a key shipped in a public
// app is no key. Abuse is held off by the rate limit and the size limit, and
// every refusal comes before GitHub is asked for anything (INV-6).

// Two kinds of body (PRESS-0436 § 4.3). KIND is what Pressless 1.3 sends: a
// line of JSON, then each log gzipped and base64-encoded, which the relay
// files as sent, so a near-limit send stays within the free plan's 10 ms of
// CPU (PRESS-0494). JSON is what Pressless 1.2 sends, kept while it is in use.
const KIND = "application/x-pressless-log";
// 4 MiB. The app's own cap (LARGEST in src/pressless/sendlog.py) must stay at
// or below this; tests/test_sendlog.py checks it.
export const LARGEST = 4_194_304;
// 2.2 MiB: Pressless 1.2's cap, 2 * log.MAX_BYTES + 65,536, is below it.
export const JSON_LARGEST = 2_306_867;
const LINE_LONGEST = 512 * 1024;             // KIND's first line
const TAIL_LONGEST = 120_000;                // UTF-16 units: the app's 60,000 characters
const GZIP = new TextEncoder().encode("H4sI");  // base64 of gzip's first three bytes
// The pattern _REFERENCE in src/pressless/sendlog.py must match this and the
// six-letter length in reference(); tests/test_sendlog.py checks it.
export const ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const VERSION = /^[0-9A-Za-z.-]{1,32}$/;
const SYSTEM_LONGEST = 128;
const EXCERPT_LINES = 100;
const EXCERPT_CHARACTERS = 60_000;           // an issue body holds 65,536
const GITHUB = "https://api.github.com";

class GitHubFailed extends Error {
  constructor(step, status) {
    super(`${step} answered ${status}`);
    this.status = status;
  }
}

function answer(status, value) {
  return new Response(JSON.stringify(value), {
    status, headers: {"Content-Type": "application/json"},
  });
}

// The body, or null once it passes `largest` bytes; the rest is never read.
async function readCapped(stream, largest) {
  if (!stream) return new Uint8Array();
  const reader = stream.getReader();
  const pieces = [];
  let total = 0;
  for (;;) {
    const {done, value} = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > largest) {
      await reader.cancel();
      return null;
    }
    pieces.push(value);
  }
  const whole = new Uint8Array(total);
  let at = 0;
  for (const piece of pieces) { whole.set(piece, at); at += piece.byteLength; }
  return whole;
}

function named(sent) {
  return sent !== null && typeof sent === "object" && !Array.isArray(sent)
    && typeof sent.version === "string" && VERSION.test(sent.version)
    && typeof sent.system === "string" && [...sent.system].length <= SYSTEM_LONGEST;
}

// A negative length needs no check of its own: it leaves a part that is not gzip.
const length = (value) => Number.isSafeInteger(value) && value % 4 === 0;

// What a file's upload carries: its base64, as a length and a writer, so it
// is written once, straight into the upload.
function encoded(text) {
  const bytes = new TextEncoder().encode(text);
  return {length: base64Length(bytes), into: (out, at) => base64Into(bytes, out, at)};
}

function asSent(part) {
  return {length: part.length, into: (out, at) => out.set(part, at)};
}

// A JSON body from Pressless 1.2, as the files and words to file; null where
// it has the wrong shape.
function fromJson(raw) {
  let sent = null;
  try { sent = JSON.parse(new TextDecoder().decode(raw)); } catch { return null; }
  if (!named(sent) || typeof sent.log !== "string" || typeof sent.old !== "string") return null;
  return {...sent, quote: sent.log,
          files: [["pressless.log", encoded(sent.log)], ["pressless.log.1", encoded(sent.old)]]};
}

// A KIND body, likewise. Its parts are checked as base64 of gzip and never
// decoded: decoding is what the kind exists to avoid.
function fromKind(raw) {
  const end = raw.subarray(0, LINE_LONGEST).indexOf(10);
  if (end < 0) return null;
  let head = null;
  try { head = JSON.parse(new TextDecoder().decode(raw.subarray(0, end))); } catch { return null; }
  if (!named(head) || typeof head.tail !== "string" || head.tail.length > TAIL_LONGEST
      || !length(head.log) || !length(head.old)) return null;
  const at = end + 1;
  if (at + head.log + head.old !== raw.length) return null;
  const parts = [raw.subarray(at, at + head.log), raw.subarray(at + head.log)];
  if (!parts.every(gzipBase64)) return null;
  return {version: head.version, system: head.system, quote: head.tail,
          files: [["pressless.log.gz", asSent(parts[0])], ["pressless.log.1.gz", asSent(parts[1])]]};
}

const DIGITS = new TextEncoder().encode(
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/");
const PAD = 61;                               // "="
const DIGIT = new Uint8Array(256);            // 1 for each base64 digit's byte
for (const byte of DIGITS) DIGIT[byte] = 1;

// Whether `part` is base64 that starts as gzip does: digits, then at most two
// "=". Read through a table, not a regex on decoded text, which cost five
// times as much CPU (PRESS-0494).
function gzipBase64(part) {
  if (part.length < GZIP.length || GZIP.some((byte, at) => part[at] !== byte)) return false;
  let end = part.length;
  if (part[end - 1] === PAD) end--;
  if (part[end - 1] === PAD) end--;
  let all = 1;
  for (let at = GZIP.length; at < end; at++) all &= DIGIT[part[at]];
  return all === 1;
}

function base64Length(bytes) {
  return Math.ceil(bytes.length / 3) * 4;
}

// Writes the base64 of `bytes` into `out` from `to`. Done in a byte array, not
// through btoa, whose string building cost most of a near-limit send's CPU
// (PRESS-0493).
function base64Into(bytes, out, to) {
  const whole = bytes.length - bytes.length % 3;
  let at = 0;
  for (; at < whole; at += 3) {
    const n = (bytes[at] << 16) | (bytes[at + 1] << 8) | bytes[at + 2];
    out[to++] = DIGITS[n >> 18];
    out[to++] = DIGITS[(n >> 12) & 63];
    out[to++] = DIGITS[(n >> 6) & 63];
    out[to++] = DIGITS[n & 63];
  }
  const left = bytes.length - whole;
  if (left) {
    const n = (bytes[at] << 16) | (left === 2 ? bytes[at + 1] << 8 : 0);
    out[to++] = DIGITS[n >> 18];
    out[to++] = DIGITS[(n >> 12) & 63];
    out[to++] = left === 2 ? DIGITS[(n >> 6) & 63] : PAD;
    out[to++] = PAD;
  }
}

export function base64(bytes) {
  const out = new Uint8Array(base64Length(bytes));
  base64Into(bytes, out, 0);
  return new TextDecoder().decode(out);
}

function base64url(bytes) {
  return base64(bytes).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

// A JWT for the App, signed RS256 with its PKCS#8 key.
async function appToken(env, now) {
  const der = Uint8Array.from(
    atob(env.APP_KEY.replace(/-----[A-Z ]+-----/g, "").replace(/\s+/g, "")),
    (letter) => letter.charCodeAt(0));
  const key = await crypto.subtle.importKey(
    "pkcs8", der, {name: "RSASSA-PKCS1-v1_5", hash: "SHA-256"}, false, ["sign"]);
  const encode = (value) => base64url(new TextEncoder().encode(JSON.stringify(value)));
  // A minute back for a clock running ahead of GitHub's; GitHub allows ten.
  const unsigned = `${encode({alg: "RS256", typ: "JWT"})}.`
    + encode({iat: now - 60, exp: now + 540, iss: String(env.APP_ID)});
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5", key, new TextEncoder().encode(unsigned));
  return `${unsigned}.${base64url(new Uint8Array(signature))}`;
}

// `body` is a value to send as JSON, or bytes already JSON.
async function github(step, method, path, token, body) {
  const reply = await fetch(GITHUB + path, {
    method,
    headers: {
      "Authorization": `Bearer ${token}`,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "pressless-logs",
      "Content-Type": "application/json",
    },
    body: body instanceof Uint8Array ? body : JSON.stringify(body),
  });
  if (!reply.ok) throw new GitHubFailed(step, reply.status);
  return reply.json();
}

// The key the rate limit counts a sender under. A home IPv6 network hands out
// a /64, so its first four groups stand for the sender; anything odd is kept whole.
function limitKey(address) {
  if (!address.includes(":") || address.includes(".")) return address;
  const halves = address.split("::");
  if (halves.length > 2) return address;
  const head = halves[0] ? halves[0].split(":") : [];
  const tail = halves.length === 2 && halves[1] ? halves[1].split(":") : [];
  const gap = 8 - head.length - tail.length;
  if (halves.length === 1 ? gap !== 0 : gap < 1) return address;
  const groups = [...head, ...Array(halves.length === 2 ? gap : 0).fill("0"), ...tail];
  if (!groups.every((group) => /^[0-9a-f]{1,4}$/i.test(group))) return address;
  const prefix = groups.slice(0, 4).map((group) => group.toLowerCase().replace(/^0+(?=.)/, ""));
  return `${prefix.join(":")}::/64`;
}

function reference() {
  const picked = crypto.getRandomValues(new Uint8Array(6));
  return Array.from(picked, (byte) => ALPHABET[byte % ALPHABET.length]).join("");
}

function fenceFor(text) {
  const longest = Math.max(0, ...(text.match(/`+/g) || []).map((run) => run.length));
  return "`".repeat(Math.max(3, longest + 1));
}

// The last lines of the log, and a fence no run of backticks in them closes.
function excerpt(log) {
  const lines = log.replace(/\n$/, "").split("\n").slice(-EXCERPT_LINES).join("\n");
  let cut = lines.slice(-EXCERPT_CHARACTERS);
  let fence = fenceFor(cut);
  // The fence is as long as the longest run of backticks, so it can be long.
  while (cut.length + 2 * fence.length > EXCERPT_CHARACTERS) {
    cut = cut.slice(Math.floor(cut.length / 2));
    fence = fenceFor(cut);
  }
  return `${fence}text\n${cut}\n${fence}`;
}

async function putFile(env, token, named, name, content) {
  const path = `logs/${named}/${name}`;
  // The JSON is built as bytes, so the content is never a string to copy.
  const encoder = new TextEncoder();
  const head = encoder.encode(`{"message":${JSON.stringify(`Log ${named}: ${name}`)},"content":"`);
  const tail = encoder.encode('"}');
  const body = new Uint8Array(head.length + content.length + tail.length);
  body.set(head);
  content.into(body, head.length);
  body.set(tail, body.length - tail.length);
  const reply = await github("file", "PUT", `/repos/${env.REPOSITORY}/contents/${path}`, token, body);
  return {path, sha: reply.content && reply.content.sha};
}

// Takes back the files a failed send wrote. A failure here is ignored; it
// returns whether any file is left behind.
async function withdraw(env, token, named, written) {
  let left = false;
  for (const {path, sha} of written) {
    try {
      await github("withdraw", "DELETE", `/repos/${env.REPOSITORY}/contents/${path}`, token,
        {message: `Log ${named}: withdrawn`, sha});
    } catch { left = true; }
  }
  return left;
}

async function file(env, sent) {
  const repository = env.REPOSITORY;
  const minted = await github(
    "token", "POST", `/app/installations/${env.INSTALLATION_ID}/access_tokens`,
    await appToken(env, Math.floor(Date.now() / 1000)),
    {repositories: [repository.split("/")[1]],
     permissions: {contents: "write", issues: "write"}});
  let named = reference();
  const written = [];
  const [[first, log], [second, old]] = sent.files;
  try {
    try {
      written.push(await putFile(env, minted.token, named, first, log));
    } catch (error) {
      // 422: the path exists. One new reference, once.
      if (!(error instanceof GitHubFailed) || error.status !== 422) throw error;
      named = reference();
      written.push(await putFile(env, minted.token, named, first, log));
    }
    written.push(await putFile(env, minted.token, named, second, old));
    const folder = `logs/${named}`;
    await github("issue", "POST", `/repos/${repository}/issues`, minted.token, {
      title: `Log ${named}: Pressless ${sent.version} on ${sent.system}`,
      body: `Files: \`${folder}/${first}\`, \`${folder}/${second}\`\n\n`
        + `The last lines of \`pressless.log\`:\n\n${excerpt(sent.quote)}\n`,
    });
  } catch (error) {
    if (await withdraw(env, minted.token, named, written)) error.leftBehind = `logs/${named}`;
    throw error;
  }
  return named;
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/log") {
      return answer(404, {error: "not found"});
    }
    // Before the limit, so a refused request uses no visitor's slot. A page on
    // another site can post text/plain with no preflight; it cannot post this.
    const type = (request.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
    const json = type === "application/json";
    if (!json && type !== KIND) return answer(415, {error: "not a log"});
    const address = request.headers.get("CF-Connecting-IP") || "unknown";
    if (!(await env.SENDS.limit({key: limitKey(address)})).success) {
      return answer(429, {error: "too many sends; try again in a minute"});
    }
    const largest = json ? JSON_LARGEST : LARGEST;
    if (Number(request.headers.get("Content-Length") || 0) > largest) {
      return answer(413, {error: "too large"});
    }
    const raw = await readCapped(request.body, largest);
    if (raw === null) return answer(413, {error: "too large"});
    const sent = json ? fromJson(raw) : fromKind(raw);
    if (!sent) return answer(400, {error: "not a log"});
    try {
      return answer(200, {reference: await file(env, sent)});
    } catch (error) {
      // The status only: a GitHub answer can quote what was sent.
      const said = error instanceof GitHubFailed ? error.message : `failed: ${error.name}`;
      console.log(error.leftBehind ? `${said}; ${error.leftBehind} left behind` : said);
      return answer(502, {error: "the log could not be filed"});
    }
  },
};
