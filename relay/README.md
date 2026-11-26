# The log relay

A Cloudflare Worker that takes the log Pressless's **Send my log** posts and
files it as an issue in the private repository `milnet01/pressless-logs`.
It reaches GitHub as a GitHub App installed on that repository alone.
`docs/specs/PRESS-0436-send-my-log.md` § 4.3 owns what it does.

Pressless 1.3 sends each log gzipped, and the relay files it as sent:
`logs/<reference>/pressless.log.gz` and `pressless.log.1.gz`. Pressless 1.2
sends JSON, filed as `pressless.log` and `pressless.log.1`.

Pressless holds no key the relay checks. The relay refuses a wrong method or
path, a body of another type, a second send within a minute from one
address (an IPv6 sender by its /64), a body over 4 MiB (2.2 MiB for JSON)
and a body of the wrong shape, all before it asks GitHub for anything.

## Setting it up

Once, from the repository root, on the maintainer's machine:

1. Make a free Cloudflare account, and run `npx wrangler login`.
2. Run `.venv/bin/python scripts/relay-setup.py`. It needs `openssl` and
   `node`.
3. On GitHub, press **Create GitHub App**.
4. On the install page, choose **Only select repositories**, pick
   `pressless-logs`, and press **Install**.

A browser that withholds GitHub's sign-in from another site's form shows
"url wasn't supplied" at step 3. Then make the App by hand instead
(2026-11-21):

1. GitHub, **Settings**, **Developer settings**, **GitHub Apps**, **New
   GitHub App**. Name it, give the repository's page as its homepage,
   untick the webhook's **Active**, set **Contents** and **Issues** to
   **Read and write**, and choose **Only on this account**.
2. On its page, **Credentials**, **Key pairs**: generate a key, which
   downloads a `.pem`.
3. **Install App**, **Only select repositories**, `pressless-logs`.
4. Run `.venv/bin/python scripts/relay-setup.py --key <the .pem> --app-id
   <its App ID>`. It moves the key into place and deletes the download.
   It never replaces a key already kept there, which may be a live App's;
   if that App is gone, remove its key and run this again.

The script then fills the App's ids into `wrangler.jsonc`, deploys the
Worker, gives it the App's key as the secret `APP_KEY`, and sends a test log
whose issue it closes. Commit `wrangler.jsonc` afterwards.

The App's key stays in `~/.config/pressless/log-relay-app.pem`, readable by
its owner alone, and never in this repository. Run the script again to
restore a relay whose App was removed; it reuses the App it made.

## Testing it

```bash
node --test 'relay/test/*.test.js'
```

`scripts/local-ci.sh` runs this where `node` is on the path. GitHub is a
replaced `fetch`, and the App's key is made fresh for each run.
