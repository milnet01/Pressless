"""The starter site, for an install that never ran Import (PRESS-0126).

Setup offers it on a Store that holds no site, and `fill` copies it in: a
header, footer and menu, a Home and an About page, the templates, and the
stylesheet of the look chosen (PRESS-0239), with the journal off. Nothing is
written over a file the Store already holds. A marker in Pressless's own
folder says the starter has not been published yet, which is what lets
publishing refuse to replace a site already on GitHub
(docs/specs/PRESS-0126-starter-site.md).
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from pressless import blocks, builder, look, store, templates
from pressless.words import say

MARKER = "starter-unpublished"   # in Pressless's own folder; empty file

# Shipped to every install, so they name nobody and assume nothing about the
# user (§ 4.3). The header and footer name the site by placeholder, so a
# rename in the Store reaches every page (PRESS-0213 § 4.6). Their words are
# looked up when a site is filled; the {{...}} placeholders and the data-nav
# names are the Builder's, and stay.


def _header() -> str:
    return (f"<!-- {say('starter.header_note')} -->\n"
            + '<header class="site">\n'
            + '  <a class="site-name" href="{{UP}}index.html">{{SITE_NAME}}</a>\n'
            + '  <p class="site-description">{{SITE_DESCRIPTION}}</p>\n'
            + "{{NAVIGATION}}\n"
            + "</header>\n")


def _navigation() -> str:
    primary = html.escape(say("starter.menu"), quote=True)
    return (f'  <nav class="primary" aria-label="{primary}">\n'
            + '    <a href="{{UP}}index.html" data-nav="Home">' + say("starter.home") + "</a>\n"
            + '    <a href="{{UP}}pages/about.html" data-nav="about">' + say("starter.about")
            + "</a>\n  </nav>")


def _footer() -> str:
    return (f"<!-- {say('starter.footer_note')} -->\n"
            + '<footer class="site">\n'
            + "  <p>&copy; {{YEAR}} {{SITE_NAME}}</p>\n"
            + "</footer>\n")

_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="{up}look/style.css">
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


def _words(key: str) -> str:
    return html.escape(say(key), quote=False)

# PRESS-0196: the looks' colours, layouts and rules live in look.py, which
# makes the style code from a site's choices. The three looks are its layouts.
LOOKS = look.LAYOUTS


# PRESS-0199 § 4.5: the disclosure counting needs, in the starter pages'
# shape. `fill` does not write it; `add_privacy` does, while counting is on.
_PRIVACY = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  {links}
</head>
<body>
  <!-- HEADER:START page="privacy" -->
  <!-- HEADER:END -->
  <main class="page">
{area}
  </main>
  <!-- FOOTER:START -->
  <!-- FOOTER:END -->
</body>
</html>
"""

_NEW_PAGE = _PRIVACY.replace('page="privacy"', 'page="{page}"')

_FOOTER_END = re.compile(r"</footer\s*>", re.IGNORECASE)


def new_page(name: str, title: str, sheets: tuple[str, ...]) -> str:
    """PRESS-0195 § 4.3: a page he adds, in the Privacy page's shape -- the
    site's stylesheets from depth 1, a header pair naming the page, his title
    as the title and heading, and one paragraph to replace."""
    links = "\n  ".join(f'<link rel="stylesheet" href="../{html.escape(sheet, quote=True)}">'
                        for sheet in sheets)
    return _NEW_PAGE.format(title=html.escape(title), links=links,
                            page=html.escape(name, quote=True),
                            area=_area(title, _words("starter.new_page.words")))


def privacy_page(site_name: str, sheets: tuple[str, ...]) -> str:
    """The Privacy page, linking each stylesheet from depth 1."""
    links = "\n  ".join(f'<link rel="stylesheet" href="../{html.escape(sheet, quote=True)}">'
                      for sheet in sheets)
    return _PRIVACY.format(
        title=say("starter.privacy.title", name=html.escape(site_name, quote=True)),
        links=links,
        # The policy's words hold links, so they go in as HTML; the rest are text.
        area=_area(say("starter.privacy"), _words("starter.privacy.counting"),
                   _words("starter.privacy.counted"), say("starter.privacy.policy"),
                   _words("starter.privacy.questions")))


def privacy_link() -> str:
    """The footer's link to the Privacy page."""
    return '<a href="{{UP}}pages/privacy.html">' + say("starter.privacy") + "</a>"


def privacy_name(folder: Path) -> str:
    """The name the Privacy page carries: the Store's, else "this site"
    (PRESS-0213 § 4.6). A malformed identity file raises StoreError."""
    identity = store.read_identity(folder)
    return identity.name if identity is not None else say("starter.this_site")


def add_privacy(folder: Path, site_name: str) -> tuple[bool, bool]:
    """PRESS-0199 § 4.5: while counting is on, the Privacy page and a footer
    link to it, each where absent, and only on a Store holding a site. Returns
    whether each was added. Never creates a footer file."""
    folder = Path(folder)
    if not store.holds_a_site(folder):
        return False, False
    page = store.html_path_for(folder, store.PAGES_FOLDER, "privacy")
    added_page = not page.exists()
    if added_page:
        store.write_html(folder, store.PAGES_FOLDER, "privacy",
                         privacy_page(site_name, builder.stylesheets(folder)))
    footer = store.html_path_for(folder, store.FURNITURE_FOLDER, "footer")
    added_link = False
    if footer.exists():
        text = store.read_html(footer)
        if "pages/privacy.html" not in text:
            end = _FOOTER_END.search(text)
            at = end.start() if end else len(text)
            store.write_html(folder, store.FURNITURE_FOLDER, "footer",
                             text[:at] + privacy_link() + "\n" + text[at:])
            added_link = True
    return added_page, added_link


def offered(folder: Path) -> bool:
    """§ 4.4: on a Store holding no site, or one whose fill was cut short."""
    return not store.holds_a_site(folder) or unpublished(folder)


def unpublished(folder: Path) -> bool:
    return (Path(folder) / MARKER).is_file()


def published(folder: Path) -> None:
    """Remove the marker; absent is fine. An OSError is the caller's."""
    (Path(folder) / MARKER).unlink(missing_ok=True)


def fill(folder: Path, site_name: str, layout: str = LOOKS[0]) -> None:
    """§ 4.3, in order: the marker, each starter file only where it is absent,
    the templates, and the journal off. `layout` is one of LOOKS; any other,
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
        raise store.StoreError(f"{MARKER} could not be written: {exc.strerror}") from exc

    name = html.escape(site_name, quote=True)
    files = (
        (store.FURNITURE_FOLDER, "header", _header()),
        (store.FURNITURE_FOLDER, "navigation", _navigation()),
        (store.FURNITURE_FOLDER, "footer", _footer()),
        (store.PAGES_FOLDER, "index", _PAGE.format(
            title=name, up="", page="Home",
            area=_area(say("starter.welcome", name=site_name), _words("starter.home.words")))),
        (store.PAGES_FOLDER, "about", _PAGE.format(
            title=say("starter.about.title", name=name), up="../", page="about",
            area=_area(say("starter.about"), _words("starter.about.words")))),
    )
    for kind, file_name, text in files:
        if not store.html_path_for(folder, kind, file_name).exists():
            store.write_html(folder, kind, file_name, text)
    if not store.style_code_path(folder).exists():
        look.save(folder, look.defaults(layout), "")
    templates.seed(folder)
    store.write_journal(folder, False)
