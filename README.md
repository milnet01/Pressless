# Pressless

> Write, preview and publish your own website from your own machine —
> without needing anyone technical, and without a service owning your
> words.

## What it is

Pressless runs on your own computer and opens in your normal browser.
You write an entry, see it as it will look, and click once to publish it
to your own GitHub Pages site.

Two things it is deliberately not. It is **not a website host** — it
never talks to your visitors, has no accounts and is not reachable from
the internet. And it **does not own your writing**: every entry is an
ordinary text file in an ordinary folder, readable in any editor with
Pressless closed, deleted, or never installed.

## Status

**Not usable yet.** What it is for and how we would know it works are
agreed ([docs/discovery.md](docs/discovery.md)), and so is the shape
([docs/design.md](docs/design.md)). The work is broken into items in
[ROADMAP.md](ROADMAP.md), and the first of them is built: Marks, the
small styling language every part that renders reads. There is no app
around it yet — nothing here writes, builds or publishes a site.

## Install

Download from the [latest release](https://github.com/milnet01/Pressless/releases/latest).
Today the program only checks that it runs and prints what it found; the
app itself comes later.

Pressless keeps your writing in a folder called `Pressless-data`, beside
the file you download. So put that file where you want your writing to
live.

### Linux

1. Download `Pressless-<version>-x86_64.AppImage`.
2. Save it in the folder where you want your writing kept.
3. Right-click it, choose **Properties → Permissions**, and tick **Allow
   executing file as program**.
4. Double-click it.

**To upgrade**, save the new AppImage in the same folder as the old one.
Saved anywhere else, it starts empty, and your writing stays beside the
old copy — the one place nothing else keeps a copy of it.

### Windows

1. Download `Pressless-<version>-windows.zip`.
2. Extract it into the folder where you want your writing kept. You get a
   `Pressless` folder and `Start Pressless.bat`.
3. Double-click `Start Pressless.bat`.

**To upgrade**, extract the new zip over the old copy, in the same folder.
Extracted anywhere else, it starts empty, and your writing stays beside
the old copy — the one place nothing else keeps a copy of it.

## Usage

(Once there is something to use.)

## Documentation

| | |
|---|---|
| [ROADMAP.md](ROADMAP.md) | What is planned, in progress and shipped |
| [CHANGELOG.md](CHANGELOG.md) | What shipped, when |
| [docs/discovery.md](docs/discovery.md) | What this is for, and how we would know it works |
| [docs/design.md](docs/design.md) | The shape — the parts, and what may touch what |
| [docs/decisions/](docs/decisions/) | Why a close call went the way it did |
| [docs/specs/](docs/specs/) | The contract for one feature, where one was needed |

## License

[MIT](LICENSE).
