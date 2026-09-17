# Pressless

> Write, preview and publish your own website from your own computer —
> without needing anyone technical, and without a company owning your
> words.

## What it is

Pressless is a program for writers who keep a website on GitHub Pages
(GitHub's free web hosting). It runs on your own computer and opens in
your normal web browser.

When it is finished, you will write an entry, see exactly how it will
look, and click once to put it on your site.

Two things it is deliberately **not**:

- **Not a website host.** It never talks to the people reading your site.
  It has no accounts and cannot be reached from the internet.
- **Not the owner of your writing.** Every entry is a plain text file in
  an ordinary folder. You can open it in any text editor, even with
  Pressless closed or uninstalled.

## Where it stands

**Not ready to use yet.** The parts that work behind the scenes are
built and tested. Those parts:

- turn your writing into web pages
- build the whole site
- keep your GitHub key safe
- publish to GitHub

What is missing is the part you would see and click.

What comes next, in order:

1. **Setup** — you paste in your GitHub key once and type a few facts
   about your site. Built; you will reach it once the next step arrives.
2. **Writing and publishing** — the editor, the preview and the Publish
   button. This is the first version you could actually use.
3. **Undo**, then **editing your other pages**, then **photographs and
   templates**, then **a visitor dashboard**.

[ROADMAP.md](ROADMAP.md) has the detail. [CHANGELOG.md](CHANGELOG.md)
lists what each release added.

## Trying the download today

Download from the [latest release](https://github.com/milnet01/Pressless/releases/latest).

**Today the program only checks itself.** It finds its folder, finds a
safe place on your computer to keep a key, prints what it found, and
stops. Nothing is written except that folder.

### Where your writing will live

Pressless keeps everything in a folder called `Pressless-data`, right
beside the program. **So put the program where you want your writing to
live** before you first start it.

### Linux

1. Download `Pressless-<version>-x86_64.AppImage`.
2. Save it in the folder where you want your writing kept.
3. Allow it to run as a program. In most file managers that is
   right-click → **Properties** → **Permissions**.
4. Start it. To see what it printed, start it from a terminal.

### Windows

1. Download `Pressless-<version>-windows.zip`.
2. Extract it into the folder where you want your writing kept. You get a
   `Pressless` folder and a file called `Start Pressless.bat`.
3. Double-click `Start Pressless.bat`. A window shows what it found and
   waits for a key press.

### Upgrading without losing anything

**Put the new version in the same place as the old one.**

- On Linux, save the new AppImage in the same folder.
- On Windows, extract the new zip over the old copy.

Put it anywhere else and it starts with an empty `Pressless-data`
folder. Your writing stays beside the old copy, and that folder is the
only place it is kept.

## Moving an existing blog in

**You cannot bring your own blog in yet.** Once Pressless is ready, you
will be able to start with an empty one and write from there.

An import from WordPress exists, but it was built for one site. It needs
that site's own files, so it only runs on the maintainer's computer.
[docs/specs/PRESS-0007-import.md](docs/specs/PRESS-0007-import.md)
explains what it carries across.

An import anyone can run is planned (PRESS-0125 on the
[roadmap](ROADMAP.md)).

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
