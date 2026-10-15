"""Jev 1.14 against 1.13, both live today, on lot L4: find_in_repo and candor on public data.

    python benchmarks/jev114/l4.py --run --limit 2       # free: replay only, first 2 items
    python benchmarks/jev114/l4.py --run --live          # spends (caps in code)
    python benchmarks/jev114/l4.py                       # analysis of the scored files, free
    python benchmarks/jev114/l4.py --seal                # seal prereg.md and the code

Pre-registered in docs/results/2026-10-15-jev114-l4/prereg.md. The inputs, questions and
thresholds are those of the originals, built by their own code:

- `find`  : benchmarks/find/swebench.py (docs/results/2026-09-29-find), 117 SWE-bench
            Verified issues, `Squire.triage_many` over the 60-fragment BM25 shortlist.
- `tau2`  : benchmarks/candor_external/tau2.py, 320 simulations, `check_done`.
- `errata`: benchmarks/candor_external/errata.py, 110 items, the holistic `misstates` question.

Three arms per item:
- `rec13`: the answers recorded on 2026-09-29 (jev-1.13.0), replayed for free, the historical
           reference. A miss means the input is no longer the one recorded.
- `j13r` : jev-1.13.0 asked again today.
- `j14`  : jev-1.14.0 asked today.
`j13r` and `j14` are asked one after the other on each item, the first alternating with the
item's position in a seeded random launch order. Every live call goes through `CappedDecider`
on the shared ledger (`$SANCHOPANZA_JEV114_RUN/ledger.json`, C:/sp-runs/jev114 by default,
LEDGER_CAP_USD) and this lot's cap (BATCH_CAP_USD), at most CONCURRENCY at once. Answers are
recorded per arm in OUT (hashed keys, no text), so a relaunch only asks what is not recorded.

The key comes from TYPESAFE_API_KEY or, failing that, from the `.env` file SANCHOPANZA_KEYS_ENV
names (machine-local, never printed).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for extra in ("src", "benchmarks/candor", "benchmarks/candor_external", "benchmarks/find"):
    sys.path.insert(0, str(REPO / extra))
sys.path.insert(0, str(HERE))

import l4_stats as st  # noqa: E402

from sanchopanza.contract import Decision  # noqa: E402

OUT = REPO / "docs" / "results" / "2026-10-15-jev114-l4"
RUN_DIR = Path(os.environ.get("SANCHOPANZA_JEV114_RUN", "C:/sp-runs/jev114"))
LEDGER_PATH = RUN_DIR / "ledger.json"
LEDGER_CAP_USD = 4.50
BATCH = "jev114-l4"
BATCH_CAP_USD = 0.60
CONCURRENCY = 4
MODELS = {"j13r": "jev-1.13.0", "j14": "jev-1.14.0"}
LIVE_ARMS = tuple(MODELS)
SETS = ("find", "tau2", "errata")  # the order of a live run: the primary metrics first
ORDER_SEED = 20261015
FAMILY = (
    "find_prod_any@1", "find_prod_any@5", "find_free_any@1", "find_free_any@5",
    "tau2_accuracy_at_cut", "tau2_auc",
    "errata_correct_at_cut", "errata_auc", "errata_auc_unverified",
)  # fmt: skip


def load_key() -> None:
    """TYPESAFE_API_KEY into this process's environment from SANCHOPANZA_KEYS_ENV if unset."""
    if os.environ.get("TYPESAFE_API_KEY"):
        return
    named = os.environ.get("SANCHOPANZA_KEYS_ENV", "")
    if not named or not Path(named).is_file():
        raise SystemExit("TYPESAFE_API_KEY unset and SANCHOPANZA_KEYS_ENV names no file")
    for line in Path(named).read_text(encoding="utf-8").splitlines():
        name, _, value = line.strip().partition("=")
        if name.strip() == "TYPESAFE_API_KEY" and value.strip():
            os.environ["TYPESAFE_API_KEY"] = value.strip().strip('"').strip("'")
            return
    raise SystemExit("no TYPESAFE_API_KEY line in the file SANCHOPANZA_KEYS_ENV names")


def preflight_or_stop() -> None:
    """`jev-preflight` for each model: the service answers, and with the model asked for."""
    from sanchopanza.providers.jev import apreflight

    for model in MODELS.values():
        result = asyncio.run(apreflight(model=model))
        if not result.ok or result.model != model:
            raise SystemExit(f"preflight {model}: {result.reason}, served {result.model}")
        print(f"preflight {model}: ok", file=sys.stderr)


# ---- one arm --------------------------------------------------------------------------------


class Arm:
    """Recorded answers first; on a miss, one live call through the cap, recorded on success.
    Counts what it could not answer, and what every answer cost (recorded or live)."""

    def __init__(self, name: str, path: Path, model: str | None, live: Any, gate: Any) -> None:
        from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider

        self.name, self.path, self.model, self.gate = name, path, model, gate
        self.recorded = RecordedDecider.from_file(path, model=model)
        self.writer = RecordingDecider(live, path) if live is not None else None
        self.failures = 0
        self.live_calls = 0
        self.live_usd = 0.0
        self.usd = 0.0

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Decision:
        found = await self.recorded.decide(point, state, questions)
        if found.answers:
            self.usd += found.cost_usd
            return found
        if self.writer is None:
            self.failures += 1
            return Decision(point, {}, self.name, "-", error="not recorded, no live decider")
        async with self.gate:
            try:
                decision = await self.writer.decide(point, state, questions)
            except Exception as error:  # noqa: BLE001 - a refusal or outage is counted
                self.failures += 1
                return Decision(point, {}, self.name, "-", error=type(error).__name__)
        self.live_calls += 1
        self.live_usd += decision.cost_usd
        self.usd += decision.cost_usd
        if decision.failed or not decision.answers:
            self.failures += 1
        elif self.model and decision.model != self.model:
            raise SystemExit(f"{self.name}: asked {self.model}, served {decision.model}")
        return decision


def arms(set_name: str, live: bool) -> dict[str, Arm]:
    gate = asyncio.Semaphore(CONCURRENCY)
    capped: dict[str, Any] = {}
    if live:
        from sanchopanza.budget import SpendLedger
        from sanchopanza.providers import CappedDecider
        from sanchopanza.providers.jev import JevDecider

        ledger = SpendLedger(LEDGER_PATH, cap_usd=LEDGER_CAP_USD)
        for name, model in MODELS.items():
            inner = JevDecider(model=model, long_context=False, images=False)
            capped[name] = CappedDecider(inner, ledger=ledger, batch=BATCH, max_usd=BATCH_CAP_USD)
    out = {
        name: Arm(name, OUT / f"{set_name}-answers-{name}.jsonl", model, capped.get(name), gate)
        for name, model in MODELS.items()
    }
    if set_name == "find":
        import swebench

        out["rec13"] = Arm("rec13", swebench.ANSWERS, None, None, gate)
    return out


async def interleaved(position: int, ask: Callable[[str], Any]) -> dict[str, Any]:
    """`ask(arm)` for both live arms, one after the other, the first alternating."""
    order = LIVE_ARMS if position % 2 == 0 else LIVE_ARMS[::-1]
    return {name: await ask(name) for name in order}


def launch_order(n: int) -> list[int]:
    """A seeded random order of the items, so a cap reached part way leaves out a random
    subset rather than the last repositories or files."""
    order = list(range(n))
    random.Random(ORDER_SEED).shuffle(order)
    return order


async def shuffled_gather(one: Callable[[int, dict[str, Any]], Any], items: list) -> list:
    """`one(position, item)` for every item, launched in `launch_order`, at most CONCURRENCY
    calls in flight (the arms' gate); rows come back in the items' order."""
    order = launch_order(len(items))
    done = await asyncio.gather(*(one(rank, items[i]) for rank, i in enumerate(order)))
    by_index = dict(zip(order, done, strict=True))
    return [by_index[i] for i in range(len(items))]


# ---- find -----------------------------------------------------------------------------------


def find_rankings(keys: list[str], verdicts: list[tuple[bool, float | None]]) -> dict[str, list]:
    """Files ranked two ways from one tournament over the shortlist (keys in BM25 order).

    `prod`: the registered product ranking (swebench.one): kept fragments first by p, then
    BM25, then the rest of the shortlist by BM25. `free`: no cut, every fragment by its last p,
    then BM25; an unanswered fragment ranks last."""
    import swebench

    kept = [(i, p) for i, (keep, p) in enumerate(verdicts) if keep]
    kept.sort(key=lambda t: (-(t[1] if t[1] is not None else 0.5), t[0]))
    first = [keys[i] for i, _ in kept]
    prod = first + [k for k in keys if k not in set(first)]

    def last_p(i: int) -> tuple[float, int]:
        p = verdicts[i][1]
        return (-(p if p is not None else -1.0), i)

    free = sorted(range(len(keys)), key=last_p)
    return {
        "prod": swebench.files_ranked(prod),
        "free": swebench.files_ranked([keys[i] for i in free]),
    }


async def find_one(position: int, row: dict[str, Any], arms_: dict[str, Arm]) -> dict[str, Any]:
    import swebench

    from sanchopanza import Squire
    from sanchopanza.context.repo import PURPOSE, chunks
    from sanchopanza.policy import Thresholds
    from sanchopanza.select import index_of

    root = swebench.checkout(row["repo"], row["base_commit"])
    query = row["problem_statement"]
    gold = swebench.gold_files(row["patch"])
    fragments = chunks(root)
    index = index_of(fragments)
    short = index.top(query, swebench.SHORTLIST)
    keys = [fragments[i].key for i, _ in short]
    pages = [(fragments[i].title, fragments[i].text) for i, _ in short]
    shortlisted = {k.rsplit(":", 1)[0] for k in keys}
    out: dict[str, Any] = {"id": row["instance_id"], "repo": row["repo"],
                           "cluster": row["repo"],
                           "gold": gold,
                           "ceiling": any(g in shortlisted for g in gold)}  # fmt: skip

    async def ask(name: str) -> dict[str, Any]:
        arm = arms_[name]
        failures, usd, t0 = arm.failures, arm.usd, time.time()
        squire = Squire(arm, thresholds=Thresholds(max_usd=0.05, max_decisions=50))
        verdicts = await squire.triage_many(purpose=PURPOSE.format(query=query), pages=pages)
        ranked = find_rankings(keys, verdicts)
        return {
            "prod": swebench.hits(ranked["prod"], gold),
            "free": swebench.hits(ranked["free"], gold),
            "kept": sum(keep for keep, _ in verdicts),
            "failed": arm.failures > failures,
            "usd": round(arm.usd - usd, 6),
            "s": round(time.time() - t0, 2),
        }

    out |= await interleaved(position, ask)
    out["rec13"] = await ask("rec13")
    return out


async def run_find(live: bool, limit: int | None) -> list[dict[str, Any]]:
    import swebench

    arms_ = arms("find", live)
    rows = swebench.instances()
    order = launch_order(len(rows))[:limit]
    out = []
    for rank, i in enumerate(order):  # one checkout at a time: the clones are shared
        out.append(await find_one(rank, rows[i], arms_))
        spent = sum(a.live_usd for a in arms_.values())
        print(f"find {rank + 1}/{len(order)} {rows[i]['instance_id']} "
              f"{spent:.4f} USD", file=sys.stderr, flush=True)  # fmt: skip
    return out


# ---- candor on public data ----------------------------------------------------------------


def _rec13_truth(store: Any, arm_point: str, state: Any, qs: Mapping[str, Any], key: str) -> Any:
    import monitors

    row = store.get(monitors._key(arm_point, {"s": state, "q": sorted(qs)}))
    if row is None:
        return None
    d = monitors.decision_of(row, "")
    return None if d.failed else d.answer(key).truth


async def run_errata(live: bool, limit: int | None) -> list[dict[str, Any]]:
    import errata
    import monitors

    arms_ = arms("errata", live)
    store = monitors.Store(errata.ANSWERS)
    items = errata.items()[:limit]
    qs = {"misstates": monitors.MISSTATES}

    async def one(position: int, item: dict[str, Any]) -> dict[str, Any]:
        state = monitors.holistic_state(item)

        async def ask(name: str) -> float | None:
            d = await arms_[name].decide("misstates", state, qs)
            return None if d.failed or not d.answers else d.answer("misstates").truth

        keep = ("id", "kind", "positive", "task", "unverified")
        return {k: item[k] for k in keep} | {"cluster": item["task"]} | (
            await interleaved(position, ask)
        ) | {"rec13": _rec13_truth(store, "jevmisstates", state, qs, "misstates")}  # fmt: skip

    return await shuffled_gather(one, items)


def tau2_tasks() -> dict[str, str]:
    """Item id -> `domain:task_id`, the cluster of the four trials and four agent models."""
    import tau2

    out = {}
    for name in tau2.FILES:
        sims = json.loads((tau2.DIR / name).read_text(encoding="utf-8"))["simulations"]
        for sim in sims:
            item_id = f"{name.split('_gpt-4.1-2025')[0]}:{sim['id']}"
            out[item_id] = f"{name.split('_')[1]}:{sim['task_id']}"
    return out


async def run_tau2(live: bool, limit: int | None) -> list[dict[str, Any]]:
    import monitors
    import tau2

    from sanchopanza.points import completion

    arms_ = arms("tau2", live)
    store = monitors.Store(tau2.ANSWERS)
    items = tau2.items()[:limit]
    tasks = tau2_tasks()

    async def one(position: int, item: dict[str, Any]) -> dict[str, Any]:
        state, qs = completion.questions(task=item["task"], record=item["record"])

        async def ask(name: str) -> float | None:
            d = await arms_[name].decide("completion", state, qs)
            return None if d.failed or not d.answers else d.answer("done").truth

        keep = ("id", "model", "domain", "done")
        return {k: item[k] for k in keep} | {"cluster": tasks[item["id"]]} | (
            await interleaved(position, ask)
        ) | {"rec13": _rec13_truth(store, "jevcompletion", state, qs, "done")}  # fmt: skip

    return await shuffled_gather(one, items)


# ---- analysis -------------------------------------------------------------------------------


def _answered(rows: list[dict[str, Any]], *arm_names: str) -> list[dict[str, Any]]:
    return [r for r in rows if all(r.get(a) is not None for a in arm_names)]


def _failures(rows: list[dict[str, Any]], failed: Callable[[dict, str], bool]) -> dict[str, Any]:
    n = len(rows) or 1
    counts = {arm: sum(failed(r, arm) for r in rows) for arm in ("rec13", *LIVE_ARMS)}
    return counts | {"gap": round((counts["j14"] - counts["j13r"]) / n, 4)}


def _as_wrong(rows: list[dict[str, Any]], right: Callable[[dict, str], bool]) -> dict[str, Any]:
    """Sensitivity: every item, a failed answer counted as wrong."""
    clusters = [r["cluster"] for r in rows]
    return st.paired_binary([right(r, "j14") for r in rows], [right(r, "j13r") for r in rows],
                            clusters)  # fmt: skip


#: The 2026-09-29 baselines the registered F1 and F2 compare against (summary.json there).
FIND_FILE_BM25_ANY5 = 0.3504
FIND_FRAG_BM25_ANY1 = 0.1368


def analyse_find(rows: list[dict[str, Any]]) -> dict[str, Any]:
    clean = [r for r in rows if not (r["j13r"]["failed"] or r["j14"]["failed"])]
    clusters = [r["cluster"] for r in clean]
    out: dict[str, Any] = {"n": len(rows), "paired": len(clean), "comparisons": {}, "arms": {},
                           "failures": _failures(rows, lambda r, a: r[a]["failed"])}  # fmt: skip
    for arm in ("rec13", *LIVE_ARMS):
        group = [r for r in rows if not r[arm]["failed"]]
        n = len(group) or 1
        costs = sorted(r[arm]["usd"] for r in group)
        summary = {
            "n": len(group),
            **{f"{mode}_{m}": round(sum(r[arm][mode][m] for r in group) / n, 4)
               for mode in ("prod", "free") for m in ("any@1", "any@5", "any@10", "all@5")},
            "usd_total": round(sum(costs), 4),
            "usd_median": costs[len(costs) // 2] if costs else None,
            "kept_mean": round(sum(r[arm]["kept"] for r in group) / n, 2),
        }  # fmt: skip
        out["arms"][arm] = summary | {"registered": find_registered(summary)}
    out["ceiling"] = round(sum(r["ceiling"] for r in rows) / (len(rows) or 1), 4)
    for mode in ("prod", "free"):
        for m in ("any@1", "any@5"):
            name = f"find_{mode}_{m}"
            out["comparisons"][name] = st.paired_binary(
                [r["j14"][mode][m] for r in clean], [r["j13r"][mode][m] for r in clean], clusters
            ) | {"failed_as_wrong": _as_wrong(rows, _find_hit(mode, m))}
    return out


def _find_hit(mode: str, metric: str) -> Callable[[dict, str], bool]:
    return lambda r, a: not r[a]["failed"] and r[a][mode][metric]


def find_registered(arm: dict[str, Any]) -> dict[str, bool | None]:
    return {
        "F1_any5_ge_file_bm25_plus_10": arm["prod_any@5"] >= FIND_FILE_BM25_ANY5 + 0.10,
        "F2_any1_ge_frag_bm25_plus_5": arm["prod_any@1"] >= FIND_FRAG_BM25_ANY1 + 0.05,
        "F3_median_cost_le_0_005": None if arm["usd_median"] is None
        else arm["usd_median"] <= 0.005,
    }  # fmt: skip


def _cut_right(cut: float, label: str) -> Callable[[dict, str], bool]:
    return lambda r, a: r[a] is not None and (r[a] >= cut) == r[label]


def analyse_errata(rows: list[dict[str, Any]]) -> dict[str, Any]:
    import errata

    cut = errata.HOLISTIC_CUT
    both = _answered(rows, *LIVE_ARMS)
    sub = [r for r in both if r["unverified"] or not r["positive"]]
    right = _cut_right(cut, "positive")
    out: dict[str, Any] = {"n": len(rows), "paired": len(both), "cut": cut, "comparisons": {},
                           "failures": _failures(rows, lambda r, a: r[a] is None)}  # fmt: skip
    for name, group in (("errata_auc", both), ("errata_auc_unverified", sub)):
        out["comparisons"][name] = st.paired_auc(
            [r["positive"] for r in group], [r["j14"] for r in group],
            [r["j13r"] for r in group], [r["cluster"] for r in group],
        )  # fmt: skip
    out["comparisons"]["errata_correct_at_cut"] = st.paired_binary(
        [right(r, "j14") for r in both], [right(r, "j13r") for r in both],
        [r["cluster"] for r in both],
    ) | {"failed_as_wrong": _as_wrong(rows, right)}  # fmt: skip
    out["arms"] = {}
    for arm in ("rec13", *LIVE_ARMS):
        group = _answered(rows, arm)
        pos = [r[arm] for r in group if r["positive"]]
        neg = [r[arm] for r in group if not r["positive"]]
        unv = [r[arm] for r in group if r["unverified"]]
        a, u = st.auc(pos, neg), st.auc(unv, neg)
        out["arms"][arm] = {
            "n": len(group), "auc": a and round(a, 4), "auc_unverified": u and round(u, 4),
            "flags_objected": sum(x >= cut for x in pos),
            "flags_accepted": sum(x >= cut for x in neg),
            "X2_auc_ge_065": None if a is None else a >= 0.65,
            "X3_auc_unverified_ge_070": None if u is None else u >= 0.70,
        }  # fmt: skip
    return out


def analyse_tau2(rows: list[dict[str, Any]]) -> dict[str, Any]:
    import tau2

    cut = tau2.DONE_CUT
    both = _answered(rows, *LIVE_ARMS)
    right = _cut_right(cut, "done")
    out: dict[str, Any] = {"n": len(rows), "paired": len(both), "cut": cut, "comparisons": {},
                           "failures": _failures(rows, lambda r, a: r[a] is None)}  # fmt: skip
    out["comparisons"]["tau2_auc"] = st.paired_auc(
        [r["done"] for r in both], [r["j14"] for r in both], [r["j13r"] for r in both],
        [r["cluster"] for r in both],
    )  # fmt: skip
    out["comparisons"]["tau2_accuracy_at_cut"] = st.paired_binary(
        [right(r, "j14") for r in both], [right(r, "j13r") for r in both],
        [r["cluster"] for r in both],
    ) | {"failed_as_wrong": _as_wrong(rows, right)}  # fmt: skip
    out["arms"] = {}
    for arm in ("rec13", *LIVE_ARMS):
        group = _answered(rows, arm)
        a = st.auc([r[arm] for r in group if r["done"]], [r[arm] for r in group if not r["done"]])
        n = len(group) or 1
        acc = sum(right(r, arm) for r in group) / n
        trust = sum(r["done"] for r in group) / n
        out["arms"][arm] = {
            "n": len(group), "auc": a and round(a, 4), "accuracy": round(acc, 4),
            "accuracy_trust": round(trust, 4), "T1_auc_ge_075": None if a is None else a >= 0.75,
            "T2_beats_trust_by_10": acc - trust >= 0.10,
        }  # fmt: skip
    return out


ANALYSE = {"find": analyse_find, "errata": analyse_errata, "tau2": analyse_tau2}
RUN = {"find": run_find, "errata": run_errata, "tau2": run_tau2}


def analyse(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The registered family of nine: a comparison not measured counts as p = 1."""
    found = {k: (v, r["failures"]["gap"]) for r in results.values()
             for k, v in r["comparisons"].items()}  # fmt: skip
    adjusted = st.holm({k: found[k][0]["p"] if k in found else 1.0 for k in FAMILY})
    family = {}
    for name in FAMILY:
        result, gap = found.get(name, ({"diff": None, "p": 1.0, "ci95": None}, 0.0))
        family[name] = result | {"p_holm": adjusted[name],
                                 "verdict": st.verdict(result, adjusted[name], gap)}  # fmt: skip
    return {"family": family, "sets": results}


def spent_in_ledger() -> dict[str, float] | None:
    from sanchopanza.budget import SpendLedger

    if not LEDGER_PATH.exists():
        return None
    ledger = SpendLedger(LEDGER_PATH, cap_usd=LEDGER_CAP_USD)
    return {"batch": round(ledger.spent(BATCH), 6), "ledger": round(ledger.spent(), 6)}


SEALED = (
    "benchmarks/jev114/l4.py", "benchmarks/jev114/l4_stats.py", "tests/test_jev114_l4.py",
    "benchmarks/find/swebench.py", "benchmarks/candor_external/errata.py",
    "benchmarks/candor_external/tau2.py", "benchmarks/candor/monitors.py",
    "src/sanchopanza/providers/jev.py", "src/sanchopanza/providers/jev_models.py",
    "src/sanchopanza/providers/capped.py", "src/sanchopanza/providers/recorded.py",
    "src/sanchopanza/budget.py", "src/sanchopanza/_lockfile.py", "src/sanchopanza/funds.py",
    "src/sanchopanza/contract.py", "src/sanchopanza/squire.py", "src/sanchopanza/select.py",
    "src/sanchopanza/policy.py", "src/sanchopanza/limits.py", "src/sanchopanza/text.py",
    "src/sanchopanza/context/repo.py", "src/sanchopanza/context/blocks.py",
    "src/sanchopanza/context/archive.py", "src/sanchopanza/points/completion.py",
    "src/sanchopanza/points/chunks.py", "src/sanchopanza/points/hierarchy.py",
    "src/sanchopanza/points/passages.py", "src/sanchopanza/points/triage.py",
    "src/sanchopanza/candor/judge.py", "src/sanchopanza/candor/claims.py",
)  # fmt: skip


def seal() -> str:
    """prereg.manifest.json (the document, then the code it names) and prereg.sha256, over the
    lines `"<path> <sha256>\\n"`, as benchmarks/candor_external/seal.py does."""
    import hashlib

    doc = OUT / "prereg.md"
    paths = [doc.relative_to(REPO).as_posix(), *SEALED]
    manifest = {p: hashlib.sha256((REPO / p).read_bytes()).hexdigest() for p in paths}
    combined = hashlib.sha256("".join(f"{k} {v}\n" for k, v in manifest.items()).encode())
    (OUT / "prereg.manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    (OUT / "prereg.sha256").write_text(combined.hexdigest() + "\n", encoding="utf-8")
    return combined.hexdigest()


def run_sets(names: list[str], live: bool, limit: int | None) -> None:
    if live:
        load_key()
        preflight_or_stop()
    OUT.mkdir(parents=True, exist_ok=True)
    for name in names:
        rows = asyncio.run(RUN[name](live, limit))
        suffix = "" if limit is None else f"-first{limit}"
        (OUT / f"{name}-scored{suffix}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="ask (replay first) and score")
    parser.add_argument("--sets", default=",".join(SETS))
    parser.add_argument("--live", action="store_true", help="with --run: ask Jev what is missing")
    parser.add_argument("--limit", type=int, default=None, help="with --run: first N items")
    parser.add_argument("--seal", action="store_true", help="seal prereg.md and the code")
    args = parser.parse_args(argv)
    if args.seal:
        print(seal())
        return 0
    names = [s for s in args.sets.split(",") if s]
    if any(s not in SETS for s in names):
        parser.error(f"--sets among {SETS}")
    if args.run:
        run_sets(names, args.live, args.limit)
    if args.limit is not None:
        return 0
    results = {}
    for name in SETS:
        path = OUT / f"{name}-scored.jsonl"
        if path.exists():
            rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
            results[name] = ANALYSE[name](rows)
    summary = analyse(results) | {"spent": spent_in_ledger()}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    brief = {k: (v["diff"], v["ci95"], v["p_holm"], v["verdict"])
             for k, v in summary["family"].items()}  # fmt: skip
    print(json.dumps(brief, indent=1), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
