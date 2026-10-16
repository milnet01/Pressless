"""The Look screen: the site's look, changed from a panel of choices with a
live preview (PRESS-0196 § 4.4, docs/specs/PRESS-0196-site-look.md).

`GET /look` shows one of three states: choices that made the style code
beside them; style code they did not make, which a save first copies into
the bin; and no style code at all, an imported site, which this screen leaves
alone (§ 4.5). The screen links none of the site's stylesheets into its own
document, so the site's CSS reaches only the frame (INV-10).
"""
from __future__ import annotations

import html
from pathlib import Path

from pressless import builder, editor, look, page_editor, settings, setup, store
from pressless.face import SENTENCES, Face, Reply, Request, Sentence, Site, render_notices
from pressless.words import say

ADDRESS = "/look"
SAVED = "saved"      # the query a save sends the screen back with


class NoStyleCode(Exception):
    """The site has no style code for the Look screen to change (§ 4.5)."""


class LookRefused(Exception):
    """A posted choice is not one § 4.1's table allows."""


SENTENCES[NoStyleCode] = Sentence(
    "failure.look_screen.NoStyleCode.what",
    Site.UNCHANGED,
    "failure.look_screen.NoStyleCode.next",
)
SENTENCES[LookRefused] = Sentence(
    "failure.look_screen.LookRefused.what",
    Site.UNCHANGED,
    "failure.look_screen.LookRefused.next",
)

# Each choice's words keys, in look.py's order.
_COLOUR_WORDS = {
    "paper": "look_screen.colour.paper", "ink": "look_screen.colour.ink",
    "soft": "look_screen.colour.soft", "link": "look_screen.colour.link",
    "heading": "look_screen.colour.heading", "band": "look_screen.colour.band",
    "on-band": "look_screen.colour.on-band", "band-soft": "look_screen.colour.band-soft",
    "accent": "look_screen.colour.accent", "foot": "look_screen.colour.foot",
    "on-foot": "look_screen.colour.on-foot", "foot-link": "look_screen.colour.foot-link",
    "line": "look_screen.colour.line"}
_FONT_WORDS = {"system": "look_screen.font.system", "serif": "look_screen.font.serif",
               "humanist": "look_screen.font.humanist", "mono": "look_screen.font.mono"}
_SIZE_WORDS = {"normal": "look_screen.size.normal", "large": "look_screen.size.large",
               "larger": "look_screen.size.larger"}
_WIDTH_WORDS = {"narrow": "look_screen.width.narrow", "medium": "look_screen.width.medium",
                "wide": "look_screen.width.wide"}
_EFFECT_WORDS = {"lift": "look_screen.effect.lift", "reveal": "look_screen.effect.reveal",
                 "smooth": "look_screen.effect.smooth"}
_SCHEME_WORDS = {"light": "script.look.light", "dark": "script.look.dark"}
_TEXT_COLOURS = {text for text, _ in look.TEXT_PAIRS}


def register(face: Face, folder: Path) -> None:
    """Add the Look screen's routes to `face`. Its frame's files are served by
    `editor.register`, which the launch calls first."""
    folder = Path(folder)

    def route(handler):
        return lambda request: handler(face, folder, request)

    face.add_page("GET", ADDRESS, route(_open))
    face.add_page("POST", ADDRESS + "/preview", route(_preview))
    face.add_page("POST", ADDRESS + "/save", route(_save))


def _has_style_code(folder: Path) -> None:
    """§ 4.5: NoStyleCode where the site has none."""
    if not store.style_code_path(folder).is_file():
        raise NoStyleCode("the site has no style code; its look is its own stylesheets")


def _posted(form: dict[str, str]) -> tuple[look.Choices, str]:
    """The choices and their own CSS a form posts, or LookRefused."""
    def colours(scheme: str) -> dict[str, str]:
        return {name: form.get(f"{scheme}.{name}", "").lower() for name in look.COLOURS}

    choices = look.Choices(
        layout=form.get("layout", ""), light=colours("light"), dark=colours("dark"),
        body_font=form.get("body_font", ""), heading_font=form.get("heading_font", ""),
        text_size=form.get("text_size", ""), width=form.get("width", ""),
        effects=tuple(name for name in look.EFFECTS if form.get(f"effect.{name}") == "on"))
    why = look.problem(choices)
    if why:
        raise LookRefused(why)
    # A browser posts a textarea's line ends as CR LF.
    extra = form.get("extra", "").replace("\r\n", "\n").replace("\r", "\n")
    return choices, extra


def _frame(face: Face, folder: Path) -> tuple[str | None, str | None]:
    """The homepage as the preview builds it (§ 4.4), else the first fixed
    page; or the failure in its place."""
    try:
        saved = settings.load(folder)
        held = store.list_html(folder, store.PAGES_FOLDER)
        if not held:
            raise builder.BuildStopped("there is no page to show the look on")
        show = page_editor.HOME if page_editor.HOME in held else held[0]
        text = store.read_html(store.html_path_for(folder, store.PAGES_FOLDER, show))
        relative = builder.preview_html(folder, saved, folder / editor.PREVIEW_FOLDER,
                                        builder.Html(store.PAGES_FOLDER, show, text),
                                        show=show, photo_src=editor.photo_src)
    except Exception as exc:  # noqa: BLE001 -- a preview failure never stops the panel
        return None, face.fail(exc, publishing=False)
    return editor.PREVIEW_ADDRESS + relative, None


def _open(face: Face, folder: Path, request: Request) -> str:
    """§ 4.4's three states, and § 6's unreadable choices."""
    with editor.LOCK, face.capture() as notices:
        if not store.style_code_path(folder).is_file():
            return render_notices(notices) + _imported()
        try:
            base = look.digest(folder)
            made = look.made_here(folder)
            choices = look.read(folder)
            extra = look.read_extra(folder)
        except store.StoreError as exc:     # LookUnreadable among them
            return render_notices(notices) + face.fail(exc, publishing=False)
        restart = choices is None
        if restart:     # § 4.4 state 2: a layout picker, on its defaults
            asked = request.query.get("layout", "")
            choices = look.defaults(asked if asked in look.LAYOUTS else look.LAYOUTS[0])
        frame, failure = _frame(face, folder)
    return render_notices(notices) + _page(choices, extra, base, made, restart, frame, failure,
                                           SAVED in request.query)


def _imported() -> str:
    return (f'<p><a href="/">{say("face.your_writing")}</a></p>'
            f'<h1>{say("look_screen.title")}</h1><p>{say("look_screen.imported")}</p>')


def _preview(face: Face, folder: Path, request: Request) -> Reply:
    """§ 4.4's live preview: the style code the form makes, and its warnings.
    Writes nothing."""
    form = editor._form(request)
    with editor.LOCK, face.capture() as notices:
        try:
            _has_style_code(folder)
            choices, extra = _posted(form)
        except (NoStyleCode, LookRefused) as exc:
            return editor._failed(face, notices, exc)
    return editor._json({"css": look.css(choices, extra), "warnings": look.warnings(choices)})


def _save(face: Face, folder: Path, request: Request) -> Reply:
    """§ 4.4's Save: nothing is written where the look changed since the
    screen was drawn, or where choices.json cannot be read (§ 4.1). Style code
    the choices did not make is copied into the bin first, and left in place
    until look.save replaces it last (INV-7)."""
    form = editor._form(request)
    with editor.LOCK, face.capture() as notices:
        try:
            _has_style_code(folder)
            if look.digest(folder) != form.get("base", ""):
                raise editor.ChangedElsewhere("the site's look changed since this window read it")
            look.read(folder)
            choices, extra = _posted(form)
            if not look.made_here(folder):
                store.copy_to_bin(folder, store.style_code_path(folder))
            look.save(folder, choices, extra)
        except (store.StoreError, editor.ChangedElsewhere, NoStyleCode, LookRefused) as exc:
            return editor._failed(face, notices, exc)
    return Reply(b"", "text/plain; charset=utf-8", status=303, location=f"{ADDRESS}?{SAVED}=1")


def _warning(scheme: str, text: str, ground: str, ratio: float) -> str:
    """One warning in words; the script says the same with the same key."""
    return say("script.look.warning", text=say(_COLOUR_WORDS[text]),
               background=say(_COLOUR_WORDS[ground]), scheme=say(_SCHEME_WORDS[scheme]),
               ratio=f"{ratio:.2f}")


def _page(choices: look.Choices, extra: str, base: str, made: bool, restart: bool,
          frame: str | None, failure: str | None, saved: bool) -> str:
    def attr(value: str) -> str:
        return html.escape(value, quote=True)

    def options(field: str, chosen: str, named: dict[str, str]) -> str:
        return (f'<select name="{field}">' + "".join(
            f'<option value="{name}"{" selected" if name == chosen else ""}>{say(key)}</option>'
            for name, key in named.items()) + "</select>")

    warned = {(scheme, text): _warning(scheme, text, ground, ratio)
              for scheme, text, ground, ratio in look.warnings(choices)}

    # A warning's slot keeps its size (face's .look-warn), so a warning
    # appearing moves nothing.
    def colour(scheme: str, name: str, value: str) -> str:
        slot = (f'<span class="look-warn" data-warn="{scheme}.{name}" role="status">'
                f'{warned.get((scheme, name), "")}</span>' if name in _TEXT_COLOURS else "")
        return (f'<td><input type="color" name="{scheme}.{name}" value="{attr(value)}" '
                f'aria-label="{attr(say(_COLOUR_WORDS[name]))}, '
                f'{attr(say(_SCHEME_WORDS[scheme]))}">{slot}</td>')

    rows = "".join(
        f'<tr data-colour="{name}" data-label="{attr(say(_COLOUR_WORDS[name]))}">'
        f"<th scope=\"row\">{say(_COLOUR_WORDS[name])}</th>"
        f"{colour('light', name, choices.light[name])}{colour('dark', name, choices.dark[name])}"
        "</tr>" for name in look.COLOURS)
    effects = "".join(
        f'<label><input type="checkbox" name="effect.{name}" value="on"'
        f'{" checked" if name in choices.effects else ""}> {say(key)}</label>'
        for name, key in _EFFECT_WORDS.items())
    said = say("look_screen.saved") if saved else ""
    replaces = "" if made else f'<p class="look-replaces">{say("look_screen.replaces")}</p>'
    return f"""<p><a href="/">{say("face.your_writing")}</a></p>
<h1>{say("look_screen.title")}</h1>
<p>{say("look_screen.about")}</p>
<p id="look-status" class="press-status" role="status">{said}</p>
<form id="look" method="post" action="{ADDRESS}/save"{' data-restart' if restart else ''}>
<input type="hidden" name="base" value="{attr(base)}">
<fieldset class="looks"><legend>{say("look_screen.layout")}</legend>
{setup.look_choices("layout", choices.layout)}
{f'<p>{say("look_screen.restart")}</p>' if restart else ""}</fieldset>
<h2>{say("look_screen.colours")}</h2>
<p>{say("look_screen.colours.about")}</p>
<table class="look-colours"><thead><tr><td></td><th scope="col">{say(_SCHEME_WORDS["light"])}</th>
<th scope="col">{say(_SCHEME_WORDS["dark"])}</th></tr></thead><tbody>{rows}</tbody></table>
<h2>{say("look_screen.type")}</h2>
<p><label>{say("look_screen.body_font")} {options("body_font", choices.body_font, _FONT_WORDS)}
</label></p>
<p><label>{say("look_screen.heading_font")}
 {options("heading_font", choices.heading_font, _FONT_WORDS)}</label></p>
<p><label>{say("look_screen.text_size")} {options("text_size", choices.text_size, _SIZE_WORDS)}
</label></p>
<p><label>{say("look_screen.width")} {options("width", choices.width, _WIDTH_WORDS)}</label></p>
<fieldset class="look-effects"><legend>{say("look_screen.effects")}</legend>
<p>{say("look_screen.effects.about")}</p>{effects}</fieldset>
<h2>{say("look_screen.extra")}</h2>
<p>{say("look_screen.extra.about")}</p>
<textarea name="extra" rows="10" spellcheck="false">
{html.escape(extra)}</textarea>
{replaces}
<p><button>{say("look_screen.save")}</button></p>
</form>
<div id="proof"><div id="look-failure">{failure or ""}</div>
<iframe id="preview" class="undimmed" title="{attr(say("look_screen.preview_title"))}"
 sandbox="allow-same-origin" src="{attr(frame or "about:blank")}"></iframe></div>
<script>{_SCRIPT}</script>"""


# § 4.4's live preview. Every change posts the form; the answer's style code
# replaces the site's own in the frame, scripted from here as the page
# editor's pair() does, since the frame runs no script of its own.
_SCRIPT = r"""
(() => {
  const form = document.getElementById("look");
  const frame = document.getElementById("preview");
  const status = document.getElementById("look-status");
  let draft = null, timer = null, asked = 0;

  function apply() {
    const doc = frame.contentDocument;
    if (draft === null || !doc || !doc.head) return;
    doc.querySelectorAll("link[rel=stylesheet]").forEach((link) => {
      if (link.href.endsWith("look/style.css")) link.disabled = true;
    });
    let style = doc.getElementById("pressless-look-draft");
    if (!style) {
      style = doc.createElement("style");
      style.id = "pressless-look-draft";
      doc.head.appendChild(style);
    }
    style.textContent = draft;
  }
  const label = (name) => form.querySelector(`tr[data-colour="${name}"]`).dataset.label;
  function warn(found) {
    form.querySelectorAll("[data-warn]").forEach((slot) => { slot.textContent = ""; });
    for (const [scheme, text, ground, ratio] of found) {
      form.querySelector(`[data-warn="${scheme}.${text}"]`).textContent = say(
        "script.look.warning", {text: label(text), background: label(ground),
                                 scheme: say("script.look." + scheme), ratio: ratio.toFixed(2)});
    }
  }
  async function preview() {
    const mine = ++asked;
    try {
      const answer = await fetch("/look/preview",
                                 {method: "POST", body: new URLSearchParams(new FormData(form))});
      if (mine !== asked) return;
      if (answer.status !== 200) { status.textContent = say("script.look.no_preview"); return; }
      const reply = await answer.json();
      if (mine !== asked) return;
      draft = reply.css;
      apply();
      warn(reply.warnings);
      status.textContent = "";
    } catch (error) {
      if (mine === asked) status.textContent = say("script.look.no_preview");
    }
  }
  form.addEventListener("input", (event) => {
    // A site whose choices were never saved starts again from a layout's own.
    if (form.hasAttribute("data-restart") && event.target.name === "layout") {
      window.location.href = "/look?layout=" + encodeURIComponent(event.target.value);
      return;
    }
    clearTimeout(timer);
    timer = setTimeout(preview, 250);
  });
  frame.addEventListener("load", apply);
})();
"""
