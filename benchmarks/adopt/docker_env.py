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
# moto's pytest config forces colour, codes inside the node ids too: read the plain text.
ANSI = re.compile(r"\x1b\[[0-9;]*m")
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
    two seconds apart were not enough when two arms exported at once (dev round 1). Output is
    read as bytes and decoded, so a patch keeps the CRLF its files hold."""
    for attempt in range(attempts):
        done = subprocess.run(cmd, capture_output=True)
        if done.returncode == 0:
            return (done.stdout or b"").decode("utf-8", "replace")
        if attempt + 1 < attempts:
            time.sleep(2 ** (attempt + 1))
    err = (done.stderr or b"").decode("utf-8", "replace").strip()[-400:]
    raise RuntimeError(f"{' '.join(cmd[3:6])}: {err}")


def agent_diff(work: Path, base: str) -> str:
    """Everything the agent changed since `base`, new files included, as one patch. Our own
    install files (.claude/, .mcp.json) and sanchopanza's state are not part of the work, and
    stay out of the index too: marked intent-to-add, an agent's `git checkout .` emptied them
    and left an S arm without its hooks (development batch 2). Both git calls are checked and
    retried: an antivirus "Permission denied" once left an empty patch that graded as nothing
    fixed, in silence (long-session pre-mortem, b)."""
    git = ["git", "-C", str(work)]
    ours = (":(exclude).claude", ":(exclude).mcp.json", ":(exclude).sanchopanza")
    _git_retry([*git, "add", "-A", "-N", "--", ".", *ours])
    return _git_retry([*git, "diff", "--binary", base, "--", ".", *ours])


LABEL = "sp.long"  # every container a long-chain call starts carries `sp.long=<chain>-<arm>`


def label_args() -> list[str]:
    """`--label sp.long=<value>` for `docker run` when the runner set ADOPT_LABEL, else none."""
    value = os.environ.get("ADOPT_LABEL", "")
    return ["--label", f"{LABEL}={value}"] if value else []


def labelled(value: str) -> list[str]:
    """Ids of the containers, running or not, that carry `sp.long=<value>`."""
    done = docker("ps", "-aq", "--filter", f"label={LABEL}={value}", timeout=120)
    return ok(done, "docker ps").decode().split()


REMOVE_WAIT_S = 5.0  # between checks on a container Docker is already removing
REMOVE_CHECKS = 12
# A `docker run --rm` the agent started can be going away when the call ends: Docker then
# answers `rm -f` with one of these, and the container is gone a moment later (2026-10-07: the
# gate's runner ended on "removal ... is already in progress" after call 51 of a paid chain).
GOING_AWAY = ("is already in progress", "No such container")


def remove_labelled(value: str) -> list[str]:
    """Remove what a call left behind (a runtests the kill orphaned); returns the ids removed.
    A container already being removed is waited for, not fatal; one still there after the wait,
    or any other Docker error, still raises."""
    found = labelled(value)
    if not found:
        return found
    done = docker("rm", "-f", *found, timeout=300)
    if done.returncode == 0:
        return found
    err = done.stderr.decode("utf-8", "replace")
    if not any(sign in err for sign in GOING_AWAY):
        ok(done, "docker rm")
    for _ in range(REMOVE_CHECKS):
        if not set(labelled(value)) & set(found):
            return found
        time.sleep(REMOVE_WAIT_S)
    raise RuntimeError(f"docker rm: {sorted(set(labelled(value)) & set(found))} still there "
                       f"after {REMOVE_CHECKS * REMOVE_WAIT_S:.0f} s: {err[-300:]}")


def health() -> str:
    """Why Docker cannot serve a call now ("" when `docker info` answers). A daemon error is a
    fault of the harness, not of an arm: the runner stops on it."""
    try:
        done = docker("info", "--format", "{{.ServerVersion}}", timeout=120)
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"docker info: {error}"
    if done.returncode != 0:
        return f"docker info: {done.stderr.decode('utf-8', 'replace').strip()[-300:]}"
    return ""


FULL_SUITE_OVER = 1500  # more nodes than this: run the whole suite once and read them from it
BATCH = 400  # nodes per pytest process when the whole suite in one process runs out of memory
# Virtual memory per pytest process on that retry: a test a bug sends into a runaway gets a
# MemoryError and fails as a test, instead of the kernel killing every test with it (astroid-1:
# a batch of 400 was still killed at 36 %).
MEMORY_KB = 6_000_000
KILLED = 137  # the container's process killed (out of memory)
NOT_FOUND = re.compile(r"^ERROR: not found: (.+?)\s*$", re.M)
NOT_FOUND_RETRIES = 3


def pytest(
    tag: str, patch: str, nodes: list[str] | None, *, reverse: bool = False, timeout: int = 3600,
    keep_collecting: bool = False,
) -> dict[str, str]:
    """node id -> outcome of `nodes` (None or too many: the whole suite) in `tag` with `patch`
    applied first, or reversed with `reverse` (an empty patch runs the image as it is). A patch
    that does not apply yields {"<patch>": "ERROR"}. `-p no:pretty`: pytest-pretty (pydantic)
    replaces the `-rA` lines this reads with a table. A whole-suite run killed for memory
    (astroid with its chain's bugs in, at 54 % and at 84 %) is run again over the nodes in
    batches of `BATCH`, one pytest process each; other runs are as they were.

    `keep_collecting` (amendment 5, development chains only): a file that cannot be collected
    stops pytest whole and every other node comes out absent, read as not passing (a bug of
    conan-long40-1 removes `rm` and test_rm.py does not import). Held-out chains keep the sealed
    command, so the confirmation's arms are all graded the same way. With it, a listed node
    that does not exist (`ERROR: not found`, which stops pytest before any test runs) is left
    out and the rest run again: it comes out absent, read as not passing (pydantic names its doc
    tests by line range, and another bug in the same file shifts the range)."""
    listed = bool(nodes) and len(nodes or []) <= FULL_SUITE_OVER
    keep = " --continue-on-collection-errors" if keep_collecting else ""
    pytest_cmd = f"python -m pytest{keep}"
    select = f"xargs -a /io/nodes.txt -d '\\n' {pytest_cmd}" if listed else pytest_cmd
    done, text = _run(tag, patch, nodes, select, reverse, timeout)
    if not listed and nodes and done.returncode == KILLED:
        batched = (f"ulimit -v {MEMORY_KB} && "
                   f"xargs -a /io/nodes.txt -d '\\n' -n {BATCH} {pytest_cmd}")
        done, text = _run(tag, patch, nodes, batched, reverse, timeout)
    for _ in range(NOT_FOUND_RETRIES if keep_collecting and listed else 0):
        gone = {m.removeprefix("/testbed/") for m in NOT_FOUND.findall(text)}
        left = [n for n in nodes or [] if n not in gone]
        if len(left) == len(nodes or []):
            break
        if not left:
            return {}  # none of the listed nodes exists: nothing passed
        nodes = left
        done, text = _run(tag, patch, nodes, select, reverse, timeout)
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


def _run(
    tag: str, patch: str, nodes: list[str] | None, select: str, reverse: bool, timeout: int
) -> tuple[subprocess.CompletedProcess, str]:
    apply = "git apply -R" if reverse else "git apply"
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
    return done, ANSI.sub("", done.stdout.decode("utf-8", "replace"))


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
