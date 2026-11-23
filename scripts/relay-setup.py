"""Set the log relay up, once (PRESS-0436 § 4.4). Run from the repository
root, with `npx wrangler login` already done:

    .venv/bin/python scripts/relay-setup.py

It makes the GitHub App from a manifest (you press Create on GitHub), waits
while you install it on the logs repository alone, fills the App's ids into
relay/wrangler.jsonc, deploys the Worker, gives it the App's key as a secret,
and sends a test log whose issue it then closes. The key is kept in
~/.config/pressless, owner-only, and never printed. Run again, it reuses the
App it made. An App made on GitHub's own form instead:

    .venv/bin/python scripts/relay-setup.py --key <downloaded .pem> --app-id <id> [--slug <slug>]

Linux only: on Windows `npx` is `npx.cmd`, and owner-only is not enforced.
"""
from __future__ import annotations

import argparse
import base64
import html
import http.server
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _refusing  # noqa: E402 -- beside this script, shared with sign-release.py

ROOT = Path(__file__).resolve().parent.parent
RELAY = ROOT / "relay"
SETTINGS = RELAY / "wrangler.jsonc"
REPOSITORY = "milnet01/pressless-logs"
KEPT = Path.home() / ".config" / "pressless"
KEY = KEPT / "log-relay-app.pem"
APP = KEPT / "log-relay-app.json"
GITHUB = "https://api.github.com"
WAIT_SECONDS = 60 * 60


def _ask(method: str, url: str, token: str | None = None,
         body: dict | None = None) -> dict | list:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "pressless-relay-setup",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers,  # noqa: S310 -- https only
                                     method=method)
    with urllib.request.urlopen(request, timeout=60) as answer:  # noqa: S310 -- https only
        text = answer.read()
    return json.loads(text) if text else {}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _jwt(app_id: int) -> str:
    """The App's own token, signed by openssl with the kept key."""
    now = int(time.time())
    unsigned = (_b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()) + "."
                + _b64url(json.dumps({"iat": now - 60, "exp": now + 540,
                                      "iss": str(app_id)}).encode()))
    signed = subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(KEY)],  # noqa: S603, S607
                            input=unsigned.encode(), capture_output=True, check=True).stdout
    return f"{unsigned}.{_b64url(signed)}"


def _make_app() -> dict:
    """Serve the manifest page, wait for GitHub's redirect, and exchange its code."""
    state = secrets.token_urlsafe(16)
    found: dict[str, str] = {}

    class Page(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802 -- http.server's name
            asked = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(asked.query)
            if asked.path == "/done" and query.get("state") == [state] and "code" in query:
                found["code"] = query["code"][0]
                said = "<p>Done. Go back to the terminal.</p>"
            else:
                # `port` is the enclosing function's, read when a request
                # arrives, by which time the server below has set it.
                manifest = json.dumps({
                    "name": "Pressless log relay",
                    "url": "https://github.com/milnet01/Pressless",
                    "redirect_url": f"http://127.0.0.1:{port}/done",
                    "public": False,
                    "hook_attributes": {"active": False},
                    "default_permissions": {"contents": "write", "issues": "write"},
                })
                said = ('<form method="post" action="https://github.com/settings/apps/new?state='
                        f'{state}"><input type="hidden" name="manifest" '
                        f'value="{html.escape(manifest, quote=True)}">'
                        "<p><button>Make the GitHub App</button></p></form>"
                        "<script>document.forms[0].submit()</script>")
            body = f"<!doctype html><meta charset=utf-8>{said}".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    server = http.server.HTTPServer(("127.0.0.1", 0), Page)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Opening http://127.0.0.1:{port}/ -- on GitHub, press Create GitHub App.")
    webbrowser.open(f"http://127.0.0.1:{port}/")
    waited = 0
    while "code" not in found and waited < WAIT_SECONDS:
        time.sleep(1)
        waited += 1
    server.shutdown()
    if "code" not in found:
        raise SystemExit("GitHub did not come back; nothing was made")
    made = _ask("POST", f"{GITHUB}/app-manifests/{found['code']}/conversions")
    kept = _keep(made["pem"].encode("ascii"), made["id"], made["slug"])
    print(f"Made the App {made['slug']} (id {made['id']}).")
    return kept


def _write_private(path: Path, data: bytes) -> None:
    """`path` holds `data` whole, owner-only, or is left as it was: a
    part-written file is never in its place."""
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _refuse_half_kept() -> None:
    """A key with no App file, or an App file with no key, is what a run
    stopped part way leaves. Making another App would replace the only copy
    of the first one's key, so the next step is the person's."""
    if KEY.exists() != APP.exists():
        held, missing = (KEY, APP) if KEY.exists() else (APP, KEY)
        raise SystemExit(f"refused: {held} is kept but {missing} is not, so an earlier run "
                         "stopped part way. Remove the App it made on GitHub and both files, "
                         "or pass that App's key with --key, then run this again")


def _keep(key: bytes, app_id: int, slug: str) -> dict:
    """Keep the App's key, then the file naming the App. The App file is
    written last, so a stop between the two leaves a key alone, which
    _refuse_half_kept refuses rather than replacing."""
    KEPT.mkdir(parents=True, exist_ok=True)
    _write_private(KEY, key)
    kept = {"id": app_id, "slug": slug}
    _write_private(APP, json.dumps(kept).encode("utf-8"))
    return kept


def _installation(app: dict) -> int:
    """Wait for the App to be installed on the logs repository, alone."""
    owner = REPOSITORY.split("/")[0]
    print(f"Opening the install page -- choose 'Only select repositories', pick "
          f"{REPOSITORY.split('/')[1]}, then press Install.")
    webbrowser.open(f"https://github.com/apps/{app['slug']}/installations/new")
    waited = 0
    while waited < WAIT_SECONDS:
        for found in _ask("GET", f"{GITHUB}/app/installations", _jwt(app["id"])):
            if found["account"]["login"] == owner:
                token = _ask("POST", f"{GITHUB}/app/installations/{found['id']}/access_tokens",
                             _jwt(app["id"]))["token"]
                reach = [repo["full_name"] for repo in
                         _ask("GET", f"{GITHUB}/installation/repositories", token)["repositories"]]
                if reach != [REPOSITORY]:
                    raise SystemExit(f"The App reaches {len(reach)} repositories; install it on "
                                     f"{REPOSITORY} alone, then run this again")
                return int(found["id"])
        time.sleep(5)
        waited += 5
    raise SystemExit("The App was not installed in time; run this again")


def _wrangler(*arguments: str, given: str | None = None) -> str:
    try:
        return _refusing.run(["npx", "--yes", "wrangler", *arguments], cwd=RELAY, input=given)
    except _refusing.Refused as exc:
        raise SystemExit(f"refused: {exc}") from None


def _made_by_hand(key: Path, app_id: int, slug: str) -> dict:
    """An App made on GitHub's own form: keep its downloaded key, owner-only,
    and remove the download. For a browser that will not post the manifest
    signed in, which a cross-site form needs. A key already kept is another
    App's, perhaps live, so it is never replaced."""
    if KEY.exists() and KEY.resolve() != key.resolve():
        raise SystemExit(f"refused: {KEY} already holds a key; remove it first if that "
                         "App is gone")
    kept = _keep(key.read_bytes(), app_id, slug)
    if key.resolve() != KEY.resolve():
        key.unlink()
    return kept


def _with_ids(text: str, app_id: int, installation: int) -> str:
    """relay/wrangler.jsonc's text with both ids filled. A missing key is a
    refusal: deploying with the old ids would fail only at the first log."""
    for name, value in (("APP_ID", app_id), ("INSTALLATION_ID", installation)):
        text, found = re.subn(rf'"{name}": "[^"]*"', f'"{name}": "{value}"', text)
        if found != 1:
            raise SystemExit(f'refused: {SETTINGS} holds {found} "{name}" entries, not one')
    return text


def _test_log(relay: str) -> str:
    """Send the test log; its reference, or a refusal naming what the
    relay's answer means (PRESS-0436 § 4.3)."""
    request = urllib.request.Request(  # noqa: S310 -- https only
        relay, method="POST", headers={"Content-Type": "application/json",
                                       "User-Agent": "pressless-relay-setup"},
        data=json.dumps({"version": "setup", "system": "relay setup test",
                         "log": "a test log from scripts/relay-setup.py\n", "old": ""}).encode())
    try:
        with urllib.request.urlopen(request, timeout=60) as answer:  # noqa: S310 -- https only
            return json.loads(answer.read())["reference"]
    except urllib.error.HTTPError as exc:
        meaning = {429: "it takes one log a minute; wait a minute and run this again",
                   502: "it could not reach GitHub; run `npx wrangler tail` in relay/ to see "
                        "the failing step, then run this again"}
        raise SystemExit(f"refused: the relay answered {exc.code} to the test log: "
                         f"{meaning.get(exc.code, 'see `npx wrangler tail` in relay/')}") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Set the log relay up (PRESS-0436 § 4.4).")
    parser.add_argument("--key", type=Path, help="an App made by hand: its downloaded .pem")
    parser.add_argument("--app-id", type=int, help="that App's id")
    parser.add_argument("--slug", default="pressless-log-relay", help="that App's slug")
    given = parser.parse_args(argv)
    if (given.key is None) != (given.app_id is None):
        parser.error("--key and --app-id go together")
    if given.key is not None:
        app = _made_by_hand(given.key, given.app_id, given.slug)
    elif APP.is_file() and KEY.is_file():
        app = json.loads(APP.read_text(encoding="utf-8"))
    else:
        _refuse_half_kept()
        app = _make_app()
    installation = _installation(app)
    text = _with_ids(SETTINGS.read_text(encoding="utf-8"), app["id"], installation)
    SETTINGS.write_text(text, encoding="utf-8", newline="\n")
    deployed = _wrangler("deploy")
    address = re.search(r"https://pressless-logs\.[a-z0-9-]+\.workers\.dev", deployed)
    if not address:
        raise SystemExit("deployed, but wrangler named no workers.dev address")
    pkcs8 = subprocess.run(["openssl", "pkcs8", "-topk8", "-nocrypt", "-in", str(KEY)],  # noqa: S603, S607
                           capture_output=True, check=True).stdout
    # The Worker is deployed first: `secret put` needs it to exist.
    _wrangler("secret", "put", "APP_KEY", given=pkcs8.decode("ascii"))
    relay = f"{address.group(0)}/log"
    print(f"Deployed. Sending a test log to {relay}.")
    time.sleep(10)        # a new secret takes a moment to reach every location
    reference = _test_log(relay)
    token = _ask("POST", f"{GITHUB}/app/installations/{installation}/access_tokens",
                 _jwt(app["id"]))["token"]
    # GitHub lists a new issue a few seconds after making it.
    for _ in range(6):
        found = [issue for issue in _ask("GET", f"{GITHUB}/repos/{REPOSITORY}/issues"
                                                "?state=open&per_page=50", token)
                 if issue["title"].startswith(f"Log {reference}:")]
        if found:
            _ask("PATCH", found[0]["url"], token, {"state": "closed"})
            print(f"The test log arrived as {reference}, and its issue is closed.")
            break
        time.sleep(5)
    else:
        print(f"The relay answered {reference}, but no open issue carries it -- look in "
              f"{REPOSITORY}.")
    print(f"Set sendlog.RELAY to {relay!r}, and commit relay/wrangler.jsonc.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
