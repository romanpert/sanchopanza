"""v6 against v5 on the adoption chains' real sessions, through the product's own hooks (review
of v6, M9: `v6_chain.py` built the tree part from the same patches as the truth, an upper bound).

Per arm, two local clones of its work folder at the chain's base (read-only `git clone
--local`; nothing in `adopt/` is written). Phase 1, recording, as the run went: for each request,
the hook's UserPromptSubmit (start snapshot) on clone A, then A moves to the request's end state
file by file (from clone B with `diff-<i>.patch` applied, the run's own patch), then its Stop
(records, tree, claims). Paths in the transcript are rewritten from the work folder to A. Phase
2, the touch: each request as a new session holding the earlier requests' records, its file
tools (v5) and also its Bash and PowerShell calls (v6) sent through `memory_hook.touch`. Truth
and labels as in `v6_chain.py`, from the patches.

    python benchmarks/memory_real/v6_chain_real.py [--arms encode__starlette-long-1r1/N,...]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import v6_chain as vc  # noqa: E402
from replay_v5 import shown_in  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402

OUT = vc.OUT.with_name("chain-v6-real.json")
GIT_ENV = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
DUMP: list[dict[str, Any]] = []  # with --dump: every record given, for diagnosis (local only)


def git(cwd: Path | str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          env=GIT_ENV, check=check)  # fmt: skip


def rewrite(entries: list[dict[str, Any]], work: str, clone: str) -> list[dict[str, Any]]:
    text = json.dumps(entries)
    for a, b in ((work.replace("\\", "/"), clone), (work.replace("\\", "\\\\"),
                                                    clone.replace("/", "\\\\"))):  # fmt: skip
        text = text.replace(a, b)
    return json.loads(text)


def state(b: Path, base: str, patch: Path | None) -> bool:
    git(b, "checkout", "-q", "-f", base)
    git(b, "clean", "-fdq")
    if patch is None or not patch.exists() or not patch.read_text(encoding="utf-8").strip():
        return True
    done = git(b, "apply", "--whitespace=nowarn", str(patch), check=False)
    return done.returncode == 0


def move(a: Path, b: Path, files: set[str]) -> None:
    """A takes B's version of these files, in place, as the agent's edits did."""
    for rel in files:
        source, target = b / rel, a / rel
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        elif target.exists():
            target.unlink()


def record_chain(arm: Path, chain: dict[str, Any], root: Path, tree: bool) -> dict[int, Any]:
    """Phase 1 through the hook: the records the store holds after each request's Stop."""
    work = chain["cwd"]
    base = git(work, "rev-parse", "HEAD").stdout.strip()
    a, b = root / "A", root / "B"
    for clone in (a, b):
        subprocess.run(["git", "clone", "-q", "--local", work, str(clone)],
                       check=True, env=GIT_ENV, capture_output=True)  # fmt: skip
        git(clone, "checkout", "-q", "-f", base)
    a_path = str(a).replace("\\", "/")
    os.environ["SANCHOPANZA_MEMORY_STORE"] = str(root / "store")
    os.environ["SANCHOPANZA_MEMORY_TREE"] = "on" if tree else "off"
    transcript = root / "projects" / "rec" / "rec.jsonl"
    transcript.parent.mkdir(parents=True)
    so_far: list[dict[str, Any]] = []
    previous: set[str] = set()
    event = {"session_id": "rec", "transcript_path": str(transcript), "cwd": a_path}
    failed = 0
    for r in chain["requests"]:
        entries = rewrite(r["entries"], work, a_path)
        entries[0] = {**entries[0], "cwd": a_path}
        transcript.write_text("".join(json.dumps(e) + "\n" for e in so_far), encoding="utf-8")
        mh.handle({**event, "hook_event_name": "UserPromptSubmit", "prompt": "next"})
        patch = arm / f"diff-{r['i']}.patch"
        if not state(b, base, patch):
            failed += 1
        touched = set(vc.patch_files(patch)) | previous
        move(a, b, touched)
        previous = set(vc.patch_files(patch))
        so_far = [*so_far, *entries]
        transcript.write_text("".join(json.dumps(e) + "\n" for e in so_far), encoding="utf-8")
        mh.handle({**event, "hook_event_name": "Stop"})
    store = mh.store_for({"transcript_path": str(transcript)})
    records = {e.index: e for e in ep.load(store, limit=0) if e.session == "rec"}
    return {"records": records, "a": a_path, "failed_patches": failed}


def score(arms: list[tuple[dict[str, Any], dict[str, Any]]], bash: bool) -> dict[str, Any]:
    n: dict[str, int] = defaultdict(int)
    for chain, rec in arms:
        work = chain["cwd"]
        lo, hi = chain.get("score", (1, 10**6))
        for k, target in enumerate(chain["requests"]):
            if not lo <= target["i"] <= hi:
                continue
            pool_reqs = [r for r in chain["requests"][:k] if r["i"] in rec["records"]]
            if not pool_reqs:
                continue
            pool = [rec["records"][r["i"]] for r in pool_reqs]
            labels = {p.key: vc.label(target, r) for p, r in zip(pool, pool_reqs, strict=True)}
            entries = rewrite(target["entries"], work, rec["a"])
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["SANCHOPANZA_MEMORY_STORE"] = str(Path(tmp) / "store")
                transcript = Path(tmp) / "projects" / "p" / "t.jsonl"
                store = mh.store_for({"transcript_path": str(transcript)})
                ep.save(store, pool, keep_days=100_000)
                mh.note_live(store, "new", 0, frozenset(), rec["a"])
                given: list[str] = []
                for t in vc.touches(entries, bash=bash):
                    out = mh.touch({"hook_event_name": "PostToolUse", "session_id": "new",
                                    "transcript_path": str(transcript), "cwd": rec["a"], **t})
                    text = out["hookSpecificOutput"]["additionalContext"] if out else ""
                    n["chars"] += len(text)
                    keys = shown_in(text, pool)
                    given.extend(keys)
                    for key in keys if DUMP else ():
                        record = next(x for x in pool if x.key == key)
                        DUMP.append({"arm": chain["cwd"][-24:], "target": target["i"],
                                     "given": record.index, "label": labels[key],
                                     "tool": t["tool_name"], "input": str(
                                         t["tool_input"].get("command")
                                         or t["tool_input"].get("file_path"))[:300],
                                     "record_changed": list(record.changed),
                                     "target_changed": sorted(target["changed"])})  # fmt: skip
            related = {key for key, v in labels.items() if v != "none"}
            n["requests"] += 1
            n["given"] += len(given)
            n["good"] += sum(labels[g] != "none" for g in given)
            if related:
                n["with_related"] += 1
                n["hits"] += bool(related & set(given))
            else:
                n["unrelated"] += 1
                n["noisy"] += bool(given)
            n["pool"] += len(pool)
            n["pool_empty"] += sum(not p.changed for p in pool)

    def ratio(a: str, b: str) -> float | None:
        return round(n[a] / n[b], 3) if n[b] else None

    return {"requests": n["requests"], "with_related": n["with_related"],
            "recall": ratio("hits", "with_related"), "precision": ratio("good", "given"),
            "noise": ratio("noisy", "unrelated"), "given": n["given"],
            "chars_per_request": ratio("chars", "requests"),
            "records_changing_nothing": ratio("pool_empty", "pool")}  # fmt: skip


def _view(name: str) -> Any:
    """The shell view of a v6.1 variant (`variants_v61.VARIANTS`) while scoring."""
    import variants_v61 as v61

    return v61.variant(*v61.VARIANTS[name])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arms", required=True, help="chain/arm[:from-to],... scored range")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--dump", default="", help="a local file for every record given")
    parser.add_argument("--views", default="", help="variants_v61 views to score v6's recording "
                        "with as well (v6.1, comma-separated)")
    args = parser.parse_args(argv)
    views = [v for v in args.views.split(",") if v]
    for name in ("SANCHOPANZA_MEMORY_SELECT", "SANCHOPANZA_PROVIDER", "TYPESAFE_API_KEY"):
        os.environ.pop(name, None)
    rows: dict[str, Any] = {}
    done: dict[str, list[Any]] = {"v5": [], "v6": []}
    failed = 0
    if args.dump:
        DUMP.append({"start": True})
    for spec in args.arms.split(","):
        name, _, span = spec.partition(":")
        lo, hi = (int(x) for x in span.split("-")) if span else (1, 10**6)
        arm = vc.RUNS / name
        chain = vc.chain(arm)
        if chain is None:
            continue
        # recorded up to the last scored request; scored only inside the range
        chain = {**chain, "requests": [r for r in chain["requests"] if r["i"] <= hi],
                 "score": (lo, hi)}  # fmt: skip
        for label, tree in (("v5", False), ("v6", True)):
            with tempfile.TemporaryDirectory() as tmp:
                rec = record_chain(arm, chain, Path(tmp), tree)
                failed += rec["failed_patches"]
                done[label].append((chain, rec))
                # phase 2 needs the clone's files only through the records: score now
                rows.setdefault(label, []).append(score([(chain, rec)], bash=tree))
                for view in views if tree else ():
                    with _view(view):
                        rows.setdefault(view, []).append(score([(chain, rec)], bash=True))
        print(spec, {k: v[-1] for k, v in rows.items()}, flush=True)
    total = {"v5": score(done["v5"], bash=False), "v6": score(done["v6"], bash=True)}
    for view in views:
        with _view(view):
            total[view] = score(done["v6"], bash=True)
    print("failed patches", failed)
    if args.dump:
        rows_out = "\n".join(json.dumps(r) for r in DUMP[1:])
        Path(args.dump).write_text(rows_out, encoding="utf-8")
    for name, m in total.items():
        print(name, json.dumps(m))
    out = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    out[args.tag] = {"arms": args.arms, "total": total, "failed_patches": failed}
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
