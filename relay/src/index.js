// The log relay (PRESS-0436 § 4.3): takes a log Pressless's Send my log
// posts, and files it as an issue in a private repository, reaching GitHub as
// a GitHub App. Pressless holds no key this checks; a key shipped in a public
// app is no key. Abuse is held off by the rate limit and the size limit, and
// every refusal comes before GitHub is asked for anything (INV-6).

export const LARGEST = 2_306_867;            // 2.2 MiB
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

function shaped(sent) {
  return sent !== null && typeof sent === "object" && !Array.isArray(sent)
    && typeof sent.version === "string" && VERSION.test(sent.version)
    && typeof sent.system === "string" && sent.system.length <= SYSTEM_LONGEST
    && typeof sent.log === "string" && typeof sent.old === "string";
}

function base64(bytes) {
  let text = "";
  for (let at = 0; at < bytes.length; at += 0x8000) {
    text += String.fromCharCode(...bytes.subarray(at, at + 0x8000));
  }
  return btoa(text);
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
    body: JSON.stringify(body),
  });
  if (!reply.ok) throw new GitHubFailed(step, reply.status);
  return reply.json();
}

function reference() {
  const picked = crypto.getRandomValues(new Uint8Array(6));
  return Array.from(picked, (byte) => ALPHABET[byte % ALPHABET.length]).join("");
}

// The last lines of the log, and a fence no run of backticks in them closes.
function excerpt(log) {
  const lines = log.replace(/\n$/, "").split("\n").slice(-EXCERPT_LINES).join("\n");
  const cut = lines.slice(-EXCERPT_CHARACTERS);
  const longest = Math.max(0, ...(cut.match(/`+/g) || []).map((run) => run.length));
  const fence = "`".repeat(Math.max(3, longest + 1));
  return `${fence}text\n${cut}\n${fence}`;
}

async function file(env, sent) {
  const repository = env.REPOSITORY;
  const minted = await github(
    "token", "POST", `/app/installations/${env.INSTALLATION_ID}/access_tokens`,
    await appToken(env, Math.floor(Date.now() / 1000)),
    {repositories: [repository.split("/")[1]],
     permissions: {contents: "write", issues: "write"}});
  const named = reference();
  const folder = `logs/${named}`;
  for (const [name, text] of [["pressless.log", sent.log], ["pressless.log.1", sent.old]]) {
    await github("file", "PUT", `/repos/${repository}/contents/${folder}/${name}`, minted.token,
      {message: `Log ${named}: ${name}`, content: base64(new TextEncoder().encode(text))});
  }
  await github("issue", "POST", `/repos/${repository}/issues`, minted.token, {
    title: `Log ${named}: Pressless ${sent.version} on ${sent.system}`,
    body: `Files: \`${folder}/pressless.log\`, \`${folder}/pressless.log.1\`\n\n`
      + `The last lines of \`pressless.log\`:\n\n${excerpt(sent.log)}\n`,
  });
  return named;
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/log") {
      return answer(404, {error: "not found"});
    }
    const address = request.headers.get("CF-Connecting-IP") || "unknown";
    if (!(await env.SENDS.limit({key: address})).success) {
      return answer(429, {error: "too many sends; try again in a minute"});
    }
    if (Number(request.headers.get("Content-Length") || 0) > LARGEST) {
      return answer(413, {error: "too large"});
    }
    const raw = await readCapped(request.body, LARGEST);
    if (raw === null) return answer(413, {error: "too large"});
    let sent = null;
    try { sent = JSON.parse(new TextDecoder().decode(raw)); } catch { /* refused below */ }
    if (!shaped(sent)) return answer(400, {error: "not a log"});
    try {
      return answer(200, {reference: await file(env, sent)});
    } catch (error) {
      // The status only: a GitHub answer can quote what was sent.
      console.log(error instanceof GitHubFailed ? error.message : `failed: ${error.name}`);
      return answer(502, {error: "the log could not be filed"});
    }
  },
};
