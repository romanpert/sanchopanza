"""The Claude Code CLI path: argv, environment, parsing, the ceiling and the cache, all offline.

No test here starts `claude`: the spawner is injected, so the suite stays free.
"""

from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from sanchopanza.contract import Truth
from sanchopanza.providers.claude_cli import (
    CeilingReached,
    ClaudeCLI,
    Session,
    SessionCache,
    build_argv,
    clean_env,
    parse_result,
)
from sanchopanza.providers.llm import LLMDecider


def _stdout(**overrides: object) -> bytes:
    body = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Paris",
        "total_cost_usd": 0.0019,
        "usage": {
            "input_tokens": 731,
            "output_tokens": 5,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
        "modelUsage": {"claude-haiku-4-5-20251001": {"costUSD": 0.0019}},
    }
    body.update(overrides)
    return json.dumps(body).encode()


class FakeSpawn:
    def __init__(self, stdout: bytes = b"", code: int = 0) -> None:
        self.stdout = stdout
        self.code = code
        self.calls: list[tuple[list[str], bytes, dict[str, str]]] = []

    async def __call__(
        self, argv: list[str], stdin: bytes, env: dict[str, str], cwd: str, timeout_s: float
    ) -> tuple[int, bytes, bytes]:
        self.calls.append((argv, stdin, env))
        return self.code, self.stdout, b""


def test_argv_isolates_the_session() -> None:
    argv = build_argv("claude", model="claude-haiku-4-5", system="S", max_budget_usd=0.05)
    assert argv[:2] == ["claude", "-p"]
    for flag in ("--no-session-persistence", "--strict-mcp-config"):
        assert flag in argv
    assert argv[argv.index("--model") + 1] == "claude-haiku-4-5"
    assert argv[argv.index("--system-prompt") + 1] == "S"
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--max-budget-usd") + 1] == "0.05"
    assert "--json-schema" not in argv


def test_argv_carries_a_schema_and_effort() -> None:
    schema = {"type": "object"}
    argv = build_argv(
        "claude", model="m", system="S", max_budget_usd=0.1, schema=schema, effort="low"
    )
    assert json.loads(argv[argv.index("--json-schema") + 1]) == schema
    assert argv[argv.index("--effort") + 1] == "low"


def test_env_never_carries_an_api_key_and_turns_thinking_off() -> None:
    env = clean_env(
        {
            "ANTHROPIC_API_KEY": "sk-x",
            "ANTHROPIC_AUTH_TOKEN": "t",
            "ANTHROPIC_BASE_URL": "http://llave",
            "PATH": "p",
        }
    )
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert "ANTHROPIC_BASE_URL" not in env
    assert env["PATH"] == "p"
    assert env["MAX_THINKING_TOKENS"] == "0"


def test_parse_reads_text_usage_and_list_cost() -> None:
    s = parse_result(_stdout(), model="claude-haiku-4-5")
    assert s.ok and s.text == "Paris"
    assert s.input_tokens == 731 and s.output_tokens == 5
    assert s.list_cost_usd == pytest.approx(0.0019)
    assert s.structured is None


def test_parse_prefers_structured_output() -> None:
    s = parse_result(_stdout(structured_output={"yes": True, "confidence": 0.9}), model="m")
    assert s.structured == {"yes": True, "confidence": 0.9}


def test_parse_marks_errors_and_garbage() -> None:
    assert not parse_result(_stdout(is_error=True, subtype="error_max_budget_usd"), "m").ok
    broken = parse_result(b"not json", model="m")
    assert not broken.ok and broken.reason == "unparseable output"


def test_a_short_prompt_goes_in_argv_last() -> None:
    # Measured: under concurrency the CLI gives up on stdin after 3 s ("Input must be
    # provided"), so a prompt that fits the Windows command line goes as the last argument.
    spawn = FakeSpawn(_stdout())
    cli = ClaudeCLI(model="claude-haiku-4-5", system="S", ceiling_usd=1.0, spawn=spawn)
    asyncio.run(cli.run("line one" + chr(10) + "line two"))
    argv, stdin, env = spawn.calls[0]
    assert argv[-1] == "line one" + chr(10) + "line two"
    assert stdin == b""
    assert "ANTHROPIC_API_KEY" not in env


def test_a_long_prompt_goes_on_stdin() -> None:
    spawn = FakeSpawn(_stdout())
    cli = ClaudeCLI(model="claude-haiku-4-5", system="S", ceiling_usd=1.0, spawn=spawn)
    asyncio.run(cli.run("a" * 50_000))
    argv, stdin, _ = spawn.calls[0]
    assert stdin == ("a" * 50_000).encode()
    assert all("a" * 100 not in part for part in argv)


def test_ceiling_refuses_before_spawning() -> None:
    spawn = FakeSpawn(_stdout(total_cost_usd=0.6))
    cli = ClaudeCLI(model="m", system="S", ceiling_usd=1.0, spawn=spawn)
    asyncio.run(cli.run("one"))
    asyncio.run(cli.run("two"))
    with pytest.raises(CeilingReached):
        asyncio.run(cli.run("three"))
    assert len(spawn.calls) == 2
    assert cli.spent_usd == pytest.approx(1.2)


def test_a_failed_exit_counts_as_no_answer() -> None:
    spawn = FakeSpawn(b"", code=1)
    cli = ClaudeCLI(model="m", system="S", ceiling_usd=1.0, spawn=spawn)
    s = asyncio.run(cli.run("x"))
    assert not s.ok and "exit 1" in s.reason


def test_cache_replays_without_spawning(tmp_path: pathlib.Path) -> None:
    cache = SessionCache(tmp_path / "cache.jsonl")
    spawn = FakeSpawn(_stdout())
    cli = ClaudeCLI(model="m", system="S", ceiling_usd=1.0, spawn=spawn, cache=cache)
    first = asyncio.run(cli.run("same"))
    again = ClaudeCLI(
        model="m", system="S", ceiling_usd=1.0, spawn=spawn, cache=SessionCache(cache.path)
    )
    second = asyncio.run(again.run("same"))
    assert len(spawn.calls) == 1
    assert second.text == first.text and second.cached
    assert again.spent_usd == 0.0


def test_cache_keys_on_model_system_schema_and_prompt(tmp_path: pathlib.Path) -> None:
    cache = SessionCache(tmp_path / "c.jsonl")
    spawn = FakeSpawn(_stdout())
    for model, system, prompt in (
        ("m", "S", "p"),
        ("n", "S", "p"),
        ("m", "T", "p"),
        ("m", "S", "q"),
    ):
        asyncio.run(
            ClaudeCLI(model=model, system=system, ceiling_usd=1.0, spawn=spawn, cache=cache).run(
                prompt
            )
        )
    assert len(spawn.calls) == 4


def test_errors_are_not_cached(tmp_path: pathlib.Path) -> None:
    cache = SessionCache(tmp_path / "c.jsonl")
    spawn = FakeSpawn(b"", code=1)
    cli = ClaudeCLI(model="m", system="S", ceiling_usd=1.0, spawn=spawn, cache=cache)
    asyncio.run(cli.run("x"))
    asyncio.run(cli.run("x"))
    assert len(spawn.calls) == 2


def test_completer_feeds_the_llm_decider() -> None:
    spawn = FakeSpawn(_stdout(structured_output={"ok": True, "confidence": 0.8}))
    cli = ClaudeCLI(model="m", system="ignored", ceiling_usd=1.0, spawn=spawn)
    decider = LLMDecider(cli.completer(), model="claude-cli:m")
    decision = asyncio.run(decider.decide("p", {"x": 1}, {"ok": Truth("Is it ok?")}))
    assert decision.answer("ok").truth == pytest.approx(0.8)
    argv, stdin, _ = spawn.calls[0]
    assert "--json-schema" in argv
    assert argv[-1].startswith("state:")


def test_registered_as_a_provider() -> None:
    from sanchopanza.providers import available, create

    assert "claude-cli" in available()
    decider = create("claude-cli", model="m", ceiling_usd=0.5)
    assert isinstance(decider, LLMDecider)


def test_a_line_cut_by_a_crash_is_skipped_not_fatal(tmp_path: pathlib.Path) -> None:
    # Measured: a run killed mid-write left a torn last line (NUL padding) and the next run
    # could not open its own cache.
    cache = SessionCache(tmp_path / "c.jsonl")
    cache.put("k1", Session(ok=True, text="kept"))
    with cache.path.open("a", encoding="utf-8") as out:
        out.write('{"key": "k2", "sess' + "\x00" * 40 + "\n")
    again = SessionCache(cache.path)
    assert again.get("k1").text == "kept"
    assert again.get("k2") is None
    assert again.skipped == 1


def test_a_row_written_after_the_padding_is_recovered(tmp_path: pathlib.Path) -> None:
    # Measured: the resumed run appended its next answer on the padded line itself, so the
    # padding preceded a whole, valid row that the first loader threw away.
    source = SessionCache(tmp_path / "a.jsonl")
    source.put("k3", Session(ok=True, text="late"))
    row = source.path.read_text(encoding="utf-8")
    torn = tmp_path / "torn.jsonl"
    torn.write_text("\x00" * 40 + row, encoding="utf-8")
    again = SessionCache(torn)
    assert again.get("k3").text == "late"
    assert again.skipped == 0


# --- the code review of 2026-09-27 ------------------------------------------------------------


def test_a_prompt_that_looks_like_a_flag_stays_a_prompt() -> None:
    # Checked: `claude -p ... "--version"` printed the version, and `claude -p ... --
    # "--version please"` answered it as a message. The prompt always follows `--`.
    spawn = FakeSpawn(_stdout())
    cli = ClaudeCLI(model="m", system="S", ceiling_usd=1.0, spawn=spawn)
    asyncio.run(cli.run('--settings={"hooks": 1}'))
    argv, stdin, _ = spawn.calls[0]
    assert argv[-2:] == ["--", '--settings={"hooks": 1}']
    assert argv.count("--") == 1
    assert stdin == b""


def test_a_batch_shim_is_refused() -> None:
    # cmd.exe re-parses the arguments of a .cmd/.bat (quotes, &, %): never run one.
    for shim in ("C:/npm/claude.cmd", "C:/npm/claude.BAT"):
        with pytest.raises(ValueError):
            ClaudeCLI(model="m", system="S", ceiling_usd=1.0, executable=shim)


def test_a_ceiling_that_is_not_a_finite_positive_number_is_refused() -> None:
    for bad in (float("nan"), float("inf"), 0.0, -1.0):
        with pytest.raises(ValueError):
            ClaudeCLI(model="m", system="S", ceiling_usd=bad, spawn=FakeSpawn())


def test_every_route_to_another_account_is_stripped() -> None:
    env = clean_env(
        {
            "ANTHROPIC_VERTEX_PROJECT_ID": "p",
            "ANTHROPIC_MODEL": "x",
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "CLAUDE_CODE_USE_VERTEX": "1",
            "AWS_BEARER_TOKEN_BEDROCK": "t",
            "HOME": "h",
        }
    )
    assert set(env) == {"HOME", "MAX_THINKING_TOKENS"}


def test_an_unknown_cost_is_charged_at_the_session_budget() -> None:
    # A timeout or an unreadable reply may still have spent up to --max-budget-usd.
    spawn = FakeSpawn(b"", code=124)
    cli = ClaudeCLI(model="m", system="S", ceiling_usd=1.0, max_budget_usd=0.05, spawn=spawn)
    asyncio.run(cli.run("x"))
    assert cli.spent_usd == pytest.approx(0.05)


def test_sessions_in_flight_are_reserved_against_the_ceiling() -> None:
    started: list[str] = []
    release = asyncio.Event()

    async def slow(argv, stdin, env, cwd, timeout_s):
        started.append(argv[-1])
        await release.wait()
        return 0, _stdout(total_cost_usd=0.01), b""

    async def main() -> list[object]:
        cli = ClaudeCLI(
            model="m", system="S", ceiling_usd=0.1, max_budget_usd=0.05, concurrency=4, spawn=slow
        )
        tasks = [asyncio.create_task(cli.run(f"p{i}")) for i in range(4)]
        await asyncio.sleep(0.05)
        release.set()
        return await asyncio.gather(*tasks, return_exceptions=True)

    results = asyncio.run(main())
    assert len(started) == 2
    assert sum(isinstance(r, CeilingReached) for r in results) == 2


def test_a_cancelled_session_kills_its_process(monkeypatch: pytest.MonkeyPatch) -> None:
    from sanchopanza.providers import claude_cli as module

    class Proc:
        returncode = None
        killed = False

        async def communicate(self, data):
            await asyncio.sleep(3600)

        def kill(self):
            self.killed = True
            self.returncode = -9

        async def wait(self):
            return -9

    proc = Proc()

    async def fake_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_exec)

    async def main() -> None:
        task = asyncio.create_task(module.spawn_process(["claude"], b"", {}, ".", 60.0))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(main())
    assert proc.killed


def test_a_long_command_line_moves_the_prompt_to_stdin() -> None:
    spawn = FakeSpawn(_stdout())
    cli = ClaudeCLI(model="m", system="S" * 20_000, ceiling_usd=1.0, spawn=spawn)
    asyncio.run(cli.run("p" * 15_000))
    argv, stdin, _ = spawn.calls[0]
    assert stdin == b"p" * 15_000


def test_effort_is_part_of_the_cache_key_only_when_set(tmp_path: pathlib.Path) -> None:
    plain = SessionCache.key("m", "S", None, "p")
    assert SessionCache.key("m", "S", None, "p", effort=None) == plain
    assert SessionCache.key("m", "S", None, "p", effort="low") != plain


def test_a_row_after_a_torn_json_line_starts_on_its_own_line(tmp_path: pathlib.Path) -> None:
    cache = SessionCache(tmp_path / "c.jsonl")
    cache.path.write_text('{"key": "k1", "sess', encoding="utf-8")
    cache.put("k2", Session(ok=True, text="two"))
    again = SessionCache(cache.path)
    assert again.get("k2").text == "two"


def test_cached_spend_counts_toward_the_ceiling_when_asked(tmp_path: pathlib.Path) -> None:
    cache = SessionCache(tmp_path / "c.jsonl")
    cache.put("k", Session(ok=True, text="a", list_cost_usd=0.9))
    spawn = FakeSpawn(_stdout(total_cost_usd=0.2))
    cli = ClaudeCLI(
        model="m", system="S", ceiling_usd=1.0, cache=cache, count_cached=True, spawn=spawn
    )
    assert cli.spent_usd == pytest.approx(0.9)
    asyncio.run(cli.run("new"))
    with pytest.raises(CeilingReached):
        asyncio.run(cli.run("newer"))


def test_a_ceiling_below_the_session_budget_caps_the_session() -> None:
    # The CLI enforces --max-budget-usd itself, so the last sessions get what is left.
    spawn = FakeSpawn(_stdout(total_cost_usd=0.004))
    cli = ClaudeCLI(model="m", system="S", ceiling_usd=0.01, max_budget_usd=0.05, spawn=spawn)
    asyncio.run(cli.run("one"))
    argv, _, _ = spawn.calls[0]
    assert argv[argv.index("--max-budget-usd") + 1] == "0.01"
    asyncio.run(cli.run("two"))
    argv, _, _ = spawn.calls[1]
    assert float(argv[argv.index("--max-budget-usd") + 1]) == pytest.approx(0.006)
