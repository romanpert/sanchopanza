"""long60 chains (`long.py`, `grader: per_bug`): validation that drops interacting bugs, and the
per-bug grade with its guard, control token and callbacks. Docker, free.

Validation (`isolate`), with every bug of the chain baked into its image:
- each bug's FAIL_TO_PASS all fail with every bug in;
- undoing that bug alone (its gold patch) makes all of its FAIL_TO_PASS pass, and makes no other
  bug's FAIL_TO_PASS pass;
- undoing every bug together makes every bug's FAIL_TO_PASS pass and breaks no PASS_TO_PASS test
  that passed with every bug in.
A bug that fails a check is dropped: for the first two, its culprits as `masking.culprits` names
them (itself when it is broken on its own); for the others, the bug whose tests are not its own
(the one whose tests another fix flips) or whose fix breaks a passing test. Dropped slots take
the chain's next spares that fit (no failing test in common, no overlapping hunk), in drawn order,
and the chain is baked and checked again, at most ROUNDS times. Valid: a round with no drop and
`size` bugs.

Guard: the PASS_TO_PASS tests (of any bug) that pass both with every bug in and with every bug
undone. The grade (`grade`): a bug is resolved when its own FAIL_TO_PASS all pass in the final
tree; regressions are guard tests that fail there, reported apart (B2's strict rule, which
needed every bug's PASS_TO_PASS* too, is kept as `strict_resolved`, secondary).
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import docker_env
import long
import masking
import related

ROUNDS = 6
CHANGES = "changes/"
_LINE = re.compile(r"^\s*[-*]?\s*bug\s*#?\s*(\d+)\s*[:\-]\s*(.*)$", re.I)


def joined(bugs: list[dict[str, Any]]) -> str:
    return "".join(p if p.endswith("\n") else p + "\n" for p in (b["patch"] for b in bugs))


def _run(tag: str, patch: str, nodes: list[str], reverse: bool = False) -> dict[str, str]:
    """pytest outcomes; a run that reports nothing reads as nothing passing, not an error."""
    try:
        return docker_env.pytest(tag, patch, nodes, reverse=reverse, keep_collecting=True)
    except RuntimeError:
        return {}


# ---- validation ----------------------------------------------------------------------------------


def check(tag: str, bugs: list[dict[str, Any]]) -> dict[str, Any]:
    """One round on the baked image: per-bug records, the bugs to drop and why, and the guard."""
    f2p = list(dict.fromkeys(t for b in bugs for t in b["FAIL_TO_PASS"]))
    in_f2p = set(f2p)
    p2p = [t for t in dict.fromkeys(t for b in bugs for t in b["PASS_TO_PASS"]) if t not in in_f2p]
    start = docker_env.pytest(tag, "", [*f2p, *p2p], keep_collecting=True)
    clean = docker_env.pytest(tag, joined(bugs), [*f2p, *p2p], reverse=True, keep_collecting=True)
    if "<patch>" in clean:
        raise RuntimeError(f"{tag}: undoing every bug together does not apply")
    alone = [_run(tag, b["patch"], f2p, reverse=True) for b in bugs]
    records, why = [], {}
    for i, bug in enumerate(bugs):
        own = bug["FAIL_TO_PASS"]
        flips = [
            j
            for j, other in enumerate(bugs)
            if j != i and any(alone[i].get(t) == "PASSED" for t in other["FAIL_TO_PASS"])
        ]
        record = {
            "instance_id": bug["instance_id"],
            "source": bug["source"],
            "f2p": len(own),
            "f2p_failing_with_bugs": sum(start.get(t) != "PASSED" for t in own),
            "f2p_passing_when_fixed": sum(alone[i].get(t) == "PASSED" for t in own),
            "f2p_passing_all_fixed": sum(clean.get(t) == "PASSED" for t in own),
            "flips": [bugs[j]["instance_id"] for j in flips],
        }
        records.append(record)
        for j in flips:
            why.setdefault(j, f"its tests pass when {masking.short(bug)} alone is fixed")
    masked = [
        i
        for i, r in enumerate(records)
        if r["f2p_failing_with_bugs"] < r["f2p"] or r["f2p_passing_when_fixed"] < r["f2p"]
    ]
    for k in masking.culprits(tag, bugs, masked, records, keep=True) if masked else []:
        why.setdefault(k, "culprit: " + ", ".join(masking.short(bugs[i]) for i in masked[:5]))
    for i, r in enumerate(records):
        if r["f2p_passing_all_fixed"] < r["f2p"] and i not in masked:
            why.setdefault(i, "its tests fail with every bug undone")
    broken = [t for t in p2p if start.get(t) == "PASSED" and clean.get(t) != "PASSED"]
    if broken:  # a test that passes with every bug in and fails with all undone: whose fix?
        for i, bug in enumerate(bugs):
            if any(
                _run(tag, bug["patch"], broken, reverse=True).get(t) != "PASSED" for t in broken
            ):
                why.setdefault(i, "undoing it breaks a test that passed")
    guard = [t for t in p2p if start.get(t) == "PASSED" and clean.get(t) == "PASSED"]
    for i, record in enumerate(records):
        record["valid"] = i not in why
        record["why"] = why.get(i, "")
    return {
        "records": records,
        "drop": why,
        "guard": guard,
        "p2p": len(p2p),
        "p2p_failing_all_fixed": sum(clean.get(t) != "PASSED" for t in p2p),
        "p2p_failing_with_bugs": sum(start.get(t) != "PASSED" for t in p2p),
        "p2p_broken_by_fixes": len(broken),
    }


def refill(
    bugs: list[dict[str, Any]], drop: set[int], spares: list[dict[str, Any]], tried: set[str]
) -> list[dict[str, Any]]:
    """`bugs` with each dropped slot taken by the next spare that fits the rest (or removed)."""
    out = [b for k, b in enumerate(bugs) if k not in drop]
    placed: dict[int, dict[str, Any]] = {}
    for k in sorted(drop):
        for spare in spares:
            if spare["instance_id"] in tried:
                continue
            if long.fits(spare, [*out, *placed.values()]):
                tried.add(spare["instance_id"])
                placed[k] = spare
                break
    return [
        placed[k] if k in drop else b for k, b in enumerate(bugs) if k not in drop or k in placed
    ]


def token_in_image(tag: str, token: str) -> bool:
    done = docker_env.docker(
        "run", "--rm", tag, "git", "-C", "/testbed", "grep", "-I", "-F", "-l", "-e", token
    )
    if done.returncode not in (0, 1):
        raise RuntimeError(f"git grep in {tag} failed: {done.stderr.decode('utf-8', 'replace')}")
    return done.returncode == 0


def isolate(chain: dict[str, Any]) -> dict[str, Any]:
    import validate  # validate imports this module

    started = time.time()
    docker_env.pull(chain["image"])
    tag = validate.tag_of(chain["chain"])
    size = chain.get("size", len(chain["bugs"]))
    bugs, spares = list(chain["bugs"]), list(chain["spares"])
    tried = {b["instance_id"] for b in bugs}
    history: list[Any] = []
    dropped: list[dict[str, Any]] = []
    result: dict[str, Any] = {}
    for attempt in range(ROUNDS):
        docker_env.bake(chain["image"], [b["patch"] for b in bugs], tag)
        result = check(tag, bugs)
        drop = result["drop"]
        history.append(
            {
                "round": attempt + 1,
                "bugs": len(bugs),
                "drop": len(drop),
                "seconds": round(time.time() - started),
            }
        )
        print(
            chain["chain"],
            f"round {attempt + 1}: {len(bugs)} bugs, {len(drop)} dropped",
            flush=True,
        )
        if not drop or attempt + 1 == ROUNDS:
            break
        dropped += [
            {
                "instance_id": bugs[k]["instance_id"],
                "source": bugs[k]["source"],
                "round": attempt + 1,
                "why": w,
            }
            for k, w in sorted(drop.items())
        ]
        bugs = refill(bugs, set(drop), spares, tried)
    valid = not result["drop"] and len(bugs) == size
    token, index, avoid = chain["token"], 0, long.texts_of(bugs)
    while token_in_image(tag, token):
        index += 1
        token = long.token_for(chain["chain"], avoid, index)
    guard = result["guard"]
    in_guard = set(guard)
    kept = [
        {
            **{k: v for k, v in b.items() if k not in ("PASS_TO_PASS", "patch_original")},
            "PASS_TO_PASS_STAR": [t for t in b["PASS_TO_PASS"] if t in in_guard],
        }
        for b in bugs
    ]
    return {
        **{k: v for k, v in chain.items() if k not in ("bugs", "spares", "token")},
        "tag": tag,
        "valid": valid,
        "token": token,
        "token_absent_in_image": True,
        "bugs": kept,
        "guard": guard,
        "records": result["records"],
        "dropped": dropped,
        "history": history,
        "p2p": {
            k: result[k]
            for k in (
                "p2p",
                "p2p_failing_all_fixed",
                "p2p_failing_with_bugs",
                "p2p_broken_by_fixes",
            )
        },
        "seconds": round(time.time() - started),
    }


# ---- control fact and callbacks ------------------------------------------------------------------


def sections(patch: str) -> dict[str, str]:
    """path -> its section of a git diff (text), for each file the diff touches."""
    out: dict[str, str] = {}
    for part in related._sections(patch):
        m = re.match(r"^diff --git a/(\S+) b/(\S+)", part[0])
        if m:
            out[m.group(2)] = "\n".join(part)
    return out


def new_file_lines(patch: str, path: str) -> list[str] | None:
    """The lines of `path` as the diff creates it, or None when the diff does not add it."""
    text = sections(patch).get(path)
    if text is None or "\n--- /dev/null" not in text:
        return None
    body = text.split("\n@@", 1)[1].split("\n", 1)[1] if "\n@@" in text else ""
    return [ln[1:] for ln in body.split("\n") if ln.startswith("+") and not ln.startswith("+++")]


def token_status(patch: str, size: int, token: str) -> dict[str, Any]:
    """Per bug n: `ok` (changes/<n>.md starts `Ref: <token>`), `wrong` or `missing`."""
    status = {}
    for n in range(1, size + 1):
        lines = new_file_lines(patch, f"{CHANGES}{n}.md")
        first = (lines or [""])[0].strip().rstrip("\r") if lines is not None else None
        status[n] = "missing" if first is None else "ok" if first == f"Ref: {token}" else "wrong"
    counts = {k: sum(1 for v in status.values() if v == k) for k in ("ok", "wrong", "missing")}
    return {"per_bug": status, **counts}


def changed_during(before: str, after: str) -> set[str]:
    """Repository files whose diff differs between two cumulative snapshots (changes/ aside)."""
    a, b = sections(before), sections(after)
    return {p for p in a.keys() | b.keys() if not p.startswith(CHANGES) and a.get(p) != b.get(p)}


def _paths(text: str) -> set[str]:
    if text.strip().lower().rstrip(".") in ("none", "nothing", "-", ""):
        return set()
    parts = re.split(r"[,\s]+", text)
    cleaned = (p.strip("`'\"()[]*;").removeprefix("./").rstrip(".:") for p in parts)
    return {p for p in cleaned if p.lower() != "none" and ("/" in p or "." in p)}


def recall_answer(text: str) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for line in text.splitlines():
        if m := _LINE.match(line):
            out[int(m.group(1))] = _paths(m.group(2))
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def score_callbacks(chain: dict[str, Any], snapshots: list[str], template: str) -> list[dict]:
    """Each callback against the harness's own diff snapshots (`snapshots[r-1]` = the cumulative
    diff after request r), scored by Jaccard per asked bug. Unanswered bugs score 0."""
    asks = long.requests(chain, template)
    index = {a["bug"]: r for r, a in enumerate(asks, start=1) if a["kind"] == "bug"}

    def snap(r: int) -> str:
        return snapshots[r - 1] if 0 < r <= len(snapshots) else ""

    out = []
    for r, ask in enumerate(asks, start=1):
        if ask["kind"] != "callback":
            continue
        lines = new_file_lines(snap(r), f"{CHANGES}recall-{ask['callback']}.md")
        answer = recall_answer("\n".join(lines or []))
        per = {}
        for n in ask["asked"]:
            truth = changed_during(snap(index[n] - 1), snap(index[n]))
            got = answer.get(n)
            per[n] = {
                "truth": sorted(truth),
                "answer": sorted(got) if got is not None else None,
                "jaccard": 0.0 if got is None else round(jaccard(got, truth), 3),
            }
        out.append(
            {
                "callback": ask["callback"],
                "request": r,
                "written": lines is not None,
                "per_bug": per,
                "mean": round(sum(p["jaccard"] for p in per.values()) / len(per), 3),
            }
        )
    return out


# ---- the grade -----------------------------------------------------------------------------------


def grade(chain: dict[str, Any], patch: str) -> dict[str, Any]:
    """Per-bug F2P on the final tree, guard regressions apart, the control token from the patch."""
    f2p = list(dict.fromkeys(t for b in chain["bugs"] for t in b["FAIL_TO_PASS"]))
    keep = chain["split"] != "held"
    outcome = docker_env.pytest(chain["tag"], patch, [*f2p, *chain["guard"]], keep_collecting=keep)
    applied = "<patch>" not in outcome
    broken = {t for t in chain["guard"] if outcome.get(t) != "PASSED"} if applied else set()
    bugs = []
    for n, bug in enumerate(chain["bugs"], start=1):
        passed = sum(outcome.get(t) == "PASSED" for t in bug["FAIL_TO_PASS"])
        resolved = applied and passed == len(bug["FAIL_TO_PASS"])
        own = sum(t in broken for t in bug["PASS_TO_PASS_STAR"])
        bugs.append(
            {
                "n": n,
                "instance_id": bug["instance_id"],
                "source": bug["source"],
                "origin": bug["origin"],
                "resolved": resolved,
                "f2p_passed": passed,
                "f2p": len(bug["FAIL_TO_PASS"]),
                "strict_resolved": resolved and not own,
                "p2p_broken": own,
            }
        )
    return {
        "chain": chain["chain"],
        "patch_applied": applied,
        "resolved": sum(b["resolved"] for b in bugs),
        "bugs_total": len(bugs),
        "strict_resolved": sum(b["strict_resolved"] for b in bugs),
        "regressions": sorted(broken),
        "guard": len(chain["guard"]),
        "token": token_status(patch, len(chain["bugs"]), chain["token"]),
        "bugs": bugs,
    }


def grade_run(chain: dict[str, Any], evidence: Path, template: str) -> dict[str, Any]:
    """A run's grade, written beside its evidence: the per-bug grade of final.patch plus the
    callbacks against the run's diff snapshots."""
    patch = (evidence / "final.patch").read_text(encoding="utf-8")
    count = len(long.requests(chain, template))
    snapshots = [
        (evidence / f"diff-{r}.patch").read_text(encoding="utf-8")
        if (evidence / f"diff-{r}.patch").exists()
        else ""
        for r in range(1, count + 1)
    ]
    result = {**grade(chain, patch), "callbacks": score_callbacks(chain, snapshots, template)}
    (evidence / "grade.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def gold_patch(tag: str, bugs: list[dict[str, Any]]) -> str:
    """Every bug fixed, as a forward diff against the baked image (what an agent's final.patch
    would be with every bug fixed): the bugs undone in a container and `git diff` taken."""
    with tempfile.TemporaryDirectory() as io_dir:
        (Path(io_dir) / "bugs.patch").write_bytes(joined(bugs).encode("utf-8"))
        script = (
            "cd /testbed && git apply -R --whitespace=nowarn /io/bugs.patch && "
            "git -c core.quotepath=off diff --binary"
        )
        done = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{Path(io_dir).as_posix()}:/io:ro",
                tag,
                "bash",
                "-lc",
                script,
            ],
            capture_output=True,
            timeout=600,
        )
    return docker_env.ok(done, "gold patch").decode("utf-8")


def token_absent(root: Path, token: str) -> list[str]:
    """Files under `root` (a working copy) that contain the token: none expected."""
    needle = token.encode()
    return [
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and ".git" not in p.parts and needle in p.read_bytes()
    ]


# ---- the driver's dry run ------------------------------------------------------------------------


def dry_run(chain: dict[str, Any], template: str, root: Path) -> dict[str, Any]:
    """Everything a long60 run does but the model: the working copy exported from the chain's
    image (the token must not be in it), the prompt sequence (written to `root/prompts.txt`; the
    token only in the first), then a scripted agent that fixes every bug with its gold patch,
    writes each `changes/<n>.md` and answers each callback from the truth, with the runner's diff
    snapshots; graded like a run. Then the gold patch and an empty patch graded directly."""
    import chains

    tag, token = chain["tag"], chain["token"]
    if docker_env.docker("image", "inspect", tag).returncode != 0:
        raise SystemExit(f"{tag} is not built: `validate.py --bake {chain['chain']}` first")
    docker_env.remove_tree(root)
    evidence, work = root / "evidence", root / "work"
    evidence.mkdir(parents=True)
    base = docker_env.export(tag, work)
    leaked = token_absent(work, token)
    asks = long.requests(chain, template)
    (root / "prompts.txt").write_text(
        "".join(
            f"===== request {r} ({a['kind']} {a['instance_id']})\n{a['prompt']}\n\n"
            for r, a in enumerate(asks, start=1)
        ),
        encoding="utf-8",
        newline="\n",
    )
    later = [r for r, a in enumerate(asks, start=1) if r > 1 and token in a["prompt"]]
    bugs = chain["bugs"]
    for r, ask in enumerate(asks, start=1):
        if ask["kind"] == "bug":
            bug = bugs[ask["bug"] - 1]
            patch = evidence / "bug.patch"
            patch.write_text(bug["patch"], encoding="utf-8", newline="\n")
            docker_env.ok(
                subprocess.run(
                    ["git", "-C", str(work), "apply", "-R", "--whitespace=nowarn", str(patch)],
                    capture_output=True,
                ),
                f"undo {bug['instance_id']}",
            )
            note = work / CHANGES / f"{ask['bug']}.md"
            note.parent.mkdir(exist_ok=True)
            note.write_text(f"Ref: {token}\nThe gold patch.\n", encoding="utf-8", newline="\n")
        else:
            lines = [
                f"bug {n}: " + (", ".join(sorted(chains.files_of(bugs[n - 1]["patch"]))) or "none")
                for n in ask["asked"]
            ]
            recall = work / CHANGES / f"recall-{ask['callback']}.md"
            recall.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        (evidence / f"diff-{r}.patch").write_text(
            docker_env.agent_diff(work, base), encoding="utf-8", newline="\n"
        )
    (evidence / "bug.patch").unlink()
    (evidence / "final.patch").write_text(
        docker_env.agent_diff(work, base), encoding="utf-8", newline="\n"
    )
    scripted = grade_run(chain, evidence, template)
    gold, empty = grade(chain, gold_patch(tag, bugs)), grade(chain, "")
    return {
        "chain": chain["chain"],
        "requests": len(asks),
        "bugs": sum(a["kind"] == "bug" for a in asks),
        "callbacks": long.callbacks(len(bugs)),
        "sequence": [
            f"{r:>3} {a['kind']:<8} {a['instance_id']:<48} {len(a['prompt']):>6} ch  "
            + a["prompt"].splitlines()[0][:70]
            for r, a in enumerate(asks, start=1)
        ],
        "token_in_working_copy": leaked,
        "token_in_later_prompts": later,
        "prompt_chars": sum(len(a["prompt"]) for a in asks),
        "scripted": {
            "resolved": scripted["resolved"],
            "regressions": len(scripted["regressions"]),
            "token_ok": scripted["token"]["ok"],
            "callback_means": [c["mean"] for c in scripted["callbacks"]],
        },
        "gold": {
            "resolved": gold["resolved"],
            "regressions": len(gold["regressions"]),
            "strict": gold["strict_resolved"],
        },
        "empty": {
            "resolved": empty["resolved"],
            "regressions": len(empty["regressions"]),
            "token_missing": empty["token"]["missing"],
        },
        "guard": len(chain["guard"]),
        "size": len(bugs),
    }
