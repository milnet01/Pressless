<!-- ants-spec-format: 1 -->
# PRESS-0219 — A searchable manual inside the app

**Status:** spec draft (2026-11-11). No `review-contract` gate: nothing
binds to the manual's format yet, and it is cheap to change until a
translation exists (`~/.claude/CLAUDE.md` rule 14).
**Kind:** feature.
**Source:** ROADMAP PRESS-0219 (user decision 2026-10-02, PRESS-0198;
widened by user request 2026-10-03; settled by the user 2026-11-11).

**Pairs with:** PRESS-0241, which adds a second language's manual file.

Layman: a Help link on every Pressless screen opens a manual, with
pictures, short captioned videos and a search box, that works offline.

## 1. Goal

After this ships, every Pressless screen has a Help link in its top bar.
It opens `/manual`: one page listing every task Pressless can do, each
with numbered steps, pictures and, where a picture cannot show the steps,
a short silent video with captions. A search box above the tasks hides
every task whose words do not match as the writer types. The manual's
words, pictures and videos ship inside the artefact, so it matches the
installed version and needs no internet.

## 2. Problem

1. **Pressless has no manual.** Help today is per-screen: the cheat sheet
   (`cheatsheet.py`), Setup's "What's happening" link (PRESS-0340), and
   the failure sentences in `face.SENTENCES`. A newcomer who does not know
   which screen a task lives on has nowhere to look.
2. **The artefact carries no data files.** Everything a screen shows is a
   string in Python: `scripts/freeze_flags.py::pyinstaller_args` passes
   no `--add-data`, and nothing under `src/pressless` reads a file beside
   itself. Pictures and videos cannot be strings.
3. **No screen module may hold English** (PRESS-0242 INV-3, enforced by
   `tests/test_words.py::test_no_screen_writes_english`), and a manual is
   mostly English. Putting it in `words.ENGLISH` one key per paragraph
   would make the table unreadable to a translator.

## 3. Scope decisions (agreed with the user)

1. **Opens from inside the app, shows rather than tells, and can be
   searched.** The user, 2026-10-03.
2. **Pictures and videos ship inside the app**, not online. Each video is
   short and silent, with captions. The user, 2026-11-11.
3. **Written for low vision**: every picture has alt text, every video
   has captions, and the page follows the text-size setting (PRESS-0338).
   The user, 2026-11-11.
4. **English now, translatable later**: the words sit in one file apart
   from the pictures. The user, 2026-11-11.
5. **It is the last 1.0.0 item**, so its pictures are made once. The
   user, 2026-11-11, moving PRESS-0204, PRESS-0205 and PRESS-0241 to 1.2.0.
6. **Help sits in the bar, after Files and before More.** *(decided
   here)* PRESS-0343 put the rest under More to keep the bar short; Help
   is the one link a lost newcomer looks for, and More hides it.
7. **One page, filtered in the browser.** *(decided here)* Every task is
   on `/manual`; the search box hides tasks rather than asking the Face.
8. **A small fixed text format, not Markdown.** *(decided here)* § 4.2
   lists every construct; anything else is a plain paragraph.
9. **Videos are WebM**, which Chrome, Edge and Firefox play, and
   `face._FILE_TYPES` already serves. *(decided here)*

Every "(decided here)" is open to the maintainer to overturn.

## 4. Design

### 4.1 Files

```
src/pressless/manual.py            # new: reads the text, serves /manual
src/pressless/manual_files/
    en.txt                         # the manual's words, English
    media/<name>.png               # pictures, shared by every language
    media/<name>.webm              # videos, shared by every language
    media/<name>.en.vtt            # captions, one file per language
```

The folder is `manual_files`, not `manual`, so it cannot shadow the
module on import. `manual.py` finds it with
`importlib.resources.files("pressless") / "manual_files"`, which reads
the source tree when run from source and the bundle when frozen.

**Translating is adding files**: `<lang>.txt` with the same task names,
and `<name>.<lang>.vtt` per video. Which language is in use is
PRESS-0241's; this item reads `en.txt` and `.en.vtt` only.

### 4.2 The text format

One file, read top to bottom. A line's start decides what it is:

```
== <task-name> | <Title>      a task: a new <section id="task-name">
                              with <h2>Title</h2>; <task-name> is
                              lowercase letters, digits and hyphens
1. <words>                    a numbered step (any number)
picture <name>.png | <alt>    an <img loading="lazy"> with that alt text
video <name>.webm | <label>   a <video controls preload="none"> with
                              aria-label, and a captions <track> for
                              <name>.en.vtt, marked default
(blank line)                  ends a paragraph
anything else                 paragraph words
```

**Every word is HTML-escaped**; the format has no way to write markup.
Lines before the first `==` are the manual's opening paragraph. A line
that looks like a construct but is malformed (a `picture` with no `|`) is
a paragraph, and INV-1's test fails on it.

### 4.3 The page

`manual.register(face)` adds `GET /manual`, and
`face.add_files("/manual/media/", ...)` for the media folder. The existing
`face._served_file` path guard and `face.FILES_POLICY` apply unchanged.
`face._FILE_TYPES` gains `".vtt": "text/vtt; charset=utf-8"`.

```
<h1>             words key manual.title
<label> and <input type="search">     words key manual.search, on screen
<p role="status">                       empty until something is typed
<section id=…> per task, in file order
```

The page script, on each input: splits the box into words, lowercased;
shows a task when every word appears in its title, steps, paragraphs or
alt text, lowercased; and sets the status line to `script.manual.found`
(with the count) or `script.manual.none`. An empty box shows every task
and empties the status. The status line uses `role="status"`, so a
screen reader reads the count without moving focus.
Source: <https://wcag.dock.codes/documentation/wcag413> (WCAG 4.1.3).

### 4.4 The Help link

`face._page` adds `<a href="/manual">{say("face.help")}</a>` after the
Files link and before `<details class="more">`.

### 4.5 Packaging

`scripts/freeze_flags.py` gains `DATA: list[tuple[Path, str]]`, the
"data pairs" PRESS-0022 § 4.4 already names, holding
`(ROOT / "src" / "pressless" / "manual_files", "pressless/manual_files")`.
The source is absolute because PyInstaller reads a relative one from
`--specpath`, the work folder.
`pyinstaller_args` passes each as `--add-data SRC:DEST`, the form
PyInstaller 6 takes on every system (pinned at 6.22.3 in
`packaging/release-requirements.txt`).

### 4.6 Making the pictures and videos

With the `record-demo` skill, on a private display, from a seeded
throwaway site, so no real site or person appears. Pictures are PNG. Videos are WebM, silent, with a `.vtt`
file giving the captions as timed text.
Source: <https://www.htmhell.dev/tips/the-track-element>.

### 4.7 Building it

1. `manual.py`, the format, the page, the Help link, the `.vtt` type, and
   `en.txt` holding one task with one picture and one video → INV-1,
   INV-2, INV-3, INV-4, INV-5 and INV-6 pass.
2. Packaging → INV-7's test passes; a Linux build opens `/manual` offline
   and shows the picture and the captioned video.
3. Every task written and recorded → the by-hand check in § 7.

## 5. Invariants

- **INV-1** — Every picture and video `en.txt` names is in
  `manual_files/media`, every file there is named by `en.txt` or is a
  named video's caption file, and no line is a malformed construct.
  *Test:* `tests/test_manual.py::test_text_and_media_agree`.
  *Breaks when:* a picture is renamed and `en.txt` is not, or a file is
  left behind after its task is cut.

- **INV-2** — Every picture has alt text and every video has a caption
  file for `en`.
  *Test:* `tests/test_manual.py::test_every_picture_and_video_is_described`.
  *Breaks when:* `picture x.png |` with nothing after the bar, or
  `x.webm` with no `x.en.vtt`.

- **INV-3** — No text in a manual file reaches the page as markup.
  *Test:* `tests/test_manual.py::test_words_are_escaped` — a fixture file
  whose paragraph, step, title and alt text each hold `<b>x</b>` renders
  each as `&lt;b&gt;x&lt;/b&gt;`.
  *Breaks when:* any construct writes its words unescaped.

- **INV-4** — Every page the Face wraps carries the Help link, before
  More.
  *Test:* `tests/test_manual.py::test_every_page_has_help` — renders
  `face._page` and finds `href="/manual"` before `class="more"`.
  *Breaks when:* the bar is rebuilt without it, or it moves under More.

- **INV-5** — The manual names nothing outside the Face: no `src` or
  `href` on `/manual` starts with a scheme or `//`.
  *Test:* `tests/test_manual.py::test_manual_works_offline`.
  *Breaks when:* a picture or video is named by an online address.

- **INV-6** — The media folder stays small: under 25 MB in all, and no
  video over 3 MB.
  *Test:* `tests/test_manual.py::test_media_stays_small`, printing both
  sizes.
  *Breaks when:* a long or high-resolution video is added.

- **INV-7** — The freeze bundles the manual.
  *Test:* `tests/test_manual.py::test_freeze_bundles_the_manual` —
  `pyinstaller_args` holds `--add-data` with the `manual_files` pair, and
  that source folder exists.
  *Breaks when:* `DATA` loses the pair, or the folder is renamed.

- **INV-8** — A task shows exactly when every typed word is in its words,
  ignoring case, and the status line gives the count.
  *Test:* a case in `scripts/by-hand-browser-checks.py`, run on the
  Windows box by `scripts/windows-gate.sh <host> --browsers`: type two
  words only one task holds together, then one word several hold, then
  nothing.
  *Breaks when:* the script matches any word instead of every word, or
  compares without lowering case.

PRESS-0242 INV-3 already covers `manual.py`: it imports `words`, so
`test_no_screen_writes_english` walks it. Its words go in
`words.ENGLISH` under `manual.` and `script.manual.`.

## 6. Failure modes

- **`en.txt` is missing or unreadable** (a broken bundle): `/manual`
  shows `face.sentence_for`'s failure page with a new sentence saying the
  manual could not be found, and the log notes it. No other screen is
  affected; the Help link still shows.
- **A media file is missing**: the Face answers 404; the browser shows
  the picture's alt text, or an empty video frame whose captions are
  also gone. INV-1 stops this before a release.
- **Scripts do not run**: every task shows and the search box does
  nothing. The Face needs scripts everywhere, so this is not new.
- **A picture is stale** after a screen changes: nothing catches it.
  § 9 and § 10 say so.

## 7. Tests

`tests/test_manual.py`, new, locks INV-1, INV-2, INV-3, INV-4, INV-5,
INV-6 and INV-7, using a fixture
manual folder for INV-3 and the real `manual_files` for the rest. Each is
seen failing before its code exists. INV-8 is a browser case, because the
push gate drives no browser; `windows-gate.sh --browsers` runs it on
request in Chrome, Edge and Firefox.

**By hand, once every task is written:** build the Linux artefact,
disconnect from the internet, open `/manual` from the Help link on three
screens, search for a task, play one video with captions on, and set the
text size to its largest. Then the same on the Windows box. Read each
picture and video for anything naming a real site or person.

## 8. Alternatives considered (and rejected)

- **The manual online.** Rejected by the user: it would need internet and
  could describe another version.
- **The manual's words in `words.ENGLISH`.** A key per paragraph splits a
  task across hundreds of entries, and a translator loses its order.
- **Markdown through a library.** A new dependency for a format that
  needs five constructs; and Markdown lets raw HTML through, which INV-3
  would then have to strip.
- **A search address the script asks on each key.** A round trip per key
  for text already on the page.
- **One file per task.** More files to keep in step across languages;
  one file reads top to bottom like the manual it is.
- **Help under More.** The newcomer who needs it least knows where More
  is.

## 9. Out of scope

- Help opening at the task for the current screen — deferred; not yet
  queued.
- Keeping pictures current when a screen changes after 1.0.0 — deferred;
  not yet queued.
- Choosing the manual's language — tracked by PRESS-0241.
- Sound in videos — excluded by scope decision 2.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_manual.py::test_text_and_media_agree` |
| INV-2 | `tests/test_manual.py::test_every_picture_and_video_is_described` |
| INV-3 | `tests/test_manual.py::test_words_are_escaped` |
| INV-4 | `tests/test_manual.py::test_every_page_has_help` |
| INV-5 | `tests/test_manual.py::test_manual_works_offline` |
| INV-6 | `tests/test_manual.py::test_media_stays_small` |
| INV-7 | **Partial:** `tests/test_manual.py::test_freeze_bundles_the_manual` checks the flag; only a built artefact proves the files arrive (§ 7) |
| INV-8 | **Partial:** `scripts/by-hand-browser-checks.py`, run on request by `windows-gate.sh --browsers`, not by the push gate |
| Every task Pressless offers has a manual entry | **nothing** — a by-hand read against the roadmap's shipped items |
| No picture or video shows a real site or person | **nothing** — the leak sweep reads text only; the § 7 by-hand read |
| Pictures match the current screens | **nothing** — see § 9 |

## 11. Cross-doc impact

- `CHANGELOG.md`: the manual and the Help link.
- `README.md`: point a newcomer at Help.
- `docs/specs/PRESS-0022-packaging.md`: none; § 4.4 already names data
  pairs.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0219-in-app-manual-loop-log.md`.

## 13. Resource cost

The artefact grows by the media folder, capped by INV-6. The page loads
pictures lazily and videos only on play, so opening `/manual` fetches the
text and the pictures in view.
