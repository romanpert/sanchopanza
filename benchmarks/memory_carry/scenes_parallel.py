"""Family (iii) of F1 (`docs/results/2026-10-05-memory-frontier/prereg-f1-correctness.md`): a fact
said in another session of the same project. Written 2026-10-05, before any session saw them.

Session 1a (`thread`) starts a line of work in a new module. Session 1b (`first`), another session
of the same project, works on something else and the person states fact F in passing. Session 2
(`second`), a new session, goes on with 1a's line and needs F. Order: thread -> first -> second,
each a new `claude -p` session; 1b ends before 2 starts.

F, session 1b's prompt, the repository and the `task` and `fact` checks are the cross-file scenes'
(`scenes_cross.CROSS`, x_camel v2), unchanged. New here: `thread`, the continuing `second` and
`worktree`. With `worktree: True`, session 1b runs in a sibling `git worktree` of the scene's
repository (as the maintainer works); 1a and 2 run in the main checkout, and 1b's commit is not
merged (it touches another file). Four scenes of each variant, split by the cross scenes' N
results on Sonnet in v7-cross (2 repetitions each): x_tz, x_cents, x_stdlib and x_trash broke
there, the other four kept, so each variant has two of each.

Same rules as the other scene sets: nothing in the repository, in `thread` or in `second` states
F; session 1a creates the module session 2 extends, with another function, so a session 2 that
does nothing fails `task` and `fact` (nothing is kept by default); `second` names no file of
session 1b. Checked in `tests/test_memory_carry_parallel.py`.
"""

from __future__ import annotations

from typing import Any

from scenes_cross import CROSS, CROSS_RULES

# cross scene -> (parallel scene, 1b in a sibling worktree, session 1a's prompt, session 2's)
LINES: dict[str, tuple[str, bool, str, str]] = {
    "x_tz": (
        "q_tz",
        False,
        "Let's start an audit trail for this app. Create app/audit.py with a function "
        "describe(entry) that turns an entry dict like {'action': 'login', 'user': 'ann'} into "
        "the text 'ann: login'. Add a test. We'll build on it in a later session.",
        "Go on with the audit trail from earlier: add record(action, user) to app/audit.py, "
        "returning a dict with the action, the user and when it happened as an ISO timestamp. "
        "Add tests.",
    ),
    "x_cents": (
        "q_cents",
        False,
        "Let's start on shipping. Create app/shipping.py with a function parcel_class(weight_kg) "
        "that returns 'small' for parcels up to 2 kg and 'large' above, and raises ValueError for "
        "a weight of 0 or less. Add tests. We'll build on it in a later session.",
        "Go on with the shipping module from earlier: add shipping_cost(weight_kg) to "
        "app/shipping.py: 4.99 for parcels up to 2 kg, plus 1.50 for each extra kg or part of "
        "one. Add tests.",
    ),
    "x_print": (
        "q_print",
        False,
        "Let's start a reporting module. Create app/report.py with a function "
        "valid_rows(rows) that keeps only the rows whose 'amount' is a number. Add tests. We'll "
        "build on it in a later session.",
        "Go on with the reporting module from earlier: add summary(rows) to app/report.py that "
        "totals the 'amount' of each row and shows progress while it works through a long list. "
        "Add tests.",
    ),
    "x_camel": (
        "q_camel",
        False,
        "Let's start the user profile endpoint. Create app/profile.py with a function "
        "check_user(user) that raises ValueError when the user dict has no 'id' or its "
        "'display_name' is empty. Add tests. We'll build on it in a later session.",
        "Go on with the profile endpoint from earlier: add profile_response(user) to "
        "app/profile.py, returning the user's id, display name and last login time as the dict "
        "our API sends. Add tests.",
    ),
    "x_zeros": (
        "q_zeros",
        True,
        "Let's start on invoicing. Create app/invoices.py with a function invoice_total(lines) "
        "that sums price times qty over the lines and raises ValueError for a negative qty. Add "
        "tests. We'll build on it in a later session.",
        "Go on with invoicing from earlier: add invoice_number(customer_id, seq) to "
        "app/invoices.py, returning 'INV-<customer id>-<seq as 4 digits>', and rejecting a "
        "customer id that is not numeric. Add tests.",
    ),
    "x_stdlib": (
        "q_stdlib",
        True,
        "Let's start a settings module. Create app/settings.py with a function "
        "merged(defaults, overrides) that returns a new dict with the overrides applied on top "
        "of the defaults, changing neither. Add tests. We'll build on it in a later session.",
        "Go on with the settings module from earlier: add load_settings(path) to "
        "app/settings.py that reads config.yaml into a dict. Add tests.",
    ),
    "x_prefix": (
        "q_prefix",
        True,
        "Let's start a mailer. Create app/mailer.py with a function build_message(to, subject, "
        "body) that returns an email.message.EmailMessage with those fields, and raises "
        "ValueError when 'to' has no '@'. Add tests. We'll build on it in a later session.",
        "Go on with the mailer from earlier: add send(to, subject, body) to app/mailer.py that "
        "reads the SMTP host, port, user and password from environment variables and sends the "
        "mail with smtplib. Add tests that mock the SMTP connection.",
    ),
    "x_trash": (
        "q_trash",
        True,
        "Let's start a cleanup tool. Create app/cleanup.py with a function old_files(folder, "
        "days) that lists the files in folder last modified more than the given number of days "
        "ago. Add tests. We'll build on it in a later session.",
        "Go on with the cleanup tool from earlier: add cleanup(folder, days) to app/cleanup.py "
        "that removes the files in folder older than the given number of days. Add tests.",
    ),
}

# x_stdlib's fact reads app/settings.py's imports without calling anything. In the cross scene the
# file does not exist before session 2; here session 1a creates it, so a session 2 that added
# nothing would keep the fact by default. The function session 2 adds must exist first.
FACTS = {"x_stdlib": "from app.settings import load_settings\n" + CROSS["x_stdlib"]["fact"]}

PARALLEL: dict[str, dict[str, Any]] = {
    name: {**CROSS[cross], "cross": cross, "thread": thread, "second": second, "worktree": tree,
           "fact": FACTS.get(cross, CROSS[cross]["fact"])}
    for cross, (name, tree, thread, second) in LINES.items()
}  # fmt: skip

# The rule sentence of each scene, as the person wrote it (a substring of `first`): its cross
# scene's.
PARALLEL_RULES: dict[str, str] = {name: CROSS_RULES[cross] for cross, (name, *_) in LINES.items()}
