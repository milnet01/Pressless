"""What the maintainer's release scripts share: a refusal, and running a
program that refuses with what it printed. sign-release.py,
publish-jpeg-xl.py and relay-setup.py import it from beside them.
"""
from __future__ import annotations

import subprocess


class Refused(Exception):
    """A check failed: nothing was signed, published or deployed past it."""


def named(argv: list[str] | tuple[str, ...]) -> str:
    """The program and the first two words it was given, leaving out options
    and `-C <folder>`, so a failed `git -C <root> show` reads `git show ...`."""
    shown: list[str] = []
    words = iter(argv)
    for word in words:
        if word == "-C":
            next(words, None)
        elif not word.startswith("-"):
            shown.append(word)
    return " ".join(shown[:3])


def run(argv: list[str] | tuple[str, ...], run=None, **options) -> str:
    """What `argv` printed, read as UTF-8 whatever the locale, a byte UTF-8
    cannot read replaced. A failure is a refusal carrying what it said.
    `run` stands in for subprocess.run, so a test reaches no program."""
    try:
        return (run or subprocess.run)(list(argv), check=True, capture_output=True,
                                       encoding="utf-8", errors="replace", **options).stdout
    except subprocess.CalledProcessError as exc:
        said = (exc.stderr or exc.stdout or "").strip()
        raise Refused(f"{named(argv)} failed: {said}") from None
