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
