# Pre-registration 2: strategy line v5 on tasks no line was developed on

Written 2026-10-02, before any session of this phase, while the first confirmation
(`prereg-strategy.md`, line v2) was still running; nothing in this document was chosen from its
results. Sealed by `prereg-strategy2.sha256` (`nav_confirm2.py --record-hash`) and committed before
the first session; `nav_confirm2.py --live` refuses to spend while the two disagree.

## What is being tested

Development (README section 15): line v5 (`strategy_lines.STRATEGY_HINT_V5`), which adds to the
earlier lines "inside the call never click or change the page's location; fetch each page and
parse it with DOMParser, or fetch the data the page loads; if it errors or falls short, fix the
code rather than walking", made Haiku right on 17 of 18 development sessions at a mean of 0.062
USD, and no session walked. It was written on S1-S5 and H1, which therefore cannot confirm it.

## Arms

Both `claude-haiku-4-5` in Claude Code with Playwright MCP, same settings and tools
(`nav_e2e.one_session`: no hook, no key, `SendMessage` and `ListAgents` denied):

- `HAIKU`: the shared system-prompt line only.
- `HAIKU-HINT5`: the same plus `STRATEGY_HINT_V5`, verbatim as committed with this document.

No decision of ours runs in either arm; Jev spends nothing.

## Tasks (`nav_confirm2.CRAWLS` and `INTERACTIVE`), three runs per task and arm, 60 sessions

Eight crawls over mechanisms no line was developed on, answers from `truth_confirm2.py`, each
checked by a second route: D1 the 50-page catalogue (a new predicate), D2 an 8-page category,
D3 quotes held back ten seconds in a script, D4 an ASP.NET search form with view state, D5
infinite scroll, D6 a "load more" button, D7 search results over several pages, D8 a sum over a
3-page category. Interactive tasks never run with v5: A2 (a to-do list) and B2 (the silent
Remove trap). Grading as in the first confirmation.

## Hypotheses and thresholds

Exactly `nav_confirm.verdicts`, the function sealed with the first confirmation, over these
arms: a runner-killed session is charged the session cap (1.00) and counts as wrong.

- **H1, cost (primary).** Crawl total list USD of `HAIKU-HINT5` / `HAIKU` **at most 0.75**, and
  `HAIKU-HINT5` cheaper on **at least 6 of 8** crawl tasks.
- **H2, answers.** `HAIKU-HINT5` right on at least `HAIKU`'s count **minus 2**, of 24.
- **H3, no harm.** On A2 and B2: right on at least `HAIKU`'s count **minus 1**, of 6, and total
  cost at most **1.25 times** `HAIKU`'s.

v5 is confirmed if all three hold; a failing one is reported by name.

## Rules

As in `prereg-strategy.md`: development numbers are not pooled; only usage-limit stops are run
again; every wrong answer is read by hand before it is counted, and a grader fault is fixed for
both arms with the first grade kept; the Claude Code version of every session is reported.
Ceiling 14 USD list through the subscription (expected about 8).
