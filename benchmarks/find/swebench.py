"""Repository search (`sanchopanza.context.repo`) on SWE-bench Verified file localisation.

    python benchmarks/find/swebench.py --prepare        # clone the repositories (free, network)
    python benchmarks/find/swebench.py --run --live     # all arms, Jev spends (cap in code)
    python benchmarks/find/swebench.py --run            # replay recorded answers, free

The question a developer's agent faces every day: given an issue, which files must change?
The label is SWE-bench's own: the files the accepted patch edits. Nobody here labels anything.

Data: `princeton-nlp/SWE-bench_Verified` at REVISION, 500 real GitHub issues from 12 Python
repositories, each with the commit the fix was written against. A seeded sample of up to
PER_REPO instances per repository, so that django (231 of 500) does not decide the result.

Arms, every one over the repository checked out at the instance's base commit:
- `file_bm25`: BM25 over whole files (path and text), the classic retrieval baseline of the
  SWE-bench paper;
- `frag_bm25`: `repo.chunks` fragments ranked by BM25, files in order of first appearance;
- `frag_judge`: the BM25 shortlist of SHORTLIST fragments judged by `triage_many` (Jev), kept
  fragments first by p, then the rest of the shortlist by BM25.
The query is the issue text; the judge's purpose is its first 400 characters (the in-context
question's limit on purpose). The shortlist ceiling (a gold file among the SHORTLIST
fragments) is reported beside every arm.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "benchmarks" / "candor"))

from sanchopanza.context.repo import PURPOSE, chunks  # noqa: E402
from sanchopanza.select import index_of  # noqa: E402
from sanchopanza.text import BM25Index  # noqa: E402

REVISION = "c104f840cc67f8b6eec6f759ebc8b2693d585d4a"
DATA = Path.home() / ".cache" / "sanchopanza" / "find" / "swebench"
REPOS = DATA.parent / "repos"
OUT = REPO / "docs" / "results" / "2026-09-29-find"
ANSWERS = OUT / "answers.jsonl"
SCORED = OUT / "scored.jsonl"
SEED = 20260929
PER_REPO = 12
SHORTLIST = 60
JEV_CAP_USD = 0.50  # registered in prereg.md; a flag can lower it, never raise it
KS = (1, 3, 5, 10)


def instances() -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    rows = pq.read_table(DATA / "verified.parquet").to_pylist()
    rng = random.Random(SEED)
    by_repo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(rows, key=lambda r: r["instance_id"]):
        by_repo[row["repo"]].append(row)
    out = []
    for repo in sorted(by_repo):
        group = by_repo[repo]
        out += rng.sample(group, min(PER_REPO, len(group)))
    return sorted(out, key=lambda r: r["instance_id"])


def gold_files(patch: str) -> list[str]:
    return sorted(set(re.findall(r"^diff --git a/(\S+) b/", patch, re.M)))


def clone_dir(repo: str) -> Path:
    return REPOS / repo.replace("/", "__")


def prepare() -> None:
    REPOS.mkdir(parents=True, exist_ok=True)
    for repo in sorted({r["repo"] for r in instances()}):
        target = clone_dir(repo)
        if not (target / ".git").exists():
            url = f"https://github.com/{repo}.git"
            subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", url,
                            str(target)], check=True)  # fmt: skip


def checkout(repo: str, commit: str) -> Path:
    root = clone_dir(repo)
    subprocess.run(["git", "-C", str(root), "checkout", "-q", "-f", commit], check=True)
    subprocess.run(["git", "-C", str(root), "clean", "-q", "-fdx"], check=True)
    return root


def files_ranked(keys: list[str]) -> list[str]:
    """Files in order of the first fragment of each (`path:first-last` keys)."""
    seen: dict[str, None] = {}
    for key in keys:
        seen.setdefault(key.rsplit(":", 1)[0], None)
    return list(seen)


def hits(ranked: list[str], gold: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in KS:
        top = set(ranked[:k])
        out[f"any@{k}"] = any(g in top for g in gold)
        out[f"all@{k}"] = all(g in top for g in gold)
    return out


def _file_bm25(root: Path, query: str) -> list[str]:
    from sanchopanza.context.repo import _read, files

    paths, docs = [], []
    for rel in files(root):
        text = _read(root / rel)
        if text:
            paths.append(rel)
            docs.append(f"{rel}\n{text}")
    return [paths[i] for i, _ in BM25Index(docs).top(query, 50)]


class ReplayFirst:
    """Recorded answers first; a live decision only when none is recorded, under a total cap.
    Every live decision is written down (`RecordingDecider`), so a rerun spends nothing."""

    def __init__(self, live: Any, cap: float) -> None:
        from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider

        self.recorded = RecordedDecider.from_file(ANSWERS)
        self.live = RecordingDecider(live, ANSWERS) if live is not None else None
        self.cap = cap
        self.spent = 0.0
        self.name = "jev"

    async def decide(self, point: str, state: Any, questions: Any) -> Any:
        from sanchopanza.contract import Decision

        d = await self.recorded.decide(point, state, questions)
        if d.answers:
            return d
        if self.live is None or self.spent >= self.cap:
            return Decision(point, {}, "none", "-", error="not recorded, no live decider")
        d = await self.live.decide(point, state, questions)
        self.spent += d.cost_usd
        return d


async def one(row: dict[str, Any], decider: ReplayFirst) -> dict[str, Any]:
    from sanchopanza import Squire
    from sanchopanza.policy import Thresholds
    from sanchopanza.select import select

    root = checkout(row["repo"], row["base_commit"])
    query = row["problem_statement"]
    gold = gold_files(row["patch"])
    started = time.time()
    fragments = chunks(root)
    index = index_of(fragments)
    short = index.top(query, SHORTLIST)
    keys = [fragments[i].key for i, _ in short]
    out: dict[str, Any] = {
        "id": row["instance_id"], "repo": row["repo"], "gold": gold,
        "fragments": len(fragments), "index_s": round(time.time() - started, 2),
        "ceiling": any(g in {k.rsplit(":", 1)[0] for k in keys} for g in gold),
        "file_bm25": hits(_file_bm25(root, query), gold),
        "frag_bm25": hits(files_ranked(keys), gold),
    }  # fmt: skip
    # The product path: `select` -> `Squire.triage_many` (the tournament), a fresh meter per
    # instance with a generous per-job cap; the total cap is the decider's.
    squire = Squire(decider, thresholds=Thresholds(max_usd=0.05, max_decisions=50))
    before, t0 = decider.spent, time.time()
    picks = await select(query, fragments, squire=squire, purpose=PURPOSE.format(query=query),
                         shortlist_k=SHORTLIST, keep=SHORTLIST, index=index)  # fmt: skip
    kept = [p.candidate.key for p in picks]
    judged = any(p.p is not None for p in picks)
    rest = [k for k in keys if k not in set(kept)]
    out["frag_judge"] = hits(files_ranked(kept + rest), gold)
    out["judge_usd"] = round(decider.spent - before, 6)
    out["judge_s"] = round(time.time() - t0, 2)
    out["judge_answered"] = judged
    out["kept"] = len(kept) if judged else None
    return out


def summary(scored: list[dict[str, Any]]) -> dict[str, Any]:
    from analyze import rate

    out: dict[str, Any] = {"n": len(scored)}
    for arm in ("file_bm25", "frag_bm25", "frag_judge"):
        out[arm] = {
            m: rate(sum(s[arm][m] for s in scored), len(scored))
            for m in (f"{w}@{k}" for w in ("any", "all") for k in KS)
        }
    out["ceiling"] = rate(sum(s["ceiling"] for s in scored), len(scored))
    costs = sorted(s["judge_usd"] for s in scored)
    out["judge_usd_total"] = round(sum(costs), 4)
    out["judge_usd_median"] = costs[len(costs) // 2] if costs else None
    times = sorted(s["judge_s"] for s in scored)
    out["judge_s_median"] = times[len(times) // 2] if times else None
    by_repo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in scored:
        by_repo[s["repo"]].append(s)
    out["by_repo"] = {
        repo: {arm: sum(s[arm]["any@5"] for s in g) for arm in ("file_bm25", "frag_bm25",
                                                                 "frag_judge")} | {"n": len(g)}
        for repo, g in sorted(by_repo.items())
    }  # fmt: skip
    a = lambda arm, m: out[arm][m]["rate"] or 0.0  # noqa: E731
    out["verdicts"] = {
        "F1_judge_any5_ge_file_bm25_plus_10": a("frag_judge", "any@5")
        >= a("file_bm25", "any@5") + 0.10,
        "F2_judge_any1_ge_frag_bm25_plus_5": a("frag_judge", "any@1")
        >= a("frag_bm25", "any@1") + 0.05,
        "F3_median_judge_cost_le_0_005": (out["judge_usd_median"] or 0.0) <= 0.005,
    }
    return out


async def run(live: bool, cap: float) -> list[dict[str, Any]]:
    inner = None
    if live:
        from sanchopanza.providers import create

        inner = create("jev", api_key=os.environ["TYPESAFE_API_KEY"])
    decider = ReplayFirst(inner, min(cap, JEV_CAP_USD))
    out = []
    for row in instances():  # one checkout at a time: the repositories are shared
        out.append(await one(row, decider))
        print(f"{row['instance_id']}: {out[-1]['frag_judge']['any@5']} "
              f"{decider.spent:.4f} USD", file=sys.stderr)  # fmt: skip
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--jev-cap", type=float, default=JEV_CAP_USD)
    args = parser.parse_args(argv)
    if args.prepare:
        prepare()
        return 0
    if not args.run:
        parser.error("--prepare or --run")
    OUT.mkdir(parents=True, exist_ok=True)
    scored = asyncio.run(run(args.live, args.jev_cap))
    SCORED.write_text("\n".join(json.dumps(s) for s in scored) + "\n", encoding="utf-8")
    result = summary(scored)
    (OUT / "summary.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result["verdicts"], indent=1), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
