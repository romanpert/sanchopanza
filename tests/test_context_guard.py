"""The compaction guard: what it carries past a native summary, and its Claude Code hooks.

No test here calls a paid provider: the decider arm is driven by a scripted fake.
"""

from __future__ import annotations

import asyncio
import io
import json
import random
from pathlib import Path
from typing import Any

import pytest

from sanchopanza.context import guard
from sanchopanza.context.transcript import Call, calls, history_from_claude_code
from sanchopanza.harness import guard_hook

MANIFEST = "\n".join(
    [f"SKU-{10000 + i}  east  qty= {i}  bin=B{i:02d}" for i in range(30)]
    + ["release token: RT-6Z4FRFLG7W"]
    + [f"SKU-{20000 + i}  west  qty= {i}  bin=C{i:02d}" for i in range(18)]
)
PROBE = "\n".join(
    [f"channel {i:02d}  gain=1.0{i % 10}  drift=0.00{i % 10}1  ok" for i in range(36)]
    + ["ProbeError: drift 0.0469 exceeds tolerance 0.0290 (code PRB-9015)"]
)


def _use(tid: str, name: str, **arguments: Any) -> dict[str, Any]:
    return {"type": "tool_use", "id": tid, "name": name, "input": arguments}


def _result(tid: str, text: str, *, error: bool = False) -> dict[str, Any]:
    return {"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": error}


def conversation() -> list[dict[str, Any]]:
    return [
        {"role": "user", "content": "Issue the release token, run the probe. Rule: every error "
                                    "message ends with [ref OPS-4471]."},  # fmt: skip
        {"role": "assistant",
         "content": [_use("t1", "Bash", command="python tools/issue_token.py")]},
        {"role": "user", "content": [_result("t1", MANIFEST)]},
        {"role": "assistant", "content": [_use("t2", "Read", file_path="pkg/a.py")]},
        {"role": "user", "content": [_result("t2", "A_SECRET_ID = 'ZX-1234'\n")]},
        {"role": "assistant", "content": [_use("t3", "Bash", command="python tools/probe.py")]},
        {"role": "user", "content": [_result("t3", PROBE, error=True)]},
        {"role": "assistant", "content": [_use("t4", "Bash", command="python -m pytest -q")]},
        {"role": "user",
         "content": [_result("t4", "FAILED tests/t.py::test_x - assert 1 == 2\n1 failed",
                             error=True)]},
        {"role": "assistant",
         "content": [_use("t5", "Edit", file_path="pkg/pricing.py", old_string="a",
                          new_string="b")]},
        {"role": "user", "content": [_result("t5", "updated")]},
        {"role": "assistant", "content": [_use("t6", "Bash", command="python -m pytest -q")]},
        {"role": "user", "content": [_result("t6", "5 passed in 0.10s")]},
        {"role": "assistant",
         "content": [_use("t7", "Bash", command="python tools/issue_token.py")]},
        {"role": "user",
         "content": [_result("t7", "error: the release token was already issued",
                             error=True)]},
    ]  # fmt: skip


def test_shape_groups_lines_printed_in_a_loop():
    assert guard.shape("SKU-20712 east qty= 95 bin=B27") == guard.shape(
        "SKU-53041 north qty= 628 bin=B34"
    )
    assert guard.shape("release token: RT-6Z4FRFLG7W") != guard.shape(
        "SKU-20712 east qty= 95 bin=B27"
    )


def test_the_single_line_beats_the_records_printed_in_a_loop():
    kept = [line for line, _ in guard.fact_lines(MANIFEST, limit=3)]
    assert "release token: RT-6Z4FRFLG7W" in kept


def test_lines_sharing_words_with_the_requests_come_first():
    rng = random.Random(7)  # a random hash per line: no two artifact lines share a shape
    rows = [f"artifact x-{i}.whl sha256={rng.getrandbits(64):016x} size={i}KB" for i in range(40)]
    text = "\n".join([*rows[:20], "release token: RT-QQ42ZZ", *rows[20:]])
    focus = guard.focus_of(["set the release token"])
    ranked = guard.ranked_lines(text, limit=4, focus=focus)
    assert ("release token: RT-QQ42ZZ", False, 0) in ranked  # first priority with the focus
    plain = guard.ranked_lines(text, limit=4)
    assert ("release token: RT-QQ42ZZ", False, 0) not in plain


def test_error_lines_come_first_and_the_output_order_is_kept():
    kept = guard.fact_lines(PROBE, limit=2)
    assert kept[-1] == ("ProbeError: drift 0.0469 exceeds tolerance 0.0290 (code PRB-9015)", True)


def test_readable_tools_are_not_at_risk():
    assert not guard.at_risk(Call(id="r", tool="Read", result="X-1"))
    assert guard.at_risk(Call(id="b", tool="Bash", result="X-1"))
    assert not guard.at_risk(Call(id="m", tool="mcp__web__fetch", result="X-1"))  # web is opt-in
    assert guard.at_risk(Call(id="m", tool="mcp__web__fetch", result="X-1"), web=True)
    assert not guard.at_risk(Call(id="w", tool="WebFetch", result="X-1"))
    assert not guard.at_risk(Call(id="e", tool="Bash", result="   "))


def test_a_rerun_that_failed_keeps_the_first_good_run():
    kept = [c.id for _, c in guard.latest_only(calls(conversation()))]
    assert "t1" in kept and "t7" in kept  # the one-shot tool refused its second run
    assert "t4" not in kept and "t6" in kept  # the test run before the fix is stale


def test_the_guard_carries_the_one_shot_values_the_rule_and_the_trail():
    g = guard.build(conversation())
    text = guard.block(g)
    assert "RT-6Z4FRFLG7W" in text and "PRB-9015" in text and "0.0290" in text
    assert "ZX-1234" not in text  # a Read: it can be read again
    assert "[ref OPS-4471]" in text  # the request, verbatim
    assert "changed: pkg/pricing.py" in text
    assert "last test run: $ python -m pytest -q -> 5 passed in 0.10s" in text
    assert "assert 1 == 2" not in text  # the stale failure is gone
    assert text.startswith(guard.HEADER)
    assert guard.instructions(g) == guard.INSTRUCTIONS


def test_the_budget_is_respected_and_errors_win_it():
    many = conversation() + [
        {"role": "assistant",
         "content": [_use(f"x{i}", "Bash", command=f"echo {i}")]} if k == 0 else
        {"role": "user", "content": [_result(f"x{i}", f"value V-{i:04d}A\n" * 3)]}
        for i in range(40) for k in (0, 1)
    ]  # fmt: skip
    g = guard.build(many, facts_chars=600)
    used = sum(len(f.line) + 4 for f in g.facts) + sum(
        len(s) + 2 for s in {f.source for f in g.facts}
    )
    assert used <= 600
    assert any("PRB-9015" in f.line for f in g.facts)


def test_nothing_to_add_means_no_block_and_no_instructions():
    g = guard.build([{"role": "user", "content": [_result("z", "x")]}])
    assert guard.block(g) == "" and guard.instructions(g) == ""


def test_same_command_compares_tokens_not_spacing():
    a = Call(id="a", tool="Bash", input={"command": "python  tools/probe.py"})
    b = Call(id="b", tool="Bash", input={"command": "python tools/probe.py"})
    c = Call(id="c", tool="Bash", input={"command": "python tools/other.py"})
    assert guard.same_command(a, b) and not guard.same_command(a, c)


class FakeSquire:
    def __init__(self, verdicts: list[tuple[bool, float | None]] | Exception) -> None:
        self.verdicts = verdicts
        self.asked: list[tuple[str, list[tuple[str, str]]]] = []

    async def triage_many(self, *, purpose: str, pages: list[tuple[str, str]]):
        self.asked.append((purpose, pages))
        if isinstance(self.verdicts, Exception):
            raise self.verdicts
        return self.verdicts[: len(pages)]


def test_the_decider_is_not_asked_when_everything_fits():
    squire = FakeSquire([])
    g = asyncio.run(guard.build_with_decider(squire, conversation()))
    assert squire.asked == [] and g.chooser == "all"


def test_the_decider_ranks_commands_when_they_do_not_fit():
    facts = guard.candidates(calls(conversation()))
    order = sorted({f.call for f in facts})
    token_call = next(f.call for f in facts if "RT-6Z4" in f.line)
    squire = FakeSquire([(c == token_call, 0.9 if c == token_call else 0.1) for c in order])
    kept, chooser = asyncio.run(guard.choose_by_decider(squire, facts, "set the token", budget=120))
    assert chooser == "decider"
    assert any("RT-6Z4FRFLG7W" in f.line for f in kept)
    assert "set the token" in squire.asked[0][0]


def test_a_failing_decider_falls_back_to_the_rule():
    facts = guard.candidates(calls(conversation()))
    kept, chooser = asyncio.run(
        guard.choose_by_decider(FakeSquire(RuntimeError("down")), facts, "t", budget=120)
    )
    assert chooser.startswith("rule") and kept == guard.choose(facts, 120)


# ---- the transcript reader and the hooks ---------------------------------------------------


def _entry(message: dict[str, Any], **extra: Any) -> str:
    return json.dumps({"type": message["role"], "message": message, **extra})


def write_session(path: Path, *, compacted: bool) -> Path:
    lines = [_entry(m) for m in conversation()]
    if compacted:
        lines.append(json.dumps({"type": "system", "subtype": "compact_boundary"}))
        lines.append(
            _entry({"role": "user", "content": "Summary: work so far."}, isCompactSummary=True)
        )
        lines.append(_entry({"role": "assistant", "content": [
            _use("t9", "Bash", command="python tools/probe.py")]}))
        lines.append(_entry({"role": "user", "content": [
            _result("t9", "error: probe state already consumed", error=True)]}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_history_keeps_what_the_compaction_replaced_and_marks_where(tmp_path):
    messages, boundary = history_from_claude_code(
        write_session(tmp_path / "s.jsonl", compacted=True)
    )
    assert boundary == len(conversation())
    assert "Summary: work so far." not in json.dumps(messages)
    assert [c.id for c in calls(messages)][-1] == "t9"
    _, none = history_from_claude_code(write_session(tmp_path / "n.jsonl", compacted=False))
    assert none == 0


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SANCHOPANZA_GUARD_DIR", str(tmp_path / "kept"))
    monkeypatch.setenv("SANCHOPANZA_GUARD_LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.delenv("SANCHOPANZA_GUARD_CHOOSER", raising=False)
    return tmp_path


def _run(event: dict[str, Any], monkeypatch) -> str:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    assert guard_hook.main() == 0
    return out.getvalue()


def test_precompact_prints_the_note_and_the_session_start_attaches_the_block(env, monkeypatch):
    path = write_session(env / "s.jsonl", compacted=False)
    note = _run({"hook_event_name": "PreCompact", "trigger": "auto", "session_id": "abc",
                 "transcript_path": str(path)}, monkeypatch)  # fmt: skip
    assert note == guard.INSTRUCTIONS
    out = json.loads(_run({"hook_event_name": "SessionStart", "source": "compact",
                           "session_id": "abc",
                           "transcript_path": str(path)}, monkeypatch))  # fmt: skip
    context = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "RT-6Z4FRFLG7W" in context and "PRB-9015" in context
    assert not (env / "kept" / "abc.json").exists()  # used once
    log = [json.loads(x) for x in (env / "log.jsonl").read_text("utf-8").splitlines()]
    assert [r["event"] for r in log] == ["PreCompact", "SessionStart"]
    assert log[1]["origin"] == "kept"


def test_a_session_start_that_is_not_a_compaction_adds_nothing(env, monkeypatch):
    path = write_session(env / "s.jsonl", compacted=False)
    assert _run({"hook_event_name": "SessionStart", "source": "startup", "session_id": "abc",
                 "transcript_path": str(path)}, monkeypatch) == ""  # fmt: skip


def test_a_rerun_after_the_compaction_gets_the_earlier_output(env, monkeypatch):
    path = write_session(env / "s.jsonl", compacted=True)
    out = json.loads(_run({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                           "session_id": "abc",
                           "tool_input": {"command": "python  tools/probe.py"},
                           "transcript_path": str(path)}, monkeypatch))  # fmt: skip
    note = out["hookSpecificOutput"]["additionalContext"]
    assert "PRB-9015" in note and "already ran before the conversation was compacted" in note


def test_no_echo_without_a_compaction_or_for_a_new_command(env, monkeypatch):
    plain = write_session(env / "p.jsonl", compacted=False)
    event = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "python tools/probe.py"},
    }
    assert _run({**event, "transcript_path": str(plain)}, monkeypatch) == ""
    compacted = write_session(env / "c.jsonl", compacted=True)
    fresh = {**event, "tool_input": {"command": "ls"}, "transcript_path": str(compacted)}
    assert _run(fresh, monkeypatch) == ""


def test_any_failure_adds_nothing_and_says_why(env, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(
        {"hook_event_name": "PreCompact",
         "transcript_path": str(env / "missing.jsonl")})))  # fmt: skip
    assert guard_hook.main() == 0
    captured = capsys.readouterr()
    assert captured.out == "" and "sanchopanza guard: added nothing" in captured.err


# ---- install --guard -------------------------------------------------------------------------


def test_install_guard_wires_three_hooks_once_and_takes_them_out(tmp_path):
    from sanchopanza.harness.generic import HarnessConfig
    from sanchopanza.harness.install import GUARD_COMMAND, GUARD_HOOKS, apply, plan

    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"hooks": {"SessionStart": [
        {"matcher": "startup",
         "hooks": [{"type": "command", "command": "theirs"}]}]}}), "utf-8")  # fmt: skip
    wired = plan(path, HarnessConfig(), guard=True)
    apply(wired)
    hooks = json.loads(path.read_text("utf-8"))["hooks"]
    for event, matcher in GUARD_HOOKS.items():
        ours = [e for e in hooks[event] if e["hooks"][0]["command"] == GUARD_COMMAND]
        assert len(ours) == 1 and ours[0]["matcher"] == matcher
    assert hooks["SessionStart"][0]["hooks"][0]["command"] == "theirs"
    again = plan(path, HarnessConfig(), guard=True)
    assert not any("(guard)" in line for line in again.added + again.removed)
    apply(plan(path, HarnessConfig(), guard=False))
    after = json.loads(path.read_text("utf-8"))["hooks"]
    flat = json.dumps(after)
    assert GUARD_COMMAND not in flat and "theirs" in flat
