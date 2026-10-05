"""A second labeller's supersession cases (2026-10-05), written without reading the first
labeller's cases, labels or results (`supersede_cases.py`, `supersede_bench.jsonl`,
`docs/results/2026-10-05-memory-supersede/`). Only the variants' question code, the module
docstrings and the carry scenes were read, to know the style; no fact of the carry scenes is
reused (column order, integer cents, legacy totals, log separators, event timestamps).

Each case: a stored `rule`, the `request` now being checked (whose diff broke the rule), the
rules `stored` since the rule, a label (1: the person has since asked for or stated the rule's
opposite, or dropped or renamed what it protects, so the send-back should be suppressed; 0: the
rule still stands) and a one-line reason.

48 cases: 16 positives (9 through the request, 7 through a newer stored rule; 9 indirect, with
no "we changed this" wording) and 32 negatives (12 tasks that would break the rule without
asking to change it, 8 refinements or additions, 6 restatements, 6 unrelated requests touching
the rule's area).
"""

from __future__ import annotations

from typing import Any

BASE_AT = 1_788_771_600.0  # 2026-09-07 10:00 local-ish
DAY = 86_400.0


def _at(day: float) -> float:
    return BASE_AT + day * DAY


def case(cid: str, label: int, kind: str, domain: str, rule: str, request: str,
         stored: tuple[str, ...] = (), reason: str = "", indirect: bool | None = None,
         ) -> dict[str, Any]:  # fmt: skip
    """The rule is said on day 0; stored rules on days 3, 6, ...; the request is later."""
    return {
        "id": cid, "label": label, "kind": kind, "domain": domain, "indirect": indirect,
        "rule": {"text": rule, "at": _at(0)},
        "request": request,
        "stored": [{"text": t, "at": _at(3 * (k + 1))} for k, t in enumerate(stored)],
        "reason": reason,
    }  # fmt: skip


CASES: list[dict[str, Any]] = [
    # --- 16 positives ---------------------------------------------------------------------------
    case("p01", 1, "pos-request", "cli",
         "The `sync` command must never delete files on the remote; it only uploads.",
         "Make `sync` mirror the local folder exactly, removing anything on the remote that is "
         "not here anymore.",
         ("Long-running commands show a spinner while they work.",),
         "asks sync to delete remote files, which the rule forbids", indirect=True),
    case("p02", 1, "pos-request", "data",
         "Dates in the API responses are always ISO 8601 strings in UTC.",
         "We're dropping the UTC-only convention for API dates: from now on return them in the "
         "user's local timezone with its offset.",
         (), "says the UTC convention is dropped and asks for local time", indirect=False),
    case("p03", 1, "pos-stored", "infra",
         "Keep the staging database on Postgres 14; the reporting tool breaks on newer versions.",
         "Bump the image versions in staging's docker-compose so they match production.",
         ("The reporting tool is gone, so staging can follow production onto Postgres 16 now.",),
         "a newer rule says the reason is gone and staging moves to 16", indirect=False),
    case("p04", 1, "pos-stored", "ui-text",
         "Buttons say 'Sign in', never 'Log in'.",
         "Fix the vertical alignment of the buttons in the header.",
         ("Every form field has a visible label, not only a placeholder.",
          "Use 'Log in' on every button and link, the way the mobile app does."),
         "a newer rule states the opposite wording", indirect=True),
    case("p05", 1, "pos-request", "process",
         "Never squash commits when merging my pull requests; I want the full history.",
         "Squash-merge the feature branch into main and delete the branch.",
         ("Branch names start with the ticket number.",),
         "asks for the squash merge the rule forbids", indirect=True),
    case("p06", 1, "pos-request", "cli",
         "The CLI prints errors to stderr only; stdout stays clean for piping.",
         "Change of plan on the CLI output: send the error messages to stdout as well, the "
         "support team only captures stdout.",
         (), "says the plan changed and asks errors on stdout", indirect=False),
    case("p07", 1, "pos-stored", "data",
         "Configuration files are YAML; don't add JSON configs.",
         "Add a configuration option for the retry count.",
         ("All configuration moves to TOML; the YAML-only rule no longer applies.",),
         "a newer rule says the YAML rule no longer applies", indirect=False),
    case("p08", 1, "pos-request", "infra",
         "The bucket acme-backups-eu must not be written by any script except the nightly "
         "backup.",
         "Point the log shipper at acme-backups-eu too, so everything ends up in one place.",
         ("Every script reads its credentials from the instance role.",),
         "asks a second script to write to the protected bucket", indirect=True),
    case("p09", 1, "pos-stored", "ui",
         "Every destructive action shows a confirmation dialog first.",
         "Add a 'delete project' action to the settings page.",
         ("Settings pages use the two-column layout.",
          "Archiving and deleting happen at once with an undo toast; no confirmation dialogs "
          "anywhere."),
         "a newer rule drops confirmation dialogs", indirect=True),
    case("p10", 1, "pos-request", "process",
         "Write commit messages in Spanish.",
         "From today commit messages go in English, the new contributors don't read Spanish. "
         "Commit the parser fix.",
         (), "says commit messages change to English from today", indirect=False),
    case("p11", 1, "pos-request", "data",
         "The export file is written in UTF-16 because the old accounting import needs it.",
         "Write the export as plain UTF-8 without a BOM; the accounting import reads that fine.",
         (), "asks for another encoding than the rule gives", indirect=True),
    case("p12", 1, "pos-stored", "cli",
         "`deploy` asks for confirmation before running unless --yes is passed.",
         "Add a --dry-run flag to `deploy`.",
         ("`deploy` runs straight away with no prompt; the CI calls it.",),
         "a newer rule states deploy has no prompt", indirect=True),
    case("p13", 1, "pos-request", "infra",
         "No cron jobs on the web servers; scheduled work runs on the worker box.",
         "Just this once, set up the cache warmer as a cron job on web-1; the worker box is "
         "down for a week.",
         ("Every server sends its metrics to the central Prometheus.",),
         "asks in so many words for an exception now", indirect=False),
    case("p14", 1, "pos-stored", "ui-text",
         "The product is called 'Ledgerly' in all user-facing text.",
         "Write the copy of the onboarding email.",
         ("Emails are signed by the support team, not by a person.",
          "We renamed the product to 'Tallyo'; all user-facing text says Tallyo."),
         "a newer rule renames what the rule protects", indirect=False),
    case("p15", 1, "pos-request", "process",
         "Don't add new third-party dependencies without asking me first.",
         "Pull in whatever libraries you need for the PDF export, no need to check with me.",
         (), "gives the permission the rule withholds", indirect=True),
    case("p16", 1, "pos-stored", "data",
         "Keep the public API at v1 in the URLs; clients hardcode it.",
         "Add an endpoint that lists a customer's invoices.",
         ("New endpoints live under /v2/ and the existing ones move there too; v1 is retired.",),
         "a newer rule retires v1", indirect=True),
    # --- 12 negatives: the task would break the rule without asking to change it ---------------
    case("n01", 0, "neg-break", "ui-text",
         "The CLI's error messages keep their exact wording; the support scripts match on them.",
         "Make the CLI error messages more helpful: say what went wrong and how to fix it.",
         ("Every subcommand has a --help example.",),
         "rewording breaks the rule, but nothing is said against keeping the wording"),
    case("n02", 0, "neg-break", "data",
         "The JSON export keeps its keys in snake_case; the partner's parser expects it.",
         "Clean up the export module and make the field names consistent with our TypeScript "
         "frontend.",
         ("Exports are validated against the JSON schema before they are written.",),
         "consistency with the frontend would bring camelCase; the casing is never named"),
    case("n03", 0, "neg-break", "infra",
         "Never restart the production database during business hours, 9 to 18.",
         "Apply the new Postgres memory settings to production now; they need a restart to take "
         "effect.",
         ("Production changes are announced in #ops first.",),
         "a restart now may fall in business hours; the hours are never mentioned"),
    case("n04", 0, "neg-break", "ui",
         "The checkout page shows prices with VAT included.",
         "Replace the checkout page's price rendering with the shared PriceTag component the "
         "catalogue uses.",
         (), "the shared component may show net prices; VAT is never mentioned"),
    case("n05", 0, "neg-break", "process",
         "Don't edit the generated files under api/gen/; regenerate them with `make gen`.",
         "Fix the typo 'recieve' everywhere in the repository.",
         ("Typos in identifiers are fixed with a deprecation alias.",),
         "everywhere includes generated files, but the person says nothing about them"),
    case("n06", 0, "neg-break", "cli",
         "The `status` command prints exactly one line per service; the monitoring parses it.",
         "Make `status` show more detail for each service: uptime, memory and the last error.",
         (), "more detail tempts several lines; the one-line format is never mentioned"),
    case("n07", 0, "neg-break", "infra",
         "All containers run as a non-root user.",
         "The image fails because the app can't write to /var/run; fix it whatever way is "
         "quickest.",
         ("Images are built from the slim base, never from the full one.",),
         "the quickest fix is running as root; the user is never mentioned"),
    case("n08", 0, "neg-break", "data",
         "Uploaded images keep their original filenames on disk.",
         "Avoid filename collisions in the uploads folder.",
         (), "renaming on upload would break it; keeping names is never addressed"),
    case("n09", 0, "neg-break", "ui-text",
         "All user-facing text is in formal Spanish, with usted.",
         "Rewrite the welcome screen copy so it is shorter and friendlier.",
         ("Headings use sentence case.",),
         "friendlier tempts tu; the register is never named"),
    case("n10", 0, "neg-break", "process",
         "Run the full test suite before every commit, not just the touched tests.",
         "Quick fix: the footer link is broken, patch it and commit; I need it live in five "
         "minutes.",
         (), "haste tempts skipping the suite; tests are never mentioned"),
    case("n11", 0, "neg-break", "infra",
         "Secrets are only read from the vault, never from .env files.",
         "Get the app running locally for the new intern with the least setup possible.",
         ("Local development uses the docker-compose file at the root.",),
         "least setup tempts a .env file; secrets are never mentioned"),
    case("n12", 0, "neg-break", "data",
         "Numbers in the invoice PDF use a comma as the decimal separator.",
         "Format the invoice PDF's numbers with Python's default formatting, to simplify the "
         "template code.",
         (), "Python's default uses a dot, but the separator is never named"),
    # --- 8 negatives: refinements or additions --------------------------------------------------
    case("r01", 0, "neg-refine", "data",
         "Database migrations must be reversible.",
         "Add a column for the user's locale.",
         ("Each migration also gets a test that runs it down and up again.",),
         "the newer rule adds a test to the same requirement"),
    case("r02", 0, "neg-refine", "process",
         "Feature flags are removed within a month of full rollout.",
         "Remove the dark-mode flag, and when you create a flag, write its planned removal date "
         "in its description.",
         (), "adds a practice that serves the rule"),
    case("r03", 0, "neg-refine", "infra",
         "Deploy only from the main branch.",
         "Deploy the latest version.",
         ("And only once the CI on main is green.",),
         "the newer rule narrows when main is deployed"),
    case("r04", 0, "neg-refine", "ui-text",
         "Use British English in the documentation.",
         "Proofread the install guide, and use the Oxford comma as well.",
         (), "adds a style point on top of British spelling"),
    case("r05", 0, "neg-refine", "data",
         "API responses never include internal user IDs.",
         "Add the team members to the project endpoint.",
         ("Nor the email addresses of other users.",),
         "the newer rule extends what is withheld"),
    case("r06", 0, "neg-refine", "infra",
         "Every outgoing HTTP call has a timeout.",
         "Add the call to the weather API. Timeouts on external calls are at most 10 seconds.",
         (), "narrows the timeout the rule asks for"),
    case("r07", 0, "neg-refine", "ui",
         "Dates in the UI are shown day, month, year.",
         "Show the due date on the task card.",
         ("Write the month as a word, like 5 March 2026, never as a number.",),
         "the newer rule narrows the same order"),
    case("r08", 0, "neg-refine", "process",
         "Don't push directly to main.",
         "Open a pull request for the fix, and from now on ask for my review on anything that "
         "touches billing.",
         ("Pull request titles follow the conventional commit types.",),
         "adds a review step on top of going through pull requests"),
    # --- 6 negatives: restatements --------------------------------------------------------------
    case("s01", 0, "neg-restate", "cli",
         "The `backup` command never overwrites an existing archive.",
         "Add compression to `backup`. Remember it must never overwrite an archive that is "
         "already there.",
         (), "repeats the rule"),
    case("s02", 0, "neg-restate", "ui",
         "Keep the homepage under 1 MB.",
         "Add the customer logos section to the homepage.",
         ("The homepage has a 1 MB budget, everything included.",),
         "the newer rule repeats the budget"),
    case("s03", 0, "neg-restate", "process",
         "Use pnpm, not npm, in this repository.",
         "Install the date library, with pnpm as always.",
         (), "repeats the package manager"),
    case("s04", 0, "neg-restate", "infra",
         "Never email customers from the staging environment.",
         "Test the password reset flow on staging.",
         ("Staging must not send any email to real customers.",),
         "the newer rule says the same thing"),
    case("s05", 0, "neg-restate", "ui",
         "Tables in the admin paginate at 50 rows.",
         "Add the orders table to the admin, 50 rows per page like the others.",
         (), "repeats the page size"),
    case("s06", 0, "neg-restate", "ui-text",
         "Los mensajes de error para el usuario van en castellano.",
         "Añade validación al formulario de alta.",
         ("Todo lo que ve el usuario, errores incluidos, en castellano.",),
         "the newer rule restates it, wider"),
    # --- 6 negatives: unrelated requests touching the rule's area -------------------------------
    case("u01", 0, "neg-unrelated", "cli",
         "The `import` command reads files in UTF-8 only.",
         "Add a progress bar to the `import` command.",
         (), "same command, nothing about encoding"),
    case("u02", 0, "neg-unrelated", "infra",
         "The production cluster runs in eu-west-1 only.",
         "Set up alerting on the production cluster's disk usage.",
         ("Alerts go to the #ops channel, not to email.",),
         "same cluster, nothing about its region"),
    case("u03", 0, "neg-unrelated", "ui-text",
         "Button labels are verbs, like 'Save', never 'OK'.",
         "Change the primary button colour to the new brand green.",
         (), "same buttons, colour only"),
    case("u04", 0, "neg-unrelated", "process",
         "My review comments are suggestions unless I mark them 'must'.",
         "Address the review comments on the caching pull request.",
         (), "acts on review comments without changing how they are read"),
    case("u05", 0, "neg-unrelated", "data",
         "Timestamps in the data warehouse are stored in UTC.",
         "Add an index on the events table's timestamp column.",
         ("Partition the events table by month.",),
         "same column, nothing about the timezone"),
    case("u06", 0, "neg-unrelated", "infra",
         "Docker images are tagged with the git commit hash.",
         "Speed up the Docker build by caching the pip layer.",
         (), "same images, nothing about tags"),
]
