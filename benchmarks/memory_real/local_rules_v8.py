"""v8's standing rules and Stop audit, replayed on the maintainer's own Claude Code sessions.

Sessions are those started before amendment 6 part B's window (`local_v6.END`, 2026-10-01
12:00), so part B's sessions stay unread. Per project folder, oldest first, every request is
first audited against the rules the project held at that moment (never its own), then its
sentences are asked whether they are standing rules, as `memory_rules.extract` and `audit` do.

The diff a request made is not in a transcript: it is rebuilt from the request's Edit,
MultiEdit and Write calls (old lines as `-`, new as `+`; a Write as a new file), test files and
secret-like names left out as `_diff` leaves them. That is a proxy, close for edits and wider
than git for a Write over an existing file.

Every decision goes through a Squire that masks secrets in the state (the product's), and the
rules in the Choice's options are masked as `audit` masks them. Answers are recorded in the
cache (`FIXTURE`, private: it holds the person's words) and replayed; the repository gets counts.
The squire's cap stops live spending at MAX_USD.

    python benchmarks/memory_real/local_rules_v8.py            # replay only
    python benchmarks/memory_real/local_rules_v8.py --live     # ask Jev what is not recorded
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))
sys.path.insert(0, str(HERE.parent / "memory_carry"))

import build  # noqa: E402
import local_v6 as lv  # noqa: E402
from rule_check_eval import api_key  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.context.archive import safe_name  # noqa: E402
from sanchopanza.context.worktree import _secret  # noqa: E402
from sanchopanza.harness import memory_rules as mr  # noqa: E402
from sanchopanza.points import rules as points  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402
from sanchopanza.redact import redact_secrets  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402

FIXTURE = build.CACHE / "local-rules-v8.jsonl"
DETAIL = build.CACHE / "local-rules-v8-detail.json"
MAX_USD = 1.00
MAX_DECISIONS = 8_000
CONCURRENCY = 6
CHANGE_BYTES = mr.NEW_FILE_BYTES
EDITS = ("Edit", "MultiEdit", "Write")


class ReplayThenLive:
    """The recording first; the live decider (recording as it goes) only for what is missing."""

    name = "jev"

    def __init__(self, recorded: RecordedDecider, live: Any | None) -> None:
        self._recorded, self._live = recorded, live
        self.live_calls = 0

    async def decide(self, point: str, state: Any, questions: Any) -> Any:
        found = await self._recorded.decide(point, state, questions)
        if found.answers or self._live is None:
            return found
        self.live_calls += 1
        return await self._live.decide(point, state, questions)


def _lines(text: str, sign: str) -> str:
    return "".join(f"{sign}{line}\n" for line in str(text).splitlines())


def change_of(group: tuple[Any, ...], cwd: str) -> tuple[str, list[str]]:
    """(a diff-like text of the request's own edits, the files it wrote, relative)."""
    parts, files, room = [], [], CHANGE_BYTES
    for message in group[1:]:
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name, data = block.get("name"), block.get("input") or {}
            if name not in EDITS or not isinstance(data, dict):
                continue
            rel = ep.relative(str(data.get("file_path") or ""), cwd)
            if not rel or _secret(rel) or mr._tested(rel):
                continue
            if name == "Write":
                body = f"+++ b/{rel} (new file)\n" + _lines(data.get("content") or "", "+")
            else:
                edits = data.get("edits") if name == "MultiEdit" else [data]
                body = f"--- a/{rel}\n+++ b/{rel}\n" + "".join(
                    _lines(e.get("old_string") or "", "-") + _lines(e.get("new_string") or "", "+")
                    for e in edits or [] if isinstance(e, dict))  # fmt: skip
            if len(body) > room:
                continue
            room -= len(body)
            parts.append(body)
            files.append(rel)
    return "".join(parts), list(dict.fromkeys(files))


def requests_of(folder: str, sessions: list[Path]) -> list[dict[str, Any]]:
    out = []
    for path in sessions:
        try:
            entries = ep.entries_of(path)
            split = ep.split_requests(entries)
        except (OSError, ValueError):
            continue
        cwd = build.cwd_of(entries)
        for index, group in enumerate(split.groups, 1):
            text = ep._request(group[0]) if group else ""
            if not text.strip():
                continue
            change, files = change_of(group, cwd)
            out.append({"folder": folder, "session": path.stem, "index": index,
                        "at": split.stamps[index - 1] or lv.stamp(path),
                        "request": text, "change": change, "files": files})  # fmt: skip
    return sorted(out, key=lambda r: r["at"])


async def extract(squire: Squire, reqs: list[dict[str, Any]]) -> None:
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(req: dict[str, Any], sentence: str) -> dict[str, Any]:
        async with gate:
            state, qs = points.questions_for_sentence(sentence, req["request"])
            d = await squire.decide("memory_standing_rule", state, qs)
        a = d.answer("rule")
        return {"sentence": sentence, "p": None if d.failed or a.empty else a.truth}

    for req in reqs:
        req["sentences"] = await asyncio.gather(
            *(one(req, s) for s in points.sentences(req["request"])))


async def audit_one(squire: Squire, req: dict[str, Any], rules: list[dict[str, Any]]
                    ) -> dict[str, Any] | None:  # fmt: skip
    """`memory_rules.audit` on a rebuilt change and an in-memory store."""
    held = [r for r in rules if not (r["session"] == req["session"] and r["index"] == req["index"])
            ][: mr.CHECK_MAX]  # fmt: skip
    if not held or not req["change"].strip():
        return None
    key = f"{safe_name(req['session'])}-{req['index']:03d}"
    order = mr._order(key, len(held))
    state, qs = points.questions_for_rules(
        [(redact_secrets(str(held[i]["text"])),
          [redact_secrets(str(f)) for f in held[i]["files"]]) for i in order], req["change"])
    seen = await squire.decide("memory_rule_all", state, qs)
    answer = seen.answer("broken")
    if seen.failed or answer.empty:
        return {"failed": "memory_rule_all"}
    named = [0.0] * len(held)
    for k, i in enumerate(order, 1):
        named[i] = float(answer.probabilities.get(f"rule_{k}", 0.0))
    asked = [i for i in range(len(held)) if named[i] >= mr.CANDIDATE_AT]
    kept: dict[int, float | None] = {}
    for i in asked:
        d = await squire.decide("memory_rule_check",
                                *points.questions_for_change(str(held[i]["text"]), req["change"]))
        k = d.answer("kept")
        kept[i] = None if d.failed or k.empty else k.truth
    return {"held": [r["text"] for r in held], "named": named, "kept": kept,
            "none": float(answer.probabilities.get("none", 0.0)),
            "broken": [held[i]["text"] for i, p in kept.items()
                       if p is not None and p < mr.BROKEN_BELOW]}  # fmt: skip


async def run(live: bool) -> dict[str, Any]:
    recorded = RecordedDecider.from_file(FIXTURE)
    inner = RecordingDecider(create("jev", api_key=api_key()), FIXTURE) if live else None
    decider = ReplayThenLive(recorded, inner)
    squire = Squire(decider, thresholds=Thresholds(max_decisions=MAX_DECISIONS, max_usd=MAX_USD),
                    redact=redact_secrets)  # fmt: skip
    projects = []
    for folder, sessions in lv.folders(lv.END):
        reqs = requests_of(folder, sessions)
        if not reqs:
            continue
        await extract(squire, reqs)
        rules: list[dict[str, Any]] = []
        for req in reqs:
            req["audit"] = await audit_one(squire, req, rules)
            for s in req["sentences"]:
                norm = mr._norm(s["sentence"])
                if s["p"] is not None and s["p"] >= mr.STANDING_AT \
                        and norm not in {mr._norm(r["text"]) for r in rules}:
                    rules = [{"text": s["sentence"], "p": s["p"], "session": req["session"],
                              "index": req["index"], "files": req["files"][:4]}, *rules
                             ][: mr.KEEP_MAX]  # fmt: skip
        projects.append({"folder": folder, "requests": reqs, "rules": rules})
        if squire.exhausted:
            break
    return {"projects": projects, "live_calls": decider.live_calls,
            "exhausted": squire.exhausted}


def summary(result: dict[str, Any]) -> dict[str, Any]:
    reqs = [r for p in result["projects"] for r in p["requests"]]
    sents = [s for r in reqs for s in r["sentences"]]
    answered = [s for s in sents if s["p"] is not None]
    flagged = [s for s in answered if s["p"] >= mr.STANDING_AT]
    audits = [r["audit"] for r in reqs if r.get("audit")]
    ok = [a for a in audits if "failed" not in a]
    return {
        "folders": len(result["projects"]), "requests": len(reqs),
        "sentences": len(sents), "answered": len(answered),
        "rule_sentences": len(flagged),
        "rule_rate": round(len(flagged) / max(1, len(answered)), 4),
        "requests_with_a_rule": sum(1 for r in reqs
                                    if any((s["p"] or 0) >= mr.STANDING_AT for s in r["sentences"])),
        "requests_with_a_change": sum(1 for r in reqs if r["change"].strip()),
        "audited": len(ok), "audit_failed": len(audits) - len(ok),
        "sent_back": sum(1 for a in ok if a["broken"]),
        "kept_asked": sum(len(a["kept"]) for a in ok),
        "rules_per_project": {p["folder"][-40:]: len(p["rules"]) for p in result["projects"]},
        "live_calls": result["live_calls"], "exhausted": result["exhausted"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    result = asyncio.run(run(args.live))
    DETAIL.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str),
                      encoding="utf-8")  # fmt: skip
    print(json.dumps(summary(result), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
