"""The menu is the user's own HTML, the navigation furniture file; these edit
one page's link in it and keep every other byte (PRESS-0195 § 4.2).

Pure text in and out: the page editor reads and writes the file. Nothing here
parses the menu to write it back, which PRESS-0014 § 4.9 forbids, so a
writer's spacing and comments survive every edit.
"""

from __future__ import annotations

import html
import re

_LINK = re.compile(r"<a\b[^>]*>(.*?)</a\s*>", re.IGNORECASE | re.DOTALL)
_HREF = re.compile(r"""\bhref\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG = re.compile(r"</?([a-zA-Z][a-zA-Z0-9-]*)\b[^>]*>")
_PAGES = "{{UP}}pages/"
_SPACE = " \t\r\n"


class Unusual(Exception):
    """The menu is laid out in a way Pressless does not edit (§ 4.2)."""


def _address(name: str) -> str:
    return f"{_PAGES}{name}.html"


def _links(text: str) -> list[re.Match]:
    """Every link, read with the comments blanked out so a commented-out link
    is not one; the blanking keeps every offset."""
    masked = _COMMENT.sub(lambda found: " " * len(found.group(0)), text)
    return list(_LINK.finditer(masked))


def _href(link: re.Match) -> re.Match | None:
    """The href in the link's start tag, not in its words."""
    found = _HREF.search(link.string, link.start(), link.start(1))
    return found


def _href_value(link: re.Match) -> str | None:
    found = _href(link)
    if found is None:
        return None
    return found.group(1) if found.group(1) is not None else found.group(2)


def _before(text: str, at: int) -> int:
    """Where the run of whitespace ending at `at` starts."""
    while at > 0 and text[at - 1] in _SPACE:
        at -= 1
    return at


def links_to(text: str, name: str) -> tuple[tuple[int, int], ...]:
    """The offsets of each link whose href is exactly {{UP}}pages/<name>.html."""
    return tuple((link.start(), link.end()) for link in _links(text)
                 if _href_value(link) == _address(name))


def _plain(text: str) -> list[re.Match]:
    """The links of a plain menu: one <nav> holding links and nothing else but
    comments and text. Raises Unusual on any other menu."""
    links = _links(text)
    rest = _COMMENT.sub("", _LINK.sub("", _COMMENT.sub(
        lambda found: " " * len(found.group(0)), text)))
    tags = [(found.group(0).startswith("</"), found.group(1).lower())
            for found in _TAG.finditer(rest)]
    if not links or tags != [(False, "nav"), (True, "nav")]:
        raise Unusual("the menu is not one <nav> holding links")
    return links


def add(text: str, name: str, words: str) -> str:
    """A link to the page after the last link to a page, else after the last
    link, preceded by the whitespace that precedes the link it follows."""
    links = _plain(text)
    pages = [link for link in links if (_href_value(link) or "").startswith(_PAGES)]
    after = (pages or links)[-1]
    space = text[_before(text, after.start()):after.start()]
    link = (f'<a href="{_address(name)}" data-nav="{html.escape(name)}">'
            f"{html.escape(words)}</a>")
    return text[:after.end()] + space + link + text[after.end():]


def remove(text: str, name: str) -> str:
    """Each link to the page taken out, with the whitespace before it."""
    _plain(text)
    for start, end in reversed(links_to(text, name)):
        text = text[:_before(text, start)] + text[end:]
    return text


def rename(text: str, old: str, new: str, old_words: tuple[str, ...],
           new_words: str) -> str:
    """Each link to `old` pointed at `new`, its words changed where they are
    one of `old_words`. Any menu: only an attribute and a link's words move."""
    for link in reversed([link for link in _links(text)
                          if _href_value(link) == _address(old)]):
        inside = link.group(1)
        if html.unescape(inside).strip() in old_words:
            lead = inside[:len(inside) - len(inside.lstrip())]
            trail = inside[len(inside.rstrip()):]
            text = (text[:link.start(1)] + lead + html.escape(new_words) + trail
                    + text[link.end(1):])
        found = _href(link)
        value = 1 if found.group(1) is not None else 2
        text = text[:found.start(value)] + _address(new) + text[found.end(value):]
    return text
