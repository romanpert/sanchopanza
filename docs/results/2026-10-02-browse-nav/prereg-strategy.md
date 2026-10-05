# Pre-registration: a fixed strategy line on crawls it was not written on

Written 2026-10-02, before any session of this phase. Sealed by `prereg-strategy.sha256`
(`nav_confirm.py --record-hash`) and committed before the first session; `nav_confirm.py --live`
refuses to spend while the document and its seal disagree.

## What is being tested

README section 14 (development): one fixed line appended to the system prompt
(`nav_e2e.STRATEGY_HINT_V2`) halved what Haiku spends on long crawls without losing answers.
The line was written and rewritten on S1-S5 and H1, so those numbers cannot confirm it. The
claim tested here is that the line does the same on crawls it has never seen, and does no harm
on interactive tasks.

## Arms

Both `claude-haiku-4-5` in Claude Code with Playwright MCP, the same settings and tools
(`nav_e2e.one_session`: no hook, no key, `SendMessage` and `ListAgents` denied):

- `HAIKU`: the shared system-prompt line only.
- `HAIKU-HINT2`: the same, plus `STRATEGY_HINT_V2`, verbatim as committed with this document.

No decision of ours runs in either arm. Jev spends nothing in this phase.

## Tasks (`nav_confirm.TASKS`), three runs per task and arm, 60 sessions

Eight crawls, answers computed from the sites by `truth_confirm.py` and each checked by a
second route: C1 a 6-page category, C2 the 50-page catalogue, C3 one page of 250 rows, C4 year
tabs filled by JavaScript, C5 pagination done in the browser, C6 a "load more" button, C7 a
10-page table layout, C8 a 24-page table. Two interactive tasks never run with the line: A2
(a to-do list built by typing) and A3 (a login, then a tag's second page). C* are graded from
the last ANSWER line (`nav_e2e.grade`), A* by required substrings, as in development.

## Hypotheses and thresholds (`nav_confirm.verdicts`, unchanged after sealing)

A session the runner kills (`subtype` starting `runner:`) is charged the session cap
(`SESSION_MAX_USD`, 1.00) and counts as wrong.

- **H1, cost (primary).** Over the 24 crawl sessions per arm, total list USD of `HAIKU-HINT2`
  divided by `HAIKU` is **at most 0.75**, and `HAIKU-HINT2` has the lower mean on **at least 6
  of the 8** crawl tasks. Both must hold.
- **H2, answers (non-inferiority).** `HAIKU-HINT2` right on at least as many crawl sessions as
  `HAIKU` **minus 2**, out of 24.
- **H3, no harm.** On A2 and A3 (6 sessions per arm): `HAIKU-HINT2` right on at least `HAIKU`
  **minus 1**, and its total cost at most **1.25 times** `HAIKU`'s.

The line is confirmed if H1, H2 and H3 all hold. Any one failing is reported as that, by name.

## Rules

- Development numbers (section 14) are not pooled with these.
- A session stopped by the subscription's usage limit is `not_run` and run again; nothing else is
  re-run. A wrong answer is read by hand before being counted, and a grader fault, if found, is
  fixed for both arms and every session re-graded, with the first grade kept beside the new.
- Claude Code version is read from every transcript. If it changes during the phase, the phase
  says so and reports per version.
- Ceiling 14 USD of list price through the subscription (expected about 10); the runner stops at
  the ceiling and resumes on the next launch.
- Described, not tested: sessions that used at most three navigations (the extraction taken up),
  turns per task, per-task cost.
