"""The browse hook on a `Bash` output Claude Code saved to a file because it was too large.

Probed 2026-10-01 (one `claude -p` session, a recording hook): past 30,000 characters Claude Code
saves the whole output to the session's `tool-results` folder, hands the hook `stdout` cut at
exactly 30,000 characters plus `persistedOutputPath` and `persistedOutputSize`, and shows the
model only the first 2,000 characters of whatever the hook returns. Phase 3i (X2, X4): the hook
ranked the 30,000-character prefix (128 of France's 3,569 elements), archived that prefix as
"never pruned", and the model saw two kilobytes of the cut; it then searched an archive that
did not hold the answer.
"""

from __future__ import annotations

import json
from pathlib import Path

from sanchopanza.squire import Squire
from tests.test_browse import _big_snapshot

PAGE = "### Page\n- Page URL: https://shop.example/\n- Page Title: Shop\n### Snapshot\n```yaml\n"
BANNER = "+--------+\n| Update available for @playwright/cli |\n+--------+\n\n"


def _session(tmp_path: Path, prompt: str = "Find the price of Product 377 blue widget") -> tuple:
    transcript = tmp_path / "project" / "sess.jsonl"
    results = tmp_path / "project" / "sess" / "tool-results"
    results.mkdir(parents=True)
    entry = {"type": "user", "message": {"role": "user", "content": prompt}}
    transcript.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    return transcript, results


def _persisted_event(tmp_path: Path, full: str, saved: Path | None, transcript: Path) -> dict:
    response = {"stdout": full[:30000], "stderr": "", "interrupted": False}
    if saved is not None:
        response = {**response, "persistedOutputPath": str(saved),
                    "persistedOutputSize": len(full)}  # fmt: skip
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "playwright-cli -s=x snapshot"},
        "tool_response": response,
        "tool_use_id": "toolu_cli",
        "session_id": "sess",
        "cwd": str(tmp_path),
        "transcript_path": str(transcript),
    }


def _full_page() -> str:
    return BANNER + PAGE + _big_snapshot(400) + "```\n"


async def test_a_saved_bash_output_is_ranked_whole_and_shown_within_the_preview(
    tmp_path, monkeypatch
):
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    transcript, results = _session(tmp_path)
    full = _full_page()
    assert len(full) > 30000 and "Product 377" not in full[:30000], "the answer is past the cut"
    saved = results / "b1.txt"
    saved.write_text(full, encoding="utf-8")
    out = await browse_hook.post_tool_use(_persisted_event(tmp_path, full, saved, transcript),
                                          Squire())  # fmt: skip
    shown = out["hookSpecificOutput"]["updatedToolOutput"]["stdout"]
    assert len(shown) <= browse_hook.PREVIEW_CHARS, "Claude Code shows the model 2,000 characters"
    assert "Product 377 blue widget" in shown, "ranked over the whole page, not the prefix"
    assert "Update available" not in shown and "/url:" not in shown
    archived = {p.name: p.read_text(encoding="utf-8") for p in (tmp_path / "archive").rglob("*")
                if p.is_file()}  # fmt: skip
    assert full in archived.values(), "the archive holds the whole output"
    pruned = [text for name, text in archived.items() if name.endswith("-pruned.txt")]
    assert pruned and "Product 377 blue widget" in pruned[0] and len(pruned[0]) < len(full) / 3
    assert "Read" in shown and "Grep" in shown, "both ways back are named"


async def test_a_saved_output_it_cannot_read_passes_through(tmp_path, monkeypatch):
    """Without the whole output the hook would rank and archive a 30,000-character prefix."""
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    transcript, _ = _session(tmp_path)
    full = _full_page()
    missing = _persisted_event(tmp_path, full, tmp_path / "project" / "sess" / "tool-results" /
                               "gone.txt", transcript)  # fmt: skip
    assert await browse_hook.post_tool_use(missing, Squire()) == {}
    outside = tmp_path / "elsewhere" / "tool-results" / "b2.txt"
    outside.parent.mkdir(parents=True)
    outside.write_text(full, encoding="utf-8")
    assert (
        await browse_hook.post_tool_use(
            _persisted_event(tmp_path, full, outside, transcript), Squire()
        )  # fmt: skip
        == {}
    ), "only this session's own tool-results folder is read"


async def test_an_output_under_the_limit_is_pruned_as_before(tmp_path, monkeypatch):
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    transcript, _ = _session(tmp_path, "Find the price of Product 7 blue widget")
    full = PAGE + _big_snapshot(150) + "```\n"
    assert len(full) < 30000
    out = await browse_hook.post_tool_use(_persisted_event(tmp_path, full, None, transcript),
                                          Squire())  # fmt: skip
    shown = out["hookSpecificOutput"]["updatedToolOutput"]["stdout"]
    assert shown.startswith(PAGE) and "# sanchopanza kept" in shown


def test_the_preview_keeps_the_lines_that_carry_content():
    from sanchopanza.harness.browse_hook import preview_lines

    pruned = (
        "- generic [ref=e1]:\n  - main [ref=e2]:\n    - table [ref=e3]:\n"
        '      - rowheader "Currency" [ref=e4]\n      - cell [ref=e5]:\n'
        '        - link "Euro" [ref=e6] [cursor=pointer]:\n          - /url: /wiki/Euro\n'
        "        - text: (EUR)\n"
    )
    lines = preview_lines(pruned)
    assert lines == ['rowheader "Currency" [ref=e4]', 'link "Euro" [ref=e6]', "text: (EUR)"]


def test_the_ranked_elements_come_before_the_text_that_fills_the_preview():
    from sanchopanza.harness.browse_hook import preview_lines

    pruned = '- paragraph [ref=t1]: Price 1\n- paragraph [ref=t2]: Price 2\n- link "Buy" [ref=b9]\n'
    assert preview_lines(pruned, frozenset({"b9"}))[0] == 'link "Buy" [ref=b9]'


async def test_a_question_about_position_on_a_saved_output_gets_the_page_in_its_order(
    tmp_path, monkeypatch
):
    """Passing through a saved output shows the model its first 2,000 characters: the banner and
    the navigation (T6, W12, Y5, Y9). The page's content lines in their own order keep "the
    first" first and skip what is not content."""
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    transcript, results = _session(tmp_path, "Report the title of the first product listed")
    nav = "".join(f'  - link "Menu entry {i}" [ref=n{i}] [cursor=pointer]:\n    - /url: /m{i}\n'
                  for i in range(300))  # fmt: skip
    page = "- generic [ref=e0]:\n- navigation [ref=nav]:\n" + nav + "- main [ref=m]:\n"
    body = "".join(f'  - link "Product {i}" [ref=p{i}] [cursor=pointer]:\n' for i in range(400))
    full = BANNER + PAGE + page + body + "```\n"
    saved = results / "b3.txt"
    saved.write_text(full, encoding="utf-8")
    out = await browse_hook.post_tool_use(_persisted_event(tmp_path, full, saved, transcript),
                                          Squire())  # fmt: skip
    shown = out["hookSpecificOutput"]["updatedToolOutput"]["stdout"]
    assert len(shown) <= browse_hook.PREVIEW_CHARS
    assert 'link "Product 0" [ref=p0]' in shown and "Menu entry" not in shown
    assert shown.index("Product 0") < shown.index("Product 1"), "the page's own order"
    assert "Grep" in shown


async def test_a_question_about_position_under_the_limit_still_passes_through(tmp_path):
    from sanchopanza.harness import browse_hook

    transcript, _ = _session(tmp_path, "Report the title of the first product listed")
    full = PAGE + _big_snapshot(150) + "```\n"
    event = _persisted_event(tmp_path, full, None, transcript)
    assert await browse_hook.post_tool_use(event, Squire()) == {}


def test_the_position_preview_reads_from_the_end_for_the_last_and_from_the_table_it_names():
    from sanchopanza.harness.browse_hook import position_lines

    body = (
        "- main [ref=m]:\n  - paragraph [ref=p]: A long introduction that fills the space\n"
        "  - generic [ref=g]: \n  - table [ref=t]:\n"
        + "".join(f'    - row "Item {i}" [ref=r{i}]\n' for i in range(5))
    )
    first_in_table = position_lines(body, "Which item is listed first in the table?")
    assert first_in_table[0] == 'row "Item 0" [ref=r0]', "from the table the question names"
    last = position_lines(body, "Report the last item listed")
    assert last[-1] == 'row "Item 4" [ref=r4]' and "introduction" in last[0]
    assert not any("" in line for line in last), "a line with no letter or digit is noise"


async def test_the_agents_own_search_saved_to_a_file_comes_back_in_page_order(
    tmp_path, monkeypatch
):
    """Y2, Y7: a `find` past 30,000 characters passed through and the model saw 2,000 raw
    characters. Its matches in page order, uncut, are what fits instead."""
    from sanchopanza.harness import browse_hook

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    transcript, results = _session(tmp_path)
    full = _full_page()
    saved = results / "b4.txt"
    saved.write_text(full, encoding="utf-8")
    event = _persisted_event(tmp_path, full, saved, transcript)
    event["tool_input"] = {"command": "playwright-cli -s=x find Product"}
    shown = (await browse_hook.post_tool_use(event, Squire()))["hookSpecificOutput"][
        "updatedToolOutput"
    ]["stdout"]
    assert len(shown) <= browse_hook.PREVIEW_CHARS and "page order" in shown
    assert shown.index("Product 0 blue") < shown.index("Product 1 blue")
    small = _persisted_event(tmp_path, full[:20000], None, transcript)
    small["tool_input"] = event["tool_input"]
    assert await browse_hook.post_tool_use(small, Squire()) == {}, "unsaved: never touched"


def test_position_needs_a_listing_word_and_reads_the_request_only():
    """Z2 (3l): "in which year was the first ascent" counted as a position, so the hook left
    the page uncut; and the agent's own step ("First I'll open the page") was read too."""
    from sanchopanza.harness.browse_hook import asks_for_position

    assert not asks_for_position(
        "Task: According to the infobox, in which year was the first ascent?"
    )
    assert asks_for_position(
        "Task: Open the quotes tagged 'humor' and report the author of the first one."
    )
    assert asks_for_position("Task: Which lake is listed first in the table?")
    step = "Task: What is the capital of France?\nAgent's step: First I'll open the page"
    assert not asks_for_position(step)
