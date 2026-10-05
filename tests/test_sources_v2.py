"""The sources hook, version 2 (`SANCHOPANZA_SOURCES_VERSION=2`): web calls counted in the
subagents too, no block once the session has spent most of its cap, and a block only on a
deterministic sign of a weak answer, with a request that never costs the answer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sanchopanza.harness import sources_hook, sources_v2
from sanchopanza.harness.sources_hook import REQUEST
from sanchopanza.harness.sources_v2 import REQUEST_V2

V2 = {"SANCHOPANZA_SOURCES_VERSION": "2"}
QUESTION = "Which city hosted the 1992 games? End with one line: ANSWER: <your answer>."
SONNET = "claude-sonnet-5"


def _usage(cache_read: int = 0, out: int = 10) -> dict[str, int]:
    return {"input_tokens": 100, "cache_read_input_tokens": cache_read, "output_tokens": out}


def _entries(
    tools: list[tuple[str, str]],
    final: str,
    question: str = QUESTION,
    side: bool = False,
    usage: dict[str, int] | None = None,
) -> list[dict]:
    """A transcript: the question, one assistant call per (tool, result), the final text."""
    out: list[dict] = []
    if not side:
        out.append({"type": "user", "message": {"role": "user", "content": question}})
    for n, (tool, result) in enumerate(tools):
        use = {"type": "tool_use", "id": f"{'s' if side else 'm'}{n}", "name": tool, "input": {}}
        message = {"id": f"msg-{side}-{n}", "role": "assistant", "model": SONNET,
                   "content": [use], "usage": usage or _usage()}  # fmt: skip
        res = {"type": "tool_result", "tool_use_id": use["id"], "content": result}
        out.append({"type": "assistant", "isSidechain": side, "message": message})
        out.append({"type": "user", "isSidechain": side,
                    "message": {"role": "user", "content": [res]}})  # fmt: skip
    text = [{"type": "text", "text": final}]
    final_msg = {"id": f"msg-{side}-final", "role": "assistant", "model": SONNET,
                 "content": text, "usage": usage or _usage()}  # fmt: skip
    out.append({"type": "assistant", "isSidechain": side, "message": final_msg})
    return out


def _write(path: Path, entries: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return path


def _session(tmp_path: Path, tools, final: str, **kw) -> Path:
    return _write(tmp_path / "proj" / "sid-1.jsonl", _entries(tools, final, **kw))


def _subagent(main: Path, tools, final: str) -> Path:
    folder = main.with_suffix("") / "subagents"
    return _write(folder / "agent-a1.jsonl", _entries(tools, final, side=True))


def _event(transcript: Path, **extra: object) -> dict[str, object]:
    return {"session_id": "sid-1", "transcript_path": str(transcript),
            "hook_event_name": "Stop", "stop_hook_active": False, **extra}  # fmt: skip


@pytest.fixture(autouse=True)
def _state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    monkeypatch.setattr(sources_hook, "state_dir", lambda: state)
    for name in ("SOURCES", "SOURCES_VERSION", "SOURCES_CAP_USD"):
        monkeypatch.delenv(f"SANCHOPANZA_{name}", raising=False)
        monkeypatch.delenv(f"SANCHO_{name}", raising=False)
    return state


SEARCH = ("WebSearch", "Barcelona hosted the 1992 Summer Olympics.")


# --- the version switch -------------------------------------------------------------------------


def test_version_1_is_the_default_and_unchanged(tmp_path: Path) -> None:
    transcript = _session(tmp_path, [SEARCH], "ANSWER: Barcelona")
    assert sources_hook.handle(_event(transcript), env={}) == {"decision": "block",
                                                                "reason": REQUEST}  # fmt: skip


def test_v2_lets_a_clean_answer_stop(tmp_path: Path, _state: Path) -> None:
    transcript = _session(tmp_path, [SEARCH], "Found it.\nANSWER: Barcelona")
    assert sources_hook.handle(_event(transcript), env=V2) is None
    assert not list(_state.glob("sources-*.json"))


# --- the signals --------------------------------------------------------------------------------


def test_v2_blocks_on_a_number_no_tool_result_shows(tmp_path: Path) -> None:
    tools = [("WebSearch", "Population 1,200 in 1990 and 1,500 in 2000.")]
    transcript = _session(tmp_path, tools, "The growth is the difference.\nANSWER: 300")
    out = sources_hook.handle(_event(transcript), env=V2)
    assert out is not None and out["decision"] == "block"
    assert out["reason"].startswith(REQUEST_V2)
    assert "number" in out["reason"]


def test_v2_a_number_read_in_a_result_or_the_question_is_not_a_sign(tmp_path: Path) -> None:
    tools = [("WebSearch", "Its population was 1,500 in 2000.")]
    read = _session(tmp_path, tools, "ANSWER: 1500")
    assert sources_hook.handle(_event(read), env=V2) is None
    asked = _session(tmp_path, [("WebSearch", "Barcelona hosted the games.")], "ANSWER: 1992")
    assert sources_hook.handle(_event(asked), env=V2) is None


def test_v2_ordinals_and_separators_are_read_as_numbers() -> None:
    assert sources_v2.numbers("the 38th holder, 1,234 votes, 12.50 %") == {38.0, 1234.0, 12.5}


@pytest.mark.parametrize(
    "final",
    [
        "It is likely Barcelona.\nANSWER: Barcelona",
        "I could not confirm the second condition.\nANSWER: Barcelona",
        "The sources are conflicting.\nANSWER: Barcelona",
        "Assuming the earlier list.\nANSWER: Barcelona",
        "ANSWER: approximately Barcelona",
    ],
)
def test_v2_blocks_on_doubt_words(tmp_path: Path, final: str) -> None:
    transcript = _session(tmp_path, [SEARCH], final)
    out = sources_hook.handle(_event(transcript), env=V2)
    assert out is not None and "doubt" in out["reason"]


def test_v2_blocks_when_the_answer_line_asked_for_is_missing(tmp_path: Path) -> None:
    transcript = _session(tmp_path, [SEARCH], "The city is Barcelona.")
    out = sources_hook.handle(_event(transcript), env=V2)
    assert out is not None and "ANSWER line" in out["reason"]
    unasked = _session(tmp_path, [SEARCH], "The city is Barcelona.", question="Which city?")
    sources_hook.state_dir().joinpath("sources-sid-1.json").unlink()
    assert sources_hook.handle(_event(unasked), env=V2) is None


def test_v2_reads_the_last_assistant_message_from_the_event_first(tmp_path: Path) -> None:
    transcript = _session(tmp_path, [SEARCH], "ANSWER: Barcelona")
    event = _event(transcript, last_assistant_message="Probably Barcelona.\nANSWER: Barcelona")
    out = sources_hook.handle(event, env=V2)
    assert out is not None and "doubt" in out["reason"]


def test_v2_blocks_once(tmp_path: Path) -> None:
    transcript = _session(tmp_path, [SEARCH], "It is likely Barcelona.\nANSWER: Barcelona")
    assert sources_hook.handle(_event(transcript), env=V2) is not None
    assert sources_hook.handle(_event(transcript), env=V2) is None


# --- subagents ----------------------------------------------------------------------------------


def test_v2_counts_web_calls_made_by_a_subagent(tmp_path: Path) -> None:
    main = _session(tmp_path, [("Agent", "The city is Barcelona.")], "Probably.\nANSWER: Barcelona")
    assert sources_hook.handle(_event(main), env=V2) is None  # no web call anywhere yet
    _subagent(main, [SEARCH], "Barcelona.")
    out = sources_hook.handle(_event(main), env=V2)
    assert out is not None and out["decision"] == "block"


def test_v2_a_number_a_subagent_read_is_not_a_sign(tmp_path: Path) -> None:
    main = _session(tmp_path, [("Agent", "Done.")], "ANSWER: 1500")
    _subagent(main, [("WebFetch", "Population: 1,500.")], "1500")
    assert sources_hook.handle(_event(main), env=V2) is None


def test_v2_a_number_only_a_subagent_report_states_is_a_sign(tmp_path: Path) -> None:
    main = _session(tmp_path, [("Agent", "The total is 2700.")], "ANSWER: 2700")
    _subagent(main, [("WebFetch", "1,200 and 1,500.")], "The total is 2700.")
    assert sources_hook.handle(_event(main), env=V2) is not None


# --- the cap ------------------------------------------------------------------------------------


def test_spent_prices_each_call_once_and_adds_the_web_readers(tmp_path: Path) -> None:
    usage = {"input_tokens": 1_000_000, "cache_read_input_tokens": 0, "output_tokens": 0}
    transcript = _session(tmp_path, [SEARCH, SEARCH], "ANSWER: Barcelona", usage=usage)
    lines = transcript.read_text(encoding="utf-8").splitlines()
    # Claude Code writes one entry per block: the same message id twice is one call.
    _write(transcript, [json.loads(x) for x in [*lines, lines[1]]])
    spent = sources_v2.spent_usd(transcript)
    assert spent == pytest.approx(3 * 2.0 + 2 * sources_v2.WEB_CALL_USD)


def test_v2_stands_aside_past_60_percent_of_the_cap(tmp_path: Path) -> None:
    usage = {"input_tokens": 100_000, "cache_read_input_tokens": 0, "output_tokens": 0}
    transcript = _session(tmp_path, [SEARCH], "Likely.\nANSWER: Barcelona", usage=usage)
    spent = sources_v2.spent_usd(transcript)  # 2 calls x 0.2 + one search reader
    over = {**V2, "SANCHOPANZA_SOURCES_CAP_USD": f"{spent / 0.61:.4f}"}
    under = {**V2, "SANCHOPANZA_SOURCES_CAP_USD": f"{spent / 0.59:.4f}"}
    assert sources_hook.handle(_event(transcript), env=over) is None
    assert sources_hook.handle(_event(transcript), env=under) is not None


def test_v2_without_a_cap_the_spend_is_not_checked(tmp_path: Path) -> None:
    usage = {"input_tokens": 10_000_000, "cache_read_input_tokens": 0, "output_tokens": 0}
    transcript = _session(tmp_path, [SEARCH], "Likely.\nANSWER: Barcelona", usage=usage)
    assert sources_hook.handle(_event(transcript), env=V2) is not None


# --- the request --------------------------------------------------------------------------------


def test_the_v2_request_keeps_the_answer_and_asks_about_the_unstated_step() -> None:
    lowered = REQUEST_V2.lower()
    assert "never withdraw" in lowered
    assert "calculated" in lowered and "counted" in lowered and "conflicting" in lowered
    assert "open" in lowered and "ANSWER" in REQUEST_V2
    assert len(REQUEST_V2) < 500
