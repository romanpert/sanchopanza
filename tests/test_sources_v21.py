"""The sources hook, version 2.1: version 2 with two opt-in settings.
`SANCHOPANZA_SOURCES_SHOWN_WORK=1` quiets the number sign when the reply shows the arithmetic,
the arithmetic is right and every operand is a number some tool result (or the question) shows;
`SANCHOPANZA_SOURCES_CAP_SHARE` moves the share of the cap past which the hook stands aside.
Version 2 as measured is unchanged when neither is set."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sanchopanza.harness import sources_hook, sources_v2, sources_work

V2 = {"SANCHOPANZA_SOURCES_VERSION": "2"}
V21 = {**V2, "SANCHOPANZA_SOURCES_SHOWN_WORK": "1"}
QUESTION = "How many years apart were the two events? End with one line: ANSWER: <your answer>."
SONNET = "claude-sonnet-5"


def _entries(tools: list[tuple[str, str]], final: str, side: bool = False, usage=None) -> list:
    usage = usage or {"input_tokens": 100, "cache_read_input_tokens": 0, "output_tokens": 10}
    out: list[dict] = (
        [] if side else [{"type": "user", "message": {"role": "user", "content": QUESTION}}]
    )
    for n, (tool, result) in enumerate(tools):
        use = {"type": "tool_use", "id": f"{'s' if side else 'm'}{n}", "name": tool, "input": {}}
        message = {"id": f"msg-{side}-{n}", "role": "assistant", "model": SONNET,
                   "content": [use], "usage": usage}  # fmt: skip
        res = {"type": "tool_result", "tool_use_id": use["id"], "content": result}
        out.append({"type": "assistant", "isSidechain": side, "message": message})
        out.append({"type": "user", "isSidechain": side,
                    "message": {"role": "user", "content": [res]}})  # fmt: skip
    final_msg = {"id": f"msg-{side}-final", "role": "assistant", "model": SONNET,
                 "content": [{"type": "text", "text": final}], "usage": usage}  # fmt: skip
    out.append({"type": "assistant", "isSidechain": side, "message": final_msg})
    return out


def _write(path: Path, entries: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return path


def _session(tmp_path: Path, tools, final: str, **kw) -> Path:
    return _write(tmp_path / "proj" / "sid-1.jsonl", _entries(tools, final, **kw))


def _event(transcript: Path) -> dict[str, object]:
    return {"session_id": "sid-1", "transcript_path": str(transcript),
            "hook_event_name": "Stop", "stop_hook_active": False}  # fmt: skip


@pytest.fixture(autouse=True)
def _state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    monkeypatch.setattr(sources_hook, "state_dir", lambda: state)
    for name in ("SOURCES", "SOURCES_VERSION", "SOURCES_CAP_USD", "SOURCES_SHOWN_WORK",
                 "SOURCES_CAP_SHARE"):  # fmt: skip
        monkeypatch.delenv(f"SANCHOPANZA_{name}", raising=False)
        monkeypatch.delenv(f"SANCHO_{name}", raising=False)
    return state


PAGES = [("WebFetch", "He was born in 1919."), ("WebFetch", "It was built in 1926.")]
SHOWN = "Built 1926, born 1919.\n1926 - 1919 = **7 years**\nANSWER: 7 years"


# --- the arithmetic a reply shows ---------------------------------------------------------------


def test_equations_are_read_with_their_operands_result_and_check() -> None:
    found = sources_work.equations("Sum: 47 + 33 = **80**; 1,200 x 3 = 3,600; 10 / 4 = 4")
    assert [(e.operands, e.result, e.right) for e in found] == [
        ((47.0, 33.0), 80.0, True),
        ((1200.0, 3.0), 3600.0, True),
        ((10.0, 4.0), 4.0, False),
    ]


def test_unicode_minus_and_division_and_rounding_are_read() -> None:
    found = sources_work.equations("660 − 141 = 519. 352,152 ÷ 6 = 58,692. 103 ÷ 29 = 3.55173")
    assert [e.right for e in found] == [True, True, True]


def test_a_percentage_is_checked_against_the_ratio_times_100() -> None:
    (share,) = sources_work.equations("58,963,125 / 110,130,418 ≈ 53.5%")
    assert share.right and share.result == 53.5


def test_grounded_results_chain_through_shown_steps() -> None:
    text = "6 + 5 = 11. 0 + 4 = 4. Combined: 11 + 4 = **15**"
    assert sources_work.grounded(text, {0.0, 4.0, 5.0, 6.0}) == {11.0, 4.0, 15.0}
    assert sources_work.grounded(text, {0.0, 4.0, 6.0}) == {4.0}  # 5 is on no page


def test_wrong_arithmetic_grounds_nothing() -> None:
    assert sources_work.grounded("660 - 141 = 529", {660.0, 141.0}) == set()


# --- the number sign with the setting -----------------------------------------------------------


def test_v21_quiets_the_number_sign_when_the_shown_work_uses_page_numbers(tmp_path: Path) -> None:
    transcript = _session(tmp_path, PAGES, SHOWN)
    assert sources_hook.handle(_event(transcript), env=V21) is None


def test_v2_as_measured_still_blocks_the_same_reply(tmp_path: Path) -> None:
    transcript = _session(tmp_path, PAGES, SHOWN)
    out = sources_hook.handle(_event(transcript), env=V2)
    assert out is not None and "number" in out["reason"]


def test_v21_blocks_when_an_operand_is_on_no_page(tmp_path: Path) -> None:
    transcript = _session(tmp_path, PAGES[1:], SHOWN)
    out = sources_hook.handle(_event(transcript), env=V21)
    assert out is not None and "number" in out["reason"]


def test_v21_blocks_on_a_number_with_no_work_shown(tmp_path: Path) -> None:
    transcript = _session(tmp_path, PAGES, "They were 7 years apart.\nANSWER: 7 years")
    assert sources_hook.handle(_event(transcript), env=V21) is not None


def test_v21_an_operand_a_subagent_read_counts(tmp_path: Path) -> None:
    main = _session(tmp_path, [("Agent", "Done."), PAGES[1]], SHOWN)
    folder = main.with_suffix("") / "subagents"
    _write(folder / "agent-a1.jsonl", _entries([PAGES[0]], "1919", side=True))
    assert sources_hook.handle(_event(main), env=V21) is None


def test_v21_keeps_the_other_signs(tmp_path: Path) -> None:
    transcript = _session(tmp_path, PAGES, "Probably right.\n" + SHOWN)
    out = sources_hook.handle(_event(transcript), env=V21)
    assert out is not None and "doubt" in out["reason"] and "number" not in out["reason"]


def test_signs_takes_the_setting_and_defaults_to_v2() -> None:
    results = ["born in 1919", "built in 1926"]
    assert sources_v2.signs(QUESTION, SHOWN, results) == ["number"]
    assert sources_v2.signs(QUESTION, SHOWN, results, shown_work=True) == []


# --- the cap share ------------------------------------------------------------------------------


def _priced(tmp_path: Path) -> tuple[Path, float]:
    usage = {"input_tokens": 100_000, "cache_read_input_tokens": 0, "output_tokens": 0}
    transcript = _session(tmp_path, PAGES, "Likely.\nANSWER: 7", usage=usage)
    return transcript, sources_v2.spent_usd(transcript)


def test_cap_share_moves_where_the_hook_stands_aside(tmp_path: Path) -> None:
    transcript, spent = _priced(tmp_path)
    cap = {"SANCHOPANZA_SOURCES_CAP_USD": f"{spent / 0.7:.4f}"}  # spent is 70 % of the cap
    assert sources_hook.handle(_event(transcript), env={**V2, **cap}) is None  # 0.6 default
    wide = {**V2, **cap, "SANCHOPANZA_SOURCES_CAP_SHARE": "0.8"}
    assert sources_hook.handle(_event(transcript), env=wide) is not None


@pytest.mark.parametrize("value", ["", "abc", "0", "-1", "1.5"])
def test_a_bad_cap_share_falls_back_to_the_measured_one(value: str) -> None:
    assert sources_v2.cap_share({"SANCHOPANZA_SOURCES_CAP_SHARE": value}) == sources_v2.CAP_SHARE


def test_the_cap_share_and_shown_work_reach_what_the_hook_records(tmp_path: Path) -> None:
    transcript, _ = _priced(tmp_path)
    seen = sources_v2.assess(transcript, "", {**V21, "SANCHOPANZA_SOURCES_CAP_SHARE": "0.8"})
    assert seen["cap_share"] == 0.8 and seen["shown_work"] is True
