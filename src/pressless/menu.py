"""The menu is the user's own HTML, the navigation furniture file; these edit
one page's link in it and keep every other byte (PRESS-0195 § 4.2), or move
its links' own bytes for the menu view (PRESS-0216 § 4.4).

Pure text in and out: the page editor reads and writes the file. Nothing here
parses the menu to write it back, which PRESS-0014 § 4.9 forbids, so a
writer's spacing and comments survive every edit.
"""

from __future__ import annotations

import html
import re

from pressless import blocks

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


# ------------------------------------------------- the menu view (PRESS-0216) --

_HOME = "{{UP}}index.html"
_PAGE = re.compile(r"\{\{UP\}\}pages/([a-z0-9-]+)\.html")
_NAV = re.compile(r"""\s+data-nav\s*=\s*(?:"[^"]*"|'[^']*')""", re.IGNORECASE)


class Refused(ValueError):
    """A menu save names a link the menu does not hold, or one it may not write."""


def _words(text: str, link: re.Match) -> str:
    return html.unescape(_TAG.sub("", text[link.start(1):link.end(1)])).strip()


def links(text: str) -> list[tuple[str, str]]:
    """Each link of a plain menu as its words, decoded and trimmed, and its
    address, decoded, in order. Raises Unusual on any other menu (§ 4.4)."""
    return [(_words(text, link), html.unescape(_href_value(link) or ""))
            for link in _plain(text)]


def _nav(address: str) -> str | None:
    """The data-nav the Builder marks the current page by, for an address
    naming a fixed page; None for any other."""
    if address == _HOME:
        return "Home"
    page = _PAGE.fullmatch(address)
    return page.group(1) if page else None


def _changed(text: str, link: re.Match, words: str, address: str) -> str:
    """The link's own bytes with only its words or its address changed."""
    own = text[link.start():link.end()]
    at = link.start()
    if words != _words(text, link):
        inside = text[link.start(1):link.end(1)]
        lead = inside[:len(inside) - len(inside.lstrip())]
        trail = inside[len(inside.rstrip()):]
        own = (own[:link.start(1) - at] + lead + html.escape(words, quote=False) + trail
               + own[link.end(1) - at:])
    if address != html.unescape(_href_value(link) or ""):
        tag_end = link.start(1) - at
        start_tag = own[:tag_end]
        found = _HREF.search(start_tag)
        if found is None:
            raise Refused("a menu link with no address cannot be given one")
        value = 1 if found.group(1) is not None else 2
        start_tag = (start_tag[:found.start(value)] + html.escape(address)
                     + start_tag[found.end(value):])
        start_tag = _NAV.sub("", start_tag)
        nav = _nav(address)
        if nav is not None:
            close = start_tag.rindex(">")
            start_tag = f'{start_tag[:close]} data-nav="{html.escape(nav)}"{start_tag[close:]}'
        own = start_tag + own[tag_end:]
    return own


def arranged(text: str, posted: object) -> str:
    """The menu with its links as `posted` lists them (§ 4.4). Each kept link
    keeps its bytes and the whitespace before it; the text outside the links
    stays where it is. Raises Refused on a post it cannot write, and Unusual
    on a menu that is not plain."""
    held = _plain(text)
    read = links(text)
    starts = [_before(text, link.start()) for link in held]
    gaps = [text[held[at].end():starts[at + 1]] for at in range(len(held) - 1)]
    space = text[starts[0]:held[0].start()]
    if not isinstance(posted, list):
        raise Refused("the menu save does not list its links")
    pieces, seen = [], set()
    for entry in posted:
        if not isinstance(entry, dict):
            raise Refused(f"{entry!r} is not a menu link")
        at, words, address = entry.get("at"), entry.get("words"), entry.get("href")
        if not isinstance(words, str) or not words.strip() or not isinstance(address, str):
            raise Refused("a menu link needs words and an address")
        if not blocks.address_allowed(address, mailto=True):
            raise Refused(f"a menu link may not go to {address!r}")
        if at is None:
            nav = _nav(address)
            marked = f' data-nav="{html.escape(nav)}"' if nav is not None else ""
            pieces.append(f'{space}<a href="{html.escape(address)}"{marked}>'
                          f"{html.escape(words.strip(), quote=False)}</a>")
            continue
        if (not isinstance(at, int) or isinstance(at, bool) or not 0 <= at < len(held)
                or at in seen):
            raise Refused(f"the menu save names link {at!r} wrongly")
        seen.add(at)
        link = held[at]
        own = text[starts[at]:link.start()]
        if (words.strip(), address) == read[at]:
            own += text[link.start():link.end()]
        else:
            own += _changed(text, link, words.strip(), address)
        pieces.append(own)
    out = [text[:starts[0]]]
    for number, piece in enumerate(pieces):
        out.append(piece)
        if number < len(gaps):
            out.append(gaps[number])
    out.extend(gaps[len(pieces):])
    out.append(text[held[-1].end():])
    return "".join(out)
