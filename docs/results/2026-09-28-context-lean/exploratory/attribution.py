"""Exploratory, offline attribution of the context-e2e tokens (no model, no network, no key).

Reads only the saved evidence of `docs/results/2026-09-28-context-e2e` under
`~/.cache/sanchopanza/context-e2e/`: arm A (autopilot) in `runs-r2/<task>/A/`, arm N (native
`/compact`) in `runs/<task>/N/` with its phase A result in `runs/<task>/A/result.json`.
Writes `attribution.json` next to this file. Paths in the output are relative to that cache root.

    python docs/results/2026-09-28-context-lean/exploratory/attribution.py
"""

# ruff: noqa: E501, B905  (a measurement script, kept as it ran)

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True  # leave the sibling folder untouched
sys.path.insert(0, str(HERE.parents[1] / "2026-09-28-context-e2e"))
import costs  # noqa: E402
import transcripts as tr  # noqa: E402

ROOT = costs.ROOT
TASKS = [f"t{n:02d}-{name}" for n, name in enumerate(
    ["orders", "shipments", "invoices", "sensors", "tickets", "bookings", "payroll", "loans", "fleet", "warehouse", "subscriptions", "meters"], start=1)]  # fmt: skip
# Haiku 4.5 list price, USD per million tokens: input, cache write, cache read, output. Claude
# Code wrote every cache entry with the 1-hour TTL (usage.cache_creation.ephemeral_1h), billed
# at 2x input; with it, the per-call sums reproduce `modelUsage.costUSD` (checked in `usd_check`).
PRICE = {"in": 1.0, "cc": 2.0, "cr": 0.10, "out": 5.0}
INJECTION = "hook_additional_context"


def arm_paths(task: str, arm: str) -> dict[str, Path]:
    if arm == "A":
        folder = ROOT / "runs-r2" / task / "A"
        return {"session": folder / "session.jsonl", "a": folder / "a.json",
                "compact": folder / "compact.json", "b": folder / "b.json"}  # fmt: skip
    folder = ROOT / "runs" / task / "N"
    return {"session": folder / "session.jsonl", "a": ROOT / "runs" / task / "A" / "result.json",
            "compact": folder / "compact.json", "b": folder / "b.json"}  # fmt: skip


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def block_text(block: dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return ""


def markers(items: list[dict[str, Any]]) -> tuple[int, int]:
    boundary = next(i for i, e in enumerate(items)
                    if e.get("type") == "system" and e.get("subtype") == "compact_boundary")  # fmt: skip
    return boundary, tr.b_start(items)


def api_calls(items: list[dict[str, Any]], boundary: int, b_index: int) -> list[dict[str, Any]]:
    """One row per API call: the first transcript entry of each message id that carries usage."""
    seen: set[str] = set()
    out = []
    for i, e in enumerate(items):
        message = e.get("message") or {}
        usage = message.get("usage")
        if e.get("type") != "assistant" or not usage or message.get("id") in seen:
            continue
        seen.add(message.get("id"))
        phase = "A" if i < boundary else ("B" if i > b_index else "between")
        out.append({"index": i, "phase": phase, "in": int(usage.get("input_tokens") or 0),
                    "cc": int(usage.get("cache_creation_input_tokens") or 0),
                    "cr": int(usage.get("cache_read_input_tokens") or 0),
                    "out": int(usage.get("output_tokens") or 0)})  # fmt: skip
    return out


def usd(row: dict[str, Any]) -> float:
    return sum(row.get(k, 0) * PRICE[k] for k in PRICE) / 1e6


def totals(calls: list[dict[str, Any]]) -> dict[str, Any]:
    t = {k: sum(c[k] for c in calls) for k in ("in", "cc", "cr", "out")}
    t["input_total"] = t["in"] + t["cc"] + t["cr"]
    t["cache_read_share"] = round(t["cr"] / t["input_total"], 4) if t["input_total"] else None
    t["calls"] = len(calls)
    t["usd"] = round(usd(t), 6)
    return t


def injections(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i, e in enumerate(items):
        att = e.get("attachment") or {}
        if att.get("type") == INJECTION:
            text = "\n".join(str(x) for x in att.get("content") or [])
            out.append(
                {"index": i, "event": att.get("hookEvent"), "chars": len(text), "text": text}
            )
    return out


def added_between(items: list[dict[str, Any]], lo: int, hi: int) -> dict[str, int]:
    """Characters that entered the transcript between two API calls, by kind."""
    inj = res = 0
    for e in items[lo + 1 : hi]:
        att = e.get("attachment") or {}
        if att.get("type") == INJECTION:
            inj += sum(len(str(x)) for x in att.get("content") or [])
        for b in tr._blocks(e):
            if b.get("type") == "tool_result":
                res += len(block_text(b))
    return {"inj": inj, "res": res}


def regression_rows(items: list[dict[str, Any]], calls: list[dict[str, Any]]) -> list[list[float]]:
    rows = []
    for prev, cur in zip(calls, calls[1:]):
        if prev["phase"] != cur["phase"]:
            continue
        added = added_between(items, prev["index"], cur["index"])
        ctx = lambda c: c["in"] + c["cc"] + c["cr"]  # noqa: E731
        rows.append([1.0, prev["out"], added["inj"], added["res"], ctx(cur) - ctx(prev)])
    return rows


def least_squares(rows: list[list[float]]) -> list[float]:
    """Normal equations solved by Gauss-Jordan: no numpy needed."""
    k = len(rows[0]) - 1
    a = [[sum(r[i] * r[j] for r in rows) for j in range(k)] + [sum(r[i] * r[k] for r in rows)]
         for i in range(k)]  # fmt: skip
    for col in range(k):
        pivot = max(range(col, k), key=lambda r: abs(a[r][col]))
        a[col], a[pivot] = a[pivot], a[col]
        a[col] = [v / a[col][col] for v in a[col]]
        a = [row if r == col else [v - row[col] * p for v, p in zip(row, a[col])]
             for r, row in enumerate(a)]  # fmt: skip
    return [row[k] for row in a]


def injection_costs(calls, injs, tokens_per_char) -> list[dict[str, Any]]:
    """Each injection's tokens, the calls it rides in, and the input tokens it cost."""
    out = []
    for inj in injs:
        tokens = inj["chars"] * tokens_per_char
        later = [c for c in calls if c["index"] > inj["index"]]
        phase = "B" if any(c["phase"] == "B" for c in later) else "A"
        later = [c for c in later if c["phase"] == phase]
        out.append({"index": inj["index"], "phase": phase, "event": inj["event"],
                    "chars": inj["chars"],
                    "tokens": round(tokens), "calls_in_context": len(later),
                    "cc": round(tokens) if later else 0,
                    "cr": round(tokens) * max(len(later) - 1, 0)})  # fmt: skip
    return out


def counterfactual(total: dict[str, Any], costs_: list[dict[str, Any]], keep) -> dict[str, Any]:
    removed = [c for c in costs_ if not keep(c)]
    cc = total["cc"] - sum(c["cc"] for c in removed)
    cr = total["cr"] - sum(c["cr"] for c in removed)
    row = {"in": total["in"], "cc": cc, "cr": cr, "out": total["out"]}
    return {"input_total": total["in"] + cc + cr, "usd": round(usd(row), 6)}


FACT_KEYS = ("token", "code", "tolerance", "window")


def fact_values(fact: dict[str, Any], key: str) -> list[str]:
    if key == "tolerance":
        return sorted({fact["tolerance"], fact["tolerance"].rstrip("0")}, key=len, reverse=True)
    return [fact[key]]


def _stem(fact: dict[str, Any]) -> str:
    return fact["window_home"].removesuffix(".py")


def window_used(text: str, fact: dict[str, Any]) -> bool:
    """The edit names the constant through its home module: `from pkg.x import ...` or `x.C`."""
    stem = _stem(fact)
    return bool(re.search(rf"\b{stem} import [A-Za-z_, ]*GRACE_WINDOW_DAYS|\b{stem}\.GRACE_WINDOW_DAYS",
                          text))  # fmt: skip


def window_known(text: str, fact: dict[str, Any]) -> bool:
    """The text ties GRACE_WINDOW_DAYS to its home module (a Read of it, a grep line, a note)."""
    stem = _stem(fact)
    return "GRACE_WINDOW_DAYS" in text and bool(
        re.search(rf"\b{stem}\.py\b|pkg[./\\]+{stem}\b|\b{stem}\.GRACE|\b{stem} import", text)
    )


def has(text: str, fact: dict[str, Any], key: str) -> bool:
    if key == "window":
        return window_known(text, fact)
    return any(v in text for v in fact_values(fact, key))


def used(text: str, fact: dict[str, Any], key: str) -> bool:
    return window_used(text, fact) if key == "window" else has(text, fact, key)


def entry_texts(e: dict[str, Any], inputs: dict[str, str]) -> list[tuple[str, str]]:
    """(kind, text) of every piece of an entry the model sees; a result carries its call."""
    out = []
    att = e.get("attachment") or {}
    if att.get("type") == INJECTION:
        out.append(("recall", "\n".join(str(x) for x in att.get("content") or [])))
    message = e.get("message") or {}
    if isinstance(message.get("content"), str):
        out.append(("user_text", message["content"]))
    for b in tr._blocks(e):
        if b.get("type") == "tool_result":
            text = block_text(b)
            kind = "stub" if tr.STUB_PREFIX in text else "tool_result"
            out.append((kind, inputs.get(str(b.get("tool_use_id")), "") + "\n" + text))
        elif b.get("type") == "text":
            out.append(("assistant_text" if e.get("type") == "assistant" else "user_text",
                        b.get("text", "")))  # fmt: skip
        elif b.get("type") == "tool_use":
            out.append(("tool_input", json.dumps(b.get("input"), ensure_ascii=False)))
    return out


def resumed_chain(items: list[dict[str, Any]], b_index: int) -> dict[str, Any]:
    """The history `--resume` rebuilds for phase B: the parentUuid chain from B's prompt.

    Claude Code cuts that chain at the compact boundary's `logicalParentUuid` and puts the
    boundary's own children (summary or masked copies) in front. If that entry is not on the
    chain, there is nothing to cut at and the chain is the history, back to the first prompt.
    Native N: the cut entry is on the chain. Arm A: see `cut_found` per task.
    """
    pos = {e["uuid"]: i for i, e in enumerate(items) if e.get("uuid")}
    boundary = next(e for e in items if e.get("subtype") == "compact_boundary")
    chain, uuid = [], items[b_index].get("parentUuid")
    while uuid in pos and pos[uuid] not in chain:
        chain.append(pos[uuid])
        uuid = items[pos[uuid]].get("parentUuid")
    cut = pos.get(boundary.get("logicalParentUuid"))
    b0 = pos[boundary["uuid"]]
    return {"indices": sorted(chain), "cut_found": cut in chain,
            "pre_boundary_entries": sum(i < b0 for i in chain),
            "pre_boundary_tool_results": sum(i < b0 and any(
                b.get("type") == "tool_result" for b in tr._blocks(items[i])) for i in chain),
            "stubs_on_chain": sum(tr.STUB_PREFIX in json.dumps(items[i].get("message"))
                                  for i in chain),
            "stubs_after_boundary": sum(tr.STUB_PREFIX in json.dumps(e.get("message"))
                                        for e in items[b0:b_index])}  # fmt: skip


def mask_check(s: dict[str, Any], tokens_per_char: float) -> dict[str, Any]:
    """First phase-B context against two predictions: the masked history, or the original.

    Both start from the last phase-A call (context + its output) and add what entered before
    phase B's first call (prompt, recall); `masked` also takes away the characters the stubs
    replaced. Thinking of phase A (reported by `a.json`) is stripped on resume
    (`thinking_stripped`), so `unmasked` should overshoot by about that much.
    """
    items, calls = s["items"], s["calls"]
    phase_a = [c for c in calls if c["phase"] == "A"]
    first_b = next(c for c in calls if c["phase"] == "B")
    originals = {b.get("tool_use_id"): len(block_text(b)) for e in items[: s["boundary"]]
                 for b in tr._blocks(e) if b.get("type") == "tool_result"}  # fmt: skip
    removed = sum(originals.get(b.get("tool_use_id"), 0) - len(block_text(b))
                  for e in items[s["boundary"] : s["b_index"]] for b in tr._blocks(e)
                  if b.get("type") == "tool_result" and tr.STUB_PREFIX in block_text(b))  # fmt: skip
    added_chars = len(json.dumps((items[s["b_index"]].get("message") or {}).get("content"))) + sum(
        i["chars"] for i in injections(items) if s["b_index"] < i["index"] < first_b["index"]
    )
    base = phase_a[-1]["in"] + phase_a[-1]["cc"] + phase_a[-1]["cr"] + phase_a[-1]["out"]
    unmasked = base + added_chars * tokens_per_char
    observed = first_b["in"] + first_b["cc"] + first_b["cr"]
    return {"observed": observed, "predicted_unmasked": round(unmasked),
            "predicted_masked": round(unmasked - removed * tokens_per_char),
            "stubbed_chars": removed, "phase_a_thinking_tokens": s["thinking_a"]}  # fmt: skip


def provenance(items, kept_indices, b_index, fact) -> dict[str, Any]:
    """Where the value phase B used came from: kept context, recall, or a phase-B tool result.

    `kept_in` lists the kinds of pre-phase-B context in `kept_indices` that already hold the
    value; `recall_before_use` and `results_before_use` are the transcript indices of
    injections and phase-B tool results holding it before first use.
    """
    inputs = {str(u.get("id")): json.dumps(u.get("input"), ensure_ascii=False)
              for u in tr.tool_uses(items)}  # fmt: skip
    out = {}
    for key in FACT_KEYS:
        kept = sorted({kind for e in (items[i] for i in kept_indices)
                       for kind, text in entry_texts(e, inputs)
                       if kind not in ("user_text", "tool_input") and has(text, fact, key)})  # fmt: skip
        first_use, recall_before, results_before = None, [], []
        for i in range(b_index + 1, len(items)):
            for kind, text in entry_texts(items[i], inputs):
                if (
                    first_use is None
                    and kind in ("assistant_text", "tool_input")
                    and used(text, fact, key)
                ):
                    first_use = {"index": i, "kind": kind}
                if first_use is None and has(text, fact, key):
                    if kind == "recall":
                        recall_before.append(i)
                    elif kind == "tool_result":
                        results_before.append(i)
        if first_use is None:
            source = "not used"
        elif kept:
            source = "kept context"
        elif recall_before and not results_before:
            source = "recall only"
        elif results_before:
            source = "phase-B tool result" + (" (recall also had it)" if recall_before else "")
        else:
            source = "unexplained"
        out[key] = {"source": source, "kept_in": kept, "first_use": first_use,
                    "recall_before_use": recall_before, "results_before_use": results_before}  # fmt: skip
    return out


def re_reads(items, boundary, b_index) -> dict[str, int]:
    a_reads = {tr.rel(u["input"].get("file_path", "")) for u in tr.tool_uses(items[:boundary])
               if u["name"] == "Read"}  # fmt: skip
    b_uses = tr.tool_uses(items[b_index:])
    reads = [tr.rel(u["input"].get("file_path", "")) for u in b_uses if u["name"] == "Read"]
    return {"reads": len(reads), "re_reads": sum(r in a_reads for r in reads),
            "archive_reads": sum(".sanchopanza" in r for r in reads),
            "bash": sum(u["name"] == "Bash" for u in b_uses),
            "grep_glob": sum(u["name"] in ("Grep", "Glob") for u in b_uses)}  # fmt: skip


def largest_results(items) -> list[int]:
    sizes = [len(block_text(b)) for e in items for b in tr._blocks(e)
             if b.get("type") == "tool_result"]  # fmt: skip
    return sorted(sizes, reverse=True)[:3]


def session(task: str, arm: str, fact: dict[str, Any]) -> dict[str, Any]:
    paths = arm_paths(task, arm)
    items = tr.entries(paths["session"])
    boundary, b_index = markers(items)
    calls = api_calls(items, boundary, b_index)
    a, compact, b = (costs._load(paths[k]) for k in ("a", "compact", "b"))
    split = costs.split(a, compact, b)
    phase_a = [c for c in calls if c["phase"] == "A"]
    phase_b = [c for c in calls if c["phase"] == "B"]
    ctx = lambda c: c["in"] + c["cc"] + c["cr"]  # noqa: E731
    return {
        "task": task, "arm": arm, "session": relative(paths["session"]),
        "items": items, "boundary": boundary, "b_index": b_index, "calls": calls,
        "phase_a": totals(phase_a), "phase_b": totals(phase_b),
        "between_calls": len([c for c in calls if c["phase"] == "between"]),
        "compaction_input": split["compact_input"] or 0,
        "compaction_usd": split["compact_usd"] or 0.0,
        "result_json": {"a_input": split["a_input"], "b_input": split["b_input"],
                        "total_input": split["total_input"], "total_usd": split["total_usd"]},
        "last_a_context": ctx(phase_a[-1]), "first_b_context": ctx(phase_b[0]),
        "first_b_call": {k: phase_b[0][k] for k in ("in", "cc", "cr")},
        "compact_metadata": tr.compaction(paths["session"]).get("metadata"),
        "thinking_a": sum(int(v.get("thinkingTokens") or 0)
                          for v in (a.get("modelUsage") or {}).values()),
        "phase_b_tools": re_reads(items, boundary, b_index),
        "largest_tool_results": largest_results(items),
    }  # fmt: skip


def main() -> None:
    facts = {f["task"]: f for f in json.loads((ROOT / "tasks" / "facts.json").read_text("utf-8"))}
    runs = {(t, arm): session(t, arm, facts[t]) for t in TASKS for arm in ("A", "N")}
    rows = [r for s in runs.values() for r in regression_rows(s["items"], s["calls"])]
    coef = least_squares(rows)
    tokens_per_char = coef[2]
    report: dict[str, Any] = {
        "note": "Exploratory; paths relative to ~/.cache/sanchopanza/context-e2e",
        "price_usd_per_mtok": PRICE,
        "calibration": {"samples": len(rows), "intercept": round(coef[0], 1),
                        "per_prev_output_token": round(coef[1], 3),
                        "tokens_per_injection_char": round(coef[2], 4),
                        "tokens_per_tool_result_char": round(coef[3], 4)},
        "tasks": [],
    }  # fmt: skip
    for t in TASKS:
        row: dict[str, Any] = {"task": t}
        for arm in ("A", "N"):
            s = runs[(t, arm)]
            whole = totals(s["calls"])
            row[arm] = {k: s[k] for k in ("session", "phase_a", "phase_b", "compaction_input",
                        "compaction_usd", "result_json", "last_a_context", "first_b_context",
                        "first_b_call", "compact_metadata", "phase_b_tools",
                        "largest_tool_results", "between_calls")}  # fmt: skip
            row[arm]["input_total"] = whole["input_total"] + s["compaction_input"]
            row[arm]["usd"] = round(whole["usd"] + s["compaction_usd"], 6)
        s = runs[(t, "A")]
        injs = injections(s["items"])
        inj_costs = injection_costs(s["calls"], injs, tokens_per_char)
        whole = totals(s["calls"])
        row["A"]["injections"] = inj_costs
        row["A"]["counterfactual"] = {
            "no_recall": counterfactual(whole, inj_costs, lambda c: False),
            "prompt_recall_only": counterfactual(whole, inj_costs,
                                                 lambda c: c["event"] == "UserPromptSubmit"),
            "as_run": counterfactual(whole, inj_costs, lambda c: True),
        }  # fmt: skip
        saved_view = list(range(s["boundary"] + 1, s["b_index"]))
        for arm in ("A", "N"):
            chain = resumed_chain(runs[(t, arm)]["items"], runs[(t, arm)]["b_index"])
            row[arm]["resumed_chain"] = {k: v for k, v in chain.items() if k != "indices"}
            if arm == "A":
                chain_view = [i for i in chain["indices"] if i < s["b_index"]]
        row["A"]["mask_check"] = mask_check(s, tokens_per_char)
        row["A"]["provenance"] = {
            "saved_file_view": provenance(s["items"], saved_view, s["b_index"], facts[t]),
            "resumed_chain_view": provenance(s["items"], chain_view, s["b_index"], facts[t]),
        }  # fmt: skip
        report["tasks"].append(row)
    report["pooled"] = pooled(report["tasks"])
    (HERE / "attribution.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    show(report)


def pooled(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def total(arm: str, path: list[str]) -> float:
        acc = 0.0
        for r in rows:
            v: Any = r[arm]
            for p in path:
                v = v[p]
            acc += v
        return round(acc, 6)

    out: dict[str, Any] = {}
    for arm in ("A", "N"):
        out[arm] = {
            "input_total": total(arm, ["input_total"]), "usd": total(arm, ["usd"]),
            "result_json_input": total(arm, ["result_json", "total_input"]),
            "result_json_usd": total(arm, ["result_json", "total_usd"]),
            "compaction_input": total(arm, ["compaction_input"]),
            "first_b_context_mean": round(total(arm, ["first_b_context"]) / len(rows)),
            "last_a_context_mean": round(total(arm, ["last_a_context"]) / len(rows)),
            "re_reads": total(arm, ["phase_b_tools", "re_reads"]),
        }  # fmt: skip
        for phase in ("phase_a", "phase_b"):
            out[arm][phase] = {
                k: total(arm, [phase, k])
                for k in ("in", "cc", "cr", "out", "input_total", "calls", "usd")
            }
            out[arm][phase]["cache_read_share"] = round(
                out[arm][phase]["cr"] / out[arm][phase]["input_total"], 4
            )
    injs = [i for r in rows for i in r["A"]["injections"]]
    out["injections"] = {
        "count": len(injs), "prompt": sum(i["event"] == "UserPromptSubmit" for i in injs),
        "tool": sum(i["event"] == "PostToolUse" for i in injs),
        "in_phase_a": sum(i["phase"] == "A" for i in injs),
        "chars": sum(i["chars"] for i in injs), "tokens": sum(i["tokens"] for i in injs),
        "input_cost_cc": sum(i["cc"] for i in injs), "input_cost_cr": sum(i["cr"] for i in injs),
    }  # fmt: skip
    for name in ("no_recall", "prompt_recall_only", "as_run"):
        out.setdefault("counterfactual", {})[name] = {
            "input_total": sum(r["A"]["counterfactual"][name]["input_total"] for r in rows),
            "usd": round(sum(r["A"]["counterfactual"][name]["usd"] for r in rows), 4),
        }  # fmt: skip
    sources: dict[str, dict[str, dict[str, int]]] = {}
    for r in rows:
        for view, facts in r["A"]["provenance"].items():
            for key, p in facts.items():
                bucket = sources.setdefault(view, {}).setdefault(key, {})
                bucket[p["source"]] = bucket.get(p["source"], 0) + 1
    out["provenance"] = sources
    checks = [r["A"]["mask_check"] for r in rows]
    out["mask_check"] = {
        "observed_mean": round(sum(c["observed"] for c in checks) / len(checks)),
        "predicted_unmasked_mean": round(sum(c["predicted_unmasked"] for c in checks) / len(checks)),
        "predicted_masked_mean": round(sum(c["predicted_masked"] for c in checks) / len(checks)),
        "phase_a_thinking_mean": round(sum(c["phase_a_thinking_tokens"] for c in checks) / len(checks)),
        "cut_found": {a: sum(r[a]["resumed_chain"]["cut_found"] for r in rows) for a in ("A", "N")},
        "stubs_on_resumed_chain_A": sum(r["A"]["resumed_chain"]["stubs_on_chain"] for r in rows),
        "original_tool_results_on_resumed_chain_A": sum(
            r["A"]["resumed_chain"]["pre_boundary_tool_results"] for r in rows),
    }  # fmt: skip
    out["largest_tool_result"] = max(max(r[a]["largest_tool_results"] or [0]) for r in rows
                                     for a in ("A", "N"))  # fmt: skip
    return out


def show(report: dict[str, Any]) -> None:
    print("calibration", report["calibration"])
    for r in report["tasks"]:
        a, n = r["A"], r["N"]
        prov = " ".join(f"{k}={v['source']}" for k, v in a["provenance"]["saved_file_view"].items())
        m = a["mask_check"]
        prov += (
            f" | first-B {m['observed']:,} masked {m['predicted_masked']:,} "
            f"unmasked {m['predicted_unmasked']:,} cut {a['resumed_chain']['cut_found']}"
        )
        print(
            f"{r['task']:18} A {a['input_total']:>9,} N {n['input_total']:>9,} | "
            f"B calls {a['phase_b']['calls']:>2}/{n['phase_b']['calls']:>2} "
            f"first-B ctx {a['first_b_context']:>6,}/{n['first_b_context']:>6,} | {prov}"
        )
    print(json.dumps(report["pooled"], indent=1))


if __name__ == "__main__":
    main()
