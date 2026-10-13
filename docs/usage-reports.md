# Reading the usage reports

How a session turns Pressless's usage reports into a short summary and
roadmap items. The contract is
`docs/specs/PRESS-0262-usage-reports.md` § 4.7; the events and their
parameters are `src/pressless/usage.py`'s `EVENTS` and `COMMON`.

## Before you start

- The reports live in the Google Analytics property kept for Pressless
  alone, never the site's own. `docs/working-here.md` § *Registering the
  usage-report property* says how it was made.
- Query it through the Google Analytics connector: `run_report` for
  counts, `run_funnel_report` for the setup funnel. `get_account_summaries`
  finds the property's id.
- A parameter is a dimension named `customEvent:<parameter>`, and the
  event's name is `eventName`.
- **The figures are a guide, never exact.** The key ships inside a public
  program, so anyone can send reports, and only users who said yes send
  any.

## The custom dimensions

Each is event-scoped, named after its parameter:

`screen`, `wizard`, `step`, `kind`, `ended`, `error`, `publishing`,
`app_version`, `system`, `session_id`.

`engagement_time_msec` is not one: Google reads it to count a user.

## The four questions

1. **Where setup stops.** A funnel over `wizard_step` with `wizard` =
   `setup`, one funnel step per `step` value in the wizard's order, split by
   `system`. The order is `setup.py`'s `_first_run_wizard`. A step where
   many stop is a candidate.
2. **What goes wrong.** `failure` counted by `error`, `screen`,
   `app_version` and `system`.
3. **How presses end.** `press` counted by `kind` and `ended`, by
   `app_version`.
4. **What is used.** `screen` counted by `screen`.

## Writing the summary

- Plain words, short: what was asked, what the figures show, and the
  date range.
- Name each query, so a reader can run it again.
- **An error, or a stopping step, seen in more than one report is filed
  with `roadmap_log`**, citing the query that found it. One report is
  noted in the summary and not filed.
- Never copy a client id or a session id into the summary or the roadmap.
