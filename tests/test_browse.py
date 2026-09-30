"""Browse: reading a page into elements, ranking them for a goal, rendering a lean page."""

from __future__ import annotations

from pathlib import Path

import pytest

from sanchopanza import answers
from sanchopanza.browse import (
    Element,
    elements_from_html,
    elements_from_snapshot,
    rank,
    render,
)
from sanchopanza.points import browse as points
from sanchopanza.providers.fixed import BrokenDecider
from sanchopanza.providers.local import LocalDecider
from sanchopanza.squire import Squire

SNAPSHOT = """- Page URL: https://example.org/
- Page Title: Example shop
- Page Snapshot:
```yaml
- generic [active] [ref=e1]:
  - banner [ref=e2]:
    - link "Home" [ref=e3] [cursor=pointer]:
      - /url: /
    - searchbox "Search products" [ref=e4]
    - button "Search" [ref=e5] [cursor=pointer]
  - heading "Filters" [level=2] [ref=e6]
  - checkbox "4 stars & up" [ref=e7]
  - paragraph [ref=e8]: Free delivery on orders over 20 EUR
  - link "Careers" [ref=e9] [cursor=pointer]:
    - /url: /jobs
```"""


def test_snapshot_elements_keep_refs_urls_and_headings():
    els = elements_from_snapshot(SNAPSHOT)
    assert [e.key for e in els] == ["e3", "e4", "e5", "e7", "e9"]
    assert els[0].context == "url=/"
    assert els[3] == Element("e7", "checkbox", "4 stars & up", "under Filters")
    assert "url=/jobs" in els[4].context
    everything = elements_from_snapshot(SNAPSHOT, interactive_only=False)
    assert "e8" in {e.key for e in everything}


HTML = """<html><body><h2>Book a flight</h2>
<form><label for="to">To</label><input id="to" name="to" placeholder="City or airport">
<select name="cabin"><option>Economy</option><option>Business</option></select>
<button type="submit"><span>Search</span> flights</button></form>
<script>var a = "<a>not a link</a>";</script>
<a href="/careers"><img alt="Careers"></a><div>plain text</div></body></html>"""


def test_html_elements_are_the_interactive_ones_with_their_names():
    els = elements_from_html(HTML)
    lines = [e.line() for e in els]
    assert [e.role for e in els] == [
        "label",
        "textbox",
        "combobox",
        "option",
        "option",
        "button",
        "link",
    ]
    assert els[1].name == "City or airport", "a field with no text is named by its placeholder"
    assert els[1].context.endswith("name=to"), "and the placeholder is not repeated"
    assert "under Book a flight" in els[1].context
    assert els[5].name == "Search flights"
    assert els[6].name == "Careers", "an image's alt names its link"
    assert not any("not a link" in line for line in lines), "script text is not read"


def test_html_with_backend_node_ids_reads_every_element_carrying_one():
    html = '<div backend_node_id="1"><span backend_node_id="2">Andorra</span></div><p>x</p>'
    els = elements_from_html(html)
    assert [(e.key, e.name) for e in els] == [("1", "Andorra"), ("2", "Andorra")]


async def test_without_a_squire_the_ranking_is_bm25_and_free():
    els = elements_from_snapshot(SNAPSHOT)
    ranked = await rank("search for headphones", els, keep=2)
    assert ranked[0].element.key in ("e4", "e5")
    assert all(r.p is None for r in ranked)


def _judge_by_name(wanted: str):
    def handler(state, question):
        label = str(question.instructions).split(":")[0].split()[-1]
        for line in state["elements"].splitlines():
            if line.startswith(label + "|"):
                return answers.truth(0.95 if wanted in line else 0.05)
        return None

    return handler


async def test_the_decider_ranks_and_the_final_round_rejudges_the_best():
    els = [Element(f"k{i}", "link", f"item {i}") for i in range(75)]
    els[61] = Element("k61", "button", "Checkout now")
    decider = LocalDecider(_judge_by_name("Checkout"), cost_usd_per_call=0.0001)
    squire = Squire(decider)
    ranked = await rank("pay for the basket", els, squire=squire, keep=3)
    assert ranked[0].element.key == "k61"
    assert ranked[0].p == pytest.approx(0.95)
    assert squire.meter.decisions == 4, "three groups of 25 and one final round"


async def test_a_failed_decider_degrades_to_bm25():
    els = elements_from_snapshot(SNAPSHOT)
    ranked = await rank("search", els, squire=Squire(BrokenDecider()), keep=2)
    assert ranked and all(r.p is None for r in ranked)


async def test_shortlist_limits_what_the_decider_sees():
    els = [Element(f"k{i}", "link", f"item {i}") for i in range(40)] + [
        Element("s", "searchbox", "Search")
    ]
    squire = Squire(LocalDecider(_judge_by_name("Search")))
    ranked = await rank("Search", els, squire=squire, shortlist=5, keep=5)
    assert ranked[0].element.key == "s"
    assert squire.meter.decisions == 1


def test_questions_cap_the_group_and_label_every_line():
    state, qs = points.questions(goal="g", done=["a"] * 20, lines=[f"l{i}" for i in range(40)])
    assert len(qs) == points.GROUP_MAX
    assert state["elements"].splitlines()[0] == "E01| l0"
    assert len(state["done"].splitlines()) == points.DONE_MAX


def test_render_keeps_refs_and_says_what_was_left_out():
    els = elements_from_snapshot(SNAPSHOT)
    from sanchopanza.browse import Ranked

    text = render([Ranked(els[1], 0.9, 1.0)], total=5, title="Shop", archive="a/b.txt")
    assert '- searchbox "Search products" [ref=e4]' in text
    assert "4 other elements not shown" in text and "a/b.txt" in text


def _big_snapshot(n: int = 400) -> str:
    rows = ["- generic [ref=e1]:", '  - heading "Results" [level=1] [ref=e2]']
    for i in range(n):
        rows.append(f"  - listitem [ref=r{i}]:")
        rows.append(f'    - link "Product {i} blue widget" [ref=l{i}] [cursor=pointer]:')
        rows.append(f"      - /url: /p/{i}")
        rows.append(f"    - paragraph [ref=t{i}]: Price {i} EUR, ships in {i % 7} days")
    rows.append('  - button "Checkout basket" [ref=co]')
    return "\n".join(rows) + "\n"


def test_prune_keeps_refs_with_ancestors_urls_and_headings():
    from sanchopanza.browse import prune_snapshot

    snap = _big_snapshot(50)
    pruned, left = prune_snapshot(snap, ["l7", "co"], purpose="checkout", text_budget=0)
    lines = pruned.splitlines()
    assert lines[0] == "- generic [ref=e1]:", "the root ancestor stays"
    assert '  - heading "Results" [level=1] [ref=e2]' in lines
    assert "  - listitem [ref=r7]:" in lines, "the kept link's parent stays"
    assert "      - /url: /p/7" in lines
    assert '  - button "Checkout basket" [ref=co]' in lines
    assert "l8" not in pruned and left > 100


def test_prune_keeps_text_lines_that_match_the_purpose_within_budget():
    from sanchopanza.browse import prune_snapshot

    pruned, _ = prune_snapshot(_big_snapshot(30), [], purpose="Price 12 EUR", text_budget=200)
    assert "Price 12 EUR" in pruned
    assert sum("paragraph" in line for line in pruned.splitlines()) <= 5


def _playwright_event(tmp_path, snapshot: str) -> dict:
    text = (
        "### Ran Playwright code\n```js\nawait page.goto('https://shop.example/');\n```\n"
        "### Page state\n- Page URL: https://shop.example/\n- Page Title: Shop\n"
        f"- Page Snapshot:\n```yaml\n{snapshot}```\n"
    )
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "mcp__playwright__browser_navigate",
        "tool_input": {"url": "https://shop.example/"},
        "tool_response": [{"type": "text", "text": text}],
        "tool_use_id": "toolu_1",
        "session_id": "s1",
        "cwd": str(tmp_path),
        "transcript_path": "",
    }


async def test_hook_prunes_a_large_snapshot_and_archives_the_whole_result(tmp_path, monkeypatch):
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    event = _playwright_event(tmp_path, _big_snapshot(400))
    out = await browse_hook.post_tool_use(event, Squire())
    updated = out["hookSpecificOutput"]["updatedToolOutput"]
    new = updated[0]["text"]
    original = event["tool_response"][0]["text"]
    assert new.startswith("### Ran Playwright code"), "what is outside the YAML passes as it was"
    assert "- Page URL: https://shop.example/" in new
    assert "# sanchopanza kept 20 of" in new
    assert len(new) < 0.3 * len(original)
    archived = list((tmp_path / "archive").rglob("browse-toolu_1*.txt"))
    assert archived and archived[0].read_text(encoding="utf-8") == original


async def test_hook_leaves_small_snapshots_and_other_results_alone(tmp_path):
    from sanchopanza.harness import browse_hook

    assert (
        await browse_hook.post_tool_use(_playwright_event(tmp_path, _big_snapshot(5)), Squire())
        == {}
    )
    plain = _playwright_event(tmp_path, "")
    plain["tool_response"] = [{"type": "text", "text": "x" * 20000}]
    assert await browse_hook.post_tool_use(plain, Squire()) == {}


REAL = Path(__file__).resolve().parents[1] / "fixtures" / "browse-snapshots" / "books-toscrape.yml"


def test_a_real_snapshot_file_is_detected_parsed_and_pruned():
    from sanchopanza.browse import prune_snapshot, snapshot_block

    text = REAL.read_text(encoding="utf-8")
    assert snapshot_block(text) == (0, len(text))
    els = elements_from_snapshot(text)
    assert len(els) == 111
    sharp = next(e for e in els if e.name == "Sharp Objects")
    assert sharp.role == "link" and "url=" in sharp.context
    pruned, left = prune_snapshot(text, [sharp.key], purpose="price of Sharp Objects")
    assert f"[ref={sharp.key}]" in pruned and len(pruned) < len(text) / 3 and left > 300


def test_a_fence_without_refs_or_plain_text_is_not_a_snapshot():
    from sanchopanza.browse import snapshot_block

    assert snapshot_block("```yaml\nkey: value\n```") is None
    assert snapshot_block("just some text\n" * 50) is None


async def test_hook_prunes_a_snapshot_read_from_a_file(tmp_path, monkeypatch):
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    text = REAL.read_text(encoding="utf-8")
    event = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": ".playwright-cli/page.yml"},
        "tool_response": {"type": "text", "file": {"filePath": "page.yml", "content": text}},
        "tool_use_id": "toolu_2",
        "session_id": "s2",
        "cwd": str(tmp_path),
        "transcript_path": "",
    }
    out = await browse_hook.post_tool_use(event, Squire())
    new = out["hookSpecificOutput"]["updatedToolOutput"]["file"]["content"]
    assert new.startswith("# sanchopanza kept 20 of 111 elements")
    assert len(new) < len(text) / 2


async def test_hook_prunes_playwright_cli_stdout(tmp_path, monkeypatch):
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    head = "### Page\n- Page URL: https://books.toscrape.com/\n### Snapshot\n```yaml\n"
    stdout = head + REAL.read_text(encoding="utf-8") + "```\n"
    event = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "playwright-cli snapshot"},
        "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False},
        "tool_use_id": "toolu_3",
        "session_id": "s3",
        "cwd": str(tmp_path),
        "transcript_path": "",
    }
    out = await browse_hook.post_tool_use(event, Squire())
    new = out["hookSpecificOutput"]["updatedToolOutput"]["stdout"]
    assert new.startswith(head) and new.endswith("```\n")


async def test_reading_the_archived_snapshot_is_never_pruned_again(tmp_path, monkeypatch):
    from sanchopanza.harness import browse_hook

    archive = tmp_path / "archive"
    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(archive))
    text = REAL.read_text(encoding="utf-8")
    kept = archive / "s4" / "browse-x.txt"
    event = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": str(kept)},
        "tool_response": {"type": "text", "file": {"filePath": str(kept), "content": text}},
        "session_id": "s4",
        "cwd": str(tmp_path),
        "transcript_path": "",
    }
    assert await browse_hook.post_tool_use(event, Squire()) == {}
    event["tool_input"] = {"file_path": str(tmp_path / "page.yml")}
    out = await browse_hook.post_tool_use(event, Squire())
    assert "never pruned" in out["hookSpecificOutput"]["updatedToolOutput"]["file"]["content"]


def test_the_hook_process_reads_and_writes_utf8_whatever_the_console(tmp_path):
    """playwright-cli prints a box-drawing banner; on Windows the console code page used to
    turn it into surrogates and the hook passed everything through (Phase 3 pilot)."""
    import json
    import os
    import subprocess
    import sys

    banner = "\u2554\u2550\u2550 Update available \u2550\u2557 a\u00f1o\n"
    stdout = banner + "### Snapshot\n```yaml\n" + REAL.read_text(encoding="utf-8") + "```\n"
    event = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "playwright-cli snapshot"},
        "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False},
        "tool_use_id": "toolu_9",
        "session_id": "s9",
        "cwd": str(tmp_path),
        "transcript_path": "",
    }
    env = {**os.environ, "SANCHOPANZA_PROVIDER": "null", "PYTHONIOENCODING": "cp1252",
           "SANCHOPANZA_ARCHIVE": str(tmp_path / "archive"), "PYTHONUTF8": "0"}  # fmt: skip
    env.pop("TYPESAFE_API_KEY", None)
    done = subprocess.run(
        [sys.executable, "-m", "sanchopanza.harness.browse_hook"],
        input=json.dumps(event, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout.decode("utf-8"))
    new = out["hookSpecificOutput"]["updatedToolOutput"]["stdout"]
    assert new.startswith(banner) and "# sanchopanza kept" in new
