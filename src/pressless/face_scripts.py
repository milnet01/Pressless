"""The Face's page scripts, as Python string constants (PRESS-0468).

They change when a page's behaviour does; face.py changes when a request's
handling does, so they live apart. `SCRIPT` is every page's own script, `SAY`
its words lookup, `FILE_SCRIPT` the file box's. face.py serves them unchanged.
"""

# Every Face page's own script: the failure's buttons, the theme and size
# pickers, More, help, message boxes and the true-colours switch. It lives in
# the page, never in a fragment, and it asks for the folder's path only when
# Copy is clicked, so the path is never in the document. It declares nothing
# at the top level, because a page written over this one by document.write
# runs it again in the same window, where a second `const` would throw.
SCRIPT = """
(() => {
// PRESS-0434: a press says at once that Pressless is working, on every
// screen (user, 2026-11-21). A form a script sends itself is left to it, as
// is anything marked data-quiet. The note is fixed, so nothing on the page
// moves; the button goes off after the submit, once the form has read it.
// PRESS-0435: the note also holds a bar and a count line, both there from the
// start so the note keeps its size, and asks GET /progress each second while
// it is up. A form's page keeps running until its reply arrives, so the count
// fills in during the wait.
// The browser's own fetch, kept once per window so a second run does not
// wrap the first run's wrapper.
const sendFetch = window.presslessSendFetch ??= window.fetch.bind(window);
let askingProgress = false, downloading = false;
async function askProgress() {
  if (askingProgress) return;
  askingProgress = true;
  let missed = 0, idle = 0;
  while (missed < 5) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    const note = document.getElementById("working-note");
    if (!note) break;
    let now;
    try { now = await (await sendFetch("/progress")).json(); } catch (error) {
      missed += 1;
      continue;
    }
    missed = 0;
    // A download's page stays, so the note goes once nothing has run for
    // two asks running (PRESS-0464).
    idle = now.running ? 0 : idle + 1;
    if (downloading && idle >= 2) {
      downloading = false;
      note.remove();
      break;
    }
    if (!now.running || !now.said) continue;
    note.querySelector(".count").textContent = now.said;
    if (now.fraction !== null) note.querySelector("progress").value = now.fraction;
  }
  askingProgress = false;
}
function showWorking(key) {
  let note = document.getElementById("working-note");
  if (!note) {
    note = document.createElement("div");
    note.id = "working-note";
    note.setAttribute("role", "status");
    const words = document.createElement("p");
    const bar = document.createElement("progress");
    const count = document.createElement("p");
    count.className = "count";
    note.append(words, bar, count);
    document.body.append(note);
  }
  note.querySelector("p").textContent = say(key);
  askProgress();
}
window.presslessWorking = showWorking;
// A POST a page's own script sends shows the note too, once it has run for
// more than a moment, and takes it down when the last such POST is answered.
let sending = 0, submitted = false;
window.fetch = (resource, options = {}) => {
  const method = (options.method || resource.method || "GET").toUpperCase();
  if (method !== "POST") return sendFetch(resource, options);
  sending += 1;
  const timer = setTimeout(() => showWorking("script.working"), 600);
  const settled = () => {
    clearTimeout(timer);
    sending -= 1;
    if (!sending && !submitted) document.getElementById("working-note")?.remove();
  };
  const sent = sendFetch(resource, options);
  sent.then(settled, settled);
  return sent;
};
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (event.defaultPrevented || form.target || form.closest("[data-quiet]")) return;
  submitted = true;
  showWorking("script.working");
  const pressed = event.submitter;
  if (pressed) setTimeout(() => { pressed.disabled = true; pressed.dataset.working = ""; });
});
// A download link says so at once: Pressless packs the file before the
// browser shows the download (PRESS-0464).
document.addEventListener("click", (event) => {
  const link = event.target.closest("a[href][download]");
  if (!link || event.defaultPrevented || event.button !== 0
      || link.closest("[data-quiet]")) return;
  downloading = true;
  showWorking("script.working");
});
// A link to a screen that takes a moment says so too, after a short wait,
// so a quick screen never flashes it.
document.addEventListener("click", (event) => {
  const link = event.target.closest("a[href]");
  if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey
      || event.metaKey || event.shiftKey || event.altKey || link.target
      || link.hasAttribute("download") || link.closest("[data-quiet]")) return;
  const to = new URL(link.href, location.href);
  if (to.origin !== location.origin || (to.pathname === location.pathname
      && to.search === location.search)) return;
  setTimeout(() => showWorking("script.opening"), 600);
});
// Back to a page the browser kept: it is not working any more.
window.addEventListener("pageshow", (event) => {
  if (!event.persisted) return;
  submitted = false;
  document.getElementById("working-note")?.remove();
  document.querySelectorAll("[data-working]").forEach((button) => {
    button.disabled = false;
    delete button.dataset.working;
  });
});
document.addEventListener("click", (event) => {
  const view = event.target.closest("button[data-view-site]");
  if (view) window.open(view.dataset.viewSite, "_blank", "noopener");
});
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  if (button.dataset.action === "copy-location") {
    const answer = await fetch("/folder/location");
    if (answer.ok) await navigator.clipboard.writeText(await answer.text());
  } else if (button.dataset.action === "open-folder") {
    const answer = await fetch("/folder/open", {method: "POST"});
    if (!answer.ok) {
      // The answer is a Face page saying it could not open the folder.
      document.open(); document.write(await answer.text()); document.close();
    }
  }
});
// PRESS-0436: Send my log opens its box; only Send in the box posts. The
// answer, the reference or the failure, takes the box's words. Once sent,
// Send is hidden, keeping its place, and Not now reads OK; after a failure
// Send stays, to try again, and the failure's own Send my log is dropped.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action^='send-log']");
  if (!button) return;
  const box = button.closest("div.send-log").querySelector("dialog");
  if (button.dataset.action === "send-log") { box.showModal(); return; }
  button.disabled = true;
  const words = box.querySelector(".said");
  let said = null;
  try { said = await (await fetch("/log/send", {method: "POST"})).text(); } catch (error) {
    // Pressless itself did not answer; Send stays, to try again.
  }
  if (said === null) {
    words.textContent = say("script.sendlog.unreachable");
    button.disabled = false;
    return;
  }
  words.innerHTML = said;
  if (words.querySelector(".failure")) {
    words.querySelectorAll("div.send-log").forEach((inner) => inner.remove());
    button.disabled = false;
    return;
  }
  button.style.visibility = "hidden";
  box.querySelector("button[data-close]").textContent = say("script.message.ok");
});
// PRESS-0190: a theme is applied the moment it is picked, then remembered.
document.addEventListener("change", (event) => {
  const picker = event.target.closest("select[data-theme-picker]");
  if (!picker) return;
  if (picker.value === "follow") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = picker.value;
  fetch("/theme", {method: "POST", body: picker.value});
});
// PRESS-0343: More shuts on a click outside it, or on Escape.
document.addEventListener("click", (event) => {
  document.querySelectorAll("details.more[open]").forEach((more) => {
    if (!more.contains(event.target)) more.open = false;
  });
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  document.querySelectorAll("details.more[open]").forEach((more) => {
    more.open = false;
    more.querySelector("summary").focus();
  });
});
// PRESS-0338: a text size, like a theme, is applied the moment it is picked,
// then remembered.
document.addEventListener("change", (event) => {
  const picker = event.target.closest("select[data-size-picker]");
  if (!picker) return;
  if (picker.value === picker.dataset.noZoom) delete document.documentElement.dataset.size;
  else document.documentElement.dataset.size = picker.value;
  fetch("/text-size", {method: "POST", body: picker.value});
});
// PRESS-0241 § 4.3: a language is kept, then the page reloads in it. From
// the top bar's picker, or from the list offered where it cannot be told.
async function chooseLanguage(code) {
  const answer = await fetch("/language", {method: "POST", body: code});
  if (answer.ok) location.reload();
}
document.addEventListener("change", (event) => {
  const picker = event.target.closest("select[data-language-picker]");
  if (picker) chooseLanguage(picker.value);
});
document.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-language]");
  if (button) chooseLanguage(button.dataset.language);
});
// PRESS-0228: a "?" beside a box opens its help; Close or Escape shuts it.
document.addEventListener("click", (event) => {
  const opener = event.target.closest("button[data-help]");
  if (opener) document.getElementById(opener.dataset.help).showModal();
  const closer = event.target.closest("button[data-close]");
  if (!closer) return;
  closer.closest("dialog").close();
});
// PRESS-0236: a message box opens when its words change, so nothing beside a
// control moves. A save writing the same words again leaves it shut; words
// cleared away close it. Closing returns to the field it is about.
for (const box of document.querySelectorAll("dialog.message")) {
  const words = box.firstElementChild;
  let shown = "";
  const look = () => {
    const now = words.innerHTML.trim();
    if (now === shown) return;
    shown = now;
    if (!now) { if (box.open) box.close(); }
    else if (!box.open) box.showModal();
  };
  new MutationObserver(look).observe(words,
    {childList: true, subtree: true, characterData: true});
  look();
  box.addEventListener("close", () => {
    // PRESS-0235 § 4.5: shutting a press's failure box forgets the outcome, or
    // the box reopens on every page. Here and not on OK's click, so Escape
    // forgets too (PRESS-0358). Words cleared away were forgotten already.
    if (shown && box.querySelector("button[data-forget]")) {
      fetch("/press/forget", {method: "POST"});
    }
    const field = box.dataset.focus &&
      document.querySelector(`[name="${CSS.escape(box.dataset.focus)}"]`);
    if (field) field.focus();
  });
}
// PRESS-0187: a dark look dims the preview; this switch shows its true colours.
// PRESS-0263: it starts as he last left it, and each change is remembered.
for (const box of document.querySelectorAll("input[data-true-colours]:checked")) {
  document.getElementById("preview").classList.add("undimmed");
}
document.addEventListener("change", (event) => {
  const box = event.target.closest("input[data-true-colours]");
  if (!box) return;
  document.getElementById("preview").classList.toggle("undimmed", box.checked);
  fetch("/true-colours", {method: "POST", body: box.checked ? "1" : "0"});
});
// PRESS-0428 § 4.4: every page asks who is answering, which tells a
// restarted Pressless that this tab came back. The page that asked for the
// restart goes home once another Face answers; any other page stays, so
// nothing typed is lost. One loop per window.
if (!window.presslessAsksAlive) {
  window.presslessAsksAlive = true;
  const asked = document.querySelector("[data-after-restart]");
  const askAlive = async () => {
    try {
      const now = await (await sendFetch("/alive")).json();
      if (asked && now.face !== asked.dataset.face) {
        location.replace(asked.dataset.afterRestart);
        return;
      }
    } catch (error) {
      // Stopped or restarting: ask again.
    }
    setTimeout(askAlive, 2000);
  };
  setTimeout(askAlive, 2000);
}
})();
"""

# PRESS-0242 § 4.3: a page script's words. It fills `{name}` gaps and turns
# `{{` and `}}` into braces, as words.say does, and nothing more: a lone brace
# stays as written here where say raises, and say's `{name:spec}` forms are
# not filled. It reads the words block on each call and declares nothing
# else, because a failure page written over this one by document.write runs
# it a second time.
SAY = r"""
function say(key, slots = {}) {
  const table = JSON.parse(document.getElementById("pressless-words").textContent);
  if (!(key in table)) throw new Error("no words for " + key);
  return table[key].replace(/\{\{|\}\}|\{(\w+)\}/g, (found, name) => {
    if (found === "{{") return "{";
    if (found === "}}") return "}";
    if (!(name in slots)) throw new Error("no " + name + " for " + key);
    return slots[name];
  });
}
"""

# Each file box on the page is wired once, however many copies of this run.
# A folder is packed as a ZIP with its files stored, not compressed: each file
# is read once for its checksum, and the ZIP refers to the files rather than
# holding a copy. A plain ZIP cannot reach past 4 GiB or hold more than
# 65,535 files; a folder past either is not sent.
FILE_SCRIPT = r"""
(() => {
  const table = new Uint32Array(256).map((_, n) => {
    for (let k = 0; k < 8; k++) n = n & 1 ? 0xEDB88320 ^ (n >>> 1) : n >>> 1;
    return n >>> 0;
  });
  const checksum = async (file) => {
    let crc = 0xFFFFFFFF;
    const reader = file.stream().getReader();
    for (;;) {
      const {done, value} = await reader.read();
      if (done) return (crc ^ 0xFFFFFFFF) >>> 0;
      for (const byte of value) crc = table[(crc ^ byte) & 0xFF] ^ (crc >>> 8);
    }
  };
  // One ZIP header: a file's local one, or, given where that sits, its entry
  // in the central directory. Names are UTF-8 (flag 0x0800); dates 1980-01-01.
  const header = (name, crc, size, at = null) => {
    const central = at !== null;
    const fixed = central ? 46 : 30;
    const out = new Uint8Array(fixed + name.length);
    const view = new DataView(out.buffer);
    let i = 0;
    const u16 = (value) => { view.setUint16(i, value, true); i += 2; };
    const u32 = (value) => { view.setUint32(i, value, true); i += 4; };
    u32(central ? 0x02014B50 : 0x04034B50);
    if (central) u16(20);
    u16(20); u16(0x0800); u16(0); u16(0); u16(0x21);
    u32(crc); u32(size); u32(size); u16(name.length); u16(0);
    if (central) { u16(0); u16(0); u16(0); u32(0); u32(at); }
    out.set(name, fixed);
    return out;
  };
  // The folder as one ZIP, or null where a plain ZIP cannot hold it.
  const zipped = async (files) => {
    const encoder = new TextEncoder();
    const names = Array.from(files, (file) =>
      encoder.encode(file.webkitRelativePath || file.name));
    let total = 22;
    names.forEach((name, n) => { total += 76 + 2 * name.length + files[n].size; });
    if (files.length > 0xFFFF || total > 0xFFFFFFFF) return null;
    const parts = [], directory = [];
    let offset = 0;
    for (let n = 0; n < files.length; n++) {
      const crc = await checksum(files[n]);
      const local = header(names[n], crc, files[n].size);
      parts.push(local, files[n]);
      directory.push(header(names[n], crc, files[n].size, offset));
      offset += local.length + files[n].size;
    }
    const end = new DataView(new ArrayBuffer(22));
    const size = directory.reduce((sum, entry) => sum + entry.length, 0);
    end.setUint32(0, 0x06054B50, true);
    end.setUint16(8, files.length, true);
    end.setUint16(10, files.length, true);
    end.setUint32(12, size, true);
    end.setUint32(16, offset, true);
    return new Blob([...parts, ...directory, end.buffer]);
  };
  for (const button of document.querySelectorAll("button[data-file]")) {
    if (button.dataset.wired) continue;
    button.dataset.wired = "1";
    const chooser = document.getElementById(button.dataset.file);
    const label = button.textContent;
    const giveBack = (key) => {
      button.disabled = false;
      button.textContent = label;
      document.getElementById(button.dataset.file + "-message").textContent = say(key);
    };
    button.addEventListener("click", () => { chooser.value = ""; chooser.click(); });
    chooser.addEventListener("change", async () => {
      if (!chooser.files.length) return;
      button.disabled = true;
      if (button.dataset.sending) button.textContent = say(button.dataset.sending);
      let body = chooser.files[0], page;
      if ("folder" in chooser.dataset) {
        try {
          body = await zipped(chooser.files);
        } catch (error) {
          return giveBack("script.file_box.unreadable");
        }
        if (!body) return giveBack("script.file_box.too_large");
      }
      try {
        const answer = await fetch(chooser.dataset.to, {method: "POST", body});
        page = await answer.text();
      } catch (error) {
        return giveBack("script.file_box.unreachable");
      }
      document.open();
      document.write(page);
      document.close();
    });
  }
})();
"""
