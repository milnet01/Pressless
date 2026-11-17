"""The Import anyone runs: a whole WordPress site into an empty Store
(PRESS-0125 §§ 4.5 to 4.7).

`bring_in` reads the export, converts every body, and writes every Store
file into the site's own `import/work/` through Store calls, moving each
held file in from `import/media/`. Only once all of it is written does it
move each folder of `import/work/` into the site's folder, by rename, with
`import/moving` saying the moves have begun; `finish` completes moves a stop
left part done. So the Store is either untouched or holds the whole site
(INV-7 there).
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import unicodedata
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from pressless import (
    blocks,
    builder,
    look,
    menu,
    os_reason,
    sitefile,
    starter,
    store,
    templates,
    zip_member,
)

from . import (
    _DRAFT_STATUSES,
    _RESIZED,
    MISSING,
    Dropped,
    ImportStopped,
    Report,
    _attachments,
    _convert,
    _counts,
    _entry,
    _field,
    _Item,
    _items,
    _old_site,
    _place_refused,
    _resolve,
    _upload_path,
    _waiting,
    _write_entries,
    _writing,
    read,
    resolve_slug,
)
from ._html import _host, bare_host, prepared, wordpress_markup

IMPORT_FOLDER = "import"   # in the site's folder; never published (§ 4.2)
_WORK = "work"
MEDIA_FOLDER = "media"     # in IMPORT_FOLDER: the fetched files; finish deletes it
FOLDER = "folder"          # in IMPORT_FOLDER: a folder of pages (PRESS-0210)
_MOVING = "moving"
# In IMPORT_FOLDER: each held file moved into import/work/, one JSON line
# each, written before it moves, so a stop can put every one back.
_MOVED = "moved.jsonl"
_NOT_EMPTY = "this site already holds a site, and Import writes only into an empty one"
_NOT_PUT_BACK = ("files an earlier try moved could not be put back where they were. Nothing "
                 "was lost. Close anything using the site's folder and try again")
# What becomes something, and what is the Report's count of the rest (§ 4.3).
_CARRIED_TYPES = frozenset({"post", "page", "attachment", "nav_menu_item", "wp_navigation"})
_NAVIGATION = "navigation"
_UNPUBLISHED_PAGE = "a page WordPress had not published, so it arrived as a draft"
_NO_FEATURED = "its featured image, which could not be placed"


# ---------------------------------------------------------- pages (§ 4.6) ----


@dataclass
class _Page:
    post_id: str
    wanted: str
    title: str
    order: int
    body: str
    link: str
    comments: int
    name: str = ""
    dropped: list[str] = field(default_factory=list)


def _pages(channel, ns) -> list[_Page]:
    """Each published page. A Pressless page is always on the site, so a page
    WordPress kept off the web is a draft entry instead (§ 4.5)."""
    pages = []
    for item in channel.findall("item"):
        if (_field(item, "post_type", ns) != "page"
                or _field(item, "status", ns) != "publish"):
            continue
        post_id = _field(item, "post_id", ns)
        title = (item.findtext("title") or "").strip()
        try:
            order = int(_field(item, "menu_order", ns) or 0)
        except ValueError:
            order = 0
        pages.append(_Page(
            post_id=post_id, wanted=resolve_slug(_field(item, "post_name", ns), post_id),
            title=title, order=order, body=item.findtext("content:encoded", "", ns) or "",
            link=(item.findtext("link") or "").strip(),
            comments=len(item.findall("wp:comment", ns))))
    return pages


def _page_refused(name: str) -> bool:
    try:
        store.html_path_for(Path(), store.PAGES_FOLDER, name)
    except store.StoreError:
        return True
    return False


def _name_pages(pages: list[_Page], site_title: str) -> list[tuple[str, str]]:
    """The front page becomes `index`: the page whose slug is `home` or whose
    title is the site's own, else the first by menu order. Every other page
    keeps its slug, or takes `<slug>-<post id>` where it is taken or refused."""
    if not pages:
        return []
    front = next((page for page in pages
                  if page.wanted == "home" or (site_title and page.title == site_title)),
                 None) or min(pages, key=lambda page: page.order)
    front.name = "index"
    taken, renamed = {"index"}, []
    for page in pages:
        if page is front:
            continue
        name = page.wanted
        if name in taken or _page_refused(name):
            name = f"{page.wanted}-{page.post_id}"
            if name in taken or _page_refused(name):
                raise ImportStopped(f"page {page.post_id} has no name left to take: {name}")
            renamed.append((page.wanted, name))
        page.name = name
        taken.add(name)
    return renamed


_ADDRESSED = re.compile(r"""(\b(?:src|href|srcset|poster)\s*=\s*)(["'])(.*?)\2""",
                        re.I | re.S)


def _addresses(body: str, up: str, web: Mapping[str, str], old_site: str
               ) -> tuple[str, list[str]]:
    """Each address under the old site's uploads folder whose file Import
    holds, pointed at the Store's copy from a page `up` from the root; any
    other is left as it is and listed."""
    listed: list[str] = []
    old = bare_host(old_site)

    def token(found: re.Match) -> str:
        address = found.group(0)
        decoded = html.unescape(address)
        place = _upload_path(decoded)
        if place is None or _host(decoded) not in ("", old):
            return address
        found = web.get(place) or web.get(_RESIZED.sub("", place))
        if found is None:
            listed.append(f"an address still pointing at the old site: {decoded}")
            return address
        return up + found

    def attribute(found: re.Match) -> str:
        return (found.group(1) + found.group(2) + re.sub(r"[^\s,]+", token, found.group(3))
                + found.group(2))

    return _ADDRESSED.sub(attribute, body), listed


def _page_html(page: _Page, sheets: tuple[str, ...], web: Mapping[str, str],
               old_site: str) -> str:
    """The page in starter.new_page's shape, its body as its area after the
    markup rule, and its addresses moved; Blocks reads what sections it can,
    and the rest is code."""
    root = page.name == "index"
    body = prepared(page.body, wordpress_markup)
    body, listed = _addresses(body, "" if root else "../", web, old_site)
    page.dropped.extend(listed)
    text = starter.new_page(builder.HOME_NAV if root else page.name, page.title, sheets,
                            main=body, root=root)
    try:
        adopted = blocks.adopt(text, builder.furniture_spans(page.name, text))
    except builder.BuildStopped:
        adopted = None
    return adopted or text


# ----------------------------------------------------------- the menu ----

_NAV_BLOCK = re.compile(
    r"<!--\s*(/)?wp:(navigation-link|navigation-submenu)(?:\s+(\{.*?\}))?\s*(/)?-->", re.S)
_TAGS = re.compile(r"<[^>]*>")


@dataclass(frozen=True)
class _Link:
    words: str
    address: str
    child: bool


def _same(one: str, other: str) -> bool:
    def bare(address: str) -> str:
        parsed = urlparse(address.strip())
        return f"{_host(address)}{parsed.path.rstrip('/')}"
    return bool(one and other) and bare(one) == bare(other)


def _target(targets: Mapping[str, tuple[str, str, str]], object_id: str, url: str
            ) -> tuple[str, str] | None:
    """A carried page's or entry's (title, address), by its post id or its
    old address."""
    found = targets.get(object_id)
    if found is None:
        found = next((target for target in targets.values() if _same(target[2], url)), None)
    return None if found is None else (found[0], found[1])


def _block_links(body: str, targets) -> list[_Link]:
    links, depth = [], 0
    for found in _NAV_BLOCK.finditer(body):
        closing, kind, attributes, self_closed = found.groups()
        if closing:
            depth = max(0, depth - 1)
            continue
        try:
            read_in = json.loads(attributes or "{}")
        except ValueError:
            read_in = {}
        if not isinstance(read_in, dict):
            read_in = {}
        url = str(read_in.get("url") or "")
        hit = _target(targets, str(read_in.get("id") or ""), url) if read_in.get(
            "kind", "post-type") == "post-type" else None
        words = html.unescape(_TAGS.sub("", str(read_in.get("label") or ""))).strip()
        links.append(_Link(words or (hit[0] if hit else url), hit[1] if hit else url,
                           depth > 0))
        if kind == "navigation-submenu" and not self_closed:
            depth += 1
    return links


def _menu_items(items, ns, targets) -> list[_Link]:
    read_in = []
    for item in items:
        meta = {_field(each, "meta_key", ns): _field(each, "meta_value", ns)
                for each in item.findall("wp:postmeta", ns)}
        try:
            order = int(_field(item, "menu_order", ns) or 0)
        except ValueError:
            order = 0
        hit = (_target(targets, meta.get("_menu_item_object_id", ""), "")
               if meta.get("_menu_item_type") == "post_type" else None)
        url = meta.get("_menu_item_url", "")
        words = (item.findtext("title") or "").strip()
        read_in.append((_field(item, "post_id", ns), meta.get("_menu_item_menu_item_parent", "0"),
                        order, _Link(words or (hit[0] if hit else url),
                                     hit[1] if hit else url, False)))
    parents = {post_id: parent for post_id, parent, _order, _link in read_in}
    orders = {post_id: order for post_id, _parent, order, _link in read_in}

    def root(post_id: str) -> str:
        seen = set()
        while parents.get(post_id, "0") not in ("", "0") and post_id not in seen:
            seen.add(post_id)
            post_id = parents[post_id]
        return post_id

    # A child joins the list after its parent (§ 4.6).
    ordered = sorted(read_in, key=lambda row: (orders.get(root(row[0]), 0),
                                               row[1] not in ("", "0"), row[2]))
    return [_Link(link.words, link.address, parent not in ("", "0"))
            for _post_id, parent, _order, link in ordered]


def _menu(channel, ns, targets) -> tuple[list[_Link], tuple[str, ...]]:
    """One menu's links, and the name of each menu, the one read first:
    the first wp_navigation, else the nav_menu with the most items."""
    navigations, classic = [], {}
    for item in channel.findall("item"):
        kind = _field(item, "post_type", ns)
        if kind == "wp_navigation" and _field(item, "status", ns) != "trash":
            navigations.append(item)
        elif kind == "nav_menu_item":
            for term in item.findall("category"):
                if term.get("domain") == "nav_menu":
                    name = (term.text or term.get("nicename") or "").strip()
                    classic.setdefault(name, []).append(item)
    names = [(item.findtext("title") or "").strip() for item in navigations]
    by_size = sorted(classic, key=lambda name: -len(classic[name]))
    names += by_size
    if navigations:
        links = _block_links(navigations[0].findtext("content:encoded", "", ns) or "",
                             targets)
    elif by_size:
        links = _menu_items(classic[by_size[0]], ns, targets)
    else:
        links = []
    return links, tuple(names)


def _navigation(links: list[_Link], listed: list[str]) -> str:
    """The links in the starter's navigation shape, written as the Menu
    screen writes them, so menu.links reads them back."""
    shape = starter.navigation()
    posted = []
    for link in links:
        if link.child:
            listed.append(f"the menu link {link.words}, under another, now beside it")
        if not link.address or not link.words or not blocks.address_allowed(
                link.address, mailto=True):
            listed.append(f"the menu link {link.words or link.address}, which has no address "
                          f"a menu may hold, left out")
            continue
        if not link.address.startswith("{{UP}}"):
            listed.append(f"the menu link {link.words} still goes to {link.address}")
        posted.append({"at": None, "words": link.words, "href": link.address})
    if not posted:
        # The starter's own Home link, so the menu is never empty.
        home = menu.links(shape)[0]
        posted = [{"at": 0, "words": home[0], "href": home[1]}]
    return menu.arranged(shape, posted)


# -------------------------------------------------- media download (§ 4.4) ----


def unpack_media(source: Path, media: Path, missing: tuple[str, ...] | list[str],
                 room: Callable[[], int]) -> tuple[str, ...]:
    """Fill each missing place from a media download: a member whose name is
    the place, or ends in `/<place>`, is unpacked to `media/<place>`. Every
    member is checked first, as a site file's are, and the members taken must
    fit `room()`; a refused download writes nothing. A place `_place` would
    refuse is never filled, nor one a member larger than the Builder keeps
    would fill. Returns the places filled."""
    # The places are fetch_all's keys, and one with no usable place is keyed
    # by its raw address, which can be absolute: joined onto `media` it would
    # replace it outright. So each place is checked here, not only the names.
    inside = media.resolve()
    try:
        with zipfile.ZipFile(source) as held:
            infos = held.infolist()
            for info in infos:
                if not zip_member.stays_inside(info.filename):
                    raise ImportStopped("the media download holds a name outside its folder")
                if sitefile.is_link(info):
                    raise ImportStopped("the media download holds a link")
            named = [(_member_name(info), info) for info in infos if not info.is_dir()]
            wanted: dict[str, zipfile.ZipInfo] = {}
            for place in missing:
                if (_place_refused(place) is not None
                        or not (media / place).resolve().is_relative_to(inside)
                        or (media / place).is_file()):
                    continue
                key = unicodedata.normalize("NFC", place)
                for name, info in named:
                    if name == key or name.endswith(f"/{key}"):
                        if info.file_size <= builder.FILE_LARGEST:
                            wanted[place] = info
                        break
            if sum(info.file_size for info in wanted.values()) > room():
                raise ImportStopped("the media download's files are larger than the room "
                                    "on this drive")
            for place, info in wanted.items():
                target = media / place
                target.parent.mkdir(parents=True, exist_ok=True)
                part = target.with_name(f".{target.name}.part")
                try:
                    with held.open(info) as unpacked, open(part, "wb") as out:
                        shutil.copyfileobj(unpacked, out)
                    part.replace(target)
                finally:
                    part.unlink(missing_ok=True)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ImportStopped(f"the media download could not be read "
                            f"({type(exc).__name__})") from None
    return tuple(sorted(wanted))


def _member_name(info: zipfile.ZipInfo) -> str:
    """A member's name as its maker wrote it, for matching only. zipfile
    reads a name without the UTF-8 flag as cp437, though most tools that
    leave the flag off write UTF-8; and macOS decomposes accents."""
    name = info.filename
    if not info.flag_bits & 0x800:
        try:
            name = name.encode("cp437").decode("utf-8")
        except UnicodeError:
            pass
    return unicodedata.normalize("NFC", name)


# ------------------------------------------------- writing (§ 4.7) ----


def bring_in(export: Path, media: Path, into: Path, layout: str, *,
             unfetched: Mapping[str, str] | None = None,
             keep: Callable[[Report], None] | None = None) -> Report:
    """§ 4.7, in order: read and resolve slugs; convert every body; write
    every Store file into import/work/, moving each held file in from
    `media`; then move each folder into `into`. `layout` is one of
    starter.LOOKS; `unfetched` is each place the fetch could not have, with
    why (fetch.fetch_all's answer), so the Report says so. `keep` is given
    the Report before the first move, so a stop during the moves loses it
    not (§ 4.8)."""
    export, media, into = Path(export), Path(media), Path(into)
    unfetched = unfetched or {}
    recover(into)
    if _holds_a_site(into):
        raise ImportStopped(_NOT_EMPTY)
    # The wizard's check_look refuses an unknown look first; any other
    # caller gets the first look rather than a stop.
    layout = layout if layout in starter.LOOKS else starter.LOOKS[0]

    read_in = read(export)
    channel, ns = read_in.channel, read_in.ns
    site_title = (channel.findtext("title") or "").strip()
    items = _items(channel, ns, page_statuses=_DRAFT_STATUSES, titled_drafts=True,
                   any_date=True)
    renamed = _resolve(items)
    pages = _pages(channel, ns)
    renamed += _name_pages(pages, site_title)
    old_site = _old_site(channel, ns)
    kept, by_address, by_id, unheld = _held(channel, ns, media)
    web = {place: builder.web_photograph(name) if folder == store.PHOTOGRAPHS_FOLDER
           else builder.web_file(name) for place, (folder, name) in kept.items()}

    bodies = {item.post_id: _convert(item, wordpress_markup, by_address, by_id, old_site)
              for item in items}
    for item in items:
        if item.page:
            item.dropped.insert(0, _UNPUBLISHED_PAGE)
        if item.featured:
            bodies[item.post_id] = _featured(item, bodies[item.post_id], by_id)
    entries = {item.post_id: _entry(item, bodies[item.post_id]) for item in items}
    links, menus = _menu(channel, ns, _targets(channel, ns, pages, items, entries))
    menu_listed: list[str] = []
    navigation = _navigation(links, menu_listed)

    def write(work: Path, move: Callable[[Path, Path], None]) -> None:
        _write_entries(work, items, entries)
        with _writing("the look"):
            look.save(work, look.defaults(layout), "")
            sheets = builder.stylesheets(work)
        for page in pages:
            with _writing(f"the page {page.name}"):
                store.write_html(work, store.PAGES_FOLDER, page.name,
                                 _page_html(page, sheets, web, old_site))
        if not pages:
            with _writing("the page index"):
                identity = store.read_identity(into)
                store.write_html(work, store.PAGES_FOLDER, "index", starter.home_page(
                    identity.name if identity is not None else site_title))
        for name, text in (("header", starter.header()), ("footer", starter.footer()),
                           (_NAVIGATION, navigation)):
            with _writing(f"the furniture file {name}"):
                store.write_html(work, store.FURNITURE_FOLDER, name, text)
        with _writing("the templates"):
            templates.seed(work)
        with _writing("the journal switch"):
            store.write_journal(work, any(not item.page for item in items))
        for place, (folder, name) in kept.items():
            with _writing(f"the file {place}"):
                move(media / place, store.photograph_path_for(work, name)
                     if folder == store.PHOTOGRAPHS_FOLDER
                     else store.file_path_for(work, name))
        # After the pages, which list what they dropped as they are written.
        made.append(Report(
            **_counts(items),
            photographs=sum(1 for folder, _name in kept.values()
                            if folder == store.PHOTOGRAPHS_FOLDER),
            files=sum(1 for folder, _name in kept.values() if folder == store.FILES_FOLDER),
            renamed_slugs=tuple(renamed),
            renamed_photographs=tuple(
                (place, name) for place, (_folder, name) in kept.items()
                if name != place.rsplit("/", 1)[-1]),
            pages=tuple(sorted(page.name for page in pages)) or ("index",),
            dropped=_dropped(items, pages, menu_listed),
            waiting=_waiting(items),
            unfetched=_unfetched(unheld, unfetched),
            menus=menus,
            other_types=_other_types(channel, ns),
        ))
        if keep is not None:
            keep(made[0])

    made: list[Report] = []
    staged(into, write)
    return made[0]


def _held(channel, ns, media: Path):
    """Each held file Import keeps, by its upload place, as (folder, Store
    name): a photograph where the Builder can show it, else a file where the
    Builder allows it. With the photograph lookups, and every place not
    kept, with why."""
    photo: dict[Path, bool] = {}

    def is_photo(path: Path) -> bool:
        if path not in photo:
            photo[path] = builder.is_photograph(path)
        return photo[path]

    names, by_address, by_id, unheld = _attachments(channel, ns, media, strict=False,
                                                    shown=is_photo)
    kept: dict[str, tuple[str, str]] = {}
    for place, name in names.items():
        if is_photo(media / place):
            kept[place] = (store.PHOTOGRAPHS_FOLDER, name)
            continue
        try:
            data = (media / place).read_bytes()
        except OSError as exc:
            # A held file that cannot be had never stops Import (INV-5).
            unheld.append((place, f"it could not be read: {os_reason.of(exc)}"))
            continue
        if builder.file_allowed(name, data):
            kept[place] = (store.FILES_FOLDER, name)
        else:
            unheld.append((place, "it is not a kind of file Pressless keeps"))
    return kept, by_address, by_id, unheld


def _targets(channel, ns, pages: list[_Page], items: list[_Item],
             entries: Mapping[str, store.Entry]) -> dict[str, tuple[str, str, str]]:
    """What a menu link may point at, by post id: each page and published
    entry's (title, new address, old address)."""
    targets = {page.post_id: (page.title, "{{UP}}index.html" if page.name == "index"
                              else f"{{{{UP}}}}pages/{page.name}.html", page.link)
               for page in pages}
    for item, link in zip(items, _links(channel, ns, items), strict=True):
        if not item.draft:
            targets[item.post_id] = (item.title, "{{UP}}" + builder.entry_path(
                entries[item.post_id]) + "/index.html", link)
    return targets


def _dropped(items: list[_Item], pages: list[_Page], menu_listed: list[str]
             ) -> tuple[Dropped, ...]:
    """What did not come across as written: entries first, then pages, then
    the menu, each line once."""
    dropped = [Dropped(item.slug, what) for item in items for what in dict.fromkeys(item.dropped)]
    for page in pages:
        if page.comments:
            page.dropped.append(f"its comments ({page.comments}), which a page does not have")
        dropped += [Dropped(f"pages/{page.name}", what) for what in dict.fromkeys(page.dropped)]
    dropped += [Dropped(_NAVIGATION, what) for what in dict.fromkeys(menu_listed)]
    return tuple(dropped)


def _unfetched(unheld: list[tuple[str, str]], fetched: Mapping[str, str]
               ) -> tuple[tuple[str, str], ...]:
    """Each attachment not held, once, with why: where its original is
    missing, the fetch's own reason for that place takes MISSING's place."""
    why_by_place: dict[str, str] = {}
    for place, why in unheld:
        if why == MISSING:
            why = fetched.get(place, "it was not fetched, nor in the media download")
        why_by_place[place] = why
    return tuple(why_by_place.items())


def _other_types(channel, ns) -> tuple[tuple[str, int], ...]:
    """Each post type Import does not carry, with how many the export holds."""
    other: dict[str, int] = {}
    for item in channel.findall("item"):
        kind = _field(item, "post_type", ns)
        if kind not in _CARRIED_TYPES:
            other[kind] = other.get(kind, 0) + 1
    return tuple(sorted(other.items()))


def _featured(item: _Item, body: str, by_id) -> str:
    """§ 4.5: the featured image opens the body, where WordPress themes show
    it, unless the body already shows that photograph."""
    name = by_id(item.featured)
    if name is None:
        item.dropped.append(_NO_FEATURED)
        return body
    if f"{{photo: {name}}}" in body or f"{{photo: {name} |" in body:
        return body
    return f"{{photo: {name}}}\n\n{body}" if body else f"{{photo: {name}}}"


def _links(channel, ns, items: list[_Item]) -> list[str]:
    """Each item's old address, in the order _items read them."""
    by_id = {_field(item, "post_id", ns): (item.findtext("link") or "").strip()
             for item in channel.findall("item")}
    return [by_id.get(item.post_id, "") for item in items]


# ---------------------------------------------------------- the moves ----


def _move(source: Path, target: Path) -> None:
    """`source` to `target` by rename; into a folder already there, each file
    alone, and a file already there is kept."""
    if not target.exists():
        os.rename(source, target)
    elif source.is_dir() and target.is_dir():
        for child in sorted(source.iterdir()):
            _move(child, target / child.name)


def _holds_a_site(into: Path) -> bool:
    try:
        return store.holds_a_site(into)
    except store.StoreError as exc:
        raise ImportStopped(str(exc)) from None


def recover(into: Path) -> None:
    """What an earlier stop left, put right before anything is read: moves
    into the site's folder that had begun are finished, and held files moved
    into import/work/ before them go back where they came from. Raises
    ImportStopped where either cannot be done; nothing is lost then."""
    stopped = finish(into)
    if stopped is not None:
        raise ImportStopped(stopped)
    if not _put_back(Path(into) / IMPORT_FOLDER):
        raise ImportStopped(_NOT_PUT_BACK)


def _put_back(held_folder: Path) -> bool:
    """Move each held file import/moved.jsonl lists back where it came from,
    where it is still in import/work/; whether every one went back. The list
    is deleted once they all have."""
    journal = held_folder / _MOVED
    into = held_folder.parent
    try:
        lines = journal.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return True
    except (OSError, UnicodeError):
        return False
    whole = True
    for line in reversed(lines):
        try:
            source, target = (into / part for part in json.loads(line))
        except (ValueError, TypeError):
            continue    # cut short by a stop before its move began
        if target.exists() and not source.exists():
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                os.rename(target, source)
            except OSError:
                whole = False
    if whole:
        try:
            journal.unlink()
        except OSError:
            return False
    return whole


def _relative(path: Path, into: Path) -> str:
    """`path` from `into`, or whole where it is on another drive."""
    try:
        return os.path.relpath(path, into)
    except ValueError:
        return str(path)


def staged(into: Path, write: Callable[[Path, Callable[[Path, Path], None]], None]) -> None:
    """§ 4.7's whole or nothing. `write(work, move)` writes every Store file
    into import/work/, moving each held file in by `move(source, target)`;
    then import/moving is written and each folder moves into `into`. A stop
    before the moves puts every held file back and deletes import/work/; a
    stop during them leaves import/moving, so `finish` completes them."""
    into = Path(into)
    held_folder = into / IMPORT_FOLDER
    work = held_folder / _WORK
    moving = held_folder / _MOVING
    if moving.exists() or not _put_back(held_folder):
        # import/work/ holds held files still: `recover` first.
        raise ImportStopped(_NOT_PUT_BACK)
    with _writing("the work folder"):
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
    try:
        with _writing("the list of held files"):
            journal = open(held_folder / _MOVED, "a", encoding="utf-8")  # noqa: SIM115
        with journal:

            def move(source: Path, target: Path) -> None:
                # Listed first: a stop after the rename can then put it back.
                journal.write(json.dumps([_relative(source, into),
                                          _relative(target, into)]) + "\n")
                journal.flush()
                target.parent.mkdir(exist_ok=True)
                os.rename(source, target)

            write(work, move)
        # Asked again: another window may have written a site meanwhile, and
        # the moves would merge the two (PRESS-0125 INV-1).
        if _holds_a_site(into):
            raise ImportStopped(_NOT_EMPTY)
        with _writing("the note that the moves have begun"):
            moving.write_bytes(b"")
    except BaseException:
        try:
            moving.unlink(missing_ok=True)
            undone = _put_back(held_folder)
        except OSError:
            # import/moving stays, so the next start finishes the moves.
            undone = False
        if undone:
            shutil.rmtree(work, ignore_errors=True)
        raise
    stopped = finish(into)
    if stopped is not None:
        raise ImportStopped(stopped)


def finish(into: Path) -> str | None:
    """§ 4.7: move what is left in import/work/ into the site's folder while
    import/moving says the moves began, then delete import/work/, import/media/
    and import/folder/. Returns a sentence to show where a move failed; nothing
    is lost, and the next start tries again."""
    held_folder = Path(into) / IMPORT_FOLDER
    moving = held_folder / _MOVING
    if not moving.exists():
        return None
    work = held_folder / _WORK
    try:
        if work.is_dir():
            for top in sorted(work.iterdir()):
                _move(top, Path(into) / top.name)
        moving.unlink()
    except OSError as exc:
        return ("Pressless could not finish moving the site it brought in into place: "
                f"{os_reason.of(exc)}. Nothing was lost. Close anything "
                "using that folder and start Pressless again.")
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(held_folder / MEDIA_FOLDER, ignore_errors=True)
    shutil.rmtree(held_folder / FOLDER, ignore_errors=True)
    try:
        (held_folder / _MOVED).unlink(missing_ok=True)
    except OSError:
        pass    # its files are in the site now, so it puts nothing back
    return None
