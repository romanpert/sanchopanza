"""What a request changed in the working tree, whatever tool changed it (v6, 2026-10-01: in
phase B2 Sonnet 5.5 edited through `python - <<E` and `sed -i` in 70-100 % of its requests, and
records built from file tools said those requests changed nothing). Real git, temp repos."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from sanchopanza.context import episodes as ep
from sanchopanza.context import worktree as wt

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

OLD = "def parse(text):\n    return text.split(',')\n"
NEW_LINE = "    return [part.strip() for part in text.split(',')]"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    (root / "pkg" / "parse.py").write_text(OLD, encoding="utf-8")
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    return root


def test_no_git_no_snapshot(tmp_path: Path) -> None:
    assert wt.snapshot(str(tmp_path)) is None


def test_a_file_changed_by_any_means_is_found_with_the_lines_it_gained(repo: Path) -> None:
    before = wt.snapshot(str(repo))
    assert before is not None and before.files == {}
    (repo / "pkg" / "parse.py").write_text(f"def parse(text):\n{NEW_LINE}\n", encoding="utf-8")
    (repo / "pkg" / "new_module.py").write_text("VALUE_FOR_THE_NEW_MODULE = 42\n", "utf-8")
    after = wt.snapshot(str(repo))
    found = dict(wt.changes(before, after))
    assert set(found) == {"pkg/parse.py", "pkg/new_module.py"}
    assert found["pkg/parse.py"] == (ep.line_print(NEW_LINE),)
    assert found["pkg/new_module.py"] == (ep.line_print("VALUE_FOR_THE_NEW_MODULE = 42"),)


def test_a_file_dirty_before_counts_only_what_this_request_added(repo: Path) -> None:
    (repo / "pkg" / "parse.py").write_text(f"def parse(text):\n{NEW_LINE}\n", encoding="utf-8")
    before = wt.snapshot(str(repo))
    untouched = wt.snapshot(str(repo))
    assert wt.changes(before, untouched) == []  # dirty, but not by this request
    added = "    raise ValueError('empty text given to parse')"
    (repo / "pkg" / "parse.py").write_text(f"def parse(text):\n{added}\n{NEW_LINE}\n", "utf-8")
    found = dict(wt.changes(before, wt.snapshot(str(repo))))
    assert found == {"pkg/parse.py": (ep.line_print(added),)}


def test_a_commit_inside_the_request_and_a_revert_are_changes(repo: Path) -> None:
    before = wt.snapshot(str(repo))
    (repo / "pkg" / "parse.py").write_text(f"def parse(text):\n{NEW_LINE}\n", encoding="utf-8")
    git(repo, "commit", "-qam", "fix")
    found = dict(wt.changes(before, wt.snapshot(str(repo))))
    assert found == {"pkg/parse.py": (ep.line_print(NEW_LINE),)}
    (repo / "README.md").write_text("# demo, edited\n", encoding="utf-8")
    dirty = wt.snapshot(str(repo))
    git(repo, "checkout", "-q", "README.md")
    assert dict(wt.changes(dirty, wt.snapshot(str(repo)))) == {"README.md": ()}


def test_a_subfolder_cwd_sees_the_whole_repository_relative_to_its_root(repo: Path) -> None:
    before = wt.snapshot(str(repo / "pkg"))
    (repo / "README.md").write_text("# demo, a longer heading now\n", encoding="utf-8")
    after = wt.snapshot(str(repo / "pkg"))
    assert before is not None and Path(before.root) == repo.resolve()
    assert [p for p, _ in wt.changes(before, after)] == ["README.md"]


def test_a_huge_file_is_named_without_prints_and_the_file_cap_holds(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wt, "MAX_BYTES", 64)
    monkeypatch.setattr(wt, "MAX_FILES", 2)
    (repo / "big.txt").write_text("a fairly long line of text\n" * 10, encoding="utf-8")
    after = wt.snapshot(str(repo))
    assert after is not None and after.files["big.txt"].startswith("stat:")
    assert after.prints["big.txt"] == ()
    for n in range(4):
        (repo / f"f{n}.py").write_text(f"X_{n} = 1\n", encoding="utf-8")
    capped = wt.snapshot(str(repo))
    assert capped is not None and len(capped.files) == 2


def test_round_trip_through_json(repo: Path) -> None:
    (repo / "pkg" / "parse.py").write_text(f"def parse(text):\n{NEW_LINE}\n", encoding="utf-8")
    snap = wt.snapshot(str(repo))
    assert snap is not None and wt.Snapshot.from_dict(snap.to_dict()) == snap


def test_a_snapshot_never_writes_the_index(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    real = subprocess.run

    def spy(args, **kwargs):  # type: ignore[no-untyped-def]
        seen.append(kwargs.get("env", {}).get("GIT_OPTIONAL_LOCKS", ""))
        return real(args, **kwargs)

    monkeypatch.setattr(wt.subprocess, "run", spy)
    (repo / "pkg" / "parse.py").write_text(f"def parse(text):\n{NEW_LINE}\n", encoding="utf-8")
    assert wt.snapshot(str(repo)) is not None
    assert seen and set(seen) == {"0"}


def test_a_repository_with_no_commit_has_a_snapshot_with_no_head(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    git(root, "init", "-q")
    (root / "a.py").write_text("FIRST_VALUE_OF_THE_MODULE = 1\n", encoding="utf-8")
    snap = wt.snapshot(str(root))
    assert snap is not None and snap.head == "" and "a.py" in snap.files


# ---- review of v6 (2026-10-01) -----------------------------------------------------------------


def test_only_looks_at_the_paths_asked_and_head_moves_are_capped(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # H1: after a pull of hundreds of files the Stop ran one `git show` per file (24.6 s)
    before = wt.snapshot(str(repo))
    for n in range(6):
        (repo / f"m{n}.py").write_text(f"MODULE_NUMBER_{n} = {n}\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "pulled")
    after = wt.snapshot(str(repo))
    assert {p for p, _ in wt.changes(before, after, only=["m3.py"])} == {"m3.py"}
    monkeypatch.setattr(wt, "MAX_FILES", 2)
    assert len(wt.changes(before, after)) == 2
    assert wt.changes(before, after, deadline=0.0) == []


def test_files_named_like_secrets_are_never_looked_at(repo: Path) -> None:
    # M7: a whole-file hash of a small `.env.local` could be brute-forced
    (repo / ".env.local").write_text("TOKEN=hunter2hunter2hunter2\n", encoding="utf-8")
    (repo / "deploy.pem").write_text("-----BEGIN-----\n", encoding="utf-8")
    snap = wt.snapshot(str(repo))
    assert snap is not None and snap.files == {}


def test_a_file_named_head_and_non_ascii_names(repo: Path) -> None:
    # L: a file named HEAD made `rev-parse HEAD` fail; M2: cp1252 decoding lost José and café
    (repo / "HEAD").write_text("not a ref\n", encoding="utf-8")
    (repo / "café.py").write_text("RESULTADO_DEL_CAFE = 'listo'\n", encoding="utf-8")
    snap = wt.snapshot(str(repo))
    assert snap is not None and len(snap.head) == 40
    assert snap.prints["café.py"] == (ep.line_print("RESULTADO_DEL_CAFE = 'listo'"),)


def test_a_repository_under_a_non_ascii_folder(tmp_path: Path) -> None:
    root = tmp_path / "José" / "repo"
    root.mkdir(parents=True)
    git(root, "init", "-q")
    (root / "a.py").write_text("FIRST_VALUE_OF_THE_MODULE = 1\n", encoding="utf-8")
    snap = wt.snapshot(str(root))
    assert snap is not None and "a.py" in snap.files


def test_different_roots_compare_to_nothing(repo: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    git(other, "init", "-q")
    (other / "a.py").write_text("FIRST_VALUE_OF_THE_MODULE = 1\n", encoding="utf-8")
    assert wt.changes(wt.snapshot(str(repo)), wt.snapshot(str(other))) == []


def test_the_read_budget_turns_content_keys_into_stat_keys(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wt, "TOTAL_BYTES", 10)
    (repo / "pkg" / "parse.py").write_text(f"def parse(text):\n{NEW_LINE}\n", encoding="utf-8")
    snap = wt.snapshot(str(repo))
    assert snap is not None and snap.files["pkg/parse.py"].startswith("stat:")
