"""check_done under Jev 1.14 on AgentDojo trajectories no recalibration has seen (lot
jev114-checkdone).

    python benchmarks/jev114/checkdone114.py fetch                  # free: public runs, pinned
    python benchmarks/jev114/checkdone114.py run --dry [--l2-runs-root MAIN]   # free: plan, bill
    python benchmarks/jev114/checkdone114.py seal                   # data.sha256, prereg.sha256
    checkdone114-run.cmd                                            # the paid launch (WMI)
    python benchmarks/jev114/checkdone114.py publish                # free: recordings, launch log
    python benchmarks/jev114/checkdone114.py rows                   # free: fixtures -> rows
    python benchmarks/jev114/checkdone114_analysis.py               # free: the verdict

Registered in docs/results/2026-10-16-checkdone114/prereg.md.

THE TRAJECTORIES are AgentDojo's own published runs (github.com/ethz-spylab/agentdojo, MIT, at
commit `AGENTDOJO_SHA`), pipeline `claude-3-7-sonnet-20250219`, suites banking, travel and
workspace. The recalibration and its confirmation read only this repository's slack runs of
2026-09-24 (Sonnet 5 and Haiku 4.5): a different model, different suites, different authors.
The label is AgentDojo's `utility`, computed by the benchmark from the environment's final state,
so it is a label by construction and no one here wrote it. `fetch` downloads exactly the files
`inputs.jsonl` lists and checks each one's git blob sha; every later step checks it again.

THE REQUEST is check_done's, built as lot L2 built it: `completion.render` over the messages
(AgentDojo's older string `content` is wrapped as one text block first) and
`points.completion.questions` with the registered record limit.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import sys
import urllib.request
from collections import Counter
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for extra in ("src", "benchmarks"):
    sys.path.insert(0, str(ROOT / extra))
sys.path.insert(0, str(HERE))

import lot as lots  # noqa: E402

from sanchopanza.points import completion as point  # noqa: E402
from sanchopanza.providers.capped import DEFAULT_PRICE_PER_MTOK, estimate_usd  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, key_of  # noqa: E402

OUT = ROOT / "docs" / "results" / "2026-10-16-checkdone114"
INPUTS = OUT / "inputs.jsonl"
DATA = OUT / "data.sha256"
RUN = Path(os.environ.get("SANCHOPANZA_JEV114_RUN", "C:/sp-runs/jev114")) / "checkdone114"
AGENTDOJO_SHA = "089ed468cf3ed0322acc66b0211f26d9d90dbf60"
PIPELINE = "claude-3-7-sonnet-20250219"
SUITES = ("banking", "travel", "workspace")
DATA_ROOT = Path(
    os.environ.get(
        "SANCHOPANZA_CHECKDONE_DATA", f"C:/sp-runs/checkdone114/agentdojo-{AGENTDOJO_SHA[:7]}"
    )
)
REPO = "ethz-spylab/agentdojo"
EXPECTED_FILES = 950  # banking 169 + travel 167 + workspace 614 at AGENTDOJO_SHA
BATCH_CAP = 0.25

LOT = lots.Lot(
    name="jev114-checkdone",
    out=OUT,
    run=RUN,
    batch_cap=BATCH_CAP,
    fixture_stem="checkdone114",
    sealed=(
        "docs/results/2026-10-16-checkdone114/prereg.md",
        "docs/results/2026-10-16-checkdone114/inputs.jsonl",
        "checkdone114-run.cmd",
        "benchmarks/jev114/checkdone114.py",
        "benchmarks/jev114/checkdone114_analysis.py",
        "benchmarks/completion/run.py",
        "benchmarks/cascade/run.py",
        "benchmarks/meter.py",
        "src/sanchopanza/points/completion.py",
        "src/sanchopanza/providers/llm.py",
        *lots.COMMON_SEALED,
    ),
)


def _completion_runner() -> Any:
    """benchmarks/completion/run.py, loaded by path (several benches ship a `run.py`)."""
    spec = importlib.util.spec_from_file_location(
        "completion_run", ROOT / "benchmarks" / "completion" / "run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- fetch: the public runs at a pinned commit ------------------------------------------------


def blob_sha(data: bytes) -> str:
    """Git's object id for a file's bytes: what the tree at AGENTDOJO_SHA lists."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()  # noqa: S324 - git's id


def selected(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every trajectory JSON of PIPELINE in SUITES, sorted by path."""
    out = []
    for entry in tree:
        parts = entry["path"].split("/")
        if (entry.get("type") == "blob" and len(parts) == 6 and parts[0] == "runs"
                and parts[1] == PIPELINE and parts[2] in SUITES
                and parts[-1].endswith(".json")):  # fmt: skip
            out.append({"path": entry["path"], "sha": entry["sha"], "size": entry.get("size")})
    return sorted(out, key=lambda e: e["path"])


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "sanchopanza-bench"})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https
        return response.read()


def cmd_fetch(args: argparse.Namespace) -> int:
    """Free. Writes inputs.jsonl from the tree (unless it exists) and downloads every listed
    file into the data root, refusing any whose blob sha differs."""
    if INPUTS.exists():
        manifest = [json.loads(x) for x in INPUTS.read_text(encoding="utf-8").splitlines() if x]
    else:
        tree_url = f"https://api.github.com/repos/{REPO}/{'git'}/trees/{AGENTDOJO_SHA}?recursive=1"
        tree = json.loads(_get(tree_url))
        if tree.get("truncated"):
            raise SystemExit("the tree listing is truncated: nothing written")
        manifest = selected(tree["tree"])
        OUT.mkdir(parents=True, exist_ok=True)
        INPUTS.write_text("".join(json.dumps(e) + "\n" for e in manifest), encoding="utf-8")
    if len(manifest) != EXPECTED_FILES:
        raise SystemExit(f"{len(manifest)} files listed, registered {EXPECTED_FILES}")

    def one(entry: Mapping[str, Any]) -> str:
        target = args.data_root / entry["path"]
        if target.exists() and blob_sha(target.read_bytes()) == entry["sha"]:
            return "kept"
        raw = f"https://raw.githubusercontent.com/{REPO}/{AGENTDOJO_SHA}/{entry['path']}"
        data = _get(raw)
        if blob_sha(data) != entry["sha"]:
            return "mismatch"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return "fetched"

    with ThreadPoolExecutor(max_workers=8) as pool:
        tally = Counter(pool.map(one, manifest))
    print(f"{dict(tally)} into {args.data_root}")
    return 1 if tally.get("mismatch") else 0


# --- the cases -----------------------------------------------------------------------------


def normalized(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """AgentDojo before v0.1.30 logs `content` as a string; render() reads text blocks."""
    out = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            content = [{"type": "text", "content": content}]
        out.append({**m, "content": content or []})
    return out


def case_of(entry: Mapping[str, Any], data: Mapping[str, Any], render: Any) -> dict[str, Any]:
    _, _, suite, task_dir, attack, _ = entry["path"].split("/")
    task, record = render(normalized(data["messages"]))
    state, qs = point.questions(task=task, record=record)
    return {
        "set": "checkdone114",
        "id": entry["path"],
        "suite": suite,
        "cluster": f"{suite}/{task_dir}",
        "attack": attack,
        "point": "completion",
        "state": state,
        "questions": qs,
        "label": "done" if data["utility"] else "not_done",
        # The injected task succeeded: `utility` can be false because the agent was hijacked,
        # not because it stopped early. Kept to report the result without these runs.
        "security": bool(data.get("security")) if attack != "none" else False,
        "injection": f"{suite}/{data.get('injection_task_id') or 'benign'}",
    }


def load(data_root: Path) -> list[dict[str, Any]]:
    """Every listed trajectory, its bytes checked against inputs.jsonl."""
    manifest = [json.loads(x) for x in INPUTS.read_text(encoding="utf-8").splitlines() if x]
    render = _completion_runner().render
    cases, problems = [], []
    for entry in manifest:
        path = data_root / entry["path"]
        if not path.exists():
            problems.append(f"missing {entry['path']}")
            continue
        raw = path.read_bytes()
        if blob_sha(raw) != entry["sha"]:
            problems.append(f"changed {entry['path']}")
            continue
        data = json.loads(raw.decode("utf-8"))
        if "messages" not in data or "utility" not in data:
            problems.append(f"unlabelled {entry['path']}")
            continue
        cases.append(case_of(entry, data, render))
    if problems:
        raise SystemExit(f"{len(problems)} input problems, first: {problems[:3]}")
    if len(cases) != EXPECTED_FILES:
        raise SystemExit(f"{len(cases)} cases, registered {EXPECTED_FILES}")
    return cases


def inputs_digest(cases: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for case in cases:
        unit = f"{case['id']}|{case['label']}|{case['cluster']}|{case['security']}|"
        h.update(unit.encode())
        h.update(key_of(case["point"], case["state"], case["questions"]).encode())
    return h.hexdigest()


# --- asking --------------------------------------------------------------------------------


async def ask(case: Mapping[str, Any], decider: Any) -> tuple[Any, None]:
    return await decider.decide(case["point"], case["state"], case["questions"]), None


async def answered(case: Mapping[str, Any], arm: lots.Arm) -> bool:
    d = await arm.recorded.decide(case["point"], case["state"], case["questions"])
    return bool(d.answers)


# --- the plan: free -------------------------------------------------------------------------


def _chars(case: Mapping[str, Any]) -> int:
    asked = {k: repr(q) for k, q in case["questions"].items()}
    return len(json.dumps({"state": case["state"], "questions": asked}, ensure_ascii=False))


def l2_rate(runs_root: Path | None) -> dict[str, Any]:
    """Characters per billed token and USD per token on lot L2's check_done calls, both arms
    (the recordings and the slack runs they were asked over). Without the runs: 4 chars per
    token, the low end of what Jev was measured at, and the default price."""
    if runs_root is None:
        return {"chars_per_token": 4.0, "usd_per_token": DEFAULT_PRICE_PER_MTOK / 1e6,
                "source": "assumed"}  # fmt: skip
    import recalconf

    l2 = recalconf.done_cases(runs_root)
    chars = tokens = 0
    usd = 0.0
    for arm, name in (("13r", "completion-jev-113r.jsonl"), ("14", "completion-jev.jsonl")):
        replay = RecordedDecider.from_file(ROOT / "fixtures" / "jev114" / name,
                                           model=lots.MODELS[arm])  # fmt: skip
        for case in l2:
            d = asyncio.run(replay.decide(case["point"], case["state"], case["questions"]))
            if d.answers and d.input_tokens:
                chars += _chars(case)
                tokens += d.input_tokens
                usd += d.cost_usd
    calls = 2 * len(l2)
    return {"chars_per_token": chars / tokens, "usd_per_token": usd / tokens,
            "calls": calls, "usd_per_call": usd / calls, "source": "lot L2"}  # fmt: skip


def overlap_with_seen(cases: list[dict[str, Any]]) -> int:
    """Request keys shared with any earlier check_done recording (L2, recalconf): must be 0."""
    seen: set[str] = set()
    for name in ("completion-jev.jsonl", "completion-jev-113r.jsonl", "recalconf-done-13r.jsonl",
                 "recalconf-done-14.jsonl"):  # fmt: skip
        path = ROOT / "fixtures" / "jev114" / name
        for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
            if line.strip():
                seen.add(json.loads(line).get("key"))
    path = ROOT / "fixtures" / "completion-jev.jsonl"  # September's 1.13 recording
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        if line.strip():
            seen.add(json.loads(line).get("key"))
    mine = {key_of(c["point"], c["state"], c["questions"], model)
            for c in cases for model in lots.MODELS.values()}  # fmt: skip
    return len(mine & seen)


def plan(cases: list[dict[str, Any]], rate: Mapping[str, Any]) -> dict[str, Any]:
    by = Counter((c["suite"], c["label"]) for c in cases)
    attacked = Counter((c["attack"] != "none", c["label"]) for c in cases)
    pessimistic = 2 * sum(
        estimate_usd(c["state"], c["questions"], price_per_mtok=DEFAULT_PRICE_PER_MTOK)
        for c in cases
    )
    tokens = sum(_chars(c) for c in cases) / rate["chars_per_token"]
    expected = 2 * tokens * rate["usd_per_token"]
    truncated = sum(c["state"]["record"].endswith(" [...]") for c in cases)
    return {
        "cases": len(cases),
        "clusters": len({c["cluster"] for c in cases}),
        "by_suite_label": {f"{s} {lab}": n for (s, lab), n in sorted(by.items())},
        "by_attack_label": {
            f"{'attacked' if a else 'benign'} {lab}": n for (a, lab), n in sorted(attacked.items())
        },  # fmt: skip
        "records_at_the_limit": truncated,
        "security_true": Counter(c["label"] for c in cases if c["security"]),
        "calls": 2 * len(cases),
        "jev_usd_expected": round(expected, 4),
        "jev_usd_pessimistic": round(pessimistic, 4),
        "rate": rate,
        "claude_usd": 0.0,
        "batch_cap": LOT.batch_cap,
        "ledger": lots.ledger_room(LOT),
        "overlap_with_l2_and_recalconf": overlap_with_seen(cases),
    }


def cmd_run(args: argparse.Namespace) -> int:
    if args.dry == args.paid:
        raise SystemExit("run: pass exactly one of --dry or --paid")
    cases = load(args.data_root)
    if args.dry:
        report = plan(cases, l2_rate(args.l2_runs_root))
        print(json.dumps(report, indent=1))
        refused = lots.may_launch(LOT)
        print(f"dry: nothing asked. A paid launch now would be "
              f"{'refused: ' + refused if refused else 'allowed after the seal'}")  # fmt: skip
        if report["overlap_with_l2_and_recalconf"]:
            return 4
        if report["jev_usd_pessimistic"] > LOT.batch_cap:
            print("note: the pessimistic estimate exceeds the cap; the cap stops the run")
        return 0
    lots.require_sealed_checkout(LOT)
    sealed = json.loads(DATA.read_text(encoding="utf-8"))
    if inputs_digest(cases) != sealed["done"]:
        raise SystemExit("inputs differ from the sealed ones: nothing spent")
    return lots.paid_launch(LOT, lambda: asyncio.run(lots.run_cases(LOT, cases, ask, answered)))


def cmd_seal(args: argparse.Namespace) -> int:
    data = {"done": inputs_digest(load(args.data_root))}
    DATA.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    (OUT / "prereg.sha256").write_text(lots.digest(LOT) + "\n", encoding="utf-8")
    print(json.dumps(data), "prereg.sha256", lots.digest(LOT))
    return 0


ROWS = OUT / "done-scored.jsonl"


async def rows_of(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    arms = lots.arms_of(LOT, False, asyncio.Semaphore(LOT.gate))
    rows = []
    for case in cases:
        ps = {}
        for arm in lots.ARMS:
            d = (await ask(case, arms[arm]))[0]
            answer = d.answer("done")  # `usable`: a NaN is a missing answer, not a block
            ps[arm] = None if d.failed or answer.empty else answer.truth
        keep = ("id", "suite", "cluster", "injection", "attack", "security", "label")
        rows.append({k: case[k] for k in keep} | {"p_13r": ps["13r"], "p_14": ps["14"]})
    return rows


def cmd_rows(args: argparse.Namespace) -> int:
    rows = asyncio.run(rows_of(load(args.data_root)))
    ROWS.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    print(f"{len(rows)} rows -> {ROWS.relative_to(ROOT).as_posix()}")
    return 0


def cmd_publish(_: argparse.Namespace) -> int:
    print("\n".join(lots.publish(LOT)) or "nothing to publish")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in (("fetch", cmd_fetch), ("run", cmd_run), ("seal", cmd_seal),
                     ("publish", cmd_publish), ("rows", cmd_rows)):  # fmt: skip
        p = sub.add_parser(name)
        p.add_argument("--data-root", type=Path, default=DATA_ROOT)
        if name == "run":
            p.add_argument("--dry", action="store_true")
            p.add_argument("--paid", action="store_true")
            p.add_argument(
                "--l2-runs-root",
                type=Path,
                default=None,
                help="checkout holding the 2026-09-24 slack runs, to price by L2",
            )
        p.set_defaults(fn=fn)
    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
