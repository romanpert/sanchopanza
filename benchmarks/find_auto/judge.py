"""The judged arm of the substitution hook: Jev's `triage_many` over the recorded source-only
shortlists (`evaluate.py`'s `+code` queries), so judged any@k is measured, not extrapolated.

    .venv/Scripts/python.exe -m benchmarks.find_auto.judge          # replay recorded answers, free
    .venv/Scripts/python.exe -m benchmarks.find_auto.judge --live   # Jev, hard cap CAP_USD in code

Jobs: the issue-text query (`Q1+code`) of every hard session's instance and of the need dev set
(`benchmarks/find_need/need-table.json`), and the issue plus search words (`Q3+code`) at R4's fire
in every hard session where R4 fires. The judge path is `find_in_repo`'s (`select`): the 60-key
shortlist, in BM25 order, judged by `Squire.triage_many` with `context.repo.PURPOSE`; ranking =
kept fragments by p, then the rest in BM25 order (the retrieval run's `frag_judge`). `kept@k`
counts kept fragments only, which is what the hook would show.

Fragment texts are rebuilt from the work copy with `git show HEAD:<path>` and the same split as
`context.repo.chunks` (read only). The key is read from TYPESAFE_API_KEY in the environment and
never printed or written. Every live decision is recorded to `answers.jsonl` (hashed keys, no
text), so a rerun spends nothing; live calls stop once the spend reaches CAP_USD - MARGIN_USD.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import subprocess
import sys
import tarfile
from collections import defaultdict
from pathlib import Path, PurePath
from typing import Any

from .evaluate import (
    FACTS,
    RETRIEVAL,
    gold_lines,
    hits,
    parse_key,
    query_name,
    verified,
    work_copy,
)

HERE = Path(__file__).resolve().parent
ANSWERS = HERE / "answers.jsonl"
OUT = HERE / "judged-table.json"
NEED_TABLE = HERE.parent / "find_need" / "need-table.json"
CAP_USD = 0.50  # approved hard cap for the whole replay; a flag may lower it, never raise it
MARGIN_USD = 0.02  # stop live calls this far below the cap (one tournament costs well under it)
KS = (1, 3, 5)


class CappedReplay:
    """Recorded answers first; a live decision only while the spend is under the cap."""

    def __init__(self, live: Any, cap: float) -> None:
        from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider

        self.recorded = RecordedDecider.from_file(ANSWERS)
        self.live = RecordingDecider(live, ANSWERS) if live is not None else None
        self.cap = cap
        self.spent = 0.0
        self.live_calls = 0
        self.refused = 0
        self.name = "jev"

    async def decide(self, point: str, state: Any, questions: Any) -> Any:
        from sanchopanza.contract import Decision

        d = await self.recorded.decide(point, state, questions)
        if d.answers:
            return d
        if self.live is None or self.spent >= self.cap - MARGIN_USD:
            self.refused += 1
            return Decision(point, {}, "none", "-", error="not recorded, no live decider or cap")
        d = await self.live.decide(point, state, questions)
        self.spent += d.cost_usd
        self.live_calls += 1
        return d


def _archived(work: Path, paths: list[str]) -> dict[str, str]:
    """The files as `git archive` wrote them for the snapshot (same bytes, same decoding as
    `context.repo._read`), read in memory."""
    cmd = ["git", "-c", "core.autocrlf=false", "-C", str(work), "archive", "--format=tar",
           "HEAD", "--", *paths]  # fmt: skip
    raw = subprocess.run(cmd, capture_output=True, check=True, timeout=300).stdout
    out = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        for member in tar:
            handle = tar.extractfile(member) if member.isfile() else None
            if handle is not None:
                out[member.name] = handle.read().decode("utf-8", "replace")
    return out


def fragments(work: Path, keys: list[str]) -> dict[str, Any]:
    """The candidates of `keys`, rebuilt from the work copy's HEAD exactly as `chunks` cuts them."""
    from sanchopanza.context.blocks import PROSE_SUFFIXES, split
    from sanchopanza.context.repo import TARGET, _headline
    from sanchopanza.select import Candidate

    wanted: dict[str, set[str]] = defaultdict(set)
    for key in keys:
        wanted[parse_key(key)[0]].add(key)
    out: dict[str, Any] = {}
    texts = _archived(work, sorted(wanted))
    for path, want in wanted.items():
        text = texts.get(path, "")
        kind = "prose" if PurePath(path).suffix.lower() in PROSE_SUFFIXES else "code"
        for block in split(text, kind, target=TARGET):
            body = block.of(text)
            key = f"{path}:{block.first_line}-{block.last_line}"
            if key in want:
                out[key] = Candidate(key, f"{key} {_headline(body)}".strip(), body)
    return out


def jobs() -> list[dict[str, Any]]:
    """Unique (instance, retrieval name) pairs, with the sessions and sets each one serves."""
    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    dev = json.loads(NEED_TABLE.read_text(encoding="utf-8"))["dev_set"]
    found: dict[tuple[str, str], dict[str, Any]] = {}

    def add(instance: str, name: str, tag: str) -> None:
        job = found.setdefault((instance, name), {"instance": instance, "name": name, "tags": []})
        job["tags"].append(tag)

    for f in facts:
        if f["hard"]:
            add(f["instance"], "Q1+code", f"hard-Q1:{f['key']}")
            if f["fires"]["R4"]:
                name = query_name(f, "R4", "Q3+code")
                if name:
                    add(f["instance"], name, f"hard-R4:{f['key']}")
    for instance in dev:
        add(instance, "Q1+code", f"dev:{instance}")
    return list(found.values())


async def judge_one(job: dict[str, Any], query: str, decider: CappedReplay) -> dict[str, Any]:
    from sanchopanza import Squire
    from sanchopanza.context.repo import PURPOSE
    from sanchopanza.policy import Thresholds

    retrieved = json.loads((RETRIEVAL / f"{job['instance']}.json").read_text(encoding="utf-8"))
    keys = retrieved["queries"][job["name"]]["keys"]
    work = work_copy(job["instance"])
    assert work is not None
    found = fragments(work, keys)
    shortlist = [found[k] for k in keys if k in found]
    squire = Squire(decider, thresholds=Thresholds(max_usd=0.05, max_decisions=50))
    before, refused = decider.spent, decider.refused
    verdicts = await squire.triage_many(purpose=PURPOSE.format(query=query),
                                        pages=[(c.title, c.text) for c in shortlist])  # fmt: skip
    pairs = enumerate(zip(shortlist, verdicts, strict=False))
    kept = [(rank, c.key, p) for rank, (c, (keep, p)) in pairs if keep]
    kept.sort(key=lambda x: (-(x[2] if x[2] is not None else 0.5), x[0]))
    kept_keys = [k for _, k, _ in kept]
    ranked = kept_keys + [c.key for c in shortlist if c.key not in set(kept_keys)]
    return {**job, "rebuilt": len(shortlist), "shortlist": len(keys), "kept": len(kept_keys),
            "complete": decider.refused == refused, "usd": round(decider.spent - before, 6),
            "judged": ranked, "kept_keys": kept_keys, "free": keys}  # fmt: skip


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    table = verified()
    out: dict[str, Any] = {}
    groups = {"hard sessions, issue text (Q1+code)": "hard-Q1",
              "hard sessions, R4 fire, issue + search words (Q3+code)": "hard-R4",
              "need dev set, issue text (Q1+code)": "dev"}  # fmt: skip
    for label, tag in groups.items():
        counts: dict[str, int] = defaultdict(int)
        n = 0
        for r in rows:
            weight = sum(t.startswith(tag) for t in r["tags"])
            if not weight or not r["complete"]:
                continue
            lines = gold_lines(table[r["instance"]]["patch"])
            hf, hj, hk = (
                hits(r["free"], lines),
                hits(r["judged"], lines),
                hits(r["kept_keys"], lines),
            )
            n += weight
            for k in KS:
                counts[f"free any@{k}"] += weight * hf[f"any@{k}"]
                counts[f"judged any@{k}"] += weight * hj[f"any@{k}"]
                counts[f"kept-only any@{k}"] += weight * hk[f"any@{k}"]
                counts[f"judged hunk@{k}"] += weight * hj[f"hunk@{k}"]
        out[label] = {"n": n, **{k: f"{v}/{n}" for k, v in sorted(counts.items())}}
    return out


async def run(live: bool, cap: float) -> dict[str, Any]:
    inner = None
    if live:
        key = os.environ.get("TYPESAFE_API_KEY", "")
        if not key:
            raise SystemExit("--live needs TYPESAFE_API_KEY in the environment")
        from sanchopanza.providers import create

        inner = create("jev", api_key=key)
    decider = CappedReplay(inner, min(cap, CAP_USD))
    statements = {i: r["problem_statement"] for i, r in verified().items()}
    texts: dict[str, str] = {}
    for f in json.loads(FACTS.read_text(encoding="utf-8")):
        texts.update(f["query_text"])
    rows = []
    for job in jobs():
        base = job["name"].removesuffix("+code")
        query = statements[job["instance"]] if base == "Q1" else texts[base]
        rows.append(await judge_one(job, query, decider))
        print(f"{job['instance']} {job['name'][:10]} kept={rows[-1]['kept']} "
              f"spent={decider.spent:.4f}", file=sys.stderr)  # fmt: skip
    report = {
        "spend_usd": round(decider.spent, 6), "cap_usd": min(cap, CAP_USD),
        "live_calls": decider.live_calls, "refused_calls": decider.refused,
        "jobs": len(rows), "incomplete_jobs": sum(not r["complete"] for r in rows),
        "rebuilt_short": sum(r["rebuilt"] < r["shortlist"] for r in rows),
        "scores": score(rows),
    }  # fmt: skip
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cap", type=float, default=CAP_USD)
    args = parser.parse_args(argv)
    print(json.dumps(asyncio.run(run(args.live, args.cap)), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
