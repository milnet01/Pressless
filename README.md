# Pressless

> Write, preview and publish your own website from your own computer —
> without needing anyone technical, and without a company owning your
> words.

## What it is

Pressless is a program for writers who keep a website on GitHub Pages
(GitHub's free web hosting). It runs on your own computer and opens in
your normal web browser.

You write an entry, see exactly how it will look, and click once to put
it on your site.

Two things it is deliberately **not**:

- **Not a website host.** It never talks to the people reading your site.
  It has no accounts and cannot be reached from the internet.
- **Not the owner of your writing.** Every entry is a plain text file in
  an ordinary folder. You can open it in any text editor, even with
  Pressless closed or uninstalled.

## Where it stands

**An early version you can use day to day, on Linux and Windows.** It
does:

- write with a few simple marks, with a cheat sheet below the box;
- show the real finished page beside the words as you type;
- save as you go, keeping changes to a live entry apart until you
  publish them;
- publish with one button, and put your files back if that fails;
- undo the last publish in one step;
- edit your other pages, and the header, footer and navigation;
- add photographs to your entries;
- start a new entry from a template;
- let you pick how Pressless itself looks: light, dark, high contrast,
  and more;
- update itself when a new version is out.

Still to come:

- **a dashboard** showing how many people read your site, and from which
  countries;
- **bringing in a WordPress blog** yourself;
- **running your whole site**: building your own homepage, adding and
  removing pages, changing the site's look, and putting music,
  downloads and documents on it.

The aim is for Pressless to replace WordPress entirely, and that comes
before version 1.0.

[ROADMAP.md](ROADMAP.md) has the detail. [CHANGELOG.md](CHANGELOG.md)
lists what each release added.

## Before you start

You need two things from GitHub (the site where your website's files
are kept):

1. **A GitHub account, and a repository for your site** — a repository
   is GitHub's name for a project folder. It can be empty. Turn on GitHub
   Pages (GitHub's free web hosting) for it in the repository's
   **Settings → Pages**.
2. **A publishing key.** On GitHub, open **Settings → Developer settings →
   Personal access tokens** and make a token that may change the contents
   of your site's repository. Pressless calls this your key. It asks for
   it once and keeps it where only your computer account can read it.

## Getting started

Download from the [latest release](https://github.com/milnet01/Pressless/releases/latest).

### Where your writing will live

Pressless keeps everything in a folder called `Pressless-data`, right
beside the program. **So put the program where you want your writing to
live** before you first start it.

### Linux

1. Download `Pressless-<version>-x86_64.AppImage`.
2. Save it in the folder where you want your writing kept.
3. Allow it to run as a program. In most file managers that is
   right-click → **Properties** → **Permissions**.
4. Double-click it. Pressless opens in your web browser.

### Windows

1. Download `Pressless-<version>-windows.zip`.
2. Extract it into the folder where you want your writing kept. You get a
   `Pressless` folder and a file called `Start Pressless.bat`.
3. Double-click `Start Pressless.bat`. Pressless opens in your web
   browser, with a plain text window beside it. Leave that window open
   while you work: closing it stops Pressless.

### The first time

Pressless asks for your site's repository (written as `owner/name`), your
site's name and address, and your key. It checks them with GitHub before
saving anything. Then it shows the list of your writing, where **New
entry** starts one.

When setup is done, Pressless offers one optional step: signing in with
Google, so it can show who reads your site once the dashboard arrives.
You can skip it and lose nothing else.

### Upgrading without losing anything

**From 0.5.0 on, Pressless updates itself.** When a new version is out,
the list of your writing says so. **Update now** installs it in place and
opens Pressless again; **Later** and **Skip this version** leave it. It
installs only a version signed by its maintainer. The line under the list
turns this checking off.

**Coming from an older version, put the new one in the same place.**

- On Linux, save the new AppImage in the same folder.
- On Windows, extract the new zip over the old copy.

Put it anywhere else and it starts with an empty `Pressless-data`
folder. Your writing stays beside the old copy, and that folder is the
only place it is kept.

## Moving an existing blog in

**You cannot bring your own blog in yet.** You start with an empty site
and write from there.

An import from WordPress exists, but it was built for one site. It needs
that site's own files, so it only runs on the maintainer's computer.
[docs/specs/PRESS-0007-import.md](docs/specs/PRESS-0007-import.md)
explains what it carries across.

An import anyone can run is planned (PRESS-0125 on the
[roadmap](ROADMAP.md)).

## Getting help

If something goes wrong or does not make sense, open an issue on
[GitHub Issues](https://github.com/milnet01/Pressless/issues). Say what
you pressed, what you expected, and what Pressless showed you. A security
problem is different: report it privately, as [SECURITY.md](SECURITY.md)
explains.

## For the curious

| Document | What it tells you |
|---|---|
| [ROADMAP.md](ROADMAP.md) | What is planned, being built, and done |
| [CHANGELOG.md](CHANGELOG.md) | What each release added |
| [docs/discovery.md](docs/discovery.md) | What Pressless is for, and how we would know it works |
| [docs/design.md](docs/design.md) | How it is put together |
| [docs/decisions/](docs/decisions/) | Why the close calls went the way they did |
| [docs/specs/](docs/specs/) | The detailed plan for one feature, where one was needed |
| [SECURITY.md](SECURITY.md) | How to report a security problem, and what is protected |

## Licence

Free to use, change and share, under the [MIT licence](LICENSE).
