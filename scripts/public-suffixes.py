"""Write src/pressless/_public_suffixes.py from the public suffix list (PRESS-0342).

The domain wizard asks it whether a typed name is a whole name someone bought,
such as example.co.za, or a part of one, such as blog.example.com. Only the
list's ICANN section is kept: those are the names sold to the public. Its
private section names services such as github.io, which the wizard refuses.

Refresh it now and then, as a dependency (dependencies.md):

    curl -sSfL -o <folder>/public_suffix_list.dat https://publicsuffix.org/list/public_suffix_list.dat
    python3 scripts/public-suffixes.py <folder>/public_suffix_list.dat
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "src" / "pressless" / "_public_suffixes.py"


def ascii_rule(rule: str) -> str:
    """A rule in the form the wizard compares, each label as IDNA ASCII."""
    mark = "!" if rule.startswith("!") else ""
    labels = rule.removeprefix("!").split(".")
    return mark + ".".join(label if label == "*" else label.encode("idna").decode("ascii")
                           for label in labels)


def main(source: Path) -> None:
    text = source.read_text(encoding="utf-8")
    version = re.search(r"^// VERSION: (\S+)$", text, re.M).group(1)
    commit = re.search(r"^// COMMIT: (\S+)$", text, re.M).group(1)
    icann = text.split("// ===BEGIN ICANN DOMAINS===", 1)[1].split(
        "// ===END ICANN DOMAINS===", 1)[0]
    rules = sorted({ascii_rule(line.strip().lower()) for line in icann.splitlines()
                    if line.strip() and not line.startswith("//")})
    body = "\n".join(f'    "{rule}",' for rule in rules)
    TARGET.write_text(
        '"""The public suffix list\'s ICANN section, as the domain wizard reads it.\n\n'
        "Made by scripts/public-suffixes.py from https://publicsuffix.org/list/.\n"
        f"Version {version},\ncommit {commit}.\nDo not edit by hand.\n\n"
        "The list is the Mozilla Foundation's, under the Mozilla Public License 2.0:\n"
        'https://mozilla.org/MPL/2.0/\n"""\n\n'
        f"RULES = frozenset((\n{body}\n))\n",
        encoding="utf-8")
    print(f"{len(rules)} rules, version {version}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
