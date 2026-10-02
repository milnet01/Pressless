"""The plain starter site, for an install that never ran Import (PRESS-0126).

Setup offers it on a Store that holds no site, and `fill` copies it in: a
header, footer and menu, a Home and an About page, the templates, and a plain
stylesheet, with the journal off. Nothing is written over a file the Store
already holds. A marker in Pressless's own folder says the starter has not
been published yet, which is what lets publishing refuse to replace a site
already on GitHub (docs/specs/PRESS-0126-starter-site.md).
"""
from __future__ import annotations

import html
from pathlib import Path

from pressless import store, templates

MARKER = "starter-unpublished"   # in Pressless's own folder; empty file

# Shipped to every install, so they name nobody and assume nothing about the
# user (§ 4.3). {name} is the site's name, already escaped.
_HEADER = """<!-- The site's header: every page is built with it. -->
<header class="site">
  <a class="site-name" href="{{{{UP}}}}index.html">{name}</a>
{{{{NAVIGATION}}}}
</header>
"""

_NAVIGATION = """  <nav class="primary" aria-label="Primary">
    <a href="{{UP}}index.html" data-nav="Home">Home</a>
    <a href="{{UP}}pages/about.html" data-nav="about">About</a>
  </nav>"""

_FOOTER = """<!-- The site's footer: every page is built with it. -->
<footer class="site">
  <p>&copy; {{{{YEAR}}}} {name}</p>
</footer>
"""

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

# Large type, dark on light, underlined links and a visible focus ring: the
# first user is partially sighted (§ 4.3). Contrast on #ffffff, by the WCAG
# formula: #1a1a1a 17.4:1, #0b4fa8 7.8:1, #3a3a3a 11.4:1.
_STYLE_CODE = """/* Your site's look. Change anything here; Pressless publishes it as it is. */

html { font-size: 112.5%; }
body {
  margin: 0;
  background: #ffffff;
  color: #1a1a1a;
  font-family: Georgia, "Times New Roman", serif;
  line-height: 1.6;
}
a { color: #0b4fa8; text-decoration: underline; }
a:focus-visible, button:focus-visible { outline: 3px solid #0b4fa8; outline-offset: 2px; }

header.site, main, footer.site, .wrap {
  max-width: 42rem;
  margin: 0 auto;
  padding: 1rem 1.25rem;
}
header.site { border-bottom: 2px solid #1a1a1a; }
.site-name { font-size: 1.5rem; font-weight: bold; text-decoration: none; color: #1a1a1a; }
nav.primary { margin-top: 0.5rem; }
nav.primary a { margin-right: 1.25rem; }
nav.primary a[aria-current="page"] { font-weight: bold; text-decoration: none; }
footer.site { border-top: 2px solid #1a1a1a; margin-top: 2rem; font-size: 0.95rem; }

h1, h2, h3 { line-height: 1.25; }
img { max-width: 100%; height: auto; }

/* The journal's pages, should you turn it on. */
.post-meta, .eyebrow, .lead, .page-intro, .comments-note { color: #3a3a3a; }
.post-list, .comment-list { list-style: none; padding: 0; }
.post-list li, .comment { margin-bottom: 1.25rem; }
.chip { display: inline-block; margin: 0 0.5rem 0.5rem 0; }
.pager, .back { margin-top: 2rem; }
"""


def offered(folder: Path) -> bool:
    """§ 4.4: on a Store holding no site, or one whose fill was cut short."""
    return not store.holds_a_site(folder) or unpublished(folder)


def unpublished(folder: Path) -> bool:
    return (Path(folder) / MARKER).is_file()


def published(folder: Path) -> None:
    """Remove the marker; absent is fine. An OSError is the caller's."""
    (Path(folder) / MARKER).unlink(missing_ok=True)


def fill(folder: Path, site_name: str) -> None:
    """§ 4.3, in order: the marker, each starter file only where it is absent,
    the templates, and the journal off. A StoreError propagates, and what was
    written stays, so setup can offer the box again and finish the fill."""
    folder = Path(folder)
    marker = folder / MARKER
    try:
        marker.write_bytes(b"")
    except OSError as exc:
        raise store.StoreError(f"{MARKER} could not be written: {exc.strerror}") from exc

    name = html.escape(site_name, quote=True)
    files = (
        (store.FURNITURE_FOLDER, "header", _HEADER.format(name=name)),
        (store.FURNITURE_FOLDER, "navigation", _NAVIGATION),
        (store.FURNITURE_FOLDER, "footer", _FOOTER.format(name=name)),
        (store.PAGES_FOLDER, "index", _PAGE.format(
            title=name, up="", page="Home", heading=f"Welcome to {name}",
            words="This is your homepage. Change these words to say what your "
                  "site is about.")),
        (store.PAGES_FOLDER, "about", _PAGE.format(
            title=f"About — {name}", up="../", page="about", heading="About",
            words="Say who you are and what this site is for.")),
    )
    for kind, file_name, text in files:
        if not store.html_path_for(folder, kind, file_name).exists():
            store.write_html(folder, kind, file_name, text)
    if not store.style_code_path(folder).exists():
        store.write_style_code(folder, _STYLE_CODE)
    templates.seed(folder)
    store.write_journal(folder, False)
