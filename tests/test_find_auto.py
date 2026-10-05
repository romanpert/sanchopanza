"""The find substitute (`install --find-auto`): Claude Code's `mcp_tool` hook calls `find_auto` on
the running find server after every search, Read and edit; at the 4th search while no source file
has been Read or edited (R4, benchmarks/find_auto), once per session, the server runs find for the
agent and answers with the likeliest places as additionalContext. Nothing when the index is not
built yet (it stays armed), when the judge fails or keeps nothing, past the session's Jev ceiling,
or after a source Read or edit."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from sanchopanza.context import repo
from sanchopanza.harness import find_auto

SOURCE = {
    "pkg/compiler.py": "class SQLInsertCompiler:\n    def execute_sql(self, returning_fields):\n"
                       "        rows = fetch_returned_insert_rows(returning_fields)\n"
                       "        return converters(rows)\n",
    "pkg/fields.py": "def from_db_value(value, expression, connection):\n    return value\n",
    "pkg/other.py": "def unrelated():\n    return 1\n",
    "docs/ref.md": "returning fields from_db_value converters insert\n",
    "tests/test_x.py": "def test_returning_fields():\n    from_db_value(1)\n",
}  # fmt: skip
REQUEST = "Database converters (from_db_value) not called for returning_fields on insert"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project = tmp_path / "proj"
    for rel, body in SOURCE.items():
        (project / rel).parent.mkdir(parents=True, exist_ok=True)
        (project / rel).write_text(body, "utf-8")
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    repo._CACHE.pop(str(project.resolve()), None)
    monkeypatch.setenv("SANCHOPANZA_GUARD_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("SANCHOPANZA_JOURNAL", str(tmp_path / "journal.jsonl"))
    monkeypatch.setenv("SANCHOPANZA_LOOP_HOME", str(tmp_path / "loop"))
    monkeypatch.delenv("SANCHOPANZA_SESSION_MAX_USD", raising=False)
    monkeypatch.delenv("SANCHOPANZA_FIND_AUTO", raising=False)
    transcript(tmp_path, [])
    return project


def warm(project: Path) -> None:
    repo.source_first(project)


def transcript(tmp_path: Path, calls: list[tuple[str, dict[str, Any]]],
               request: str = REQUEST) -> Path:  # fmt: skip
    path = tmp_path / "transcript.jsonl"
    rows: list[dict[str, Any]] = [
        {"type": "user", "isMeta": True, "message": {"role": "user", "content": "<caveat/>"}},
        {"type": "user", "message": {"role": "user", "content": request}},
    ]
    for n, (name, tool_input) in enumerate(calls):
        block = {"type": "tool_use", "id": f"t{n}", "name": name, "input": tool_input}
        rows.append({"type": "assistant", "message": {"role": "assistant", "content": [block]}})
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", "utf-8")
    return path


def fields(project: Path, tool: str, event: str = "PostToolUse", **values: str) -> dict[str, str]:
    return {"hook_event_name": event, "session_id": "s-1", "tool_name": tool,
            "tool_use_id": values.pop("tool_use_id", "tu"),
            "transcript_path": str(project.parent / "transcript.jsonl"), "cwd": str(project),
            "agent_id": values.pop("agent_id", ""), **values}  # fmt: skip


def grep(project: Path, pattern: str, **extra: str) -> dict[str, str]:
    return fields(project, "Grep", pattern=pattern, **extra)


def bash(project: Path, command: str, **extra: str) -> dict[str, str]:
    return fields(project, "Bash", command=command, **extra)


class Judge:
    """A stand-in squire: keeps the fragments whose path holds one of `keep`, at p 0.9."""

    def __init__(self, keep: tuple[str, ...] = ("compiler",), fail: bool = False,
                 unanswered: bool = False) -> None:  # fmt: skip
        self.keep, self.fail, self.unanswered = keep, fail, unanswered
        self.meter = type("M", (), {"cost_usd": 0.0021, "decisions": 2})()
        self.asked: list[str] = []

    async def triage_many(self, *, purpose: str, pages: list[tuple[str, str]]) -> list[Any]:
        self.asked.append(purpose)
        if self.fail:
            raise RuntimeError("jev down")
        if self.unanswered:
            return [(True, None) for _ in pages]
        return [(any(k in title for k in self.keep), 0.9) for title, _ in pages]


def run(project: Path, values: dict[str, str], judge: Any = None) -> dict[str, Any]:
    out = asyncio.run(find_auto.respond(values, project, squire_for=lambda _usd: judge))
    return json.loads(out)


def context(out: dict[str, Any]) -> str:
    return (out.get("hookSpecificOutput") or {}).get("additionalContext", "")


def journal(project: Path) -> list[dict[str, Any]]:
    path = project.parent / "journal.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]
    return [r for r in rows if r["kind"] == "find_auto"]


def four_searches(project: Path, judge: Any = None) -> list[dict[str, Any]]:
    events = [grep(project, "from_db_value"), bash(project, "find . -name '*.py' | head -20"),
              fields(project, "Glob", pattern="**/compiler*.py"),
              bash(project, "grep -rn returning_fields pkg", tool_use_id="tu-4")]  # fmt: skip
    return [run(project, e, judge) for e in events]


# ---- the trigger ---------------------------------------------------------------------------------


def test_the_fourth_search_before_any_source_read_fires_once(root: Path) -> None:
    warm(root)
    judge = Judge()
    outs = four_searches(root, judge)
    assert [bool(context(o)) for o in outs] == [False, False, False, True]
    note = context(outs[-1])
    assert note.splitlines()[0] == find_auto.HEADER
    assert note.splitlines()[1].startswith("- pkg/compiler.py:1-4  ")
    assert "returning_fields" in note.splitlines()[1]
    assert outs[-1]["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert set(outs[-1]) == {"hookSpecificOutput"}
    assert run(root, grep(root, "converters"), judge) == {}  # once per session
    assert len(judge.asked) == 1


def test_the_query_is_the_request_plus_the_search_words(root: Path) -> None:
    warm(root)
    judge = Judge()
    four_searches(root, judge)
    [row] = journal(root)
    data = row["data"]
    assert data["outcome"] == "fired" and data["search"] == 4 and data["tool_use_id"] == "tu-4"
    assert data["query"].startswith(REQUEST + "\n")
    assert data["words"] == ["from_db_value", "compiler", "returning_fields", "pkg"]
    assert data["keys"] == ["pkg/compiler.py:1-4"]
    assert data["jev_usd"] == pytest.approx(0.0021)
    assert REQUEST in judge.asked[0]  # the judge's purpose is find's, on the same query


def test_a_source_read_closes_the_window(root: Path) -> None:
    warm(root)
    run(root, grep(root, "a"))
    run(root, fields(root, "Read", file_path=str(root / "pkg" / "other.py")))
    outs = [run(root, grep(root, w), Judge()) for w in ("b", "c", "d", "e")]
    assert all(o == {} for o in outs)


def test_reading_a_test_or_a_doc_does_not_close_it(root: Path) -> None:
    warm(root)
    run(root, fields(root, "Read", file_path=str(root / "tests" / "test_x.py")))
    run(root, fields(root, "Read", file_path=str(root / "docs" / "ref.md")))
    assert context(four_searches(root, Judge())[-1])


def test_an_edit_of_an_existing_file_closes_it_but_a_new_file_does_not(root: Path) -> None:
    warm(root)
    run(root, fields(root, "Write", file_path=str(root / "reproduce.py")))  # a new file
    assert context(four_searches(root, Judge())[-1])


def test_an_edit_closes_it(root: Path, tmp_path: Path) -> None:
    warm(root)
    run(root, fields(root, "Read", file_path=str(root / "setup.cfg")))
    run(root, fields(root, "Write", file_path=str(root / "setup.cfg")))  # read first: an edit
    assert all(o == {} for o in four_searches(root, Judge()))


def test_a_failed_edit_does_not_close_it_and_a_failed_search_counts(root: Path) -> None:
    warm(root)
    run(root, fields(root, "Edit", "PostToolUseFailure", file_path=str(root / "pkg/fields.py")))
    run(root, fields(root, "Grep", "PostToolUseFailure", pattern="nothing_here"))
    outs = [run(root, grep(root, w), Judge()) for w in ("x", "y", "z")]
    assert [bool(context(o)) for o in outs] == [False, False, True]


def test_a_fire_on_a_failed_search_answers_for_that_event(root: Path) -> None:
    warm(root)
    for w in ("a", "b", "c"):
        run(root, grep(root, w))
    out = run(root, fields(root, "Bash", "PostToolUseFailure", command="grep -rn zz ."), Judge())
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUseFailure"


def test_a_subagents_calls_are_not_counted(root: Path) -> None:
    warm(root)
    for w in ("a", "b", "c", "d", "e"):
        assert run(root, grep(root, w, agent_id="sub-1"), Judge()) == {}
    assert context(four_searches(root, Judge())[-1])


def test_a_source_read_in_the_transcript_closes_it_even_if_its_event_was_missed(
    root: Path, tmp_path: Path
) -> None:
    warm(root)
    transcript(tmp_path, [("Read", {"file_path": str(root / "pkg" / "compiler.py")})])
    assert all(o == {} for o in four_searches(root, Judge()))
    assert journal(root)[0]["data"]["outcome"] == "touched"


# ---- failing open --------------------------------------------------------------------------------


def test_not_ready_injects_nothing_and_stays_armed(root: Path) -> None:
    outs = four_searches(root, Judge())
    assert outs[-1] == {}
    assert [r["data"]["outcome"] for r in journal(root)] == ["not_ready"]
    warm(root)
    assert context(run(root, grep(root, "converters"), Judge()))  # the next search, now ready
    assert [r["data"]["outcome"] for r in journal(root)] == ["not_ready", "fired"]
    assert journal(root)[-1]["data"]["search"] == 5


def test_a_failing_judge_injects_nothing_and_closes(root: Path) -> None:
    warm(root)
    assert four_searches(root, Judge(fail=True))[-1] == {}
    assert journal(root)[-1]["data"]["outcome"] == "judge_failed"
    assert run(root, grep(root, "again"), Judge()) == {}


def test_an_unanswered_judge_is_a_failure_too(root: Path) -> None:
    warm(root)
    assert four_searches(root, Judge(unanswered=True))[-1] == {}
    assert journal(root)[-1]["data"]["outcome"] == "judge_failed"


def test_a_judge_that_keeps_nothing_injects_nothing(root: Path) -> None:
    warm(root)
    assert four_searches(root, Judge(keep=("nowhere",)))[-1] == {}
    assert journal(root)[-1]["data"]["outcome"] == "nothing_kept"


def test_without_a_decider_the_free_ranking_is_shown(root: Path) -> None:
    warm(root)
    note = context(four_searches(root, None)[-1])
    assert note.startswith(find_auto.HEADER) and "pkg/" in note
    assert "tests/" not in note and "docs/" not in note
    assert journal(root)[-1]["data"]["outcome"] == "free"


def test_past_the_session_ceiling_nothing_is_asked(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sanchopanza.harness.autopilot import write_ledger
    from sanchopanza.harness.loop_hook import _ledger_root

    warm(root)
    monkeypatch.setenv("SANCHOPANZA_SESSION_MAX_USD", "0.10")
    write_ledger(_ledger_root(), "s-1", {"usd": 0.10, "decisions": 9, "injected": []})
    judge = Judge()
    assert four_searches(root, judge)[-1] == {}
    assert judge.asked == [] and journal(root)[-1]["data"]["outcome"] == "ceiling"


def test_a_fire_charges_the_session_ledger(root: Path) -> None:
    from sanchopanza.harness.autopilot import read_ledger
    from sanchopanza.harness.loop_hook import _ledger_root

    warm(root)
    four_searches(root, Judge())
    assert read_ledger(_ledger_root(), "s-1")["usd"] == pytest.approx(0.0021)


def test_switched_off_by_its_variable(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    warm(root)
    monkeypatch.setenv("SANCHOPANZA_FIND_AUTO", "0")
    assert all(o == {} for o in four_searches(root, Judge()))


def test_a_malformed_call_answers_nothing(root: Path) -> None:
    assert run(root, {"hook_event_name": "PostToolUse"}) == {}
    assert run(root, {"hook_event_name": "Stop", "session_id": "s"}) == {}


# ---- pieces --------------------------------------------------------------------------------------


def test_search_words_are_the_benchmarks() -> None:
    assert find_auto.search_words("Grep", {"pattern": "from_db_value", "glob": "*.py"}) == [
        "from_db_value"]  # fmt: skip
    assert find_auto.search_words(
        "Bash", {"command": "grep -rn --include=*.py 'returning_fields' django/db | head -20"}
    ) == ["returning_fields", "django"]  # 3+ letters
    assert find_auto.search_words("Read", {"file_path": "x.py"}) == []


def test_first_request_skips_meta_and_tool_results(tmp_path: Path) -> None:
    path = transcript(tmp_path, [("Grep", {"pattern": "x"})], request="Fix the export")
    with path.open("a", encoding="utf-8") as out:
        out.write(
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "content": [{"type": "tool_result", "tool_use_id": "t0", "content": "a.py"}]
                    },
                }
            )
            + "\n"
        )
        out.write(json.dumps({"type": "user", "message": {"content": "a later request"}}) + "\n")
    assert find_auto.first_request(str(path)) == "Fix the export"
    assert find_auto.first_request(str(tmp_path / "missing.jsonl")) == ""


def test_the_note_is_short() -> None:
    from sanchopanza.select import Candidate

    picks = [
        Candidate(
            f"pkg/m{i}.py:{i}-{i + 40}", "t", "x = 1\ndef returning_fields(" + "arg, " * 60 + "):\n"
        )
        for i in range(5)
    ]
    note = find_auto.render(picks, "returning_fields")
    lines = note.splitlines()
    assert len(lines) == 6 and all(len(line) <= 160 for line in lines)
    assert lines[1].startswith("- pkg/m0.py:0-40  def returning_fields(arg, ")


# ---- the server and the install ------------------------------------------------------------------


def test_the_server_serves_find_auto_hidden_from_the_model(root: Path) -> None:
    from sanchopanza.harness import mcp

    server = mcp._server("sanchopanza", mcp.FIND_INSTRUCTIONS)
    mcp.add_find(server, repo=root)
    mcp.add_find_auto(server, repo=root, warm=False)
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert set(tools) == {"find_in_repo", "find_auto"}
    meta = tools["find_auto"].meta or {}
    assert meta == {"ui": {"visibility": ["app"]}}  # Claude Code keeps it from the model
    tool = tools["find_auto"]
    schema = (getattr(tool, "input_schema", None) or tool.inputSchema)["properties"]
    assert set(schema) == {*find_auto.FIELDS, *find_auto.INPUT_FIELDS}
    assert all(p.get("type") == "string" for p in schema.values())
    warm(root)
    calls = [grep(root, "a"), grep(root, "b"), grep(root, "c"), grep(root, "converters")]
    answers = [asyncio.run(server.call_tool("find_auto", c)) for c in calls]
    assert "{}" in str(answers[0])
    assert find_auto.HEADER in str(answers[-1])  # no key in the test: the free ranking


def test_the_hook_passes_only_what_the_trigger_reads() -> None:
    hook = find_auto.hook()
    assert hook["type"] == "mcp_tool" and hook["server"] == "sanchopanza"
    assert hook["tool"] == "find_auto" and hook["timeout"] == find_auto.HOOK_TIMEOUT_S
    assert hook["input"]["command"] == "${tool_input.command}"
    assert hook["input"]["session_id"] == "${session_id}"
    assert "${tool_input}" not in json.dumps(hook)  # never a Write's whole content
    assert "${tool_response" not in json.dumps(hook)


def _install(settings: Path, *flags: str) -> int:
    from sanchopanza import cli

    return cli.main(["install", "--path", str(settings), *flags, "--write"])


def _auto_entries(settings: Path) -> dict[str, list[dict[str, Any]]]:
    hooks = json.loads(settings.read_text("utf-8")).get("hooks", {})
    return {
        event: [e for e in hooks.get(event, [])
                if any(h.get("type") == "mcp_tool" for h in e["hooks"])]
        for event in find_auto.EVENTS
    }  # fmt: skip


def _server_entry(settings: Path) -> dict[str, Any]:
    data = json.loads((settings.parent.parent / ".mcp.json").read_text("utf-8"))
    return data["mcpServers"]["sanchopanza"]


def test_install_find_auto_wires_both_events_and_the_server_flag(tmp_path: Path) -> None:
    settings = tmp_path / "proj" / ".claude" / "settings.json"
    assert _install(settings, "--find-auto") == 0
    entries = _auto_entries(settings)
    for event in find_auto.EVENTS:
        [entry] = entries[event]
        assert entry == {"matcher": find_auto.MATCHER, "hooks": [find_auto.hook()]}
    assert _server_entry(settings) == {"command": "sanchopanza", "args": ["find-mcp", "--auto"],
                                       "alwaysLoad": True}  # fmt: skip
    assert json.loads(settings.read_text("utf-8"))["enabledMcpjsonServers"] == ["sanchopanza"]
    assert _install(settings, "--find-auto") == 0  # twice: still one of each
    assert all(len(v) == 1 for v in _auto_entries(settings).values())


def test_an_install_without_the_flag_takes_it_out(tmp_path: Path) -> None:
    settings = tmp_path / "proj" / ".claude" / "settings.json"
    assert _install(settings, "--find-auto") == 0
    assert _install(settings) == 0
    assert _auto_entries(settings) == {e: [] for e in find_auto.EVENTS}
    assert _server_entry(settings)["args"] == ["find-mcp"]
    hooks = json.loads(settings.read_text("utf-8"))["hooks"]
    assert "PostToolUseFailure" not in hooks  # an event left empty goes


def test_find_auto_keeps_other_hooks_on_its_events(tmp_path: Path) -> None:
    settings = tmp_path / "proj" / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    theirs = {"matcher": "Bash", "hooks": [{"type": "mcp_tool", "server": "x", "tool": "y"}]}
    settings.write_text(json.dumps({"hooks": {"PostToolUseFailure": [theirs]}}), "utf-8")
    assert _install(settings, "--find-auto") == 0
    assert _install(settings) == 0
    assert json.loads(settings.read_text("utf-8"))["hooks"]["PostToolUseFailure"] == [theirs]


def test_find_auto_needs_find_and_replaces_the_nudge(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = tmp_path / "proj" / ".claude" / "settings.json"
    assert _install(settings, "--find-auto", "--no-find") == 0
    assert _auto_entries(settings) == {e: [] for e in find_auto.EVENTS}
    assert "find-auto hook needs find_in_repo" in capsys.readouterr().err
    assert _install(settings, "--find-auto", "--find-nudge") == 0
    post = json.loads(settings.read_text("utf-8"))["hooks"]["PostToolUse"]
    assert not any("find-hook" in h.get("command", "") for e in post for h in e["hooks"])
    assert len(_auto_entries(settings)["PostToolUse"]) == 1
    assert "the nudge is not wired" in capsys.readouterr().err


def test_find_mcp_auto_serves_the_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    from sanchopanza import cli
    from sanchopanza.harness import mcp

    seen: list[list[str]] = []
    monkeypatch.setattr(mcp, "main", lambda argv: seen.append(argv) or 0)
    assert cli.main(["find-mcp", "--auto"]) == 0 and cli.main(["find-mcp"]) == 0
    assert seen == [["--tools", "find,find_auto"], ["--tools", "find"]]


def test_paths_are_made_relative_whatever_their_spelling() -> None:
    root = r"C:\Users\me\work\proj"
    for given in (
        r"C:\Users\me\work\proj\pkg\a.py",
        "c:/users/me/work/proj/pkg/a.py",
        "/c/Users/me/work/proj/pkg/a.py",
        "./pkg/a.py",
        "pkg/a.py",
    ):
        assert find_auto.relative(given, root) == "pkg/a.py", given
    assert find_auto.relative("/c/elsewhere/a.py", root) == "c:/elsewhere/a.py"


def test_a_git_bash_read_of_source_closes_the_window(root: Path) -> None:
    warm(root)
    posix = str(root / "pkg" / "other.py").replace("\\", "/")
    drive = f"/{posix[0].lower()}{posix[2:]}"  # C:/x -> /c/x
    run(root, fields(root, "Read", file_path=drive))
    assert all(o == {} for o in four_searches(root, Judge()))


def test_the_judge_is_capped_by_what_is_left_of_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("SANCHOPANZA_PROVIDER", "SANCHO_PROVIDER", "TYPESAFE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert find_auto.squire_from_env_capped(0.5) is None  # no decider: the free ranking
    monkeypatch.setenv("TYPESAFE_API_KEY", "not-a-key")  # building it sends nothing
    squire = find_auto.squire_from_env_capped(0.03)
    assert squire is not None and squire.thresholds.max_usd == pytest.approx(0.03)
    assert find_auto.squire_from_env_capped(5.0).thresholds.max_usd == pytest.approx(0.10)
