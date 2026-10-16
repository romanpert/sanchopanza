"""A6 ceiling: how much of a session's expensive-model cost could imposing find_in_repo save?

Free and offline: recorded Claude Code streams, local work copies, BM25 only (find_in_repo
without a key, kind="code", exactly `context.repo.source_first(...).top(query, k)`). No Jev,
no claude -p, no other paid API. Result: docs/results/2026-10-16-a6-ceiling/.

Per bug request (long chains) or session (singles):
  - the first touch of a gold file (a file the gold patch changes):
      view      the primary (HEADLINE): a Read / Edit / Write / MultiEdit of a gold path, or a
                Bash/PowerShell/Grep call whose arguments name a gold file
      readedit  a sensitivity: a Read / Edit / Write / MultiEdit of a gold path only
  - API requests, tool calls and USD (API list rates, meter.OWNER_RATES) of the expensive model
    strictly before the message that makes that touch (requests 0..i-1; `shift`: 1..i, leaving
    out the session's first request, the system prompt's cache write); a request that never
    touches a gold file counts in full under "never=all" and not at all under "never=0";
  - whether find's top-5 for the issue text holds a gold file.
Each request is priced from the session's transcript (`transcript*.jsonl` beside the streams),
matched by message id, as the long runner meters calls: a stream-json `assistant` event carries
the usage at message start, so its output tokens are short. A session with no transcript is
priced from its stream, and the report counts those requests.
Ceiling = sum(cost before gold | find top-5 hit) / sum(all expensive-model cost of the sessions).
Bootstrap: resample sessions (a long chain arm is one Claude Code session; a single is one), and
for the long chains also chains.

    python benchmarks/find_need/a6_ceiling.py retrieve --runs <runs root>  # snapshots + BM25 top-k
    python benchmarks/find_need/a6_ceiling.py report --runs <runs root>    # tables + full results
    python benchmarks/find_need/a6_ceiling.py summary                      # the published JSON

`--runs` (or SANCHOPANZA_A6_RUNS) is the folder that holds the long-chain run roots (L, L-n2,
...). `--work` (or SANCHOPANZA_A6_WORK, default ~/.cache/sanchopanza/a6-ceiling) holds the
snapshots, the BM25 top-k cache (find-top.json) and the full results with every unit
(a6-results.json); those stay local. `summary` writes aggregates and per-session figures only,
with no issue text, no file path and no message id.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tarfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "benchmarks"))
sys.path.insert(0, str(REPO))

import meter  # noqa: E402
from benchmarks.find_need.replay import Call, is_gold, names_gold  # noqa: E402

from sanchopanza.harness.find_nudge import EDIT_TOOLS, SHELL_TOOLS  # noqa: E402

CACHE = Path.home() / ".cache" / "sanchopanza"
MANIFESTS = REPO / "benchmarks" / "adopt" / "long60"
PUBLISHED = REPO / "docs" / "results" / "2026-10-16-a6-ceiling" / "a6-ceiling.json"
KS = (5, 8)
SEED = 20261015
B = 10_000
VIEW_TOOLS = SHELL_TOOLS | {"Grep"}
READ_EDIT = {"Read"} | set(EDIT_TOOLS)
THRESHOLD = 0.05
HEADLINE = "view|never=all|top5"


@dataclass(frozen=True)
class Paths:
    runs: Path  # the long-chain run roots
    work: Path  # snapshots, find-top.json, a6-results.json

    @property
    def snap(self) -> Path:
        return self.work / "snap"

    @property
    def tops(self) -> Path:
        return self.work / "find-top.json"

    @property
    def out(self) -> Path:
        return self.work / "a6-results.json"


# ---- which sessions ------------------------------------------------------------------------------

# Long chains: every recorded arm without sanchopanza (N clean, Ne = N + compact window,
# Nl = N + early compaction), on 2.1.287 with an empty CLAUDE_CONFIG_DIR. A arms load sanchopanza.
LONG_ROOTS = ["L", "L-n2", "L-n2c", "L-ne", "L-ne2c", "L-compact", "L-compact-conan2"]
NO_SANCHO_ARMS = {"N", "Ne", "Nl"}
# Phase B (2026-10-0x): Sonnet 5.5, N arm, Claude Code 2.1.285 with a user configuration loaded.
PHASE_B_CHAINS = ("pydantic__pydantic-long40-1", "encode__starlette-long-1r1")


def long_arms(paths: Paths) -> list[dict[str, Any]]:
    out = []
    for root in LONG_ROOTS:
        for row_path in sorted((paths.runs / root / "runs").glob("*/*/row.json")):
            row = json.loads(row_path.read_text(encoding="utf-8"))
            if row.get("arm") not in NO_SANCHO_ARMS:
                continue
            out.append(
                {
                    "dir": row_path.parent,
                    "row": row,
                    "chain": row["chain"],
                    "model": row["model"],
                    "arm": row["arm"],
                    "work": Path(row["work"]),
                    "label": f"{root}/{row['run']}/{row['arm']}",
                    "group": "long60-clean",
                }
            )
    for chain in PHASE_B_CHAINS:
        d = CACHE / "adopt" / "runs" / chain / "N"
        row = json.loads((d / "row.json").read_text(encoding="utf-8"))
        out.append(
            {
                "dir": d,
                "row": row,
                "chain": row["chain"],
                "model": row["model"],
                "arm": row["arm"],
                "work": CACHE / "adopt" / "work" / f"{chain}-N",
                "label": f"phaseB/{row['chain']}/{row['arm']}",
                "group": "phaseB-owner-setup",
            }
        )
    return out


# ---- gold files and issue texts ------------------------------------------------------------------

DIFF = re.compile(r"^diff --git a/(\S+) b/(\S+)", re.M)


def patch_files(patch: str) -> list[str]:
    return sorted({m.group(2) for m in DIFF.finditer(patch)})


def bug_rows() -> dict[str, dict[str, Any]]:
    """instance_id -> row with patch and problem_statement, from every drawn chain and spare."""
    found: dict[str, dict[str, Any]] = {}

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            if "instance_id" in x and "patch" in x and "problem_statement" in x:
                found.setdefault(x["instance_id"], x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for p in (CACHE / "adopt").glob("*-full.json"):
        walk(json.loads(p.read_text(encoding="utf-8")))
    return found


def manifest_gold() -> dict[str, list[str]]:
    out = {}
    for p in MANIFESTS.glob("*.json"):
        for b in json.loads(p.read_text(encoding="utf-8"))["bugs"]:
            out[b["instance_id"]] = b["files"]
    return out


def is_test_path(path: str) -> bool:
    from sanchopanza.context.repo import is_test

    return is_test(path)


def gold_of(instance: str, rows: dict[str, Any], manifest: dict[str, list[str]]) -> list[str]:
    if instance in manifest:
        return manifest[instance]
    files = patch_files(rows[instance]["patch"])
    code = [f for f in files if not is_test_path(f)]
    return code or files


# ---- streams -------------------------------------------------------------------------------------


def transcript_prices(folder: Path) -> dict[str, meter.Request]:
    """Message id -> the request as the session transcripts beside the streams report it
    (`transcript.jsonl`, `transcript-<n>.jsonl`): the final usage, output tokens included."""
    found: dict[str, meter.Request] = {}
    for path in sorted(folder.glob("transcript*.jsonl")):
        found.update({r.id: r for r in meter.transcript_requests(path)})
    return found


def parse_stream(
    path: Path, prices: dict[str, meter.Request] | None = None
) -> list[dict[str, Any]]:
    """Main-thread API messages in order (deduplicated by id) with their tool uses, plus
    `compact` markers. Subagent messages (parent_tool_use_id) are kept apart with the index of
    the main message whose tool use spawned them. Each message is priced from `prices` (the
    transcript's request of the same id) when it is there, else from the stream's own usage,
    whose output tokens are the count at message start; `priced` says which."""
    prices = prices or {}
    order: list[Any] = []
    msgs: dict[str, dict[str, Any]] = {}
    seen_tools: set[str] = set()
    tool_owner: dict[str, str] = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if not isinstance(e, dict):
                continue
            if e.get("type") == "system" and e.get("subtype") == "compact_boundary":
                order.append("compact")
                continue
            if e.get("type") != "assistant":
                continue
            m = e.get("message") or {}
            req = meter.request_of(m, bool(e.get("parent_tool_use_id")))
            if req is None or req.model == "<synthetic>":
                continue
            parent = e.get("parent_tool_use_id")
            if req.id not in msgs:
                msgs[req.id] = {"id": req.id, "req": req, "tools": [], "parent": parent}
                order.append(req.id)
            msgs[req.id]["req"] = req
            for b in m.get("content") or []:
                if (
                    isinstance(b, dict)
                    and b.get("type") == "tool_use"
                    and b.get("id") not in seen_tools
                ):
                    seen_tools.add(b["id"])
                    tool_owner[b["id"]] = req.id
                    given = b.get("input") if isinstance(b.get("input"), dict) else {}
                    msgs[req.id]["tools"].append((b.get("name"), given))
    out = []
    for item in order:
        if item == "compact":
            out.append({"compact": True})
            continue
        m = msgs[item]
        r = prices.get(item, m["req"])
        out.append(
            {
                "compact": False,
                "id": r.id,
                "model": r.model,
                "side": m["parent"] is not None,
                "owner": tool_owner.get(m["parent"]) if m["parent"] else None,
                "cost": r.cost(meter.OWNER_RATES),
                "context": r.context,
                "tools": m["tools"],
                "priced": "transcript" if item in prices else "stream",
            }
        )
    return out


def touches(name: str, given: dict[str, Any], gold: list[str], mode: str) -> bool:
    path = str(given.get("file_path") or given.get("notebook_path") or "")
    if name in READ_EDIT and path and is_gold(path, gold):
        return True
    if mode == "view" and name in VIEW_TOOLS:
        return names_gold(Call(name, given), gold)
    return False


def _cost_of(main: list[dict[str, Any]], side: list[dict[str, Any]], expensive: str) -> float:
    """The expensive model's cost of these main-thread requests and the subagents they spawned."""
    ids = {x["id"] for x in main}
    cost = sum(x["cost"] for x in main if x["model"] == expensive)
    return cost + sum(s["cost"] for s in side if s["owner"] in ids and s["model"] == expensive)


def before_gold(
    entries: list[dict[str, Any]], gold: list[str], expensive: str, mode: str, *,
    shift: bool = False,
) -> dict[str, Any]:  # fmt: skip
    """Expensive-model cost, API requests and tool calls before the first gold touch: requests
    0..i-1 of the main thread, or with `shift` 1..i (the session's first request, which carries
    the system prompt's cache write, is one find cannot remove; the touching request is)."""
    main = [e for e in entries if not e["compact"] and not e["side"]]
    side = [e for e in entries if not e["compact"] and e["side"]]
    total = sum(e["cost"] for e in main + side if e["model"] == expensive)
    other = sum(e["cost"] for e in main + side if e["model"] != expensive)
    calls = 0
    for i, e in enumerate(main):
        for name, given in e["tools"]:
            if touches(name, given, gold, mode):
                cost = _cost_of(main[1 : i + 1] if shift else main[:i], side, expensive)
                added = max(0, e["context"] - main[0]["context"]) if i else 0
                return {
                    "touched": True,
                    "at_request": i,
                    "calls_before": calls,
                    "cost_before": cost,
                    "total": total,
                    "other_models": other,
                    "added_tokens": added,
                    "touch_msg": e["id"],
                }
            calls += 1
    return {
        "touched": False,
        "at_request": len(main),
        "calls_before": calls,
        "cost_before": total - _cost_of(main[:1], side, expensive) if shift else total,
        "total": total,
        "other_models": other,
        "added_tokens": 0,
        "touch_msg": None,
    }


# ---- find's top-k --------------------------------------------------------------------------------


def export(work: Path, dest: Path) -> None:
    if dest.exists():
        return
    tmp = dest.with_name(dest.name + ".part")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    tar = tmp.with_suffix(".tar")
    subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=false",
            "-C",
            str(work),
            "archive",
            "--format=tar",
            "-o",
            str(tar),
            "HEAD",
        ],
        check=True,
        timeout=900,
        stdin=subprocess.DEVNULL,
    )
    with tarfile.open(tar) as t:
        for member in t:
            if member.isfile():
                t.extract(member, tmp, filter="data")
    tar.unlink()
    tmp.rename(dest)


def retrieve(paths: Paths) -> None:
    from sanchopanza.context.repo import indexed, source_first

    os.environ["GIT_CEILING_DIRECTORIES"] = str(paths.snap)
    rows, manifest = bug_rows(), manifest_gold()
    tops = json.loads(paths.tops.read_text(encoding="utf-8")) if paths.tops.exists() else {}
    by_chain: dict[str, dict[str, Any]] = {}
    for arm in long_arms(paths):
        by_chain.setdefault(arm["chain"], {"work": arm["work"], "ids": set()})
        for c in arm["row"]["calls"]:
            iid = c.get("instance_id", "")
            if iid and not iid.startswith("callback"):
                by_chain[arm["chain"]]["ids"].add(iid)
    for chain, info in sorted(by_chain.items()):
        todo = [i for i in sorted(info["ids"]) if i not in tops]
        if not todo:
            continue
        root = paths.snap / chain
        export(info["work"], root)
        candidates, ranked = source_first(root)
        _, every = indexed(root)
        print(chain, len(candidates), "fragments;", len(todo), "bugs", flush=True)
        for iid in todo:
            q = rows[iid]["problem_statement"]
            code = [candidates[i].key for i, _ in ranked.top(q, max(KS))]
            alls = [candidates[i].key for i, _ in every.top(q, 5)]
            tops[iid] = {
                "chain": chain,
                "code": code,
                "all5": alls,
                "gold": gold_of(iid, rows, manifest),
            }
        paths.work.mkdir(parents=True, exist_ok=True)
        paths.tops.write_text(json.dumps(tops, indent=1), encoding="utf-8")


def path_of(key: str) -> str:
    return key.rsplit(":", 1)[0].replace("\\", "/")


def hit(keys: list[str], gold: list[str]) -> bool:
    return any(is_gold(path_of(k), gold) for k in keys)


# ---- sessions to units ---------------------------------------------------------------------------


def stream_for(d: Path, request: int) -> Path | None:
    for name in (f"stream-{request}.jsonl", f"stream-{request}-dead.jsonl"):
        if (d / name).exists():
            return d / name
    return None


SHIFTED = ("readedit_shift", "readedit"), ("view_shift", "view")


def add_modes(unit: dict[str, Any], entries: list[dict[str, Any]], gold: list[str],
              expensive: str) -> None:  # fmt: skip
    """The unit's reach of the gold in both modes, and both shifted (requests 1..i)."""
    for mode in ("readedit", "view"):
        unit[mode] = before_gold(entries, gold, expensive, mode)
    for key, mode in SHIFTED:
        unit[key] = before_gold(entries, gold, expensive, mode, shift=True)


def priced_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    msgs = [e for e in entries if not e["compact"]]
    return {"transcript": sum(e["priced"] == "transcript" for e in msgs),
            "stream": sum(e["priced"] == "stream" for e in msgs)}  # fmt: skip


def long_units(tops: dict[str, Any], paths: Paths) -> list[dict[str, Any]]:
    """One unit per bug request, with callbacks kept for the session's total."""
    units = []
    for arm in long_arms(paths):
        expensive = arm["model"]
        prices = transcript_prices(arm["dir"])
        for c in arm["row"]["calls"]:
            path = stream_for(arm["dir"], c["request"])
            if path is None:
                continue
            entries = parse_stream(path, prices)
            iid = c.get("instance_id", "")
            is_bug = bool(iid) and not iid.startswith("callback")
            unit = {
                "session": arm["label"],
                "group": arm["group"],
                "model": expensive,
                "arm": arm["arm"],
                "chain": arm["chain"],
                "request": c["request"],
                "instance": iid,
                "bug": is_bug,
                "dead": path.name.endswith("-dead.jsonl"),
                "priced": priced_counts(entries),
            }
            if is_bug:
                t = tops[iid]
                gold = t["gold"]
                unit.update(
                    gold=gold,
                    hit5=hit(t["code"][:5], gold),
                    hit8=hit(t["code"][:8], gold),
                    hit5_all=hit(t["all5"], gold),
                    top5=[path_of(k) for k in t["code"][:5]],
                )
                add_modes(unit, entries, gold, expensive)
            else:
                main = [e for e in entries if not e["compact"]]
                total = sum(e["cost"] for e in main if e["model"] == expensive)
                other = sum(e["cost"] for e in main if e["model"] != expensive)
                for mode in ("readedit", "view", "readedit_shift", "view_shift"):
                    unit[mode] = {
                        "touched": False,
                        "cost_before": 0.0,
                        "total": total,
                        "other_models": other,
                        "calls_before": 0,
                        "at_request": 0,
                        "added_tokens": 0,
                        "touch_msg": None,
                    }
            unit["entries"] = entries
            units.append(unit)
    add_carry(units)
    for u in units:
        u.pop("entries", None)
    return units


def add_carry(units: list[dict[str, Any]]) -> None:
    """Context carried: the tokens the pre-gold exploration added are re-read (cache read rate)
    by every later main-thread request of the same session until a compaction."""
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for u in units:
        by_session[u["session"]].append(u)
    for session_units in by_session.values():
        seq = []  # (unit index, entry)
        for k, u in enumerate(session_units):
            for e in u["entries"]:
                if e["compact"] or not e["side"]:
                    seq.append((k, e))
        for k, u in enumerate(session_units):
            rate = meter.rates_of(meter.OWNER_RATES, u["model"]).read / 1e6
            for mode in ("readedit", "view"):
                b = u[mode]
                b["carry"] = 0.0
                if not u["bug"] or not b.get("touched") or not b["added_tokens"]:
                    continue
                start = next(
                    i
                    for i, (kk, e) in enumerate(seq)
                    if kk == k and not e["compact"] and e["id"] == b["touch_msg"]
                )
                later = 0
                for _, e in seq[start + 1 :]:
                    if e["compact"]:
                        break
                    later += 1
                b["carry"] = b["added_tokens"] * rate * later


def single_units() -> list[dict[str, Any]]:
    """Haiku 4.5 single SWE-bench Verified sessions (find_need's 179), N-like arms only, with
    find_auto's recorded BM25 retrieval (Q1 = issue text, +code = kind code)."""
    rows = json.loads((CACHE / "find-need" / "sessions.json").read_text(encoding="utf-8"))
    units = []
    for r in rows:
        if r["source"] == "chains" or not r["arm"].startswith("N"):
            continue
        ret = CACHE / "find-auto" / "retrieval" / f"{r['instance']}.json"
        got = json.loads(ret.read_text(encoding="utf-8")).get("queries", {}) if ret.exists() else {}
        if "Q1+code" not in got:
            continue
        stream = CACHE / r["stream"]
        entries = parse_stream(stream, transcript_prices(stream.parent))
        expensive = r["model"]
        gold = r["gold"]
        code, alls = got["Q1+code"]["keys"], got["Q1"]["keys"]
        u = {
            "session": f"{r['source']}:{r['instance']}:{r['arm']}:{r['variant']}",
            "group": "singles-haiku",
            "model": expensive,
            "arm": r["arm"],
            "chain": None,
            "request": 1,
            "instance": r["instance"],
            "bug": True,
            "gold": gold,
            "hit5": hit(code[:5], gold),
            "hit8": hit(code[:8], gold),
            "hit5_all": hit(alls[:5], gold),
            "top5": [path_of(k) for k in code[:5]],
            "dead": False,
            "priced": priced_counts(entries),
            "entries": entries,
        }
        add_modes(u, entries, gold, expensive)
        units.append(u)
    add_carry(units)
    for u in units:
        u.pop("entries", None)
    return units


# ---- statistics ----------------------------------------------------------------------------------


def ceiling(
    units: list[dict[str, Any]],
    mode: str,
    hitkey: str = "hit5",
    never: str = "all",
    carry: bool = False,
    perfect: bool = False,
) -> tuple[float, float]:
    num = den = 0.0
    for u in units:
        b = u[mode]
        den += b["total"]
        if not u["bug"] or not (perfect or u[hitkey]):
            continue
        if not b["touched"] and never == "0":
            continue
        num += b["cost_before"] + (b.get("carry", 0.0) if carry else 0.0)
    return num, den


def boot(units: list[dict[str, Any]], key: str = "session", **kw: Any) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for u in units:
        groups[u[key] if key != "unit" else f"{u['session']}#{u['request']}"].append(u)
    parts = {g: ceiling(us, **kw) for g, us in groups.items()}
    names = list(parts)
    n, d = (sum(parts[g][0] for g in names), sum(parts[g][1] for g in names))
    rng = random.Random(SEED)
    stats = []
    for _ in range(B):
        pick = [names[rng.randrange(len(names))] for _ in names]
        nn = sum(parts[g][0] for g in pick)
        dd = sum(parts[g][1] for g in pick)
        stats.append(nn / dd if dd else 0.0)
    stats.sort()
    return {
        "ceiling": n / d if d else None,
        "lo": stats[int(0.025 * B)],
        "hi": stats[int(0.975 * B) - 1],
        "num_usd": round(n, 4),
        "den_usd": round(d, 4),
        "clusters": len(names),
    }


def describe(units: list[dict[str, Any]]) -> dict[str, Any]:
    bugs = [u for u in units if u["bug"]]
    out: dict[str, Any] = {
        "sessions": len({u["session"] for u in units}),
        "bug_units": len(bugs),
        "requests_all": len(units),
        "hit5": sum(u["hit5"] for u in bugs),
        "hit8": sum(u["hit8"] for u in bugs),
        "hit5_kind_all": sum(u["hit5_all"] for u in bugs),
        "total_expensive_usd": round(sum(u["readedit"]["total"] for u in units), 3),
        "other_models_usd": round(sum(u["readedit"]["other_models"] for u in units), 3),
        "readedit_never_view_touched": sum(
            not u["readedit"]["touched"] and u["view"]["touched"] for u in bugs
        ),
        "dead_bug_units": sum(bool(u.get("dead")) for u in bugs),
        "requests_priced": {
            k: sum(u["priced"][k] for u in units if "priced" in u) for k in ("transcript", "stream")
        },
        "sessions_without_transcript": len(
            {u["session"] for u in units if "priced" in u and not u["priced"]["transcript"]}
        ),
    }
    for mode in ("readedit", "view"):
        touched = [u for u in bugs if u[mode]["touched"]]
        calls = sorted(u[mode]["calls_before"] for u in touched)
        reqs = sorted(u[mode]["at_request"] for u in touched)
        out[mode] = {
            "touched": len(touched),
            "never": len(bugs) - len(touched),
            "calls_before_p50": calls[len(calls) // 2] if calls else None,
            "calls_before_p90": calls[int(0.9 * len(calls))] if calls else None,
            "requests_before_p50": reqs[len(reqs) // 2] if reqs else None,
            "requests_before_p90": reqs[int(0.9 * len(reqs))] if reqs else None,
            "cost_before_usd_touched": round(sum(u[mode]["cost_before"] for u in touched), 3),
            "cost_never_touched_usd": round(
                sum(u[mode]["total"] for u in bugs if not u[mode]["touched"]), 3
            ),
            "cost_before_hit_touched_usd": round(
                sum(u[mode]["cost_before"] for u in touched if u["hit5"]), 3
            ),
            "carry_hit_usd": round(sum(u[mode].get("carry", 0.0) for u in touched if u["hit5"]), 3),
        }
    return out


def report(paths: Paths) -> None:
    tops = json.loads(paths.tops.read_text(encoding="utf-8"))
    units = long_units(tops, paths) + single_units()
    blocks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for u in units:
        blocks[f"{u['group']} | {u['model']}"].append(u)
    result: dict[str, Any] = {"threshold": THRESHOLD, "blocks": {}}
    for name, us in sorted(blocks.items()):
        res = {"describe": describe(us), "ceilings": {}}
        for mode in ("readedit", "view"):
            for never in ("all", "0"):
                tag = f"{mode}|never={never}"
                res["ceilings"][tag + "|top5"] = boot(us, mode=mode, never=never)
                res["ceilings"][tag + "|top5|by-request"] = boot(
                    us, key="unit", mode=mode, never=never
                )
            res["ceilings"][f"{mode}|never=all|top8"] = boot(us, mode=mode, hitkey="hit8")
            res["ceilings"][f"{mode}|never=all|top5-kind-all"] = boot(
                us, mode=mode, hitkey="hit5_all"
            )
            res["ceilings"][f"{mode}|never=all|top5+carry"] = boot(us, mode=mode, carry=True)
            res["ceilings"][f"{mode}|never=all|perfect-find"] = boot(us, mode=mode, perfect=True)
            res["ceilings"][f"{mode}|never=all|perfect-find+carry"] = boot(
                us, mode=mode, perfect=True, carry=True
            )
        res["ceilings"]["view_shift|never=all|top5"] = boot(us, mode="view_shift")
        res["ceilings"]["readedit_shift|never=0|top5"] = boot(us, mode="readedit_shift", never="0")
        if all(u["chain"] for u in us):
            res["ceilings"][HEADLINE + "|by-chain"] = boot(us, key="chain", mode="view")
        res["by_arm"] = {
            arm: boot([u for u in us if u["arm"] == arm], mode="view")
            for arm in sorted({u["arm"] for u in us})
        }
        per_session = defaultdict(lambda: [0.0, 0.0, 0, 0])
        for u in us:
            n, d = ceiling([u], mode="readedit")
            s = per_session[u["session"]]
            s[0] += n
            s[1] += d
            s[2] += int(u["bug"])
            s[3] += int(u["bug"] and u["hit5"])
        res["per_session_readedit_top5"] = {
            k: {
                "ceiling": round(v[0] / v[1], 4) if v[1] else None,
                "usd": round(v[1], 3),
                "bugs": v[2],
                "hit5": v[3],
            }
            for k, v in sorted(per_session.items())
        }
        result["blocks"][name] = res
        d = res["describe"]
        print(
            f"\n== {name}: {d['sessions']} sessions, {d['bug_units']} bug units, "
            f"find top5 hit {d['hit5']}/{d['bug_units']}, ${d['total_expensive_usd']}"
        )
        for tag, c in res["ceilings"].items():
            print(
                f"  {tag:42s} {100 * c['ceiling']:6.2f} %  "
                f"[{100 * c['lo']:5.2f}, {100 * c['hi']:5.2f}]"
                f"  ({c['num_usd']} / {c['den_usd']} USD, {c['clusters']} clusters)"
            )
    result["units"] = units
    paths.work.mkdir(parents=True, exist_ok=True)
    paths.out.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")


# ---- the published summary -----------------------------------------------------------------------


def _ratio(num: float, den: float) -> float | None:
    return round(num / den, 4) if den else None


def per_session(units: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per session: bugs, top-5 hits, the expensive model's USD, and the headline ceiling
    (view, never=all, top 5) beside the Read/Edit-only one with never-touched requests at 0."""
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for u in units:
        by[u["session"]].append(u)
    out = {}
    for name, us in sorted(by.items()):
        view_n, den = ceiling(us, mode="view")
        read_n, _ = ceiling(us, mode="readedit", never="0")
        bugs = [u for u in us if u["bug"]]
        out[name] = {
            "model": us[0]["model"],
            "arm": us[0]["arm"],
            "bugs": len(bugs),
            "hit5": sum(bool(u["hit5"]) for u in bugs),
            "usd": round(den, 3),
            "view_top5": _ratio(view_n, den),
            "readedit_never0_top5": _ratio(read_n, den),
        }
    return out


def summary(full: Path, dest: Path) -> dict[str, Any]:
    """Aggregates and per-session figures from the full results: no unit, issue text, gold or
    top-k path, nor message id."""
    result = json.loads(full.read_text(encoding="utf-8"))
    units_by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for u in result["units"]:
        units_by[f"{u['group']} | {u['model']}"].append(u)
    blocks = {}
    for name, block in result["blocks"].items():
        blocks[name] = {
            "describe": block["describe"],
            "ceilings": block["ceilings"],
            "headline": block["ceilings"][HEADLINE],
            "per_session": per_session(units_by[name]),
        }
    out = {
        "question": "at most what share of the expensive model's cost imposing find could save",
        "headline": HEADLINE,
        "threshold": result["threshold"],
        "bootstrap": {"draws": B, "seed": SEED, "unit": "session (or request, 'by-request')"},
        "rates": "API list rates, benchmarks/meter.py OWNER_RATES",
        "blocks": blocks,
    }
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("step", choices=("retrieve", "report", "summary"))
    parser.add_argument(
        "--runs",
        type=Path,
        default=os.environ.get("SANCHOPANZA_A6_RUNS"),
        help="the folder with the long-chain run roots (SANCHOPANZA_A6_RUNS)",
    )
    parser.add_argument(
        "--work",
        type=Path,
        default=os.environ.get("SANCHOPANZA_A6_WORK", CACHE / "a6-ceiling"),
        help="snapshots, top-k cache and full results (SANCHOPANZA_A6_WORK)",
    )
    parser.add_argument("--out", type=Path, default=PUBLISHED, help="summary: where to write")
    args = parser.parse_args(argv)
    if args.step == "summary":
        summary(Path(args.work) / "a6-results.json", args.out)
        return 0
    if args.runs is None:
        parser.error("--runs (or SANCHOPANZA_A6_RUNS) is required for retrieve and report")
    paths = Paths(runs=Path(args.runs), work=Path(args.work))
    {"retrieve": retrieve, "report": report}[args.step](paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
