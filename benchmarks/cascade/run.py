"""A calibrated first stage in front of an LLM judge, on sets this repository did not write.

    python benchmarks/cascade/run.py --hash                       # the pre-registration's sha256
    python benchmarks/cascade/run.py --plan  --rjudge DIR --register FILE
    python benchmarks/cascade/run.py --jev   --rjudge DIR --register FILE --env-file PATH/TO/.env
    python benchmarks/cascade/run.py --submit haiku,sonnet,opus ...   # Message Batches, 50 % off
    python benchmarks/cascade/run.py --collect ...
    python benchmarks/cascade/run.py --analyze ...                    # free, from recordings

The design, the split, the threshold rule and the verdict are fixed in
`docs/results/2026-09-25-cascade/prereg.md`; every paying step refuses to run if that file's
hash has changed since it was recorded in `prereg.sha256`.

Data is read, not redistributed: R-Judge from the git objects of a clone pinned at the commit
in the pre-registration, a private labelled register (not released) from a local export.
What this directory keeps is keys, answers, token counts and the analysis.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import pathlib
import random
import re
import subprocess
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))

from meter import PRICES  # noqa: E402

from sanchopanza.points import actions, entities  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.llm import SYSTEM, answers_from, build_schema  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider, key_of  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-25-cascade"
PREREG = RESULTS / "prereg.md"
PREREG_HASH = RESULTS / "prereg.sha256"
JEV_FIXTURE = ROOT / "fixtures" / "cascade-jev.jsonl"
LLM_ANSWERS = RESULTS / "llm-answers.jsonl"
BATCHES = RESULTS / "batches.json"
RJUDGE_COMMIT = "83ce301da3ad50dd8b397e772863f5411c3d3dc2"
MODELS = {"haiku": "claude-haiku-4-5", "sonnet": "claude-sonnet-5", "opus": "claude-opus-5"}
TAUS = [round(i * 0.05, 2) for i in range(21)]
BATCH_DISCOUNT = 0.5


# --- the pre-registration guard ------------------------------------------------------------


def prereg_hash() -> str:
    files = [PREREG, ROOT / "src" / "sanchopanza" / "points" / "actions.py"]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.read_bytes())
    return digest.hexdigest()


def require_prereg() -> None:
    if not PREREG_HASH.exists():
        raise SystemExit("no prereg.sha256: run --hash --record-hash before spending")
    if PREREG_HASH.read_text(encoding="utf-8").strip() != prereg_hash():
        raise SystemExit("prereg.md or points/actions.py changed since it was registered")


# --- data ----------------------------------------------------------------------------------


def load_rjudge(clone: pathlib.Path) -> list[dict[str, Any]]:
    def git(*args: str) -> bytes:
        return subprocess.run(["git", *args], cwd=clone, capture_output=True, check=True).stdout

    names = git("ls-tree", "-r", "--name-only", RJUDGE_COMMIT, "data").decode().split()
    cases = []
    for name in sorted(n for n in names if n.endswith(".json")):
        for record in json.loads(git("show", f"{RJUDGE_COMMIT}:{name}").decode("utf-8")):
            state, qs = actions.questions(
                record=actions.render_record(record["contents"]), profile=record.get("profile", "")
            )
            stem = name.removeprefix("data/").removesuffix(".json")
            cases.append(
                {
                    "set": "rjudge",
                    "id": f"{stem}/{record['id']}",
                    "point": "action_risk",
                    "state": state,
                    "questions": qs,
                    "label": "unsafe" if int(record["label"]) == 1 else "safe",
                }
            )
    return cases


def load_register(path: pathlib.Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = []
    for case in data["cases"]:
        e = case["entrada"]
        state, qs = entities.classification_questions(
            field=e["campo"],
            text=e["texto"],
            options=e["opciones"],
            context=e.get("contexto", ""),
            add_other=False,
        )
        cases.append(
            {
                "set": "register",
                "id": case["id"],
                "point": "classify",
                "state": state,
                "questions": qs,
                "label": case["esperado"],
            }
        )
    return cases


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def load_codex(path: pathlib.Path) -> list[dict[str, Any]]:
    """ATBench-Codex (prereg-codex.md). Only `conversation` and `is_safe` are read."""
    cases = []
    for record in json.loads(path.read_text(encoding="utf-8")):
        steps = []
        for message in record["conversation"]:
            role = message.get("role")
            if role == "user":
                steps.append({"role": "user", "content": _as_text(message.get("content"))})
            elif role == "assistant":
                action = message.get("action")
                steps.append(
                    {
                        "role": "agent",
                        "thought": message.get("thought"),
                        "action": _as_text(action) if action else message.get("content"),
                    }
                )
            elif role == "environment":
                steps.append({"role": "environment", "content": _as_text(message.get("content"))})
        state, qs = actions.questions(record=actions.render_record([steps]))
        cases.append(
            {
                "set": "codex",
                "id": str(record["id"]),
                "point": "action_risk",
                "state": state,
                "questions": qs,
                "label": "safe" if record["is_safe"] else "unsafe",
            }
        )
    return cases


def require_codex_prereg() -> None:
    registered = RESULTS / "prereg-codex.sha256"
    digest = hashlib.sha256((RESULTS / "prereg-codex.md").read_bytes()).hexdigest()
    if not registered.exists() or registered.read_text().strip() != digest:
        raise SystemExit("prereg-codex.md missing or changed: nothing spent")


def load_all(args: argparse.Namespace) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    if args.rjudge:
        cases += load_rjudge(pathlib.Path(args.rjudge))
    if getattr(args, "codex", ""):
        cases += load_codex(pathlib.Path(args.codex))
    if args.register:
        cases += load_register(pathlib.Path(args.register))
    return cases


def half(case: dict[str, Any]) -> str:
    ident = "{}:{}".format(case["set"], case["id"])
    h = int(hashlib.sha256(ident.encode()).hexdigest()[:8], 16)
    return "derivation" if h % 2 == 0 else "held_out"


def custom_id(case: dict[str, Any], arm: str) -> str:
    ident = "{}:{}".format(case["set"], case["id"])
    return f"{arm}-{hashlib.sha256(ident.encode()).hexdigest()[:24]}"


def key_from_env(env_file: str | None, name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    if env_file:
        text = pathlib.Path(env_file).read_text(encoding="utf-8")
        match = re.search(rf"^{name}=(.*)$", text, re.M)
        if match:
            return match.group(1).strip().strip("'\"")
    raise SystemExit(f"{name} not found")


# --- the plan and the bill -----------------------------------------------------------------


def plan(cases: list[dict[str, Any]]) -> None:
    by_set: dict[str, list[dict[str, Any]]] = {}
    for c in cases:
        by_set.setdefault(c["set"], []).append(c)
    total = 0.0
    for name, rows in by_set.items():
        chars = sum(len(json.dumps(c["state"], ensure_ascii=False)) for c in rows)
        tokens = chars / 3.5 + 450 * len(rows)
        halves = sum(half(c) == "held_out" for c in rows)
        line = f"{name}: {len(rows)} cases ({halves} held out), ~{tokens / 1e6:.2f} MTok input"
        for arm, model in MODELS.items():
            cost = tokens / 1e6 * PRICES[model][0] * BATCH_DISCOUNT + len(rows) * 40 / 1e6 * (
                PRICES[model][1] * BATCH_DISCOUNT
            )
            total += cost
            line += f"; {arm} {cost:.2f} $"
        jev = tokens / 1e6 * 0.042
        total += jev
        print(line + f"; jev {jev:.3f} $")
    print(f"estimated total: {total:.2f} USD (batch prices for the LLM arms)")


# --- phase 1: Jev, live and recorded -------------------------------------------------------


async def run_jev(cases: list[dict[str, Any]], api_key: str, concurrency: int = 6) -> None:
    recorded = RecordedDecider.from_file(JEV_FIXTURE)
    live = RecordingDecider(create("jev", api_key=api_key), JEV_FIXTURE)
    gate = asyncio.Semaphore(concurrency)
    spent = 0.0
    done = 0

    async def one(case: dict[str, Any]) -> None:
        nonlocal spent, done
        replay = await recorded.decide(case["point"], case["state"], case["questions"])
        if replay.answers:
            return
        async with gate:
            try:
                decision = await live.decide(case["point"], case["state"], case["questions"])
            except Exception as error:  # recorded as missing; rerun picks it up
                print(f"  {case['id']}: {error.__class__.__name__}", file=sys.stderr)
                return
        spent += decision.cost_usd
        done += 1

    await asyncio.gather(*(one(c) for c in cases))
    print(f"jev: {done} new decisions, {spent:.4f} USD")


# --- phase 2: the LLM arms through Message Batches ------------------------------------------


def request_for(case: dict[str, Any], model: str) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": 300,
        "system": SYSTEM,
        "tools": [
            {
                "name": "answer",
                "description": "Typed answers",
                "input_schema": build_schema(case["questions"]),
            }
        ],
        "tool_choice": {"type": "tool", "name": "answer"},
        "messages": [
            {
                "role": "user",
                "content": "state:\n" + json.dumps(case["state"], ensure_ascii=False, default=str),
            }
        ],
    }


def done_ids() -> set[str]:
    if not LLM_ANSWERS.exists():
        return set()
    return {
        json.loads(line)["custom_id"]
        for line in LLM_ANSWERS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def submit(cases: list[dict[str, Any]], arms: list[str], api_key: str) -> None:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    have = done_ids()
    state = json.loads(BATCHES.read_text(encoding="utf-8")) if BATCHES.exists() else []
    sets = ",".join(sorted({c["set"] for c in cases}))
    pending_arms = {
        b["arm"]
        for b in state
        # batches before the Codex extension carry no `sets`: they were the main two sets
        if b.get("status") != "collected" and b.get("sets", "register,rjudge") == sets
    }
    for arm in arms:
        if arm in pending_arms:
            print(f"{arm}: a batch is already in flight; --collect first")
            continue
        requests = [
            {"custom_id": custom_id(c, arm), "params": request_for(c, MODELS[arm])}
            for c in cases
            if custom_id(c, arm) not in have
        ]
        if not requests:
            print(f"{arm}: nothing missing")
            continue
        batch = client.messages.batches.create(requests=requests)
        state.append(
            {
                "arm": arm,
                "id": batch.id,
                "count": len(requests),
                "status": "submitted",
                "sets": sets,
            }
        )
        print(f"{arm}: batch {batch.id} with {len(requests)} requests")
    RESULTS.mkdir(parents=True, exist_ok=True)
    BATCHES.write_text(json.dumps(state, indent=1), encoding="utf-8")


def collect(api_key: str) -> bool:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    state = json.loads(BATCHES.read_text(encoding="utf-8")) if BATCHES.exists() else []
    everything_in = True
    for entry in state:
        if entry["status"] == "collected":
            continue
        batch = client.messages.batches.retrieve(entry["id"])
        if batch.processing_status != "ended":
            counts = batch.request_counts
            print(f"{entry['arm']}: {batch.processing_status} ({counts.succeeded} done)")
            everything_in = False
            continue
        written = 0
        with LLM_ANSWERS.open("a", encoding="utf-8") as out:
            for result in client.messages.batches.results(entry["id"]):
                row: dict[str, Any] = {
                    "custom_id": result.custom_id,
                    "arm": entry["arm"],
                    "type": result.result.type,
                }
                if result.result.type == "succeeded":
                    message = result.result.message
                    row["model"] = message.model
                    row["input_tokens"] = message.usage.input_tokens
                    row["output_tokens"] = message.usage.output_tokens
                    row["payload"] = next(
                        (b.input for b in message.content if b.type == "tool_use"), None
                    )
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                written += 1
        entry["status"] = "collected"
        print(f"{entry['arm']}: collected {written}")
    BATCHES.write_text(json.dumps(state, indent=1), encoding="utf-8")
    return everything_in


# --- phase 3: the analysis, free -------------------------------------------------------------


def llm_rows() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if LLM_ANSWERS.exists():
        for line in LLM_ANSWERS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                rows[row["custom_id"]] = row
    return rows


def label_of(case: dict[str, Any], answers: dict[str, Any]) -> tuple[str | None, float]:
    """(label, confidence) from contract answers."""
    if case["point"] == "action_risk":
        a = answers.get("unsafe")
        if a is None or a.truth is None:
            return None, 0.0
        return ("unsafe" if a.truth >= 0.5 else "safe"), abs(2 * a.truth - 1)
    a = answers.get("category")
    if a is None or a.choice is None:
        return None, 0.0
    return a.choice, a.confidence


def llm_cost(row: dict[str, Any], arm: str) -> float:
    price_in, price_out = PRICES[MODELS[arm]]
    return (row.get("input_tokens", 0) * price_in + row.get("output_tokens", 0) * price_out) / 1e6


async def table(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    jev = RecordedDecider.from_file(JEV_FIXTURE)
    llm = llm_rows()
    out = []
    for case in cases:
        decision = await jev.decide(case["point"], case["state"], case["questions"])
        label, conf = label_of(case, dict(decision.answers))
        row = {
            "set": case["set"],
            "id": case["id"],
            "half": half(case),
            "label": case["label"],
            "jev": label,
            "jev_conf": conf,
            "jev_cost": decision.cost_usd,
            "jev_ms": decision.latency_ms,
            "key": key_of(case["point"], case["state"], case["questions"]),
        }
        for arm in MODELS:
            r = llm.get(custom_id(case, arm))
            if r and r.get("payload"):
                answered = answers_from(r["payload"], case["questions"])
                row[arm], _ = label_of(case, answered)
                row[f"{arm}_cost"] = llm_cost(r, arm)
            else:
                row[arm], row[f"{arm}_cost"] = None, None
        out.append(row)
    return out


def answered_accuracy(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    """Accuracy over the cases the arm answered, with the count, and Jev on the same cases.

    A missing answer (a cancelled or failed request) is not a wrong answer. The first
    analysis of 2026-09-25 divided by every case and put Opus 5 at 90.0 % on R-Judge; on the
    541 cases it answered it scored 95.0 %.
    """
    answered = [r for r in rows if r[arm] is not None]
    if not answered:
        return {"n": 0, "acc": None, "jev_same_cases": None}
    return {
        "n": len(answered),
        "acc": round(sum(r[arm] == r["label"] for r in answered) / len(answered), 4),
        "jev_same_cases": round(sum(r["jev"] == r["label"] for r in answered) / len(answered), 4),
    }


def cascade(rows: list[dict[str, Any]], arm: str, tau: float) -> tuple[list[bool], float, int]:
    hits, cost, escalated = [], 0.0, 0
    for r in rows:
        if r["jev"] is not None and r["jev_conf"] >= tau:
            answer, spend = r["jev"], r["jev_cost"]
        else:
            answer, spend = r[arm], r["jev_cost"] + (r[f"{arm}_cost"] or 0.0)
            escalated += 1
        hits.append(answer == r["label"])
        cost += spend
    return hits, cost, escalated


def alone(rows: list[dict[str, Any]], arm: str) -> tuple[list[bool], float]:
    return [r[arm] == r["label"] for r in rows], sum(r[f"{arm}_cost"] or 0.0 for r in rows)


def derive_tau(rows: list[dict[str, Any]], arm: str) -> float:
    target = sum(alone(rows, arm)[0])
    for tau in TAUS:
        if sum(cascade(rows, arm, tau)[0]) >= target:
            return tau
    return 1.01


def paired_bootstrap(a: list[bool], b: list[bool], seed: int = 7, reps: int = 2000) -> tuple:
    rng = random.Random(seed)
    n = len(a)
    diffs = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append(sum(a[i] - b[i] for i in idx) / n)
    diffs.sort()
    return (sum(a) - sum(b)) / n, diffs[int(0.025 * reps)], diffs[int(0.975 * reps)]


def rates(rows: list[dict[str, Any]], answers: list[str | None]) -> dict[str, float]:
    pos = [i for i, r in enumerate(rows) if r["label"] == "unsafe"]
    neg = [i for i, r in enumerate(rows) if r["label"] == "safe"]
    fn = sum(answers[i] != "unsafe" for i in pos)
    fp = sum(answers[i] == "unsafe" for i in neg)
    return {
        "fnr": round(fn / len(pos), 4) if pos else None,
        "fpr": round(fp / len(neg), 4) if neg else None,
    }


def analyze_set(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    usable = [r for r in rows if r[arm] is not None and r["jev"] is not None]
    derivation = [r for r in usable if r["half"] == "derivation"]
    held = [r for r in usable if r["half"] == "held_out"]
    tau = derive_tau(derivation, arm)
    c_hits, c_cost, esc = cascade(held, arm, tau)
    a_hits, a_cost = alone(held, arm)
    diff, low, high = paired_bootstrap(c_hits, a_hits)
    splits = []
    rng = random.Random(11)
    for _ in range(500):
        shuffled = usable[:]
        rng.shuffle(shuffled)
        d, h = shuffled[: len(shuffled) // 2], shuffled[len(shuffled) // 2 :]
        t = derive_tau(d, arm)
        ch, cc, _ = cascade(h, arm, t)
        ah, ac = alone(h, arm)
        splits.append(((sum(ch) - sum(ah)) / len(h), cc / ac if ac else None, t))
    splits.sort(key=lambda s: s[0])
    ratios = sorted(s[1] for s in splits if s[1] is not None)
    jev_held = [r["jev"] == r["label"] for r in held]
    return {
        "arm": arm,
        "n_usable": len(usable),
        "n_derivation": len(derivation),
        "n_held_out": len(held),
        "tau": tau,
        "held_out": {
            "cascade_acc": round(sum(c_hits) / len(held), 4),
            "alone_acc": round(sum(a_hits) / len(held), 4),
            "jev_acc": round(sum(jev_held) / len(held), 4),
            "diff": round(diff, 4),
            "diff_ci95": [round(low, 4), round(high, 4)],
            "cascade_cost": round(c_cost, 6),
            "alone_cost": round(a_cost, 6),
            "cost_ratio": round(c_cost / a_cost, 4) if a_cost else None,
            "escalated": esc,
        },
        "robustness_500_splits": {
            "diff_p05_p50_p95": [
                round(splits[25][0], 4),
                round(splits[250][0], 4),
                round(splits[475][0], 4),
            ],
            "cost_ratio_p50_p95": [round(ratios[250], 4), round(ratios[475], 4)]
            if ratios
            else None,
            "tau_median": sorted(s[2] for s in splits)[250],
        },
    }


def verdict(block: dict[str, Any]) -> bool:
    h = block["held_out"]
    return (
        h["diff"] >= -0.02
        and h["diff_ci95"][0] >= -0.06
        and h["cost_ratio"] is not None
        and h["cost_ratio"] <= 0.5
    )


async def analyze(cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows = await table(cases)
    report: dict[str, Any] = {"prereg_sha256": prereg_hash(), "sets": {}}
    for name in sorted({r["set"] for r in rows}):
        subset = [r for r in rows if r["set"] == name]
        entry: dict[str, Any] = {
            "cases": len(subset),
            "missing": {
                "jev": sum(r["jev"] is None for r in subset),
                **{arm: sum(r[arm] is None for r in subset) for arm in MODELS},
            },
            "all_cases": {
                "jev_acc": round(sum(r["jev"] == r["label"] for r in subset) / len(subset), 4),
                **{f"{arm}_answered": answered_accuracy(subset, arm) for arm in MODELS},
                "jev_cost": round(sum(r["jev_cost"] for r in subset), 6),
                **{
                    f"{arm}_cost": round(sum(r[f"{arm}_cost"] or 0 for r in subset), 6)
                    for arm in MODELS
                },
                "jev_median_ms": sorted(r["jev_ms"] for r in subset)[len(subset) // 2],
            },
            "cascades": {},
        }
        if name == "rjudge":
            entry["rates"] = {
                arm: rates(
                    [r for r in subset if r[arm] is not None],
                    [r[arm] for r in subset if r[arm] is not None],
                )
                for arm in ("jev", *MODELS)
                if any(r[arm] is not None for r in subset)
            }
        for arm in MODELS:
            if all(r[arm] is None for r in subset):
                continue
            block = analyze_set(subset, arm)
            block["passes"] = verdict(block)
            if name == "rjudge":
                held = [r for r in subset if r["half"] == "held_out" and r[arm] is not None]
                answers = [
                    r["jev"] if r["jev"] is not None and r["jev_conf"] >= block["tau"] else r[arm]
                    for r in held
                ]
                block["held_out"]["rates_cascade"] = rates(held, answers)
                block["held_out"]["rates_alone"] = rates(held, [r[arm] for r in held])
            entry["cascades"][arm] = block
        report["sets"][name] = entry
    p1 = report["sets"].get("rjudge", {}).get("cascades", {}).get("sonnet", {}).get("passes")
    p2 = report["sets"].get("register", {}).get("cascades", {}).get("sonnet", {}).get("passes")
    report["P1_rjudge"], report["P2_register"] = p1, p2
    report["verdict"] = "solid" if p1 and p2 else "partial" if (p1 or p2) else "negative"
    report["rows"] = rows
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hash", action="store_true")
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--jev", action="store_true")
    ap.add_argument("--submit", default="")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--rjudge", default="")
    ap.add_argument("--register", default="")
    ap.add_argument("--codex", default="", help="ATBench-Codex test.json (prereg-codex.md)")
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()

    if args.hash:
        print(prereg_hash())
        if args.record_hash:
            PREREG_HASH.write_text(prereg_hash() + "\n", encoding="utf-8")
            print("recorded")
        return 0
    cases = load_all(args)
    if args.plan:
        plan(cases)
        return 0
    if args.jev:
        require_prereg()
        if args.codex:
            require_codex_prereg()
        asyncio.run(run_jev(cases, key_from_env(args.env_file, "TYPESAFE_API_KEY")))
        return 0
    if args.submit:
        require_prereg()
        if args.codex:
            require_codex_prereg()
        submit(cases, args.submit.split(","), key_from_env(args.env_file, "ANTHROPIC_API_KEY"))
        return 0
    if args.collect:
        while not collect(key_from_env(args.env_file, "ANTHROPIC_API_KEY")):
            time.sleep(60)
        return 0
    if args.analyze:
        report = asyncio.run(analyze(cases))
        RESULTS.mkdir(parents=True, exist_ok=True)
        rows = report.pop("rows")
        (RESULTS / "analysis.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        (RESULTS / "rows.json").write_text(
            json.dumps(
                [{k: v for k, v in r.items() if k != "id" or r["set"] == "rjudge"} for r in rows],
                ensure_ascii=False,
                indent=0,
            ),
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
