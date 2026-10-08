"""Every word Pressless shows, in one table (PRESS-0242).

English is the only table. Each word is looked up when it is shown, so a
second table put in front of it with `use` changes every screen at once --
the hook PRESS-0241's language choice takes. A key is a dotted name grouped
by screen, never the English words, so rewording English changes no key.

A word a page script reads lives under `script.`, once, and Python reads
that same key where it shows the word too. An entry holds words and the
markup its sentence needs, never a page's template, and names its gaps as
`{slot}`; a literal brace is written `{{`.

Two families come from their own sources: `country.<code>` from
`_flag_data.NAMES`, which scripts/make_flags.py goes on generating, and
`mark.<name>` and `mark.<name>.example` from `marks.MARKS`, whose `example`
stays the parse fixture. This module touches no disk and no network, and
imports only the standard library and those two modules.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator

from pressless import _flag_data, marks

_WORDS: dict[str, str] = {
    # A failure's three parts (face.SENTENCES, with the parts that add to it):
    # failure.<module>.<Class>.what / .next / .link.
    "failure.again": (
        "Try again. If it keeps happening, send the details below to whoever helps you."
    ),
    "failure.paths.NotPackaged.what": "Pressless could not tell where it is running from.",
    "failure.paths.NotPackaged.next": "Start Pressless by double-clicking the file you downloaded.",
    "failure.paths.FolderUnusable.what": (
        "Pressless could not create or write its Pressless-data folder."
    ),
    "failure.paths.FolderUnusable.next": (
        "Move Pressless to a folder you can save files in, then start it again."
    ),
    "failure.store.StoreError.what": "Pressless could not use one of your files.",
    "failure.store.EntryNotFound.what": "Pressless could not find that entry.",
    "failure.store.EntryNotFound.next": "Go back to your list of entries and choose it again.",
    "failure.store.SlugInUse.what": (
        "Another entry already uses that address, so nothing was moved."
    ),
    "failure.store.SlugInUse.next": "Choose a different address and save again.",
    "failure.store.DanglingReply.what": (
        "A reply points at a comment that is not there, so nothing was saved."
    ),
    "failure.store.DanglingReply.next": "Send the details below to whoever helps you.",
    "failure.builder.BuildStopped.what": (
        "Pressless could not build your site from one of your files."
    ),
    "failure.builder.BuildStopped.next": (
        "Check the file named in the details below, then try again. If it keeps happening, "
        "send the details to whoever helps you."
    ),
    "failure.builder.SiteFolderUnusable.what": (
        "Pressless could not write the folder your site is built into."
    ),
    "failure.insights.InsightsError.what": "Google sent back an answer Pressless could not use.",
    "failure.insights.InsightsError.next": (
        "Try again later. If it keeps happening, send the details below to whoever helps you."
    ),
    "failure.insights.NotConfigured.what": "The visitor numbers are not set up.",
    "failure.insights.NotConfigured.next": (
        "Set up the dashboard in Settings if you want to see them."
    ),
    "failure.insights.Unreachable.what": "Pressless could not reach Google.",
    "failure.insights.Unreachable.next": "Check your internet connection and try again.",
    "failure.insights.Refused.what": "Google would not let Pressless read your visitor numbers.",
    "failure.insights.Refused.next": "Sign in to Google again from Settings.",
    "failure.insights.RateLimited.what": "Google asked Pressless to wait before asking again.",
    "failure.insights.RateLimited.next": "Try again later.",
    "failure.google_signin.Declined.what": (
        "You chose not to let Pressless read your visitor numbers."
    ),
    "failure.google_signin.Declined.next": "Sign in with Google from Settings whenever you like.",
    "failure.google_signin.Expired.what": "The sign-in with Google took too long.",
    "failure.google_signin.Expired.next": "Sign in with Google again from Settings.",
    "failure.credentials.NoStore.what": (
        "Pressless found nowhere safe on this computer to keep {secret}."
    ),
    "failure.credentials.NoStore.next": "Send the details below to whoever helps you.",
    "failure.credentials.NotStored.what": "Pressless does not have {secret} yet.",
    "failure.credentials.NotStored.next": "Enter it again in Settings.",
    "failure.credentials.CredentialError.what": (
        "Pressless could not safely reach {secret} in this computer's keyring."
    ),
    "failure.credentials.CredentialError.next": (
        "If your keyring is locked, unlock it and try again; otherwise enter it again in "
        "Settings. If this keeps happening, send the details below to whoever helps you."
    ),
    "failure.settings.NotSetUp.what": "Pressless is not set up yet.",
    "failure.settings.NotSetUp.next": "Go through setup first.",
    "failure.settings.SettingsError.what": "Pressless could not read its settings.",
    "failure.settings.SettingsError.next": (
        "Pressless changed nothing in them. Send the details below to whoever helps you."
    ),
    "failure.publisher.PublishError.what": "GitHub answered in a way Pressless did not expect.",
    "failure.publisher.Unreachable.what": "Pressless could not reach GitHub.",
    "failure.publisher.Unreachable.next": "Check your internet connection and try again.",
    "failure.publisher.OutcomeUnknown.what": (
        "GitHub's answer did not say whether your site was updated."
    ),
    "failure.publisher.OutcomeUnknown.next": (
        "Check your internet connection and click Press to site again. Publishing again is "
        "safe and settles it."
    ),
    "failure.publisher.Refused.what": "GitHub would not accept your publishing key.",
    "failure.publisher.Refused.next": (
        "Enter your publishing key again in Settings, then try again."
    ),
    "failure.publisher.SignInRefused.what": "GitHub would not accept Pressless's sign-in.",
    "failure.publisher.SignInRefused.next": "Sign in to GitHub again in Settings, then try again.",
    "failure.publisher.SignInRefused.link": "Sign in to GitHub again",
    "failure.publisher.RepositoryMissing.what": "GitHub could not find your site's repository.",
    "failure.publisher.RepositoryMissing.next": (
        "Check the repository name in Settings, then click Press to site again."
    ),
    "failure.publisher.Conflict.what": (
        "Your site on GitHub changed while Pressless was publishing."
    ),
    "failure.publisher.Conflict.next": "Try again.",
    "failure.publisher.TooLarge.what": (
        "Something you are publishing is larger than GitHub accepts."
    ),
    "failure.publisher.TooLarge.next": (
        "If you added a large file, remove or shrink it. Then try again, and if it keeps "
        "happening, send the details below to whoever helps you."
    ),
    "failure.publisher.RateLimited.what": "GitHub asked Pressless to slow down.",
    "failure.publisher.RateLimited.next": "Wait a while, then try again.",
    "failure.publisher.NoPreviousState.what": (
        "There is no earlier version of your site to go back to."
    ),
    "failure.publisher.NoPreviousState.next": "Nothing needs undoing.",
    "failure.publisher.SiteFolderMissing.what": (
        "Pressless could not find the folder your site is built into."
    ),
    "failure.publisher.SiteFolderMissing.next": (
        "Build your site again, then click Press to site again. If it keeps happening, send "
        "the details below to whoever helps you."
    ),
    "failure.publisher.StrayFile.what": "Your site folder holds a file Pressless did not make.",
    "failure.publisher.StrayFile.next": (
        "Remove that file from your site folder, then click Press to site again."
    ),
    "failure.publisher.SiteWouldBeEmptied.what": (
        "Publishing now would empty your site, so Pressless stopped."
    ),
    "failure.publisher.SiteWouldBeEmptied.next": (
        "Build your site again, then click Press to site again."
    ),
    "failure.publisher.FetchNotWritten.what": (
        "Pressless could not save the earlier version of your site to this computer."
    ),
    "failure.publisher.FetchNotWritten.next": (
        "Free some space on this computer's drive, then try again."
    ),
    "failure.publisher.UnfetchablePath.what": (
        "The earlier version of your site names a file this computer cannot hold."
    ),
    "failure.publisher.UnfetchablePath.next": (
        "Rename the file named below on your site, publish, then try again."
    ),
    "failure.publisher.RepositoryMoved.what": (
        "GitHub says your site's repository has been renamed or moved."
    ),
    "failure.publisher.RepositoryMoved.next": (
        "Enter its new name in Settings, then click Press to site again."
    ),
    "failure.publisher.RemoteStateMissing.what": (
        "Something Pressless needed from GitHub was not there."
    ),
    "failure.publisher.RemoteStateMissing.next": "Try again.",
    "failure.github_signin.Pending.what": "GitHub has not heard from you yet.",
    "failure.github_signin.Pending.next": (
        "Type the code on GitHub's page, click Authorize, then try again."
    ),
    "failure.github_signin.Expired.what": "The code for signing in to GitHub ran out.",
    "failure.github_signin.Expired.next": "Sign in to GitHub again from Settings.",
    "failure.github_signin.Declined.what": "The sign-in was cancelled on GitHub.",
    "failure.github_signin.Declined.next": (
        "Sign in to GitHub again from Settings whenever you like."
    ),
    "failure.github_signin.SignedOut.what": "GitHub has signed Pressless out.",
    "failure.github_signin.SignedOut.next": "Sign in to GitHub again in Settings, then try again.",
    "failure.github_signin.SignedOut.link": "Sign in to GitHub again",
    "failure.face.FolderNotOpened.what": "Pressless could not open the folder.",
    "failure.face.FolderNotOpened.next": (
        "Use Copy location instead, and paste it into your file manager."
    ),
    "failure.shortcuts.ShortcutError.what": (
        "Pressless could not change its shortcut in the menu or on the desktop."
    ),
    "failure.publishing.NothingToPublish.what": (
        "Publishing now would leave your site with no entries, so Pressless stopped."
    ),
    "failure.publishing.NothingToPublish.next": "Send the details below to whoever helps you.",
    "failure.publishing.JournalOff.what": (
        "Your journal is off, so entries are not on your site. This entry is still saved as a "
        "draft."
    ),
    "failure.publishing.JournalOff.next": (
        "Turn the journal on from Your writing, then publish this entry again."
    ),
    "failure.publishing.WouldReplaceASite.what": (
        "Your GitHub repository already holds a website, and publishing your starter site "
        "would replace it, so Pressless stopped."
    ),
    "failure.publishing.WouldReplaceASite.next": (
        "If you mean to replace it, choose Replace the site on GitHub below, then publish "
        "again."
    ),
    "failure.editor.ChangedElsewhere.what": (
        "This entry was changed in another window or outside Pressless, so Pressless did not "
        "save over it."
    ),
    "failure.editor.ChangedElsewhere.next": (
        "Copy anything you typed since, then open the entry again from your list."
    ),
    "failure.editor.TooManyCopies.what": (
        "More than one draft holds unpublished changes to this entry, so Pressless did not "
        "open it."
    ),
    "failure.editor.TooManyCopies.next": (
        "Open your Pressless-data folder, keep one of those drafts, and move the others out of "
        "the drafts folder."
    ),
    "failure.photographs.NotAPhotograph.what": (
        "That file is not a picture Pressless can put on your site, so it was not added."
    ),
    "failure.photographs.NotAPhotograph.next": "Choose a JPEG, PNG, WebP or GIF photograph.",
    "failure.page_editor.PiecesChanged.what": (
        "Not saved: the paragraph count no longer matches your page."
    ),
    "failure.page_editor.PiecesChanged.next": "Put it back, or use Show me the code.",
    "failure.undo.NothingToUndo.what": "Pressless cannot undo your very first publish.",
    "failure.undo.NothingToUndo.next": "There is no earlier version of your site to go back to.",
    "failure.installer.UpdateError.what": "Pressless could not update itself.",
    "failure.installer.UpdateError.next": "Keep using this version, and try again later.",
    "failure.updater.DownloadFailed.what": "Pressless could not download the new version.",
    "failure.updater.DownloadFailed.next": (
        "Check your internet connection and click Update now again."
    ),
    "failure.updater.DiskFull.what": (
        "There is not enough room on this computer to download the new version."
    ),
    "failure.updater.DiskFull.next": (
        "Free some space on this computer, then click Update now again."
    ),
    "failure.updater.DownloadEndedEarly.what": "The download stopped before it finished.",
    "failure.updater.DownloadEndedEarly.next": "Click Update now again.",
    "failure.updater.UpdateRejected.what": (
        "The download did not prove it came from Pressless, so nothing was installed."
    ),
    "failure.updater.UpdateRejected.next": (
        "Keep using this version, and send the details below to whoever helps you."
    ),
    "failure.installer.InstallFailed.what": (
        "Pressless could not put the new version in place. This version is still installed."
    ),
    "failure.installer.InstallFailed.next": (
        "Try again later. If it keeps happening, send the details below to whoever helps you."
    ),
    # A failure no entry above names (face.sentence_for).
    "failure.unforeseen.what": "Something went wrong that Pressless did not expect.",
    "failure.unforeseen.next": "Try again, and send the details below to whoever helps you.",
    # What a credential sentence says where the Face named no secret.
    "failure.unnamed_secret": "that secret",
    # Every failure's Show details.
    "failure.show_details": "Show details",
    "failure.log": (
        "The log is {log}, and the older part of it {old}, in the Pressless-data folder, "
        "beside the program."
    ),
    "failure.copy_location": "Copy location",
    "failure.open_folder": "Open folder",
    # A notice's next step, and what a failure or notice means for the site.
    "notice.next": "Nothing was lost. Send this to whoever helps you if you did not expect it.",
    "site.unchanged": "Your site has not changed.",
    "site.unknown": "Pressless cannot tell whether your site changed.",
    "site.updated": "Your site has been updated.",
    # The Face's frame, on every screen.
    "face.running": "Pressless is running.",
    "face.view_site": "View your site",
    "face.settings": "Settings",
    "face.report": "Suggest or report a problem",
}

def _literal(text: str) -> str:
    """`text` as an entry with no gaps: a mark's own syntax uses braces."""
    return text.replace("{", "{{").replace("}", "}}")


ENGLISH: dict[str, str] = {
    **_WORDS,
    **{f"country.{code}": _literal(name) for code, name in _flag_data.NAMES.items()},
    **{f"mark.{row.name}": _literal(row.explains) for row in marks.MARKS},
    **{f"mark.{row.name}.example": _literal(row.example) for row in marks.MARKS},
}

# The table in front of ENGLISH, for the whole process: every server thread
# reads the same one (spec § 4.1).
_in_use: dict[str, str] = {}


def _words(key: str) -> str:
    found = _in_use.get(key)
    return found if found is not None else ENGLISH[key]


def say(key: str, **slots: str) -> str:
    """The words for `key` in the table in use, gaps filled.

    A key the table in use lacks takes ENGLISH's words. A key ENGLISH lacks,
    or a gap left unfilled, raises KeyError. Slot values go in as given:
    each caller escapes what it passes.
    """
    return _words(key).format_map(slots)


@contextlib.contextmanager
def use(table: dict[str, str]) -> Iterator[None]:
    """Put `table` in front of ENGLISH for the whole process while the block
    runs."""
    global _in_use
    before = _in_use
    _in_use = dict(table)
    try:
        yield
    finally:
        _in_use = before


def for_scripts() -> str:
    """Every `script.` entry, gaps unfilled, as a JSON object safe inside
    <script>. The page's own `say` fills the gaps."""
    chosen = {key: _words(key) for key in ENGLISH if key.startswith("script.")}
    return json.dumps(chosen).replace("</", "<\\/")
