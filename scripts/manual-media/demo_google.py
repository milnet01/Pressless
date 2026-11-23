"""A pretend Google for the throwaway instance: made-up visitor figures, no network."""
import json
import random
from datetime import date, timedelta

# Made-up figures for 28 days, one tuple per row of the report insights._fetch asks for:
# PAGES (path, views, visitors, engagement seconds); SOURCES (channel, source,
# sessions, visitors); REGIONS (country, region, visitors); COUNTRIES
# (country, visitors). Two PAGES paths are instance.ENTRIES' entries.
# Another period scales them by PERIOD_SCALE; one not listed shows them as they are.
PERIOD_SCALE = {7: 0.27, 28: 1.0, 365: 11.4}
PAGES = (("/", 412, 260, 9100.0), ("/journal/first-light-on-the-harbour/", 238, 171, 15400.0),
         ("/about/", 96, 80, 2100.0), ("/journal/a-morning-at-the-market/", 74, 61, 5200.0))
SOURCES = (("Organic Search", "google", 210, 168), ("Direct", "(direct)", 140, 122),
           ("Organic Social", "facebook.com", 64, 55), ("Referral", "example.net", 22, 19))
REGIONS = (("ZA", "Western Cape", 112), ("ZA", "Gauteng", 56), ("GB", "England", 52),
           ("US", "California", 21))
COUNTRIES = (("ZA", 168), ("GB", 61), ("US", 44), ("NL", 19), ("AU", 12), ("DE", 9))


def _rows(dims_metrics):
    return [{"dimensionValues": [{"value": str(d)} for d in dims],
             "metricValues": [{"value": str(m)} for m in mets]} for dims, mets in dims_metrics]


class Google:
    def request(self, method, url, body, headers):
        if url.startswith("https://oauth2.googleapis.com/token"):
            return 200, {}, json.dumps({"access_token": "demo", "expires_in": 3600}).encode()
        if url.endswith(":batchRunReports"):
            # Read and answered by position, in insights._fetch's order:
            # countries, the period strip, pages, sources, regions.
            reqs = json.loads(body)["requests"]
            period = reqs[1]["dimensions"][0]["name"]
            start = int(reqs[0]["dateRanges"][0]["startDate"].removesuffix("daysAgo"))
            rnd = random.Random(start)  # noqa: S311 -- made-up figures, the same each run
            today = date.today()
            if period == "date":
                days = [((today - timedelta(n)).strftime("%Y%m%d"),)
                        for n in range(start, -1, -1)]
                strip = [(d, (rnd.randint(9, 18),)) for d in days]
            else:
                months = sorted({(today - timedelta(n)).strftime("%Y%m")
                                 for n in range(0, start + 1)})
                strip = [((m,), (rnd.randint(240, 420),)) for m in months]
            scale = PERIOD_SCALE.get(start, 1.0)

            def scaled(n):
                return max(1, round(n * scale))

            total = sum(scaled(n) for _, n in COUNTRIES)
            answer = {"reports": [
                {"rows": _rows(((c,), (scaled(n),)) for c, n in COUNTRIES),
                 "totals": [{"metricValues": [{"value": str(total)}]}]},
                {"rows": _rows(strip)},
                {"rows": _rows(((p,), (scaled(v), scaled(u), s * scale))
                               for p, v, u, s in PAGES)},
                {"rows": _rows(((g, s), (scaled(n), scaled(u))) for g, s, n, u in SOURCES)},
                {"rows": _rows(((c, r), (scaled(n),)) for c, r, n in REGIONS)},
            ]}
            return 200, {}, json.dumps(answer).encode()
        return 404, {}, b""

    def now(self):
        import time
        return time.time()
