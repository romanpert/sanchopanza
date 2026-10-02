"""v7 standing rules (`harness.memory_rules`, `points.rules`): extracted from the person's words
at Stop, given at every session start, and a request's diff held against them before it stops.
A scripted decider stands in for Jev; git is real."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from sanchopanza.context import episodes as ep
from sanchopanza.harness import memory_hook as mh
from sanchopanza.harness import memory_rules as mr
from sanchopanza.points.rules import sentences
from sanchopanza.squire import Squire

from .context_helpers import ScriptedDecider

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="no git")
RULE = "Ops sets PAYMENT_TIMEOUT by that exact name in every deployment, it can't be renamed."
MINE = ["app/config.py"]


def by_words(point: str, key: str, state: Any) -> float | None:
    """Standing: a sentence with 'can't' or 'never' is a rule. Kept: a change that drops the
    protected name breaks it."""
    if key == "rule":
        return 0.9 if ("can't" in state["sentence"] or "never" in state["sentence"]) else 0.1
    if key == "kept":
        return 0.1 if "APP_PAYMENT_TIMEOUT" in state["change"] else 0.9
    return None


def squire() -> Squire:
    return Squire(ScriptedDecider(by_words))


def episode(text: str, session: str = "s1", index: int = 1) -> ep.Episode:
    return ep.Episode(session=session, index=index, request=text, report="done",
                      changed=("app/config.py",), at=1_790_900_000.0)  # fmt: skip


def test_sentences_split_after_a_stop_whatever_case_follows() -> None:
    text = "Add items_count to order_dict, with a test. legacy_total stays, e.g. for the app."
    assert sentences(text) == ["Add items_count to order_dict, with a test.",
                               "legacy_total stays, e.g. for the app."]  # fmt: skip


def test_rules_come_from_the_persons_sentences_once_per_request(tmp_path: Path) -> None:
    text = f"Make load() raise ValueError on a bad APP_RETRIES. {RULE}"
    added = asyncio.run(mr.extract(squire(), tmp_path, [episode(text)]))
    assert added == [RULE]
    again = asyncio.run(mr.extract(squire(), tmp_path, [episode(text)]))
    assert again == []
    data = mr.load(tmp_path)
    assert [r["text"] for r in data["rules"]] == [RULE] and data["asked"] == ["s1-001"]


def test_the_rules_are_given_in_the_persons_words_newest_first(tmp_path: Path) -> None:
    assert mr.render(tmp_path) == ""
    asyncio.run(mr.extract(squire(), tmp_path, [episode(RULE)]))
    asyncio.run(mr.extract(squire(), tmp_path, [
        ep.Episode(session="s2", index=1, request="We never print from the cron job.",
                   report="", at=1_790_990_000.0)]))  # fmt: skip
    text = mr.render(tmp_path)
    assert text.startswith(mr.HEADER) and text.endswith(mr.CLOSING)
    assert text.index("never print") < text.index(RULE)
    assert "while changing app/config.py" in text


def _repo(root: Path) -> str:
    (root / "app").mkdir(parents=True)
    (root / "app" / "config.py").write_text(
        "def load():\n    return {\n    'timeout': env('PAYMENT_TIMEOUT'),\n    }\n", "utf-8")
    for args in (["init", "-q"], ["config", "user.email", "t@example.org"],
                 ["config", "user.name", "t"], ["add", "."], ["commit", "-qm", "base"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()  # fmt: skip
    return head


@needs_git
def test_a_diff_that_breaks_a_rule_is_found_once_per_request(tmp_path: Path) -> None:
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    asyncio.run(mr.extract(squire(), store, [episode(RULE, session="old")]))
    (repo / "app" / "config.py").write_text(
        "def load():\n    return {\n    'timeout': env('APP_PAYMENT_TIMEOUT'),\n    }\n", "utf-8")
    broken, found = asyncio.run(mr.audit(squire(), store, "new", 1, str(repo), head, MINE))
    assert [r["text"] for r in broken] == [RULE] and list(found.values()) == [0.1]
    assert asyncio.run(mr.audit(squire(), store, "new", 1, str(repo), head, MINE)) == ([], {})
    assert "in their words" in mr.block_reason(broken) and RULE in mr.block_reason(broken)


@needs_git
def test_a_new_file_git_does_not_track_is_part_of_the_change(tmp_path: Path) -> None:
    # sim of 2026-10-02: a new module was invisible to `git diff`, so the check never ran
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    asyncio.run(mr.extract(squire(), store, [episode(RULE, session="old")]))
    (repo / "app" / "mailer.py").write_text("HOST = env('APP_PAYMENT_TIMEOUT')\n", "utf-8")
    (repo / ".env.local").write_text("SECRET=1\n", "utf-8")
    mine = ["app/mailer.py", ".env.local"]
    assert "+++ b/app/mailer.py (new file)" in mr._diff(str(repo), head, mine)
    assert ".env.local" not in mr._diff(str(repo), head, mine)
    broken, _ = asyncio.run(mr.audit(squire(), store, "new", 1, str(repo), head, mine))
    assert [r["text"] for r in broken] == [RULE]


@needs_git
def test_a_rule_is_not_held_against_the_request_that_stated_it(tmp_path: Path) -> None:
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    asyncio.run(mr.extract(squire(), store, [episode(RULE, session="s1", index=1)]))
    (repo / "app" / "config.py").write_text("def load():\n    return {}\n", "utf-8")
    assert asyncio.run(mr.audit(squire(), store, "s1", 1, str(repo), head, MINE)) == ([], {})


@needs_git
def test_no_change_no_question(tmp_path: Path) -> None:
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    asyncio.run(mr.extract(squire(), store, [episode(RULE, session="old")]))
    decider = ScriptedDecider(by_words)
    assert asyncio.run(mr.audit(Squire(decider), store, "new", 1, str(repo), head, MINE)) == (
        [], {})
    assert decider.calls == []


# ---- through the hook ----------------------------------------------------------------------------


@pytest.fixture
def hook_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE", str(tmp_path / "memory"))
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE_LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("SANCHOPANZA_PROVIDER", "scripted")
    for name in ("SANCHOPANZA_MEMORY_SELECT", "SANCHOPANZA_MEMORY_RULES", "TYPESAFE_API_KEY",
                 "SANCHOPANZA_MEMORY_TREE", "SANCHOPANZA_MEMORY_PROMPT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("sanchopanza.harness.claude_code.squire_from_env",
                        lambda env=None, redact=False: squire())  # fmt: skip
    return tmp_path


def _transcript(path: Path, cwd: str, text: str, edit: bool) -> Path:
    use = {"type": "tool_use", "id": "t1", "name": "Edit",
           "input": {"file_path": f"{cwd}/app/config.py", "old_string": "a", "new_string": "b"}}
    entries = [{"type": "user", "cwd": cwd, "timestamp": "2026-10-02T10:00:00Z",
                "message": {"role": "user", "content": text}}]  # fmt: skip
    if edit:
        entries += [{"type": "assistant", "message": {"role": "assistant", "content": [use]}},
                    {"type": "user", "message": {"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": "t1",
                         "content": "ok"}]}}]  # fmt: skip
    entries.append({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "Done."}]}})  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


@needs_git
def test_the_hook_learns_a_rule_gives_it_at_the_next_start_and_sends_a_break_back(
    hook_env: Path,
) -> None:
    repo = hook_env / "repo"
    _repo(repo)
    cwd = str(repo).replace("\\", "/")
    project = hook_env / "projects" / "p"
    first = {"session_id": "s1", "cwd": cwd, "transcript_path": str(project / "s1.jsonl")}
    text1 = f"Make load() raise ValueError on a bad APP_RETRIES. {RULE}"
    mh.handle({**first, "hook_event_name": "UserPromptSubmit", "prompt": text1})
    _transcript(project / "s1.jsonl", cwd, text1, edit=False)
    assert mh.handle({**first, "hook_event_name": "Stop"}) == {}

    second = {"session_id": "s2", "cwd": cwd, "transcript_path": str(project / "s2.jsonl")}
    out = mh.handle({**second, "hook_event_name": "SessionStart", "source": "startup"})
    assert RULE in out["hookSpecificOutput"]["additionalContext"]
    text2 = "Give every environment variable an APP_ prefix."
    mh.handle({**second, "hook_event_name": "UserPromptSubmit", "prompt": text2})
    (repo / "app" / "config.py").write_text(
        "def load():\n    return {\n    'timeout': env('APP_PAYMENT_TIMEOUT'),\n    }\n", "utf-8")
    _transcript(project / "s2.jsonl", cwd, text2, edit=True)
    sent = mh.handle({**second, "hook_event_name": "Stop"})
    assert sent["decision"] == "block" and RULE in sent["reason"]
    again = mh.handle({**second, "hook_event_name": "Stop", "stop_hook_active": True})
    assert again == {}


def test_the_rules_can_be_turned_off(hook_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_RULES", "off")
    store = hook_env / "memory" / "p"
    asyncio.run(mr.extract(squire(), store, [episode(RULE)]))
    event = {"session_id": "s", "cwd": "C:/x", "transcript_path": str(hook_env / "projects" /
             "p" / "s.jsonl"), "hook_event_name": "SessionStart", "source": "startup"}  # fmt: skip
    assert mh.handle(event) == {}


# ---- review of v7 (2026-10-02): H1, M4, M7 -------------------------------------------------------


@needs_git
def test_review_h1_a_persons_uncommitted_edit_is_not_the_requests(tmp_path: Path) -> None:
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    asyncio.run(mr.extract(squire(), store, [episode(RULE, session="old")]))
    (repo / "app" / "config.py").write_text("x = env('APP_PAYMENT_TIMEOUT')\n", "utf-8")
    (repo / "app" / "other.py").write_text("y = 1\n", "utf-8")
    decider = ScriptedDecider(by_words)
    out = asyncio.run(mr.audit(Squire(decider), store, "new", 1, str(repo), head,
                               ["app/other.py"]))  # fmt: skip
    assert out[0] == [] and all("APP_PAYMENT" not in c[1]["change"] for c in decider.calls)
    assert asyncio.run(mr.audit(squire(), store, "new", 2, str(repo), head, [])) == ([], {})


def test_review_m4_tagged_blocks_and_long_pastes_give_no_rule() -> None:
    text = ("Fix the importer for empty rows.\n<bash-stdout>\n"
            "Always run ./setup.sh before committing.\n</bash-stdout>\n"
            "<ide_selection>Never use the cache layer anywhere.</ide_selection>")
    assert sentences(text) == ["Fix the importer for empty rows."]
    paste = "Look at this log:\n" + "\n".join(f"line {i}: never retry the call" for i in range(40))
    assert len(sentences(paste)) <= 20


def test_review_m4_the_stop_hooks_own_feedback_is_not_a_request() -> None:
    assert not ep.is_request({"role": "user", "content": "Stop hook feedback: [sanchopanza ..."})


def test_review_m7_a_request_the_decider_failed_on_is_asked_again(tmp_path: Path) -> None:
    def down(point: str, key: str, state: Any) -> float | None:
        return None

    asyncio.run(mr.extract(Squire(ScriptedDecider(down)), tmp_path, [episode(RULE)]))
    assert mr.load(tmp_path)["asked"] == []
    assert asyncio.run(mr.extract(squire(), tmp_path, [episode(RULE)])) == [RULE]
