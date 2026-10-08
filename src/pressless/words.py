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
    # Notices: a StoreNotice or SettingsNotice carries its key and slots.
    "notice.store.twin": (
        "{twin} names the same entry as {target} and is not the file Pressless reads; after "
        "this move the folder holds both, and {twin} can only be reached by renaming it"
    ),
    "notice.store.passed_over": "{file} was passed over: {reason}",
    "notice.store.not_private": (
        "{file} could not be made private: this filesystem granted mode {mode} rather than "
        "owner-only, so others with an account on this machine can read it"
    ),
    "notice.settings.not_private": (
        "the settings file could not be made private: this filesystem granted mode {mode} "
        "rather than owner-only, so others with an account on this machine can read it"
    ),
    "notice.editor.left_out.categories": (
        "“{name}” was left out of the categories: Pressless cannot make it part of "
        "a web address. Give it another name."
    ),
    "notice.editor.left_out.tags": (
        "“{name}” was left out of the tags: Pressless cannot make it part of a web "
        "address. Give it another name."
    ),
    "notice.publishing.starter_kept": (
        "Pressless could not note that your starter site is now published, so your next "
        "publish will ask once more before it replaces a site."
    ),
    # "A waiting draft", not "the draft of your changes": a copy of a demoted
    # entry bins two drafts, and a failure between them leaves the OLD one
    # (PRESS-0162).
    "notice.publishing.kept_copy": (
        "A waiting draft from this publish was left in place after publishing. You can throw "
        "it away."
    ),
    # After an unknown outcome the move stands, so the published entry already
    # holds the copy's changes and throwing the copy away loses nothing
    # (PRESS-0013 § 4.3, PRESS-0147).
    "notice.publishing.kept_copy_unknown": (
        "Pressless cannot tell whether your changes were published, and a waiting draft from "
        "this publish was left in place. You can throw it away."
    ),
    "notice.page_editor.kept_copy": (
        "Your changes were published, but their waiting copy was left in place. You can throw "
        "it away."
    ),
    # After an unknown outcome the live file already holds the changes
    # (PRESS-0014 § 4.7), so throwing the copy away loses nothing either way
    # (PRESS-0144).
    "notice.page_editor.kept_copy_unknown": (
        "Pressless cannot tell whether your changes were published, and their waiting copy "
        "was left in place. You can throw it away."
    ),
    "site.unchanged": "Your site has not changed.",
    "site.unknown": "Pressless cannot tell whether your site changed.",
    "site.updated": "Your site has been updated.",
    # The press row's lines (PRESS-0235 § 4.3): Python and the scripts read
    # these same keys.
    "script.press.publishing": "Publishing… this can take a few minutes the first time.",
    "script.press.undoing": "Putting your site back… this can take a few minutes.",
    "script.press.published": "Published. Your site shows it within a few minutes.",
    "script.press.paragraphs": (
        "Not published, because the box holds a different number of paragraphs from your "
        "page."
    ),
    "script.press.not_published": "Not published. The reason is below.",
    "script.press.undone": "Your site was put back.",
    "script.press.not_undone": "Your site was not put back. The reason is below.",
    # The Face's frame, on every screen.
    "face.running": "Pressless is running.",
    "face.view_site": "View your site",
    "face.your_writing": "Your writing",  # the way back to the list
    "face.settings": "Settings",
    "face.report": "Suggest or report a problem",
    # The editor and the list (editor.py).
    "editor.journal.on": (
        "Your journal is on: each published entry has a page of its own on your site, and "
        "your journal lists them, newest first."
    ),
    "editor.journal.on_published": (
        "Turning it off takes your published entries off your site at your next publish; "
        "turning it on again brings them back."
    ),
    "editor.journal.turn_off": "Turn the journal off",
    "editor.journal.off": (
        "Your journal is off. A journal is the dated part of a site, like a blog: each entry "
        "gets a page of its own, and the journal lists them, newest first. While it is off, "
        "your entries stay here and are not on your site. If your menu links to the journal, "
        "that link stays until you remove it from the header or navigation in Your pages."
    ),
    "editor.journal.turn_on": "Turn the journal on",
    "editor.site_line.unnamed": "Your site",
    "editor.site_line": "Editing <b>{name}</b> at {address}",
    "editor.list.pages_unreadable": "Pressless cannot open your pages folder.",
    "editor.list.changed": "changes not on your site yet",
    "editor.list.untitled": "untitled",
    "editor.list.unreadable": "Pressless cannot open this file",
    "editor.list.none": "None yet.",
    "editor.list.new": "New entry",
    "editor.list.drafts": "Drafts",
    "editor.list.on_site": "On your site",
    "editor.list.pages": "Your pages",
    "editor.list.blank": "A blank entry",
    "editor.list.start_from": "Start from",
    "editor.pages.home": "Home",
    "editor.pages.header": "Header",
    "editor.pages.footer": "Footer",
    "editor.pages.navigation": "Navigation",
    "editor.title": "Title",
    "editor.categories": "Categories",
    "editor.tags": "Tags",
    "editor.address": "Address",
    "editor.change_address": "Change address",
    "editor.press": "Press to site",
    "editor.undo": "Undo the last press",
    "editor.add_photograph": "Add a photograph",
    "editor.throw_draft": "Throw this draft away",
    "editor.proof_title": "Proof (preview)",
    "editor.bin_proof": "Bin this proof",
    "editor.standing.published": (
        "This entry is on your site. Your changes stay on this computer until you publish it."
    ),
    "editor.standing.waiting": "These changes are not on your site yet.",
    "editor.standing.draft": "A draft. It is not on your site.",
    "editor.hint.gone": "This entry is not there any more.",
    "editor.hint.proof": "A proof's address cannot be changed.",
    "editor.hint.proof_waiting": (
        "Press your changes to your site, or bin this proof, then change the address."
    ),
    "editor.hint.bad_address": "An address uses only the letters a to z, the digits 0 to 9 and -.",
    "editor.hint.taken": "Another entry already uses that address.",
    "editor.hint.forwarded": "Another entry's old address forwards from there.",
    "script.standing.on_site": "On your site",
    "script.standing.changes": "Changes not published yet",
    "script.standing.off_site": "Not on your site yet",
    "script.undo.back": "Back to your writing",
    "script.undo.unreachable": "Pressless could not reach itself. Your site was not changed.",
    "script.editor.throw_entry": "Throw this entry away",
    "script.editor.not_saved": "Not saved",
    "script.editor.missing_one": (
        "Pressless does not have this photograph: {names}. Add it with Add a photograph, or "
        "correct the name, before you press this entry to your site."
    ),
    "script.editor.missing_many": (
        "Pressless does not have these photographs: {names}. Add each with Add a photograph, "
        "or correct the name, before you press this entry to your site."
    ),
    "script.editor.saving": "Saving",
    "script.editor.saved": "Saved",
    "script.editor.adding_photograph": "Adding the photograph\u2026",
    "script.editor.photograph_added": "Added {name}.",
    "script.editor.confirm_address": (
        "Change this entry's address? It moves now in your Pressless-data folder, and on "
        "your site the next time you press to site. Links to the old address will still "
        "reach it."
    ),
    "script.editor.confirm_throw_entry": (
        "Throw this entry away? It moves to the bin in your Pressless-data folder now, and "
        "leaves your site the next time you press to site. Undo the last press can bring it "
        "back after that."
    ),
    "script.editor.confirm_throw_draft": (
        "Throw this draft away? It moves to the bin in your Pressless-data folder."
    ),
    # The fixed pages and the furniture (page_editor.py).
    "notice.page_editor.stray": (
        "The text you put between the header or footer markers will be replaced from the one "
        "Header or Footer when your site is built. Edit the Header or Footer instead."
    ),
    "page_editor.show_code": "Show me the code",
    "page_editor.show_words": "Back to the words",
    "page_editor.newest": "Your newest entry",
    "page_editor.show_on": "Show it on:",
    "page_editor.standing": "Your changes stay on this computer until you publish this page.",
    # What Undo the last press did (undo.py), one clause each.
    "undo.summary": "Your site is back the way it was: {clauses}.",
    "undo.unchanged": "Your site was already as it was before the last publish.",
    "undo.restored": "{count} put back",
    "undo.demoted_one": "{count} turned back into a draft",
    "undo.demoted_many": "{count} turned back into drafts",
    "undo.kept_one": "your own version of {count} kept as a draft",
    "undo.kept_many": "your own versions of {count} kept as drafts",
    "undo.one_entry": "1 entry",
    "undo.entries": "{count} entries",
    # Replacing a site already on GitHub (publishing.py, PRESS-0126 § 4.5).
    "publishing.replace": "Replace the site on GitHub",
    "publishing.replace.intro": (
        "Your repository, {repository}, already holds a website. Publishing your starter "
        "site replaces its pages with yours."
    ),
    "publishing.replace.confirm": "Type <strong>{repository}</strong> to confirm",
    "publishing.replace.button": "Replace it",
    "publishing.keep": (
        "Pressless leaves these alone. Untick anything of the old site that should go:"
    ),
    "publishing.keep_none": "Nothing on it is marked to be left alone.",
    "publishing.hint": "Type the repository's name exactly as it is shown above.",
    "publishing.nothing.heading": "Nothing to replace",
    "publishing.nothing": "Your site has been published already.",
    "publishing.ready.heading": "Ready to replace your site",
    "publishing.ready": (
        "Now publish again from where you were. Your starter site will replace the site in "
        "{repository}."
    ),
    # Every wizard's frame (wizard.py).
    "wizard.step": "Step {number} of {total}",
    "wizard.next": "Next",
    "wizard.back": "Back",
    "wizard.help": "Help: {label}",
    "wizard.close": "Close",
    # Signing in to GitHub (github_setup.py), and the links its page shares with Google's.
    "setup.back": "Back to Settings",
    "setup.first": "Set up Pressless first, <a href=\"/setup\">on the setup page</a>.",
    "github_setup.title": "Sign in to GitHub",
    "github_setup.unavailable": (
        "This copy of Pressless cannot sign in to GitHub. Paste a publishing key in Settings "
        "instead."
    ),
    "github_setup.how": "Pressless signs in to GitHub with a short code rather than your password.",
    "github_setup.how.1": "Press <b>Next</b>. Pressless shows a code and a link to GitHub.",
    "github_setup.how.2": "Open the link, sign in to GitHub if it asks, and type the code.",
    "github_setup.how.3": "Click <b>Authorize</b> on GitHub's page.",
    "github_setup.how.4": "Come back here and press <b>Next</b> again.",
    "github_setup.code": "Your code: <strong>{code}</strong>",
    "github_setup.type_at": "Type it at {link}",
    "github_setup.type_it": (
        "Type this code on GitHub's page, click Authorize, then press Next here."
    ),
    "github_setup.not_heard": (
        "GitHub has not heard from you yet. Type the code on GitHub's page, click Authorize, "
        "then press Next here."
    ),
    "github_setup.cancelled": "The sign-in was cancelled on GitHub. Press Next to start again.",
    # The secret a credential failure names (PRESS-0011 § 4.2).
    "failure.secret.publishing_key": "your publishing key",
    "failure.secret.github_sign_in": "your GitHub sign-in",
    "failure.secret.google_sign_in": "your Google sign-in",
    # Visitor numbers: signing in to Google (google_setup.py).
    "google_setup.title": "Visitor numbers",
    "google_setup.unavailable": (
        "This copy of Pressless cannot connect to Google, so it cannot show your visitor "
        "numbers."
    ),
    "google_setup.offer": (
        "Pressless can show how many people read your site, and from which countries, by "
        "reading them from Google Analytics. This is optional: without it, only the visitor "
        "numbers are missing."
    ),
    "google_setup.unverified": (
        "Google is still checking Pressless, so it will say it has not verified this app. "
        "Pressless only reads your visitor numbers. To carry on, click "
        "<strong>Advanced</strong>, then <strong>Go to Pressless</strong>."
    ),
    "google_setup.sign_in": "Sign in with Google",
    "google_setup.signed_in": "You are signed in to Google.",
    "google_setup.continue": "Continue",
    "google_setup.none_found.title": "No Analytics site found",
    "google_setup.none_found": (
        "This Google account can see no Google Analytics property. Sign in with the account "
        "that can."
    ),
    "google_setup.which": "Which site should Pressless show numbers for?",
    "google_setup.use": "Use this site",
    "google_setup.choose_hint": "Choose one of the sites in the list.",
    "google_setup.reading": "Pressless reads visitor numbers for Analytics property {property}.",
    "google_setup.choose_other": "Choose a different site",
    "google_setup.sign_in_again": "Sign in again",
    "google_setup.turn_off": "Turn off visitor numbers",
    "google_setup.ready": "Visitor numbers are ready.",
    "google_setup.privacy_failed": (
        "Visitor counting is on, but the Privacy page or its link could not be added. Saving "
        "Settings tries once more."
    ),
    "google_setup.counting.failed": (
        "Pressless could not read this site's counting code from Google, so counting is "
        "still off. You can type its measurement id on the Settings page."
    ),
    "google_setup.counting.kept": "Counting stays on with {id}.",
    "google_setup.counting.also": "Google also lists {ids} for this site.",
    "google_setup.counting.found": (
        "Pressless found this site's counting code ({id}) and will put it on every page you "
        "publish."
    ),
    "google_setup.counting.several": (
        "Google lists several web streams for this site: {ids}. Type the right measurement "
        "id on the Settings page to start counting."
    ),
    "google_setup.counting.none": (
        "This site has no web stream in Google Analytics yet, so counting is off. In Google "
        "Analytics open Admin, then Data streams, then Add stream, choose Web and enter your "
        "site's address. Then type the measurement id it shows on the Settings page."
    ),
    "google_setup.off": "Visitor numbers are off.",
    "google_setup.not_told": (
        "Pressless could not tell Google to forget its permission. You can remove it "
        "yourself at {link}."
    ),
    # Setup: the first-run wizard, Settings and the shortcuts (setup.py).
    "setup.step.welcome": "Set up Pressless",
    "setup.step.account": "A GitHub account",
    "setup.step.repository": "A home for your site",
    "setup.step.key": "A key for Pressless",
    "setup.step.install": "Let Pressless reach your site",
    "setup.step.pages": "Switch the site on",
    "setup.step.site": "Your site",
    "setup.welcome": (
        "Pressless publishes your site on GitHub, which hosts it for free. These steps take "
        "you through getting it ready, one screen at a time. You need an email address and "
        "about fifteen minutes."
    ),
    "setup.welcome.beside": (
        "Some steps happen on GitHub's own pages. Keep this page open beside them. If you "
        "close Pressless partway, it starts again where you left off."
    ),
    "setup.account.have": "If you already have a GitHub account, type its name below.",
    "setup.account.make": "If not, make one:",
    "setup.account.need": "You need a GitHub account. If you do not have one yet, make one now:",
    "setup.sign_up.1": (
        "Open <a href=\"https://github.com/signup\" target=\"_blank\" "
        "rel=\"noopener\">github.com/signup</a>."
    ),
    "setup.sign_up.2": (
        "Type your email address, a password and a username, and follow GitHub's steps. It "
        "sends a code to your email to check it is yours."
    ),
    "setup.sign_up.3": "When GitHub asks which plan, the free one is all Pressless needs.",
    "setup.signin.account": (
        "Type the name of the GitHub account your site will live in. If you have more than "
        "one, Pressless checks you sign in to this one."
    ),
    "setup.install": (
        "Pressless works through its own app on GitHub, Pressless App, which reaches only "
        "the repositories you let it. Install it on your account:"
    ),
    "setup.install.1": "Open {link}.",
    "setup.install.2": (
        "If GitHub asks you to select a user, click <b>Continue</b> beside <b>{account}</b>."
    ),
    "setup.install.3": (
        "Under <b>for these repositories</b>, leave <b>All repositories</b> chosen. "
        "Pressless makes your site's repository next, and at the end tells you how to let "
        "the app reach only that one."
    ),
    "setup.install.4": "Click <b>Install</b>, then come back here and press <b>Next</b>.",
    "setup.install.already": (
        "If GitHub shows Pressless App's settings instead, with no <b>Install</b> button, "
        "the app is already installed. Come back here and press <b>Next</b>."
    ),
    "setup.new_repository": (
        "A repository is the folder on GitHub your site lives in. Pressless makes it for "
        "you, as Public: GitHub hosts sites for free only from public repositories."
    ),
    "setup.new_repository.named": (
        "Named <b>{account}.github.io</b>, your site's address is "
        "https://{account}.github.io. Any other name works too, and gives "
        "https://{account}.github.io/<i>the-name</i>/."
    ),
    "setup.repository": "A repository is the folder on GitHub your site lives in. Make one:",
    "setup.new_repository.1": (
        "Open <a href=\"https://github.com/new\" target=\"_blank\" "
        "rel=\"noopener\">github.com/new</a>. Or, on GitHub, click the <b>+</b> at the top "
        "right, then <b>New repository</b>."
    ),
    "setup.new_repository.2": (
        "Under <b>Repository name</b>, type <b>{account}.github.io</b>. Your site's address "
        "is then https://{account}.github.io. Any other name works too, and gives "
        "https://{account}.github.io/<i>the-name</i>/."
    ),
    "setup.new_repository.3": (
        "Choose <b>Public</b>. GitHub hosts sites for free only from public repositories."
    ),
    "setup.new_repository.4": "Click <b>Create repository</b>. Leave everything else as it is.",
    "setup.key": (
        "Pressless needs a key that reaches your site's repository and no other. Make one:"
    ),
    "setup.key.kept": (
        "Pressless already has the key you gave it. Leave the box empty to keep it, or paste "
        "a new one."
    ),
    "setup.key.safe": (
        "Pressless keeps the key in your computer's own safe store, never in a file it shows "
        "anyone."
    ),
    "setup.new_key.1": "On GitHub, click your picture at the top right, then <b>Settings</b>.",
    "setup.new_key.2": (
        "At the bottom of the left-hand list, click <b>Developer settings</b>, then "
        "<b>Personal access tokens</b>, then <b>Fine-grained tokens</b>."
    ),
    "setup.new_key.3": (
        "Click <b>Generate new token</b>. Name it <b>Pressless</b>, and choose how long it "
        "lasts. When it runs out, make a new one the same way and paste it into Settings."
    ),
    "setup.new_key.4": (
        "Under <b>Repository access</b>, choose <b>Only select repositories</b>, then your "
        "site's repository."
    ),
    "setup.new_key.5": (
        "Under <b>Repository permissions</b>, set <b>Contents</b>, <b>Pages</b> and "
        "<b>Administration</b> each to <b>Read and write</b>. Pressless needs Administration "
        "to switch your site on (PRESS-0230)."
    ),
    "setup.new_key.6": "Click <b>Generate token</b>, then copy it. GitHub shows it only once.",
    "setup.pages": (
        "GitHub Pages is what puts your repository on the web. Press Next and Pressless "
        "checks it, and switches it on if it is off."
    ),
    "setup.pages.nojekyll": (
        "It also adds an empty file named .nojekyll to your repository, which tells GitHub "
        "to show your site's files exactly as Pressless makes them."
    ),
    "setup.site": (
        "Your site's address is {link}. It can take a few minutes after your first publish "
        "before it shows."
    ),
    "setup.site.finish": "Press Next to check everything with GitHub one last time and finish.",
    "setup.narrow": (
        "The Pressless app can reach every repository in your account. To let it reach only "
        "your site's: on GitHub, click your picture, then <b>Settings</b>, then "
        "<b>Applications</b>. Click <b>Configure</b> beside <b>Pressless App</b>, choose "
        "<b>Only select repositories</b>, pick <b>{repository}</b>, and click <b>Save</b>."
    ),
    "setup.hint.repository": "Type it as owner/name, the way GitHub shows it.",
    "setup.hint.site_name": "Type the site's name on one line.",
    "setup.hint.site_description": "Write the description on one line, or leave it empty.",
    "setup.hint.site_address": "Type the site's full address, starting with https://.",
    "setup.hint.measurement_id": (
        "Type the measurement id as Google shows it: G- and then capital letters and "
        "numbers, or leave it empty."
    ),
    "setup.hint.no_such_repository": (
        "GitHub has no repository by that name that this key can reach."
    ),
    "setup.hint.key_missing": "Paste your publishing key.",
    "setup.hint.key_malformed": "A publishing key has no spaces or line breaks. Paste it again.",
    "setup.hint.type_account": "Type your GitHub account name, as GitHub shows it.",
    "setup.hint.no_account": (
        "GitHub has no account by that name. Check the spelling, or finish making it first."
    ),
    "setup.hint.not_public": (
        "GitHub shows no public repository by that name. Check the spelling, and that you "
        "chose Public when you made it."
    ),
    "setup.hint.key_not_granted": (
        "This key cannot reach that repository. On GitHub, edit the key and choose your "
        "site's repository under Repository access."
    ),
    "setup.hint.no_pages_read": (
        "This key cannot see GitHub Pages. On GitHub, edit the key and set Pages to Read and "
        "write under Repository permissions."
    ),
    "setup.hint.no_pages_write": (
        "This key cannot switch GitHub Pages on. On GitHub, edit the key and set Pages and "
        "Administration to Read and write under Repository permissions, then press Next "
        "again."
    ),
    "setup.hint.name_alone": (
        "Type the repository's name alone, as GitHub shows it after your account name."
    ),
    "setup.hint.not_installed": (
        "GitHub shows no Pressless app installed on your account yet. Follow the steps "
        "above, then press Next again."
    ),
    "setup.hint.taken": (
        "A repository by that name already exists in your account. Choose another name."
    ),
    "setup.hint.add_to_app": (
        "Pressless made the repository, but the Pressless app cannot reach it yet. On "
        "GitHub, click your picture, then Settings, then Applications. Click Configure "
        "beside Pressless App, click Select repositories, pick {repository}, and click Save. "
        "Then press Next again."
    ),
    "setup.hint.app_cannot_reach": (
        "The Pressless app cannot reach this repository. On GitHub, click your picture, then "
        "Settings, then Applications, and check that Pressless App's installation includes "
        "it. Then press Next again."
    ),
    "setup.hint.other_account": (
        "You signed in to GitHub as {signed_in}, not {typed}. To use {typed}, switch to it "
        "on github.com, or correct the name above. Then press Next to sign in again."
    ),
    "setup.hint.elsewhere": (
        "This repository already puts a site on the web another way, so Pressless cannot "
        "publish to it. Press Back and choose a different, new repository. Leave this one's "
        "GitHub Pages settings as they are: changing them would take the site already there "
        "offline."
    ),
    "setup.field.account": "Your GitHub account name",
    "setup.field.repository_name": "The repository's name",
    "setup.field.paste_key": "Paste the key here",
    "setup.field.repository": "Your site's repository on GitHub (owner/name)",
    "setup.field.site_name": "Your site's name",
    "setup.field.site_description": "A short description of your site (optional)",
    "setup.field.site_address": "Your site's address",
    "setup.field.daily_prompt_filter": (
        "Leave out entries with a tag matching (optional, for example dailyprompt-*)"
    ),
    "setup.field.measurement_id": (
        "Google's measurement id, to count your visitors (optional, starts G-)"
    ),
    "setup.field.key": "Your publishing key",
    "setup.help.repository": (
        "Type the repository's owner and name with a slash between, as GitHub shows them at "
        "the top of the repository's page: <b>owner/name</b>. They are also the end of that "
        "page's address, after github.com/."
    ),
    "setup.help.repository.new": "To make a new repository:",
    "setup.help.site_name": (
        "Your own choice. Pressless puts it wherever your site's header and footer have a "
        "place for the site's name."
    ),
    "setup.help.site_description": (
        "One line about your site, in your own words. Pressless puts it wherever your site's "
        "header and footer have a place for it. Leave it empty if you do not want one."
    ),
    "setup.help.site_address": (
        "The address people type to reach your site, starting with https://. On GitHub, open "
        "your site's repository and click <b>Settings</b>, then <b>Pages</b>: once the site "
        "is live, its address is shown there."
    ),
    "setup.help.site_address.named": (
        "A repository named <b>your-name.github.io</b> is at https://your-name.github.io. "
        "Any other name is at https://your-name.github.io/<i>the-name</i>/. If you gave your "
        "site a domain of your own under <b>Custom domain</b> on that page, type that "
        "instead."
    ),
    "setup.help.daily_prompt_filter": (
        "Pressless leaves off your site every entry with a tag that matches this. A <b>*</b> "
        "stands for any letters, so <b>dailyprompt-*</b> matches dailyprompt-1 and "
        "dailyprompt-2024. Capital letters must match too."
    ),
    "setup.help.daily_prompt_filter.empty": "Leave it empty to keep every entry.",
    "setup.help.measurement_id": (
        "It tells Google Analytics which counter your visitors are counted on. Leave it "
        "empty and Pressless adds no counting code to your site. To find it:"
    ),
    "setup.help.measurement_id.1": (
        "Open <a href=\"https://analytics.google.com\" target=\"_blank\" "
        "rel=\"noopener\">analytics.google.com</a> and sign in."
    ),
    "setup.help.measurement_id.2": "Click <b>Admin</b>, the gear at the bottom left.",
    "setup.help.measurement_id.3": (
        "Under <b>Data collection and modification</b>, click <b>Data streams</b>, then your "
        "site's stream. If there is none, click <b>Add stream</b>, then <b>Web</b>, and type "
        "your site's address."
    ),
    "setup.help.measurement_id.4": "Copy the <b>Measurement ID</b>. It starts G-.",
    "setup.help.key": (
        "The key lets Pressless change your site's repository and its settings, and no other "
        "repository. Leave the box empty to keep the key Pressless already has. To make a "
        "new one:"
    ),
    "setup.signed_in": (
        "Pressless is signed in to GitHub. Typing a key below replaces the sign-in. <a "
        "href=\"/setup/github\">Sign in to GitHub again</a>."
    ),
    "setup.key_kept": "Leave the key box empty to keep the key Pressless already has.",
    "setup.save": "Check the repository again and save",
    "setup.starter.box": (
        "Start with a plain site: a homepage, an About page, a menu, a header and a footer, "
        "ready for you to change."
    ),
    "setup.starter.box.empty": (
        "Leave it unticked if you will bring in a site you already have: that needs an empty "
        "copy of Pressless."
    ),
    "setup.starter.unpublished": "Your starter site is not on the web yet.",
    "setup.starter.publish": (
        "To put it on the web, open <b>Home</b> under <b>Your pages</b> on your list, and "
        "press <b>Press to site</b>."
    ),
    "setup.done": "Setup is done.",
    "setup.done.address": "Your site's address is {link}.",
    "setup.done.starter": (
        "Your starter site is in place. It is not on the web until you publish it."
    ),
    "setup.done.left_alone": "Pressless will leave these alone on your site:",
    "setup.done.nothing_left_alone": "Pressless found nothing on your site it must leave alone.",
    "setup.done.kept_key": "Your publishing key is kept in {store}.",
    "setup.done.kept_sign_in": "Your GitHub sign-in is kept in {store}.",
    "setup.done.in_a_file": (
        "No keyring was found on this computer, so it is kept in a file only your account "
        "can read, in the Pressless-data folder."
    ),
    "setup.onward": "Go to your list",
    "setup.google.on": (
        "Visitor numbers are on: <a href=\"/setup/google\">change the site or turn them "
        "off</a>."
    ),
    "setup.google.offer": (
        "Optional: <a href=\"/setup/google\">see how many people read your site</a>, from "
        "Google Analytics."
    ),
    "setup.privacy.failed": (
        "Visitor counting is on, but the Privacy page or its link could not be added. Saving "
        "again tries once more."
    ),
    "setup.privacy.page": (
        "Your site now has a Privacy page saying that it counts visitors. Open it from Your "
        "pages and add how people can reach you."
    ),
    "setup.privacy.link": "Your footer now links to the Privacy page.",
    "setup.cannot_finish": "Setup cannot finish on this computer.",
    "setup.name_not_moved": (
        "Pressless could not move your site's name into your site's own files, and will try "
        "again next time it starts: {reason}"
    ),
    "setup.shortcuts.unavailable": (
        "Pressless can add itself to the menu and the desktop only when it runs from the "
        "file you downloaded."
    ),
    "setup.shortcuts.title.windows": "Start Menu and desktop",
    "setup.shortcuts.title": "App menu and desktop",
    "setup.shortcuts.start_menu": "the Start Menu",
    "setup.shortcuts.app_menu": "your app menu",
    "setup.shortcuts.menu": "Put Pressless in {menu}",
    "setup.shortcuts.desktop": "Put a Pressless icon on the desktop",
    "setup.shortcuts.untick": "Untick a box and save to take that one away again.",
    "setup.shortcuts.save": "Save these",
    "setup.shortcuts.pinning.windows": (
        "Pressless is in the Start Menu. To pin it to the taskbar, find it in the Start "
        "Menu, right-click it and choose Pin to taskbar."
    ),
    "setup.shortcuts.pinning": (
        "Pressless is in your app menu. To add it to your panel, find it in the menu, "
        "right-click it and choose the option that pins it or adds it to the panel. Its name "
        "differs between desktops."
    ),
    "setup.shortcuts.removed": "Pressless is no longer in {menu}.",
    "setup.shortcuts.icon_added": "There is a Pressless icon on your desktop.",
    "setup.shortcuts.icon_removed": "The Pressless icon is gone from your desktop.",
    "setup.shortcuts.unchanged": "Nothing needed changing.",
    # The visitor numbers page and its card on the list (dashboard.py).
    "dashboard.title": "Who is reading",
    "dashboard.window.7": "Last 7 days",
    "dashboard.window.7.phrase": "the last 7 days",
    "dashboard.window.28": "Last 4 weeks",
    "dashboard.window.28.phrase": "the last 4 weeks",
    "dashboard.window.365": "Last 12 months",
    "dashboard.window.365.phrase": "the last 12 months",
    "dashboard.card.ask": "<a href=\"{page}\">See who is reading your site</a>",
    "dashboard.card.read": (
        "{people} read your site in {window}, as of {when}. <a href=\"{page}\">See where they "
        "are</a>"
    ),
    "dashboard.off": (
        "Visitor numbers are off. Pressless can read them from Google Analytics if you sign "
        "in with Google: <a href=\"{page}\">turn on visitor numbers</a>."
    ),
    "dashboard.sign_in_again": (
        "If Google no longer accepts the sign-in, <a href=\"{page}\">sign in again</a>."
    ),
    "dashboard.stale": (
        "Pressless could not reach Google just now, so these are the numbers from {when}."
    ),
    "dashboard.updated": "Last updated {when}.",
    "dashboard.count.none": "Nobody read your site in {window}, as far as Google can tell.",
    "dashboard.count.one": "<b>{count}</b> <span>person read your site in {window}.</span>",
    "dashboard.count.many": "<b>{count}</b> <span>people read your site in {window}.</span>",
    "dashboard.day": "{day}: {people}",
    "dashboard.nobody": "nobody",
    "dashboard.each_day": "People each day",
    "dashboard.each_month": "People each month",
    "dashboard.where": "Where they are",
    "dashboard.country": "Country",
    "dashboard.people": "People",
    "dashboard.unknown_country": "Somewhere Google could not tell",
    "dashboard.how": "How they found you",
    "dashboard.came_from": "Came from",
    "dashboard.visits": "Visits",
    "dashboard.channel.organic_search": "A search engine",
    "dashboard.channel.paid_search": "A search advert",
    "dashboard.channel.direct": "Typed the address or used a bookmark",
    "dashboard.channel.referral": "A link on another site",
    "dashboard.channel.organic_social": "Social media",
    "dashboard.channel.paid_social": "A social media advert",
    "dashboard.channel.email": "An email",
    "dashboard.channel.organic_video": "A video site",
    "dashboard.channel.unassigned": "Google could not tell",
    "dashboard.what": "What they read",
    "dashboard.page": "Page",
    "dashboard.views": "Views",
    "dashboard.time_on_page": "Time on page",
    "dashboard.minutes": "{minutes}m {seconds}s",
    "dashboard.seconds": "{seconds}s",
    "dashboard.people.one": "1 person",
    "dashboard.people.many": "{count} people",
    "dashboard.when": "{date} at {clock}",
    # Updating (updating.py): the offer, the switch, Update now's pages and console line.
    "updating.offer": "Pressless {version} is ready to install. Your writing stays where it is.",
    "updating.update_now": "Update now",
    "updating.later": "Later",
    "updating.skip": "Skip this version",
    "updating.checking": "Pressless looks for a new version each time it starts.",
    "updating.stop_looking": "Stop looking",
    "updating.not_checking": "Pressless does not look for new versions.",
    "updating.look": "Look when Pressless starts",
    "updating.installing": (
        "Pressless is installing version {version} and will open again by itself in a "
        "moment. You can close this tab."
    ),
    "updating.not_reopened": (
        "Pressless is updated to version {version} but could not open again by itself. Close "
        "its window and start it again."
    ),
    "updating.console": "Pressless is updating. You can close this window.",
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
