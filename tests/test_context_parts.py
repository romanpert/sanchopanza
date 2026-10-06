# ruff: noqa: E501, F811
"""The guard's block split over several SessionStart hooks (`context.parts`, `guard-hook --part`).

Claude Code keeps each hook's context inline only up to 10,000 characters and joins the contexts
of an event's hooks, in the order they finish. No model, no network: the split is pure, and the
hook is driven through `main` with a scripted stdin.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path
from typing import Any

import pytest

from sanchopanza.context import guard, parts, structural
from sanchopanza.context.transcript import Call
from sanchopanza.harness import guard_hook
from sanchopanza.harness.generic import HarnessConfig
from sanchopanza.harness.install import GUARD_COMMAND, GUARD_HOOKS, apply, plan
from sanchopanza.harness.install_guard import guard_commands, is_guard_command

from .test_context_guard import _entry, _result, _use, env, write_session  # noqa: F401


def _call(cid: str, tool: str, result: str = "ok", *, msg: int = 0, **arguments: Any) -> Call:
    return Call(id=cid, tool=tool, input=arguments, result=result, is_error=False, use_msg=msg)


def _emit(i: int, lines: int = 40) -> str:
    return "\n".join(f"EMIT-{i:02d}-{n:02d}: " + "x" * 48 for n in range(lines))


def _history(emits: int = 20) -> tuple[list[Call], list[str]]:
    """Reads, edits and one-shot commands with unique output, well over one part."""
    history = [_call(f"r{i}", "Read", "\n".join(f"{n:6d}\tvalue_{i}_{n} = {n}" for n in range(1, 60)),
                     file_path=f"/w/pkg/mod{i}.py") for i in range(30)]  # fmt: skip
    history += [_call(f"e{i}", "Edit", f"updated mod{i}", file_path=f"/w/pkg/mod{i}.py",
                      old_string="a", new_string="b") for i in range(12)]  # fmt: skip
    history += [_call(f"b{i}", "Bash", _emit(i), command=f"python emit.py {i}")
                for i in range(emits)]  # fmt: skip
    return history, ["Refactor the package and keep every emitted code. " * 12]


def _contents(history: list[Call]) -> dict[int, str]:
    return {p: structural.content_of(c) for p, c in enumerate(history)}


# ---- the split -----------------------------------------------------------------------------------


def test_every_part_is_within_the_cap_and_names_itself():
    history, requests = _history()
    for cap in (3_000, 6_000, structural.INLINE_CHARS):
        split = parts.split_calls(history, requests, inline_chars=cap, parts=6)
        n = len(split.texts)
        assert 1 < n <= 6
        for i, text in enumerate(split.texts, start=1):
            assert structural.width(text) <= cap
            assert text.splitlines()[0] == parts.header(i, n)
            assert f"part {i} of {n}" in text.splitlines()[0]
            assert text.endswith(guard.CLOSING)


def test_each_kept_result_is_whole_in_exactly_one_part():
    history, requests = _history()
    split = parts.split_calls(history, requests, parts=6)
    contents = _contents(history)
    kept = {f.call for f in split.guard.facts}
    assert len(kept) == len(split.guard.facts)  # no result twice
    for p in kept:
        holding = [t for t in split.texts if contents[p] in t]
        assert len(holding) == 1, history[p].id
    emitted = [t.count("EMIT-") for t in split.texts]
    assert sum(emitted) == sum(contents[p].count("EMIT-") for p in kept)  # never cut in two


def test_the_split_carries_the_measured_budget_not_one_parts_worth():
    history, requests = _history()
    split = parts.split_calls(history, requests)  # defaults: 44,000 over 6 parts of 9,500
    carried = sum(structural.cost(f.source, f.line) for f in split.guard.facts)
    single = structural.build_from_calls(history, requests)
    assert carried <= structural.STRUCT_CHARS
    assert carried > 4 * sum(structural.cost(f.source, f.line) for f in single.facts)
    assert carried > 0.9 * structural.STRUCT_CHARS


def test_part_one_holds_the_rest_and_the_results_that_matter_most():
    history, requests = _history()
    split = parts.split_calls(history, requests, parts=6)
    first, later = split.texts[0], split.texts[1:]
    assert "Refactor the package" in first and "Work so far:" in first
    assert structural.POINTERS_HEADING in first
    for text in later:
        assert "Refactor the package" not in text and "Work so far:" not in text
        assert structural.POINTERS_HEADING not in text
    ranked, _ = structural.order(history)
    assert structural.content_of(history[ranked[0]]) in first  # the top of the order


def test_one_part_is_todays_block_and_no_cap_is_one_uncapped_part():
    history, requests = _history()
    single = guard.block(structural.build_from_calls(history, requests))
    assert parts.split_calls(history, requests, parts=1).texts == (single,)
    uncapped = parts.split_calls(history, requests, inline_chars=0, parts=6).texts
    assert len(uncapped) == 1 and len(uncapped[0]) > structural.INLINE_CHARS
    assert parts.header(1, 1) == guard.HEADER


def test_nothing_to_keep_gives_no_parts():
    assert parts.split_calls([], [], parts=6).texts == ()


def test_a_result_bigger_than_a_part_is_pointed_to_or_lost_never_cut():
    big = "\n".join(f"{n:6d}\tline {n} " + "y" * 60 for n in range(1, 400))
    history = [
        _call("read", "Read", big, file_path="/w/pkg/huge.py"),
        _call(
            "run", "Bash", "\n".join(f"OUT-{n}: " + "z" * 70 for n in range(300)), command="./once"
        ),
        _call("small", "Bash", "token: SMALL-1", command="./tiny"),
    ]
    split = parts.split_calls(history, [], parts=4)
    text = "\n".join(split.texts)
    assert "SMALL-1" in text
    assert "line 1 " not in text and "OUT-0:" not in text
    assert any("huge.py" in p for p in split.guard.pointers)  # can be read again
    assert not any("once" in p for p in split.guard.pointers)  # cannot: lost, as over the budget


def test_a_result_that_fits_only_an_empty_part_goes_alone():
    room = 9_500 - parts._results_overhead(3)
    filler = "w" * (room - 200)
    history = [_call("a", "Bash", "first " + filler, command="./a"),
               _call("b", "Bash", "second " + filler, command="./b")]  # fmt: skip
    split = parts.split_calls(history, [], parts=3)
    assert len(split.texts) == 3
    assert split.texts[0].count(filler) == 0  # part 1 is header and closing only
    assert [t.count(filler) for t in split.texts[1:]] == [1, 1]


def test_characters_outside_the_bmp_count_as_claude_code_counts_them():
    assert structural.width("a\U0001f600b") == 4
    history = [_call(f"m{i}", "Bash", "\U0001f600" * 1_500, command=f"./m{i}") for i in range(6)]
    for text in parts.split_calls(history, [], parts=6).texts:
        assert structural.width(text) <= structural.INLINE_CHARS


def test_default_parts_cover_the_budget_with_room_for_part_one():
    assert parts.default_parts(44_000, 9_500) == 6
    assert parts.default_parts() == parts.PARTS
    assert parts.default_parts(44_000, 0) == 1
    assert parts.default_parts(9_000, 9_500) == 2


# ---- the hook ------------------------------------------------------------------------------------


def _run(event: dict[str, Any], monkeypatch, argv: list[str] | None = None) -> str:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    assert guard_hook.main(argv) == 0
    return out.getvalue()


def _big(path: Path) -> Path:
    lines = [_entry({"role": "user", "content": "Run every emitter and keep their codes."})]
    for i in range(24):
        lines.append(_entry({"role": "assistant", "content": [
            _use(f"t{i}", "Bash", command=f"python emit.py {i}")]}))  # fmt: skip
        lines.append(_entry({"role": "user", "content": [_result(f"t{i}", _emit(i))]}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _pre(path: Path, session: str, monkeypatch, k: int = 6) -> str:
    return _run({"hook_event_name": "PreCompact", "trigger": "auto", "session_id": session,
                 "transcript_path": str(path)}, monkeypatch, ["--parts", str(k)])  # fmt: skip


def _part(path: Path, session: str, i: int, monkeypatch, k: int = 6) -> str:
    out = _run({"hook_event_name": "SessionStart", "source": "compact", "session_id": session,
                "transcript_path": str(path)}, monkeypatch, ["--part", str(i), "--parts", str(k)])  # fmt: skip
    return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""


def test_precompact_keeps_one_file_per_part_and_each_command_prints_its_own(env, monkeypatch):
    path = _big(env / "s.jsonl")
    assert _pre(path, "p", monkeypatch) == guard.INSTRUCTIONS_RESULTS
    files = sorted((env / "kept").glob("p.part*.json"))
    assert len(files) == 6 and not (env / "kept" / "p.json").exists()
    texts = [_part(path, "p", i, monkeypatch) for i in range(1, 7)]
    assert not list((env / "kept").glob("p.part*.json"))  # each removed by its own command
    present = [t for t in texts if t]
    n = len(present)
    assert n > 2 and texts[n:] == [""] * (6 - n)
    assert all(len(t) <= structural.INLINE_CHARS for t in present)
    joined = "\n".join(present)
    for i in range(24):  # every emitter whose output was kept is there once
        assert joined.count(f"EMIT-{i:02d}-00:") <= 1
    assert joined.count("EMIT-") > 3 * structural.INLINE_CHARS // 60
    log = [json.loads(x) for x in (env / "log.jsonl").read_text("utf-8").splitlines()]
    assert log[0]["event"] == "PreCompact" and log[0]["parts"] == n
    assert {r["origin"] for r in log[1:]} == {"kept"}


def test_the_parts_read_in_any_order_give_the_same_texts(env, monkeypatch):
    path = _big(env / "s.jsonl")
    _pre(path, "a", monkeypatch)
    forward = [_part(path, "a", i, monkeypatch) for i in range(1, 7)]
    _pre(path, "b", monkeypatch)
    backward = [_part(path, "b", i, monkeypatch) for i in range(6, 0, -1)][::-1]
    assert forward == backward


def test_missing_part_files_are_rebuilt_to_the_same_split(env, monkeypatch):
    path = _big(env / "s.jsonl")
    _pre(path, "k", monkeypatch)
    kept = [_part(path, "k", i, monkeypatch) for i in range(1, 7)]
    rebuilt = [_part(path, "none", i, monkeypatch) for i in range(1, 7)]  # no PreCompact ran
    assert rebuilt == kept
    log = [json.loads(x) for x in (env / "log.jsonl").read_text("utf-8").splitlines()]
    assert [r["origin"] for r in log[-6:]] == ["rebuilt"] * 6


def test_a_stale_part_is_rebuilt(env, monkeypatch):
    path = _big(env / "s.jsonl")
    _pre(path, "old", monkeypatch)
    one = env / "kept" / "old.part1.json"
    data = json.loads(one.read_text("utf-8"))
    one.write_text(json.dumps({**data, "text": "STALE", "at": time.time() - 7_200}), "utf-8")
    assert "STALE" not in _part(path, "old", 1, monkeypatch)


def test_a_single_block_kept_by_an_older_precompact_goes_in_part_one_only(env, monkeypatch):
    path = _big(env / "s.jsonl")
    _run({"hook_event_name": "PreCompact", "trigger": "auto", "session_id": "one",
          "transcript_path": str(path)}, monkeypatch)  # fmt: skip  # no --parts: one block
    single = json.loads((env / "kept" / "one.json").read_text("utf-8"))["block"]
    assert _part(path, "one", 2, monkeypatch) == ""
    assert _part(path, "one", 1, monkeypatch) == single
    assert _part(path, "one", 3, monkeypatch) == ""


def test_without_part_the_hook_attaches_the_single_capped_block(env, monkeypatch):
    path = _big(env / "s.jsonl")
    _run({"hook_event_name": "PreCompact", "trigger": "auto", "session_id": "s",
          "transcript_path": str(path)}, monkeypatch)  # fmt: skip
    out = _run({"hook_event_name": "SessionStart", "source": "compact", "session_id": "s",
                "transcript_path": str(path)}, monkeypatch)  # fmt: skip
    text = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert text.startswith(guard.HEADER) and len(text) <= structural.INLINE_CHARS


def test_a_part_after_another_session_start_adds_nothing(env, monkeypatch):
    path = _big(env / "s.jsonl")
    out = _run({"hook_event_name": "SessionStart", "source": "startup", "session_id": "x",
                "transcript_path": str(path)}, monkeypatch, ["--part", "1", "--parts", "6"])  # fmt: skip
    assert out == ""


@pytest.mark.parametrize("where", ["precompact", "rebuild"])
def test_any_error_while_splitting_gives_the_rule_in_part_one_only(env, monkeypatch, where):
    def broken(*_: Any, **__: Any) -> Any:
        raise KeyError("boom")

    monkeypatch.setattr("sanchopanza.context.parts.split", broken)
    path = write_session(env / "s.jsonl", compacted=False)
    if where == "precompact":
        assert _pre(path, "f", monkeypatch) == guard.INSTRUCTIONS  # the rule's note
    texts = [_part(path, "f", i, monkeypatch) for i in range(1, 7)]
    messages, _ = guard_hook.history_from_claude_code(str(path))
    assert texts[0] == guard.block(guard.build(messages))
    assert texts[1:] == [""] * 5
    log = [json.loads(x) for x in (env / "log.jsonl").read_text("utf-8").splitlines()]
    assert any(r["event"] == "error" and "KeyError" in r["error"] for r in log)


def test_part_and_parts_are_read_from_the_command_line():
    assert guard_hook._arguments(["--part", "3", "--parts", "6"]) == (3, 6)
    assert guard_hook._arguments(["--part"]) == (0, 0)
    assert guard_hook._arguments(["--part", "x", "--parts", "-2"]) == (0, 0)
    assert guard_hook._arguments(None) == (0, 0)


def test_the_cli_passes_part_and_parts_to_the_hook(monkeypatch):
    from sanchopanza import cli

    seen: list[tuple[int, int]] = []

    def fake(argv: Any = None, *, part: int = 0, parts: int = 0) -> int:
        seen.append((part, parts))
        return 0

    monkeypatch.setattr("sanchopanza.harness.guard_hook.main", fake)
    assert cli.main(["guard-hook", "--part", "2", "--parts", "6"]) == 0
    assert cli.main(["guard-hook"]) == 0
    assert seen == [(2, 6), (0, 0)]


# ---- install ------------------------------------------------------------------------------------


def _ours(hooks: dict[str, Any], event: str) -> list[dict[str, Any]]:
    return [e for e in hooks.get(event, []) if any(is_guard_command(h.get("command"))
                                                   for h in e["hooks"])]  # fmt: skip


def test_install_writes_one_command_per_part_and_takes_them_all_out(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"hooks": {"SessionStart": [
        {"matcher": "compact", "hooks": [{"type": "command", "command": "theirs"}]}]}}), "utf-8")  # fmt: skip
    apply(plan(path, HarnessConfig(), guard=True))
    hooks = json.loads(path.read_text("utf-8"))["hooks"]
    starts = _ours(hooks, "SessionStart")
    assert len(starts) == 1 and starts[0]["matcher"] == "compact"
    assert [h["command"] for h in starts[0]["hooks"]] == [
        f"{GUARD_COMMAND} --part {i} --parts {parts.PARTS}" for i in range(1, parts.PARTS + 1)]  # fmt: skip
    assert [h["command"] for e in _ours(hooks, "PreCompact") for h in e["hooks"]] == [
        f"{GUARD_COMMAND} --parts {parts.PARTS}"]  # fmt: skip
    assert [h["command"] for e in _ours(hooks, "PostToolUse") for h in e["hooks"]] == [
        GUARD_COMMAND
    ]
    assert hooks["SessionStart"][0]["hooks"][0]["command"] == "theirs"
    assert not plan(path, HarnessConfig(), guard=True).changed  # idempotent
    apply(plan(path, HarnessConfig(), guard=False))
    after = json.loads(path.read_text("utf-8"))
    assert GUARD_COMMAND not in json.dumps(after) and "theirs" in json.dumps(after)


def test_another_k_replaces_the_parts_and_one_is_the_single_block(tmp_path):
    path = tmp_path / "settings.json"
    apply(plan(path, HarnessConfig(), guard=True))
    apply(plan(path, HarnessConfig(), guard=True, guard_parts=3))
    hooks = json.loads(path.read_text("utf-8"))["hooks"]
    for event in GUARD_HOOKS:
        assert len(_ours(hooks, event)) == 1
    assert [h["command"] for h in _ours(hooks, "SessionStart")[0]["hooks"]] == list(
        guard_commands(3)["SessionStart"])  # fmt: skip
    apply(plan(path, HarnessConfig(), guard=True, guard_parts=1))
    hooks = json.loads(path.read_text("utf-8"))["hooks"]
    for event in GUARD_HOOKS:
        assert [h["command"] for e in _ours(hooks, event) for h in e["hooks"]] == [GUARD_COMMAND]


def test_an_older_single_command_install_is_upgraded_in_place(tmp_path):
    path = tmp_path / "settings.json"
    apply(plan(path, HarnessConfig(), guard=True, guard_parts=1))
    upgraded = plan(path, HarnessConfig(), guard=True)
    assert any(line == "SessionStart: compact (guard, 6 parts)" for line in upgraded.added)
    apply(upgraded)
    hooks = json.loads(path.read_text("utf-8"))["hooks"]
    assert len(_ours(hooks, "SessionStart")[0]["hooks"]) == parts.PARTS


def test_install_reads_the_budget_and_cap_the_hooks_will_read(tmp_path, monkeypatch):
    monkeypatch.setenv("SANCHOPANZA_GUARD_STRUCT_CHARS", "20000")
    path = tmp_path / "settings.json"
    apply(plan(path, HarnessConfig(), guard=True))
    hooks = json.loads(path.read_text("utf-8"))["hooks"]
    assert len(_ours(hooks, "SessionStart")[0]["hooks"]) == parts.default_parts(20_000, 9_500)
