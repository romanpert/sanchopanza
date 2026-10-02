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


def test_an_unnamed_element_is_described_by_its_classes_and_what_holds_it():
    """Mind2Web development misses (misses.py): unnamed SVG icons whose class said what they do
    (`add-wishlist-new__icon`, `save-icon-favorite`) and the reader threw it away."""
    html = (
        '<div backend_node_id="1"><svg backend_node_id="2" class="add-wishlist-new__icon"/></div>'
        '<button backend_node_id="3"><span backend_node_id="4">Save</span>'
        '<svg backend_node_id="5" class="icon save-icon-favorite mntl-button__icon jsx-1785568775">'
        "</svg></button>"
        '<a backend_node_id="6" class="nav-link">Home</a>'
    )
    plain = elements_from_html(html, describe_unnamed=False)
    assert not any("looks like" in e.context for e in plain), "it can be turned off"
    els = {e.key: e for e in elements_from_html(html)}
    assert "looks like: add wishlist" in els["2"].context
    assert "looks like: save favorite" in els["5"].context
    assert 'inside button "Save"' in els["5"].context
    assert "jsx" not in els["5"].context and "mntl" not in els["5"].context
    assert "looks like" not in els["6"].context, "a named element is left as it was"
    camel = elements_from_html(
        '<div backend_node_id="1"><i backend_node_id="2" class="shareButtonIcon"/></div>',
        describe_unnamed=True,
    )
    assert "looks like: share" in camel[1].context


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


def test_kept_elements_are_shown_in_page_order_not_rank_order():
    from sanchopanza.browse import Ranked, in_page_order

    page = [Element(f"k{i}", "link", f"item {i}") for i in range(6)]
    ranked = [Ranked(page[4], 0.9, 0.0), Ranked(page[1], 0.8, 0.0), Ranked(page[3], 0.7, 0.0)]
    assert [r.element.key for r, _ in in_page_order(ranked, page)] == ["k1", "k3", "k4"]
    assert all(note == "" for _, note in in_page_order(ranked, page)), "unique lines need no note"


def test_a_repeated_line_says_which_one_it_is_and_what_precedes_it():
    from sanchopanza.browse import Ranked, in_page_order

    page = [
        Element("a", "label", "Min price"),
        Element("b", "textbox", "", "type=tel"),
        Element("c", "label", "Max price"),
        Element("d", "textbox", "", "type=tel"),
    ]
    shown = in_page_order([Ranked(page[3], 0.9, 0.0), Ranked(page[1], 0.8, 0.0)], page)
    assert [note for _, note in shown] == [
        '1st of 2 alike, after label "Min price"',
        '2nd of 2 alike, after label "Max price"',
    ]


def test_render_follows_the_page_when_given_it():
    from sanchopanza.browse import Ranked

    page = [Element("x", "button", "View more"), Element("y", "link", "Home"),
            Element("z", "button", "View more")]  # fmt: skip
    text = render([Ranked(page[2], 0.9, 0.0), Ranked(page[1], 0.5, 0.0)], total=3, page=page)
    body = [line for line in text.splitlines() if line.startswith("- ")]
    assert body == [
        '- link "Home" [ref=y]',
        '- button "View more" [ref=z]  (2nd of 2 alike, after link "Home")',
    ]
    assert "in page order" in text


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


def _transcript(tmp_path, prompt: str = "Find the price of the blue widget and check out") -> str:
    """A Claude Code transcript with one user prompt: a hook in a real session always has one."""
    import json

    path = tmp_path / "transcript.jsonl"
    entry = {"type": "user", "message": {"role": "user", "content": prompt}}
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    return str(path)


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
        "transcript_path": _transcript(tmp_path),
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
        "transcript_path": _transcript(tmp_path),
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
        "transcript_path": _transcript(tmp_path),
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
        "transcript_path": _transcript(tmp_path),
    }
    assert await browse_hook.post_tool_use(event, Squire()) == {}
    event["tool_input"] = {"file_path": str(tmp_path / "page.yml")}
    out = await browse_hook.post_tool_use(event, Squire())
    assert "never pruned" in out["hookSpecificOutput"]["updatedToolOutput"]["file"]["content"]


def _oversize_event(tmp_path, saved: Path, *, transcript: Path) -> dict:
    """What Claude Code hands a PostToolUse hook when an MCP result passes its token limit:
    a notice with the path it saved the result to, never the result (probed 2026-09-30)."""
    notice = (
        "Error: result (72.457 characters across 1175 lines) exceeds maximum allowed tokens. "
        f"Output has been saved to {saved}.\nFormat: Plain text\n"
        "- For targeted searches (find a line, locate a string): use grep on the file directly."
    )
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "mcp__playwright__browser_snapshot",
        "tool_input": {},
        "tool_response": notice,
        "tool_use_id": "toolu_big",
        "session_id": "sess",
        "cwd": str(tmp_path),
        "transcript_path": str(transcript),
    }


async def test_an_oversized_mcp_result_comes_back_pruned_instead_of_the_notice(
    tmp_path, monkeypatch
):
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    page = "### Page\n- Page URL: https://shop.example/\n### Snapshot\n```yaml\n"
    saved, transcript = _saved_snapshot(tmp_path, page + _big_snapshot(400) + "```\n")
    out = await browse_hook.post_tool_use(_oversize_event(tmp_path, saved, transcript=transcript),
                                          Squire())  # fmt: skip
    new = out["hookSpecificOutput"]["updatedToolOutput"]
    assert isinstance(new, str) and new.startswith("### Page\n- Page URL: https://shop.example/")
    assert "# sanchopanza kept 20 of" in new and "exceeds maximum" not in new
    assert len(new) < 0.3 * saved.stat().st_size


async def test_a_notice_naming_a_file_outside_the_session_is_left_alone(tmp_path, monkeypatch):
    """A page can print a fake notice; the hook reads only its own session's tool-results."""
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    elsewhere = tmp_path / "secrets" / "tool-results" / "notes.txt"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.write_text(_big_snapshot(400), encoding="utf-8")
    event = _oversize_event(tmp_path, elsewhere, transcript=tmp_path / "project" / "sess.jsonl")
    assert await browse_hook.post_tool_use(event, Squire()) == {}


async def test_the_agents_own_search_results_are_never_pruned(tmp_path, monkeypatch):
    """Phase 3b: a pruned `browser_find` sent the agent to read the whole archive (3 of 4)."""
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    event = _playwright_event(tmp_path, _big_snapshot(400))
    event["tool_name"] = "mcp__playwright__browser_find"
    assert await browse_hook.post_tool_use(event, Squire()) == {}
    stdout = event["tool_response"][0]["text"]
    cli = {**event, "tool_name": "Bash", "tool_input": {"command": "playwright-cli find Price"},
           "tool_response": {"stdout": stdout, "stderr": ""}}  # fmt: skip
    assert await browse_hook.post_tool_use(cli, Squire()) == {}


async def test_what_the_agent_narrowed_itself_is_never_pruned(tmp_path, monkeypatch):
    """Phase 3c: a `Read` with a limit and a snapshot of one element were cut, and the agent
    went looking for what the cut removed (M4)."""
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    text = REAL.read_text(encoding="utf-8")
    read = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "page.yml", "limit": 150},
        "tool_response": {"type": "text", "file": {"filePath": "page.yml", "content": text}},
        "session_id": "s5",
        "cwd": str(tmp_path),
        "transcript_path": _transcript(tmp_path),
    }
    assert await browse_hook.post_tool_use(read, Squire()) == {}
    targeted = _playwright_event(tmp_path, _big_snapshot(400))
    targeted["tool_name"] = "mcp__playwright__browser_snapshot"
    targeted["tool_input"] = {"target": "e166"}
    assert await browse_hook.post_tool_use(targeted, Squire()) == {}
    whole = {**targeted, "tool_input": {}}
    note = (await browse_hook.post_tool_use(whole, Squire()))["hookSpecificOutput"]
    assert "Grep" in note["updatedToolOutput"][0]["text"], "recovery starts with a search"


def test_the_goal_keeps_every_part_when_there_is_a_follow_up():
    """Review 2026-10-01: a long request plus a follow-up pushed the agent's step past 400."""
    from sanchopanza.harness.browse_hook import GOAL_LIMIT, browse_goal

    long = "Please open the page and look around carefully. " * 12 + "Which license is it?"
    messages = [
        {"role": "user", "content": [{"type": "text", "text": long}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Opening it"}]},
        {"role": "user", "content": [{"type": "text", "text": "And the main language too?"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Taking the snapshot now"}]},
    ]
    goal = browse_goal(messages)
    assert len(goal) <= GOAL_LIMIT
    assert "Which license is it?" in goal and "main language" in goal
    assert "Taking the snapshot now" in goal


async def test_with_no_goal_the_hook_does_not_rank(tmp_path, monkeypatch):
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    event = _playwright_event(tmp_path, _big_snapshot(400))
    event["transcript_path"] = str(tmp_path / "missing.jsonl")
    assert browse_hook.browse_goal([]) == ""
    assert await browse_hook.post_tool_use(event, Squire()) == {}


def _saved_snapshot(tmp_path, body: str) -> tuple:
    transcript = tmp_path / "project" / "sess.jsonl"
    saved = tmp_path / "project" / "sess" / "tool-results" / "mcp-playwright-browser_snapshot-2.txt"
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_text(body, encoding="utf-8")
    transcript.write_text(
        '{"type": "user", "message": {"role": "user", "content": "find the blue widget"}}\n',
        encoding="utf-8",
    )
    return saved, transcript


async def test_only_an_mcp_result_is_read_from_the_saved_file(tmp_path, monkeypatch):
    """Review 2026-10-01: a page printed by `cat` could carry a notice naming another file."""
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    page = "### Page\n### Snapshot\n```yaml\n" + _big_snapshot(400) + "```\n"
    saved, transcript = _saved_snapshot(tmp_path, page)
    event = _oversize_event(tmp_path, saved, transcript=transcript)
    bash = {**event, "tool_name": "Bash", "tool_input": {"command": "cat page.txt"},
            "tool_response": {"stdout": event["tool_response"], "stderr": ""}}  # fmt: skip
    assert await browse_hook.post_tool_use(bash, Squire()) == {}
    wrapped = {**event, "tool_response": [{"type": "text", "text": event["tool_response"]}]}
    out = await browse_hook.post_tool_use(wrapped, Squire())
    new = out["hookSpecificOutput"]["updatedToolOutput"]
    assert isinstance(new, list) and "# sanchopanza kept" in new[0]["text"], "the shape is kept"


async def test_a_pruned_result_past_claude_codes_limit_is_not_returned(tmp_path, monkeypatch):
    """Review 2026-10-01: text outside the YAML passes untouched, so a saved result can still
    be past the limit after pruning; the notice stays."""
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    huge = "### Console\n" + ("log line\n" * 20000)
    page = huge + "### Snapshot\n```yaml\n" + _big_snapshot(400) + "```\n"
    saved, transcript = _saved_snapshot(tmp_path, page)
    event = _oversize_event(tmp_path, saved, transcript=transcript)
    assert await browse_hook.post_tool_use(event, Squire()) == {}


def test_page_order_uses_the_pages_own_lines():
    """A ranked element whose line differs from the page's (same key) must not crash."""
    from sanchopanza.browse import Ranked, in_page_order

    page = [Element("a", "button", "Go"), Element("b", "button", "Go")]
    stale = Element("b", "button", "Go now")
    shown = in_page_order([Ranked(stale, 0.9, 0.0)], page)
    assert shown[0][1] == '2nd of 2 alike, after button "Go"' or shown[0][1].startswith("2nd")


def test_a_heading_that_matches_the_goal_brings_the_start_of_its_section():
    """Phase 3f, W2: the cut kept "Languages" and dropped "TypeScript 95.6%" under it, and the
    agent went looking for it (+0.05 USD a session)."""
    from sanchopanza.browse import prune_snapshot

    rows = ["- generic [ref=e1]:", '  - heading "About" [level=2] [ref=e2]']
    rows += [f"  - paragraph [ref=p{i}]: filler line number {i}" for i in range(300)]
    rows += ['  - heading "Languages" [level=2] [ref=e3]', "  - list [ref=e4]:"]
    rows += ["    - listitem [ref=e5]: TypeScript 95.6%", "    - listitem [ref=e6]: CSS 1.4%"]
    rows += ['  - heading "Footer" [level=2] [ref=e7]']
    rows += [f"  - paragraph [ref=f{i}]: footer text {i}" for i in range(50)]
    snapshot = "\n".join(rows) + "\n"
    pruned, _ = prune_snapshot(snapshot, [], purpose="Which language makes up most of the code?")
    assert "TypeScript 95.6%" in pruned and "CSS 1.4%" in pruned
    assert "footer text 3" not in pruned and "filler line number 7" not in pruned


async def test_a_huge_page_is_shortlisted_before_the_decider(tmp_path, monkeypatch):
    """Phase 3f, W4 and W7: ranking 2,000-3,000 elements cost Jev 0.02-0.035 USD a snapshot,
    more than the cut saved. Past BROWSE_MAX_ELEMENTS, BM25 shortlists first."""
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    monkeypatch.setenv("SANCHOPANZA_BROWSE_MAX_ELEMENTS", "120")
    calls = []

    def judge(state, question):
        calls.append(1)
        # the request's own question (`judged_position`) gets a no: this goal is not a place
        return answers.truth(0.0 if "request" in state else 0.5)

    squire = Squire(LocalDecider(judge, cost_usd_per_call=0.0001))
    event = _playwright_event(tmp_path, _big_snapshot(400))
    out = await browse_hook.post_tool_use(event, squire)
    assert out, "it still cuts"
    assert squire.meter.decisions <= 120 // points.GROUP_MAX + 1 + 1, "ranking, plus position"


def test_layout_classes_say_nothing():
    from sanchopanza.browse import _class_words

    assert _class_words("flex items-center justify-between rounded shadow hover") == []
    assert _class_words("SVGIcon heartIcon") == ["heart"]


def test_a_cli_url_containing_find_is_not_a_search():
    from sanchopanza.harness.browse_hook import _is_search

    assert not _is_search("Bash", {"command": "playwright-cli goto https://x.com/find-a-store"})
    assert _is_search("Bash", {"command": "playwright-cli -s=t1 find Price"})
    assert _is_search("Bash", {"command": "agent-browser find 'Add to cart'"})


def test_the_goal_keeps_the_question_at_the_end_of_a_long_request():
    """A 2026-09-30 probe: the shared purpose kept the first 130 characters of the request, the
    URL and the instructions, and cut "which license" off; the ranking never saw the question."""
    from sanchopanza.harness.browse_hook import browse_goal

    request = (
        "Call browser_navigate to https://github.com/microsoft/playwright?tab=readme-ov-file"
        "&utm_source=x, then call browser_snapshot exactly once, and look carefully at the "
        "sidebar and at every section of the page before you answer. From that snapshot "
        "alone, say which license the repository has."
    )
    messages = [
        {"role": "user", "content": [{"type": "text", "text": request}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Taking the snapshot"}]},
    ]
    goal = browse_goal(messages)
    assert "which license the repository has" in goal
    assert "github.com" in goal and "utm_source" not in goal, "a URL is cut to its host"
    assert "Taking the snapshot" in goal and len(goal) <= 400


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
        "transcript_path": _transcript(tmp_path),
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


def test_a_question_about_position_is_never_cut():
    """Phases 3c (M6), 3f (W12) and 3h (X12): asked for the first book or quote listed, the cut
    kept the elements to act on and dropped the first one; in 3h a run answered with the wrong
    author. Nothing in a line says it is first, so the hook does not cut for such a goal."""
    from sanchopanza.harness.browse_hook import asks_for_position

    assert asks_for_position(
        "Open the quotes tagged 'humor' and report the author of the first one."
    )
    assert asks_for_position("What is the title of the 3rd book on page 2?")
    assert asks_for_position("Report the last entry in the table")
    assert asks_for_position("Go to page 3 and report the title of the first book on it.")
    assert not asks_for_position("Which license is this repository under?")
    assert not asks_for_position("Who designed Python and in which year did it first appear?")
    assert not asks_for_position("When was it first released?")


async def test_the_hook_passes_a_positional_goal_through(tmp_path, monkeypatch):
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    event = _playwright_event(tmp_path, _big_snapshot(400))
    event["transcript_path"] = _transcript(tmp_path, "Report the title of the first product listed")
    assert await browse_hook.post_tool_use(event, Squire()) == {}


def _infobox(rows: int = 30) -> str:
    out = ["- generic [ref=e1]:", "  - table [ref=t1]:", "    - rowgroup [ref=g1]:"]
    for i in range(rows):
        out += [
            f"      - row [ref=r{i}]:",
            f'        - rowheader "Key {i}" [ref=h{i}]',
            f"        - cell [ref=c{i}]:",
            f"          - text: value {i} km",
        ]
    out += [
        "      - row [ref=rm]:",
        "        - rowheader [ref=hm]:",
        '          - link "Mouth" [ref=lm] [cursor=pointer]:',
        "            - /url: /mouth",
        "        - cell [ref=cm]:",
        '          - link "Delta" [ref=ld] [cursor=pointer]:',
    ]
    out += ["  - table [ref=t2]:"]
    for i in range(30):
        out += [
            f"    - row [ref=d{i}]:",
            f'      - rowheader "Lake {i}" [ref=dh{i}]',
            f'      - cell "Area {i}" [ref=da{i}]',
            f'      - cell "Depth {i}" [ref=dd{i}]',
        ]
    return "\n".join(out) + "\n"


def test_a_key_value_table_the_cut_touches_keeps_its_keys_and_values():
    """Phase 3j, Y4: the cut kept the infobox row "Mouth" (its header is a link) and dropped
    "Length 2,850 km", plain text the ranking never sees and with no word of "how long"."""
    from sanchopanza.browse import prune_snapshot

    pruned, _ = prune_snapshot(_infobox(), ["lm"], purpose="how long is the river", text_budget=0)
    assert '- rowheader "Key 17" [ref=h17]' in pruned and "- text: value 17 km" in pruned
    assert "Lake 3" not in pruned, "a table of several cells a row is not a key-value table"


def test_key_value_rows_nearest_the_kept_one_come_first_within_the_budget():
    """The Danube's "Length" is the 23rd of 52 rows, three after "Mouth" (the kept one); in page
    order the budget ran out before it. An infobox groups related facts, so nearest first."""
    from sanchopanza.browse import KEY_VALUE_CHARS, prune_snapshot

    pruned, _ = prune_snapshot(_infobox(400), ["lm"], purpose="length", text_budget=0)
    assert "Key 399" in pruned and "Key 380" in pruned and "Key 0" not in pruned
    assert len(pruned) < 2 * KEY_VALUE_CHARS


def test_an_untouched_key_value_table_stays_out():
    from sanchopanza.browse import prune_snapshot

    pruned, _ = prune_snapshot(_infobox(), [], purpose="nothing", text_budget=0)
    assert "Key 5" not in pruned


def _catalogue(n: int = 40) -> str:
    out = ["- generic [ref=e1]:", "  - list [ref=l0]:"]
    for i in range(n):
        out += [
            f"    - listitem [ref=li{i}]:",
            f"      - article [ref=a{i}]:",
            f"        - link [ref=im{i}] [cursor=pointer]:",
            f"          - /url: /b/{i}",
            f'          - img "Book {i}" [ref=g{i}]',
            f"        - paragraph [ref=st{i}]:",
            *[f"          - generic [ref=st{i}x{k}]: " for k in range(5)],
            f'        - heading "Book {i}" [level=3] [ref=h{i}]:',
            f'          - link "Book {i}" [ref=k{i}] [cursor=pointer]:',
            f"            - /url: /b/{i}",
            f"        - paragraph [ref=p{i}]: £{i}.44",
            f"        - paragraph [ref=s{i}]: In stock",
            f'        - button "Add to basket" [ref=b{i}]',
        ]
    return "\n".join(out) + "\n"


def test_a_kept_element_brings_the_facts_of_its_card():
    """3j/3k Y12: the cut kept the link "The Stranger" and dropped its price, a paragraph beside
    it in the same product card."""
    from sanchopanza.browse import prune_snapshot

    pruned, _ = prune_snapshot(_catalogue(), ["k7"], purpose="price of Book 7", text_budget=0)
    assert "£7.44" in pruned and "In stock" in pruned
    assert "£8.44" not in pruned, "only the kept element's own card"
