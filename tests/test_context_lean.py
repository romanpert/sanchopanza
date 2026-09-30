"""The lean configuration: index stubs, the free arrival cut, recall placement, pull recall
from the archive, `install --lean`, and no copy of the conversation left by a failed compaction.
No provider is paid: the only decider here refuses every call, to show none is asked."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import re
import sys
from pathlib import Path

import pytest

from sanchopanza import Squire, cli
from sanchopanza.context import archive as archive_mod
from sanchopanza.context import arrival, compact
from sanchopanza.context.index import codes_of, index_of
from sanchopanza.harness import autopilot, install
from sanchopanza.harness.generic import HarnessConfig
from sanchopanza.harness.mcp import build_archive_server
from tests.context_helpers import BrokenDecider, write_transcript


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SANCHOPANZA_JOURNAL", str(tmp_path / "journal.jsonl"))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("SANCHOPANZA_STUB_STYLE", raising=False)
    monkeypatch.delenv("SANCHO_STUB_STYLE", raising=False)


# --- index_of ---------------------------------------------------------------------------------

SAMPLE = """Starting build on 2026-09-28 at host web-01
ticket PRB-4821 opened, trace a1b32c8c7d
TIMEOUT=30s retries: 3 mode=fast
ERROR: disk full writing /var/log/app.log (code RT-8KX2)
see src/app/main.py and the and/or case, version 1.2.3
"""


def test_index_of_puts_error_lines_first_then_the_rest_in_order():
    index = index_of(SAMPLE)
    items = index.split("; ")
    assert items[0] == "ERROR: disk full writing /var/log/app.log (code RT-8KX2)"
    assert items[1:6] == ["web-01", "PRB-4821", "a1b32c8c7d", "TIMEOUT=30s", "retries: 3"]
    assert "src/app/main.py" in items
    assert "mode=fast" not in index  # a pair whose value has no digit
    assert "2026-09-28" not in items  # an ISO date alone is not an identifier
    assert "and/or" not in index and "RT-8KX2" not in items  # inside the error line already


def test_the_failing_line_of_a_long_log_survives_the_limit():
    noise = [f"step {i} ok path/to/mod_{i}.py hash a1b2c{i}" for i in range(200)]
    log = "\n".join([*noise, "CHECK BLD-4471 failed: expected 3.25 got 3.40", *noise[:50]])
    assert index_of(log).startswith("CHECK BLD-4471 failed: expected 3.25 got 3.40")


def test_index_of_is_pure_bounded_and_cut_at_a_separator():
    text = "\n".join(f"id CODE-{i:04d}X" for i in range(200))
    index = index_of(text, limit=60)
    assert len(index) <= 60 and not index.endswith(";") and not index.endswith(" ")
    assert all(re.fullmatch(r"CODE-\d{4}X", item) for item in index.split("; "))
    assert index_of(text, limit=60) == index
    assert index_of("") == "" and index_of("just some plain words here") == ""


def test_index_of_trims_error_lines_and_long_tokens():
    long_line = "Traceback: " + "x" * 200
    token = "a1" * 40
    index = index_of(f"{long_line}\nhash {token}\n")
    first, second = index.split("; ")
    assert first == long_line[:80]
    assert second == token[:40]
    assert codes_of("PRB-4821 and 4821_17 but not 12345 nor 2026-01-02") == ("PRB-4821", "4821_17")


# --- stub styles ------------------------------------------------------------------------------


def _messages(result: str) -> list[dict]:
    return [
        {"role": "user", "content": "task"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "x"}}
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": result}],
        },
        *({"role": "assistant", "content": f"note {i}"} for i in range(8)),
    ]


RESULT = "line of output\n" * 50 + "ERROR: ticket PRB-4821 failed\n"


async def _masked(tmp_path: Path, style: str) -> tuple[str, Path]:
    messages = _messages(RESULT)
    plan = await compact.plan(
        Squire(BrokenDecider()), messages, arm="mask", keep_recent=2, mask_turns=0
    )
    archive = tmp_path / "arc"
    pruned = compact.apply(messages, plan, archive, stub_style=style)
    return pruned[2]["content"][0]["content"], archive


async def test_plain_stub_is_unchanged(tmp_path):
    stub, archive = await _masked(tmp_path, "plain")
    assert stub.startswith("[sanchopanza pruned this Bash result") and "Holds:" not in stub
    assert (archive / "t1.txt").read_text(encoding="utf-8") == RESULT


async def test_index_stub_says_what_the_result_holds(tmp_path):
    stub, archive = await _masked(tmp_path, "index")
    plain, _ = await _masked(tmp_path / "p", "plain")
    assert stub == f"{plain.replace(str(tmp_path / 'p'), str(tmp_path))} Holds: {index_of(RESULT)}"
    assert "PRB-4821" in stub
    assert (archive / "t1.txt").exists()


async def test_cleared_stub_is_claude_codes_text_and_archives_nothing(tmp_path):
    stub, archive = await _masked(tmp_path, "cleared")
    assert stub == "[Old tool result content cleared]" == compact.CLEARED
    assert not archive.exists()


def test_an_unknown_stub_style_is_refused():
    plan = compact.Plan("mask", ())
    with pytest.raises(ValueError):
        compact.apply([], plan, None, stub_style="fancy")


def _stdin(monkeypatch, payload) -> None:
    raw = json.dumps(payload).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8"))


def _compact_args(*extra: str) -> list[str]:
    base = ["compact", "--stdin", "--arm", "mask", "--provider", "null", "--session", "s"]
    return [*base, "--keep-recent", "2", "--mask-turns", "0", "--min-reduction", "0", *extra]


def test_cli_stub_style_comes_from_the_flag_else_the_environment(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SANCHOPANZA_STUB_STYLE", "index")
    _stdin(monkeypatch, {"messages": _messages(RESULT)})
    assert cli.main(_compact_args()) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["stub_style"] == "index"
    assert "Holds: " in json.dumps(out["messages"])
    _stdin(monkeypatch, {"messages": _messages(RESULT)})
    assert cli.main(_compact_args("--stub-style", "cleared", "--session", "c")) == 0
    out = json.loads(capsys.readouterr().out)
    assert compact.CLEARED in json.dumps(out["messages"])
    assert not (tmp_path / ".sanchopanza" / "archive" / "c").exists()


def test_cli_refuses_an_unknown_stub_style_in_the_environment(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SANCHOPANZA_STUB_STYLE", "fancy")
    _stdin(monkeypatch, {"messages": _messages(RESULT)})
    assert cli.main(_compact_args()) == 2
    assert "unknown stub style" in capsys.readouterr().err


# --- no copy of the conversation after a failed compaction -----------------------------------


def test_exit_3_blanks_a_stale_out_file_and_writes_no_archive(tmp_path, capsys, monkeypatch):
    """The context-e2e leftover file: an earlier run's `--out` that nobody blanked must not
    survive a fallback, and a fallback archives nothing."""
    monkeypatch.chdir(tmp_path)
    out = tmp_path / ".sanchopanza" / "compact-s.json"
    out.parent.mkdir(parents=True)
    out.write_text(json.dumps({"messages": [{"role": "user", "content": "secret"}]}), "utf-8")
    path = write_transcript(tmp_path / "abc.jsonl")
    args = ["compact", "--transcript", str(path), "--provider", "null", "--session", "s"]
    code = cli.main([*args, "--out", str(out), "--min-reduction", "0.99"])
    capsys.readouterr()
    assert code == cli.COMPACT_BELOW_MINIMUM
    assert out.read_text(encoding="utf-8") == "{}"
    archive = tmp_path / ".sanchopanza" / "archive"
    assert not any(p.is_file() for p in archive.rglob("*")) if archive.exists() else True


# --- the free arrival cut ---------------------------------------------------------------------


def _log() -> tuple[str, str]:
    rows = [
        f"2026-09-28 12:{i // 60:02d}:{i % 60:02d} INFO worker step {i} finished its unit ok\n"
        for i in range(700)
    ]
    needed = "2026-09-28 13:00:00 INFO payment reconciliation mismatch for invoice batch\n"
    text = "".join([*rows[:350], needed, *rows[350:]])
    return text, needed


def test_free_cut_keeps_the_needed_middle_line_and_the_edges():
    text, needed = _log()
    assert len(text) > 40_000
    result = arrival.free_cut(text, "why is the payment reconciliation mismatched?")
    assert result.text is not None
    assert needed in result.text
    lines = text.splitlines(keepends=True)
    assert result.text.startswith("".join(lines[:20]))
    assert result.text.endswith("".join(lines[-20:]))
    assert "sanchopanza omitted lines" in result.text
    assert result.report["kept_chars"] == len(result.text) <= len(text) * 0.3
    assert result.report["omitted"] > 0
    assert arrival.free_cut(text, "why is the payment reconciliation mismatched?") == result


def test_free_cut_keeps_errors_and_rare_codes_and_respects_the_target():
    text, _ = _log()
    lines = text.splitlines(keepends=True)
    text = "".join(
        [*lines[:200], "Traceback: worker crashed\n", "ref PRB-4821 opened\n", *lines[200:]]
    )
    result = arrival.free_cut(text, "unrelated words", arrival.Settings(target=4_000))
    assert "Traceback: worker crashed" in result.text and "PRB-4821" in result.text
    kept = [line for line in result.text.splitlines(keepends=True) if "sanchopanza" not in line]
    assert sum(len(line) for line in kept) <= 4_000


def test_free_cut_fails_open():
    assert arrival.free_cut("short", "x").text is None
    text, _ = _log()
    whole = arrival.free_cut(text, "x", arrival.Settings(min_saving=0.99))
    assert whole.text is None and "passed whole" in whole.reason


async def test_the_autopilot_free_mode_cuts_without_a_decider(tmp_path):
    text, needed = _log()
    event = {
        "hook_event_name": "PostToolUse",
        "session_id": "s-1",
        "transcript_path": str(write_transcript(tmp_path / "session.jsonl")),
        "cwd": str(tmp_path),
        "tool_name": "Bash",
        "tool_use_id": "toolu_1",
        "tool_input": {"command": "cat worker.log | grep reconciliation"},
        "tool_response": {"stdout": text, "stderr": "", "interrupted": False},
    }
    config = autopilot.Config(arrival=True, arrival_mode="free")
    squire = Squire(BrokenDecider())
    out = await autopilot.post_tool_use(event, squire, config)
    stdout = out["hookSpecificOutput"]["updatedToolOutput"]["stdout"]
    assert needed in stdout and len(stdout) < len(text) / 2
    assert squire.meter.decisions == 0
    saved = Path(re.search(r"Full text: (.+?) \(Read it", stdout).group(1))
    assert saved.read_text(encoding="utf-8") == text


# --- configuration ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "env,expected",
    [
        ({"SANCHOPANZA_AUTOPILOT": "1"}, (True, True)),
        ({}, (False, False)),
        ({"SANCHOPANZA_AUTOPILOT": "1", "SANCHOPANZA_RECALL_ON": "off"}, (False, False)),
        ({"SANCHOPANZA_AUTOPILOT": "1", "SANCHOPANZA_RECALL_ON": "prompt"}, (True, False)),
        ({"SANCHOPANZA_RECALL_ON": "tool"}, (False, True)),
        ({"SANCHOPANZA_RECALL_ON": "both"}, (True, True)),
        ({"SANCHOPANZA_RECALL_ON": "off", "SANCHOPANZA_RECALL": "1"}, (True, False)),
        ({"SANCHOPANZA_RECALL_ON": "both", "SANCHOPANZA_RECALL_ON_TOOL": "0"}, (True, False)),
        ({"SANCHOPANZA_AUTOPILOT": "1", "SANCHOPANZA_RECALL_ON": "nonsense"}, (True, True)),
    ],
)
def test_recall_placement(env, expected):
    config = autopilot.config_from_env(env)
    assert (config.recall, config.recall_on_tool) == expected


def test_arrival_mode_from_the_environment():
    assert autopilot.config_from_env({}).arrival_mode == "jev"
    free = autopilot.config_from_env(
        {"SANCHOPANZA_ARRIVAL_MODE": "free", "SANCHOPANZA_ARRIVAL_FREE_CHARS": "5000"}
    )
    assert free.arrival_mode == "free" and free.free_target == 5_000
    assert autopilot.config_from_env({"SANCHOPANZA_ARRIVAL_MODE": "x"}).arrival_mode == "jev"


# --- pull recall: search_archive --------------------------------------------------------------


def _archive(root: Path) -> None:
    filler = "unrelated build output line\n" * 80
    archive_mod.write_entry(
        root / "s1", "t1", filler + "deploy key rotated for RT-8KX2 at 04:00\n" + filler,
        {"tool": "Bash", "about": "cat deploy.log", "by": "compaction"},
    )  # fmt: skip
    for i in range(7):
        archive_mod.write_entry(
            root / "s2", f"t{i}", f"notes {i} about RT-8KX2 and caching\n" * 3, {"tool": "Read"}
        )
    (root / "s3").mkdir(parents=True)
    (root / "s3" / "legacy.txt").write_text("legacy stub about RT-8KX2 deploy", "utf-8")


def test_search_archive_returns_path_meta_and_window(tmp_path):
    root = tmp_path / "archive"
    _archive(root)
    out = archive_mod.search(root, "key rotated", k=1)
    assert out.startswith("[1] ") and "t1.txt" in out.splitlines()[0]
    assert out.splitlines()[1].startswith("meta: ") and '"about": "cat deploy.log"' in out
    assert "deploy key rotated for RT-8KX2" in out
    window = out.split("\n", 2)[2].split("\n\nRead a path")[0]
    assert len(window) <= archive_mod.WINDOW + 6
    many = archive_mod.search(root, "RT-8KX2", k=50)
    assert len(re.findall(r"(?m)^\[\d\] ", many)) == archive_mod.SEARCH_MAX
    assert "(no sidecar)" in archive_mod.search(root, "legacy stub", k=1)


def test_search_archive_on_empty_or_unmatched(tmp_path):
    assert "holds no entries" in archive_mod.search(tmp_path / "none", "anything")
    _archive(tmp_path / "archive")
    assert "No archived entry" in archive_mod.search(tmp_path / "archive", "zebra")
    assert "Give a query" in archive_mod.search(tmp_path / "archive", "  ")


def test_the_archive_server_builds_without_a_key(tmp_path):
    _archive(tmp_path / "archive")
    server = build_archive_server(tmp_path / "archive")
    tools = asyncio.run(server.list_tools())
    assert [t.name for t in tools] == ["search_archive"]
    assert len(tools[0].description) < 200


def test_archive_mcp_is_a_subcommand():
    parser_help = io.StringIO()
    with pytest.raises(SystemExit), contextlib.redirect_stdout(parser_help):
        cli.main(["archive-mcp", "--help"])
    assert "--archive" in parser_help.getvalue()


# --- install --lean ---------------------------------------------------------------------------


def _install(tmp_path: Path, *flags: str) -> dict:
    settings = tmp_path / "proj" / ".claude" / "settings.json"
    plugin = tmp_path / "plugin"
    # --no-find: these tests are about the archive server alone (find is on by default since
    # 2026-09-30).
    args = ["install", *flags, "--no-find", "--path", str(settings), "--plugin-dir", str(plugin),
            "--write"]  # fmt: skip
    assert cli.main(args) == 0
    return json.loads(settings.read_text(encoding="utf-8"))


def test_install_lean_writes_the_env_and_the_archive_server(tmp_path, capsys):
    data = _install(tmp_path, "--autopilot", "--lean")
    for key, value in install.LEAN_ENV.items():
        assert data["env"][key] == value
    assert data["env"]["SANCHOPANZA_AUTOPILOT"] == "1"
    assert data["enabledMcpjsonServers"] == ["sanchopanza-archive"]
    mcp = json.loads((tmp_path / "proj" / ".mcp.json").read_text(encoding="utf-8"))
    entry = mcp["mcpServers"]["sanchopanza-archive"]
    assert entry == {"command": "sanchopanza", "args": ["archive-mcp"]}
    assert ".mcp.json" in capsys.readouterr().out


def test_install_lean_keeps_other_servers_and_is_idempotent(tmp_path, capsys):
    mcp_file = tmp_path / "proj" / ".mcp.json"
    mcp_file.parent.mkdir(parents=True)
    mcp_file.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}), "utf-8")
    first = _install(tmp_path, "--lean")
    capsys.readouterr()
    assert _install(tmp_path, "--lean") == first
    assert "already wired" in capsys.readouterr().out
    servers = json.loads(mcp_file.read_text(encoding="utf-8"))["mcpServers"]
    assert set(servers) == {"other", "sanchopanza-archive"}


def test_plain_autopilot_is_unchanged_and_undoes_lean(tmp_path):
    plain = _install(tmp_path / "a", "--autopilot")
    assert not any(k in plain["env"] for k in install.LEAN_ENV)
    assert "enabledMcpjsonServers" not in plain
    assert not (tmp_path / "a" / "proj" / ".mcp.json").exists()
    _install(tmp_path / "b", "--autopilot", "--lean")
    undone = _install(tmp_path / "b", "--autopilot")
    assert not any(k in undone["env"] for k in install.LEAN_ENV)
    assert "enabledMcpjsonServers" not in undone
    mcp = json.loads((tmp_path / "b" / "proj" / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"] == {}
    assert undone["env"] == plain["env"] and undone["hooks"] == plain["hooks"]


def test_lean_needs_the_autopilot_in_plan(tmp_path):
    with pytest.raises(ValueError):
        install.plan(tmp_path / "s.json", HarnessConfig(), compact_root=tmp_path, lean=True)


def test_the_archive_server_entry_follows_the_hook_command():
    entry = install.archive_server_entry("C:\\venv\\python.exe -m sanchopanza hook")
    assert entry["args"] == ["-m", "sanchopanza", "archive-mcp"]
    assert entry["command"].endswith("python.exe")
