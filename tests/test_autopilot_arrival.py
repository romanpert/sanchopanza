"""The arrival cut: splitting, the tournament over blocks, assembly, fail-open. No network."""

from __future__ import annotations

import re

import pytest

from sanchopanza import Squire, Thresholds
from sanchopanza.context import arrival, blocks
from tests.context_helpers import BrokenDecider, ScriptedDecider

CODE = "".join(
    f"def function_{i}(x):\n    value = x * {i}\n    return value + {i}\n\n" for i in range(120)
)
LOG = "".join(f"2026-09-28 12:00:{i % 60:02d} INFO step {i} ok\n" for i in range(400))
PROSE = "\n\n".join(
    " ".join(f"Paragraph {p} sentence {s} talks about topic{p}." for s in range(6))
    for p in range(40)
)


def _pages_answer(wanted: set[int], *, high: float = 0.9, low: float = 0.05):
    """Keep blocks whose text mentions one of `wanted` markers; everything else low."""

    def answer(point, key, state):
        if point == "triage_pages":
            parts = re.split(r"(?m)^(P\d\d)\| ", state["pages"])
            line = dict(zip(parts[1::2], parts[2::2], strict=True)).get(key, "")
            return (
                high
                if any(f"function_{w}(" in line or f"topic{w}." in line for w in wanted)
                else low
            )
        if point == "select_sentences":
            return 0.9 if key == "S1" else 0.01
        return None

    return answer


def _squire(answer=None, decider=None, **t):
    decider = decider or ScriptedDecider(answer)
    return Squire(decider, thresholds=Thresholds().with_(**t) if t else Thresholds())


# --- blocks ---------------------------------------------------------------------------------


@pytest.mark.parametrize("text,kind", [(CODE, "code"), (LOG, "log"), (PROSE, "prose")])
def test_blocks_tile_the_text_exactly(text, kind):
    found = blocks.split(text, kind)
    assert found[0].start == 0 and found[-1].end == len(text)
    assert all(a.end == b.start for a, b in zip(found, found[1:], strict=False))
    assert "".join(b.of(text) for b in found) == text
    assert max(b.end - b.start for b in found) <= blocks.TARGET * 2


def test_a_long_line_is_split_and_blocks_stay_bounded():
    text = "word " * 5_000  # no newline at all
    found = blocks.split(text, "prose")
    assert len(found) > 5
    assert "".join(b.of(text) for b in found) == text


def test_code_starts_blocks_at_top_level_definitions():
    found = blocks.split(CODE, "code")
    starts = [CODE[b.start : b.end].lstrip().split("\n", 1)[0] for b in found]
    assert all(s.startswith("def ") for s in starts)


def test_too_many_blocks_grow_the_target():
    text = "x\n" * 400_000
    assert len(blocks.split(text, "log", max_blocks=50)) <= 51


@pytest.mark.parametrize(
    "tool,inp,kind",
    [
        ("Read", {"file_path": "C:\\p\\app.py"}, "code"),
        ("Read", {"file_path": "/p/README.md"}, "prose"),
        ("Bash", {"command": "pytest"}, "log"),
        ("Grep", {"pattern": "x"}, "log"),
        ("WebFetch", {"url": "https://x.test"}, "prose"),
    ],
)
def test_kind_of(tool, inp, kind):
    assert blocks.kind_of(tool, inp, "text") == kind


def test_an_mcp_listing_reads_as_log():
    assert blocks.kind_of("mcp__x__list", {}, "a\n" * 50) == "log"


def test_assembly_keeps_order_and_marks_omitted_runs_with_original_lines():
    found = blocks.split(LOG, "log")
    kept = [i in (0, 5) for i in range(len(found))]
    out = blocks.assemble(LOG, found, kept, line_offset=100)
    assert out.startswith(found[0].of(LOG))
    assert out.index(found[0].of(LOG)) < out.index(found[5].of(LOG))
    markers = re.findall(r"\[\.\.\. sanchopanza omitted lines (\d+)-(\d+)", out)
    assert len(markers) == 2  # blocks 1-4, then 6-end
    first = found[1].first_line + 100
    assert int(markers[0][0]) == first


def test_partial_blocks_keep_only_chosen_sentences_in_order():
    found = blocks.split(PROSE, "prose")
    spans = blocks.sentence_spans(PROSE, found[0])
    assert len(spans) >= 6
    out = blocks.assemble(PROSE, found[:1], [[spans[0], spans[3]]])
    assert PROSE[spans[0][0] : spans[0][1]].strip() in out
    assert PROSE[spans[3][0] : spans[3][1]].strip() in out
    assert PROSE[spans[1][0] : spans[1][1]].strip() not in out
    assert out.index("sentence 0") < out.index("sentence 3")
    assert blocks.SENTENCE_GAP.strip() in out


# --- the cut --------------------------------------------------------------------------------


async def test_under_the_threshold_nothing_is_asked():
    decider = ScriptedDecider(lambda *a: 0.9)
    result = await arrival.cut(Squire(decider), "short", tool="Bash", purpose="p")
    assert result.text is None and "under" in result.reason
    assert decider.calls == []


async def test_a_failure_passes_under_the_error_threshold():
    text = "Traceback (most recent call last):\n" + "  frame\n" * 1_500
    decider = ScriptedDecider(lambda *a: 0.01)
    result = await arrival.cut(Squire(decider), text, tool="Bash", purpose="p")
    assert result.text is None and "failure" in result.reason
    assert decider.calls == []


async def test_code_keeps_the_relevant_definitions_literally_and_in_order():
    squire = _squire(_pages_answer({7, 90}))
    result = await arrival.cut(
        squire, CODE, tool="Read", tool_input={"file_path": "/p/app.py"}, purpose="fix function_7"
    )
    assert result.text is not None
    assert "def function_7(x):\n    value = x * 7\n    return value + 7\n" in result.text
    assert "def function_90(x):" in result.text
    assert result.text.index("function_7(") < result.text.index("function_90(")
    assert "def function_50(" not in result.text
    assert "sanchopanza omitted" in result.text
    assert len(result.text) < len(CODE) * 0.3


async def test_code_is_never_cut_below_the_block():
    squire = _squire(_pages_answer({3}, high=0.99))
    result = await arrival.cut(squire, CODE, tool="Read", tool_input={}, purpose="p")
    assert result.text is not None
    assert all(point != "select_sentences" for point, *_ in squire._decider.calls)


async def test_prose_goes_to_sentences_only_above_the_paragraph_gate():
    squire = _squire(_pages_answer({2}, high=0.95))
    result = await arrival.cut(squire, PROSE, tool="WebFetch", purpose="topic2")
    points = [p for p, *_ in squire._decider.calls]
    assert "select_sentences" in points
    assert result.text is not None
    # window 2 around S1: sentences 0-2 of paragraph 2 kept, 4-5 cut
    assert "Paragraph 2 sentence 0" in result.text and "Paragraph 2 sentence 2" in result.text
    assert "Paragraph 2 sentence 5" not in result.text


async def test_a_kept_block_below_the_gate_is_kept_whole():
    squire = _squire(_pages_answer({2}, high=0.6))
    result = await arrival.cut(squire, PROSE, tool="WebFetch", purpose="topic2")
    assert "select_sentences" not in [p for p, *_ in squire._decider.calls]
    assert "Paragraph 2 sentence 5" in result.text


async def test_keeping_nothing_passes_the_whole_result():
    squire = _squire(lambda *a: 0.01)
    result = await arrival.cut(squire, CODE, tool="Read", purpose="p")
    assert result.text is None and "no block" in result.reason


async def test_an_outage_passes_the_whole_result():
    result = await arrival.cut(Squire(BrokenDecider()), CODE, tool="Read", purpose="p")
    assert result.text is None and "no answer from the decider" in result.reason


async def test_keeping_almost_everything_passes_the_whole_result():
    squire = _squire(lambda *a: 0.9)
    result = await arrival.cut(squire, CODE, tool="Read", purpose="p")
    assert result.text is None and "saves" in result.reason


async def test_secrets_never_reach_the_decider_but_reach_the_agent():
    secret = "sk-" + "A" * 30
    text = CODE.replace("value = x * 7", f"value = '{secret}'")
    squire = _squire(_pages_answer({7}))
    result = await arrival.cut(squire, text, tool="Read", purpose="function_7")
    assert all(secret not in repr(state) for _, state, _ in squire._decider.calls)
    assert secret in result.text


def test_purpose_names_the_task_the_step_and_the_call():
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "Fix the parser"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Reading parser.py"}]},
    ]
    purpose = arrival.purpose_of(messages, "Read", {"file_path": "/p/parser.py"})
    assert "Fix the parser" in purpose and "Reading parser.py" in purpose
    assert "/p/parser.py" in purpose and len(purpose) <= arrival.PURPOSE_LIMIT + 6
