"""A pretend Google for the throwaway instance: made-up visitor figures, no network."""
import json
import random
from datetime import date, timedelta

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
            k = {7: 0.27, 28: 1.0, 365: 11.4}.get(start, 1.0)

            def sc(n):
                return max(1, round(n * k))

            total = sum(sc(n) for _, n in COUNTRIES)
            answer = {"reports": [
                {"rows": _rows(((c,), (sc(n),)) for c, n in COUNTRIES),
                 "totals": [{"metricValues": [{"value": str(total)}]}]},
                {"rows": _rows(strip)},
                {"rows": _rows(((p,), (sc(v), sc(u), s * k)) for p, v, u, s in PAGES)},
                {"rows": _rows(((g, s), (sc(n), sc(u))) for g, s, n, u in SOURCES)},
                {"rows": _rows(((c, r), (sc(n),)) for c, r, n in REGIONS)},
            ]}
            return 200, {}, json.dumps(answer).encode()
        return 404, {}, b""

    def now(self):
        import time
        return time.time()
