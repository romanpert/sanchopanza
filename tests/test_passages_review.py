"""The independent review of the passages hook (2026-10-07): each finding, its test first.

1 Write from a cut view; 2 lint, typecheck and build output; 3 re-requests after an edit;
4 a cut Read keeps every line in place; 5 more diffs, and shell views of edited files;
6 the ledger; 7 the decision deadline; 8 the provider in env; 9 Read's output shape;
10-13 the smaller ones.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path

import pytest

from sanchopanza import Squire
from sanchopanza.context import passages as ps
from sanchopanza.journal import MemoryJournal
from tests.context_helpers import ScriptedDecider
from tests.test_passages_cut import module_source, pytest_log
from tests.test_passages_hook import _bash, _read, _transcript

MARKER = re.compile(r"^\[sanchopanza: lines (\d+)-(\d+) omitted")


@pytest.fixture(autouse=True)
def _archive(tmp_path, monkeypatch):
    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / ".sanchopanza" / "archive"))
    for name in ("PASSAGES_FRACTION", "PASSAGES_TOKENS", "SESSION_MAX_USD", "PROVIDER"):
        monkeypatch.delenv(f"SANCHOPANZA_{name}", raising=False)


def _squire(decider=None) -> Squire:
    return Squire(decider, journal=MemoryJournal())


def _events(squire: Squire, kind: str) -> list[dict]:
    return [e["data"] for e in squire.journal.events if e["kind"] == kind]


def _pre(tmp_path, tool: str, **tool_input) -> dict:
    return {"hook_event_name": "PreToolUse", "session_id": "sess", "cwd": str(tmp_path),
            "transcript_path": str(tmp_path / "project" / "sess.jsonl"), "tool_name": tool,
            "tool_use_id": f"pre-{tool}", "tool_input": tool_input}  # fmt: skip


def _denied(out: dict) -> str:
    spec = out.get("hookSpecificOutput", {})
    denied = spec.get("permissionDecision") == "deny"
    return spec.get("permissionDecisionReason", "") if denied else ""


async def _cut_read(tmp_path, target: Path, source: str, squire=None) -> str:
    from sanchopanza.harness import passages_hook as ph

    transcript = _transcript(tmp_path, "fix parse_config", "Reading settings.")
    out = await ph.post_tool_use(_read(tmp_path, transcript, target, source), squire or _squire())
    return out["hookSpecificOutput"]["updatedToolOutput"]["file"]["content"]


# --- 1. Write from a cut view ------------------------------------------------------------------


async def test_write_over_a_cut_view_is_denied_until_the_rest_is_read(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    target, source = tmp_path / "settings.py", module_source()
    content = await _cut_read(tmp_path, target, source)
    assert "partial view: do not rewrite this file with Write from here" in content
    reason = _denied(ph.pre_tool_use(_pre(tmp_path, "Write", file_path=str(target), content="x")))
    assert "partial view" in reason and "Read" in reason
    transcript = tmp_path / "project" / "sess.jsonl"
    lines = source.splitlines()
    for n, line in enumerate(content.splitlines(), 1):
        found = MARKER.match(line)
        if found:
            a, b = int(found[1]), int(found[2])
            part = "\n".join(lines[a - 1 : b]) + "\n"
            event = _read(tmp_path, transcript, target, part, use_id=f"r{n}", offset=a,
                          limit=b - a + 1)  # fmt: skip
            await ph.post_tool_use(event, _squire())
    assert ph.pre_tool_use(_pre(tmp_path, "Write", file_path=str(target), content="x")) == {}


async def test_a_whole_read_passed_through_lifts_the_guard(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    target, source = tmp_path / "settings.py", module_source()
    await _cut_read(tmp_path, target, source)
    transcript = tmp_path / "project" / "sess.jsonl"
    again = await ph.post_tool_use(_read(tmp_path, transcript, target, source, use_id="r2"),
                                   _squire())  # fmt: skip
    assert again == {}, "a whole re-request passes whole"
    assert ph.pre_tool_use(_pre(tmp_path, "Write", file_path=str(target), content="x")) == {}


async def test_edits_carrying_the_marker_are_denied_and_plain_edits_pass(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    target = tmp_path / "settings.py"
    await _cut_read(tmp_path, target, module_source())
    marked = "def a():\n[sanchopanza: lines 3-40 omitted (def b); Read offset=3 limit=38]\n"
    assert _denied(ph.pre_tool_use(_pre(tmp_path, "Edit", file_path=str(target),
                                        old_string=marked, new_string="x")))  # fmt: skip
    multi = _pre(tmp_path, "MultiEdit", file_path=str(target),
                 edits=[{"old_string": "a", "new_string": "b"},
                        {"old_string": marked, "new_string": "c"}])  # fmt: skip
    assert _denied(ph.pre_tool_use(multi))
    plain = _pre(tmp_path, "Edit", file_path=str(target), old_string="return total", new_string="y")
    assert ph.pre_tool_use(plain) == {}
    other = tmp_path / "other.py"
    assert ph.pre_tool_use(_pre(tmp_path, "Write", file_path=str(other), content="ok")) == {}
    assert _denied(ph.pre_tool_use(_pre(tmp_path, "Write", file_path=str(other), content=marked)))


def test_main_answers_a_pre_tool_use_event(tmp_path, monkeypatch, capsys):
    import io

    from sanchopanza.harness import passages_hook as ph
    from sanchopanza.harness import passages_state as st

    root = tmp_path / ".sanchopanza" / "archive"
    target = tmp_path / "x.py"
    st.write(root, "sess", st.mark_partial(st.read(root, "sess"), str(target), 100, [(1, 10)]))
    event = _pre(tmp_path, "Write", file_path=str(target), content="new")
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(event).encode())))
    assert ph.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


# --- 2. lint, typecheck and build output -------------------------------------------------------


def test_checkers_are_logs_whose_errors_are_kept():
    for command in ("mypy src", "pyright", "npx tsc --noEmit", "ruff check .", "flake8",
                    "npx eslint src", "cargo clippy", "cargo build", "go vet ./...",
                    "go build ./...", "make", "pnpm run lint", "npm run build",
                    "./gradlew build", "mvn -q compile"):  # fmt: skip
        assert ps.kind_of("Bash", {"command": command}, "x") == "test", command
    notes = [f"src/pkg/mod_{i}.py:{i}: note: see the definition of helper_{i}" for i in range(900)]
    errors = [f"src/pkg/mod_{i}.py:{i * 3}: error: Incompatible types in assignment  [assignment]"
              for i in range(0, 900, 30)]  # fmt: skip
    lines = [*notes, *errors]
    lines.sort(key=lambda line: int(line.split(":")[1]))
    text = "\n".join([*lines, "Found 30 errors in 30 files (checked 120 source files)"]) + "\n"
    cut = ps.cut_free(text, ps.kind_of("Bash", {"command": "mypy src"}, text), "fix types",
                      ps.Settings())  # fmt: skip
    assert cut.text is not None
    for line in [*errors, "Found 30 errors in 30 files (checked 120 source files)"]:
        assert line in cut.text.splitlines(), line


def test_compiler_diagnostics_are_kept():
    tsc = "src/app.ts(12,5): error TS2322: Type 'string' is not assignable to type 'number'."
    cargo = "error[E0308]: mismatched types"
    where = "  --> src/main.rs:4:5"
    ruff = "src/a.py:3:8: F401 [*] `os` imported but unused"
    filler = [f"   Compiling crate_{i} v0.1.{i}" for i in range(400)]
    text = "\n".join([*filler[:200], tsc, cargo, where, ruff, *filler[200:]]) + "\n"
    cut = ps.cut_free(text, "test", "build", ps.Settings())
    assert cut.text is not None
    for line in (tsc, cargo, where, ruff):
        assert line in cut.text.splitlines(), line


def test_a_search_for_errors_is_not_all_rules():
    hits = "".join(f"src/m{i}.py:{i}: raise error_{i}  # error handling\n" for i in range(400))
    assert ps.kind_of("Bash", {"command": "grep -rn error src"}, hits) == "search"
    cut = ps.cut_free(hits, "search", "error_17", ps.Settings())
    assert cut.text is not None and "error_17" in cut.text


# --- 3. re-requests after an edit --------------------------------------------------------------


async def test_a_rerun_after_an_edit_is_not_a_rerequest_and_is_cut(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    transcript = _transcript(tmp_path, "make the suite pass", "Running the tests.")
    squire = _squire()
    assert await ph.post_tool_use(_bash(tmp_path, transcript, "pytest -v", pytest_log()), squire)
    assert ph.pre_tool_use(_pre(tmp_path, "Edit", file_path=str(tmp_path / "app.py"),
                                old_string="a - b", new_string="a + b")) == {}  # fmt: skip
    after = pytest_log().replace("2 failed, 300", "1 failed, 301")
    again = await ph.post_tool_use(_bash(tmp_path, transcript, "pytest -v", after,
                                         use_id="toolu_b2"), squire)  # fmt: skip
    assert again, "a new output after an edit is cut"
    assert not _events(squire, "passages_rerequest")


async def test_the_same_output_again_is_whole_even_after_an_edit(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    transcript = _transcript(tmp_path, "make the suite pass", "Running the tests.")
    squire = _squire()
    await ph.post_tool_use(_bash(tmp_path, transcript, "pytest -v", pytest_log()), squire)
    ph.pre_tool_use(_pre(tmp_path, "Edit", file_path=str(tmp_path / "app.py"), old_string="a",
                         new_string="b"))  # fmt: skip
    again = await ph.post_tool_use(_bash(tmp_path, transcript, "pytest -v", pytest_log(),
                                         use_id="toolu_b2"), squire)  # fmt: skip
    assert again == {}
    [event] = _events(squire, "passages_rerequest")
    assert event["kind"] == "whole" and event["identical"] is True


# --- 4 and 9. a cut Read keeps every line in place, in Read's own shape -------------------------


async def test_a_cut_read_keeps_the_line_count_and_every_kept_line_in_place(tmp_path):
    target, source = tmp_path / "settings.py", module_source()
    content = await _cut_read(tmp_path, target, source)
    original, shown = source.splitlines(), content.splitlines()
    assert len(shown) == len(original), "Claude Code numbers the lines: none removed or added"
    markers = [i for i, line in enumerate(shown) if MARKER.match(line)]
    assert markers, "at least one omitted run"
    assert not shown[0].startswith("[sanchopanza cut"), "the header is never first"
    for i, line in enumerate(shown):
        if line and not line.startswith("[sanchopanza"):
            assert line == original[i], f"line {i + 1} moved or changed"
    for i in markers:
        found = MARKER.match(shown[i])
        assert int(found[1]) == i + 1, "a marker sits on the first line it stands for"
        assert f"Read offset={i + 1} limit=" in shown[i]
    assert "def parse_config(path):" in shown
    assert sum(len(x) for x in shown) < 0.45 * len(source)


async def test_the_read_output_has_read_s_exact_shape(tmp_path):
    """Seen in 2.1.287: `outputSchema.safeParse` on the rewrite (type "text": filePath, content,
    numLines, startLine, totalLines, truncatedByTokenCap?), then the mapper numbers `content` from
    `startLine`; numLines and totalLines are only read when content is empty."""
    from sanchopanza.harness import passages_hook as ph

    target, source = tmp_path / "settings.py", module_source()
    transcript = _transcript(tmp_path, "fix parse_config", "Reading settings.")
    event = _read(tmp_path, transcript, target, source)
    out = await ph.post_tool_use(event, _squire())
    updated = out["hookSpecificOutput"]["updatedToolOutput"]
    assert updated["type"] == "text" and set(updated) == {"type", "file"}
    file = updated["file"]
    assert set(file) == {"filePath", "content", "numLines", "startLine", "totalLines"}
    assert file["numLines"] == len(file["content"].splitlines()) == len(source.splitlines())
    assert file["startLine"] == 1 and file["totalLines"] == event["tool_response"]["file"][
        "totalLines"]  # fmt: skip


# --- 5. diffs and shell views of edited files --------------------------------------------------


@pytest.mark.parametrize("command", [
    "git -C repo --no-pager diff", "git -c color.ui=never show HEAD", "git --no-pager log -p -3",
    "gh pr diff 12", "svn diff", "hg diff",
])  # fmt: skip
async def test_more_diffs_pass(tmp_path, command):
    from sanchopanza.harness import passages_hook as ph

    diff = "".join(f"diff --git a/f{i}.py b/f{i}.py\n+line {i}\n-old {i}\n\n" for i in range(400))
    transcript = _transcript(tmp_path, "review")
    assert await ph.post_tool_use(_bash(tmp_path, transcript, command, diff), _squire()) == {}


async def test_shell_views_of_an_edited_or_announced_file_pass(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    target = tmp_path / "settings.py"
    edit = [{"type": "assistant", "message": {"id": "m2", "role": "assistant", "content": [
        {"type": "tool_use", "id": "e1", "name": "Edit",
         "input": {"file_path": str(target), "old_string": "a", "new_string": "b"}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "e1", "content": "updated"}]}}]
    edited = _transcript(tmp_path, "fix parse_config", extra=edit)
    for command in ("cat settings.py", f"Get-Content {target}", "sed -n 1,400p settings.py",
                    "head -n 500 settings.py", "tail -n 500 settings.py"):  # fmt: skip
        out = await ph.post_tool_use(_bash(tmp_path, edited, command, module_source(),
                                           use_id=command), _squire())  # fmt: skip
        assert out == {}, command
    announced = _transcript(tmp_path, "the parser", "I'll fix settings.py now.")
    out = await ph.post_tool_use(_bash(tmp_path, announced, "cat settings.py", module_source(),
                                       use_id="c2"), _squire())  # fmt: skip
    assert out == {}


# --- 6. the ledger -----------------------------------------------------------------------------


def test_the_ledger_is_written_atomically_and_an_unreadable_one_is_over(tmp_path):
    from sanchopanza.harness import autopilot

    root = tmp_path / ".sanchopanza" / "archive"
    config = autopilot.Config()
    assert not autopilot._over_ceiling(autopilot.read_ledger(root, "s"), config), "none yet"
    autopilot.write_ledger(root, "s", {"usd": 0.01, "decisions": 1, "injected": []})
    folder = root.parent / autopilot.LEDGER
    assert [p.name for p in folder.iterdir()] == ["s.json"], "no temporary file left"
    (folder / "s.json").write_text("{half a fi", encoding="utf-8")
    assert autopilot._over_ceiling(autopilot.read_ledger(root, "s"), config)


async def test_an_unreadable_ledger_ranks_without_the_decider(tmp_path):
    from sanchopanza.harness import autopilot

    root = tmp_path / ".sanchopanza" / "archive"
    (root.parent / autopilot.LEDGER).mkdir(parents=True)
    (root.parent / autopilot.LEDGER / "sess.json").write_text("garbage", encoding="utf-8")
    decider = ScriptedDecider(lambda *_: 0.9)
    squire = _squire(decider)
    await _cut_read(tmp_path, tmp_path / "m.py", module_source(), squire)
    assert not decider.calls
    assert _events(squire, "passages")[0]["ranked_by"] == "bm25 (session ceiling)"


# --- 7. the deadline ---------------------------------------------------------------------------


async def test_a_slow_decider_passes_the_output_whole(tmp_path, monkeypatch):
    from sanchopanza.harness import passages_hook as ph

    class Slow:
        name = "slow"
        accepts_attachments = False

        async def decide(self, point, state, questions):
            await asyncio.sleep(30)

    monkeypatch.setattr(ph, "DECIDE_TIMEOUT_S", 0.05)
    squire = _squire(Slow())
    transcript = _transcript(tmp_path, "fix parse_config", "Reading settings.")
    event = _read(tmp_path, transcript, tmp_path / "m.py", module_source())
    started = time.monotonic()
    assert await ph.post_tool_use(event, squire) == {}
    assert time.monotonic() - started < 5
    assert "deadline" in _events(squire, "passages")[0]["reason"]


# --- 8. install: provider, PreToolUse, timeout -------------------------------------------------


def _install(path: Path, *extra: str) -> int:
    from sanchopanza import cli

    return cli.main(["install", "--path", str(path), "--no-skill", "--no-find", *extra, "--write"])


def test_install_writes_the_guard_the_timeout_and_the_provider(tmp_path):
    from sanchopanza.harness.install_passages import GUARD_HOOKS, PASSAGES_COMMAND

    path = tmp_path / "settings.json"
    assert _install(path, "--passages") == 0
    doc = json.loads(path.read_text("utf-8"))
    assert doc["env"]["SANCHOPANZA_PROVIDER"] == "null"
    for event, matcher in {"PostToolUse": "Bash|PowerShell|Read", **GUARD_HOOKS}.items():
        [entry] = [e for e in doc["hooks"][event]
                   if e["hooks"][0].get("command") == PASSAGES_COMMAND]  # fmt: skip
        assert entry["matcher"] == matcher and entry["hooks"][0]["timeout"] > 0
    assert re.fullmatch(GUARD_HOOKS["PreToolUse"], "Write")
    assert re.fullmatch(GUARD_HOOKS["PreToolUse"], "MultiEdit")
    assert _install(path, "--passages", "--provider", "jev") == 0
    assert json.loads(path.read_text("utf-8"))["env"]["SANCHOPANZA_PROVIDER"] == "jev"
    assert _install(path) == 0
    doc = json.loads(path.read_text("utf-8"))
    assert PASSAGES_COMMAND not in json.dumps(doc)


# --- 10 to 13 ----------------------------------------------------------------------------------


async def test_wants_lets_go_once_the_window_has_passed(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    transcript = _transcript(tmp_path, "make the suite pass", "Running the tests.")
    await ph.post_tool_use(_bash(tmp_path, transcript, "pytest -v", pytest_log()), _squire())
    small = _bash(tmp_path, transcript, "ls", "a\n", use_id="s")
    for i in range(ph.REREQUEST_WINDOW):
        assert ph.wants(small), i
        await ph.post_tool_use({**small, "tool_use_id": f"s{i}"}, _squire())
    assert not ph.wants(small)


def test_a_failed_replace_leaves_no_temporary_file(tmp_path, monkeypatch):
    from sanchopanza.harness import passages_state as st

    root = tmp_path / ".sanchopanza" / "archive"

    def broken(self, target):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", broken)
    st.write(root, "sess", {"calls": 1, "cuts": []})
    folder = root.parent / st.FOLDER
    assert not list(folder.glob("*.tmp"))


def test_an_agent_id_cannot_leave_the_subagents_folder(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    event = {"transcript_path": str(tmp_path / "project" / "sess.jsonl"),
             "agent_id": "../../../evil"}  # fmt: skip
    own = ph.subagent_transcript(event)
    assert own is not None and own.parent == tmp_path / "project" / "sess" / "subagents"


async def test_the_sidecar_hides_secrets_and_old_entries_are_pruned(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    archive = tmp_path / ".sanchopanza" / "archive"
    old = archive / "older-session" / "passages-old.txt"
    old.parent.mkdir(parents=True)
    old.write_text("old", encoding="utf-8")
    keep = archive / "older-session" / "browse-old.txt"
    keep.write_text("not ours", encoding="utf-8")
    stale = time.time() - 8 * 86400
    for path in (old, keep):
        os.utime(path, (stale, stale))
    transcript = _transcript(tmp_path, "make the suite pass", "Running the tests.")
    secret = "sk-ant-api03-" + "x" * 40
    await ph.post_tool_use(_bash(tmp_path, transcript, f"API_KEY={secret} pytest -v",
                                 pytest_log()), _squire())  # fmt: skip
    metas = list((archive / "sess").glob("*.meta.json"))
    assert metas and all(secret not in m.read_text(encoding="utf-8") for m in metas)
    assert not old.exists() and keep.exists()
