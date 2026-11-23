"""Stamp a language file's new translations, and report what needs
translating (PRESS-0241 § 4.5).

A translation comes back as a plain string per key. `stamp` turns each one
into the pair the app reads, [made-from, words], made from today's English.
An entry already a pair keeps its made-from, so English reworded since it
was translated still reads as out of date. Run from the repository root:

    python scripts/translations.py stamp <code>
    python scripts/translations.py --report

The report lists, per language in words.LANGUAGES, each key missing or made
from other English, and each manual file or video caption it lacks. It never
fails the gate (decision 8); the release checklist runs it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pressless import manual, safe_write, words  # noqa: E402 -- after the path is set


def stamp(path: Path) -> int:
    """Give each plain-string entry in `path` its made-from; return how many.
    A key ENGLISH does not hold is refused, so a misspelt key is not kept."""
    held = json.loads(path.read_text(encoding="utf-8"))
    unknown = sorted(key for key in held["words"] if key not in words.ENGLISH)
    if unknown:
        raise SystemExit(f"{path.name}: no such keys: {', '.join(unknown)}")
    stamped = 0
    for key, value in held["words"].items():
        if isinstance(value, str):
            held["words"][key] = [words.made_from(words.ENGLISH[key]), value]
            stamped += 1
    held["words"] = dict(sorted(held["words"].items()))
    # Whole or not at all, LF on any system: the file holds pasted
    # translations that are not yet committed anywhere.
    safe_write.write_whole(path, json.dumps(held, ensure_ascii=False, indent=1) + "\n",
                           prefix=f".{path.name}.")
    return stamped


def report(folder: Path = words.FOLDER, manual_folder: Path = manual.FOLDER,
           codes: tuple[str, ...] | None = None) -> list[str]:
    """One line per thing a language lacks."""
    lines = []
    videos = sorted(path.name.split(".")[0]
                    for path in (manual_folder / "media").glob(f"*.{manual.FALLBACK}.vtt"))
    translated = tuple(code for code in words.LANGUAGES if code != manual.FALLBACK)
    for code in translated if codes is None else codes:
        path = folder / f"{code}.json"
        held = json.loads(path.read_text(encoding="utf-8"))["words"] if path.is_file() else {}
        for key, english in words.ENGLISH.items():
            entry = held.get(key)
            if entry is None:
                lines.append(f"{code} missing {key}")
            elif not isinstance(entry, list) or entry[0] != words.made_from(english):
                lines.append(f"{code} out of date {key}")
        if not (manual_folder / f"{code}.txt").is_file():
            lines.append(f"{code} missing the manual, {code}.txt")
        lines += [f"{code} missing the captions {stem}.{code}.vtt" for stem in videos
                  if not (manual_folder / "media" / f"{stem}.{code}.vtt").is_file()]
    return lines


def main(argv: list[str]) -> int:
    if argv == ["--report"]:
        found = report()
        print("\n".join(found) if found else "every language is up to date")
        return 0
    if len(argv) == 2 and argv[0] == "stamp":
        print(f"stamped {stamp(words.FOLDER / f'{argv[1]}.json')}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
