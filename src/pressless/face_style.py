"""The Face's stylesheet, as Python string constants (PRESS-0468).

It changes when the Face's look does; face.py changes when a request's
handling does, so it lives apart. `STYLE` is the whole sheet face.py serves.
"""

from pressless import themes

# The Face's look (PRESS-0178, PRESS-0189). The colours are a theme's
# (themes.py, PRESS-0190); with none chosen they follow the computer, light or
# dark. Every rule sits under `.face`, because the editor links his site's
# stylesheets into this same document and a bare `body` or `a` rule of his
# would otherwise restyle the Face. The box keeps his site's font, and takes its
# colours only where his stylesheet sets none. The body resets every property
# first, because a rule of his can set one no `.face` rule does, as a
# two-column `body { display: grid }` would (PRESS-0133).
# A hidden #photograph-missing, #address, .states or #standing child keeps its
# space, so nothing beside a control moves; #panel's hidden rows are dropped.
# PRESS-0261: a code box's textarea is reached as `.code-box > :last-child`, so
# a site's own textarea rule cannot cover the coloured copy behind it.
# PRESS-0338: the text size zooms the body. A width rule is therefore a
# container query, which measures the zoomed width where a media query would
# measure the window's; and the window's height or width, which zoom
# multiplies, is divided by --face-zoom first. A container body no longer
# hands its background to the window in Chrome, so the root takes it.
# Measured 2026-11-06 in Chrome and Firefox.
SHAPES = """
body.face { all: unset; display: block; margin: 0; background: var(--paper); color: var(--ink);
  font: 16px/1.55 system-ui, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  zoom: var(--face-zoom, 1); container-type: inline-size; }
:root:has(> body.face) { background: var(--paper); }
.face .bar { position: sticky; top: 0; z-index: 10; display: flex; align-items: center;
  flex-wrap: wrap;
  gap: .6rem; padding: .6rem 1.5rem; background: var(--sheet);
  border-bottom: 1px solid var(--line); box-shadow: 0 2px 10px var(--shadow); }
.face .bar svg { width: 1.3rem; height: auto; }
.face .bar svg [fill]:not([fill="none"]), .face .bar svg g { fill: var(--amber); }
.face .bar b { font: 700 1.2rem/1 Arial, Calibri, "Liberation Sans", Helvetica, sans-serif; }
.face .bar b span { font-family: system-ui, "Segoe UI", sans-serif; font-weight: 400; }
.face .bar .theme, .face .bar .size { margin: 0; flex-direction: column; align-items: stretch;
  gap: .3rem; }
.face .bar .theme select, .face .bar .size select { padding: .3rem .5rem; }
.face .bar .more { margin-left: auto; position: relative; }
.face .bar .more > summary { list-style: none; cursor: pointer; padding: .35rem .9rem;
  font-weight: 600; line-height: 1.4; color: var(--ink); background: var(--paper);
  border: 1px solid var(--line); border-radius: 999px; box-shadow: 0 1px 3px var(--shadow); }
.face .bar .more > summary::-webkit-details-marker { display: none; }
.face .bar .more > summary::after { content: " ▾"; }
.face .bar .more > summary:focus-visible { outline: 2px solid var(--amber); outline-offset: 2px; }
.face .bar .more > div { position: absolute; right: 0; top: calc(100% + .4rem); z-index: 20;
  display: flex; flex-direction: column; gap: .6rem; min-width: 16rem; padding: .9rem;
  background: var(--sheet); border: 1px solid var(--line); border-radius: 14px;
  box-shadow: 0 8px 30px var(--shadow); }
.face .bar .more a { color: var(--ink); font-weight: 600; }
.face .bar > a, .face .nav > a { display: inline-block; margin: 0; padding: .35rem .9rem;
  font: inherit; font-weight: 600; line-height: 1.4; color: var(--ink);
  background: var(--sheet); border: 1px solid var(--line); border-radius: 999px;
  text-decoration: none; box-shadow: 0 1px 3px var(--shadow);
  transition: border-color .15s, box-shadow .15s; }
.face .bar > a { background: var(--paper); }
.face .bar > a:hover, .face .nav > a:hover { color: var(--ink); border-color: var(--amber);
  box-shadow: 0 3px 10px var(--shadow); }
.face #working-note { position: fixed; left: 50%; bottom: 1.5rem; transform: translateX(-50%);
  margin: 0; padding: .7rem 1.2rem; width: min(40rem, 90vw); box-sizing: border-box; z-index: 20;
  background: var(--sheet); color: var(--ink); border: 1px solid var(--amber);
  border-radius: 12px; box-shadow: 0 8px 30px var(--shadow); font-weight: 600; }
.face #working-note p { margin: 0; }
.face #working-note progress { display: block; width: 100%; height: .8rem; margin: .5rem 0;
  accent-color: var(--amber); }
.face #working-note .count { font-weight: 400; min-height: 2.8em; line-height: 1.4; }
.face .bar > a[aria-disabled] { opacity: .45; cursor: not-allowed;
  border-color: var(--line); box-shadow: none; }
.face .bar > a:focus-visible, .face .nav > a:focus-visible { outline: 2px solid var(--amber);
  outline-offset: 2px; }
.face .nav { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem; }
.face ul.sites li form { display: flex; align-items: center; gap: .75rem; margin: 0; }
.face main { max-width: 72rem; margin: 0 auto; padding: 2rem 1.5rem 3rem; }
.face h1, .face h2 { font-family: Arial, Calibri, "Liberation Sans", Helvetica, sans-serif;
  font-weight: 600; line-height: 1.2; color: var(--ink); }
.face h1 { font-size: 2.1rem; margin: .25rem 0 1.5rem; letter-spacing: -.01em; }
.face h1::after { content: none; }
.face h2 { font-size: 1.3rem; margin: 2rem 0 .75rem; }
.face .card { background: var(--sheet); border: 1px solid var(--line); border-radius: 14px;
  padding: 1.1rem 1.4rem; margin: 1.25rem 0; box-shadow: 0 4px 18px var(--shadow); }
.face .card > h2:first-child { margin-top: 0; }
.face .card > :last-child { margin-bottom: 0; }
.face .tiles { /* PRESS-0353 § 4.3: as many tiles to a row as fit */
  display: grid; gap: 0 1.25rem;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr)); }
.face .tiles .card { margin: .6rem 0; }
.face #checklist ul { list-style: none; padding: 0; }
.face #checklist li { margin: .35rem 0; }
.face #checklist li.done a { color: var(--soft); }
.face a { color: var(--amber-ink); text-underline-offset: .15em; }
.face ul { padding-left: 1.2rem; }
.face li { margin: .3rem 0; }
.face small, .face .hint, .face [id$="-hint"], .face [id$="-status"] { color: var(--soft); }
.face label { display: inline-flex; flex-direction: column; gap: .25rem;
  margin: 0 1rem .75rem 0; font-size: .9rem; color: var(--soft); vertical-align: bottom; }
.face input, .face select, .face :where(textarea) { font: inherit; color: var(--ink);
  background: var(--paper); border: 1px solid var(--line); border-radius: 10px;
  padding: .5rem .7rem; }
.face input:focus, .face select:focus, .face :where(textarea:focus), .face button:focus-visible {
  outline: 2px solid var(--amber); outline-offset: 2px; }
.face button { font: inherit; font-weight: 600; cursor: pointer; color: var(--ink);
  background: var(--sheet); border: 1px solid var(--line); border-radius: 999px;
  padding: .5rem 1.1rem; vertical-align: bottom; box-shadow: 0 1px 3px var(--shadow);
  transition: border-color .15s, transform .15s, box-shadow .15s; }
.face label + button, .face label ~ button { margin-bottom: .75rem; }
.face .switch-row { display: flex; align-items: center; justify-content: space-between;
  gap: 1rem 1.5rem; flex-wrap: wrap; margin: 1.25rem 0; padding: .9rem 1.4rem;
  background: var(--sheet); border: 1px solid var(--line); border-radius: 14px; }
.face .switch-row p { margin: 0; }
.face .switch-row > .states { flex: 1 1 22rem; }
.face form.switch-row > button:only-of-type { flex: none; margin: 0; background: var(--paper);
  color: var(--ink); border-color: var(--line); }
.face .site-line { margin: -.4rem 0 1rem; color: var(--soft); }
.face button.help { padding: .4rem .8rem; min-width: 2.4rem; }
.face .picture-row p { margin-bottom: .4rem; }
.face .picture-shown { display: inline-block; width: 4rem; height: 4rem; margin-right: .75rem;
  vertical-align: middle; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.face .picture-shown img { width: 100%; height: 100%; object-fit: cover; }
.face dialog { max-width: min(42rem, calc(100vw / var(--face-zoom, 1) - 2rem)); color: var(--ink);
  background: var(--sheet); border: 1px solid var(--line); border-radius: 14px;
  padding: 1.1rem 1.4rem; box-shadow: 0 8px 30px var(--shadow); }
.face dialog::backdrop { background: rgba(0, 0, 0, .5); }
.face button:hover { border-color: var(--amber); transform: translateY(-1px);
  box-shadow: 0 3px 10px var(--shadow); }
.face button:disabled, .face button:disabled:hover { opacity: .45; cursor: not-allowed;
  border-color: var(--line); transform: none; box-shadow: none; }
.face .press-status { min-height: 4.5em; }
.face dialog.message [id] { color: var(--ink); }
.face [aria-invalid="true"] { outline: 3px solid var(--amber-ink); outline-offset: 2px; }
.face #save-status { display: inline-block; min-width: 6em; }
.face #photograph-status { display: block; min-height: 1.55em; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.face #editor > #photograph-missing { min-height: 4.65em; max-height: 4.65em;
  overflow-y: auto; margin-top: 0; }
.face #photograph-missing[hidden] { display: block; visibility: hidden; }
.face #address[hidden] { display: inline; visibility: hidden; }
.face .sign-in-slot { min-height: 6.5em; }
.face #domain-state { min-height: 3.1em; }
.face .states, .face #standing { display: grid; }
.face .states > * { grid-area: 1 / 1; }
.face #standing > [data-when="1"]:not(form) { grid-area: 1 / 1; }
.face #standing > form[data-when="1"] { grid-area: 2 / 1; }
.face #standing > [data-when="0"] { grid-area: 1 / 1 / 3 / 2; }
.face .states [hidden], .face #standing [hidden] { display: block; visibility: hidden; }
.face #standing[hidden] { display: grid; visibility: hidden; }
.face #save-hint { min-height: 4.7em; }
.face [data-editor="publish"], .face form > button:only-of-type { background: var(--press);
  color: var(--on-press); border-color: var(--press); }
.face #editor { display: flex; flex-wrap: wrap; align-items: flex-end; }
.face #editor > p { flex-basis: 100%; margin: .25rem 0 .75rem; }
.face :where(textarea) { box-sizing: border-box; width: 100%; }
.face :where(#editor textarea) { flex-basis: 100%; min-height: 60vh; resize: vertical;
  padding: 1rem 1.2rem; }
.face details { margin: 1rem 0; }
.face summary { cursor: pointer; color: var(--soft); }
.face table { border-collapse: collapse; margin: .5rem 0; }
.face th, .face td { text-align: left; padding: .4rem .8rem .4rem 0;
  border-bottom: 1px solid var(--line); vertical-align: top; }
.face code, .face pre { font: .9em/1.4 ui-monospace, Consolas, "DejaVu Sans Mono", monospace; }
.face pre { white-space: pre-wrap; background: var(--paper); padding: .7rem;
  border-radius: 10px; }
.face .failure, .face .notices > li { list-style: none; margin: 1rem 0;
  padding: .9rem 1.1rem; background: var(--sheet); border: 1px solid var(--line);
  border-left: 5px solid var(--alert); border-radius: 12px; box-shadow: 0 4px 18px var(--shadow); }
.face .notices { padding: 0; }
.face .notices > li { border-left-color: var(--amber); }
.face .failure p, .face .notices p { margin: .2rem 0; }
.face .failure .what, .face .notices .what { font-weight: 600; }
.face iframe#preview { width: 100%; min-height: 70vh; border: 1px solid var(--line);
  border-radius: 12px; background: #fff; filter: var(--preview-dim); }
.face iframe#preview.undimmed { filter: none; }
.face #proof { position: relative; }
.face #drag-handle { position: absolute; z-index: 2; margin: 0; padding: .2rem .7rem;
  cursor: grab; touch-action: none; }
.face #drop-line { position: absolute; z-index: 2; height: 3px; background: var(--amber);
  pointer-events: none; }
.face .true-colours { display: var(--preview-switch); margin: 0 0 .5rem; }
.face .true-colours label { margin: 0; }
.face label:has(> input[type="radio"]), .face label:has(> input[type="checkbox"]) {
  flex-direction: row; align-items: center; gap: .5rem; font-size: 1rem; color: var(--ink);
  cursor: pointer; }
.face input[type="radio"], .face input[type="checkbox"] { width: 1.25rem; height: 1.25rem;
  margin: 0; padding: 0; accent-color: var(--amber); flex: none; }
.face fieldset.looks, .face fieldset.sign-ins, .face fieldset.picks {
  border: 0; margin: 0 0 1rem; padding: 0; }
.face fieldset.looks legend, .face fieldset.sign-ins legend, .face fieldset.picks legend {
  padding: 0; margin-bottom: .5rem; }
.face form:has(input[name="reuse"]:not([value=""]):checked) .someone-else { display: none; }
.face form:has(input[name="pick"]:not([value=""]):checked) .new-one { display: none; }
.face .look-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
  gap: .5rem; margin: 0 0 .75rem; }
.face .look-grid label.look { display: grid; grid-template-columns: auto 1fr;
  align-items: start; gap: .4rem .5rem; margin: 0; padding: .5rem;
  border: 2px solid transparent; border-radius: 8px; }
.face .look-grid label.look:has(input:checked) { border-color: var(--amber); }
.face .look-grid label.look > :last-child { grid-column: 1 / 3; line-height: 1.3; }
.face .look-grid label.look b { display: block; }
.face .mini { flex: none; display: grid; width: 6rem; height: 4rem; overflow: hidden;
  border: 1px solid var(--soft); border-radius: 6px; background: var(--paper);
  grid-template-rows: 1.2rem 1fr .7rem; }
.face .mini > :nth-child(1) { background: var(--band); }
.face .mini > :nth-child(2) { background: var(--paper); }
.face .mini > :nth-child(3) { background: var(--foot); }
.face .mini-sunrise { grid-template-rows: 1.4rem 1fr .7rem; }
.face .mini-meadow { grid-template-columns: 1.8rem 1fr; grid-template-rows: 1fr .5rem; }
.face .mini-meadow > :nth-child(1) { grid-row: 1 / 3; }
.face .mini-meadow > :nth-child(3) { border-top: 1px solid var(--line); }
.face .mini-harbour { grid-template-rows: 1rem 1fr .9rem; }
.face .mini-studio { grid-template-rows: .9rem 1fr .6rem; }
.face .mini-studio > :nth-child(1) { background: var(--paper);
  border-bottom: 1px solid var(--line); }
.face .mini-market { grid-template-rows: 1.5rem 1fr .6rem; }
.face .mini-market > :nth-child(2) { margin: -.6rem .6rem .3rem;
  border: 1px solid var(--line); border-radius: 2px; }
.face .mini-stage { grid-template-rows: 2rem 1fr .6rem; }
.face .mini-stage > :nth-child(1) { box-shadow: inset 0 -.3rem 0 var(--band),
  inset 0 -.55rem 0 var(--link); }
.face .mini-commons { grid-template-rows: 1.6rem 1fr .6rem; }
.face .mini-commons > :nth-child(1) { border-bottom: .45rem solid var(--foot); }
.face .mini-letter { grid-template-rows: .9rem 1fr .5rem; padding: 0 1.5rem; }
.face .mini-letter > :nth-child(1) { background: var(--paper);
  border-bottom: 1px solid var(--line); }
.face .mini-style > :nth-child(2) { background: linear-gradient(var(--link), var(--link))
  .6rem 50% / 55% 3px no-repeat, var(--paper); }
.face #panel { flex-basis: 100%; box-sizing: border-box; height: 60vh; overflow-y: auto;
  padding: .5rem 1rem; border: 1px solid var(--line); border-radius: 12px;
  background: var(--sheet); }
.face #panel [hidden], .face #panel .panel-row[hidden] { display: none; }
.face #panel #picked, .face #panel #panel-said { min-height: 3.1em; }
.face #panel #picked { position: sticky; top: -.5rem; z-index: 1; margin-top: 0;
  padding: .5rem 0; background: var(--sheet); }
.face #panel .panel-row { display: flex; flex-wrap: wrap; gap: .5rem; margin: .5rem 0; }
.face :where(#panel textarea) { min-height: 12rem; font: .9em/1.4 ui-monospace, Consolas,
  "DejaVu Sans Mono", monospace; }
.face .code-box { position: relative; width: 100%; flex-basis: 100%; }
.face .code-box > pre { position: absolute; inset: 0; margin: 0; box-sizing: border-box;
  overflow: hidden; pointer-events: none; border-style: solid; border-color: transparent;
  border-radius: 10px; color: var(--ink); background: var(--paper); }
.face .code-box > :last-child { position: relative; display: block; margin: 0; overflow-y: auto;
  color: transparent; -webkit-text-fill-color: transparent; caret-color: var(--ink);
  background: transparent; }
.face .code-box > * { white-space: pre-wrap; overflow-wrap: break-word;
  scrollbar-gutter: stable; }
.face .code-box > :last-child::selection {
  background: color-mix(in srgb, var(--amber) 35%, transparent); }
.face .code-box .k-tag { color: var(--code-tag); }
.face .code-box .k-attr { color: var(--code-attr); }
.face .code-box .k-value { color: var(--code-value); }
.face .code-box .k-note { color: var(--soft); }
.face #panel .panel-add { border-bottom: 1px solid var(--line); margin-bottom: .75rem;
  padding-bottom: .5rem; }
.face main:has(> #editor), .face main:has(> #look) { display: flex; flex-direction: column; }
.face main > #undo-result { order: -1; }
.face .look-colours td { vertical-align: top; padding: .25rem 1rem .25rem 0; }
.face .look-colours input[type=color] { width: 4rem; height: 2.25rem; padding: 2px; }
.face .look-warn { display: block; width: 13rem; height: 4.5em; overflow-y: auto;
  font-size: .85em; }
.face .look-effects, .face .look-route { border: 0; margin: 1rem 0; padding: 0; }
.face .look-effects label, .face .look-route label { display: block; margin: .25rem 0; }
@container (min-width: 1120px) {
  .face main:has(> #editor), .face main:has(> #look) { max-width: none; display: grid;
    column-gap: 2rem; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .face main:has(> #editor) > *, .face main:has(> #look) > * { grid-column: 1; }
  .face main > #proof { grid-column: 2; grid-row: 1 / span 12; align-self: start;
    position: sticky; top: 4.5rem; height: calc(100vh / var(--face-zoom, 1) - 6rem);
    display: flex; flex-direction: column; }
  .face #proof > #preview { flex: 1; min-height: 0; }
}
@media (prefers-reduced-motion: reduce) { .face button { transition: none; }
  .face button:hover { transform: none; } }
@media print { .face .bar { display: none; } body.face { background: #fff; color: #000; }
  .face .card { box-shadow: none; } }
"""

STYLE = (
    f":root {{ color-scheme: light dark; {themes.declarations(themes.find('light'))}"
    f" --shadow: rgba(60, 40, 10, .10); {themes.preview_dimming(False)} }}\n"
    f"@media (prefers-color-scheme: dark) {{ :root {{ {themes.declarations(themes.find('dark'))}"
    f" --shadow: rgba(0, 0, 0, .45); {themes.preview_dimming(True)} }} }}\n"
    + themes.css() + SHAPES
)
