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

from pressless import builder, store, templates
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
    <h1>{heading}</h1>
    <p>{words}</p>
  </main>
  <!-- FOOTER:START -->
  <!-- FOOTER:END -->
</body>
</html>
"""

# PRESS-0239: three looks to start from, each with large type, underlined
# links and a visible focus ring, and each rearranging itself to the screen's
# width: the first user is partially sighted (§ 4.3). Every text colour has a
# contrast of at least 7:1 against its background, by the WCAG formula. The
# names are the looks' own, as file names are, and are never shown: the words
# table holds what setup says about each.
LOOKS = ("sunrise", "meadow", "harbour")

# Sunrise: a warm band across the top, one centred column. Lowest contrast:
# the footer's links, #7c2a0b on #f3e3cf, 7.6:1.
_SUNRISE = """
html { font-size: 118.75%; }
body {
  margin: 0;
  background: #fffaf2;
  color: #2b1d14;
  font-family: system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  line-height: 1.65;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}
a { color: #7c2a0b; text-decoration: underline; text-underline-offset: 0.15em; }
a:focus-visible, button:focus-visible { outline: 3px solid #2b1d14; outline-offset: 3px; }

header.site {
  background: #9a3412;
  color: #ffffff;
  padding: 1.5rem max(1.25rem, calc((100% - 44rem) / 2));
}
header.site a { color: #ffffff; }
header.site a:focus-visible { outline-color: #ffffff; }
.site-name {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 1.9rem;
  font-weight: bold;
  text-decoration: none;
}
.site-description { margin: 0.25rem 0 0; font-size: 1.05rem; }
.site-description:empty { display: none; }
nav.primary { display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; margin-top: 1rem; }
nav.primary a { font-weight: 600; }
nav.primary a[aria-current="page"] { text-decoration: none; border-bottom: 3px solid #ffffff; }

main, .wrap { flex: 1 0 auto; width: 100%; box-sizing: border-box; max-width: 46.5rem;
  margin: 0 auto; padding: 2rem 1.25rem; }
h1, h2, h3 { font-family: Georgia, "Times New Roman", serif; line-height: 1.25; color: #2b1d14; }
h1 { font-size: 2.2rem; margin-top: 0.5rem; }
img { max-width: 100%; height: auto; border-radius: 0.5rem; }

footer.site {
  background: #f3e3cf;
  padding: 1.25rem max(1.25rem, calc((100% - 44rem) / 2));
  font-size: 0.95rem;
}
footer.site p { margin: 0; }
"""

# Meadow: the name and menu in a green panel, beside the page on a wide
# screen and above it on a narrow one. Lowest: links, #1d5c32 on #f6f8f4, 7.5:1.
_MEADOW = """
html { font-size: 118.75%; }
body {
  margin: 0;
  background: #f6f8f4;
  color: #1c2a1f;
  font-family: system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  line-height: 1.65;
}
a { color: #1d5c32; text-decoration: underline; text-underline-offset: 0.15em; }
a:focus-visible, button:focus-visible { outline: 3px solid #1c2a1f; outline-offset: 3px; }

header.site { background: #1f4d2b; color: #ffffff; padding: 1.5rem 1.25rem; }
header.site a { color: #ffffff; }
header.site a:focus-visible { outline-color: #ffffff; }
.site-name { font-size: 1.7rem; font-weight: bold; text-decoration: none; line-height: 1.2; }
.site-description { margin: 0.5rem 0 0; font-size: 1rem; }
.site-description:empty { display: none; }
nav.primary { display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; margin-top: 1rem; }
nav.primary a { font-weight: 600; }
nav.primary a[aria-current="page"] { text-decoration: none; border-bottom: 3px solid #ffffff; }

main, .wrap { max-width: 42rem; padding: 2rem 1.25rem; }
h1, h2, h3 { line-height: 1.25; }
h1 { font-size: 2.1rem; margin-top: 0.5rem; color: #1f4d2b; }
img { max-width: 100%; height: auto; border-radius: 0.5rem; }

footer.site {
  border-top: 2px solid #c9d6c9;
  margin: 2rem 1.25rem 0;
  padding: 1rem 0 1.5rem;
  font-size: 0.95rem;
}

/* Wide screens: the name and the menu sit in a panel on the left. */
@media (min-width: 56rem) {
  body {
    display: grid;
    grid-template-columns: 17rem minmax(0, 1fr);
    grid-template-rows: 1fr auto;
    min-height: 100vh;
  }
  header.site { grid-row: 1 / 3; padding: 2.5rem 1.75rem; }
  nav.primary { flex-direction: column; gap: 0.75rem; margin-top: 2rem; }
  nav.primary a { border-left: 4px solid transparent; padding-left: 0.6rem;
    margin-left: calc(-0.6rem - 4px); }
  nav.primary a[aria-current="page"] { border-bottom: none; border-left-color: #ffffff; }
  main, .wrap { padding: 3rem 3rem 2rem; }
  footer.site { margin: 0 3rem; }
}
"""

# Harbour: a navy bar, the name on the left and the menu on the right on a
# wide screen. Lowest: links, #1e40af on #ffffff, 8.7:1.
_HARBOUR = """
html { font-size: 118.75%; }
body {
  margin: 0;
  background: #ffffff;
  color: #14213d;
  font-family: system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  line-height: 1.65;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}
a { color: #1e40af; text-decoration: underline; text-underline-offset: 0.15em; }
a:focus-visible, button:focus-visible { outline: 3px solid #14213d; outline-offset: 3px; }

header.site {
  background: #14213d;
  color: #ffffff;
  padding: 1.25rem max(1.25rem, calc((100% - 43.5rem) / 2));
}
header.site a { color: #ffffff; }
header.site a:focus-visible { outline-color: #ffffff; }
.site-name { font-size: 1.6rem; font-weight: 800; text-decoration: none; letter-spacing: 0.01em; }
.site-description { margin: 0.25rem 0 0; font-size: 1rem; color: #dbe4f3; }
.site-description:empty { display: none; }
nav.primary { display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; margin-top: 0.75rem; }
nav.primary a { font-weight: 600; }
nav.primary a[aria-current="page"] { text-decoration: none; border-bottom: 3px solid #f4a261; }

/* Wide screens: the name on the left, the menu on the right. */
@media (min-width: 48rem) {
  header.site {
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    column-gap: 2rem;
  }
  .site-name { grid-column: 1; }
  .site-description { grid-column: 1; }
  nav.primary { grid-column: 2; grid-row: 1 / 3; margin-top: 0; }
}

main, .wrap { flex: 1 0 auto; width: 100%; box-sizing: border-box; max-width: 46rem;
  margin: 0 auto; padding: 2.5rem 1.25rem; }
h1, h2, h3 { line-height: 1.2; color: #14213d; }
h1 { font-size: clamp(2rem, 7vw, 2.6rem); font-weight: 800; margin-top: 0.5rem; }
h1::after {
  content: "";
  display: block;
  width: 4rem;
  height: 0.3rem;
  margin-top: 0.75rem;
  background: #f4a261;
  border-radius: 0.15rem;
}
img { max-width: 100%; height: auto; border-radius: 0.5rem; }

footer.site {
  background: #14213d;
  color: #ffffff;
  padding: 1.5rem max(1.25rem, calc((100% - 43.5rem) / 2));
  font-size: 0.95rem;
}
footer.site a { color: #ffffff; }
footer.site p { margin: 0; }
"""

_LOOK_RULES = {"sunrise": _SUNRISE, "meadow": _MEADOW, "harbour": _HARBOUR}

_JOURNAL_RULES = """.prose { overflow-wrap: break-word; }
.post-meta, .eyebrow, .lead, .page-intro, .comments-note { color: #3a3a3a; }
.post-list, .comment-list { list-style: none; padding: 0; }
.post-list li, .comment { margin-bottom: 1.25rem; }
.chip { display: inline-block; margin: 0 0.5rem 0.5rem 0; }
.pager, .back { margin-top: 2rem; }
"""


def _style_code(look: str) -> str:
    return (f"/* {say('starter.style_note')} */\n" + _LOOK_RULES[look] + "\n"
            + f"/* {say('starter.journal_note')} */\n" + _JOURNAL_RULES)


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
    <h1>{heading}</h1>
    <p>{counting}</p>
    <p>{counted}</p>
    <p>{policy}</p>
    <p>{questions}</p>
  </main>
  <!-- FOOTER:START -->
  <!-- FOOTER:END -->
</body>
</html>
"""

_FOOTER_END = re.compile(r"</footer\s*>", re.IGNORECASE)


def privacy_page(site_name: str, sheets: tuple[str, ...]) -> str:
    """The Privacy page, linking each stylesheet from depth 1."""
    links = "\n  ".join(f'<link rel="stylesheet" href="../{html.escape(sheet, quote=True)}">'
                      for sheet in sheets)
    return _PRIVACY.format(
        title=say("starter.privacy.title", name=html.escape(site_name, quote=True)),
        links=links, heading=say("starter.privacy"),
        counting=say("starter.privacy.counting"), counted=say("starter.privacy.counted"),
        policy=say("starter.privacy.policy"), questions=say("starter.privacy.questions"))


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


def fill(folder: Path, site_name: str, look: str = LOOKS[0]) -> None:
    """§ 4.3, in order: the marker, each starter file only where it is absent,
    the templates, and the journal off. `look` is one of LOOKS; any other,
    a forged post's, is the first (PRESS-0239). A StoreError propagates, and
    what was written stays, so setup can offer the box again and finish the
    fill."""
    if look not in _LOOK_RULES:
        look = LOOKS[0]
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
            title=name, up="", page="Home", heading=say("starter.welcome", name=name),
            words=say("starter.home.words"))),
        (store.PAGES_FOLDER, "about", _PAGE.format(
            title=say("starter.about.title", name=name), up="../", page="about",
            heading=say("starter.about"), words=say("starter.about.words"))),
    )
    for kind, file_name, text in files:
        if not store.html_path_for(folder, kind, file_name).exists():
            store.write_html(folder, kind, file_name, text)
    if not store.style_code_path(folder).exists():
        store.write_style_code(folder, _style_code(look))
    templates.seed(folder)
    store.write_journal(folder, False)
