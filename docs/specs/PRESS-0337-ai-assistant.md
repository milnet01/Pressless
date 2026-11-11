<!-- ants-spec-format: 1 -->
# PRESS-0337 — Let an AI assistant drive Pressless

**Status:** accepted (2026-11-11). One review loop, by the user's one-round budget; its fixes are read by no lane. Built 2026-11-11, with the build's corrections folded in (`impl` row); § 7's by-hand checks are owed before release.
**Kind:** feature.
**Source:** ROADMAP PRESS-0337 (user request, 2026-11-03).

Layman: you can ask an AI app on your computer to write, edit or publish on
your site; nothing goes live or is thrown away until you press yes in
Pressless.

## 1. Goal

An AI app on the writer's computer can read and change the open site through
Pressless: entries, pages, photographs and files, the look, and Insights'
figures. It talks to the running Pressless through the Model Context Protocol
(MCP), the protocol AI apps use to call tools. Whatever would publish, undo a
publish or put something in the bin waits until the writer presses yes in
Pressless's own window. No tool can reach a key.

## 2. Problem

Pressless has one way in, the Face, and it admits one browser. A separate
process cannot reach it:

1. The Face listens on 127.0.0.1 at a port the system picks
   (`face.Face.__init__` binds port 0), and nothing writes the port down.
2. It admits a request only with the session cookie, which the one-use link
   sets (`face._Handler._dispatch`). The link secret and the cookie live in
   the `Face` object alone.
3. A second Pressless refuses to start while one runs: `__main__._hold`
   locks `pressless.lock` in Pressless's own folder, and `_serve` answers
   `main.already`.
4. Much of the logic an assistant would call sits inside a route handler that
   takes a `Request` and answers HTML: `editor._new`, `editor._address`,
   `editor._throw`, `editor._discard`, `page_editor._new`,
   `page_editor._reshaped`, `files_screen._remove`, `look_screen._save`.

And the design's rules bind any new way in. Only the Face knows the order of
write, build and publish (`docs/design.md` § What may depend on what, rule 1),
and only the Face reaches Credentials (rule 10).

## 3. Scope decisions (agreed with the user)

All by the user on 2026-11-10 and 2026-11-11, recorded on PRESS-0337.

- **An MCP server, built as one set of actions a command line could reuse
  later.** No command line now.
- **The writer approves in Pressless's own window**, never in the AI app.
- **Pressless must be open.** With it closed, every tool answers that it
  should be opened first.
- **The first version covers entries, pages, photographs and files, the
  look, and Insights.** The last two went beyond the recommendation.
- **Desktop AI apps only**: an app that starts a local program. A chat that
  runs only in a browser cannot reach one, and serving it would need a server
  of Pressless's own, which `docs/design.md` § The stack rules out.

Decided here, each in § 8:

- **Off until the writer switches it on.**
- **No MCP library.** The protocol subset is written here, on the standard
  library.
- **The assistant never touches code.** No script, style or code section of a
  page, and no hand-written stylesheet.

## 4. Design

### 4.1 Three pieces

```
AI app ──stdio──▶ bridge ──HTTP 127.0.0.1──▶ door (inside the Face) ──▶ the parts
                  pressless --assistant      POST /assistant
```

| Piece | Module | Knows |
|---|---|---|
| **Catalogue** | `assistant_tools.py` | Every tool's name, description and input schema, as data. Pure: no disk, no network. |
| **Door** | `assistant.py` | The tools' work. Part of the Face, so rules 1 and 10 stay true: it calls the same plain functions the screens call, under the same locks. |
| **Bridge** | `bridge.py` | The protocol and the door file. Nothing about the site. |

The bridge is the packaged program started as `pressless --assistant` by the
AI app, so the writer installs nothing more. It is a second process, which is
why it holds no lock and no state.

### 4.2 Switching it on

A line on the Face's list, **AI helper**, opens `/assistant/setup`. It holds:

- a switch, kept in `assistant.json` in Pressless's own folder as
  `{"on": true|false}`. Absent means off. Machine-wide, like the theme,
  because it is about this computer's AI apps rather than the site;
- the program path and the argument `--assistant`, with a copy button, and
  the same as an `mcpServers` JSON block. Each app's exact steps are words in
  the words table, checked by hand per app before release (§ 7).

While the switch is on and a Face serves, the **door file**
`assistant-door.json` sits in Pressless's own folder:

```json
{"port": 41234, "token": "<secrets.token_urlsafe(32)>", "version": "0.15.0"}
```

Written when the Face starts or the switch turns on, through
`safe_write.write_whole`, with owner-only permissions where the system has them.
Removed when the Face stops or the switch turns off. A new token every
time. A restart, an update or a switch of site (PRESS-0223) writes a new
file, and the bridge reads the file on every call, so it follows.

**What the token protects.** It keeps out web pages and other users' programs,
which can reach 127.0.0.1 but not the writer's files. It does not keep out
the writer's own programs. Those can already write the Store directly, so the
door gives them nothing more except the right to ask, and asking still waits
for the writer.

### 4.3 The door

`POST /assistant`, registered through a new `Face.add_door(path, page, admits)`,
where `admits` takes the `Authorization` header. The
Face's `_dispatch` answers it before its cookie check, and only where all of
these hold. Any failure gets the same 403 as any refused request, and nothing
runs:

- `Host` is the Face's own, as for every request;
- **no `Origin` header**. Browsers send one on a cross-site POST; the bridge
  never does;
- `Authorization: Bearer <token>` matches the door file's token, compared by
  `face._is_secret`;
- the switch is on.

Request and reply bodies are JSON:

```json
{"tool": "save_entry", "arguments": {...}, "version": "0.15.0"}
{"ok": true, "result": {...}}
{"ok": false, "said": "<a sentence from the words table>"}
```

A `version` other than the running program's is refused with
`assistant.restart_app`: the AI app's bridge is from before an update.

**One call at a time.** The door takes its own `threading.Lock` for the whole
call, and each tool takes `editor.LOCK` where its screen does. Calls queue;
none run in parallel.

**What a call writes to the log**: one line, `assistant: <tool> <ok|refused
<FailureType>>`. Never an argument, a result or a path (`docs/design.md`
§ Logging).

**Failures** become `said`: `face.sentence_for`'s three parts, joined as
plain text, with `secret=` naming the key in words where the screens name it.
The log gets `face.details_for`, as `Face.fail` writes it. Neither adds a
defence: a failure is free of a credential because the part that raised it
left it out (`docs/design.md` § Logging), and the door relies on that. A
protocol-level mistake (an unknown tool, a missing argument) is refused before
anything runs.

### 4.4 The bridge

`__main__.main` gains a third route, `["--assistant"]`, taken before the
report is printed: the report goes to stdout, and stdout belongs to the
protocol. The route calls `bridge.run(sys.stdin, sys.stdout)` and exits 0 at
end of input.

The protocol is a subset of MCP over stdio. Source:
<https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio>,
`.../basic/versioning`, `.../server/discover`, `.../server/tools`.

- **Framing.** One JSON-RPC message per line, UTF-8, no embedded newline.
  Nothing else on stdout. Diagnostics go to stderr.
- **Versions.** Modern: `2026-07-28`, read from each request's
  `_meta["io.modelcontextprotocol/protocolVersion"]`. Legacy: `2025-11-25`
  and `2025-06-18`, chosen by an `initialize` request. An unsupported modern
  version gets `UnsupportedProtocolVersionError` (-32022) listing the
  supported ones.
- **Methods.** `server/discover`, `initialize`, `notifications/initialized`
  (ignored), `ping` (legacy, answers `{}`), `tools/list`, `tools/call`,
  `notifications/cancelled` (ignored: a call already at the door finishes).
  Anything else is -32601. A request naming no version in `_meta` is
  legacy.
- **Modern results** carry `resultType: "complete"`. `server/discover`
  answers `supportedVersions`, `capabilities` and the server's name under
  `_meta["io.modelcontextprotocol/serverInfo"]`.
- **`tools/list`** answers from the catalogue the bridge imports, never from
  the door. So the list is the same whether or not Pressless is open, and the
  AI app learns the tools even when it starts first. One page, no cursor,
  deterministic order, `ttlMs` and `cacheScope: "public"` on modern
  requests and on `server/discover`.
- **`tools/call`** checks the name against the catalogue (-32602 if
  unknown), reads the door file, and posts to the door with a 300-second
  timeout. A missing file, a refused connection or a 403 answers a tool
  error, `isError: true`, with `assistant.open_pressless`. A door reply
  becomes `content: [{type: "text", text: <JSON>}]` and `structuredContent`
  for `ok`; `said` as text with `isError: true` otherwise.

The bridge imports `assistant_tools`, `paths` and `words` and nothing else
from Pressless.

### 4.5 The catalogue

Every tool acts on the site the Face has open. Names are stable once
released. A later release may add a tool or an optional argument, never
rename or remove one, nor make an argument required.

Every read that a later write must name returns a `version`, the digest the
screens already send back as `base` (`editor.digest`, `look.digest`). A
write with a stale `version` is refused with `ChangedElsewhere`'s sentence,
as the screens refuse it. So the assistant cannot overwrite what the writer
typed meanwhile.

**Reads** (a read returning a `version` takes `editor.LOCK`, as `editor._edit`
does, so the version matches what it returned):

| Tool | Arguments | Returns |
|---|---|---|
| `site_overview` | — | site name, its address, journal on or off, entry and page counts, whether a press runs (`pressing.state`), the waiting request if any |
| `writing_guide` | — | the marks cheat sheet as text (`cheatsheet._table`'s source rows) |
| `list_entries` | — | each entry: address, title, date, `draft`, `has_changes` (a working copy exists) |
| `read_entry` | `address` | title, date, categories, tags, body in marks, `draft`, `version`. A published entry with a working copy returns the working copy, as `editor._edit` does |
| `list_pages` | — | each page and part (`header`, `footer`, `navigation`): name, `changed` (a waiting copy exists) |
| `read_page` | `name` | each section by path, kind and fields, or, for `navigation`, its links; `version`. A script, style or code section, and words holding a Builder placeholder, appear with their kind and `"locked": true`, and no code. `header`, `footer` and `navigation` name the parts |
| `list_files` | — | each added file and photograph: name, and the pages naming it (`builder.files_named`) |
| `read_look` | — | `look.Choices` as JSON, `version` |
| `read_insights` | `days`, one of `dashboard.WINDOWS`' spans | `insights.Report`'s figures as JSON. `NotConfigured` answers its sentence |
| `request_status` | `request` | `waiting`, `refused`, `expired`, `running`, `done`, `failed` or `unknown`, with the press's outcome sentence |

**Writes** (under `editor.LOCK`; nothing goes live):

| Tool | Arguments | Does |
|---|---|---|
| `new_entry` | `title`, `template`? | `editor.new_draft` (§ 4.7); returns `address`, `version` |
| `save_entry` | `address`, `version`, any of `title`, `body`, `categories`, `tags` | `editor.save` in the marks view (`view` other than `"visual"`); a published entry gets its working copy, as on screen |
| `change_entry_address` | `address`, `version`, `to` | `editor.change_address` (§ 4.7) |
| `new_page` | `name` | `page_editor.new_page` (§ 4.7): a waiting copy only |
| `save_page` | `name`, `version`, `sections` or `links` | `page_editor._write` with a `view` other than `"code"`; a top-level section not kept is removed; refused if it adds, changes, moves or removes a locked section (§ 4.8) |
| `add_photograph` | `filename`, `data` (base64) | `photographs.add`; returns its name and `builder.web_photograph` address |
| `add_file` | `filename`, `data` (base64) | `files.add`, with its own size and kind checks |
| `save_look` | `version`, `choices` | `look_screen.save` (§ 4.7), with the route and hand-written CSS the Look screen would post unchanged, so neither changes |

**Asks** (each makes a request, § 4.6, and changes nothing):

| Tool | Arguments | The press it asks for |
|---|---|---|
| `publish` | `entry` or `page`, or neither for the whole site | `publishing.press_entry`, `page_editor.press_page` or `publishing.press_site` (§ 4.7). An entry or page with nothing waiting publishes the site as it stands |
| `undo_last_publish` | — | `undo.press_undo` (§ 4.7) |
| `remove_entry` | `address`, `version` | `editor.throw` (§ 4.7) |
| `discard_changes` | `entry` or `page`, `version` | `editor.discard` or `page_editor.discard` (§ 4.7) |
| `remove_page` | `name` | `page_editor.reshape(renaming=False)` |
| `rename_page` | `name`, `to` | `page_editor.reshape(renaming=True)` |
| `remove_file` | `name` | `files_screen.remove` (§ 4.7) |

An ask answers `{"request": "<id>", "status": "waiting"}` at once. Calls do
not wait for the writer: AI apps time calls out, and the writer may be away.
The assistant asks `request_status` later.

### 4.6 Requests and the writer's yes

The door keeps **at most one waiting request**, in memory. A second ask while
one waits is refused with `assistant.one_waiting`. Memory is right: losing it
in a crash costs one question asked again, and nothing of the writer's is in
it. That is the same reason `docs/design.md` § State allows Updating's
in-memory offer.

A request holds its id (`secrets.token_urlsafe(8)`), the press it asks for,
the time, the plan, and the **Store's mark**. The plan is what the box lists:

| Ask | Plan |
|---|---|
| `publish` | `publishing.plan`'s answer: the pages it writes, and how many other files it adds and removes |
| `undo_last_publish` | `assistant.box.undo`: the site goes back to how it was before the last publish |
| `remove_page`, `rename_page` | the page's name, and `assistant.box.remove` or `assistant.box.rename` with the new name; both go live at once, as on screen |
| `remove_entry`, `discard_changes`, `remove_file` | each entry, page or file that goes to the bin, by name |

`GET /assistant/waiting` answers `_plan`'s JSON shape, `pages`, `added` and
`removed`, plus `lines`: the plan's other sentences, as text. PRESS-0345's
`presslessPlan` gains `lines`. No ask runs a build to plan except `publish`;
the box for the others, deferred on PRESS-0345, stays a sentence here too.
The mark is a digest of the relative path, size and modification time of
every file under the site folder's Store, and of `settings.json`
(`settings.path_for`), since the build reads both
(`store.mark(folder, settings.path_for(folder))`, new).

**The box.** Every Face page asks `GET /assistant/waiting` every two seconds
while the switch is on. A waiting request opens PRESS-0345's box, headed
`assistant.box.title`, listing the plan, with **Yes, do it** and **Not yet**.
Everything in the box is Pressless's own words or page titles shown as text. A
request carries no message from the assistant, so the box cannot be made to
say "this is safe".

**Yes** is `POST /assistant/answer` with `yes=1`, behind the Face's cookie
and Origin checks like every screen button. The door then:

1. takes the press record (`pressing.run`) for an ask that publishes or
   undoes, as `PUBLISH` or `UNDO` like its screen, then `editor.LOCK`.
   `remove_entry`, `discard_changes` and `remove_file` take `editor.LOCK`
   alone, as their screens do;
2. compares `store.mark(folder)` with the request's. **A difference means the
   site changed since the box was drawn**, so the press does not run. The
   request is re-planned and stays waiting, and the box redraws with the new
   plan;
3. runs the press and records its outcome on the request.

**Not yet** refuses the request. A request waiting for 30 minutes expires.
Neither changes anything.

### 4.7 Logic moved out of the handlers

Each handler below is split into a plain function and the handler that calls
it, so the door and the screen run the same code (rule 1). Each plain function
takes `folder` and plain arguments, raises what the handler caught, and never
takes a lock; its caller holds `editor.LOCK`. Each press function also takes
`transport`, as the press it came from did. `AddressRefused` and
`NameRefused` carry the hint as their sentence.

| New function | Taken from | Signature |
|---|---|---|
| `editor.new_draft` | `editor._new` | `(folder, title, template) -> store.Entry` |
| `editor.change_address` | `editor._address` | `(folder, slug, base, address, *, draft) -> str` (new digest), raising `AddressRefused(hint)` where `_address_refused` returns a hint |
| `editor.throw` | `editor._throw` | `(folder, slug, base, *, draft) -> None` |
| `editor.discard` | `editor._discard` | `(folder, slug, base) -> str` (the published address) |
| `page_editor.new_page` | `page_editor._new` | `(folder, named) -> str`, raising `NameRefused(hint)` |
| `page_editor.discard` | `page_editor._discard` | `(folder, kind, name, base) -> None` |
| `page_editor.reshape` | `page_editor._reshaped` | `(folder, name, to, *, renaming, capture, notices) -> Published` |
| `page_editor.press_page` | `page_editor._pressed` | `(folder, form, *, capture, notices) -> Published` |
| `publishing.press_entry` | `publishing._pressed` | `(folder, form, *, capture, notices) -> tuple[store.Entry, Published]` |
| `files_screen.remove` | `files_screen._remove` | `(folder, name) -> None`, raising `FileInUse` |
| `look_screen.save` | `look_screen._save` | `(folder, form) -> None`: the route check, the base check and the copy to the bin, then `look.save` |
| `publishing.plan` | `publishing._plan` | `(folder, *, entry, page) -> Preview` |
| `publishing.press_site` | `page_editor._publish_or_put_back`'s call | `(folder, *, capture, notices) -> Published`: `publish(entry=None)` |
| `undo.press_undo` | `undo._pressed` | `(folder, *, capture, notices) -> Undone` |
| `dashboard.figures` | `dashboard._show` | `(folder, days) -> insights.Report`, the Google token fetched inside |

`publishing.preview`, `publishing.publish` and `undo.undo` take the key as an
argument, so the door calls none of them directly. Every function above that
needs the key fetches it through `github_setup.token`, inside the function, so
it never reaches the door's frame.

The door builds the form `press_entry` and `press_page` take from the stored
entry or waiting copy, with its digest as `base`, so the press saves nothing
new.

### 4.8 What the assistant may not touch

- **A page's script, style or code section** (`blocks.SCRIPT`,
  `blocks.STYLE`, `blocks.CODE`). `save_page` compares the posted sections
  with the stored ones and refuses `assistant.locked_section` if any locked
  section was added, changed, moved or removed. Moved means the locked
  sections, read in order, are no longer the same list; an unlocked section
  added or removed around them moves none. The page's code view is not
  offered at all.
- **The look's hand-written CSS** (`look.read_extra`) and the "own
  stylesheet" route of `look_screen`.
- **Settings, setup, sign-ins, sites, updates, backups, the takeover and the
  import.** No tool reaches them.

Entries need no rule: Marks escapes everything it writes
(`marks._escape_text`, `marks._escape_attr`).

### 4.9 Updating on Windows

The Windows update helper waits up to 60 seconds for every process whose
image is inside the program folder (`installer.WINDOWS_SCRIPT`), then gives
up. A bridge the AI app keeps running is such a process, so it would stop
every update. On each pass of its wait, the helper ends every such process
whose command line ends in `--assistant`, so a bridge started during the wait
is ended too. It ends them through `Invoke-CimMethod Terminate`, since
PRESS-0023 INV-12 bars `-Id` from the script. A bridge holds no state and no lock, so ending it loses
at most a call in flight. Its AI app sees the call fail and starts a new bridge
when next needed.

On Linux the AppImage is replaced by `os.replace` with the bridge running, as
with Pressless itself, and the bridge's next call meets the version check
(§ 4.3).

## 5. Invariants

Every test below is new; none can run before the code exists.

- **INV-1** — No tool result, `said` sentence or log line carries a
  credential. *Test:* `tests/test_assistant.py::test_no_tool_returns_a_key`
  runs every catalogue tool against a site whose fake keyring answers a
  sentinel key, including failing presses whose transport's error replies
  quote it. It asserts the sentinel appears in no reply and no log line.
  *Breaks when:* a raised failure's own words quote the key, or a tool
  returns a settings object or transport that holds one.

- **INV-2** — The door does nothing without its token and switch, or with an
  `Origin` header or a foreign `Host`. *Test:*
  `tests/test_assistant.py::test_the_door_refuses` posts a `site_overview`
  call with no token, a wrong token, a right token plus `Origin`, a foreign
  `Host`, and the switch off. Each gets 403 and writes no log line.
  *Breaks when:* `add_door` routes are answered after the cookie check is
  skipped but before the token check.

- **INV-3** — The token opens only the door, and the cookie never opens it.
  *Test:* `tests/test_assistant.py::test_token_and_cookie_stay_apart` sends
  the token to `/`, `/assistant/answer` and `/publish`, which are refused,
  and the cookie without the token to `/assistant`, which is refused.
  *Breaks when:* the door's check is written as "token or cookie".

- **INV-4** — No ask changes the Store or GitHub before the writer's yes.
  *Test:* `tests/test_assistant.py::test_asks_change_nothing` calls every ask
  tool with a recording transport. The Store's file tree is byte-identical
  before and after, and the transport recorded no write.
  *Breaks when:* an ask calls its press function instead of recording it.

- **INV-5** — A yes runs nothing when the Store changed after the request was
  made. *Test:* `tests/test_assistant.py::test_yes_after_a_change_replans`
  makes a `publish` request, then saves the entry through the screen's
  `/save`, then answers yes. The transport records no write and the request is
  still waiting with a new plan.
  *Breaks when:* the yes path skips the mark comparison, or the mark leaves
  out a file the build reads.

- **INV-6** — The assistant cannot add, change, move or remove a script,
  style or code section. *Test:*
  `tests/test_assistant.py::test_locked_sections_hold` saves a page holding
  one of each through `save_page`, once per breach, and asserts
  `assistant.locked_section` and an unchanged waiting copy. One more case
  changes only an unlocked section and must succeed.
  *Breaks when:* the comparison ignores order, so swapping two locked
  sections passes.

- **INV-7** — With `--assistant`, stdout carries only protocol messages.
  *Test:* `tests/test_bridge.py::test_stdout_is_protocol_only` runs `main
  (["--assistant"])` with a `server/discover`, a `tools/list` and a
  `tools/call` on stdin and no door file. Every stdout line parses as a
  JSON-RPC response, and `pressless: ok` is absent.
  *Breaks when:* the report is printed before the route is chosen.

- **INV-8** — The bridge imports only `assistant_tools`, `paths` and `words`
  from Pressless. *Test:* `tests/test_bridge.py::test_bridge_imports`, an AST
  walk like PRESS-0022 INV-1's. *Breaks when:* the bridge imports
  `credentials`, `store` or `settings` for convenience.

- **INV-9** — A fresh install has the door shut. *Test:*
  `tests/test_assistant.py::test_off_by_default` serves a Face over an empty
  own folder. No door file exists and `/assistant` refuses with the right
  token shape. *Breaks when:* absent `assistant.json` is read as on.

- **INV-10** — At most one call runs and at most one request waits. *Test:*
  `tests/test_assistant.py::test_one_at_a_time` holds the door lock from a
  test thread and posts a call, which completes only after release. Two asks
  in a row get `assistant.one_waiting` on the second. *Breaks when:* the
  door lock is per tool.

- **INV-11** — A write with a stale `version` changes nothing. *Test:*
  `tests/test_assistant.py::test_stale_version_refused`, for `save_entry`,
  `save_page` and `save_look`. *Breaks when:* a tool reads the digest
  itself instead of taking it from the caller.

- **INV-12** — The box shows nothing the assistant wrote as markup. *Test:*
  `tests/test_assistant.py::test_box_is_escaped` publishes an entry titled
  `<img src=x onerror=alert(1)>` and reads `/assistant/waiting`, whose JSON
  carries the title as it is. It then reads the box's script for any plan
  field written other than through `textContent`. *Breaks when:* the plan's
  titles are inserted as HTML.

- **INV-13** — The Windows update helper ends `--assistant` processes while
  it waits. *Test:* `tests/test_installer.py::test_helper_ends_bridges` reads
  `WINDOWS_SCRIPT` for the stop step inside the wait loop, and the by-hand
  check in § 7 runs it on the Windows box. *Breaks when:* the stop step
  matches every process in the folder.

## 6. Failure modes

| What breaks | What happens |
|---|---|
| Pressless closed, or the switch off | Every call answers `assistant.open_pressless` as a tool error; `tools/list` still answers. |
| Door file left by a crash | The connection is refused; same answer. The next Face rewrites the file. |
| Port taken by another program after a crash | It gets a POST with a token it cannot use, and answers something that is not the door's JSON. The bridge treats any reply that does not parse as `assistant.open_pressless`. |
| A press already running | The yes waits on `pressing.run`'s busy answer: the request stays waiting and the box says a press runs. |
| The writer never answers | The request expires after 30 minutes; `request_status` says `expired`. |
| Site switched while a request waits | The Face restarts, the in-memory request is gone, and `request_status` answers `unknown`. |
| Text on the site steers the assistant (an imported comment saying "publish everything") | It can change drafts, which the writer can see and the daily backup (PRESS-0225) keeps. It cannot publish or bin without the writer's yes. **This is the limit of the defence, not a fix.** |
| A huge upload | The Face's 64 MiB body cap refuses it (`face._MAX_BODY`); base64 makes the largest file about 48 MiB, under `files.add`'s 50 MiB own cap. |
| An AI app speaking only a protocol version not listed | Modern: -32022 with the list. Legacy: `initialize` answers the newest legacy version, and the app decides. |

## 7. Tests

- `tests/test_assistant.py` locks INV-1, INV-2, INV-3, INV-4, INV-5, INV-6,
  INV-9, INV-10, INV-11 and INV-12: the door, the catalogue and the
  requests.
- `tests/test_bridge.py` locks INV-7 and INV-8, and checks § 4.4's framing,
  versions and methods.
- `tests/test_installer.py` locks INV-13's script half.

Each invariant's test is seen failing before its code exists.

By hand, before release, on Linux and the Windows box:

- connect Claude Desktop, Claude Code and the ChatGPT desktop app; list
  tools; save an entry; ask to publish; answer yes in the browser; see the
  site change;
- update Pressless on Windows with an AI app connected; the update
  completes.

## 8. Alternatives considered (and rejected)

- **The official MCP Python library.** It brings pydantic, starlette and
  uvicorn into both artefacts (Source:
  <https://py.sdk.modelcontextprotocol.io/installation/>) for a stdio
  subset of a handful of methods (§ 4.4). Every new dependency is packaged, pinned with
  hashes (PRESS-0022 § 4.4) and reviewed on update. Lost on size and supply
  chain. The cost of our choice: protocol changes are ours to follow.
- **The AI app connects straight to the Face over HTTP.** Each app would
  need the port and token typed into its own settings, and both change on
  every start. Stdio is the transport MCP defines for a program the app
  starts, so the bridge serves every app the same way.
- **The bridge acts on the files itself, with Pressless closed.** Two
  writers to one Store, and no window for the writer's yes. Rejected by the
  user.
- **Approval through the AI app (MCP elicitation, or the app's own "allow?"
  prompt).** Apps let the writer pre-approve, and Claude Desktop is reported
  to drop elicitation requests (Source:
  <https://claudeissues.com/issue/41110-feature-mcp-elicitation-support-in-claude-desktop-app>).
  Rejected by the user.
- **Tools that wait for the yes.** AI apps time a call out, and the writer may
  be away. Lost to the request and `request_status`.
- **On by default.** A door nobody asked for is surface nobody needs; a
  fresh install should not listen for AI apps.
- **The assistant edits code sections.** A prompt-injected assistant could
  put a script on the published site, and the box lists pages, not what
  changed inside them. Lost on that.

## 9. Out of scope

- A command line on the same tools — deferred; not yet queued.
- Browser-only AI chats — would need a server of Pressless's own.
- Showing, in the box, what changed inside each page — deferred; not yet
  queued.
- Restoring something from the bin — no such function exists today;
  `undo_last_publish` is the way back for a published removal.

## 10. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-1 | `tests/test_assistant.py::test_no_tool_returns_a_key` |
| INV-2 | `tests/test_assistant.py::test_the_door_refuses` |
| INV-3 | `tests/test_assistant.py::test_token_and_cookie_stay_apart` |
| INV-4 | `tests/test_assistant.py::test_asks_change_nothing` |
| INV-5 | `tests/test_assistant.py::test_yes_after_a_change_replans` |
| INV-6 | `tests/test_assistant.py::test_locked_sections_hold` |
| INV-7 | `tests/test_bridge.py::test_stdout_is_protocol_only` |
| INV-8 | `tests/test_bridge.py::test_bridge_imports` |
| INV-9 | `tests/test_assistant.py::test_off_by_default` |
| INV-10 | `tests/test_assistant.py::test_one_at_a_time` |
| INV-11 | `tests/test_assistant.py::test_stale_version_refused` |
| INV-12 | `tests/test_assistant.py::test_box_is_escaped` |
| INV-13 | **Partial:** `tests/test_installer.py::test_helper_ends_bridges` reads the script; only the § 7 Windows check runs it |
| Names stay stable (§ 4.5) | **nothing** — a renamed tool passes every test; caught only by review |
| Each app's connection steps (§ 4.2) | **Partial:** the § 7 by-hand check, for the three apps named there |
| The protocol subset matches MCP (§ 4.4) | **Partial:** `tests/test_bridge.py` checks our reading of the spec, not the spec; the § 7 check runs real apps |

## 11. Cross-doc impact

- `docs/design.md`: the Face row gains the door and the AI helper screen; a
  Bridge row; § State gains the waiting request beside Updating's offer;
  § The stack names the hand-written MCP subset.
- PRESS-0022 § 4.5: a third route, `--assistant`, which prints no report.
- PRESS-0023: INV-12's helper now ends bridges while it waits (§ 4.9).
- PRESS-0345: its box gains a second caller.
- PRESS-0262 INV-9: `bridge.py` joins the modules that import a network
  module; it reaches only 127.0.0.1.
- The words table: the `assistant.` keys.
- README and the Hub: what the AI helper is and how to connect it.
- CHANGELOG at release.

## 12. Cold-eyes loop log

Rows live in `../reviews/PRESS-0337-ai-assistant-loop-log.md`.

## 13. Open questions

None. `2025-06-18` is a published MCP version
(<https://modelcontextprotocol.io/specification/2025-06-18>), and the
2026-07-28 versioning page counts "`2025-11-25` and earlier" as legacy,
checked 2026-11-11.
