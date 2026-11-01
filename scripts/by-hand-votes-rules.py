"""PRESS-0211 INV-6: run votes.RULES on the Firestore and Auth emulators.

Deliberately NOT in the gate and NOT in CI: it needs Java and firebase-tools,
which local-ci.sh does not assume. Run it by hand before a release, and after
any change to the rules:

    python3 scripts/by-hand-votes-rules.py --firebase <path to the firebase command>

Where `firebase` is on the PATH, --firebase can be left out. It exits non-zero
on any wrong answer, and where Java or firebase-tools is absent. --rules runs
another rules file instead, which is how a clause's removal is shown to fail.

A project id starting `demo-` needs no login and reaches no real service, so
nothing here leaves the machine. Real Firestore is PRESS-0211 § 7's hand check.
"""
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

PROJECT = "demo-pressless"
FIRESTORE_PORT = 18080
AUTH_PORT = 19099
DOCUMENTS = (f"http://127.0.0.1:{FIRESTORE_PORT}/v1/projects/{PROJECT}"
             "/databases/(default)/documents")
SIGN_UP = (f"http://127.0.0.1:{AUTH_PORT}/identitytoolkit.googleapis.com/v1/accounts:signUp"
           "?key=fake")
ENTRY = "2026-11-01-seaside"


def _call(method: str, url: str, body: dict | None = None, token: str | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            return answer.status, json.loads(answer.read() or b"null")
    except urllib.error.HTTPError as refused:
        return refused.code, refused.read().decode("utf-8", "replace")[:160]


def _visitor() -> tuple[str, str]:
    status, reply = _call("POST", SIGN_UP, {"returnSecureToken": True})
    assert status == 200, reply
    return reply["localId"], reply["idToken"]


def _vote(entry: str, uid: str, fields: dict, token: str | None) -> int:
    return _call("PATCH", f"{DOCUMENTS}/entries/{entry}/votes/{uid}", {"fields": fields}, token)[0]


def _value(number: int) -> dict:
    return {"value": {"integerValue": str(number)}}


def _count(entry: str, number: int) -> int | str:
    query = {"structuredAggregationQuery": {
        "structuredQuery": {"from": [{"collectionId": "votes"}], "where": {"fieldFilter": {
            "field": {"fieldPath": "value"}, "op": "EQUAL",
            "value": {"integerValue": str(number)}}}},
        "aggregations": [{"alias": "n", "count": {}}]}}
    status, reply = _call("POST", f"{DOCUMENTS}/entries/{entry}:runAggregationQuery", query)
    if status != 200:
        return f"refused {status}"
    return int(reply[0]["result"]["aggregateFields"]["n"]["integerValue"])


def probe() -> int:
    """Every row of INV-6, run inside `firebase emulators:exec`."""
    wrong = 0

    def show(label: str, got, want) -> None:
        nonlocal wrong
        wrong += got != want
        print(f"  [{'PASS' if got == want else 'FAIL'}] {label}: got {got!r}, want {want!r}")

    a_uid, a = _visitor()
    b_uid, b = _visitor()
    a_vote = f"{DOCUMENTS}/entries/{ENTRY}/votes/{a_uid}"
    show("voting with no sign-in is refused", _vote(ENTRY, a_uid, _value(1), None), 403)
    show("a visitor's first vote is allowed", _vote(ENTRY, a_uid, _value(1), a), 200)
    show("another visitor's first vote is allowed", _vote(ENTRY, b_uid, _value(-1), b), 200)
    show("writing a new vote under another's id is refused",
         _vote(ENTRY, "somebody-else", _value(1), a), 403)
    show("changing another's vote is refused", _vote(ENTRY, b_uid, _value(1), a), 403)
    show("a value of 5 is refused", _vote(ENTRY, a_uid, _value(5), a), 403)
    show("a value of another type is refused",
         _vote(ENTRY, a_uid, {"value": {"stringValue": "1"}}, a), 403)
    show("an extra field is refused",
         _vote(ENTRY, a_uid, {**_value(1), "spam": {"stringValue": "x"}}, a), 403)
    show("an entry key of the wrong shape is refused", _vote("garbage", a_uid, _value(1), a), 403)
    show("a key one character over the limit is refused",
         _vote("2026-11-01-" + "a" * 190, a_uid, _value(1), a), 403)
    show("a key at the limit is allowed", _vote("2026-11-01-" + "a" * 189, a_uid, _value(1), a),
         200)
    show("a write elsewhere is refused",
         _call("PATCH", f"{DOCUMENTS}/other/x", {"fields": {}}, a)[0], 403)
    show("a write to the entry itself is refused",
         _call("PATCH", f"{DOCUMENTS}/entries/{ENTRY}", {"fields": {}}, a)[0], 403)
    show("likes are counted with no sign-in", _count(ENTRY, 1), 1)
    show("dislikes are counted with no sign-in", _count(ENTRY, -1), 1)
    show("a visitor changes their vote", _vote(ENTRY, a_uid, _value(-1), a), 200)
    show("likes follow the change", _count(ENTRY, 1), 0)
    show("dislikes follow the change", _count(ENTRY, -1), 2)
    show("a visitor reads their own vote", _call("GET", a_vote, None, a)[0], 200)
    show("reading another's vote by its id is refused", _call("GET", a_vote, None, b)[0], 403)
    show("deleting another's vote is refused", _call("DELETE", a_vote, None, b)[0], 403)
    show("deleting with no sign-in is refused", _call("DELETE", a_vote)[0], 403)
    show("a visitor removes their own vote", _call("DELETE", a_vote, None, a)[0], 200)
    show("dislikes follow the removal", _count(ENTRY, -1), 1)
    print(f"{wrong} wrong" if wrong else "every answer was right")
    return 1 if wrong else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PRESS-0211 INV-6, on the emulators.")
    parser.add_argument("--firebase", help="the firebase command, if it is not on the PATH")
    parser.add_argument("--rules", type=Path, help="run this rules file instead of votes.RULES")
    parser.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    options = parser.parse_args()
    if options.probe:
        return probe()

    firebase = options.firebase or shutil.which("firebase")
    missing = [name for name, found in (("Java", shutil.which("java")),
                                        ("firebase-tools", firebase)) if not found]
    if missing:
        print(f"NOT RUN: {' and '.join(missing)} not found. See this script's docstring.")
        return 1

    from pressless import votes

    rules = options.rules.read_text(encoding="utf-8") if options.rules else votes.RULES
    with tempfile.TemporaryDirectory(prefix="pressless-votes-rules-") as held:
        work = Path(held)
        (work / "firestore.rules").write_text(rules, encoding="utf-8")
        (work / "firebase.json").write_text(json.dumps({
            "firestore": {"rules": "firestore.rules"},
            "emulators": {"firestore": {"port": FIRESTORE_PORT, "host": "127.0.0.1"},
                          "auth": {"port": AUTH_PORT, "host": "127.0.0.1"},
                          "ui": {"enabled": False}, "singleProjectMode": True},
        }), encoding="utf-8")
        inner = shlex.join([sys.executable, str(Path(__file__).resolve()), "--probe"])
        run = subprocess.run(
            [str(Path(firebase).resolve()) if options.firebase else firebase,
             "emulators:exec", "--only", "firestore,auth", "--project", PROJECT, inner],
            cwd=work, check=False)
    return run.returncode


if __name__ == "__main__":
    raise SystemExit(main())
