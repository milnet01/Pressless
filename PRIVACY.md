# Pressless privacy policy

Pressless is a program that runs on your own computer. It has no server,
and nobody who makes Pressless receives any of your data.

## Signing in with Google

Signing in with Google is optional. It lets Pressless show how many
people read your site, and from which countries.

- **What Pressless asks Google for:** permission to *read* your Google
  Analytics data (the `analytics.readonly` permission). It cannot change
  anything in your Google account or your Analytics.
- **What it reads:** the names of the Analytics properties your account
  can see, so you can pick your site; and, for the site you pick, the
  number of visitors and their countries.
- **Where it keeps things:** Google's permission is kept in your
  computer's own password store (on Linux without one, in a file only
  your account can read). The visitor numbers are kept in Pressless's
  own folder on your computer. Nothing is sent anywhere except to Google,
  to ask for these numbers.
- **Nothing is shared or sold.** Pressless never sends your data to its
  makers or to anyone else.

Pressless's use of information received from Google APIs adheres to the
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the Limited Use requirements.

## Turning it off

In Pressless, open Settings, follow the link to your visitor numbers,
and click **Turn off visitor numbers**. Pressless tells Google to forget its permission. You
can also remove it yourself at
<https://myaccount.google.com/permissions>.

## Questions

Open an issue at <https://github.com/milnet01/Pressless/issues>.
