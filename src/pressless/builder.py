"""The Builder -- the Store and Settings become the site folder (PRESS-0008).

One call turns every published entry, fixed page and furniture file into the
finished site: every page today's generator wrote, at the address it wrote it,
plus `content/`, the sitemap and `robots.txt`. It is the only part that can keep
a draft off the site (S7), which is why it never lists the drafts folder.

It renders writing only through Marks (rule 2), reaches no network (rule 4),
and writes into a new folder beside `into` that replaces it only once every
file is there (§4.8), so a failure leaves the site folder as it was.

The page shells are ported from today's generator in the sibling workspace,
never copied: that code names the writer, and this repository must not.

The contract is `docs/specs/PRESS-0008-builder.md`; the section and INV-N
references below are to it.
"""
from __future__ import annotations

import fnmatch
import html
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageOps, ImageSequence

from pressless import marks, store
from pressless.settings import Settings

ROOT_OUTPUT = ("index.html", "pages", "blog", "photographs", "content",
               "sitemap.xml", "robots.txt")
PER_PAGE = 20
STYLESHEETS = ("assets/site.css", "assets/blog.css")   # every page links these, from the root
BODY_CLASS = "post-body prose"                         # the class an entry's body is written in
LONGEST_SIDE = 1600


@dataclass(frozen=True)
class Built:
    files: tuple[str, ...]      # every file written, relative to `into`, "/"-separated, sorted
    filtered: tuple[str, ...]   # published slugs the Daily Prompt filter kept off every page


@dataclass(frozen=True)
class Html:
    kind: str                   # store.PAGES_FOLDER or store.FURNITURE_FOLDER
    name: str
    html: str


class BuildStopped(Exception):
    """The Store holds something that cannot be built; `into` is unchanged."""


class SiteFolderUnusable(Exception):
    """`into` could not be replaced; it is as it was."""


# §4.3: a date reads the same on every system. Never a platform strftime flag
# for the day, and never the locale's month names (INV-12).
_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")

# §4.4, matched as Import matches them.
_START = re.compile(r"<!--\s*(HEADER|FOOTER):START(?P<attrs>[^>]*?)-->")
_ANY_END = re.compile(r"<!--\s*(?:HEADER|FOOTER):END\s*-->")
_PAGE_ATTR = re.compile(r'page="([^"]*)"')
_LEADING_COMMENT = re.compile(r"^\s*<!--.*?-->[ \t]*\n", re.S)
_ANIMATION = (" reveal-load d1", " reveal-load d2", " reveal-load d3")

# §4.6: re-encoded in their own format. Anything else Pillow opens is refused.
_REENCODED = {"JPEG": "JPEG", "MPO": "JPEG", "PNG": "PNG", "WEBP": "WEBP"}

_JOURNAL_LEAD = "poetry, lyrics, photographs and passing thoughts"


def web_photograph(name: str) -> str:
    """The address of a picture's web copy, from the site's root (§4.1). The
    file itself is `photographs/<name>`; only the address is encoded."""
    return f"{store.PHOTOGRAPHS_FOLDER}/{quote(name, safe='')}"


def build(folder: Path, settings: Settings, into: Path, *,
          photo_src: marks.PhotoSrc | None = None,
          change: store.Entry | Html | None = None) -> Built:
    """§4.8, in order: settle what an interrupted build left, refuse a folder
    the Builder did not make, build everything into `<into>.pressless-new`, and
    swap it in only once it is whole."""
    folder = Path(folder)
    return _replace(Path(into), photo_src is None,
                    lambda new: _Build(folder, settings, new, photo_src, change).run())


def preview(folder: Path, settings: Settings, into: Path, entry: store.Entry, *,
            photo_src: marks.PhotoSrc) -> str:
    """PRESS-0012 §4.2: the one page `build` would write for `entry` published,
    into `into` by §4.8's order. Returns its path relative to `into`."""
    folder = Path(folder)

    def write(new: Path) -> str:
        page = _Build(folder, settings, new, photo_src, entry)
        page.read_furniture()
        for name in (*entry.categories, *entry.tags):
            page.refuse_an_unusable_name(entry, name)
        page.entry_page(entry)
        return page.files[0]

    return _replace(Path(into), False, write)


def _replace(into: Path, publishing: bool, write):
    """§4.8's order around `write`, which fills the new folder and returns what
    the caller hands back."""
    shown = "the site folder" if publishing else "the preview folder"
    new = into.with_name(f"{into.name}.pressless-new")
    old = into.with_name(f"{into.name}.pressless-old")

    if not into.parent.is_dir():
        raise SiteFolderUnusable(f"the folder {shown} sits in does not exist")
    try:
        if not into.exists() and old.is_dir():
            os.rename(old, into)
        _refuse_a_folder_it_did_not_make(into, shown)
        if new.exists():
            shutil.rmtree(new)
        if into.exists() and old.exists():
            shutil.rmtree(old)
        new.mkdir()
    except OSError as exc:
        raise SiteFolderUnusable(f"{shown} could not be prepared: {_why(exc)}") from None

    try:
        result = write(new)
    except BaseException as exc:
        shutil.rmtree(new, ignore_errors=True)
        if isinstance(exc, OSError):
            raise SiteFolderUnusable(f"{shown} could not be written: {_why(exc)}") from None
        raise

    try:
        if into.exists():
            os.rename(into, old)
        os.rename(new, into)
    except OSError as exc:
        if old.exists() and not into.exists():
            try:
                os.rename(old, into)
            except OSError:
                pass  # the next build renames it back (§4.8)
        shutil.rmtree(new, ignore_errors=True)
        raise SiteFolderUnusable(f"{shown} could not be replaced: {_why(exc)}") from None
    # Not a failed build if this fails: the next one removes it (§4.8).
    shutil.rmtree(old, ignore_errors=True)
    return result


def _refuse_a_folder_it_did_not_make(into: Path, shown: str) -> None:
    """§4.8: a folder Settings was pointed at by mistake is not one the Builder
    made, and replacing it would delete what he keeps there."""
    if not into.exists():
        return
    if not into.is_dir():
        raise SiteFolderUnusable(f"{shown} is a file, not a folder")
    for child in sorted(into.iterdir()):
        if child.name not in ROOT_OUTPUT:
            raise SiteFolderUnusable(
                f"{shown} holds {child.name}, which Pressless does not make, "
                f"so the folder was left as it is")


def _why(exc: OSError) -> str:
    return exc.strerror or type(exc).__name__


# ------------------------------------------------------------ dates (§4.3) --


def _long_date(when: datetime) -> str:
    return f"{when.day} {_MONTHS[when.month - 1]} {when.year}"


def _short_date(when: datetime) -> str:
    return f"{when.day} {_MONTHS[when.month - 1][:3]}"


def _month_year(when: datetime) -> str:
    return f"{_MONTHS[when.month - 1]} {when.year}"


def _iso_day(when: datetime) -> str:
    return f"{when.year:04d}-{when.month:02d}-{when.day:02d}"


# ------------------------------------------------------ the text of a body --


def _as_text_html(text: str) -> str:
    """Plain text as HTML, escaped by Marks rather than here (rule 2): one
    `Text` in one line of one paragraph, with the paragraph's tags removed so
    it can sit inside the shell's own element."""
    rendered = marks.to_html(
        (marks.Paragraph((marks.Line((marks.Text(text),)),)),), _no_photographs)
    return rendered.removeprefix("<p>").removesuffix("</p>")


def _no_photographs(name: str) -> str:
    raise AssertionError(f"plain text holds no picture, yet one was named: {name}")


def _entry_text(doc: marks.Document) -> str:
    """§4.3, an entry's text: the body's Text nodes, lines joined by a space --
    or, where those hold nothing but whitespace, its top-level pictures'
    captions, so a picture-only entry reads as it does today (INV-16)."""
    lines: list[str] = []

    def text_of(nodes) -> str:
        return "".join(
            node.value if isinstance(node, marks.Text)
            else text_of(node.children) if isinstance(node, marks.Span)
            else ""
            for node in nodes)

    for block in doc:
        if isinstance(block, marks.Paragraph):
            paragraphs: tuple[marks.Paragraph, ...] = (block,)
        elif isinstance(block, marks.Quote):
            paragraphs = block.paragraphs
        else:
            continue
        lines.extend(text_of(line.children) for paragraph in paragraphs
                     for line in paragraph.lines)
    words = " ".join(lines)
    # Judged after decoding, as the cut is: an imported `&nbsp;` is no words.
    if html.unescape(words).strip():
        return words
    return " ".join(block.caption for block in doc
                    if isinstance(block, marks.Photo) and block.caption)


def _excerpt(text: str, limit: int) -> str:
    """Cut as today: character references decoded, whitespace collapsed, and an
    ellipsis where anything was cut."""
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text[:limit].rstrip() + "…" if len(text) > limit else text


# -------------------------------------------------------- furniture (§4.4) --


@dataclass(frozen=True)
class _Furniture:
    header: str
    navigation: str
    footer: str
    year: int

    def fill(self, kind: str, depth: int, *, page: str = "", animate: bool = False,
             nav: bool = True) -> str:
        if kind == "HEADER":
            text = _LEADING_COMMENT.sub("", self.header, count=1).rstrip("\n")
            navigation = ""
            if nav:
                navigation = self.navigation
                if page:
                    navigation = re.sub(
                        rf'(<a\b[^>]*\bdata-nav="{re.escape(page)}")',
                        r'\1 aria-current="page"', navigation, count=1)
            text = text.replace("{{NAVIGATION}}", navigation)
        else:
            text = _LEADING_COMMENT.sub("", self.footer, count=1).rstrip("\n")
        text = text.replace("{{UP}}", "../" * depth)
        for number, animation in enumerate(_ANIMATION, start=1):
            text = text.replace(f"{{{{ANIM{number}}}}}", animation if animate else "")
        return text.replace("{{YEAR}}", str(self.year))


def _fill_fixed_page(name: str, text: str, depth: int, furniture: _Furniture) -> str:
    """Byte for byte, except between each marker pair, which gets the filled
    furniture on lines of its own. The markers stay."""
    out, pos = [], 0
    while True:
        start = _START.search(text, pos)
        before = start.start() if start else len(text)
        if _ANY_END.search(text, pos, before):
            raise BuildStopped(f"the page {name} has a marker END with no START before it")
        if start is None:
            out.append(text[pos:])
            return "".join(out)
        kind = start.group(1)
        end = re.compile(rf"<!--\s*{kind}:END\s*-->").search(text, start.end())
        if end is None:
            raise BuildStopped(f"the page {name} has a {kind}:START with no {kind}:END after it")
        attrs = start.group("attrs").split()
        page = next((found.group(1) for attr in attrs
                     if (found := _PAGE_ATTR.fullmatch(attr))), "")
        block = furniture.fill(kind, depth, page=page, animate="animate" in attrs,
                               nav="nonav" not in attrs)
        indent = re.search(r"[ \t]*\Z", text[start.end():end.start()]).group(0)
        out.append(text[pos:start.end()] + "\n" + block + "\n" + indent + end.group(0))
        pos = end.end()


# --------------------------------------------------------------- the build --


class _Build:
    def __init__(self, folder: Path, settings: Settings, root: Path,
                 photo_src: marks.PhotoSrc | None, change: store.Entry | Html | None):
        self.folder = folder
        self.settings = settings
        self.root = root
        self.photo_src = photo_src
        self.change = change
        self.files: list[str] = []
        self.copied: set[str] = set()

    # -- writing --

    def write_text(self, relative: str, text: str) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
        self.files.append(relative)

    def write_bytes(self, relative: str, data: bytes) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self.files.append(relative)

    # -- the whole --

    def read_furniture(self) -> None:
        """The three furniture files as the Store holds them, for a preview
        (PRESS-0012 §4.2)."""
        furniture = {name: store.read_html(
                         store.html_path_for(self.folder, store.FURNITURE_FOLDER, name))
                     for name in ("header", "navigation", "footer")}
        self.furniture = _Furniture(furniture["header"], furniture["navigation"],
                                    furniture["footer"], datetime.now().year)

    def run(self) -> Built:
        entries = {slug: store.read(store.path_for(self.folder, slug, draft=False))
                   for slug in store.list_slugs(self.folder, draft=False)}
        if isinstance(self.change, store.Entry):
            entries[self.change.slug] = self.change
        pages = {name: store.read_html(store.html_path_for(self.folder, store.PAGES_FOLDER, name))
                 for name in store.list_html(self.folder, store.PAGES_FOLDER)}
        furniture = {name: store.read_html(
                         store.html_path_for(self.folder, store.FURNITURE_FOLDER, name))
                     for name in ("header", "navigation", "footer")
                     if not (isinstance(self.change, Html)
                             and self.change.kind == store.FURNITURE_FOLDER
                             and self.change.name == name)}
        if isinstance(self.change, Html):
            # The Store's own refusal of a kind or name it does not hold (§6).
            store.html_path_for(self.folder, self.change.kind, self.change.name)
            (pages if self.change.kind == store.PAGES_FOLDER else furniture)[
                self.change.name] = self.change.html
        self.furniture = _Furniture(furniture["header"], furniture["navigation"],
                                    furniture["footer"], datetime.now().year)

        pattern = self.settings.daily_prompt_filter
        filtered = sorted(slug for slug, entry in entries.items()
                          if any(fnmatch.fnmatchcase(tag, pattern) for tag in entry.tags))
        shown = sorted(
            sorted((entry for slug, entry in entries.items() if slug not in filtered),
                   key=lambda entry: entry.slug),
            key=lambda entry: entry.date, reverse=True)
        for entry in shown:
            for name in (*entry.categories, *entry.tags):
                self.refuse_an_unusable_name(entry, name)

        for entry in shown:
            self.entry_page(entry)
        self.listings(shown)
        self.archive(shown)
        for name, text in pages.items():
            depth = 0 if name == "index" else 1
            relative = "index.html" if name == "index" else f"pages/{name}{store.HTML_SUFFIX}"
            self.write_text(relative, _fill_fixed_page(name, text, depth, self.furniture))
        self.content()
        self.sitemap(sorted(pages), shown)
        return Built(files=tuple(sorted(self.files)), filtered=tuple(filtered))

    def refuse_an_unusable_name(self, entry: store.Entry, name: str) -> None:
        """§4.3: a category or tag becomes a folder name, so the Store's slug
        test decides it."""
        try:
            store.path_for(self.folder, name, draft=False)
        except store.StoreError:
            raise BuildStopped(
                f"the entry {entry.slug} is filed under {name!r}, which cannot be "
                f"part of an address: one or more of a-z, 0-9 and '-'") from None

    # -- a page's shell (§4.3) --

    def page(self, relative: str, depth: int, title: str, description: str,
             body: str) -> None:
        up = "../" * depth
        links = "\n".join(f'<link rel="stylesheet" href="{up}{sheet}">' for sheet in STYLESHEETS)
        self.write_text(f"{relative}/index.html", f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} — {html.escape(self.settings.site_name)}</title>
<meta name="description" content="{html.escape(description)}">
{links}
</head>
<body>

{self.furniture.fill("HEADER", depth, page="Journal")}

  <main class="wrap">
{body}
  </main>

{self.furniture.fill("FOOTER", depth)}

</body>
</html>
""")

    def meta(self, entry: store.Entry, up: str) -> str:
        """The date line: the entry's own date, then a chip per category."""
        chips = " ".join(
            f'<a class="chip" href="{up}blog/category/{category}/index.html">'
            f"{html.escape(_label(category))}</a>"
            for category in entry.categories)
        when = entry.date
        return f'<time datetime="{_iso_day(when)}">{_long_date(when)}</time> {chips}'

    # -- an entry --

    def entry_page(self, entry: store.Entry) -> None:
        relative = _entry_path(entry)
        depth = relative.count("/") + 1
        up = "../" * depth
        doc = marks.parse(entry.body)
        if self.photo_src is None:
            for block in doc:
                if isinstance(block, marks.Photo):
                    self.web_copy(block.name)

            def src(name: str) -> str:
                return up + web_photograph(name)
        else:
            src = self.photo_src

        heading = entry.title or _long_date(entry.date)
        tags = " ".join(
            f'<a class="chip chip--tag" href="{up}blog/tag/{tag}/index.html">'
            f"#{html.escape(tag)}</a>"
            for tag in entry.tags)
        comments = self.comments(entry)
        body = f"""
    <article class="post">
      <p class="post-meta">{self.meta(entry, up)}</p>
      <h1>{html.escape(heading)}</h1>
      <div class="{BODY_CLASS}">
{marks.render(entry.body, src)}
      </div>
      <p class="post-tags">{tags}</p>
    </article>
{comments}
    <p class="back"><a href="{up}blog/index.html">← All journal entries</a></p>"""
        description = _excerpt(_entry_text(doc), 150) or heading
        self.page(relative, depth, heading, description, body)

    def comments(self, entry: store.Entry) -> str:
        """§4.3: flat, in file order (decision 6); a body through Marks' own
        escaping as plain Text, so a reader's asterisks stay asterisks."""
        found = store.read_comments(store.comments_path_for(self.folder, entry.slug))
        if not found:
            return ""
        items = "\n".join(_comment_item(comment) for comment in found)
        count = len(found)
        return f"""
    <section class="comments" aria-label="Comments">
      <h2>{count} comment{"s" if count != 1 else ""}</h2>
      <p class="comments-note">Comments from the original journal, kept as they were written.
        New comments are not open at the moment.</p>
      <ul class="comment-list">
{items}
      </ul>
    </section>"""

    # -- photographs (§4.6) --

    def web_copy(self, name: str) -> None:
        if name in self.copied:
            return
        if name.startswith("."):
            raise BuildStopped(
                f"the photograph {name} begins with a dot, and a publish refuses such a name")
        original = store.photograph_path_for(self.folder, name)
        if not original.is_file():
            raise BuildStopped(f"the photograph {name} is not in the photographs folder")
        # Decoded and transformed first, so a picture Pillow cannot read is
        # told apart from a site folder that cannot be written.
        try:
            with Image.open(original) as picture:
                fmt = _REENCODED.get(picture.format, picture.format)
                if fmt == "GIF":
                    frames, durations = _gif_frames(picture)
                    loop = picture.info.get("loop")
                    options = {"save_all": True, "append_images": frames[1:],
                               "duration": durations}
                    if loop is not None:
                        options["loop"] = loop
                    copy = frames[0]
                elif picture.format in _REENCODED:
                    options = ({"quality": 82, "progressive": True, "optimize": True}
                               if fmt == "JPEG" else {})
                    if "icc_profile" in picture.info:
                        options["icc_profile"] = picture.info["icc_profile"]
                    copy = _bare(_shrunk(ImageOps.exif_transpose(picture)))
                else:
                    copy = None
        except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
            raise BuildStopped(
                f"the photograph {name} could not be read as a picture") from None
        if copy is None:
            raise BuildStopped(
                f"the photograph {name} is a {fmt} picture, which Pressless does not publish")
        relative = f"{store.PHOTOGRAPHS_FOLDER}/{name}"
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copy.save(target, fmt, **options)
        self.files.append(relative)
        self.copied.add(name)

    # -- listings --

    def card(self, entry: store.Entry, depth: int) -> str:
        up = "../" * depth
        if entry.title:
            label = html.escape(entry.title)
            excerpt = _excerpt(_entry_text(marks.parse(entry.body)), 180)
            excerpt_row = f'\n        <p class="post-excerpt">{_as_text_html(excerpt)}</p>'
            untitled = ""
        else:
            teaser = _excerpt(_entry_text(marks.parse(entry.body)), 48) \
                or _long_date(entry.date)
            label, excerpt_row, untitled = _as_text_html(teaser), "", " untitled"
        return f"""      <article class="post-card{untitled}">
        <p class="post-meta">{self.meta(entry, up)}</p>
        <h2><a href="{up}{_entry_path(entry)}/index.html">{label}</a></h2>{excerpt_row}
      </article>"""

    def listing(self, relative: str, depth: int, heading: str, intro: str,
                entries: list[store.Entry]) -> None:
        chunks = [entries[at:at + PER_PAGE] for at in range(0, len(entries), PER_PAGE)] or [[]]
        for number, chunk in enumerate(chunks, start=1):
            here = relative if number == 1 else f"{relative}/page/{number}"
            here_depth = depth if number == 1 else depth + 2
            cards = "\n".join(self.card(entry, here_depth) for entry in chunk)
            pager = ""
            if len(chunks) > 1:
                up = "../" * here_depth
                newer = (f"{up}{relative}/index.html" if number == 2
                         else f"{up}{relative}/page/{number - 1}/index.html")
                links = []
                if number > 1:
                    links.append(f'<a class="pg" href="{newer}">← Newer</a>')
                links.append(f'<span class="pg-count">Page {number} of {len(chunks)}</span>')
                if number < len(chunks):
                    links.append(
                        f'<a class="pg" href="{up}{relative}/page/{number + 1}/index.html">'
                        f"Older →</a>")
                pager = f'\n    <nav class="pager" aria-label="Pagination">{" ".join(links)}</nav>'
            # Where the heading already says "journal", the eyebrow would say it
            # a third time on one screen.
            eyebrow = ("" if "journal" in heading.lower()
                       else '\n      <p class="eyebrow">Journal</p>')
            body = f"""
    <div class="page-intro">{eyebrow}
      <h1>{html.escape(heading)}</h1>
      <p class="lead">{html.escape(intro, quote=False)}</p>
    </div>

    <div class="post-list">
{cards}
    </div>{pager}"""
            self.page(here, here_depth, heading, intro, body)

    def listings(self, shown: list[store.Entry]) -> None:
        count = len(shown)
        span = (f", from {_month_year(shown[-1].date)} to {_month_year(shown[0].date)}"
                if shown else "")
        self.listing("blog", 1, "The journal",
                     f"{count} entries — {_JOURNAL_LEAD}{span}.", shown)
        by_category: dict[str, list[store.Entry]] = {}
        by_tag: dict[str, list[store.Entry]] = {}
        for entry in shown:
            for category in entry.categories:
                by_category.setdefault(category, []).append(entry)
            for tag in entry.tags:
                by_tag.setdefault(tag, []).append(entry)
        for category, entries in sorted(by_category.items()):
            label = _label(category)
            self.listing(f"blog/category/{category}", 3, label,
                         f"{len(entries)} entries in {label.lower()}.", entries)
        for tag, entries in sorted(by_tag.items()):
            self.listing(f"blog/tag/{tag}", 3, f"#{tag}",
                         f"{len(entries)} entries tagged “{tag}”.", entries)

    def archive(self, shown: list[store.Entry]) -> None:
        years: dict[int, list[store.Entry]] = {}
        for entry in shown:
            years.setdefault(entry.date.year, []).append(entry)
        blocks = []
        for year in sorted(years, reverse=True):
            rows = "\n".join(
                f"          <li><time>{_short_date(entry.date)}</time> "
                f'<a href="../../{_entry_path(entry)}/index.html">'
                f"{html.escape(entry.title or _long_date(entry.date))}</a></li>"
                for entry in years[year])
            blocks.append(
                f'      <section class="arch-year">\n        <h2>{year} '
                f'<span class="arch-count">{len(years[year])}</span></h2>\n'
                f'        <ul class="arch-index">\n{rows}\n        </ul>\n      </section>')
        count = len(shown)
        joined = "\n".join(blocks)
        self.page("blog/archive", 2, "Archive", f"All {count} entries by year.", f"""
    <div class="page-intro">
      <p class="eyebrow">Journal</p>
      <h1>Archive</h1>
      <p class="lead">All {count} entries, newest first.</p>
    </div>

    <div class="archive">
{joined}
    </div>""")

    # -- content/ (§4.7) --

    def content(self) -> None:
        """The Store's own bytes, from the Store alone -- never `change`."""
        paths = []
        for slug in store.list_slugs(self.folder, draft=False):
            paths.append(store.path_for(self.folder, slug, draft=False))
            comments = store.comments_path_for(self.folder, slug)
            if comments.is_file():
                paths.append(comments)
        for kind in (store.PAGES_FOLDER, store.FURNITURE_FOLDER):
            paths.extend(store.html_path_for(self.folder, kind, name)
                         for name in store.list_html(self.folder, kind))
        paths.extend(store.template_path_for(self.folder, name)
                     for name in store.list_templates(self.folder))
        for path in paths:
            relative = path.relative_to(self.folder).as_posix()
            self.write_bytes(f"content/{relative}", path.read_bytes())

    # -- sitemap.xml and robots.txt (§4.9) --

    def sitemap(self, pages: list[str], shown: list[store.Entry]) -> None:
        address = self.settings.site_address.rstrip("/")
        urls: list[tuple[str, str | None]] = []
        if "index" in pages:
            urls.append((f"{address}/", None))
        urls += [(f"{address}/pages/{name}{store.HTML_SUFFIX}", None)
                 for name in pages if name != "index"]
        urls += [(f"{address}/blog/index.html", None),
                 (f"{address}/blog/archive/index.html", None)]
        urls += [(f"{address}/{_entry_path(entry)}/index.html", _iso_day(entry.date))
                 for entry in shown]
        lines = "\n".join(
            f"  <url><loc>{html.escape(loc, quote=False)}</loc>"
            + (f"<lastmod>{lastmod}</lastmod>" if lastmod else "")
            + "</url>"
            for loc, lastmod in urls)
        self.write_text("sitemap.xml",
                        '<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                        f"{lines}\n</urlset>\n")
        self.write_text("robots.txt",
                        "# Everything here is meant to be found.\n"
                        "User-agent: *\n"
                        "Allow: /\n"
                        "\n"
                        f"Sitemap: {address}/sitemap.xml\n")


def _entry_path(entry: store.Entry) -> str:
    """§4.3: dated by the entry's own date, never the build's."""
    when = entry.date
    return f"blog/{when.year:04d}/{when.month:02d}/{when.day:02d}/{entry.slug}"


def _label(category: str) -> str:
    """Decision 7: each hyphen a space, the first letter upper case."""
    text = category.replace("-", " ")
    return text[:1].upper() + text[1:]


def _comment_item(comment: store.Comment) -> str:
    author = html.escape(comment.author or "Anonymous")
    return f"""        <li class="comment">
          <p class="comment-meta"><strong>{author}</strong> · {_iso_day(comment.date)}</p>
          {_comment_html(comment.body)}
        </li>"""


def _comment_html(body: str) -> str:
    """§4.3: split at blank lines into Paragraphs and at newlines into Lines of
    one Text each, then Marks writes it."""
    text = body.replace("\r\n", "\n").replace("\r", "\n").strip()
    parts = (part.strip() for part in re.split(r"\n\s*\n", text))
    paragraphs = tuple(
        marks.Paragraph(tuple(marks.Line((marks.Text(line),)) for line in part.split("\n")))
        for part in parts if part)
    return marks.to_html(paragraphs, _no_photographs)


def _shrunk(picture: Image.Image) -> Image.Image:
    """Fitted inside LONGEST_SIDE on each side, never enlarged."""
    picture.thumbnail((LONGEST_SIDE, LONGEST_SIDE))
    return picture


def _bare(picture: Image.Image) -> Image.Image:
    """Nothing a saver would carry from the original: Pillow's JPEG saver takes
    a comment from `info`, so `info` keeps only what draws the picture."""
    picture.info = {key: value for key, value in picture.info.items()
                    if key == "transparency"}
    return picture


def _gif_frames(picture: Image.Image) -> tuple[list[Image.Image], list[int]]:
    """§4.6 step 4: every frame, each shrunk, its timing kept."""
    frames, durations = [], []
    for frame in ImageSequence.Iterator(picture):
        durations.append(frame.info.get("duration", 0))
        frames.append(_bare(_shrunk(frame.convert("RGBA"))))
    return frames, durations
