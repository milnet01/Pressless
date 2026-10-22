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
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from pressless import blocks, builder, look, menu, sitefile, starter, store, templates

from . import (
    _RESIZED,
    Dropped,
    ImportStopped,
    Report,
    _convert,
    _field,
    _Item,
    _items,
    _old_site,
    _photographs,
    _resolve,
    _upload_path,
    _waiting,
    read,
    resolve_slug,
)
from ._html import autop, wordpress_markup

IMPORT_FOLDER = "import"   # in the site's folder; never published (§ 4.2)
_WORK = "work"
_MEDIA = "media"
_MOVING = "moving"
_MISSING = "its original is missing"
# What becomes something, and what is the Report's count of the rest (§ 4.3).
_CARRIED_TYPES = frozenset({"post", "page", "attachment", "nav_menu_item", "wp_navigation"})
_PAGE_STATUSES = frozenset({"publish", "draft", "private", "pending", "future"})
_NAVIGATION = "navigation"


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
    pages = []
    for item in channel.findall("item"):
        if (_field(item, "post_type", ns) != "page"
                or _field(item, "status", ns) not in _PAGE_STATUSES):
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


def _host(address: str) -> str:
    return urlparse(address).netloc.lower().removeprefix("www.")


def _addresses(body: str, up: str, held: Mapping[str, str], old_site: str
               ) -> tuple[str, list[str]]:
    """Each address under the old site's uploads folder whose file Import
    holds, pointed at the Store's copy from a page `up` from the root; any
    other is left as it is and listed."""
    listed: list[str] = []
    old = old_site.lower().removeprefix("www.")

    def token(found: re.Match) -> str:
        address = found.group(0)
        decoded = html.unescape(address)
        place = _upload_path(decoded)
        if place is None or _host(decoded) not in ("", old):
            return address
        web = held.get(place) or held.get(_RESIZED.sub("", place))
        if web is None:
            listed.append(f"an address still pointing at the old site: {decoded}")
            return address
        return up + web

    def attribute(found: re.Match) -> str:
        return (found.group(1) + found.group(2) + re.sub(r"[^\s,]+", token, found.group(3))
                + found.group(2))

    return _ADDRESSED.sub(attribute, body), listed


def _page_html(page: _Page, sheets: tuple[str, ...], held: Mapping[str, str],
               old_site: str) -> str:
    """The page in starter.new_page's shape, its body as its area after the
    markup rule, and its addresses moved; Blocks reads what sections it can,
    and the rest is code."""
    root = page.name == "index"
    body = page.body if wordpress_markup(page.body) else autop(page.body)
    body, listed = _addresses(body, "" if root else "../", held, old_site)
    page.dropped.extend(listed)
    text = starter.new_page("Home" if root else page.name, page.title, sheets,
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
    fit `room()`; a refused download writes nothing. Returns the places
    filled."""
    try:
        with zipfile.ZipFile(source) as held:
            infos = held.infolist()
            for info in infos:
                if not sitefile.stays_inside(info.filename):
                    raise ImportStopped("the media download holds a name outside its folder")
                if sitefile.is_link(info):
                    raise ImportStopped("the media download holds a link")
            wanted: dict[str, zipfile.ZipInfo] = {}
            for place in missing:
                if (media / place).is_file():
                    continue
                for info in infos:
                    if not info.is_dir() and (info.filename == place
                                              or info.filename.endswith(f"/{place}")):
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


# ------------------------------------------------- writing (§ 4.7) ----


def bring_in(export: Path, media: Path, into: Path, layout: str, *,
             unfetched: Mapping[str, str] | None = None) -> Report:
    """§ 4.7, in order: read and resolve slugs; convert every body; write
    every Store file into import/work/, moving each held file in from
    `media`; then move each folder into `into`. `layout` is one of
    starter.LOOKS; `unfetched` is each place the fetch could not have, with
    why (fetch.fetch_all's answer), so the Report says so."""
    export, media, into = Path(export), Path(media), Path(into)
    unfetched = unfetched or {}
    if store.holds_a_site(into):
        raise ImportStopped("this site already holds a site, and Import writes only "
                            "into an empty one")
    layout = layout if layout in starter.LOOKS else starter.LOOKS[0]
    held_folder = into / IMPORT_FOLDER
    work = held_folder / _WORK

    read_in = read(export)
    channel, ns = read_in.channel, read_in.ns
    items = _items(channel, ns, pages=False)
    renamed = _resolve(items)
    pages = _pages(channel, ns)
    renamed += _name_pages(pages, (channel.findtext("title") or "").strip())
    old_site = _old_site(channel, ns)

    photo: dict[Path, bool] = {}

    def is_photo(path: Path) -> bool:
        if path not in photo:
            photo[path] = builder.photograph_format(path) is not None
        return photo[path]

    names, by_address, by_id, unheld = _photographs(channel, ns, media, strict=False,
                                                    shown=is_photo)
    kept: dict[str, tuple[str, str]] = {}      # place -> (folder, Store name)
    for place, name in names.items():
        if is_photo(media / place):
            kept[place] = (store.PHOTOGRAPHS_FOLDER, name)
        elif builder.file_allowed(name, (media / place).read_bytes()):
            kept[place] = (store.FILES_FOLDER, name)
        else:
            unheld.append((place, "it is not a kind of file Pressless keeps"))
    web = {place: builder.web_photograph(name) if folder == store.PHOTOGRAPHS_FOLDER
           else builder.web_file(name) for place, (folder, name) in kept.items()}

    bodies = {item.post_id: _convert(item, wordpress_markup, by_address, by_id, old_site)
              for item in items}
    entries = {item.post_id: store.Entry(
        slug=item.slug, title=item.title, date=item.date, categories=item.categories,
        tags=item.tags, body=bodies[item.post_id], extra=()) for item in items}
    targets = {page.post_id: (page.title, "{{UP}}index.html" if page.name == "index"
                              else f"{{{{UP}}}}pages/{page.name}.html", page.link)
               for page in pages}
    for item, link in zip(items, _links(channel, ns, items), strict=True):
        if not item.draft:
            targets[item.post_id] = (item.title, "{{UP}}" + builder.entry_path(
                entries[item.post_id]) + "/index.html", link)
    links, menus = _menu(channel, ns, targets)
    menu_listed: list[str] = []
    navigation = _navigation(links, menu_listed)

    if work.exists():
        shutil.rmtree(work)    # an earlier attempt that stopped before its moves
    work.mkdir(parents=True)
    moved: list[tuple[Path, Path]] = []
    doing = "the folder"
    try:
        for item in items:
            doing = f"the entry {item.slug}"
            store.write(work, entries[item.post_id], draft=item.draft)
            if item.comments:
                doing = f"the comments on {item.slug}"
                store.write_comments(work, item.slug, item.comments)
        doing = "the look"
        look.save(work, look.defaults(layout), "")
        sheets = builder.stylesheets(work)
        for page in pages:
            doing = f"the page {page.name}"
            store.write_html(work, store.PAGES_FOLDER, page.name,
                             _page_html(page, sheets, web, old_site))
        if not pages:
            doing = "the page index"
            identity = store.read_identity(into)
            store.write_html(work, store.PAGES_FOLDER, "index", starter.home_page(
                identity.name if identity is not None else
                (channel.findtext("title") or "").strip()))
        for name, text in (("header", starter.header()), ("footer", starter.footer()),
                           (_NAVIGATION, navigation)):
            doing = f"the furniture file {name}"
            store.write_html(work, store.FURNITURE_FOLDER, name, text)
        doing = "the templates"
        templates.seed(work)
        doing = "the journal switch"
        store.write_journal(work, bool(items))
        for place, (folder, name) in kept.items():
            doing = f"the file {place}"
            target = (store.photograph_path_for(work, name) if folder == store.PHOTOGRAPHS_FOLDER
                      else store.file_path_for(work, name))
            target.parent.mkdir(exist_ok=True)
            os.rename(media / place, target)
            moved.append((media / place, target))
    except BaseException as exc:
        for source, target in reversed(moved):
            try:
                os.rename(target, source)
            except OSError:
                pass
        shutil.rmtree(work, ignore_errors=True)
        if isinstance(exc, ImportStopped):
            raise
        if isinstance(exc, store.StoreError):
            raise ImportStopped(f"the Store refused {doing}: {exc}") from None
        if isinstance(exc, OSError):
            raise ImportStopped(
                f"{doing} could not be written: {exc.strerror or type(exc).__name__}") from None
        raise

    (held_folder / _MOVING).write_bytes(b"")
    stopped = finish(into)
    if stopped is not None:
        raise ImportStopped(stopped)

    dropped = [Dropped(item.slug, what) for item in items for what in dict.fromkeys(item.dropped)]
    for page in pages:
        if page.comments:
            page.dropped.append(f"{page.comments} comments, which a page does not carry")
        dropped += [Dropped(f"pages/{page.name}", what) for what in dict.fromkeys(page.dropped)]
    dropped += [Dropped(_NAVIGATION, what) for what in dict.fromkeys(menu_listed)]
    other: dict[str, int] = {}
    for item in channel.findall("item"):
        kind = _field(item, "post_type", ns)
        if kind not in _CARRIED_TYPES:
            other[kind] = other.get(kind, 0) + 1
    return Report(
        published=sum(1 for item in items if not item.draft),
        drafts=sum(1 for item in items if item.draft),
        comments=sum(len(item.comments) for item in items),
        photographs=sum(1 for folder, _name in kept.values()
                        if folder == store.PHOTOGRAPHS_FOLDER),
        files=sum(1 for folder, _name in kept.values() if folder == store.FILES_FOLDER),
        renamed_slugs=tuple(renamed),
        renamed_photographs=tuple(
            (place, name) for place, (_folder, name) in kept.items()
            if name != place.rsplit("/", 1)[-1]),
        pages=tuple(sorted(page.name for page in pages)) or ("index",),
        dropped=tuple(dropped),
        waiting=_waiting(items),
        unfetched=tuple(dict(
            (place, unfetched.get(place, "it was not fetched, nor in the media download")
             if why == _MISSING else why) for place, why in unheld).items()),
        menus=menus,
        other_types=tuple(sorted(other.items())),
    )


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


def finish(into: Path) -> str | None:
    """§ 4.7: move what is left in import/work/ into the site's folder while
    import/moving says the moves began, then delete import/work/ and
    import/media/. Returns a sentence to show where a move failed; nothing is
    lost, and the next start tries again."""
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
                f"{exc.strerror or type(exc).__name__}. Nothing was lost. Close anything "
                "using that folder and start Pressless again.")
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(held_folder / _MEDIA, ignore_errors=True)
    return None
