# Pressless privacy policy

Pressless is a program that runs on your own computer. It has no server.
It sends the people who make Pressless nothing, unless you say yes to
usage reports, or press Send in the Send my log box (both below).

## Google user data

Signing in with Google is optional. It is used only to show you your own
website's visitor numbers inside Pressless.

### What Google user data Pressless accesses

Pressless asks Google for one permission: to read your Google Analytics
data (`https://www.googleapis.com/auth/analytics.readonly`). It cannot
change anything in your Analytics or your Google account, and it cannot
see your email, contacts, files or anything else.

With that permission it reads:

- the names and ids of the Analytics accounts and properties your Google
  account can see, so you can choose your site;
- the web data streams of the property you choose, to find the
  measurement id your site's counting code needs;
- your site's visitor figures: how many people visited, from which
  countries and which provinces or states, on which days (or months,
  for spans longer than 90 days), which pages they read and for how
  long, and
  how they found your site (for example, a search engine or a link).

These are totals. Google Analytics does not give Pressless the names,
email addresses or internet addresses of your visitors.

### How Pressless uses it

Only to show these figures to you, inside Pressless, on your own
computer, and to fill in your site's measurement id. Pressless does not
use Google user data for advertising, does not sell it, and does not use
it to train any AI or machine-learning model.

### Who it is shared with

No one. Pressless has no server, and its makers receive none of your
Google user data, with one exception you choose: a log you send with
Send my log can hold Google's own short error message, which can name
your Analytics property. Usage reports carry none of it. Pressless talks
to Google only to ask for the figures above, and it does not send Google
user data to anyone else.

### How it is protected

- Everything that passes between Pressless and Google's servers travels
  over an encrypted connection (HTTPS). When you sign in, Google's answer
  comes back to Pressless through your browser on your own computer,
  and never leaves it.
- The key Google gives Pressless when you sign in is kept in your
  computer's own password store: Windows Credential Manager, or your
  Linux desktop's keyring. On a Linux computer with no keyring, it is
  kept in a file in Pressless's own folder that only your user account
  can read.
- The visitor figures are kept in one file in Pressless's own folder
  (`Pressless-data`). That folder is never part of your website, so the
  figures are never published.

### How long it is kept, and how to delete it

- **Visitor figures:** Pressless keeps only the latest answer for each
  time span you look at, and replaces it when it asks Google again. It
  never keeps a history.
- **Turning it off:** in Pressless, open Settings, follow the link to
  your visitor numbers, and choose **Turn off visitor numbers**.
  Pressless asks Google to cancel its key, so it can no longer read
  anything, and forgets which property you chose. It also deletes the
  key and the visitor figures from your computer; your publishing key
  is left alone. If Google cannot be reached, Pressless still deletes
  them, says so, and links you to Google's permissions page below, where
  you can cancel the key yourself. If either cannot be deleted, Pressless
  says so.
- You can also remove Pressless's access from Google's side at any time:
  <https://myaccount.google.com/permissions>.

Pressless's use and transfer of information received from Google APIs
adheres to the
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the Limited Use requirements.

## Usage reports

Pressless can send anonymous usage reports. They are off unless you say
yes. Setup asks, with the box unticked. If you set Pressless up before
reports existed, it asks once, on Your site, and leaving the question
unanswered counts as no. A copy of Pressless built without the reports'
key never asks and never sends.

### What a report holds

Each report says one of these things happened:

- a Pressless screen was opened, and its address inside Pressless, such
  as `/usage`;
- a step of a guided task, such as setup, was shown, and the task's and
  the step's names;
- a guided task was finished, and its name;
- a publish or an undo ended, and whether it worked;
- something went wrong, and the kind of error, the screen, and whether
  it happened while publishing.

Each report also carries Pressless's version, your operating system's
name (with its version, where the system gives one), a random code
made when you said yes, a random number made each time Pressless
starts, and a fixed number, always 1, that Google needs to count a report.

A report never holds your writing, your pages' names, your site's
address, your files or your settings.

### Where it goes

Straight from your computer to a Google Analytics property kept for
Pressless alone, never your website's. It goes to Google's European
address, `region1.google-analytics.com`, over an encrypted connection
(HTTPS). Pressless's makers read the reports there. Like any request,
it shows Google your computer's internet address.

The property's settings, as checked on 2026-11-17:

- Google works out your country and region, such as a province, from
  that address. It does not record your city.
- Google keeps each report's details for two months. After that, only
  totals remain, such as how often a screen was opened.
- The reports cannot be used for advertising, and Google signals is
  off, so they are not linked to any Google account.

### Seeing them

The **Usage reports** link at the top of every Pressless screen opens a
screen listing the latest reports sent, word for word, newest first.

### Turning them off

On the Usage reports screen, choose **Turn usage reports off**.
Pressless stops sending, forgets its random code, and deletes its list
of sent reports from your computer. Reports already sent stay with
Google. If you turn reports on again, Pressless makes a new random code.

## Send my log

Failure pages and Report a problem have a **Send my log** button. It
opens a box saying what goes and where. Nothing is sent until you press
**Send** in that box; **Not now** sends nothing.

### What it sends

- Pressless's two log files, `pressless.log` and the older
  `pressless.log.1`;
- Pressless's version and your operating system's name.

The log says what Pressless did and what went wrong. It names your site,
its pages and its files. It is written to leave out your keys,
passwords, account names and full paths, and before sending, Pressless
also removes the known shapes of keys and tokens. If Google refused a
request, the log keeps Google's own short error message, which can name
your Analytics property or YouTube channel.

### Where it goes

Over an encrypted connection (HTTPS) to a small relay Pressless's makers
run on Cloudflare. The relay files the two files, and an issue quoting
the log's last lines, in a private GitHub repository only the makers can
read. It answers a short reference, which Pressless shows you. Cloudflare
uses your computer's internet address to limit how often a log can be
sent; the relay does not store it.

### How long it is kept

Nothing deletes a sent log on a schedule. It stays in that repository
until the makers delete it.

## Checking for updates

Each time the downloaded Pressless starts, it asks GitHub, over HTTPS,
which version of Pressless is newest. The request names Pressless and
nothing about you or your site; GitHub sees your internet address, as it
does for any web request. Nothing goes to Pressless's makers.

The check is on until you turn it off: in Settings, press **Stop
looking**. Pressless then asks GitHub nothing until you press **Look when
Pressless starts**.

## Questions

Open an issue at <https://github.com/milnet01/Pressless/issues>.
