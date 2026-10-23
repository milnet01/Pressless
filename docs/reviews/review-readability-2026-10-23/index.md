# review-readability — whole tree, 2026-10-23

One pass, nine lanes, each a `review-lane` run through `neutral-lane`.
Each lane's return is beside this file as it came back. Premise checks
are in `premise-checks.md`.

| Lane | Model | Turns | Cache read | Cache write | Output | Cost USD | HIGH | MEDIUM | LOW |
|---|---|---|---|---|---|---|---|---|---|
| lane-01-face | claude-opus-5-5 | 23 | 667275 | 112748 | 17157 | 1.38 | 1 | 4 | 7 |
| lane-02-page-editor | claude-opus-5-5 | 15 | 706407 | 115035 | 19657 | 1.45 | 0 | 8 | 10 |
| lane-03-editor | claude-opus-5-5 | 18 | 417789 | 88670 | 22048 | 1.23 | 0 | 8 | 12 |
| lane-04-store | claude-opus-5-5 | 13 | 392474 | 80779 | 17549 | 1.08 | 0 | 5 | 7 |
| lane-05-build-publish | claude-opus-5-5 | 16 | 769001 | 111914 | 19016 | 1.43 | 1 | 10 | 8 |
| lane-06-setup-signin-insights | claude-opus-5-5 | 21 | 887564 | 128334 | 29257 | 1.79 | 0 | 6 | 16 |
| lane-07-app-sites-update | claude-opus-5-5 | 25 | 363667 | 76288 | 16619 | 1.02 | 1 | 5 | 6 |
| lane-08-import | claude-opus-5-5 | 17 | 277347 | 71373 | 11830 | 0.86 | 1 | 4 | 6 |
| lane-09-tooling | claude-opus-5-5 | 24 | 410677 | 101031 | 21047 | 1.31 | 2 | 4 | 8 |
