"""A throwaway Pressless for the manual's pictures and videos.

The whole program through the launcher, with a made-up site, the tests'
pretend GitHub so publishing works, and made-up visitor figures. It reaches
no network, no keyring and none of the writer's own files. Prints
`LINK <url>` in place of opening a browser, and runs until killed.

    .venv/bin/python scripts/manual-media/instance.py [site|fresh]

`kit.start` is what normally runs it.
"""
import sys
import webbrowser
from datetime import datetime

import kit

for folder in ("src", "scripts", "tests"):
    sys.path.insert(0, str(kit.ROOT / folder))

import demo_google  # noqa: E402
import practice  # noqa: E402
import test_publishing  # noqa: E402

from pressless import __main__ as launcher  # noqa: E402
from pressless import (  # noqa: E402
    credentials,
    google_signin,
    insights,
    publisher,
    settings,
    sites,
    starter,
    store,
)

ENTRIES = (
    ("first-light-on-the-harbour", "First light on the harbour",
     "The boats go out before the sun. I watched them from the wall.",
     "2026-10-08 07:15:00", False),
    ("a-morning-at-the-market", "A morning at the market",
     "The fish stalls open at six. Gulls wait on every roof.", "2026-10-11 06:40:00", False),
    ("rain-on-the-quay", "Rain on the quay",
     "Something about rain. Finish this later.", "2026-10-20 21:05:00", True),
)


def seed(site) -> None:
    """Seaside Notes: set up, published once, two entries out and one draft."""
    (site / "site").mkdir(parents=True, exist_ok=True)
    credentials.write("file", site, "github", practice.NOT_A_KEY)
    credentials.write("file", site, "google", "demo-not-a-key")
    settings.save(site, settings.Settings(
        site_folder=site / "site", repository="your-name/your-name.github.io",
        site_address="https://seaside.example", daily_prompt_filter="", untouchable=(),
        credentials=settings.Credentials(
            store="file", github_account="github", google_account="google"),
        analytics_property_id="999", measurement_id="G-DEMO000000"))
    starter.fill(site, "Seaside Notes", starter.LOOKS[-1])
    starter.published(site)
    store.write_identity(site, store.Identity("Seaside Notes", "Notes from a small harbour town"))
    store.write_journal(site, True)
    for slug, title, body, date, draft in ENTRIES:
        store.write(site, store.Entry(slug=slug, title=title, date=datetime.fromisoformat(date),
                                      categories=(), tags=(), body=body, extra=()), draft=draft)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "site"
    kit.INSTANCE.mkdir(parents=True)
    sites.move_in(kit.INSTANCE)
    if mode == "site":
        seed(sites.open_site(kit.INSTANCE))
    practice.disarm()
    publisher._Urllib = lambda: test_publishing._github()
    insights._own_client = demo_google.Google
    google_signin.CLIENT_ID = "demo.apps.googleusercontent.com"
    google_signin.CLIENT_SECRET = "demo"  # noqa: S105 -- not a secret
    google_signin.available = lambda: True
    webbrowser.open = lambda link, *a, **k: (print("LINK", link, flush=True), True)[1]
    launcher._serve(kit.INSTANCE)


if __name__ == "__main__":
    main()
