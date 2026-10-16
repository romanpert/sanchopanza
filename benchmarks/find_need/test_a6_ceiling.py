"""The A6 ceiling on two synthetic sessions with known prices. No cache, no API.

Run: .venv/Scripts/python.exe -m pytest benchmarks/find_need -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from . import a6_ceiling as a6

SONNET = "claude-sonnet-5-5"


def _assistant(
    mid: str,
    output: int,
    tools: list[tuple[str, dict]],
    *,
    write: int = 0,
    read: int = 1000,
    parent: str | None = None,
) -> dict:
    content = [
        {"type": "tool_use", "id": f"{mid}-t{k}", "name": n, "input": given}
        for k, (n, given) in enumerate(tools)
    ]
    usage = {
        "input_tokens": 10,
        "output_tokens": output,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": write,
    }
    return {
        "type": "assistant",
        "parent_tool_use_id": parent,
        "message": {"id": mid, "model": SONNET, "usage": usage, "content": content},
    }


def _session(folder: Path, msgs: list[tuple[str, list, int]], *, start_output: int = 5) -> Path:
    """A stream whose usage carries the output tokens at message start (`start_output`), and a
    transcript beside it with each message's final usage, as Claude Code writes them."""
    folder.mkdir(parents=True)
    stream = [_assistant(mid, start_output, tools, write=write) for mid, tools, write in msgs]
    final = [
        _assistant(mid, 100 * (k + 1), tools, write=write)
        for k, (mid, tools, write) in enumerate(msgs)
    ]
    (folder / "stream-1.jsonl").write_text("\n".join(map(json.dumps, stream)), encoding="utf-8")
    (folder / "transcript.jsonl").write_text("\n".join(map(json.dumps, final)), encoding="utf-8")
    return folder / "stream-1.jsonl"


GOLD = ["pkg/core.py"]
MSGS = [
    ("m0", [("Bash", {"command": "ls"})], 20_000),  # the system prompt's cache write
    ("m1", [("Grep", {"pattern": "parse"})], 0),
    ("m2", [("Bash", {"command": "sed -n 1,40p pkg/core.py"})], 0),  # names the gold
    ("m3", [("Edit", {"file_path": "/w/pkg/core.py"})], 0),
]


def _cost(output: int, write: int = 0) -> float:
    return (10 * 3.0 + output * 15.0 + 1000 * 0.3 + write * 6.0) / 1e6


def test_a_request_is_priced_from_the_transcript_not_the_stream(tmp_path):
    stream = _session(tmp_path / "s", MSGS)
    priced = a6.parse_stream(stream, a6.transcript_prices(stream.parent))
    assert [e["cost"] for e in priced] == pytest.approx(
        [_cost(100, 20_000), _cost(200), _cost(300), _cost(400)]
    )
    started = a6.parse_stream(stream)  # the stream alone: output at message start
    assert started[1]["cost"] == pytest.approx(_cost(5))


def test_cost_before_the_gold_and_the_shifted_reading(tmp_path):
    stream = _session(tmp_path / "s", MSGS)
    entries = a6.parse_stream(stream, a6.transcript_prices(stream.parent))
    view = a6.before_gold(entries, GOLD, SONNET, "view")
    assert view["touched"] and view["at_request"] == 2
    assert view["cost_before"] == pytest.approx(_cost(100, 20_000) + _cost(200))
    shifted = a6.before_gold(entries, GOLD, SONNET, "view", shift=True)
    assert shifted["cost_before"] == pytest.approx(_cost(200) + _cost(300))
    readedit = a6.before_gold(entries, GOLD, SONNET, "readedit")
    assert readedit["at_request"] == 3
    total = sum(_cost(100 * (k + 1), w) for k, (_, _, w) in enumerate(MSGS))
    assert view["total"] == pytest.approx(total)


def test_the_ceiling_over_two_sessions_and_its_bootstrap(tmp_path):
    units = []
    for name, hit in (("a", True), ("b", False)):
        stream = _session(tmp_path / name, MSGS)
        entries = a6.parse_stream(stream, a6.transcript_prices(stream.parent))
        unit = {"session": name, "chain": name, "request": 1, "bug": True, "hit5": hit}
        for mode in ("readedit", "view"):
            unit[mode] = a6.before_gold(entries, GOLD, SONNET, mode)
        units.append(unit)
    num, den = a6.ceiling(units, mode="view")
    one = _cost(100, 20_000) + _cost(200)
    assert num == pytest.approx(one)
    assert den == pytest.approx(2 * units[0]["view"]["total"])
    result = a6.boot(units, mode="view")
    assert result["clusters"] == 2 and result["lo"] <= result["ceiling"] <= result["hi"]
    by_chain = a6.boot(units, key="chain", mode="view")
    assert by_chain["ceiling"] == pytest.approx(result["ceiling"])


def test_the_summary_carries_no_text_paths_or_ids(tmp_path):
    unit = {
        "session": "L/x/N",
        "group": "g",
        "model": SONNET,
        "arm": "N",
        "chain": "x",
        "request": 1,
        "instance": "repo__x.1",
        "bug": True,
        "gold": ["pkg/core.py"],
        "hit5": True,
        "top5": ["pkg/core.py"],
        "readedit": {"touched": True, "cost_before": 1.0, "total": 4.0, "touch_msg": "msg_1"},
        "view": {"touched": True, "cost_before": 1.0, "total": 4.0, "touch_msg": "msg_1"},
    }
    full = tmp_path / "full.json"
    block = {"describe": {"sessions": 1}, "ceilings": {a6.HEADLINE: {"ceiling": 0.25}}}
    full.write_text(
        json.dumps({"threshold": 0.05, "blocks": {"g | " + SONNET: block}, "units": [unit]}),
        encoding="utf-8",
    )
    a6.summary(full, tmp_path / "out.json")
    text = (tmp_path / "out.json").read_text(encoding="utf-8")
    assert "pkg/core.py" not in text and "msg_1" not in text and "repo__x.1" not in text
