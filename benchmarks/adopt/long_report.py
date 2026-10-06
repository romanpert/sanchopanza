"""Reading long-chain runs (`long_run.py`): the grade, the headroom gate, the contrasts and what
was lost. Free; only the grade runs pytest in Docker.

- **Grade.** long60 chains go through `perbug.grade_run` (per-bug FAIL_TO_PASS primary, the
  guard's regressions apart, B2's strict rule secondary, the control token, the callbacks), with
  the chain as the arm was asked it: its own token and the bugs it was given. A long40 chain
  (no guard) is graded the same way from its PASS_TO_PASS* with `run.bug_result`.
- **Gate** (prereg section 5): peak context >= 250k, >= 150 requests, >= 50 % of the cost above
  200k, 0 or 1 compaction, an effective window >= 400k with its source, per-bug F2P in 30-90 %.
  A criterion that cannot be read from the run is None, never a pass.
- **Statistics** (section 4, decision 1): Holm over the primary contrasts, McNemar exact on
  discordant bugs, a bootstrap over chains for the difference in resolved bugs, non-inferiority
  at -5 points (`MARGIN`), and the paired log cost ratio with a t interval.
- **Loss**: re-reads within 20 requests of a compaction, and check-done send-backs (requests
  after a Stop hook sent Claude back) with their cost (pre-mortem 17).
"""

from __future__ import annotations

import json
import math
import random
import re
import statistics
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parent))  # appended: benchmarks/ holds names like agentdojo
sys.path.insert(0, str(HERE.parents[1] / "src"))

import docker_env  # noqa: E402
import meter  # noqa: E402
import run  # noqa: E402

from sanchopanza.eval.stats import mcnemar  # noqa: E402

MARGIN = 0.05  # decision 1: -5 points on resolved bugs, this suite only
SEED, RESAMPLES = 20261005, 10_000
GATE = {"peak": 250_000, "requests": 150, "share_over_200k": 0.50, "compactions": 1,
        "window": 400_000, "f2p_rate": (0.30, 0.90)}  # fmt: skip
COMPACT_MARGIN = 33_000  # window = threshold + 33k (install_defaults.COMPACT_MARGIN)
REREAD_WINDOW = 20
_READS = re.compile(r"(?:^|[;&|]\s*|\s)(?:cat|head|tail|less|sed\s+-n\s+\S+)\s+([^\s|;&<>]+)")


# ---- grade ---------------------------------------------------------------------------------------


def stored_counts(grade: Mapping[str, Any]) -> dict[str, int]:
    """Strict and per-bug F2P counts from a grade's per-bug fields, as stored (B2 has no
    `resolved_f2p`: it is read from `f2p_passed`, `f2p` and `patch_applied`)."""
    bugs = grade["bugs"]
    f2p = sum(1 for b in bugs if b["f2p_passed"] == b["f2p"] and b.get("patch_applied", True))
    return {"strict": sum(1 for b in bugs if b["resolved"]), "f2p": f2p, "bugs": len(bugs)}


def snapshots(evidence: Path, count: int) -> list[str]:
    return [(evidence / f"diff-{r}.patch").read_text(encoding="utf-8")
            if (evidence / f"diff-{r}.patch").exists() else "" for r in range(1, count + 1)]


def grade_arm(chain: Mapping[str, Any], evidence: Path) -> dict[str, Any]:
    import long_run
    import perbug

    row = json.loads((evidence / "row.json").read_text(encoding="utf-8"))
    asked = long_run.with_control(chain, row["token"], row["bugs"])
    if "guard" in chain:
        return perbug.grade_run(asked, evidence, run.PROMPT)
    patch = (evidence / "final.patch").read_text(encoding="utf-8")
    nodes = [n for b in asked["bugs"] for n in (*b["FAIL_TO_PASS"], *b["PASS_TO_PASS_STAR"])]
    outcome = docker_env.pytest(chain["tag"], patch, list(dict.fromkeys(nodes)),
                                keep_collecting=chain["split"] != "held")  # fmt: skip
    bugs = [run.bug_result(b, outcome) for b in asked["bugs"]]
    count = len(run.requests_of(asked))
    result = {"chain": chain["chain"], "resolved": sum(b["resolved_f2p"] for b in bugs),
              "strict_resolved": sum(b["resolved"] for b in bugs), "bugs_total": len(bugs),
              "regressions": sorted({t for b in asked["bugs"] for t in b["PASS_TO_PASS_STAR"]
                                     if outcome.get(t) != "PASSED"}),
              "token": perbug.token_status(patch, len(bugs), asked["token"]),
              "callbacks": perbug.score_callbacks(asked, snapshots(evidence, count), run.PROMPT),
              "bugs": bugs}  # fmt: skip
    (evidence / "grade.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def grade_all(layout: Any, names: list[str], known: Mapping[str, Any], models: list[str],
              arms: tuple[str, ...]) -> int:  # fmt: skip
    """Grade every arm that ran; print resolved bugs and, apart, the give-ups; write
    `<root>/report.json` with each arm's line and, for arm N, its gate row (the gate's table)."""
    import run as runner

    report: dict[str, Any] = {}
    for model in models:
        for name in names:
            for arm in arms:
                evidence = layout.runs / f"{name}-{model}" / arm
                if not (evidence / "final.patch").exists():
                    continue
                g = grade_arm(known[name], evidence)
                line = gate_row(evidence, g)
                quits = line["give_ups"]
                print(name, model, arm, g["resolved"], "of", g["bugs_total"], "resolved;",
                      quits["give_ups"], "gave up,", quits[f"at_or_past_{GIVE_UP_AT // 1000}k"],
                      f"at or past {GIVE_UP_AT // 1000}k", flush=True)  # fmt: skip
                report[f"{name}/{runner.MODELS.get(model, model)}/{arm}"] = line
    gate = {m: gate_verdict([r for k, r in report.items() if k.split("/")[1:] ==
                             [runner.MODELS.get(m, m), "N"]]) for m in models}  # fmt: skip
    print("gate:", gate, flush=True)
    (layout.root / "report.json").write_text(json.dumps({"arms": report, "gate": gate}, indent=1),
                                             encoding="utf-8")  # fmt: skip
    return 0


# ---- the gate ------------------------------------------------------------------------------------


def requests_of(evidence: Path) -> tuple[meter.Request, ...]:
    found: dict[str, meter.Request] = {}
    for path in sorted(evidence.glob("transcript*.jsonl")):
        found.update({r.id: r for r in meter.transcript_requests(path)})
    return tuple(found.values())


def window_evidence(row: Mapping[str, Any], peak: int) -> dict[str, Any]:
    """The effective window and where it comes from: the settings env; the session's own debug
    line (`long_window`: effectiveWindow + the 20k output reserve, with the source the server
    cache names); else a compaction's `pre` tokens plus the margin, or a lower bound when the
    session reached `peak` uncompacted (rows from before the debug line)."""
    window = row.get("window") or {}
    configured = window.get("configured", window.get("value"))
    pres = [c.get("pre") for c in compactions(row) if c.get("pre")]
    if configured:
        return {"value": int(configured), "source": "settings env", "bound": "exact"}
    if window.get("effective_reported"):
        return {"value": int(window["value"]), "effective": int(window["effective_reported"]),
                "source": f"session debug line; {window.get('source')}", "bound": "exact",
                "server_cache": window.get("server_cache", {})}  # fmt: skip
    if pres:
        return {"value": min(pres) + COMPACT_MARGIN, "source": "first compaction", "bound": "about"}
    return {"value": peak + COMPACT_MARGIN, "source": "no compaction up to the peak",
            "bound": "at least"}  # fmt: skip


def compactions(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [c for call in row["calls"] for c in call.get("compactions") or []]


def gate_row(evidence: Path, grade: Mapping[str, Any] | None) -> dict[str, Any]:
    row = json.loads((evidence / "row.json").read_text(encoding="utf-8"))
    found = requests_of(evidence)
    cost = sum(r.cost(meter.OWNER_RATES) for r in found)
    over = sum(r.cost(meter.OWNER_RATES) for r in found if r.context > 200_000)
    peak = max((r.context for r in found), default=0)
    window = window_evidence(row, peak)
    rate = grade["resolved"] / grade["bugs_total"] if grade else None
    low, high = GATE["f2p_rate"]
    # "at least" below 400k says nothing yet: pending, not failed
    reached = window["value"] >= GATE["window"]
    window_ok = reached if reached or window["bound"] != "at least" else None
    checks = {"peak": peak >= GATE["peak"], "requests": len(found) >= GATE["requests"],
              "share_over_200k": (over / cost >= GATE["share_over_200k"]) if cost else None,
              "compactions": len(compactions(row)) <= GATE["compactions"],
              "window": window_ok if found else None,
              "f2p_rate": (low <= rate <= high) if rate is not None else None}  # fmt: skip
    verdict = None if None in checks.values() else all(checks.values())
    quits = {k: v for k, v in give_ups(evidence, row).items() if k != "items"}
    return {"run": row.get("run"), "arm": row.get("arm"), "peak": peak, "requests": len(found),
            "owner_usd": round(cost, 4), "share_over_200k": round(over / cost, 3) if cost else None,
            "compactions": len(compactions(row)), "window": window, "f2p_rate": rate,
            "give_ups": quits, "checks": checks, "pass": verdict}  # fmt: skip


def gate_verdict(rows: Sequence[Mapping[str, Any]]) -> str:
    """A model passes when every gate chain passes; a pending criterion keeps it pending."""
    if any(r["pass"] is None for r in rows):
        return "pending"
    return "passes" if rows and all(r["pass"] for r in rows) else "sin margen"


# ---- statistics ----------------------------------------------------------------------------------


def holm(pvalues: Mapping[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Holm's step-down: which hypotheses are rejected at family-wise `alpha`."""
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    out, going = {}, True
    for i, (name, p) in enumerate(ordered):
        going = going and p <= alpha / (len(ordered) - i)
        out[name] = going
    return out


def bugs_mcnemar(treated: Sequence[bool], control: Sequence[bool]) -> dict[str, Any]:
    only_t, only_c, p = mcnemar(treated, control)
    return {"treated_only": only_t, "control_only": only_c, "p": p}


Pairs = Sequence[Sequence[tuple[bool, bool]]]  # per chain, (treated, control) per bug


def _difference(sample: Pairs) -> float:
    pairs = [p for chain in sample for p in chain]
    return sum(t - c for t, c in pairs) / len(pairs) if pairs else 0.0


def _draws(chains: Pairs, reps: int, seed: int) -> list[float]:
    """The difference over `reps` resamples of whole chains, sorted."""
    rng = random.Random(seed)
    return sorted(_difference([rng.choice(chains) for _ in chains]) for _ in range(reps))


def cluster_bootstrap(chains: Pairs, reps: int = RESAMPLES,
                      seed: int = SEED) -> tuple[float, float, float]:  # fmt: skip
    """Difference in resolved rate (treated - control) over bugs paired within chains, with a
    95 % interval from resampling whole chains."""
    draws = _draws(chains, reps, seed)
    return _difference(chains), draws[int(0.025 * reps)], draws[int(0.975 * reps) - 1]


def one_sided_low(chains: Pairs, reps: int = RESAMPLES, seed: int = SEED) -> float:
    """The one-sided 95 % lower bound of the difference (the 5th percentile of the draws)."""
    return _draws(chains, reps, seed)[int(0.05 * reps)]


def noninferior(chains: Pairs, margin: float = MARGIN) -> bool:
    return one_sided_low(chains) > -margin


T95 = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447, 8: 2.365, 9: 2.306,
       10: 2.262, 11: 2.228, 12: 2.201, 16: 2.131, 20: 2.093, 24: 2.069}  # fmt: skip


def cost_ratio(pairs: Sequence[tuple[float, float]]) -> dict[str, float]:
    """Paired mean of ln(treated / control) per chain: the ratio and its 95 % t interval."""
    logs = [math.log(t / c) for t, c in pairs if t > 0 and c > 0]
    if len(logs) < 2:
        return {"ratio": math.exp(logs[0]) if logs else float("nan"), "n": len(logs)}
    mean, sd = statistics.mean(logs), statistics.stdev(logs)
    half = T95.get(len(logs), 1.96) * sd / math.sqrt(len(logs))
    return {"ratio": math.exp(mean), "low": math.exp(mean - half), "high": math.exp(mean + half),
            "n": len(logs), "sd": sd}  # fmt: skip


# ---- loss ----------------------------------------------------------------------------------------


def _entries(path: Path) -> list[dict[str, Any]]:
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


def _reads(block: Mapping[str, Any]) -> list[str]:
    """Paths a tool call reads: Read's file_path, or cat/head/tail/sed -n in a shell command."""
    data = block.get("input") or {}
    if block.get("name") == "Read":
        return [str(data.get("file_path") or "")]
    if block.get("name") in ("Bash", "PowerShell"):
        return _READS.findall(str(data.get("command") or ""))
    return []


def rereads(transcript: Path, window: int = REREAD_WINDOW) -> dict[str, Any]:
    """Reads, within `window` requests after each compaction, of a path read before it."""
    read_before: set[str] = set()
    since: int | None = None
    requests, found = 0, []
    for entry in _entries(transcript):
        if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary":
            since = requests
        if entry.get("type") != "assistant":
            continue
        requests += 1
        for block in (entry.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            for path in _reads(block):
                near = since is not None and requests - since <= window
                if near and path in read_before:
                    found.append({"path": path, "after": requests - since})
                read_before.add(path)
    return {"rereads": len(found), "items": found}


def _sent_back(entry: Mapping[str, Any]) -> bool:
    message = entry.get("message") or {}
    content = message.get("content") if isinstance(message, dict) else None
    texts = [content] if isinstance(content, str) else [
        b.get("text", "") for b in content or [] if isinstance(b, dict)]  # fmt: skip
    attachment = entry.get("attachment") or {}
    return any("Stop hook feedback" in t for t in texts) or "stop" in str(
        attachment.get("type") or "").lower() and "block" in str(attachment).lower()


def send_backs(transcript: Path) -> dict[str, Any]:
    """Pre-mortem 17: requests made after a Stop hook sent Claude back, until the next prompt,
    tagged and priced (owner USD)."""
    tagged, blocks, after = [], 0, False
    for entry in _entries(transcript):
        if entry.get("type") == "user" and _sent_back(entry):
            blocks, after = blocks + 1, True
        elif entry.get("type") == "user" and _prompt(entry):
            after = False
        elif after and entry.get("type") == "assistant":
            one = meter.request_of(entry.get("message") or {})
            tagged += [one] if one else []
    unique = {r.id: r for r in tagged}
    return {"blocks": blocks, "requests": len(unique),
            "owner_usd": round(sum(r.cost(meter.OWNER_RATES) for r in unique.values()), 6)}


def _prompt(entry: Mapping[str, Any]) -> bool:
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    return not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content or [])


# ---- give-ups ------------------------------------------------------------------------------------

GIVE_UP_AT = 150_000  # BrowseComp-Plus (2026-10-06): N's give-ups came past ~150k (median 184k)
_SAID = re.compile(
    r"\b(?:could not|couldn't|cannot|can't|unable to|not able to|did not manage to)\b[^.]{0,80}"
    r"\b(?:fix|reproduce|find|resolve|determine|locate|identify)\b|\bgiv(?:e|ing) up\b",
    re.IGNORECASE)  # fmt: skip


def code_part(patch: str) -> str:
    """The patch without its `changes/` files (the control rule's notes are not a fix)."""
    blocks = re.split(r"(?m)^(?=diff --git )", patch)
    return "".join(b for b in blocks if not re.match(r"diff --git a/changes/", b))


def give_ups(evidence: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    """Bug requests the agent gave up on, counted apart from wrong fixes: the call ran and changed
    no code outside `changes/`, or its final answer says it could not fix or find the bug. With
    the context the call reached, and how many came at or past `GIVE_UP_AT`."""
    items = []
    for call in row.get("calls", []):
        if call.get("kind") != "bug" or call.get("status") != "ran" or call.get("superseded"):
            continue
        k = int(call["request"])
        before, after = (evidence / f"diff-{k - 1}.patch"), (evidence / f"diff-{k}.patch")
        old = code_part(before.read_text(encoding="utf-8")) if before.exists() else ""
        new = code_part(after.read_text(encoding="utf-8")) if after.exists() else old
        unchanged, said = old == new, bool(_SAID.search(str(call.get("result_tail") or "")))
        if unchanged or said:
            items.append({"request": k, "instance_id": call.get("instance_id"),
                          "context": int(call.get("peak_context") or 0),
                          "no_code_change": unchanged, "said_so": said})  # fmt: skip
    contexts = [i["context"] for i in items]
    return {"give_ups": len(items), "no_code_change": sum(i["no_code_change"] for i in items),
            "said_so": sum(i["said_so"] for i in items),
            f"at_or_past_{GIVE_UP_AT // 1000}k": sum(c >= GIVE_UP_AT for c in contexts),
            "median_context": statistics.median(contexts) if contexts else None,
            "items": items}  # fmt: skip
