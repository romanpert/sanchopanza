"""The `+commit` label (benchmarks/memory_real/commit_label.py): files a request committed, from
git, never from the shell parser. Temporary repositories, no network. The cases below the first
block are the adversarial review's (2026-10-01): each used to credit a commit that was not the
request's."""

from __future__ import annotations

import os
import pathlib
import subprocess
import time

import pytest

from sanchopanza.context import episodes as ep

from .helpers import bench_module

ROOT = pathlib.Path(__file__).resolve().parents[1]
cl = bench_module(ROOT / "benchmarks" / "memory_real", "commit_label")

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t"}  # fmt: skip
SUBJECT_A, SUBJECT_B = "feat: add module a", "feat: add module b"


def _git(repo: pathlib.Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env=ENV, check=True)  # fmt: skip
    return done.stdout


def _clear() -> None:
    for f in (cl.root_of, cl.full_sha, cl.reflog, cl.files_of, cl.subject_of):
        f.cache_clear()


def _commit(repo: pathlib.Path, rel: str, subject: str, *extra: str) -> str:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(f"# {subject}\n")
    _git(repo, "add", "-A")
    return _git(repo, "commit", *extra, "-m", subject).splitlines()[0]


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> tuple[pathlib.Path, str, str]:
    """A repository with two commits: (root, the first's output line, the second's)."""
    _git(tmp_path, "init", "-q", "-b", "main")
    first = _commit(tmp_path, "src/a.py", SUBJECT_A)
    second = _commit(tmp_path, "src/b.py", SUBJECT_B)
    _clear()
    return tmp_path, first, second


def _now() -> list[float]:
    return [time.time() - 60, time.time() + 60]


def _item(cwd: str, touches: list[dict], pool: list[ep.Episode] = (), window=None) -> dict:
    return {"cwd": cwd, "touches": touches, "pool": list(pool),
            "window": _now() if window is None else window,
            "labels": {r.key: "none" for r in pool}}  # fmt: skip


def _record(index: int, changed: tuple[str, ...]) -> ep.Episode:
    return ep.Episode(session="s0", index=index, request="r", report="", changed=changed,
                      at=1.0, changed_raw=changed)  # fmt: skip


def _files(item: dict) -> set[str]:
    return cl.committed(item)[0]


@pytest.mark.parametrize(
    ("line", "found"),
    [
        ("[main 1a2b3c4] fix: x", ["1a2b3c4"]),
        ("[main (root-commit) 1a2b3c4] first", ["1a2b3c4"]),
        ("[detached HEAD 0123abc] wip", ["0123abc"]),
        ("[feat/x-y 89abcdef0] y\n 1 file changed", ["89abcdef0"]),
        ("see [main 1a2b3c4] in the log", []),
        ("[1, 2, 3] list", []),
        ("[main abc] too short", []),
    ],
    ids=["plain", "root", "detached", "slash", "mid", "list", "short"],
)
def test_hashes(line: str, found: list[str]) -> None:
    assert cl.hashes(line) == found


def test_committed_files_from_git(repo) -> None:
    root, _, second = repo
    files, counts = cl.committed(_item(str(root), [{"command": "git commit", "output": second}]))
    assert files == {"src/b.py"} and counts["found"] == 1


def test_relative_to_a_subfolder_cwd(repo) -> None:
    root, _, second = repo
    assert _files(_item(str(root / "src"), [{"command": "git commit", "output": second}])) == {
        "b.py"
    }


def test_cd_into_the_repo(repo, tmp_path_factory) -> None:
    root, _, second = repo
    elsewhere = tmp_path_factory.mktemp("other")
    command = f'cd "{root.as_posix()}" && git commit -m x'
    files = _files(_item(str(elsewhere), [{"command": command, "output": second}]))
    assert any(f.endswith("src/b.py") for f in files)


def test_quiet_commit_then_oneline_log(repo) -> None:
    root, _, _ = repo
    command = f'git commit -q -m "{SUBJECT_B}" && git log --oneline -2'
    item = _item(str(root), [{"command": command, "output": _git(root, "log", "--oneline", "-2")}])
    assert _files(item) == {"src/b.py"}


def test_oneline_log_without_a_commit_command_is_ignored(repo) -> None:
    root, _, _ = repo
    log = _git(root, "log", "--oneline", "-2")
    assert _files(_item(str(root), [{"command": "git log --oneline -2", "output": log}])) == set()


def test_commit_and_log_in_separate_calls(repo) -> None:
    root, _, _ = repo
    item = _item(str(root), [{"command": f'git commit -q -m "{SUBJECT_B}"', "output": ""},
                             {"command": "git log --oneline -1",
                              "output": _git(root, "log", "--oneline", "-1")}])  # fmt: skip
    assert _files(item) == {"src/b.py"}


def test_unknown_hash_is_not_found(repo) -> None:
    root, _, _ = repo
    files, counts = cl.committed(_item(str(root), [{"command": "git commit",
                                                    "output": "[main deadbee] x"}]))  # fmt: skip
    assert files == set() and counts["refused: not in a repository"] == 1


def test_label_turns_none_into_file_only_for_committed_files(repo) -> None:
    root, _, second = repo
    hit, miss = _record(1, ("src/b.py",)), _record(2, ("src/a.py",))
    item = _item(str(root), [{"command": "git commit", "output": second}], [hit, miss])
    (labelled,), has, counts = cl.with_commit_label([item])
    assert has == [True] and counts["found"] == 1
    assert labelled["labels"] == {hit.key: "file", miss.key: "none"}
    assert item["labels"][hit.key] == "none"  # the input is not changed


def test_no_commit_keeps_the_sealed_label(repo) -> None:
    root, _, _ = repo
    rec = _record(1, ("src/b.py",))
    (labelled,), has, _ = cl.with_commit_label(
        [_item(str(root), [{"command": "ls", "output": "src"}], [rec])]
    )
    assert has == [False] and labelled["labels"] == {rec.key: "none"}


# ---- the review's cases ------------------------------------------------------------------------


def test_an_older_commit_whose_subject_is_inside_the_new_one_is_not_credited(repo) -> None:
    root, _, _ = repo
    _commit(root, "old.py", "fix: tests")
    _commit(root, "new.py", "fix: tests for v6")
    _clear()
    command = 'git commit -q -m "fix: tests for v6" && git log --oneline -2'
    item = _item(str(root), [{"command": command, "output": _git(root, "log", "--oneline", "-2")}])
    assert _files(item) == {"new.py"}


def test_a_commit_before_the_request_window_is_not_credited(repo) -> None:
    """`nothing to commit` and then the log: the previous request's commit."""
    root, _, _ = repo
    command = f'git commit -m "{SUBJECT_B}"; git log --oneline -1'
    output = "nothing to commit\n" + _git(root, "log", "--oneline", "-1")
    later = [time.time() + 3600, time.time() + 3700]
    files, counts = cl.committed(_item(str(root), [{"command": command, "output": output}],
                                       window=later))  # fmt: skip
    assert files == set()
    assert counts["refused: not this worktree's commit in the window"] == 1


def test_an_amend_is_not_credited(repo) -> None:
    root, _, _ = repo
    (root / "tiny.py").write_text("x\n")
    _git(root, "add", "-A")
    line = _git(root, "commit", "--amend", "--no-edit").splitlines()[0]
    _clear()
    files, counts = cl.committed(_item(str(root), [{"command": "git commit --amend --no-edit",
                                                    "output": line}]))  # fmt: skip
    assert files == set() and counts["found"] == 0


def test_a_cherry_pick_is_not_credited(repo) -> None:
    root, _, _ = repo
    _git(root, "checkout", "-q", "-b", "side")
    _commit(root, "side.py", "feat: side work")
    sha = _git(root, "rev-parse", "HEAD").strip()
    _git(root, "checkout", "-q", "main")
    _commit(root, "main_only.py", "feat: main moves on")  # else the pick is the same commit
    line = _git(root, "cherry-pick", sha).splitlines()[0]
    _clear()
    files = _files(_item(str(root), [{"command": f"git cherry-pick {sha}", "output": line}]))
    assert files == set()


def test_a_sibling_worktree_commit_is_not_credited_to_this_one(repo, tmp_path_factory) -> None:
    root, _, _ = repo
    sibling = tmp_path_factory.mktemp("wt") / "b"
    _git(root, "worktree", "add", "-q", "-b", "other", str(sibling))
    line = _commit(sibling, "shared.py", "feat: in worktree b")
    _clear()
    command = f'git -C "{sibling.as_posix()}" commit -m "feat: in worktree b"'
    assert _files(_item(str(root), [{"command": command, "output": line}])) == set()


def test_home_and_bash_drive_folders() -> None:
    home = pathlib.Path.home().as_posix()
    assert cl.folder("~/x") == f"{home}/x"
    assert cl.folder("$HOME/.claude") == f"{home}/.claude"
    assert cl.folder("%USERPROFILE%/a") == f"{home}/a"
    if os.name == "nt":
        assert cl.folder("/c/Users/x") == "c:/Users/x"


def test_request_windows_from_a_transcript(tmp_path, monkeypatch) -> None:
    """A request runs from its prompt's stamp to the next prompt's; the last to the file's end."""
    import json

    def user(text: str, stamp: str) -> dict:
        return {"type": "user", "timestamp": stamp, "message": {"role": "user", "content": text}}

    def reply(stamp: str) -> dict:
        return {
            "type": "assistant",
            "timestamp": stamp,
            "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
        }

    entries = [user("one", "2026-10-01T10:00:00Z"), reply("2026-10-01T10:05:00Z"),
               user("two", "2026-10-01T11:00:00Z"), reply("2026-10-01T11:30:00Z")]  # fmt: skip
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "sid.jsonl").write_text("".join(json.dumps(e) + "\n" for e in entries), "utf-8")
    monkeypatch.setattr(cl, "PROJECTS", tmp_path)
    cl._windows.cache_clear()
    windows = cl._windows("sid")
    cl._windows.cache_clear()
    assert windows[2][1] - windows[2][0] == 1800 and windows[1][1] == windows[2][0]
    assert windows[2][0] - windows[1][0] == 3600


def test_double_printing_counts_one_commit(repo) -> None:
    root, _, second = repo
    item = _item(str(root), [{"command": f'git commit -m "{SUBJECT_B}"', "output": second},
                             {"command": "git log --oneline -1",
                              "output": _git(root, "log", "--oneline", "-1")}])  # fmt: skip
    files, counts = cl.committed(item)
    assert files == {"src/b.py"} and counts["considered"] == 1 and counts["found"] == 1
