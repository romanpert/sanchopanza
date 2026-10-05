"""Browse, development: fetch by passages against WebFetch's Haiku reader, replayed for free.

python benchmarks/browse/free_fetch_offline.py --collect   # transcripts; each URL downloaded once
python benchmarks/browse/free_fetch_offline.py             # the report (no network)

Two questions on the recorded sessions of both FRAMES pilots and the free calibration
(`2026-10-03-browse-free`), 220 sessions, no model and no money:

1. What the readers inside WebSearch and WebFetch cost. Neither shows in a transcript: per
   session it is `modelUsage` less the transcript's own calls priced at list rates
   (`free_trace`), split between the two tools by least squares on their call counts (no
   intercept; sessions with no web call have no gap). Only WebFetch calls that returned 200 count.
2. For every WebFetch that returned 200, what `sanchopanza.webpage` would have given the agent
   for the same `prompt`, against the reader's summary in the transcript: its size, whether the
   task's gold answer is in it (when it is on the page at all), and how many of the summary's
   numbers and names that are on the page it keeps. Each URL is downloaded once, today, and
   cached outside the repository; a page that changed since the session is a source of noise.

Nothing from a task, a page or a summary is written here: the report holds counts, sizes and
dollars. The URL list, pages and summaries stay in the private cache.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import pathlib
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza import webpage  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


trace = _load("browse_free_trace", HERE / "free_trace.py")
frames = _load("browse_free_frames", HERE / "free_frames.py")
CACHE = frames.free.CACHE
PAGES = CACHE / "fetch-pages"
RECORDS = CACHE / "fetch-records.json"  # URLs, prompts and summaries: private
REPORT = frames.RESULTS / "fetch-offline.json"
SOURCES = {
    "P1": CACHE / "frames-pilot" / "sessions.jsonl",
    "P2": CACHE / "frames-pilot2" / "sessions.jsonl",
    "CAL": ROOT / "docs" / "results" / "2026-10-03-browse-free" / "calib-sessions.jsonl",
}
UA = "Mozilla/5.0 (compatible; sanchopanza-offline/0.3; research replay, one fetch per URL)"
CHARS_PER_TOKEN = 4.0
BUDGETS = (4_000, 8_000, 16_000)
# List USD per million tokens a result costs the agent that reads it: a 1-hour cache write
# (Claude Code writes 1 h; measured on pilot 2) and a cache read on every later call.
CONTEXT_PRICE = {"SONNET": (4.0, 0.2), "HAIKU": (2.0, 0.1)}
SEARCH_FEE_USD = 0.01


# --- collection ---------------------------------------------------------------------------------


def _fetches(folder: pathlib.Path) -> list[dict[str, Any]]:
    """Every WebFetch call of a session with its reply and the later calls of its agent file."""
    out = []
    for path in sorted(folder.rglob("*.jsonl")) if folder.is_dir() else []:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        entries = [json.loads(x) for x in lines if x.strip()]
        order: dict[str, int] = {}
        uses: list[tuple[str, str, Mapping[str, Any]]] = []
        replies: dict[str, tuple[Mapping[str, Any], str]] = {}
        for entry in entries:
            message = entry.get("message") or {}
            content = message.get("content")
            blocks = content if isinstance(content, list) else []
            if entry.get("type") == "assistant" and message.get("id"):
                order.setdefault(message["id"], len(order))
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use" and block.get("name") == "WebFetch":
                    uses.append((str(block.get("id")), message["id"], block.get("input") or {}))
                elif block.get("type") == "tool_result":
                    extra = entry.get("toolUseResult")
                    text = trace._result_text(block.get("content"))
                    replies[str(block.get("tool_use_id"))] = (
                        extra if isinstance(extra, dict) else {},
                        text,
                    )
        for use_id, message_id, given in uses:
            extra, text = replies.get(use_id, ({}, ""))
            out.append(
                {
                    "url": str(given.get("url") or ""),
                    "prompt": str(given.get("prompt") or ""),
                    "code": extra.get("code"),
                    "summary": str(extra.get("result") or text or ""),
                    "later_calls": len(order) - 1 - order[message_id],
                }
            )
    return out


def reader_usd(row: Mapping[str, Any], calls: Sequence[Mapping[str, Any]]) -> float:
    seen: dict[str, float] = {}
    for call in calls:
        family = trace.family(call["model"])
        seen[family] = seen.get(family, 0.0) + trace.call_usd(call["model"], call["usage"])
    reported: dict[str, float] = {}
    for model, usd in (row.get("usd_by_model") or {}).items():
        reported[trace.family(model)] = reported.get(trace.family(model), 0.0) + float(usd)
    return sum(max(0.0, usd - seen.get(f, 0.0)) for f, usd in reported.items())


def key_of(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def download(url: str) -> dict[str, Any]:
    meta = PAGES / f"{key_of(url)}.json"
    if meta.exists():
        return json.loads(meta.read_text(encoding="utf-8"))
    PAGES.mkdir(parents=True, exist_ok=True)
    info: dict[str, Any] = {"status": None, "type": "", "error": ""}
    try:
        request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
        with urllib.request.urlopen(request, timeout=25) as reply:  # noqa: S310 - recorded URLs
            (PAGES / f"{key_of(url)}.body").write_bytes(reply.read(8_000_000))
            info = {**info, "status": reply.status, "type": reply.headers.get("Content-Type", "")}
    except urllib.error.HTTPError as error:
        info = {**info, "status": error.code}
    except Exception as error:  # noqa: BLE001 - a replay skips what it cannot reach
        info = {**info, "error": error.__class__.__name__}
    meta.write_text(json.dumps(info), encoding="utf-8")
    time.sleep(0.5)
    return info


def collect() -> None:
    sessions, fetches = [], []
    for src, path in SOURCES.items():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            folder = trace.folder_of(row["workdir"])
            calls = trace.load_calls(folder)
            counts = trace.tool_counts(calls)
            sid = f"{src}:{row['task']}:{row['arm']}:{row['run']}"
            found = _fetches(folder)
            sessions.append({"sid": sid, "src": src, "task": row["task"], "arm": row["arm"],
                             "list_usd": row["list_usd"], "searches": counts.get("WebSearch", 0),
                             "fetches_ok": sum(f["code"] == 200 for f in found),
                             "reader_usd": reader_usd(row, calls)})  # fmt: skip
            fetches.extend({"sid": sid, "src": src, "task": row["task"], "arm": row["arm"], **f}
                           for f in found)  # fmt: skip
    for url in sorted({f["url"] for f in fetches if f["code"] == 200 and f["url"]}):
        download(url)
    RECORDS.write_text(json.dumps({"sessions": sessions, "fetches": fetches}), encoding="utf-8")


# --- the report ---------------------------------------------------------------------------------


def split_costs(rows: Sequence[Mapping[str, Any]]) -> tuple[float, float]:
    """USD per search and per successful fetch: reader = a * searches + b * fetches."""
    sss = sum(r["searches"] ** 2 for r in rows)
    sff = sum(r["fetches_ok"] ** 2 for r in rows)
    ssf = sum(r["searches"] * r["fetches_ok"] for r in rows)
    sy = sum(r["searches"] * r["reader_usd"] for r in rows)
    fy = sum(r["fetches_ok"] * r["reader_usd"] for r in rows)
    det = sss * sff - ssf**2
    if not det:
        return (sy / sss if sss else 0.0), 0.0
    return (sy * sff - fy * ssf) / det, (sss * fy - ssf * sy) / det


def gold_map() -> dict[str, str]:
    import csv

    out = {frames.tid_of(r): r["Answer"] for r in frames.read_frames()}
    rows = list(csv.DictReader((CACHE / "browsecomp.csv").open(encoding="utf-8")))
    out.update({f"BC{i}": frames.free._xor(r["answer"], r["canary"]) for i, r in enumerate(rows)})
    for line in (CACHE / "ab_dev.jsonl").open(encoding="utf-8"):
        record = json.loads(line)
        out[f"AB{record['id'][:8]}"] = str(record["answer"])
    return out


def present(gold: str, text: str) -> bool:
    """The grader's rule for an ANSWER line, applied to a whole text."""
    got = f" {frames.normal(text)} "
    wanted = [g for g in frames.golds(gold) if g]
    if not wanted:
        return frames._symbols(text, gold)
    for g in wanted:
        if g.replace(".", "", 1).lstrip("-").isdigit():
            if any(float(x) == float(g) for x in frames._NUMBER.findall(got)):
                return True
        elif f" {g} " in got:
            return True
    return False


_COMMON = frozenset(
    [
        "The",
        "This",
        "That",
        "These",
        "Those",
        "There",
        "Here",
        "What",
        "When",
        "Where",
        "Which",
        "Who",
        "Based",
        "According",
        "Key",
        "Summary",
        "Note",
        "However",
        "Also",
        "From",
        "With",
        "Without",
        "Information",
        "Details",
        "Page",
        "Article",
        "Section",
    ]
)


def facts(text: str) -> set[str]:
    """Numbers and capitalised names in a reader's summary: what it told the agent."""
    import re

    found = re.findall(r"\b(?:\d[\d,.]*\d|\d)\b|\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)*", text)
    cleaned = {m.strip().rstrip(".,").replace(",", "") for m in found}
    return {m for m in cleaned if m and m not in _COMMON and not (m.isdigit() and len(m) < 2)}


def page_for(url: str) -> webpage.Page | None:
    meta_path = PAGES / f"{key_of(url)}.json"
    body = PAGES / f"{key_of(url)}.body"
    if not meta_path.exists() or not body.exists():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    ctype = str(meta.get("type") or "").lower()
    if meta.get("status") != 200 or not any(t in ctype for t in ("html", "text/plain", "xml")):
        return None
    return webpage.page_from_html(webpage.decode(body.read_bytes(), ctype))


def replay(fetches: Sequence[Mapping[str, Any]], golds: Mapping[str, str]) -> list[dict]:
    pages: dict[str, webpage.Page | None] = {}
    rows = []
    for f in fetches:
        if f["code"] != 200 or not f["url"]:
            continue
        if f["url"] not in pages:
            pages[f["url"]] = page_for(f["url"])
        page = pages[f["url"]]
        if page is None:
            continue
        full = "\n".join(c.text for c in page.chunks)
        gold = golds.get(f["task"], "")
        on_page = {x for x in facts(f["summary"]) if x in full}
        row = {"src": f["src"], "arm": f["arm"], "task": f["task"],
               "page_tok": len(full) / CHARS_PER_TOKEN,
               "summary_tok": len(f["summary"]) / CHARS_PER_TOKEN,
               "later_calls": f["later_calls"], "gold_on_page": present(gold, full),
               "gold_in_summary": present(gold, f["summary"]), "facts": len(on_page)}  # fmt: skip
        for budget in BUDGETS:
            out = webpage.passages(page, f["prompt"], budget)
            text = f"{out.title}\n{out.text}"
            row[f"tok_{budget}"] = len(text) / CHARS_PER_TOKEN
            row[f"gold_{budget}"] = present(gold, text)
            row[f"facts_{budget}"] = sum(1 for x in on_page if x in text)
        rows.append(row)
    return rows


def _q(values: Sequence[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[int(p * (len(ordered) - 1))] if ordered else 0.0


def summarise(rows: Sequence[Mapping[str, Any]], per_fetch_usd: float) -> dict[str, Any]:
    with_gold = [r for r in rows if r["gold_on_page"]]
    n_facts = sum(r["facts"] for r in rows)
    out: dict[str, Any] = {
        "fetches": len(rows),
        "page_tokens_median": round(_q([r["page_tok"] for r in rows], 0.5)),
        "page_tokens_p90": round(_q([r["page_tok"] for r in rows], 0.9)),
        "summary_tokens_mean": round(statistics.mean(r["summary_tok"] for r in rows)),
        "later_calls_mean": round(statistics.mean(r["later_calls"] for r in rows), 2),
        "gold_on_page": len(with_gold),
        "gold_in_summary": sum(r["gold_in_summary"] for r in with_gold),
        "summary_facts_on_page": n_facts,
    }
    for budget in BUDGETS:
        net = []
        for r in rows:
            write, read = CONTEXT_PRICE["HAIKU" if r["arm"].startswith("HAIKU") else "SONNET"]
            extra = r[f"tok_{budget}"] - r["summary_tok"]
            net.append(per_fetch_usd - extra * (write + read * r["later_calls"]) / 1e6)
        out[f"budget_{budget}"] = {
            "tokens_mean": round(statistics.mean(r[f"tok_{budget}"] for r in rows)),
            "tokens_p90": round(_q([r[f"tok_{budget}"] for r in rows], 0.9)),
            "gold": sum(r[f"gold_{budget}"] for r in with_gold),
            "gold_where_summary_had_it_lost": sum(
                r["gold_in_summary"] and not r[f"gold_{budget}"] for r in with_gold
            ),
            "summary_facts_kept": sum(r[f"facts_{budget}"] for r in rows),
            "net_usd_per_fetch_mean": round(statistics.mean(net), 4),
            "fetches_net_negative": sum(x < 0 for x in net),
        }
    whole = [r["page_tok"] - r["summary_tok"] for r in rows]
    out["whole_page_net_usd_per_fetch_mean"] = round(
        statistics.mean(per_fetch_usd - w * (4.0 + 0.2 * r["later_calls"]) / 1e6
                        for w, r in zip(whole, rows, strict=True)), 4)  # fmt: skip
    return out


def cost_table(
    sessions: Sequence[Mapping[str, Any]], fits: Mapping[str, tuple[float, float]]
) -> dict[str, Any]:
    """Per source and arm, the readers split with that source's own fit."""
    table = {}
    groups = collections.defaultdict(list)
    for s in sessions:
        groups[f"{'FRAMES' if s['src'] != 'CAL' else 'CAL'} {s['arm']}"].append(s)
    for name, rows in sorted(groups.items()):
        a, b = fits["cal" if name.startswith("CAL") else "frames"]
        searches = sum(r["searches"] for r in rows)
        fetches = sum(r["fetches_ok"] for r in rows)
        table[name] = {
            "sessions": len(rows),
            "list_usd": round(sum(r["list_usd"] for r in rows), 3),
            "reader_usd": round(sum(r["reader_usd"] for r in rows), 3),
            "searches": searches,
            "fetches_ok": fetches,
            "search_usd": round(a * searches, 3),
            "search_fee_usd": round(SEARCH_FEE_USD * searches, 3),
            "fetch_usd": round(b * fetches, 3),
        }
    return table


def report() -> dict[str, Any]:
    data = json.loads(RECORDS.read_text(encoding="utf-8"))
    sessions = data["sessions"]
    framed = [s for s in sessions if s["src"] != "CAL"]
    fits = {name: split_costs(rows) for name, rows in (
        ("all", sessions), ("frames", framed), ("cal", [s for s in sessions if s["src"] == "CAL"]),
        ("search_only", [s for s in sessions if not s["fetches_ok"] and s["searches"]]),
    )}  # fmt: skip
    b = fits["frames"][1]
    rows = replay(data["fetches"], gold_map())
    return {
        "fit_usd_per_call": {
            k: {"search": round(x, 4), "fetch": round(y, 4)} for k, (x, y) in fits.items()
        },  # fmt: skip
        "costs": cost_table(sessions, fits),
        "replay_frames": summarise([r for r in rows if r["src"] != "CAL"], b),
        "replay_cal": summarise([r for r in rows if r["src"] == "CAL"], fits["cal"][1]),
        "skipped_fetches": sum(f["code"] == 200 for f in data["fetches"]) - len(rows),
        "chars_per_token": CHARS_PER_TOKEN,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect", action="store_true")
    args = parser.parse_args()
    if args.collect:
        collect()
    out = report()
    REPORT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    sys.stdout.write(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
