"""The browser scripts both editors load, as Python string constants (PRESS-0476).

The entry editor (editor.py) and the page editor (page_editor.py) each carry
a script of their own, `_EDITOR_SCRIPT` and `_PAGE_SCRIPT`, built from these.
`UNDO_SCRIPT` is also read by Your site (overview.py). A fix to one of these is
a fix to every page that loads it. Neither editor's own script, nor either
visual view's, is here: each is used by one editor only.
"""
from pressless import pressing

# PRESS-0015 s 4.6. Both pages carry this, and Your site (overview.py) and the
# page editor read it from here. Neither page reloads itself (s 4.2):
# the reply is the only place the summary and the gathered notices exist, and a
# reload throws both away before he has read them. So the box is replaced with
# what came back, and a link back to his list is offered instead.
UNDO_SCRIPT = pressing.SCRIPT + """
(() => {
  const button = document.querySelector("button[data-undo]");
  if (!button) return;
  // PRESS-0234: an editor's press row has one status line for both buttons.
  const said = document.getElementById("publish-status") ||
    document.getElementById("undo-status");
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
    link.textContent = say("script.undo.back");
    back.appendChild(link);
    result.appendChild(back);
    for (const box of [document.getElementById("editor"),
                       document.getElementById("listing")]) {
      if (box) box.hidden = true;
    }
  };

  button.addEventListener("click", async () => {
    button.disabled = true;
    said.textContent = say("script.press.undoing");
    try {
      const answer = await fetch("/undo", {method: "POST"});
      const text = await answer.text();
      said.textContent = "";
      if (answer.status !== 200) { show("", text); return; }
      const reply = JSON.parse(text);
      if (window.presslessPress.busy(reply)) return;
      said.textContent = reply.undone
        ? say("script.press.undone") : say("script.press.not_undone");
      show((reply.notices || "") + (reply.undone ? "" : reply.failure || ""),
           reply.undone ? reply.summary : "");
    } catch (error) {
      said.textContent = "";
      show("", say("script.undo.unreachable"));
    } finally {
      button.disabled = window.presslessPress.asking();
    }
  });
})();
"""


# PRESS-0012 § 4.7 and PRESS-0135: both editors' leaving, the entry's here and
# page_editor._PAGE_SCRIPT's. An unsaved change goes with the page unless a
# save is in flight. A keepalive request carries at most 64 KiB, counted over
# every keepalive body the page has in flight. This is the page's only one, so
# where the change nears 60,000 bytes, a margin under that, the browser asks
# before leaving instead. `unsaved` says a
# change waits and saving has not stopped; `sending` says a save is in flight.
LEAVING_SCRIPT = """
window.presslessLeaving = (address, fields, unsaved, sending) => {
  window.addEventListener("pagehide", () => {
    if (!unsaved() || sending()) return;
    fetch(address, {method: "POST", body: fields(), keepalive: true}).catch(() => {});
  });
  window.addEventListener("beforeunload", (event) => {
    if (unsaved() && new Blob([fields().toString()]).size > 60000) event.preventDefault();
  });
};
"""


# § 4.7: both editors' saving, the entry's here and page_editor._PAGE_SCRIPT's.
# `send` posts a change; `waiting` says one waits and saving has not stopped.
# A save runs about a second after `schedule`, never two at once. A request
# that posts what a save would post, or may move it, calls `settle` first: it
# waits out a save in flight, saves a waiting change first where `first` says
# so, and holds saves back until the request has answered (PRESS-0135,
# PRESS-0309, PRESS-0329). `release` lets them go, saving what was typed
# meanwhile. `sending` says a save or a held request is in flight.
SAVING_SCRIPT = """
window.presslessSaving = (send, waiting) => {
  let timer = null, held = null, done = null;
  const hold = () => { held = new Promise((resolve) => { done = resolve; }); };
  const free = () => { held = null; done(); };
  const schedule = () => { clearTimeout(timer); timer = setTimeout(save, 1000); };
  async function save() {
    if (held || !waiting()) return;
    hold();
    try { await send(); } finally { release(); }
  }
  async function settle(first) {
    for (;;) {
      clearTimeout(timer);
      while (held) await held;
      if (!first || !waiting()) break;
      first = false;
      await save();
    }
    hold();
  }
  function release() {
    free();
    if (waiting()) schedule();
  }
  return {schedule, settle, release, sending: () => held !== null};
};

// Saving stops: `stopping` sets the editor's own flag, and the failure shows.
window.presslessStop = (stopping) => (text) => {
  stopping();
  document.getElementById("save-status").textContent = say("script.editor.not_saved");
  document.getElementById("failure").innerHTML = text;
};

// The save itself, `send` above: `on` is the editor's own part: `address`,
// the route; posting() and fields(posted), what it posts; unsaved(now), which
// sets its flag; stop(text); and saved(reply, posted), what a reply updates.
// A clean save clears only a failure a save showed: one a press showed
// meanwhile, such as a refused Remove, stays until it is read (PRESS-0480).
window.presslessSend = (on) => {
  let shown = "";
  return async () => {
    const status = document.getElementById("save-status");
    on.unsaved(false);
    status.textContent = say("script.editor.saving");
    try {
      const posted = on.posting();
      const answer = await fetch(on.address, {method: "POST", body: on.fields(posted)});
      const text = await answer.text();
      if (answer.status !== 200) { on.stop(text); return; }
      const reply = JSON.parse(text);
      const box = document.getElementById("failure");
      if (reply.failure || box.innerHTML === shown) box.innerHTML = reply.failure || "";
      shown = reply.failure ? box.innerHTML : "";
      on.saved(reply, posted);
      status.textContent = say("script.editor.saved");
    } catch (error) {
      on.stop("");
    }
  };
};
"""


# A file posted to be kept, from either editor: a photograph to /photograph
# (PRESS-0016) or any other file to /file (PRESS-0197). Answers the reply,
# with its notices shown; or null where the Face refused the file, whose
# failure is then shown, or could not be reached, which `stop`, the editor's
# own, says. `said`, the view's status line, says it is adding meanwhile.
UPLOAD_SCRIPT = """
window.presslessUpload = async (route, file, stop, said) => {
  said.textContent = say(route === "/file" ? "script.editor.adding_file"
                                           : "script.editor.adding_photograph");
  try {
    const answer = await fetch(route + "?name=" + encodeURIComponent(file.name),
                               {method: "POST", body: file});
    const text = await answer.text();
    if (answer.status !== 200) {
      document.getElementById("failure").innerHTML = text;
      return null;
    }
    const reply = JSON.parse(text);
    document.getElementById("notices").innerHTML = reply.notices;
    return reply;
  } catch (error) {
    stop("");
    return null;
  } finally {
    said.textContent = "";
  }
};
"""

# The Publish button's press, shared by both editors' scripts (PRESS-0339,
# PRESS-0345). `on` is the editor's own part: `address`, the route; asked(),
# the plan's question; posting() and fields(posted), what a save posts; settle
# and release, its saving's; standing(), the line between presses; stop(text);
# pressing(now) and unsaved(now), which set its flags; and published(reply,
# posted), what a reply updates.
PUBLISH_SCRIPT = """
window.presslessPublish = (on) => {
  const publish = document.querySelector("button[data-editor=publish]");
  publish.addEventListener("click", async () => {
    // PRESS-0339: said at once, though a save in flight is waited out first.
    const said = document.getElementById("publish-status");
    publish.disabled = true;
    said.textContent = say("script.press.checking");
    on.pressing(true);
    // A save meanwhile would post the copy the publish bins. PRESS-0345: what
    // waits is saved first, so the plan reads it; saves stay held while the
    // box is open.
    await on.settle(true);
    const unpressed = () => {
      said.textContent = on.standing(); on.pressing(false); publish.disabled = false;
      on.release();
    };
    try {
      if (!(await window.presslessCheck(on.asked()))) { unpressed(); return; }
    } catch (error) {
      unpressed(); on.stop(""); return;
    }
    said.textContent = say("script.press.publishing");
    try {
      const posted = on.posting();
      const body = on.fields(posted);
      on.unsaved(false);
      const answer = await fetch(on.address, {method: "POST", body: body});
      const text = await answer.text();
      if (answer.status !== 200) { said.textContent = on.standing(); on.stop(text); return; }
      const reply = JSON.parse(text);
      // Another press runs: nothing was saved, so the change is still to save.
      if (window.presslessPress.busy(reply)) { on.unsaved(true); return; }
      on.published(reply, posted);
      document.getElementById("failure").innerHTML = reply.failure || "";
      said.textContent = reply.published
        ? say("script.press.published") : say("script.press.not_published");
      if (reply.published) window.presslessPress.viewable();
    } catch (error) {
      said.textContent = on.standing(); on.stop("");
    } finally {
      on.pressing(false);
      publish.disabled = window.presslessPress.asking();
      on.release();
    }
  });
};
"""


# PRESS-0260 § 4.4's typing, shared by both visual views: the page editor's
# and the entry's (PRESS-0346 § 4.4). The words are read from the element's
# nodes, never from innerHTML, and a paste is its plain text. Bold, Italic,
# Link and the keys are here too; each editor passes in its own part.
TYPING_SCRIPT = r"""
window.presslessTyping = (() => {
  // A browser types a no-break space where spaces meet; it is saved as a space.
  const text = (value) => value.replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/\u00a0/g, " ");
  // blocks.address_allowed's rule, which the save holds to: the scheme read as
  // a browser reads it, outer spaces and controls stripped, tabs and line
  // breaks removed (PRESS-0306).
  const allowed = (href) => {
    const folded = href.replace(/^[\x00-\x20]+|[\x00-\x20]+$/g, "").replace(/[\t\n\r]/g, "");
    const scheme = /^([A-Za-z][A-Za-z0-9+.-]*):/.exec(folded);
    return !scheme || ["http", "https", "mailto"].includes(scheme[1].toLowerCase());
  };
  // `linkable` says which addresses a link may keep; `keep`, where given,
  // returns the tags to write for an element other words keep, such as the
  // entry editor's colour spans, or null.
  function inline(element, {linkable = allowed, keep = () => null} = {}) {
    let out = "";
    const walk = (parent, linked) => {
      for (const child of parent.childNodes) {
        if (child.nodeType === Node.TEXT_NODE) { out += text(child.data); continue; }
        if (child.nodeType !== Node.ELEMENT_NODE) continue;
        const tag = child.localName;
        const href = child.getAttribute("href");
        if (tag === "br") {
          out += "<br>";
        } else if (tag === "b" || tag === "strong" || tag === "i" || tag === "em") {
          const written = tag === "b" || tag === "strong" ? "strong" : "em";
          wrap("<" + written + ">", "</" + written + ">", child, linked);
        } else if (tag === "a" && !linked && href && linkable(href)) {
          wrap('<a href="' + text(href).replace(/"/g, "&quot;") + '">', "</a>", child, true);
        } else if (keep(child)) {
          wrap(...keep(child), child, linked);
        } else {
          walk(child, linked);
        }
      }
    };
    // An emptied Bold or Italic, as a split at its edge leaves, is dropped.
    const wrap = (opening, closing, child, linked) => {
      const at = out.length;
      walk(child, linked);
      out = out.length === at ? out : out.slice(0, at) + opening + out.slice(at) + closing;
    };
    walk(element, false);
    return out.replace(/<br>$/, "");
  }

  function paste(doc, event) {
    event.preventDefault();
    const words = (event.clipboardData.getData("text/plain") || "").replace(/\s*\n\s*/g, " ");
    doc.execCommand("insertText", false, words);
  }

  // Bold, Italic or Link on the words picked in `doc`. A link takes only an
  // address `linkable` accepts; any other is refused with the words key
  // `refused`, in the panel. True where the words changed.
  function format(doc, name, {linkable = allowed, refused}) {
    if (name !== "link") {
      doc.execCommand(name);
      return true;
    }
    const address = window.prompt(say("script.visual.ask_link"), "https://");
    if (!address) return false;
    if (!linkable(address)) {
      document.getElementById("panel-said").textContent = say(refused);
      return false;
    }
    // With no words picked Firefox links nothing; give the link its address.
    if (doc.getSelection().isCollapsed) {
      doc.execCommand("insertHTML", false, '<a href="' + text(address).replace(/"/g, "&quot;")
        + '">' + text(address) + "</a>");
    } else {
      doc.execCommand("createLink", false, address);
    }
    return true;
  }

  // Enter, Shift+Enter, Backspace and Ctrl+B, I or K, typed in `on.el`.
  // `on` is the editor's own part:
  //   format(name)  Bold, Italic or Link;
  //   inside        Enter starts a paragraph inside the element (a quotation);
  //   split(pieces) adds a section below holding `pieces`, what followed the
  //                 caret, and returns its element, or null;
  //   joins         Backspace at the very start may join the section above;
  //   above()       that section, where it can take the words, else null;
  //   join(above)   drops the section typed in, once `above` holds its words.
  function keyed(event, doc, on) {
    const selection = doc.getSelection();
    const key = event.key.toLowerCase();
    if ((event.ctrlKey || event.metaKey) && ["b", "i", "k"].includes(key)) {
      event.preventDefault();
      on.format({b: "bold", i: "italic", k: "link"}[key]);
      return;
    }
    if (event.key === "Enter" && (event.shiftKey || on.inside)) {
      event.preventDefault();
      doc.execCommand(event.shiftKey ? "insertLineBreak" : "insertParagraph");
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (!selection.rangeCount) return;
      const range = selection.getRangeAt(0);
      range.deleteContents();
      const rest = doc.createRange();
      rest.setStart(range.startContainer, range.startOffset);
      rest.setEnd(on.el, on.el.childNodes.length);
      // An emptied Bold or Italic the split leaves behind is not carried.
      const pieces = [...rest.extractContents().childNodes]
        .filter((part) => part.textContent !== "" || part.nodeName === "BR");
      const added = on.split(pieces);
      if (added) selection.collapse(added, 0);
      return;
    }
    if (event.key === "Backspace" && on.joins && selection.isCollapsed
        && selection.rangeCount) {
      const head = doc.createRange();
      head.setStart(on.el, 0);
      head.setEnd(selection.anchorNode, selection.anchorOffset);
      if (head.toString() !== "" || head.cloneContents().querySelector("br, img")) return;
      // With nothing above to take the words, the key does what it would.
      const above = on.above();
      if (!above) return;
      event.preventDefault();
      const joined = above.el.childNodes.length;
      above.el.append(...on.el.childNodes);
      on.join(above);
      selection.collapse(above.el, joined);
    }
  }
  return {text, allowed, inline, paste, format, keyed};
})();
"""
