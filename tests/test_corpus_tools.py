"""The label and browse tools as an agent reaches them: MCP tools and CLI subcommands."""

from __future__ import annotations

import json

import pytest

from sanchopanza import answers
from sanchopanza.providers.local import LocalDecider
from sanchopanza.squire import Squire


class Fake:
    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, description: str | None = None):  # noqa: ANN201
        def register(fn):  # noqa: ANN001, ANN202
            assert description is None or len(description) <= 200, "every session pays for it"
            self.tools[fn.__name__] = fn
            return fn

        return register

    def run(self) -> None:
        pass


def sports_or_business(state, question):
    if "goal" in state.get("text", "").lower():
        return answers.choice({"sports": 0.95, "business": 0.03, "other": 0.02})
    return answers.choice({"sports": 0.05, "business": 0.9, "other": 0.05})


async def test_label_file_tool_writes_the_columns_and_caps_spend(tmp_path):
    from sanchopanza.harness.mcp import add_label

    items = tmp_path / "items.jsonl"
    items.write_text('{"id": "a", "text": "late goal"}\n{"id": "b", "text": "shares up"}\n')
    squire = Squire(LocalDecider(sports_or_business, cost_usd_per_call=0.001))
    server = add_label(Fake(), squire)
    rubric = json.dumps({"field": "topic", "options": {"sports": "sport", "business": "money"}})
    out = tmp_path / "out.csv"
    report = json.loads(await server.tools["label_file"](str(items), rubric, str(out), 0.5))
    assert report["labelled"] == 2 and report["labels"] == {"sports": 1, "business": 1}
    assert out.read_text().splitlines()[1].startswith("a,sports,0.9500")
    capped = json.loads(
        await add_label(Fake(), squire).tools["label_file"](
            str(items), rubric.replace("money", "finance"), str(tmp_path / "o2.csv"), 0.0005
        )
    )
    assert capped["abstained"].get("budget", 0) >= 1, "the ceiling holds per call"


async def test_label_file_tool_explains_a_bad_rubric(tmp_path):
    from sanchopanza.harness.mcp import add_label

    squire = Squire(LocalDecider(sports_or_business))
    tool = add_label(Fake(), squire).tools["label_file"]
    assert "Could not read" in await tool(str(tmp_path / "none.jsonl"), "{}", "o.csv")


async def test_rank_elements_tool_reads_a_snapshot_or_a_file(tmp_path):
    from sanchopanza.harness.mcp import add_browse

    snapshot = '- searchbox "Search" [ref=e4]\n- link "Careers" [ref=e9]\n'
    tool = add_browse(Fake()).tools["rank_elements"]
    text = await tool("search for shoes", snapshot, "", 1)
    assert "[ref=e4]" in text and "1 other elements not shown" in text
    page = tmp_path / "page.html"
    page.write_text('<a href="/x">Careers</a><input placeholder="Search shoes">')
    assert "Search shoes" in await tool("search for shoes", str(page), "", 1)
    assert "No elements" in await tool("x", "plain words", "", 3)


def test_mcp_main_offers_the_new_tool_sets(monkeypatch: pytest.MonkeyPatch):
    from sanchopanza.harness import mcp

    fake = Fake()
    monkeypatch.setattr(mcp, "_server", lambda name: fake)
    mcp.main(["--tools", "label,browse"])
    assert list(fake.tools) == ["label_file", "rank_elements"]


def test_cli_browse_ranks_a_snapshot_for_free(tmp_path, capsys, monkeypatch):
    from sanchopanza.cli import main

    monkeypatch.setenv("SANCHOPANZA_PROVIDER", "null")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    page = tmp_path / "snap.yaml"
    page.write_text('- link "Careers" [ref=e9]\n- button "Add to basket" [ref=e3]\n')
    assert main(["browse", str(page), "--goal", "add to basket", "--keep", "1"]) == 0
    assert "[ref=e3]" in capsys.readouterr().out


def test_cli_label_refuses_without_a_provider(tmp_path, monkeypatch):
    from sanchopanza.cli import main

    monkeypatch.setenv("SANCHOPANZA_PROVIDER", "null")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    rubric = tmp_path / "r.json"
    rubric.write_text('{"field": "t", "options": ["a", "b"]}')
    items = tmp_path / "i.txt"
    items.write_text("one\n")
    assert main(["label", str(items), "--rubric", str(rubric), "--out", str(tmp_path / "o")]) == 2
