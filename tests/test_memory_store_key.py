"""F1 fix 2, the store key ("K1 read + K4 write", `harness.memory_store`).

K1: a session's store is named after the git repository its start folder belongs to (the common
git dir, so sibling worktrees share one store), worked out once per session; outside git, on a
git error or with `SANCHOPANZA_MEMORY_STORE_KEY=folder`, the folder key as before. K4: rules said
in a request are written to the store of the repository its changes landed in. Migration: a
store kept under the old key is merged into the new one the first time a session uses it. Git
is real; no decider is paid."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from sanchopanza import Decision
from sanchopanza.context import episodes as ep
from sanchopanza.harness import memory_hook as mh
from sanchopanza.harness import memory_rules as mr
from sanchopanza.harness import memory_store as ms
from sanchopanza.harness.memory_gate import project_key
from sanchopanza.squire import Squire

from .helpers import yes

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="no git")
RULE = "Ops sets PAYMENT_TIMEOUT by that exact name in every deployment, it can't be renamed."


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE", str(tmp_path / "memory"))
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE_LOG", str(tmp_path / "log.jsonl"))
    for name in ("SANCHOPANZA_MEMORY_STORE_KEY", "SANCHOPANZA_MEMORY_SELECT",
                 "SANCHOPANZA_MEMORY_RULES", "SANCHOPANZA_MEMORY_TREE", "TYPESAFE_API_KEY",
                 "SANCHOPANZA_MEMORY_PROMPT", "SANCHOPANZA_PROVIDER"):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                          text=True)  # fmt: skip
    return done.stdout.strip()


def _repo(path: Path) -> Path:
    (path / "app").mkdir(parents=True)
    (path / "app" / "config.py").write_text("TIMEOUT = env('PAYMENT_TIMEOUT')\n", "utf-8")
    for args in (
        ["init", "-q", "-b", "main"],
        ["config", "user.email", "t@example.org"],
        ["config", "user.name", "t"],
        ["add", "."],
        ["commit", "-qm", "base"],
    ):
        _git(path, *args)
    return path


def _event(root: Path, session: str, cwd: Path | str, folder: str = "p") -> dict[str, Any]:
    return {"session_id": session, "cwd": str(cwd).replace("\\", "/"),
            "transcript_path": str(root / "projects" / folder / f"{session}.jsonl")}  # fmt: skip


def _expected(repo: Path) -> Path:
    top = _git(repo, "rev-parse", "--path-format=absolute", "--show-toplevel")
    return Path(str(ms.store_root())) / project_key(top)


def _counting(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    real = ms.lookup

    def counted(path: str) -> tuple[ms.Repo | None, str]:
        calls.append(path)
        return real(path)

    monkeypatch.setattr(ms, "lookup", counted)
    return calls


def _rows(root: Path) -> list[dict[str, Any]]:
    log = root / "log.jsonl"
    lines = log.read_text("utf-8").splitlines() if log.exists() else []
    return [json.loads(x) for x in lines]


# ---- K1 --------------------------------------------------------------------------------------


@needs_git
def test_two_worktrees_of_one_repository_share_one_store(root: Path) -> None:
    main = _repo(root / "main")
    side = root / "side"
    _git(main, "worktree", "add", "-q", "-b", "side", str(side))
    a = mh.store_for(_event(root, "s1", main, folder="main-folder"))
    b = mh.store_for(_event(root, "s2", side, folder="side-folder"))
    assert a == b == _expected(main)


@needs_git
def test_a_subfolder_of_the_repository_shares_its_store(root: Path) -> None:
    main = _repo(root / "main")
    assert mh.store_for(_event(root, "s1", main / "app", "sub")) == _expected(main)


def test_a_folder_outside_git_keeps_the_folder_key(root: Path) -> None:
    plain = root / "plain"
    plain.mkdir()
    assert mh.store_for(_event(root, "s1", plain)) == ms.store_root() / "p"


@needs_git
def test_a_git_error_keeps_the_folder_key(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main = _repo(root / "main")

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired("git", ms.GIT_SECONDS)

    monkeypatch.setattr(ms.subprocess, "run", broken)
    assert mh.store_for(_event(root, "s1", main)) == ms.store_root() / "p"


@needs_git
def test_git_is_asked_once_per_session(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main = _repo(root / "main")
    calls = _counting(monkeypatch)
    first = {mh.store_for(_event(root, "s1", main)) for _ in range(5)}
    assert len(first) == 1 and len(calls) == 1
    # the agent changed directory: the session keeps the store it started with, no new call
    assert mh.store_for(_event(root, "s1", root)) in first and len(calls) == 1
    mh.store_for(_event(root, "s2", main))
    assert len(calls) == 2


def test_a_failed_lookup_is_kept_too(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _counting(monkeypatch)
    for _ in range(3):
        assert mh.store_for(_event(root, "s1", root / "nowhere")) == ms.store_root() / "p"
    assert len(calls) == 1


@needs_git
def test_the_folder_key_can_be_chosen(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE_KEY", "folder")
    main = _repo(root / "main")
    calls = _counting(monkeypatch)
    assert mh.store_for(_event(root, "s1", main)) == ms.store_root() / "p"
    assert calls == []


def test_without_a_session_or_a_folder_nothing_is_asked(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _counting(monkeypatch)
    transcript = str(root / "projects" / "p" / "t.jsonl")
    assert mh.store_for({"transcript_path": transcript}) == ms.store_root() / "p"
    assert mh.store_for({"cwd": "C:/x/y"}) == ms.store_root() / project_key("C:/x/y")
    assert calls == []


# ---- migration ---------------------------------------------------------------------------------


def _sub(main: Path) -> tuple[Path, str]:
    """A session started in `main/app`: before F1 its store was that folder's key."""
    return main / "app", project_key(str(main / "app").replace("\\", "/"))


def _old_store(name: str, rules: list[dict[str, Any]]) -> Path:
    old = ms.store_root() / name
    mr._save(old, {"rules": rules, "asked": ["old-001"], mr.AUDITED: ["old-002"]})
    record = ep.Episode(session="old", index=1, request="Rename the export.", report="Done.",
                        changed=("app/export.py",), changed_raw=("app/export.py",),
                        at=1_790_000_000.0)  # fmt: skip
    ep.save(old, [record])
    return old


@needs_git
def test_a_store_under_the_old_key_is_read_at_the_first_session(root: Path) -> None:
    main = _repo(root / "main")
    cwd, name = _sub(main)
    _old_store(name, [{"text": RULE, "session": "old", "index": 1, "at": 1_790_000_000.0,
                       "files": ["app/config.py"]}])  # fmt: skip
    out = mh.handle({**_event(root, "s1", cwd, name), "hook_event_name": "SessionStart",
                     "source": "startup"})  # fmt: skip
    assert RULE in out["hookSpecificOutput"]["additionalContext"]
    new = _expected(main)
    data = mr.load(new)
    assert [r["text"] for r in data["rules"]] == [RULE]
    assert data["asked"] == ["old-001"] and data[mr.AUDITED] == ["old-002"]
    assert [e.key for e in ep.load(new)] == ["old-001"] and "old-001" in ep.index_of(new)


@needs_git
def test_a_worktrees_old_store_is_its_own_and_is_read(root: Path) -> None:
    main = _repo(root / "main")
    side = root / "side"
    _git(main, "worktree", "add", "-q", "-b", "side", str(side))
    name = project_key(str(side).replace("\\", "/"))
    _old_store(name, [{"text": RULE, "at": 1.0}])
    assert mh.store_for(_event(root, "s1", side, name)) == _expected(main)
    assert [r["text"] for r in mr.load(_expected(main))["rules"]] == [RULE]


@needs_git
def test_another_checkouts_folder_key_is_never_merged(root: Path) -> None:
    """Review of F1, H1: launched in A, moved into B, cleared (a new session id): the transcript
    folder is still A's. A's store must not be merged into B's; the skip is logged."""
    a, b = _repo(root / "a"), _repo(root / "b")
    name = project_key(str(a).replace("\\", "/"))
    _old_store(name, [{"text": RULE, "at": 1.0}])
    assert mh.store_for(_event(root, "s1", b, name)) == _expected(b)
    assert mr.load(_expected(b))["rules"] == [] and ep.load(_expected(b)) == []
    [row] = [r for r in _rows(root) if r.get("adopt") == "skipped"]
    assert row["old"] == name and row["new"] == _expected(b).name


def test_the_folder_key_must_be_the_cwds_or_a_parent_up_to_the_top() -> None:
    top = "C:/w/repo"
    assert ms.own_folder_key(project_key("C:/w/repo/app/x"), "C:/w/repo/app/x", top)
    assert ms.own_folder_key(project_key("C:/w/repo/app"), "C:/w/repo/app/x", top)
    assert ms.own_folder_key(project_key("C:/w/repo"), "C:/w/repo/app/x", top)
    assert not ms.own_folder_key(project_key("C:/w"), "C:/w/repo/app/x", top)
    assert not ms.own_folder_key(project_key("C:/w/other"), "C:/w/repo", top)


@needs_git
def test_the_merge_keeps_both_sides_and_runs_again_only_when_the_old_store_moves(
    root: Path,
) -> None:
    main = _repo(root / "main")
    cwd, name = _sub(main)
    old = _old_store(name, [{"text": RULE, "session": "old", "index": 1, "at": 1.0}])
    new = _expected(main)
    mine = "Every migration has to be reversible, with a working down step."
    mr._save(new, {"rules": [{"text": mine, "session": "n", "index": 1, "at": 5.0}],
                   "asked": [], mr.AUDITED: []})  # fmt: skip
    mh.store_for(_event(root, "s1", cwd, name))
    assert [r["text"] for r in mr.load(new)["rules"]] == [mine, RULE]
    mr._save(new, {**mr.load(new), "rules": mr.load(new)["rules"][:1]})  # gone from the new one
    mh.store_for(_event(root, "s2", cwd, name))
    assert [r["text"] for r in mr.load(new)["rules"]] == [mine]  # the old store did not move
    later = "Never print from the cron job."
    data = mr.load(old)
    mr._save(old, {**data, "rules": [{"text": later, "at": 9.0}, *data["rules"]]})
    mh.store_for(_event(root, "s3", cwd, name))
    assert [r["text"] for r in mr.load(new)["rules"]] == [later, mine, RULE]


@needs_git
def test_two_first_sessions_adopting_at_once_merge_once(root: Path) -> None:
    import threading

    main = _repo(root / "main")
    cwd, name = _sub(main)
    rules = [{"text": f"Rule {n} can never change in this project.", "at": float(n)}
             for n in range(20)]  # fmt: skip
    _old_store(name, rules)
    gate = threading.Barrier(4)
    found: list[Path] = []

    def first(session: str) -> None:
        gate.wait()
        found.append(mh.store_for(_event(root, session, cwd, name)))

    threads = [threading.Thread(target=first, args=(f"s{n}",)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    new = _expected(main)
    assert found == [new] * 4
    texts = [r["text"] for r in mr.load(new)["rules"]]
    assert sorted(texts) == sorted(r["text"] for r in rules) and len(texts) == len(set(texts))
    assert [e.key for e in ep.load(new)] == ["old-001"]
    assert list(json.loads((new / ms.ADOPTED).read_text("utf-8"))) == [name]


@needs_git
def test_a_session_already_running_at_the_upgrade_keeps_its_state(root: Path) -> None:
    main = _repo(root / "main")
    cwd, name = _sub(main)
    old = _old_store(name, [])
    ep.write_private(old / mh.SHOWN / "s1.json", json.dumps({"boundaries": 0, "keys": ["k"]}))
    ep.write_private(old / mh.TREE / "s1.json", json.dumps({"index": 2, "cwd": "x"}))
    store = mh.store_for(_event(root, "s1", cwd, name))
    assert mh.shown_since_compaction(store, "s1", 0) == frozenset({"k"})
    assert (store / mh.TREE / "s1.json").exists()


# ---- why a lookup failed --------------------------------------------------------------------


def test_a_cached_lookup_failure_says_why(root: Path) -> None:
    plain = root / "plain"
    plain.mkdir()
    mh.store_for(_event(root, "s1", plain))
    mh.store_for(_event(root, "s1", plain))
    rows = [r for r in _rows(root) if r.get("event") == "store"]
    assert len(rows) == 1 and rows[0]["key"] == "folder" and rows[0]["why"]
    assert ms.session_key(ms.store_root(), "s1")["why"] == rows[0]["why"]


def test_git_older_than_2_31_falls_back_and_says_so(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def old_git(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        # rev-parse echoes an option it does not know
        out = b"--path-format=absolute\n.git\nC:/w/repo\n"
        return subprocess.CompletedProcess(args, 0, out, b"")

    monkeypatch.setattr(ms.subprocess, "run", old_git)
    assert mh.store_for(_event(root, "s1", root)) == ms.store_root() / "p"
    [row] = [r for r in _rows(root) if r.get("event") == "store"]
    assert row["why"] == ms.OLD_GIT


# ---- K4 ----------------------------------------------------------------------------------------


@needs_git
def test_a_request_lands_in_the_repository_it_wrote_to(root: Path) -> None:
    a, b = _repo(root / "a"), _repo(root / "b")
    start = mh.store_for(_event(root, "s1", a))
    there = ep.Episode(session="s1", index=1, request="x", report="y",
                       changed_raw=(f"{b}/app/config.py".replace("\\", "/"),))  # fmt: skip
    here = ep.Episode(session="s1", index=2, request="x", report="y",
                      changed_raw=("app/config.py",))  # fmt: skip
    nothing = ep.Episode(session="s1", index=3, request="x", report="y")
    out = ms.landing(start, "s1", str(a), [there, here, nothing])
    assert {k: [e.index for e in v] for k, v in out.items()} == {_expected(b): [1],
                                                                 start: [2, 3]}  # fmt: skip


@needs_git
def test_landing_asks_git_only_outside_the_start_checkout(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _repo(root / "a")
    start = mh.store_for(_event(root, "s1", a))
    calls = _counting(monkeypatch)
    inside = ep.Episode(session="s1", index=1, request="x", report="y",
                        changed_raw=("app/config.py", f"{a}/app/other.py"))  # fmt: skip
    assert ms.landing(start, "s1", str(a), [inside]) == {start: [inside]}
    assert calls == []
    many = [ep.Episode(session="s1", index=i, request="x", report="y",
                       changed_raw=(str(root / f"d{i}" / "f.py"),)) for i in range(9)]  # fmt: skip
    ms.landing(start, "s1", str(a), many)
    assert len(calls) <= ms.LANDING_DIRS


class Standing:
    """Every sentence with "can't" is a standing rule; nothing else is answered."""

    name = "scripted"
    accepts_attachments = False

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        answers = {"rule": yes(0.9 if "can't" in state["sentence"] else 0.1)} \
            if "rule" in questions else {}  # fmt: skip
        return Decision(point=point, answers=answers, provider=self.name, model="scripted-1")


@needs_git
def test_a_rule_said_while_writing_another_repository_is_kept_there(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SANCHOPANZA_PROVIDER", "scripted")
    monkeypatch.setattr("sanchopanza.harness.claude_code.squire_from_env",
                        lambda env=None, redact=False: Squire(Standing()))  # fmt: skip
    a, b = _repo(root / "a"), _repo(root / "b")
    base = _event(root, "s1", a)
    target = f"{b}/app/config.py".replace("\\", "/")
    text = f"Fix the timeout in the other repo. {RULE}"
    mh.handle({**base, "hook_event_name": "UserPromptSubmit", "prompt": text})
    use = {
        "type": "tool_use",
        "id": "t1",
        "name": "Edit",
        "input": {"file_path": target, "old_string": "a", "new_string": "b"},
    }
    entries = [{"type": "user", "cwd": base["cwd"], "timestamp": "2026-10-05T10:00:00Z",
                "message": {"role": "user", "content": text}},
               {"type": "assistant", "message": {"role": "assistant", "content": [use]}},
               {"type": "user", "message": {"role": "user", "content": [
                   {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}},
               {"type": "assistant", "message": {"role": "assistant", "content": [
                   {"type": "text", "text": "Done."}]}}]  # fmt: skip
    path = Path(base["transcript_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    assert mh.handle({**base, "hook_event_name": "Stop"}) == {}
    assert [r["text"] for r in mr.load(_expected(b))["rules"]] == [RULE]
    assert mr.load(_expected(a))["rules"] == []
    assert mr.load(_expected(b))["asked"] == ["s1-001"]


@needs_git
def test_a_requests_store_is_fixed_the_first_time_it_is_decided(root: Path) -> None:
    """Review of F1, M4: the record later gains files in A (the tree merged in); the request's
    rules still go where they went first, so it is never asked twice nor written twice."""
    a, b = _repo(root / "a"), _repo(root / "b")
    start = mh.store_for(_event(root, "s1", a))
    in_b = f"{b}/app/config.py".replace("\\", "/")
    first = ep.Episode(session="s1", index=1, request="x", report="y", changed_raw=(in_b,))
    assert list(ms.landing(start, "s1", str(a), [first])) == [_expected(b)]
    later = ep.Episode(session="s1", index=1, request="x", report="y",
                       changed_raw=(in_b, "app/one.py", "app/two.py"))  # fmt: skip
    assert list(ms.landing(start, "s1", str(a), [later])) == [_expected(b)]


@needs_git
def test_extract_landed_asks_a_request_once_whatever_its_files_become(root: Path) -> None:
    import asyncio

    class Counting(Standing):
        def __init__(self) -> None:
            self.asked = 0

        async def decide(self, point: str, state: Any, questions: Any) -> Decision:
            self.asked += "rule" in questions
            return await super().decide(point, state, questions)

    a, b = _repo(root / "a"), _repo(root / "b")
    start = mh.store_for(_event(root, "s1", a))
    in_b = f"{b}/app/config.py".replace("\\", "/")
    decider = Counting()
    once = ep.Episode(session="s1", index=1, request=RULE, report="y", changed_raw=(in_b,))
    added = asyncio.run(mr.extract_landed(Squire(decider), start, "s1", str(a), [once]))
    grown = ep.Episode(session="s1", index=1, request=RULE, report="y",
                       changed_raw=(in_b, "app/one.py", "app/two.py"))  # fmt: skip
    again = asyncio.run(mr.extract_landed(Squire(decider), start, "s1", str(a), [grown]))
    assert added == [RULE] and again == [] and decider.asked == 1
    assert mr.load(start)["rules"] == [] and mr.load(start)["asked"] == []


def test_without_a_session_key_everything_lands_in_the_start(root: Path) -> None:
    start = ms.store_root() / "p"
    elsewhere = ep.Episode(session="s9", index=1, request="x", report="y",
                           changed_raw=("C:/far/away/f.py",))  # fmt: skip
    assert ms.landing(start, "s9", "C:/x", [elsewhere]) == {start: [elsewhere]}
