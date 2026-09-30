"""Docker plumbing for the adoption benchmark: bake a chain's bugs into its image, export the
agent's working copy, and run pytest there against a diff.

The disk this runs on is nearly full, so images live one repository at a time: `drop` removes a
chain's tags as soon as its sessions and grades are done.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

LOGIN = "bash -lc"  # SWE-smith and SWE-bench images activate the `testbed` env in a login shell
# Some SWE-smith images keep the project's test environment in /testbed/.venv (uv) and leave the
# conda `testbed` env without its dependencies (pydantic: no jsonschema, conftest fails). Where
# that venv exists it is the environment; the images without one (pygments, starlette) are as
# they were.
VENV = "if [ -x /testbed/.venv/bin/python ]; then . /testbed/.venv/bin/activate; fi; "
RESULT = re.compile(r"^(PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED) (\S+)", re.M)
GIT_ID = "-c user.name=adopt -c user.email=adopt@localhost"


def docker(
    *args: str, stdin: bytes | None = None, timeout: int = 3600
) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], input=stdin, capture_output=True, timeout=timeout)


def ok(done: subprocess.CompletedProcess, what: str) -> bytes:
    if done.returncode != 0:
        err = done.stderr.decode("utf-8", "replace")[-800:]
        raise RuntimeError(f"{what} failed ({done.returncode}): {err}")
    return done.stdout


def pull(image: str) -> None:
    if docker("image", "inspect", image).returncode != 0:
        ok(docker("pull", "-q", image, timeout=7200), f"pull {image}")


def bake(image: str, patches: list[str], tag: str) -> None:
    """`tag`: `image` with `patches` applied inside its single commit (amended: no trace in
    history). A patch that does not apply fails the bake. `--no-verify`: the pydantic image
    carries a pre-commit hook that rewrites files and then fails for want of `uv`."""
    name = f"bake-{tag.replace('/', '-').replace(':', '-')}"
    docker("rm", "-f", name)
    ok(docker("create", "--name", name, "-i", image, "bash", "-lc",
              f"cd /testbed && git apply --whitespace=nowarn - && git add -A && "
              f"git {GIT_ID} commit -q --amend --no-edit --no-verify && git gc -q --prune=now"),
       "create")  # fmt: skip
    try:
        combined = "".join(p if p.endswith("\n") else p + "\n" for p in patches).encode()
        ok(docker("start", "-ai", name, stdin=combined), "apply the bugs")
        ok(docker("commit", name, tag), "commit")
    finally:
        docker("rm", "-f", name)


def export(tag: str, dest: Path, attempts: int = 2) -> str:
    """The image's /testbed as a fresh repository at `dest`, one commit, LF endings. Returns the
    commit id the agent's diff is taken against. A failed export is removed and done again."""
    for attempt in range(attempts):
        try:
            return _export_once(tag, dest)
        except RuntimeError:
            remove_tree(dest)
            if attempt + 1 == attempts:
                raise
            time.sleep(10)
    raise AssertionError("unreachable")


def _export_once(tag: str, dest: Path) -> str:
    tar = ok(docker("run", "--rm", tag, "git", "-C", "/testbed", "archive", "--format=tar", "HEAD"),
             "archive")  # fmt: skip
    dest.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
        archive.extractall(dest, filter="data")
    git = ["git", "-C", str(dest), "-c", "gc.auto=0", "-c", "core.autocrlf=false"]
    _git_retry([*git, "init", "-q"])
    _git_retry([*git, "config", "core.autocrlf", "false"])
    _git_retry([*git, "add", "-A"])
    # gc.auto=0: an automatic gc during this first commit (5,000+ files) raced and warned.
    _git_retry([*git, *GIT_ID.split(), "commit", "-q", "-m", "Initial commit"])
    return _git_retry([*git, "rev-parse", "HEAD"]).strip()


def _git_retry(cmd: list[str], attempts: int = 5) -> str:
    """Git on freshly written files on Windows fails now and then (a scanner holding a file, a
    stale index.lock): five tries, 2 to 16 seconds apart, then the error as it was. Three tries
    two seconds apart were not enough when two arms exported at once (dev round 1)."""
    for attempt in range(attempts):
        done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace")  # fmt: skip
        if done.returncode == 0:
            return done.stdout
        if attempt + 1 < attempts:
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"{' '.join(cmd[3:6])}: {done.stderr.strip()[-400:]}")


def agent_diff(work: Path, base: str) -> str:
    """Everything the agent changed since `base`, new files included, as one patch. Our own
    install files (.claude/, .mcp.json) and sanchopanza's state are not part of the work, and
    stay out of the index too: marked intent-to-add, an agent's `git checkout .` emptied them
    and left an S arm without its hooks (development batch 2)."""
    git = ["git", "-C", str(work)]
    ours = (":(exclude).claude", ":(exclude).mcp.json", ":(exclude).sanchopanza")
    subprocess.run([*git, "add", "-A", "-N", "--", ".", *ours], capture_output=True)
    out = subprocess.run([*git, "diff", "--binary", base, "--", ".", *ours], capture_output=True)
    return out.stdout.decode("utf-8", "replace")


FULL_SUITE_OVER = 1500  # more nodes than this: run the whole suite once and read them from it


def pytest(
    tag: str, patch: str, nodes: list[str] | None, *, reverse: bool = False, timeout: int = 3600
) -> dict[str, str]:
    """node id -> outcome of `nodes` (None or too many: the whole suite) in `tag` with `patch`
    applied first, or reversed with `reverse` (an empty patch runs the image as it is). A patch
    that does not apply yields {"<patch>": "ERROR"}. `-p no:pretty`: pytest-pretty (pydantic)
    replaces the `-rA` lines this reads with a table."""
    listed = bool(nodes) and len(nodes or []) <= FULL_SUITE_OVER
    apply = "git apply -R" if reverse else "git apply"
    select = "xargs -a /io/nodes.txt -d '\\n' python -m pytest" if listed else "python -m pytest"
    with tempfile.TemporaryDirectory() as io_dir:
        folder = Path(io_dir)
        (folder / "work.patch").write_bytes(patch.encode("utf-8"))
        (folder / "nodes.txt").write_text("\n".join(nodes or []) + "\n", encoding="utf-8",
                                          newline="\n")  # fmt: skip
        script = (f"cd /testbed && {VENV}(test ! -s /io/work.patch || {apply} --whitespace=nowarn "
                  "/io/work.patch || { echo PATCH_FAILED; exit 3; }) && "
                  f"{select} -rA -p no:cacheprovider -p no:pretty --tb=no -q 2>&1")  # fmt: skip
        done = docker("run", "--rm", "-v", f"{folder.as_posix()}:/io:ro", tag, "bash", "-lc",
                      script, timeout=timeout)  # fmt: skip
    text = done.stdout.decode("utf-8", "replace")
    if "PATCH_FAILED" in text:
        return {"<patch>": "ERROR"}
    found = {node: status for status, node in RESULT.findall(text)}
    # 123 is xargs reporting that pytest exited 1 (tests failed): a run, not a broken one.
    if not found or done.returncode not in (0, 1, 123):
        # A run that reports nothing is a broken run, not a patch that fails every test: the
        # first pilot grade read an empty run as 0 of 5 resolved.
        err = done.stderr.decode("utf-8", "replace")[-600:]
        raise RuntimeError(f"pytest in {tag} gave no results (exit {done.returncode}): "
                           f"{text[-600:]} {err}")  # fmt: skip
    return found


def remove_tree(path: Path) -> None:
    """rmtree that also removes read-only files (git's packs on Windows), and says when it cannot:
    a silent failure left an old working copy under a new session."""

    def writable(func, target, _exc):  # noqa: ANN001, ANN202
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if path.exists():
        shutil.rmtree(path, onexc=writable)
    if path.exists():
        raise RuntimeError(f"could not remove {path}")


def drop(*tags: str) -> None:
    for tag in tags:
        docker("rmi", "-f", tag)


def disk_free_gb(path: str = "C:\\") -> float:
    usage = os.statvfs(path) if hasattr(os, "statvfs") else None
    if usage:
        return usage.f_bavail * usage.f_frsize / 1e9
    import shutil

    return shutil.disk_usage(path).free / 1e9
