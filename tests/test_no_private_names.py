"""No tracked file names the owner's other projects or a home folder of the machine the runs used:
not in its path, not in its bytes (a `.gz` fixture is read decompressed).

Names are kept only as sha256 digests of their lowercased form, compared with every word of every
tracked path and file (and with every two adjacent words joined, so a spelling with a hyphen, an
underscore, a space or a capital is caught too): the public test must not publish the names it
guards. More names can be given, never committed, as a comma-separated list in
SANCHOPANZA_PRIVATE_NAMES.

Home folders. A user folder in any spelling (`C:\\Users\\<user>`, `C:/Users/<user>`, a bare or
`%HOMEDRIVE%` `\\Users\\<user>`, a UNC `\\\\host\\c$\\Users\\<user>`, Git Bash's `/c/Users/<user>`,
WSL's `/mnt/c/Users/<user>`, URL-encoded `C%3A%5CUsers%5C<user>`, Claude Code's project folder
`C--Users-<user>`, a `/home/<user>` or `/var/home/<user>`) is refused unless `<user>` is one of
the stand-ins the tests and docs use (`someone`, `me`, `x`...), so the owner's account name is
never written here either. Use `~`, `%USERPROFILE%`, a path relative to the repository or a
placeholder instead.

The allow-lists hold files that had such text before this test, and that are not edited here: a
seal covers their bytes (a prereg's sha256, a lot's manifest, a sealed launcher), or they are a
run's recorded output (sessions, reports, status), which stays as the run wrote it until the owner
decides how to redact it. A file leaves its list when it is cleaned; nothing new joins one.
"""

from __future__ import annotations

import gzip
import hashlib
import os
import re
import shutil
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SEALED_NAME = "dda820158d142a0b73380cd3efa9ff7d9fa11336e9ba4b3693098964537d61a3"
HASHED = frozenset({
    "2ec0c243ce772956c756a80daba067aebac7787af7193ddfcd2964e30e20bcf6",
    "871218d9cd73fe0c69c22f890eab7411278e7bef7affd5e3fefde347df3644ec",
    "216bda9c86fdb3c9effef948a05b377afa54e19e32d2dc3ddca0cd97605c7993",
    SEALED_NAME,
    "3967a2ab24764ba36d71cf2172c0e9d9f59467deb1ace321180463c7e61e18cd",
    "d380d3982230397ad7c786d0b8ffba170ec562591fe6a26a3d0da5c3c689ec60",
})  # fmt: skip
EXTRA_ENV = "SANCHOPANZA_PRIVATE_NAMES"
WORD = re.compile(rb"[a-z]+")

# path -> the digests it may still hold. Sealed: a recorded selection where the word is a third
# party's public repository.
NAMES_ALLOWED: dict[str, frozenset[str]] = {
    "docs/results/2026-10-01-memory-real/selection-2.json": frozenset({SEALED_NAME}),
}

STAND_INS = frozenset({b"someone", b"me", b"name", b"user", b"username", b"x", b"r", b"u", b"..."})
SEGMENT = rb"([^\\/\s\"'`<>*%$:;,|()\[\]{}]+)"
HOME_FOLDERS = (
    # C:\Users, C:/Users, /c/Users, /mnt/c/Users, and a bare \Users or /Users after a non-word
    # (%HOMEDRIVE%\Users, \\host\c$\Users, macOS /Users); not a URL's /users/ (after a word)
    re.compile(
        rb"(?i)(?:\b[a-z]:[\\/]+|(?<![\w.])(?:/mnt)?/[a-z]/|(?<![\w.-])[\\/]+)users[\\/]+" + SEGMENT
    ),
    # URL-encoded, after an encoded drive colon or a non-word (not a URL's %2Fusers%2F)
    re.compile(rb"(?i)(?:%3a|(?<![\w.-]))(?:%5c|%2f)+users(?:%5c|%2f)+" + SEGMENT),
    re.compile(rb"(?i)\b[a-z]--users-([^-\s\"'`<>/\\{}]+)"),  # Claude Code's projects/<folder>
    re.compile(rb"(?<![\w.])(?:/var)?/home/" + SEGMENT),
)

RESULTS = "docs/results/"
BROWSE = RESULTS + "2026-09-30-browse/"
NAV = RESULTS + "2026-10-02-browse-nav/"
V6 = RESULTS + "2026-10-03-browse-v6/"
CARRY = RESULTS + "2026-10-02-memory-carry/"
# Sealed: never edited here (the seal's sha256 or the lot's manifest would no longer match).
HOME_SEALED = frozenset({
    "benchmarks/adopt/repos.py",
    CARRY + "prereg-v8-haiku.md",
    CARRY + "prereg-v81-haiku.md",
    CARRY + "prereg-v81-haiku-amendment-1.md",
    CARRY + "v81h-run.cmd",
    CARRY + "v81h-continue.cmd",
    RESULTS + "2026-10-05-memory-frontier/prereg-f1-gate.md",
    "f1-gate-run.cmd",
    RESULTS + "2026-10-13-memory-cell/prereg.md",
    "mem-cell-run.cmd",
})  # fmt: skip
# A run's recorded output (work folders under the user's temp folder): the owner's decision.
HOME_RECORDED = frozenset({
    RESULTS + "2026-09-29-candor/frontier-doubts.jsonl",
    *(BROWSE + f"e2e-{arm}-sessions.jsonl" for arm in (
        "cli-new", "cli-u", "cli-wide", "cli-x", "cli-y", "cli-z", "mcp", "mcp-fixed", "mcp-new",
        "mcp-r", "mcp-t", "mcp-u", "mcp-v", "mcp-wide", "mcp-x", "mcp-y", "mcp-z")),
    *(BROWSE + f"e2e-cli-{arm}.json" for arm in ("u", "x", "y", "z")),
    BROWSE + "e2e-sessions.jsonl",
    BROWSE + "e2e.json",
    BROWSE + "visible-dev-jev.json",
    NAV + "extract-replay.json",
    NAV + "extract-replay2.json",
    *(NAV + f"nav-{lot}-sessions.jsonl" for lot in (
        "confirm", "confirm2", "confirm3", "hard", "loop", "pilot", "smoke", "strategy",
        "strategy-harm", "traps")),
    RESULTS + "2026-10-03-browse-delegate/delegate-sessions.jsonl",
    RESULTS + "2026-10-03-browse-free/calib-sessions.jsonl",
    RESULTS + "2026-10-03-browse-free/free-sessions.jsonl",
    *(V6 + f"nav-{lot}-sessions.jsonl" for lot in (
        "confirm4", "confirm5", "v6", "v6-smoke", "v7", "v7-smoke", "v8", "v8-smoke", "v81",
        "v81-smoke", "v9", "v9-smoke")),
    RESULTS + "2026-10-13-memory-cell/run.status",
    CARRY + "v8-run.cmd",  # the launcher the v8 runs used, kept as it ran
})  # fmt: skip


def _tracked() -> list[str]:
    if shutil.which("git") is None or not (REPO / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"], capture_output=True,
                         check=True).stdout  # fmt: skip
    return [p for p in out.decode("utf-8").split("\0") if p]


def _bodies() -> Iterable[tuple[str, bytes]]:
    """(path, bytes) of every tracked file present in the work tree, a `.gz` decompressed."""
    for rel in _tracked():
        path = REPO / rel
        if not path.is_file():
            continue  # deleted in the work tree, not yet staged
        body = path.read_bytes()
        if rel.endswith(".gz"):
            body = gzip.decompress(body)
        yield rel, body


def _digest(word: bytes) -> str:
    return hashlib.sha256(word).hexdigest()


def hashed_names(environ: Mapping[str, str] = os.environ) -> frozenset[str]:
    extra = environ.get(EXTRA_ENV, "")
    words = (w.strip().lower().encode("utf-8") for w in extra.split(","))
    return HASHED | {_digest(re.sub(rb"[^a-z]", b"", w)) for w in words if w}


def found(blob: bytes, digests: Iterable[str]) -> frozenset[str]:
    """The digests of `digests` that a word of `blob`, or two adjacent words joined, hash to."""
    wanted = frozenset(digests)
    words = WORD.findall(blob.lower())
    candidates = {*words, *(a + b for a, b in zip(words, words[1:], strict=False))}
    return frozenset(d for d in map(_digest, candidates) if d in wanted)


def hits(blob: bytes, digests: Iterable[str]) -> bool:
    """Whether a word of `blob`, or two adjacent words joined, hashes to one of `digests`."""
    return bool(found(blob, digests))


def home_users(blob: bytes) -> frozenset[bytes]:
    """The user names of the home folders `blob` writes, stand-ins left out (lowercased)."""
    users = {m.group(1).lower() for pattern in HOME_FOLDERS for m in pattern.finditer(blob)}
    return frozenset(users - STAND_INS)


def test_no_tracked_path_or_file_holds_a_hashed_private_name() -> None:
    digests = hashed_names()
    bad = {}
    for rel, body in _bodies():
        held = found(rel.encode("utf-8"), digests) | found(body, digests)
        if held - NAMES_ALLOWED.get(rel, frozenset()):
            bad[rel] = len(held)  # how many names, never which
    assert bad == {}


def test_no_tracked_file_writes_a_home_folder_outside_its_allow_list() -> None:
    allowed = HOME_SEALED | HOME_RECORDED
    bad = {}
    for rel, body in _bodies():
        users = home_users(rel.encode("utf-8") + b"\n" + body)
        if users and rel not in allowed:
            bad[rel] = len(users)  # how many user names, never which
    assert bad == {}


def test_the_allow_lists_name_tracked_files_only() -> None:
    tracked = set(_tracked())
    assert not (HOME_SEALED | HOME_RECORDED | set(NAMES_ALLOWED)) - tracked
    assert not HOME_SEALED & HOME_RECORDED


def test_the_allow_lists_cannot_go_stale() -> None:
    # A file cleaned (or a digest no longer in it) must leave its list: nothing waits there.
    bodies = dict(_bodies())
    stale = sorted(rel for rel in HOME_SEALED | HOME_RECORDED
                   if not home_users(rel.encode("utf-8") + b"\n" + bodies[rel]))  # fmt: skip
    assert stale == []
    for rel, digests in NAMES_ALLOWED.items():
        assert found(rel.encode("utf-8") + b"\n" + bodies[rel], digests) == digests, rel


def test_the_hashed_check_catches_case_and_separator_variants() -> None:
    digests = {_digest(b"projecta")}
    variants = (b"x projecta y", b"C--x-ProjectA-sancho", b"project-a", b"Project_A", b"PROJECT A")
    for text in variants:
        assert hits(text, digests), text
    assert not hits(b"project-b and a project", digests)
    assert found(b"a project-a", digests | {_digest(b"other")}) == {_digest(b"projecta")}


def test_extra_names_come_from_the_environment_only() -> None:
    assert hashed_names({}) == HASHED
    extra = hashed_names({EXTRA_ENV: " Project-A , ,other"})
    assert extra == HASHED | {_digest(b"projecta"), _digest(b"other")}


@pytest.mark.parametrize(
    "text",
    [
        rb"C:\Users\{u}\x.py", b"c:/users/{u}/x", b"cd /c/Users/{u}/proj", b"/home/{u}/x",
        rb'"cwd": "C:\\\\Users\\\\{u}\\\\AppData"', b"projects/C--Users-{u}-repo/s.jsonl",
        b"open /Users/{u}/Downloads", b"cd /mnt/c/Users/{u}/proj", b"folder C--Users-{u}",
        b"projects/C--Users-{u}/x.jsonl", rb"see \Users\{u}\x", rb"%HOMEDRIVE%\Users\{u}\x",
        rb"\\host\c$\Users\{u}\share", b"/var/home/{u}/x", b"file:///C%3A%5CUsers%5C{u}%5Cx",
        b"p=c%3A%2FUsers%2F{u}%2Fx",
    ],
)  # fmt: skip
def test_a_real_home_folder_is_caught_in_every_spelling(text: bytes) -> None:
    # The name is put in at run time: written here, this file would hold a home folder itself.
    user = b"ali" + b"ce"
    assert home_users(text.replace(b"{u}", user)) == {user}
    assert home_users(text) == frozenset()  # `{u}` is no user name


@pytest.mark.parametrize(
    "text",
    [
        rb"C:\Users\someone\.cache", b"/c/Users/x/a.txt", rb"C:\Users\<name>\file.docx",
        b"/home/user/doc.pdf", b"C--Users-r-a-b", b"https://api.github.com/users/octocat",
        b"%USERPROFILE%\\.cache", b"~/.cache/sanchopanza", b"https%3A%2F%2Fapi.x.com%2Fusers%2Fbob",
        b"GET /api/users/{id}", b"src/users/models.py",
    ],
)  # fmt: skip
def test_stand_ins_urls_and_portable_forms_pass(text: bytes) -> None:
    assert home_users(text) == frozenset()
