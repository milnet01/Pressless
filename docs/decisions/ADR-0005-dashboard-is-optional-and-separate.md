# ADR-0005: The dashboard is a separate part that publishing never depends on

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

S11 asks for visitor numbers by country inside Pressless. The site
already reports to Google Analytics, so the numbers exist; reading them
needs a second Google authorisation, separate from the GitHub key.

Discovery is explicit that Pressless never collects this itself — it
runs on his machine and no visitor can reach it — so the shape is fixed:
a service collects, Pressless displays.

## Decision

Insights is its own part. It may read Settings and talk to Google, and
nothing else. Nothing in writing or publishing may call it or depend on
it, and its setup is optional: he can decline the Google step and lose
the dashboard and nothing besides.

## Consequences

- A Google outage, an expired authorisation, or no internet costs him
  the dashboard and not his ability to publish — which is the whole
  point of the separation.
- **Setup has two steps instead of one.** S5 is about the publishing key
  and survives, but his first hour is longer, and the second step has to
  be skippable or it becomes a wall.
- The numbers are Google's and arrive already aggregated. Pressless
  cannot check them, and cannot show anything Google does not report.
- A second external dependency, with its own limits on how often it will
  answer — which is why Insights is the one part allowed a cache.
