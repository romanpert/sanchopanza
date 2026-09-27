"""The selector at the scale it was written for: a 250-group catalog.

    python benchmarks/agentdojo/tools_wide.py --dry     # the catalog, free
    python benchmarks/agentdojo/tools_wide.py           # 97 selections, about 0.08 USD

`points/tools.py` justifies itself with a production agent binding 250 schemas at 25-38k
tokens per step. Everything measured so far has been the AgentDojo catalog of 16 groups, so
the point has never been run at the scale it exists for, and two things only appear there:

1. **Chunking.** Above `GROUPS_PER_CALL = 48` the catalog is split, asked in parallel, and
   the probabilities merged before one policy pass. No bench has ever exercised that path.
2. **The prior shifts.** With 16 groups, 3 are needed and 13 are noise. With 250, 3 are
   needed and 247 are noise, so a per-group question answered independently has 247 chances
   to produce a false positive and the selection can silently stop reducing anything.

The 234 padding groups are written from domains an enterprise harness actually carries -
ticketing, CRM, CI, observability, payroll, and so on. **None of them is ever needed**: the
ground truth is unchanged, because the padding cannot be called by any AgentDojo task. So
survival can only get worse and reduction can only get harder, which is the right direction
for a stress test: the padding is a pure distractor set.

What this cannot tell you is whether a *real* 250-tool catalog behaves like a padded one. Real
catalogs have near-duplicates, overlapping domains and ambiguous names; this padding is
deliberately distinct. Read the result as an upper bound on how well it scales, not as the
scaling behaviour of a genuine large catalog.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tools_bench import GROUPS, build, catalog  # noqa: E402

# 234 distractor groups over domains a large harness carries. Written once, never tuned.
DOMAINS: dict[str, list[str]] = {
    "ticketing": ["issues", "sprints", "backlog", "epics", "releases", "boards", "labels"],
    "crm": ["leads", "opportunities", "accounts", "quotes", "campaigns", "pipelines"],
    "ci": ["builds", "pipelines_ci", "artifacts", "runners", "deployments", "rollbacks"],
    "observability": ["metrics", "traces", "logs", "alerts", "dashboards", "incidents", "oncall"],
    "payroll": ["salaries", "benefits", "timesheets", "expenses", "reimbursements"],
    "hr": ["candidates", "interviews", "onboarding", "reviews", "leave", "org_chart"],
    "legal": ["contracts", "clauses", "signatures", "matters", "disclosures"],
    "inventory": ["stock", "warehouses", "shipments", "suppliers", "purchase_orders"],
    "support": ["tickets", "macros", "sla", "csat", "knowledge_base"],
    "analytics": ["reports", "cohorts", "funnels", "experiments", "segments"],
    "infra": ["instances", "volumes", "networks", "dns", "certificates", "secrets_store"],
    "data": ["datasets", "schemas", "jobs", "lineage", "quality_checks", "catalogs"],
    "security": ["findings", "policies", "audit_log", "access_reviews", "keys"],
    "marketing": ["ads", "audiences", "creatives", "attribution", "newsletters"],
    "commerce": ["orders", "refunds", "subscriptions", "coupons", "taxes", "payouts"],
    "docs": ["pages", "spaces", "comments_docs", "templates", "exports"],
    "design": ["files_design", "components", "prototypes", "handoff"],
    "translation": ["locales", "strings", "glossaries", "reviews_i18n"],
    "telephony": ["calls", "voicemail", "numbers", "recordings", "ivr"],
    "maps": ["geocoding", "routes", "places", "isochrones"],
    "media": ["uploads", "transcodes", "captions", "thumbnails"],
    "iot": ["devices", "firmware", "telemetry", "fleets"],
    "education": ["courses", "enrolments", "assignments", "grades"],
    "health": ["appointments_h", "records", "prescriptions", "billing_h"],
    "energy": ["meters", "tariffs", "consumption", "outages"],
    "logistics": ["routes_l", "drivers", "vehicles", "deliveries", "manifests"],
    "government": ["filings", "permits", "registries", "notices"],
    "research": ["papers", "citations_r", "datasets_r", "preprints"],
    "social": ["posts", "followers", "mentions", "schedules"],
    "banking_ext": ["cards", "disputes", "statements", "forex"],
    "erp": ["ledger", "journals", "cost_centres", "assets", "depreciation"],
    "procurement": ["vendors", "rfqs", "contracts_p", "approvals", "catalogues"],
    "manufacturing": ["work_orders", "bom", "quality", "maintenance", "shifts"],
    "realestate": ["listings", "viewings", "tenancies", "valuations"],
    "insurance": ["policies_i", "claims", "quotes_i", "underwriting"],
    "travel_corp": ["bookings", "policies_t", "itineraries", "receipts"],
    "events": ["venues", "agendas", "speakers", "registrations", "badges"],
    "gaming": ["players", "matches", "leaderboards", "inventory_g"],
    "streaming": ["channels_s", "viewers", "playlists", "rights"],
    "agriculture": ["fields", "crops", "irrigation", "yields"],
    "aviation": ["flights_a", "crews", "slots", "maintenance_a"],
    "maritime": ["vessels", "ports", "cargo", "charters"],
    "construction": ["sites", "crews_c", "permits_c", "inspections"],
    "nonprofit": ["donors", "grants", "volunteers", "programmes"],
    "publishing": ["titles", "authors", "royalties", "printruns"],
    "museum": ["collections", "loans", "conservation", "exhibitions"],
    "sports": ["fixtures", "squads", "injuries", "transfers"],
    "weather": ["forecasts", "stations", "warnings", "climate"],
    "telecom": ["subscribers", "plans", "usage_t", "roaming"],
    "waste": ["collections_w", "routes_w", "bins", "recycling"],
}


def wide_catalog() -> list[dict]:
    """The real 16 groups plus distractors, to 250."""
    groups = catalog()
    for domain, members in DOMAINS.items():
        for member in members:
            groups.append(
                {
                    "name": f"{domain}_{member}",
                    "about": f"{member.replace('_', ' ')} in the {domain} system: "
                    f"list, read, create and update {member.replace('_', ' ')}",
                }
            )
    return groups[:250]


async def run(cases: list[dict], groups: list[dict]) -> list[dict]:
    from sanchopanza.providers import create
    from sanchopanza.squire import Squire

    squire = Squire(create("jev", api_key=os.environ.get("TYPESAFE_API_KEY")))
    squire._t = squire.thresholds.with_(max_decisions=5000, max_usd=1.0)  # noqa: SLF001
    names = [g["name"] for g in groups]
    out = []
    for case in cases:
        selection = await squire.select_tools(purpose=case["purpose"], catalog=groups)
        kept = set(selection.keep)
        needed = set(case["needed"])
        out.append(
            {
                **case,
                "kept": sorted(kept),
                "survived": needed <= kept,
                "missing": sorted(needed - kept),
                "n_kept": len(kept),
                "padding_kept": len([g for g in kept if g not in GROUPS]),
                "reduction_groups": 1 - len(kept) / len(names),
            }
        )
    out.append({"_cost_usd": squire.meter.cost_usd, "_decisions": squire.meter.decisions})
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="docs/results/2026-09-24-tools/wide.json")
    p.add_argument("--dry", action="store_true")
    args = p.parse_args()

    cases, _sizes = build()
    groups = wide_catalog()
    print(
        f"{len(cases)} tasks, catalog of {len(groups)} groups "
        f"({len(GROUPS)} real, {len(groups) - len(GROUPS)} distractors)"
    )
    print(f"chunks per selection: {-(-len(groups) // 48)}")
    if args.dry:
        print("\n--dry: nothing called.")
        return 0

    rows = asyncio.run(run(cases, groups))
    meta = rows[-1]
    rows = [r for r in rows if "_cost_usd" not in r]
    ok = sum(1 for r in rows if r["survived"])
    kept = sum(r["n_kept"] for r in rows) / len(rows)
    pad = sum(r["padding_kept"] for r in rows) / len(rows)
    red = sum(r["reduction_groups"] for r in rows) / len(rows)
    print("\n| catalog | tasks | survive | mean kept | distractors kept | reduction |")
    print("|---|---|---|---|---|---|")
    print(
        f"| 250 groups | {len(rows)} | {ok}/{len(rows)} = {ok / len(rows):.0%} | "
        f"{kept:.1f} | {pad:.1f} | {red:.0%} |"
    )
    failures = [r for r in rows if not r["survived"]]
    if failures:
        print("\nTasks that lost a group they needed:")
        for r in failures[:12]:
            print(f"  {r['id']:34} dropped {r['missing']} - {r['purpose'][:60]}")
    print(f"\n{meta['_decisions']} decisions, {meta['_cost_usd']:.4f} USD.")
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows + [meta], indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
