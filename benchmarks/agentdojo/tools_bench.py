"""The tool selector, measured on a real catalog with ground truth nobody had to label.

    python benchmarks/agentdojo/tools_bench.py --dry      # the catalog and the labels, free
    python benchmarks/agentdojo/tools_bench.py            # 97 decisions, about 0.004 USD

`select_tools` is the only point in this package whose accuracy has never been measured. The
README has said so since the first release - *"accuracy not yet measured; the wiring is, and
it is the one that can cost you money"* - and it stayed unmeasured because a selection bench
needs a catalog, a set of realistic requests, and a ground truth for which groups each
request needs. Hand-labelling that is where it always stopped.

AgentDojo supplies all three for nothing. Its four suites are 74 real tools across a
workspace, a travel agent, a bank and a Slack, and each of its 97 user tasks carries a
`ground_truth()` that names the exact tool calls a correct run makes. So **the needed groups
are derived, not judged**: a group is needed for a task if the ground truth calls one of its
tools. There is no annotator here and therefore no annotator disagreement.

WHAT IS MEASURED, and the two numbers are not symmetric.

- **Survival.** Did every group the task actually needs survive the selection? Dropping a
  needed group costs capability - the agent cannot call what it cannot see - and that error
  is silent and unrecoverable within the turn. This is the number that has to be near 1.0
  before anyone switches the point on.
- **Reduction.** What fraction of the catalog's schema tokens did the selection remove? This
  is the prize, and it is worth nothing if survival is not first.

Reported per suite as well as overall, because a request in a four-application catalog is an
easier problem than a request inside one application, and quoting only the easy one would be
the usual way to flatter a selector.

THE CATALOG IS DELIBERATELY HARDER THAN THE SUITES. All four suites are merged into one
catalog of seventeen groups, so every task sees the tools of three applications it does not
need. That is the situation the point exists for - a harness binding a large catalog on every
step - and it is also the situation where a selector can do real damage, because most of what
it sees is genuinely irrelevant and the temptation to over-drop is strongest.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import pathlib
import sys
from collections import defaultdict
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

VERSION = "v1.2.2"

# name -> (about, tool name prefixes/exact names). Written from the tool lists, before any
# decision was run, and never adjusted afterwards.
GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "calendar": (
        "Create, move, cancel and search calendar events and their participants",
        (
            "create_calendar_event",
            "cancel_calendar_event",
            "reschedule_calendar_event",
            "search_calendar_events",
            "get_day_calendar_events",
            "add_calendar_event_participants",
        ),
    ),
    "email": (
        "Read, search, send and delete email, including drafts and unread mail",
        (
            "send_email",
            "delete_email",
            "get_draft_emails",
            "get_received_emails",
            "get_sent_emails",
            "get_unread_emails",
            "search_emails",
        ),
    ),
    "files": (
        "Create, read, append to, share, list and search documents in a drive",
        (
            "create_file",
            "append_to_file",
            "delete_file",
            "get_file_by_id",
            "list_files",
            "search_files",
            "search_files_by_filename",
            "share_file",
            "read_file",
        ),
    ),
    "contacts": (
        "Look up a person's contact details by name or by email address",
        ("search_contacts_by_email", "search_contacts_by_name"),
    ),
    "clock": ("What today's date is", ("get_current_day",)),
    "hotels": (
        "Find hotels in a city and their prices, addresses, ratings and reviews",
        (
            "get_all_hotels_in_city",
            "get_hotels_address",
            "get_hotels_prices",
            "get_rating_reviews_for_hotels",
            "reserve_hotel",
        ),
    ),
    "restaurants": (
        "Find restaurants in a city: cuisine, price, hours, diet, contact, booking",
        (
            "get_all_restaurants_in_city",
            "check_restaurant_opening_hours",
            "get_contact_information_for_restaurants",
            "get_cuisine_type_for_restaurants",
            "get_dietary_restrictions_for_all_restaurants",
            "get_price_for_restaurants",
            "get_rating_reviews_for_restaurants",
            "get_restaurants_address",
            "reserve_restaurant",
        ),
    ),
    "car_rental": (
        "Car rental companies in a city: types, fuel, price, address, reviews, booking",
        (
            "get_all_car_rental_companies_in_city",
            "get_car_fuel_options",
            "get_car_price_per_day",
            "get_car_rental_address",
            "get_car_types_available",
            "get_rating_reviews_for_car_rental",
            "reserve_car_rental",
        ),
    ),
    "flights": ("Flight schedules and prices between cities", ("get_flight_information",)),
    "traveller": ("The traveller's own saved profile and preferences", ("get_user_information",)),
    "accounts": (
        "Bank balance, IBAN and account holder details",
        ("get_balance", "get_iban", "get_user_info", "update_user_info"),
    ),
    "transactions": (
        "Send money, schedule and amend transfers, read transaction history",
        (
            "send_money",
            "schedule_transaction",
            "update_scheduled_transaction",
            "get_most_recent_transactions",
            "get_scheduled_transactions",
        ),
    ),
    "credentials": ("Change the account password", ("update_password",)),
    "channels": (
        "List Slack channels, their members, and add or remove people",
        (
            "get_channels",
            "get_users_in_channel",
            "add_user_to_channel",
            "invite_user_to_slack",
            "remove_user_from_slack",
        ),
    ),
    "messaging": (
        "Read and post Slack channel messages and direct messages",
        ("read_channel_messages", "send_channel_message", "send_direct_message", "read_inbox"),
    ),
    "web": ("Fetch and publish web pages", ("get_webpage", "post_webpage")),
}


def group_of(tool: str) -> str | None:
    for name, (_about, members) in GROUPS.items():
        if tool in members:
            return name
    return None


def catalog() -> list[dict[str, Any]]:
    return [{"name": n, "about": a} for n, (a, _m) in GROUPS.items()]


def schema_chars(suites: Any) -> dict[str, int]:
    """Rough size of each group's schemas, for the reduction figure. Chars, not tokens."""
    sizes: dict[str, int] = defaultdict(int)
    seen: set[str] = set()
    for suite in suites.values():
        for tool in suite.tools:  # a list of `Function`, not a mapping
            name = str(tool.name)
            g = group_of(name)
            if not g or name in seen:  # the same tool appears in more than one suite
                continue
            seen.add(name)
            size = len(name) + len(str(tool.description or ""))
            with contextlib.suppress(Exception):
                size += len(json.dumps(tool.parameters.model_json_schema()))
            sizes[g] += size
    return dict(sizes)


def build() -> tuple[list[dict[str, Any]], dict[str, int]]:
    from agentdojo.task_suite.load_suites import get_suites

    suites = get_suites(VERSION)
    sizes = schema_chars(suites)
    cases = []
    for suite_name, suite in suites.items():
        for task_id, task in suite.user_tasks.items():
            env = suite.load_and_inject_default_environment({})
            try:
                calls = task.ground_truth(env)
            except Exception:
                continue
            needed = sorted({g for c in calls if (g := group_of(c.function))})
            if not needed:
                continue
            cases.append(
                {
                    "id": f"tl-{suite_name}-{task_id}",
                    "suite": suite_name,
                    "purpose": task.PROMPT,
                    "needed": needed,
                    "n_calls": len(calls),
                }
            )
    return cases, sizes


async def run(cases: list[dict], sizes: dict[str, int], provider: str) -> list[dict]:
    from sanchopanza.providers import create
    from sanchopanza.squire import Squire

    if provider == "jev":
        # Through the window bench's recording: the 97 selections ask the same state, so a
        # rerun replays them for free and the raw probabilities are on disk (method rule 9).
        from tools_window import decider as recorded_or_live

        decider = recorded_or_live(offline=False)
    else:
        decider = create(provider)
    squire = Squire(decider)
    squire._t = squire.thresholds.with_(max_decisions=1000)  # noqa: SLF001 - bench, not production
    out = []
    total = sum(sizes.values()) or 1
    for case in cases:
        selection = await squire.select_tools(purpose=case["purpose"], catalog=catalog())
        kept = set(selection.keep)
        needed = set(case["needed"])
        kept_chars = sum(sizes.get(g, 0) for g in kept)
        out.append(
            {
                **case,
                "kept": sorted(kept),
                "dropped": sorted(set(GROUPS) - kept),
                "survived": needed <= kept,
                "missing": sorted(needed - kept),
                "reduction": 1 - kept_chars / total,
            }
        )
    out.append({"_cost_usd": squire.meter.cost_usd, "_decisions": squire.meter.decisions})
    return out


def report(rows: list[dict]) -> str:
    meta = rows[-1]
    rows = [r for r in rows if "_cost_usd" not in r]
    lines = [
        "| Suite | tasks | needed groups survive | mean catalog reduction |",
        "|---|---|---|---|",
    ]
    by_suite: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_suite[r["suite"]].append(r)
    for suite, group in sorted(by_suite.items()):
        ok = sum(1 for r in group if r["survived"])
        red = sum(r["reduction"] for r in group) / len(group)
        lines.append(f"| {suite} | {len(group)} | {ok}/{len(group)} | {red:.0%} |")
    ok = sum(1 for r in rows if r["survived"])
    red = sum(r["reduction"] for r in rows) / len(rows)
    lines.append(f"| **all** | **{len(rows)}** | **{ok}/{len(rows)}** | **{red:.0%}** |")
    failures = [r for r in rows if not r["survived"]]
    if failures:
        lines += ["", "Tasks that lost a group they needed:", ""]
        for r in failures[:20]:
            lines.append(f"- `{r['id']}` dropped {r['missing']} - {r['purpose'][:90]}")
    lines += ["", f"{meta['_decisions']} decisions, {meta['_cost_usd']:.4f} USD."]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--provider", default="jev")
    p.add_argument("--out", default="docs/results/2026-09-24-tools")
    p.add_argument("--dry", action="store_true")
    args = p.parse_args()

    cases, sizes = build()
    print(
        f"{len(cases)} tasks, catalog of {len(GROUPS)} groups, "
        f"{sum(sizes.values())} characters of schema"
    )
    spread = defaultdict(int)
    for c in cases:
        spread[len(c["needed"])] += 1
    print(f"groups needed per task: {dict(sorted(spread.items()))}")
    if args.dry:
        print("\n--dry: nothing called.")
        return 0

    rows = asyncio.run(run(cases, sizes, args.provider))
    text = report(rows)
    print("\n" + text)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(
        json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    (out / "summary.md").write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
