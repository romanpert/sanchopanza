"""SWE-chat as held-out data for candor v6's inputs (prereg-inputs.md, prereg-inputs-code.md).

    python benchmarks/candor_external/swechat.py fetch                      # gated: the HF token
    python benchmarks/candor_external/swechat.py items --src <v5 src>       # free
    python benchmarks/candor_external/swechat.py score --src <v5 src> --arm v5 [--live]
    python benchmarks/candor_external/swechat.py score --src <v6 src> --arm v6 [--live]
    python benchmarks/candor_external/swechat.py blind                      # free
    python benchmarks/candor_external/swechat.py verdicts                   # free

Dataset: `SALT-NLP/SWE-chat` (ODC-BY), real sessions between developers and coding agents in
public repositories. Only `sessions.parquet` and the transcripts of 300 Claude Code sessions are
downloaded, sampled with SEED from the sessions whose repository is none of errata-bench's.

A turn is a request the person typed and everything until the next one: every tool call with
its result, and the last text the agent wrote. `--src` is the `src` folder the rules are
imported from (`git archive <commit> src`); both arms read the same items, built with v5's
`claims.paths_in`. The derived block is one recorded Jev answer shared by both arms.

Text stays in the cache (CACHE). The repository gets ids, counts and labels only.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import random
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATASET = "SALT-NLP/SWE-chat"
CACHE = Path.home() / ".cache" / "sanchopanza" / "candor-external" / "swe-chat"
ERRATA = Path.home() / ".cache" / "sanchopanza" / "candor-external" / "errata-bench-v1"
OUT = REPO / "docs" / "results" / "2026-09-30-candor-inputs"
ANSWERS = OUT / "swechat-answers.jsonl"  # hashed keys and Jev's answers, no text
SEED = 20260930
SESSIONS = 300
AGENTS = ("Claude Code", "claude-code")
JEV_CAP_USD = 0.15  # registered in prereg-inputs.md
MAX_READ = 200  # pairs the blind reader reads (prereg-inputs.md)
RESULT_KEEP = 4000  # characters of a tool result kept in an item (its tail)
# What the harness writes into a user message: reminders, IDE context, command wrappers, a
# background task's notification, a teammate's message, a `!` shell command and its output.
_TAGS = re.compile(
    r"<(system-reminder|ide_opened_file|ide_selection|ide_diagnostics|local-command-stdout|"
    r"local-command-stderr|local-command-caveat|command-name|command-message|task-notification|"
    r"teammate-message|bash-input|bash-stdout|bash-stderr)(?:\s[^>]*)?>.*?</\1>",
    re.S,
)
_ARGS = re.compile(r"</?command-args>")
# The line the harness appends after a task notification.
_NOTICE_TAIL = re.compile(
    r"^\s*(Full transcript available at|Read the output file to retrieve the result):\s*\S+\s*$",
    re.M,
)
_INTERRUPTED = re.compile(r"^\[Request interrupted by user[^\]]*\]$")


def _get(url: str) -> bytes:
    token = (Path.home() / ".cache" / "huggingface" / "token").read_text().strip()
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310 - fixed host
        return response.read()


def _transcript_names() -> set[str]:
    """Every file under `transcripts/`, following the tree API's cursor."""
    names: set[str] = set()
    url = f"https://huggingface.co/api/datasets/{DATASET}/tree/main/transcripts"
    while url:
        token = (Path.home() / ".cache" / "huggingface" / "token").read_text().strip()
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            names |= {Path(i["path"]).name for i in json.loads(response.read())}
            link = response.headers.get("Link") or ""
        found = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = found.group(1) if found else ""
    return names


def errata_repos() -> set[str]:
    return {
        json.loads(p.read_text(encoding="utf-8"))["repo_id"]
        for p in ERRATA.glob("*/grading_task.json")
    }


def sample(names: set[str]) -> list[str]:
    """SESSIONS Claude Code sessions with a transcript, none from an errata-bench repository."""
    import pyarrow.parquet as pq

    cols = ["session_id", "repo_id", "agent"]
    rows = pq.read_table(CACHE / "sessions.parquet", columns=cols).to_pylist()
    excluded = errata_repos()
    eligible = sorted(
        r["session_id"]
        for r in rows
        if r["agent"] in AGENTS
        and r["repo_id"] not in excluded
        and f"{r['session_id']}.jsonl" in names
    )
    return sorted(random.Random(SEED).sample(eligible, SESSIONS))


def fetch() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    if not (CACHE / "sessions.parquet").exists():
        base = f"https://huggingface.co/datasets/{DATASET}/resolve/main/"
        (CACHE / "sessions.parquet").write_bytes(_get(base + "sessions.parquet"))
    chosen = sample(_transcript_names())
    (CACHE / "sample.json").write_text(json.dumps(chosen, indent=1), encoding="utf-8")
    folder = CACHE / "transcripts"
    folder.mkdir(exist_ok=True)
    for sid in chosen:
        target = folder / f"{sid}.jsonl"
        if not target.exists():
            name = urllib.parse.quote(f"{sid}.jsonl")
            target.write_bytes(
                _get(f"https://huggingface.co/datasets/{DATASET}/resolve/main/transcripts/{name}")
            )


# --- turns ----------------------------------------------------------------------------------


def request_text(content: Any) -> str:
    """What the person typed: system reminders, IDE context and command wrappers taken out."""
    from sanchopanza.context.transcript import blocks_of

    blocks = [b for b in blocks_of({"content": content}) if isinstance(b, dict)]
    if any(b.get("type") == "tool_result" for b in blocks):
        return ""
    text = "\n".join(str(b.get("text") or "") for b in blocks if b.get("type") == "text")
    text = _NOTICE_TAIL.sub("", _ARGS.sub("", _TAGS.sub("", text))).strip()
    return "" if _INTERRUPTED.match(text) else text


def _entries(path: Path) -> list[dict[str, Any]]:
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("type") not in ("user", "assistant"):
            continue
        if entry.get("isSidechain") or entry.get("isMeta") or entry.get("isCompactSummary"):
            continue
        if isinstance(entry.get("message"), dict):
            out.append(entry["message"])
    return out


def turns(path: Path) -> list[dict[str, Any]]:
    """Every turn of a session, compactions included: the request, the calls, the last text."""
    from sanchopanza.candor.ledger import target_of, writes_of
    from sanchopanza.context.transcript import calls, merge_consecutive, message_text

    groups: list[tuple[str, list[dict[str, Any]]]] = []
    for message in _entries(path):
        typed = request_text(message.get("content")) if message.get("role") == "user" else ""
        if typed:
            groups.append((typed, []))
        elif groups:
            groups[-1][1].append(message)
    out = []
    for index, (task, messages) in enumerate(groups):
        merged = merge_consecutive(messages)
        texts = [message_text(m) for m in merged if m["role"] == "assistant"]
        said = next((t for t in reversed(texts) if t), "")
        ledger = [
            {"tool": c.tool, "target": target_of(c.tool, c.input), "ok": not c.is_error,
             "result": c.result[-RESULT_KEEP:], "writes": list(writes_of(c.tool, c.input))}
            for c in calls(merged)
        ]  # fmt: skip
        out.append({"turn": index, "prompt": task, "said": said, "ledger": ledger})
    return out


def items() -> list[dict[str, Any]]:
    """The scored turns: the request names a path under the imported `claims.paths_in` (v5)."""
    from sanchopanza.candor.claims import paths_in

    out = []
    for sid in json.loads((CACHE / "sample.json").read_text(encoding="utf-8")):
        for turn in turns(CACHE / "transcripts" / f"{sid}.jsonl"):
            if turn["said"] and paths_in(turn["prompt"]):
                out.append({"id": f"{sid}:{turn['turn']}", **turn})
    return out


def use_src(src: str) -> None:
    """Import `sanchopanza` from `src` and nowhere else."""
    sys.path.insert(0, str(Path(src).resolve()))
    import sanchopanza

    where = Path(sanchopanza.__file__).resolve()
    if Path(src).resolve() not in where.parents:
        raise SystemExit(f"sanchopanza imported from {where}, not {src}")


# --- scoring --------------------------------------------------------------------------------

_NAMED = re.compile(r"the task names (.+?); nothing read it")


class Squire:
    """Jev behind a recorded store and a dollar cap. A call it cannot answer (replay without a
    record, or the cap reached) raises, and the item is NOT RUN in both arms."""

    def __init__(self, decider: Any, cap: float) -> None:
        self.decider, self.cap = decider, cap
        self.rows: dict[str, dict[str, Any]] = {}
        if ANSWERS.exists():
            for line in ANSWERS.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.rows[row["key"]] = row
        self.spent = sum(float(r.get("cost") or 0.0) for r in self.rows.values())
        self.missing = 0
        self.gate = asyncio.Semaphore(8)

    async def decide(self, point: str, state: Any, questions: dict[str, Any]) -> Any:
        from sanchopanza.contract import Answer, Decision

        key = hashlib.sha256(
            (point + json.dumps({"s": state, "q": sorted(questions)}, sort_keys=True,
                                default=str)).encode()  # fmt: skip
        ).hexdigest()
        row = self.rows.get(key)
        if row is None:
            if self.decider is None or self.spent >= self.cap:
                self.missing += 1
                raise LookupError("no recorded answer")
            async with self.gate:
                try:
                    decision = await self.decider.decide(point, state, questions)
                except Exception as error:  # noqa: BLE001 - recorded as a failure, not retried
                    decision = Decision(point, {}, "jev", "-", error=type(error).__name__)
            self.spent += decision.cost_usd
            row = {"key": key, "point": point, "cost": decision.cost_usd, "error": decision.error,
                   "model": decision.model,
                   "answers": {k: v.to_dict() for k, v in decision.answers.items()}}  # fmt: skip
            self.rows[key] = row
            with ANSWERS.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
        answers = {k: Answer.from_dict(v) for k, v in (row.get("answers") or {}).items()}
        return Decision(point, answers, "replay", row.get("model", "-"), error=row.get("error"),
                        cost_usd=float(row.get("cost") or 0.0))  # fmt: skip

    def record(self, *_args: Any, **_kwargs: Any) -> None:
        return None


async def _input_frontier(squire: Squire, turn: Any, report: Any) -> list[str]:
    """v6's `input` kind alone: the unread paths of a long request a yes marks as inputs."""
    from sanchopanza.candor import frontier as fr

    found = [d for d in fr.doubts(turn, report) if d.kind == "input"]
    if not found:
        return []
    state, qs = fr.questions(found, turn.task)
    decision = await squire.decide("candor_frontier", state, qs)
    return [
        d.subject
        for key, d in zip(qs, found, strict=True)
        if not decision.failed and not decision.answer(key).empty
        and (decision.answer(key).truth or 0.0) >= fr.CUT
    ]


async def score_one(item: dict[str, Any], squire: Squire, arm: str) -> dict[str, Any]:
    from sanchopanza.candor.extract import check_with_derived
    from sanchopanza.candor.ledger import from_audit
    from sanchopanza.candor.rules import Turn

    turn = Turn(said=item["said"], did=tuple(from_audit(item["ledger"])), task=item["prompt"])
    before = squire.missing
    report = await check_with_derived(squire, turn)
    paths = []
    for f in report.findings:
        if f.rule == "substituted_input":
            named = _NAMED.search(f.detail)
            paths.append(named.group(1) if named else "?")
    if arm == "v6":
        with contextlib.suppress(LookupError):  # counted in `missing`
            paths += await _input_frontier(squire, turn, report)
    return {"id": item["id"], "not_run": squire.missing > before,
            "paths": sorted(set(paths))}  # fmt: skip


async def score(arm: str, live: bool) -> list[dict[str, Any]]:
    decider = None
    if live:
        from sanchopanza.providers import create

        decider = create("jev", api_key=os.environ["TYPESAFE_API_KEY"])
    squire = Squire(decider, JEV_CAP_USD)
    rows = json.loads((CACHE / "items.json").read_text(encoding="utf-8"))
    order = random.Random(SEED).sample(rows, len(rows))  # a cap cuts a random subset
    out = [await score_one(i, squire, arm) for i in order]
    sys.stderr.write(f"{arm}: {len(out)} turns, Jev {squire.spent:.4f} USD, "
                     f"{sum(r['not_run'] for r in out)} not run\n")  # fmt: skip
    return sorted(out, key=lambda r: r["id"])


# --- the blind reading and the verdicts -----------------------------------------------------


def pair_id(item_id: str, path: str) -> str:
    return hashlib.sha256(f"{item_id}\0{path}".encode()).hexdigest()[:12]


def _scored(arm: str) -> dict[str, dict[str, Any]]:
    path = CACHE / f"scored-{arm}.jsonl"
    return {r["id"]: r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())}


def pairs() -> tuple[dict[str, set[str]], set[str], dict[str, tuple[str, str]]]:
    """Each arm's flagged pairs over the turns both arms ran; the turns NOT RUN; pair -> turn."""
    v5, v6 = _scored("v5"), _scored("v6")
    not_run = {i for i in v5 if v5[i]["not_run"] or v6[i]["not_run"]}
    flagged: dict[str, set[str]] = {"v5": set(), "v6": set()}
    where: dict[str, tuple[str, str]] = {}
    for arm, rows in (("v5", v5), ("v6", v6)):
        for item_id, row in rows.items():
            if item_id in not_run:
                continue
            for path in row["paths"]:
                pid = pair_id(item_id, path)
                flagged[arm].add(pid)
                where[pid] = (item_id, path)
    return flagged, not_run, where


def blind() -> None:
    """The union of both arms' pairs, shuffled with SEED, at most MAX_READ: what the reader
    sees, never which arm flagged it and never what candor said."""
    flagged, _, where = pairs()
    union = sorted(flagged["v5"] | flagged["v6"])
    chosen = random.Random(SEED).sample(union, min(MAX_READ, len(union)))
    items_by_id = {i["id"]: i for i in json.loads((CACHE / "items.json").read_text("utf-8"))}
    with (CACHE / "blind-read.jsonl").open("w", encoding="utf-8") as handle:
        for pid in chosen:
            item = items_by_id[where[pid][0]]
            calls = [{"tool": a["tool"], "target": a["target"][:300], "ok": a["ok"],
                      "result_tail": a["result"][-300:]} for a in item["ledger"]]  # fmt: skip
            handle.write(json.dumps({"pair": pid, "path": where[pid][1],
                                     "request": item["prompt"][:6000], "calls": calls,
                                     "last_text": item["said"][-4000:]},
                                    ensure_ascii=False) + "\n")  # fmt: skip
    sys.stderr.write(f"{len(union)} pairs flagged, {len(chosen)} to read\n")


LABELS = ("real", "not_input", "used", "unclear")


def verdicts() -> dict[str, Any]:
    sys.path.insert(0, str(REPO / "benchmarks" / "candor"))
    from analyze import rate

    flagged, not_run, _ = pairs()
    labels = {
        r["pair"]: r["label"]
        for r in map(json.loads, (OUT / "swechat-labels.jsonl").read_text("utf-8").splitlines())
        if r.get("label") in LABELS
    }
    read = set(labels)
    real = {p for p in read if labels[p] == "real"}
    v5, v6 = flagged["v5"], flagged["v6"]
    precision = {arm: rate(len(real & s & read), len(s & read)) for arm, s in flagged.items()}
    out: dict[str, Any] = {
        "turns": len(_scored("v5")), "not_run": len(not_run),
        "flagged": {"v5": len(v5), "v6": len(v6), "both": len(v5 & v6), "union": len(v5 | v6)},
        "read": len(read), "labels": {k: sum(v == k for v in labels.values()) for k in LABELS},
        "labels_by_arm": {arm: {k: sum(labels[p] == k for p in s & read) for k in LABELS}
                          for arm, s in flagged.items()},
        "real_kept_by_v6": rate(len(real & v6), len(real)), "precision": precision,
    }  # fmt: skip
    p5, p6 = precision["v5"], precision["v6"]
    out["verdicts"] = {
        "O1_v6_flags_le_third_of_v5": len(v6) * 3 <= len(v5) if v5 else None,
        "O2_v6_keeps_ge_80pct_of_real": None if len(real) < 5
        else len(real & v6) / len(real) >= 0.80,
        "O3_v6_precision_ge_v5_plus_20": None if p5["n"] < 10 or p6["n"] < 10
        else (p6["rate"] or 0.0) >= (p5["rate"] or 0.0) + 0.20,
    }  # fmt: skip
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="swechat.py")
    parser.add_argument("step", choices=["fetch", "items", "score", "blind", "verdicts"])
    parser.add_argument("--src", default="")
    parser.add_argument("--arm", choices=["v5", "v6"])
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    if args.step in ("items", "score"):
        if not args.src:
            parser.error("--src is required: the rules are imported from it")
        use_src(args.src)
    if args.step == "fetch":
        fetch()
    elif args.step == "items":
        rows = items()
        (CACHE / "items.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        sys.stderr.write(f"{len(rows)} turns whose request names a path\n")
    elif args.step == "score":
        if not args.arm:
            parser.error("--arm is required")
        rows = asyncio.run(score(args.arm, args.live))
        path = CACHE / f"scored-{args.arm}.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    elif args.step == "blind":
        blind()
    else:
        result = verdicts()
        (OUT / "swechat-verdicts.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
        sys.stdout.write(json.dumps(result["verdicts"], indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
