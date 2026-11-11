"""The AI helper's tools, as data (PRESS-0337 § 4.5,
docs/specs/PRESS-0337-ai-assistant.md).

Each tool's name, what it is for, and the arguments it takes, as a JSON
schema. The bridge lists them to an AI app and checks a call's name against
them; the door does each one's work. Pure: no disk, no network, and no other
Pressless module, so the bridge loads nothing it does not need.

Names are stable once released. A later release may add a tool or an
optional argument, never rename or remove one, nor make an argument required.
"""
from __future__ import annotations

from dataclasses import dataclass, field

READ, WRITE, ASK = "read", "write", "ask"

# dashboard.WINDOWS' spans, written out so this module imports nothing; a test
# checks they match.
INSIGHTS_DAYS = (7, 28, 365)

_TEXT = {"type": "string"}
_NAMES = {"type": "array", "items": {"type": "string"}}
_VERSION = {"type": "string", "description": "The version the last read of it returned."}
_ADDRESS = {"type": "string", "description": "The entry's address, as list_entries gives it."}
_PAGE = {"type": "string", "description": "The page's name, or header, footer or navigation."}


@dataclass(frozen=True)
class Tool:
    name: str
    kind: str                       # READ, WRITE or ASK
    description: str
    arguments: dict[str, dict] = field(default_factory=dict)   # name -> JSON schema
    required: tuple[str, ...] = ()

    def schema(self) -> dict:
        """The tool's input schema, as MCP's tools/list carries it."""
        return {"type": "object", "properties": self.arguments,
                "required": list(self.required), "additionalProperties": False}


_ASKS = (" Nothing changes yet: this asks the writer, who answers yes or not yet in "
         "Pressless's own window. It answers a request id at once; ask request_status "
         "later.")

TOOLS: tuple[Tool, ...] = (
    # ------------------------------------------------------------ reads ---
    Tool("site_overview", READ,
         "What the open site is: its address, whether it has a journal, how many "
         "entries and pages it holds, whether a publish is running, and any request "
         "waiting for the writer."),
    Tool("writing_guide", READ,
         "How an entry's body is written: each mark Pressless reads, an example of it, "
         "and what it does."),
    Tool("list_entries", READ,
         "Every entry: its address, title, date, whether it is a draft, and whether "
         "it has changes not yet published."),
    Tool("read_entry", READ,
         "One entry: title, date, categories, tags and its body in marks, with the "
         "version a change must name. A published entry with changes waiting reads "
         "as those changes.",
         {"address": _ADDRESS}, ("address",)),
    Tool("list_pages", READ,
         "Every page, and the site's header, footer and navigation, each saying "
         "whether it has changes not yet published."),
    Tool("read_page", READ,
         "One page's sections in order, or the navigation's links, with the version a "
         "change must name. A script, style or code section shows its kind and "
         "locked: it must be kept as it is.",
         {"name": _PAGE}, ("name",)),
    Tool("list_files", READ,
         "Every photograph and file the site keeps, and the pages that use each."),
    Tool("read_look", READ,
         "The site's look: layout, colours, fonts, text size, width and effects, "
         "with the version a change must name."),
    Tool("read_insights", READ,
         "How many people read the site, from where, and which pages, over the last "
         "7, 28 or 365 days.",
         {"days": {"type": "integer", "enum": list(INSIGHTS_DAYS)}}),
    Tool("request_status", READ,
         "Where a request stands: waiting, refused, expired, running, done, failed "
         "or unknown, with what happened.",
         {"request": _TEXT}, ("request",)),
    # ----------------------------------------------------------- writes ---
    Tool("new_entry", WRITE,
         "Start a draft entry. Nothing is published.",
         {"title": _TEXT, "template": _TEXT}, ("title",)),
    Tool("save_entry", WRITE,
         "Change an entry's title, body (in marks), categories or tags. A published "
         "entry's changes wait as a copy until it is published.",
         {"address": _ADDRESS, "version": _VERSION, "title": _TEXT, "body": _TEXT,
          "categories": _NAMES, "tags": _NAMES}, ("address", "version")),
    Tool("change_entry_address", WRITE,
         "Give an entry a new address. A published entry's old address forwards to "
         "the new one once it is published.",
         {"address": _ADDRESS, "version": _VERSION, "to": _TEXT},
         ("address", "version", "to")),
    Tool("new_page", WRITE,
         "Start a new page. It waits until it is published.",
         {"name": _TEXT}, ("name",)),
    Tool("save_page", WRITE,
         "Change a page's sections, or the navigation's links. List every section to "
         "keep as {\"keep\": path} and give a changed or new one as {kind, fields, "
         "parts}; a section left out is removed. A locked section must be kept, in "
         "its place. The change waits until it is published.",
         {"name": _PAGE, "version": _VERSION,
          "sections": {"type": "array", "items": {"type": "object"}},
          "links": {"type": "array", "items": {"type": "object"}}},
         ("name", "version")),
    Tool("add_photograph", WRITE,
         "Keep a photograph so an entry or page can show it. Answers its name and the "
         "address a page names it by.",
         {"filename": _TEXT, "data": {"type": "string", "description": "The file, base64."}},
         ("filename", "data")),
    Tool("add_file", WRITE,
         "Keep a music, video, PDF, ZIP or text file so a page can offer it.",
         {"filename": _TEXT, "data": {"type": "string", "description": "The file, base64."}},
         ("filename", "data")),
    Tool("save_look", WRITE,
         "Change the site's look, given as read_look gives it. It goes live at the "
         "next publish.",
         {"version": _VERSION, "choices": {"type": "object"}}, ("version", "choices")),
    # ------------------------------------------------------------- asks ---
    Tool("publish", ASK,
         "Publish an entry, a page, or the whole site." + _ASKS,
         {"entry": _ADDRESS, "page": _PAGE}),
    Tool("undo_last_publish", ASK,
         "Put the site back as it was before the last publish." + _ASKS),
    Tool("remove_entry", ASK,
         "Put an entry in the bin. A published one leaves the site at the next "
         "publish." + _ASKS,
         {"address": _ADDRESS, "version": _VERSION}, ("address", "version")),
    Tool("discard_changes", ASK,
         "Throw away the changes waiting on a published entry or page." + _ASKS,
         {"entry": _ADDRESS, "page": _PAGE, "version": _VERSION}, ("version",)),
    Tool("remove_page", ASK,
         "Remove a page from the site, and its link from the navigation. It goes live "
         "at once." + _ASKS,
         {"name": _PAGE}, ("name",)),
    Tool("rename_page", ASK,
         "Give a page a new name; its old address forwards to the new one. It goes "
         "live at once." + _ASKS,
         {"name": _PAGE, "to": _TEXT}, ("name", "to")),
    Tool("remove_file", ASK,
         "Put a kept photograph or file in the bin. One a page uses is refused." + _ASKS,
         {"name": _TEXT}, ("name",)),
)

BY_NAME = {tool.name: tool for tool in TOOLS}

_TYPES = {"string": str, "integer": int, "array": list, "object": dict}


def problem(name: str, arguments: object) -> str | None:
    """Why a call cannot run, in a plain sentence for the AI app; None where it
    can. Checks the name, that the arguments are an object holding every
    required one and no other, and each one's JSON type."""
    tool = BY_NAME.get(name)
    if tool is None:
        return f"there is no tool {name!r}"
    if not isinstance(arguments, dict):
        return "the arguments are not an object"
    for argument in tool.required:
        if argument not in arguments:
            return f"{name} needs {argument}"
    for argument, value in arguments.items():
        schema = tool.arguments.get(argument)
        if schema is None:
            return f"{name} takes no {argument}"
        wanted = _TYPES[schema["type"]]
        if not isinstance(value, wanted) or (wanted is int and isinstance(value, bool)):
            return f"{argument} must be {schema['type'] if wanted is not int else 'a whole number'}"
        if "enum" in schema and value not in schema["enum"]:
            return f"{argument} must be one of {schema['enum']}"
        if wanted is list and schema["items"]["type"] == "string" and not all(
                isinstance(item, str) for item in value):
            return f"{argument} must list text"
    return None
