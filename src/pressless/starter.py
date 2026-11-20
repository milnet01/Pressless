"""The starter site, for an install that never ran Import (PRESS-0126).

Setup offers it on a Store that holds no site, and `fill` copies it in: a
header, footer and menu, a Home and an About page, the templates, and the
stylesheet of the look chosen (PRESS-0239), with the journal off. Nothing is
written over a file the Store already holds. A marker in the site's
folder says the starter has not been published yet, which is what lets
publishing refuse to replace a site already on GitHub
(docs/specs/PRESS-0126-starter-site.md).
"""
from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path

from pressless import (
    blocks,
    builder,
    json_record,
    languages,
    look,
    menu,
    os_reason,
    settings,
    store,
    templates,
)
from pressless.safe_write import write_whole
from pressless.words import say_in

MARKER = "starter-unpublished"   # in the site's folder; empty file
# What the marker holds once the user has agreed to replace the site already
# on GitHub (PRESS-0126 § 4.5). The marker stays until a publish lands, so
# nothing says the starter is on the web before it is (PRESS-0393).
REPLACE_AGREED = "replace\n"
# In the site's folder: a digest of the Home page and the menu as fill wrote
# them, which checklist compares with, so a rename or reworded starter words
# never reads as the site made its own (PRESS-0383).
FILLED = "starter-filled.json"
# The Privacy page's name. add_privacy keeps it up to date by this name, and the
# page editor never renames it, nor removes it while it discloses something.
PRIVACY = "privacy"

# Shipped to every install, so they name nobody and assume nothing about the
# user (§ 4.3). The header and footer name the site by placeholder, so a
# rename in the Store reaches every page (PRESS-0213 § 4.6). Their words are
# looked up when a site is filled; the {{...}} placeholders and the data-nav
# names are the Builder's, and stay. Import writes the same header, footer and
# navigation shape (PRESS-0125 § 4.6, § 4.7).


def header(code: str = "en") -> str:
    return (f"<!-- {say_in(code, 'starter.header_note')} -->\n"
            + '<header class="site">\n'
            + '  <a class="site-name" href="{{UP}}index.html">{{SITE_NAME}}</a>\n'
            + '  <p class="site-description">{{SITE_DESCRIPTION}}</p>\n'
            + "{{NAVIGATION}}\n"
            + "</header>\n")


def navigation(code: str = "en") -> str:
    primary = html.escape(say_in(code, "starter.menu"), quote=True)
    return (f'  <nav class="primary" aria-label="{primary}">\n'
            + f'    <a href="{{{{UP}}}}index.html" data-nav="{builder.HOME_NAV}">'
            + say_in(code, "starter.home") + "</a>\n"
            + '    <a href="{{UP}}pages/about.html" data-nav="about">'
            + say_in(code, "starter.about") + "</a>\n  </nav>")


def menu_linking(pages: list[tuple[str, str]], code: str = "en") -> str:
    """PRESS-0423: a menu in navigation's shape, linking each (page, words)
    in order, for a site that holds none."""
    primary = html.escape(say_in(code, "starter.menu"), quote=True)
    links = "".join(
        f'    <a href="{menu.address(page)}" data-nav="'
        f'{html.escape(builder.HOME_NAV if page == "index" else page, quote=True)}">'
        f"{html.escape(words)}</a>\n" for page, words in pages)
    return f'  <nav class="primary" aria-label="{primary}">\n{links}  </nav>'


def footer(code: str = "en") -> str:
    return (f"<!-- {say_in(code, 'starter.footer_note')} -->\n"
            + '<footer class="site">\n'
            + "  <p>&copy; {{YEAR}} {{SITE_NAME}}</p>\n"
            + "</footer>\n")

# Every page the starter or the editor writes, in one shape. `links` is the
# page's stylesheet links; `page` names it to the header pair; `lang` is the
# site's language (PRESS-0241 § 4.4).
_PAGE = """<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  {links}
</head>
<body>
  <!-- HEADER:START page="{page}" -->
  <!-- HEADER:END -->
  <main class="page">
{area}
  </main>
  <!-- FOOTER:START -->
  <!-- FOOTER:END -->
</body>
</html>
"""


def _links(sheets: tuple[str, ...], up: str) -> str:
    """One stylesheet link per sheet, each from the root by way of `up`."""
    return "\n  ".join(f'<link rel="stylesheet" href="{up}{html.escape(sheet, quote=True)}">'
                       for sheet in sheets)


# Home and About are written by `fill`, which always writes the style code,
# so builder.stylesheets would answer this one sheet for them.
_OWN_SHEET = (builder.STYLE_CODE,)


def _area(heading: str, *paragraphs: str) -> str:
    """PRESS-0215 § 4.8: a page's words as a sections area, the heading and
    each paragraph a section. `heading` is text; each paragraph is inline
    HTML, so a caller escapes plain words before passing them."""
    sections = [blocks.Section(blocks.HEADING, {"level": "1",
                                                "html": html.escape(heading, quote=False)})]
    sections += [blocks.Section(blocks.TEXT, {"html": words}) for words in paragraphs]
    return "\n".join(f"    {line}" for line in ("<!-- pressless:page -->",
                                                  *map(blocks.section_html, sections),
                                                  "<!-- /pressless:page -->"))


def _words(key: str, code: str) -> str:
    return html.escape(say_in(code, key), quote=False)

# PRESS-0196: the looks' colours, layouts and rules live in look.py, which
# makes the style code from a site's choices. The looks are its layouts.
LOOKS = look.LAYOUTS


_FOOTER_END = re.compile(r"</footer\s*>", re.IGNORECASE)
_MAIN_END = re.compile(r"</main\s*>", re.IGNORECASE)
_AREA_END = "<!-- /pressless:page -->"


def new_page(name: str, title: str, sheets: tuple[str, ...], *,
             main: str | None = None, root: bool = False, code: str = "en") -> str:
    """PRESS-0195 § 4.3: a page he adds, in the Privacy page's shape -- the
    site's stylesheets from depth 1, a header pair naming the page, his title
    as the title and heading, and one paragraph to replace. Import passes a
    page's own body as `main`, in place of the heading and paragraph, and
    `root` for the page that sits at the root (PRESS-0125 § 4.6)."""
    return _PAGE.format(title=html.escape(title), links=_links(sheets, "" if root else "../"),
                        page=html.escape(name, quote=True), lang=code,
                        area=_area(title, _words("starter.new_page.words", code))
                        if main is None else main)


def home_page(site_name: str, sheets: tuple[str, ...] = _OWN_SHEET, *,
              code: str = "en") -> str:
    """The starter's Home page, which sits at the root. A site filled before
    FILLED existed is compared with this by checklist, as worded today. The
    Pages screen's Add a Home page passes the site's own `sheets` (PRESS-0423)."""
    name = html.escape(site_name, quote=True)
    return _PAGE.format(title=name, links=_links(sheets, ""), page=builder.HOME_NAV, lang=code,
                        area=_area(say_in(code, "starter.welcome", name=site_name),
                                   _words("starter.home.words", code)))


def _counting_words(code: str) -> tuple[str, ...]:
    """PRESS-0199 § 4.5. The policy's words hold links, so they go in as HTML."""
    return (_words("starter.privacy.counting", code), _words("starter.privacy.counted", code),
            say_in(code, "starter.privacy.policy"))


def _votes_words(code: str) -> tuple[str, ...]:
    """PRESS-0211 § 4.5. The second holds a link, so it goes in as HTML."""
    return _words("starter.privacy.votes", code), say_in(code, "starter.privacy.votes.who")


def _recaptcha_words(code: str) -> tuple[str, ...]:
    return (_words("starter.privacy.recaptcha", code),)


def disclosures(saved: settings.Settings) -> dict[str, bool]:
    """What `saved` has on, as `privacy_page` and `add_privacy` take it."""
    return {"counting": saved.measurement_id is not None, "votes": saved.votes is not None,
            "recaptcha": saved.votes is not None and saved.votes.recaptcha_key is not None}


def privacy_page(site_name: str, sheets: tuple[str, ...], *, counting: bool, votes: bool,
                 recaptcha: bool, code: str = "en") -> str:
    """The Privacy page, linking each stylesheet from depth 1, saying only what
    is on (PRESS-0199 § 4.5, PRESS-0211 § 4.5). `fill` does not write it;
    `add_privacy` does, while something it discloses is on."""
    words = ((_counting_words(code) if counting else ())
             + (_votes_words(code) if votes else ())
             + (_recaptcha_words(code) if recaptcha else ()))
    return _PAGE.format(
        title=say_in(code, "starter.privacy.title", name=html.escape(site_name, quote=True)),
        links=_links(sheets, "../"), page=PRIVACY, lang=code,
        area=_area(say_in(code, "starter.privacy"), *words,
                   _words("starter.privacy.questions", code)))


def privacy_link(code: str = "en") -> str:
    """The footer's link to the Privacy page."""
    return '<a href="{{UP}}pages/privacy.html">' + say_in(code, "starter.privacy") + "</a>"


def privacy_name(folder: Path) -> str:
    """The name the Privacy page carries: the Store's, else "this site"
    (PRESS-0213 § 4.6). A malformed identity file raises StoreError."""
    identity = store.read_identity(folder)
    return (identity.name if identity is not None
            else say_in(languages.of_site(folder), "starter.this_site"))


def _with_missing_words(text: str, *, counting: bool, votes: bool, recaptcha: bool,
                        code: str) -> str:
    """PRESS-0211 § 4.5: `text` with each disclosure that is on and that it does
    not mention, so each is added once and a writer's own wording stands. A page
    with no sections area gets plain paragraphs: section marks outside one are
    marks that do not pair."""
    # Each product's name, as starter.privacy.counting, starter.privacy.votes
    # and starter.privacy.recaptcha in words.py spell it: a rewording that
    # drops the name adds the paragraph again at every run.
    lower = text.lower()
    words = ((_counting_words(code) if counting and "google analytics" not in lower else ())
             + (_votes_words(code) if votes and "firebase" not in lower else ())
             + (_recaptcha_words(code) if recaptcha and "recaptcha" not in lower else ()))
    if not words:
        return text
    if _AREA_END in text:
        at = text.index(_AREA_END)
        added = "".join(f"{blocks.section_html(blocks.Section(blocks.TEXT, {'html': said}))}\n"
                        for said in words)
        return text[:at] + added + text[at:]
    added = "".join(f"<p>{said}</p>\n" for said in words)
    end = _MAIN_END.search(text)
    at = end.start() if end else len(text)
    return text[:at] + added + text[at:]


def add_privacy(folder: Path, site_name: str, *, counting: bool, votes: bool,
                recaptcha: bool) -> tuple[bool, bool]:
    """PRESS-0199 § 4.5 and PRESS-0211 § 4.5: the Privacy page and a footer link
    to it, each where absent, and only on a Store holding a site. A page already
    there, and a waiting copy that pressing would put in its place, gain any
    words they lack. Returns whether the page and the link were added. Never
    creates a footer file."""
    folder = Path(folder)
    if not store.holds_a_site(folder):
        return False, False
    code = languages.of_site(folder)
    page = store.html_path_for(folder, store.PAGES_FOLDER, PRIVACY)
    added_page = not page.exists()
    if added_page:
        store.write_html(folder, store.PAGES_FOLDER, PRIVACY,
                         privacy_page(site_name, builder.stylesheets(folder), counting=counting,
                                      votes=votes, recaptcha=recaptcha, code=code))
    for waiting in (False, True):
        held = store.html_path_for(folder, store.PAGES_FOLDER, PRIVACY, waiting=waiting)
        if not held.exists():
            continue
        text = store.read_html(held)
        changed = _with_missing_words(text, counting=counting, votes=votes, recaptcha=recaptcha,
                                      code=code)
        if changed != text:
            store.write_html(folder, store.PAGES_FOLDER, PRIVACY, changed, waiting=waiting)
    footer_path = store.html_path_for(folder, store.FURNITURE_FOLDER, "footer")
    added_link = False
    if footer_path.exists():
        text = store.read_html(footer_path)
        if "pages/privacy.html" not in text:
            end = _FOOTER_END.search(text)
            at = end.start() if end else len(text)
            store.write_html(folder, store.FURNITURE_FOLDER, "footer",
                             text[:at] + privacy_link(code) + "\n" + text[at:])
            added_link = True
    return added_page, added_link


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def filled(folder: Path) -> dict[str, str] | None:
    """FILLED's digests by file name, or None for a site filled before it
    existed, or never filled. A file fill did not write has no digest."""
    data = json_record.read(Path(folder) / FILLED)
    if not data:
        return None
    return {name: value for name, value in data.items()
            if name != "version" and isinstance(value, str)}


def note_filled(folder: Path, wrote: dict[str, str]) -> None:
    """Add what this fill, or the Pages screen's Add, wrote to FILLED; a fill
    finished later keeps the digests of the first. An empty `wrote` still
    makes FILLED, after which a page or part with no digest in it reads to
    checklist as his own (PRESS-0423)."""
    try:
        json_record.write(Path(folder) / FILLED, {**(filled(folder) or {}), **wrote})
    except OSError as exc:
        raise store.StoreError(f"{FILLED} could not be written: {os_reason.of(exc)}") from exc


def offered(folder: Path) -> bool:
    """§ 4.4: on a Store holding no site, or one whose fill was cut short."""
    return not store.holds_a_site(folder) or unpublished(folder)


def unpublished(folder: Path) -> bool:
    return (Path(folder) / MARKER).is_file()


def mark_published(folder: Path) -> None:
    """Remove the marker; absent is fine. An OSError is the caller's."""
    (Path(folder) / MARKER).unlink(missing_ok=True)


def agree_to_replace(folder: Path) -> None:
    """Record in the marker that the user agreed to replace the site on
    GitHub. An OSError is the caller's."""
    write_whole(Path(folder) / MARKER, REPLACE_AGREED, prefix=f".{MARKER}.")


def replace_agreed(folder: Path) -> bool:
    try:
        return (Path(folder) / MARKER).read_text(encoding="utf-8") == REPLACE_AGREED
    except OSError:
        return False


def fill(folder: Path, site_name: str, layout: str = LOOKS[0], *,
         code: str = "en") -> None:
    """§ 4.3, in order: the marker, each starter file only where it is absent,
    the templates, and the journal off, every word in the language `code`
    (PRESS-0241 § 4.4). `layout` is one of LOOKS; any other,
    a forged post's, is the first (PRESS-0239). The look is that layout's
    defaults, saved as the Look screen saves them (PRESS-0196 § 4.6). A
    StoreError propagates, and what was written stays, so setup can offer the
    box again and finish the fill."""
    if layout not in LOOKS:
        layout = LOOKS[0]
    folder = Path(folder)
    marker = folder / MARKER
    try:
        marker.write_bytes(b"")
    except OSError as exc:
        raise store.StoreError(f"{MARKER} could not be written: {os_reason.of(exc)}") from exc

    name = html.escape(site_name, quote=True)
    files = (
        (store.FURNITURE_FOLDER, "header", header(code)),
        (store.FURNITURE_FOLDER, "navigation", navigation(code)),
        (store.FURNITURE_FOLDER, "footer", footer(code)),
        (store.PAGES_FOLDER, "index", home_page(site_name, code=code)),
        (store.PAGES_FOLDER, "about", _PAGE.format(
            title=say_in(code, "starter.about.title", name=name),
            links=_links(_OWN_SHEET, "../"), page="about", lang=code,
            area=_area(say_in(code, "starter.about"), _words("starter.about.words", code)))),
    )
    wrote = {}
    for kind, file_name, text in files:
        path = store.html_path_for(folder, kind, file_name)
        if not path.exists():
            store.write_html(folder, kind, file_name, text)
            wrote[file_name] = digest(store.read_html(path))
    note_filled(folder, {name: wrote[name] for name in ("index", "navigation")
                          if name in wrote})
    if not store.style_code_path(folder).exists():
        look.save(folder, look.defaults(layout), "")
    templates.seed(folder, code)
    store.write_journal(folder, False)
