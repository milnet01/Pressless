"""The editor: the list, the box, and the real page beside it (PRESS-0012).

His words save themselves shortly after he stops typing, and every save
rebuilds the preview, which is the Builder's own page for the entry
(docs/specs/PRESS-0012-editor.md § 4.2). Changes to a published entry go into
a working copy -- a draft carrying a `Replaces` header -- so the live version is
untouched until PRESS-0013 publishes them (§ 3 decision 2).

Nothing is held between requests: every route reads the Store afresh, and a
save refuses a file this window did not see (§ 4.8, design § State).
"""
from __future__ import annotations

import dataclasses
import hashlib
import html
import json
import re
import threading
import unicodedata
import urllib.parse
from datetime import datetime
from pathlib import Path

from pressless import builder, paths, settings, store
from pressless.face import (
    SENTENCES,
    Face,
    Reply,
    Request,
    Sentence,
    Site,
    render_notices,
    within,
)

PREVIEW_FOLDER = "preview"          # inside Pressless's own folder; the Face's alone
REPLACES = "Replaces"               # the header naming the published entry a copy changes
UNTITLED = "untitled"
COPY_SUFFIX = "-changes"
LONGEST_ADDRESS = 60
PREVIEW_ADDRESS = "/preview/"
ASSETS_ADDRESS = "/preview/assets/"
ORIGINALS_ADDRESS = "/originals/"


class ChangedElsewhere(Exception):
    """The file is not the one this window last saw (§ 4.8)."""


class TooManyCopies(Exception):
    """Two drafts replace one published entry (§ 4.1)."""


# Added here rather than in face.py, which cannot import this module back
# (§ 4.1).
SENTENCES[ChangedElsewhere] = Sentence(
    "This entry was changed in another window or outside Pressless, so Pressless "
    "did not save over it.",
    Site.UNCHANGED,
    "Copy anything you typed since, then open the entry again from your list.",
)
SENTENCES[TooManyCopies] = Sentence(
    "More than one draft holds unpublished changes to this entry, so Pressless did "
    "not open it.",
    Site.UNCHANGED,
    "Open your Pressless-data folder, keep one of those drafts, and move the others "
    "out of the drafts folder.",
)

# Every write, preview and publish runs under it; a threading.Lock cannot be
# taken twice, so `save` leaves it to its caller (PRESS-0013 § 4.1).
LOCK = threading.Lock()

_JSON = "application/json"
_HTML = "text/html; charset=utf-8"


def address_for(title: str) -> str:
    """A new entry's address, from its title (§ 4.1)."""
    text = "".join(ch for ch in title if unicodedata.category(ch) not in ("Cc", "Cf"))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower())[:LONGEST_ADDRESS].strip("-")
    return text or UNTITLED


def free_address(folder: Path, wanted: str) -> str:
    """`wanted`, or the first of `wanted-2`, `wanted-3` … no entry holds and the
    Store accepts (§ 4.1)."""
    number = 1
    while True:
        candidate = wanted if number == 1 else f"{wanted}-{number}"
        try:
            if not store.exists(folder, candidate):
                return candidate
        except store.StoreError:
            pass  # a name the Store refuses, such as a Windows device name
        number += 1


def working_copy(folder: Path, slug: str) -> str | None:
    """The draft holding unpublished changes to the published entry `slug`
    (§ 4.1). Raises TooManyCopies where two drafts do."""
    if slug not in store.list_slugs(folder, draft=False):
        return None
    found = [draft for draft in store.list_slugs(folder, draft=True)
             if _named(folder, draft) == slug]
    if len(found) > 1:
        raise TooManyCopies(f"{len(found)} drafts replace the entry {slug}")
    return found[0] if found else None


def photo_src(name: str) -> str:
    """The preview's address for a photograph's original (§ 4.1)."""
    return ORIGINALS_ADDRESS + urllib.parse.quote(name, safe="")


def register(face: Face, folder: Path) -> None:
    """Add the editor's routes to `face` (§ 4.4). `folder` is Pressless's own
    folder, the one `face.serve` was handed."""
    folder = Path(folder)

    def route(handler):
        return lambda request: handler(face, folder, LOCK, request)

    face.add_page("GET", "/", route(_list))
    face.add_page("POST", "/new", route(_new))
    face.add_page("GET", "/edit", route(_edit))
    face.add_page("POST", "/save", route(_save))
    face.add_page("POST", "/address", route(_address))
    face.add_page("POST", "/discard", route(_discard))
    face.add_files(ASSETS_ADDRESS, within(folder / paths.PREVIEW_ASSETS))
    face.add_files(PREVIEW_ADDRESS, within(folder / PREVIEW_FOLDER))
    face.add_files(ORIGINALS_ADDRESS, lambda name: store.photograph_path_for(folder, name))


# ------------------------------------------------------------- the Store ---


def _named(folder: Path, draft: str) -> str | None:
    """The `Replaces` value of a draft, or None -- an unreadable one included,
    which the list reports on its own (§ 4.5)."""
    try:
        entry = store.read(store.path_for(folder, draft, draft=True))
    except store.StoreError:
        return None
    return _replaces(entry)


def _replaces(entry: store.Entry) -> str | None:
    return next((value for name, value in entry.extra if name == REPLACES), None)


def _replaced(folder: Path, entry: store.Entry) -> str | None:
    """The published entry a draft is a working copy of, or None: a draft whose
    `Replaces` names no published entry is an ordinary draft (§ 4.1)."""
    named = _replaces(entry)
    if named is None or named not in store.list_slugs(folder, draft=False):
        return None
    return named


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _form(request: Request) -> dict[str, str]:
    """Every POST body is form-encoded, read as setup reads its own (§ 4.4)."""
    fields = urllib.parse.parse_qs(request.body.decode("utf-8"), keep_blank_values=True)
    return {name: values[0] for name, values in fields.items()}


def _list_of(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _preview(face: Face, folder: Path, entry: store.Entry, *, draft: bool
             ) -> tuple[str | None, str | None]:
    """§ 4.8 step 5: the preview's address, or the failure in its place."""
    shown = entry
    named = _replaced(folder, entry) if draft else None
    if named is not None:
        shown = dataclasses.replace(entry, slug=named, extra=tuple(
            field for field in entry.extra if field[0] != REPLACES))
    try:
        saved = settings.load(folder)
        relative = builder.preview(folder, saved, folder / PREVIEW_FOLDER, shown,
                                   photo_src=photo_src)
    except Exception as exc:  # noqa: BLE001 -- a preview failure never undoes the save
        return None, face.fail(exc, publishing=False)
    return PREVIEW_ADDRESS + relative, None


def _failed(face: Face, notices: list[str], failure: Exception) -> Reply:
    body = render_notices(notices) + face.fail(failure, publishing=False)
    return Reply(body.encode("utf-8"), _HTML, status=409)


def _json(value: dict) -> Reply:
    return Reply(json.dumps(value).encode("utf-8"), _JSON)


def _edit_address(slug: str) -> str:
    return "/edit?slug=" + urllib.parse.quote(slug, safe="")


# ---------------------------------------------------------------- routes ---


def _list(face: Face, folder: Path, lock: threading.Lock, request: Request) -> str:
    """§ 4.5."""
    readable: dict[bool, list[store.Entry]] = {True: [], False: []}
    unreadable: dict[bool, list[str]] = {True: [], False: []}
    first_failure: Exception | None = None
    with face.capture() as notices:
        for draft in (True, False):
            for slug in store.list_slugs(folder, draft=draft):
                try:
                    readable[draft].append(store.read(store.path_for(folder, slug, draft=draft)))
                except store.StoreError as exc:
                    first_failure = first_failure or exc
                    unreadable[draft].append(slug)
        try:
            pages = _pages(folder)
        except store.StoreError as exc:
            first_failure = first_failure or exc
            pages = "<p>Pressless cannot open your pages folder.</p>"
    published = {entry.slug for entry in readable[False]}
    changed = {_replaces(entry) for entry in readable[True]} & published
    drafts = [entry for entry in readable[True] if _replaces(entry) not in published]

    def rows(entries: list[store.Entry], broken: list[str]) -> str:
        ordered = sorted(sorted(entries, key=lambda entry: entry.slug),
                         key=lambda entry: entry.date, reverse=True)
        items = []
        for entry in ordered:
            note = (" <em>changes not on your site yet</em>"
                    if entry.slug in changed else "")
            items.append(
                f'<li><a href="{html.escape(_edit_address(entry.slug), quote=True)}">'
                f"{html.escape(entry.title or 'untitled')}</a> "
                f"<small>{entry.date:%d %b %Y}</small>{note}</li>")
        items.extend(f"<li>{html.escape(slug)} <em>Pressless cannot open this file</em></li>"
                     for slug in broken)
        return "<ul>" + "".join(items) + "</ul>" if items else "<p>None yet.</p>"

    failure = face.fail(first_failure, publishing=False) if first_failure else ""
    return (render_notices(notices) + failure +
            '<h1>Your writing</h1>'
            # PRESS-0023 § 4.9: what other parts show here, without this
            # module importing them.
            + "".join(face.list_pieces(above=True)) +
            '<div id="undo-result"></div>'
            '<div id="listing">'
            '<form method="post" action="/new"><label>Title '
            '<input name="title" autocomplete="off"></label> '
            "<button>New entry</button></form>"
            # PRESS-0015 § 4.6: it always shows, and nothing asks GitHub before
            # showing it (§ 3 decision 3).
            '<p><button type="button" data-undo>Undo the last publish</button> '
            '<span id="undo-status"></span></p>'
            f"<h2>Drafts</h2>{rows(drafts, unreadable[True])}"
            f"<h2>On your site</h2>{rows(readable[False], unreadable[False])}"
            f"<h2>Your pages</h2>{pages}"
            "</div>"
            + "".join(face.list_pieces(above=False)) +
            f"<script>{_UNDO_SCRIPT}</script>")


def _pages(folder: Path) -> str:
    """PRESS-0014 § 4.4: each fixed page, then the three furniture files, each
    saying where its changes are not on the site yet. Drawn from the Store
    alone, so this module imports nothing of page_editor.py."""
    rows = [(store.PAGES_FOLDER, name, "Home" if name == "index" else name)
            for name in store.list_html(folder, store.PAGES_FOLDER)]
    rows += [(store.FURNITURE_FOLDER, name, name.capitalize())
             for name in ("header", "footer", "navigation")]
    items = []
    for kind, name, label in rows:
        address = "/page?" + urllib.parse.urlencode({"kind": kind, "name": name})
        note = (" <em>changes not on your site yet</em>"
                if store.html_path_for(folder, kind, name, waiting=True).is_file() else "")
        items.append(f'<li><a href="{html.escape(address, quote=True)}">'
                     f"{html.escape(label)}</a>{note}</li>")
    return "<ul>" + "".join(items) + "</ul>"


def _new(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.6."""
    title = _form(request).get("title", "")
    with lock, face.capture():
        slug = free_address(folder, address_for(title))
        store.write(folder, store.Entry(
            slug=slug, title=title.strip(), date=datetime.now().replace(microsecond=0),
            categories=(), tags=(), body="", extra=()), draft=True)
    return Reply(b"", "text/plain; charset=utf-8", status=303, location=_edit_address(slug))


def _edit(face: Face, folder: Path, lock: threading.Lock, request: Request) -> str | Reply:
    """§ 4.7."""
    slug = request.query.get("slug", "")
    with lock, face.capture() as notices:
        try:
            if slug in store.list_slugs(folder, draft=True):
                draft = True
            elif slug in store.list_slugs(folder, draft=False):
                copy = working_copy(folder, slug)
                if copy is not None:
                    return Reply(b"", "text/plain; charset=utf-8", status=303,
                                 location=_edit_address(copy))
                draft = False
            else:
                raise store.EntryNotFound(f"there is no entry {slug!r}")
            path = store.path_for(folder, slug, draft=draft)
            entry = store.read(path)
            base = _digest(path)
        except (store.StoreError, TooManyCopies) as exc:
            failure: Exception | None = exc
        else:
            failure = None
            preview, preview_failure = _preview(face, folder, entry, draft=draft)
    if failure is not None:
        return render_notices(notices) + face.fail(failure, publishing=False)
    return render_notices(notices) + _page(folder, entry, draft, base, preview, preview_failure)


def _page(folder: Path, entry: store.Entry, draft: bool, base: str,
          preview: str | None, failure: str | None) -> str:
    def attr(value: str) -> str:
        return html.escape(value, quote=True)

    named = _replaced(folder, entry) if draft else None
    if not draft:
        standing = ("<p>This entry is on your site. Your changes stay on this computer "
                    "until you publish it.</p>")
        address = ""
    elif named is not None:
        standing = ("<p>These changes are not on your site yet.</p>"
                    '<form method="post" action="/discard">'
                    f'<input type="hidden" name="slug" value="{attr(entry.slug)}">'
                    f'<input type="hidden" name="base" value="{attr(base)}">'
                    "<button>Throw away changes</button></form>")
        address = ""
    else:
        standing = "<p>A draft. It is not on your site.</p>"
        address = (f'<label>Address <input name="address" value="{attr(entry.slug)}">'
                   '</label> <button type="button" data-editor="address">'
                   'Change address</button> <span id="address-hint"></span>')
    stylesheets = "".join(f'<link rel="stylesheet" href="{attr(PREVIEW_ADDRESS + sheet)}">'
                          for sheet in builder.STYLESHEETS)
    return f"""{stylesheets}
<p><a href="/">Your writing</a> <span id="save-status"></span></p>
{standing}
<div id="notices"></div>
<form id="editor" data-slug="{attr(entry.slug)}" data-draft="{'1' if draft else '0'}"
 data-base="{attr(base)}" onsubmit="return false">
<label>Title <input name="title" value="{attr(entry.title)}"></label>
<label>Categories <input name="categories"
 value="{attr(store.LIST_SEPARATOR.join(entry.categories))}"></label>
<label>Tags <input name="tags" value="{attr(store.LIST_SEPARATOR.join(entry.tags))}"></label>
{address}
<p><button type="button" data-editor="publish">Publish</button>
 <span id="publish-status"></span>
 <button type="button" data-undo>Undo the last publish</button>
 <span id="undo-status"></span></p>
<textarea name="body" class="{attr(builder.BODY_CLASS)}" rows="24">
{html.escape(entry.body)}</textarea>
</form>
<div id="failure">{failure or ""}</div>
<div id="undo-result"></div>
<iframe id="preview" title="Preview" sandbox="allow-same-origin allow-scripts"
 src="{attr(preview or 'about:blank')}"></iframe>
<script>{_EDITOR_SCRIPT}</script>
<script>{_UNDO_SCRIPT}</script>"""


def save(folder: Path, form: dict[str, str]) -> tuple[store.Entry, str]:
    """PRESS-0012 § 4.8 steps 1 to 4: write the box to its draft, and return the
    entry written and its new digest. Takes no lock; the caller holds LOCK."""
    slug, draft, base = form.get("slug", ""), form.get("draft") == "1", form.get("base", "")
    path = store.path_for(folder, slug, draft=draft)
    entry = store.read(path)
    if _digest(path) != base:
        raise ChangedElsewhere(f"the entry {slug} changed since this window read it")
    extra = entry.extra
    written_slug = slug
    if not draft:
        if working_copy(folder, slug) is not None:
            raise ChangedElsewhere(f"the entry {slug} gained a working copy")
        written_slug = free_address(folder, slug + COPY_SUFFIX)
        extra = tuple(field for field in entry.extra
                      if field[0] != REPLACES) + ((REPLACES, slug),)
    body = form.get("body", "").replace("\r\n", "\n").replace("\r", "\n")
    written = store.Entry(
        slug=written_slug, title=form.get("title", "").strip(), date=entry.date,
        categories=_list_of(form.get("categories", "")),
        tags=_list_of(form.get("tags", "")), body=body, extra=extra)
    return written, _digest(store.write(folder, written, draft=True))


def _save(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.8."""
    form = _form(request)
    with lock, face.capture() as notices:
        try:
            written, new_base = save(folder, form)
        except (store.StoreError, ChangedElsewhere, TooManyCopies) as exc:
            failure: Exception | None = exc
        else:
            failure = None
            preview, preview_failure = _preview(face, folder, written, draft=True)
    if failure is not None:
        return _failed(face, notices, failure)
    return _json({"slug": written.slug, "draft": True, "base": new_base, "preview": preview,
                  "failure": preview_failure, "notices": render_notices(notices)})


def _address(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.9."""
    form = _form(request)
    slug, base, address = form.get("slug", ""), form.get("base", ""), form.get(
        "address", "").strip()
    hint = None
    with lock, face.capture() as notices:
        try:
            entry = (store.read(store.path_for(folder, slug, draft=True))
                     if slug in store.list_slugs(folder, draft=True) else None)
            if entry is None or _replaced(folder, entry) is not None:
                hint = "Only a draft's address can be changed here."
            elif address != slug:
                try:
                    taken = store.exists(folder, address)
                except store.StoreError:
                    hint = "An address uses only the letters a to z, the digits 0 to 9 and -."
                else:
                    if taken:
                        hint = "Another entry already uses that address."
            if hint is None and entry is not None and address != slug:
                path = store.path_for(folder, slug, draft=True)
                if _digest(path) != base:
                    raise ChangedElsewhere(f"the entry {slug} changed since this window read it")
                store.write(folder, dataclasses.replace(entry, slug=address), draft=True)
                comments = store.comments_path_for(folder, slug)
                if comments.is_file():
                    store.write_comments(folder, address, store.read_comments(comments))
                    store.move_to_bin(folder, comments)
                store.move_to_bin(folder, path)
                slug = address
                base = _digest(store.path_for(folder, slug, draft=True))
        except (store.StoreError, ChangedElsewhere) as exc:
            failure: Exception | None = exc
        else:
            failure = None
    if failure is not None:
        return _failed(face, notices, failure)
    return _json({"slug": slug, "draft": True, "base": base, "preview": None,
                  "failure": None, "notices": render_notices(notices), "hint": hint})


def _discard(face: Face, folder: Path, lock: threading.Lock, request: Request) -> Reply:
    """§ 4.10."""
    form = _form(request)
    slug, base = form.get("slug", ""), form.get("base", "")
    with lock, face.capture() as notices:
        try:
            if slug not in store.list_slugs(folder, draft=True):
                raise ChangedElsewhere(f"the draft {slug} is not there")
            path = store.path_for(folder, slug, draft=True)
            named = _replaced(folder, store.read(path))
            if named is None or _digest(path) != base:
                raise ChangedElsewhere(f"the draft {slug} is not the working copy this "
                                       "window read")
            store.move_to_bin(folder, path)
        except (store.StoreError, ChangedElsewhere) as exc:
            failure: Exception | None = exc
        else:
            failure = None
    if failure is not None:
        return _failed(face, notices, failure)
    return Reply(b"", "text/plain; charset=utf-8", status=303, location=_edit_address(named))


# The page's script (§ 4.7). A change saves about a second after the last one,
# never two saves at once, and on leaving only where a change is unsaved.
# PRESS-0015 s 4.6. Both pages carry this. Neither reloads itself (s 4.2):
# the reply is the only place the summary and the gathered notices exist, and a
# reload throws both away before he has read them. So the box is replaced with
# what came back, and a link back to his list is offered instead.
_UNDO_SCRIPT = """
(() => {
  const button = document.querySelector("button[data-undo]");
  if (!button) return;
  const said = document.getElementById("undo-status");
  const result = document.getElementById("undo-result");

  const show = (fragment, sentence) => {
    result.innerHTML = fragment || "";
    if (sentence) {
      const line = document.createElement("p");
      line.textContent = sentence;
      result.appendChild(line);
    }
    const back = document.createElement("p");
    const link = document.createElement("a");
    link.href = "/";
    link.textContent = "Back to your writing";
    back.appendChild(link);
    result.appendChild(back);
    for (const box of [document.getElementById("editor"),
                       document.getElementById("listing")]) {
      if (box) box.hidden = true;
    }
  };

  button.addEventListener("click", async () => {
    button.disabled = true;
    said.textContent = "Putting your site back\u2026 this can take a few minutes. " +
      "Keep this page open.";
    try {
      const answer = await fetch("/undo", {method: "POST"});
      const text = await answer.text();
      said.textContent = "";
      if (answer.status !== 200) { show("", text); return; }
      const reply = JSON.parse(text);
      show((reply.notices || "") + (reply.undone ? "" : reply.failure || ""),
           reply.undone ? reply.summary : "");
    } catch (error) {
      said.textContent = "";
      show("", "Pressless could not reach itself. Your site was not changed.");
    } finally {
      button.disabled = false;
    }
  });
})();
"""


_EDITOR_SCRIPT = """
(() => {
  const form = document.getElementById("editor");
  const state = {slug: form.dataset.slug, draft: form.dataset.draft, base: form.dataset.base};
  const status = document.getElementById("save-status");
  let timer = null, inFlight = false, dirty = false, stopped = false;

  const fields = () => {
    const data = new URLSearchParams();
    data.set("slug", state.slug); data.set("draft", state.draft); data.set("base", state.base);
    for (const name of ["title", "categories", "tags", "body"]) {
      data.set(name, form.elements[name].value);
    }
    return data;
  };
  const adopt = (reply) => {
    state.slug = reply.slug; state.draft = reply.draft ? "1" : "0"; state.base = reply.base;
    document.querySelectorAll("input[name=base]").forEach((input) => { input.value = reply.base; });
    history.replaceState(null, "", "/edit?slug=" + encodeURIComponent(reply.slug));
    document.getElementById("notices").innerHTML = reply.notices;
  };
  const stop = (text) => {
    stopped = true;
    status.textContent = "Not saved";
    document.getElementById("failure").innerHTML = text;
  };

  async function save() {
    if (stopped || inFlight || !dirty) return;
    inFlight = true; dirty = false; status.textContent = "Saving";
    try {
      const answer = await fetch("/save", {method: "POST", body: fields()});
      const text = await answer.text();
      if (answer.status !== 200) { stop(text); return; }
      const reply = JSON.parse(text);
      adopt(reply);
      document.getElementById("failure").innerHTML = reply.failure || "";
      if (reply.preview) {
        document.getElementById("preview").src = reply.preview + "?n=" + Date.now();
      }
      status.textContent = "Saved";
    } catch (error) {
      stop("");
    } finally {
      inFlight = false;
      if (dirty && !stopped) schedule();
    }
  }
  function schedule() { clearTimeout(timer); timer = setTimeout(save, 1000); }

  form.addEventListener("input", (event) => {
    if (event.target.name === "address") return;
    dirty = true; schedule();
  });
  window.addEventListener("pagehide", () => {
    if (stopped || inFlight || !dirty) return;
    fetch("/save", {method: "POST", body: fields(), keepalive: true});
  });

  const publish = document.querySelector("button[data-editor=publish]");
  publish.addEventListener("click", async () => {
    clearTimeout(timer);
    while (inFlight) await new Promise((resolve) => setTimeout(resolve, 100));
    const said = document.getElementById("publish-status");
    publish.disabled = true;
    said.textContent = "Publishing\u2026 this can take a few minutes the first time. " +
      "Keep this page open.";
    try {
      const answer = await fetch("/publish", {method: "POST", body: fields()});
      const text = await answer.text();
      if (answer.status !== 200) { said.textContent = ""; stop(text); return; }
      const reply = JSON.parse(text);
      dirty = false;
      adopt(reply);
      document.getElementById("failure").innerHTML = reply.failure || "";
      said.textContent = reply.published
        ? "Published. Your site shows it within a few minutes." : "";
    } catch (error) {
      said.textContent = ""; stop("");
    } finally {
      publish.disabled = false;
    }
  });

  const button = document.querySelector("button[data-editor=address]");
  if (button) {
    button.addEventListener("click", async () => {
      const data = new URLSearchParams();
      data.set("slug", state.slug); data.set("base", state.base);
      data.set("address", document.querySelector("input[name=address]").value);
      const answer = await fetch("/address", {method: "POST", body: data});
      const text = await answer.text();
      if (answer.status !== 200) { stop(text); return; }
      const reply = JSON.parse(text);
      document.getElementById("address-hint").textContent = reply.hint || "";
      if (!reply.hint) adopt(reply);
    });
  }
})();
"""
