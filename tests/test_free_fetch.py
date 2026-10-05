"""The offline replay and the smoke runner of fetch by passages. No model, no network, no money:
only the pure helpers are run here."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


offline = _load("browse_free_fetch_offline", "benchmarks/browse/free_fetch_offline.py")
smoke = _load("browse_free_fetch_smoke", "benchmarks/browse/free_fetch_smoke.py")


def _s(searches: int, fetches: int, a: float = 0.023, b: float = 0.024) -> dict:
    return {"searches": searches, "fetches_ok": fetches, "reader_usd": a * searches + b * fetches}


def test_the_split_recovers_the_per_call_costs() -> None:
    rows = [_s(4, 0), _s(3, 2), _s(0, 5), _s(7, 1), _s(2, 6)]
    a, b = offline.split_costs(rows)
    assert abs(a - 0.023) < 1e-9 and abs(b - 0.024) < 1e-9


def test_with_no_fetch_the_split_is_per_search_only() -> None:
    a, b = offline.split_costs([_s(4, 0), _s(2, 0)])
    assert abs(a - 0.023) < 1e-9 and b == 0.0


def test_gold_presence_uses_the_graders_rules() -> None:
    assert offline.present("1873", "the survey of 1873 was")
    assert not offline.present("1873", "the survey of 18734")
    assert offline.present("Lake Example", "about lake example, a lake")
    assert not offline.present("Lake Example", "about lake examples")


def test_summary_facts_are_numbers_and_names() -> None:
    found = offline.facts("The lake is 1,642 m deep; Pierre Dupont surveyed it in 1873.")
    assert {"1642", "Pierre Dupont", "1873"} <= found
    assert "The" not in found


def _row(arm: str = "SONNET", tok: float = 1000.0, later: int = 4) -> dict:
    row = {"arm": arm, "page_tok": 3000.0, "summary_tok": 100.0, "later_calls": later,
           "gold_on_page": True, "gold_in_summary": False, "facts": 3}  # fmt: skip
    for budget in offline.BUDGETS:
        row.update({f"tok_{budget}": tok, f"gold_{budget}": True, f"facts_{budget}": 2})
    return row


def test_the_net_saving_prices_the_passages_at_cache_write_and_reads() -> None:
    out = offline.summarise([_row()], per_fetch_usd=0.024)
    expected = 0.024 - 900 * (4.0 + 0.2 * 4) / 1e6
    assert abs(out["budget_8000"]["net_usd_per_fetch_mean"] - round(expected, 4)) < 1e-9
    assert out["gold_on_page"] == 1 and out["budget_8000"]["gold"] == 1


def test_the_smoke_adds_the_server_and_hooks_webfetch(tmp_path: pathlib.Path) -> None:
    def original(work: pathlib.Path) -> pathlib.Path:
        path = work / "mcp.json"
        path.write_text(json.dumps({"mcpServers": {"playwright": {}}}), encoding="utf-8")
        return path

    doc = json.loads(smoke.mcp_config_with_fetch(original)(tmp_path).read_text(encoding="utf-8"))
    assert set(doc["mcpServers"]) == {"playwright", smoke.SERVER}
    assert doc["mcpServers"][smoke.SERVER]["args"][-1] == "fetch-mcp"
    hooks = smoke.hooks()["PreToolUse"]
    assert hooks[0]["matcher"] == "WebFetch"
    assert "sanchopanza.harness.fetch_hook" in hooks[0]["hooks"][0]["command"]


# --- fetch v2, offline ---------------------------------------------------------------------------


def test_the_pilot_page_calls_are_read_with_their_purpose_and_budget(
    tmp_path: pathlib.Path,
) -> None:
    given = {"url": "https://a.example/x", "purpose": "the year", "budget": 5000}
    use = {"type": "tool_use", "id": "u1", "name": offline.PASSAGES_TOOL, "input": given}
    result = {
        "type": "tool_result",
        "tool_use_id": "u1",
        "content": "Could not fetch it: HTTP 404.",
    }
    lines = [{"type": "assistant", "message": {"id": "m1", "content": [use]}},
             {"type": "user", "message": {"content": [result]}}]  # fmt: skip
    (tmp_path / "s.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    calls = offline.passage_calls(tmp_path)
    assert calls == [{"url": "https://a.example/x", "purpose": "the year", "budget": 5000,
                      "failed": True}]  # fmt: skip


def test_the_versions_are_compared_on_the_same_page_purpose_and_budget() -> None:
    html = ("<h1>Lake</h1><div class='mw-portlet'>" + "Lang " * 300 + "</div>"
            "<p>The lake is deep and cold in every season of the year.</p>"
            "<h2>History</h2><p>The first survey was in 1873.</p>")  # fmt: skip
    out = offline.compare_versions(html, "first survey", 8000, "1873")
    assert out["gold_v1"] and out["gold_v2"]
    assert out["tok_v2"] < out["tok_v1"]
