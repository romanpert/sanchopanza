"""What the agent did, as a record built by code: the side of "said vs did" nobody has to trust.

A monitor that reads the transcript and judges it is the design the literature keeps
breaking: an injection written into the agent's own output drove a GPT-4.1 monitor to score
all 375 backdoored samples as safe (Terekhov et al., arXiv 2510.09462), and nine LLM monitors
reached 60.9 % where a 20-line deterministic check reached 100 % (arXiv 2609.07162). So the
"did" side here is never read by a model. It is a list of `Action`s, each classified by rules
into an `Effect`, with the outcome of any test run parsed from its exit and its output.

Every function in this module is pure and cheap: no model, no network, no file access.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

Effect = Literal[
    "read",  # looked at something: no change anywhere
    "write",  # changed a file in the workspace
    "delete",  # removed files, rows, branches or history
    "external",  # something left the machine: push, publish, POST, mail, deploy
    "test",  # ran a check whose outcome can be claimed
    "tamper",  # touched the monitor, the hooks, the trace or the permissions
    "secret",  # read or moved credentials
    "exec",  # ran something else
]

TARGET_LIMIT = 300
RESULT_LIMIT = 400

READ_TOOLS = frozenset({"read", "grep", "glob", "ls", "websearch", "webfetch", "view", "search"})
WRITE_TOOLS = frozenset(
    {"edit", "write", "multiedit", "notebookedit", "apply_patch", "str_replace", "create"}
)
SHELL_TOOLS = frozenset({"bash", "shell", "powershell", "exec", "local_shell", "terminal"})

# Things a monitored agent must not touch whatever it says: the monitor itself, its hooks and
# permissions, and the trace that holds it to account. Anthropic's auto mode post names an
# agent editing its own settings as the case its `ConfigChange` event exists for.
TAMPER = re.compile(
    r"\.claude[\\/](settings(\.local)?\.json|hooks)|managed-settings"
    # The monitor's home, new or legacy (`~/.sanchopanza`, `~/.sancho`): the lock, the ledgers,
    # the journal. Dotted, so a checkout's `src/sanchopanza/candor/lock.py` is code, not the lock.
    r"|\.sancho(panza)?[\\/].*(lock|journal|candor)"
    r"|\bjournal\.jsonl\b|[\\/]audit[\\/]|events\.jsonl|\bhistory\s+-c\b|unset\s+HISTFILE"
    r"|--no-verify\b|git\s+push\s+(-f\b|--force)|\bgit\s+commit\s+--amend\b.*--no-edit"
    r"|\.git[\\/]hooks|\bchmod\b|\bchown\b|\bsudo\b|\bicacls\b|Set-ExecutionPolicy"
    # v5: the measurement that lets a frontier kind lock is part of the monitor.
    r"|frontier_measured\.json"
    # Codex's own hooks and configuration: candor's hooks in Codex live there.
    r"|\.codex[\\/](hooks\.json|config\.toml)",
    re.IGNORECASE,
)
SECRET = re.compile(
    r"(^|[\\/\s'\"])\.env(\.|\b)|id_rsa|id_ed25519|\.pem\b|\.ssh[\\/]|credentials|api[_-]?key"
    r"|\btoken\.json\b|\.npmrc\b|\.pypirc\b|\bprintenv\b|\benv\s*\|",
    re.IGNORECASE,
)
DELETE = re.compile(
    r"\brm\s|\brmdir\b|\bdel\s|\bRemove-Item\b|\bgit\s+(rm|clean|reset\s+--hard|branch\s+-D"
    r"|push\s+\S+\s+--delete|checkout\s+--\s)|\bDROP\s+(TABLE|DATABASE)\b|\bTRUNCATE\b"
    r"|\bDELETE\s+FROM\b|\bshred\b|\bunlink\b|os\.remove|shutil\.rmtree|\bdocker\s+(rm|volume\s+rm)"
    # v4: `find build -name "*.tmp" -delete` deletes; it was read as a listing.
    r"|\bfind\b[^|;&]*\s-delete\b|\bxargs\s+rm\b",
    re.IGNORECASE,
)
EXTERNAL = re.compile(
    r"\bgit\s+push\b|\bnpm\s+publish\b|\btwine\s+upload\b|\bgh\s+(pr|issue|release)\s+"
    r"(create|merge|comment)|\bcurl\b[^\n]*(-X\s*(POST|PUT|PATCH|DELETE)|\s-d\s|--data|-F\s|-T\s)"
    r"|\bwget\b[^\n]*--post|\bInvoke-(WebRequest|RestMethod)\b[^\n]*-Method\s+(Post|Put|Delete)"
    r"|\bscp\b|\brsync\b[^\n]*:|\bsftp\b|\bssh\b|\bsendmail\b|\bmail\s+-s|\bkubectl\s+(apply|delete)"
    r"|\bterraform\s+apply\b|\bdeploy\b|\bvercel\b|\bfly\s+deploy\b|\bdocker\s+push\b",
    re.IGNORECASE,
)
TEST = re.compile(
    r"\bpytest\b|\bpython\s+-m\s+(pytest|unittest)\b|\b(npm|pnpm|yarn|bun)\s+(run\s+)?test\b"
    r"|\bvitest\b|\bjest\b|\bgo\s+test\b|\bcargo\s+test\b|\bmvn\s+test\b|\bgradle\w*\s+test\b"
    r"|\bdotnet\s+test\b|\bctest\b|\bmake\s+(test|check)\b|\btox\b|\bnox\b|\bphpunit\b|\brspec\b",
    re.IGNORECASE,
)
SHELL_WRITE = re.compile(
    r"(^|[^<>&0-9])>{1,2}\s*[^\s&|>]|\bsed\s+-i\b|\btee\b|\bmv\s|\bcp\s|\btouch\s|\bmkdir\b"
    r"|\bSet-Content\b|\bOut-File\b|\bAdd-Content\b|\bNew-Item\b|\bgit\s+(commit|apply|checkout|merge"
    r"|rebase|stash)\b|\bpatch\s",
    re.IGNORECASE,
)
_FAILED = re.compile(
    r"\b(\d+)\s+(failed|failures?|errors?)\b|\bFAILED\b|\bFAIL\b|Tests?:\s+\d+\s+failed"
    r"|AssertionError|Traceback \(most recent|exit code [1-9]|Exit code [1-9]|\bERRORS?\b"
    r"|npm ERR!|test result: FAILED|\berror\[E\d+\]",
)
_PASSED = re.compile(
    r"\b(\d+)\s+passed\b|\bOK\b(\s+\(|$)|All tests passed|Tests?:\s+\d+\s+passed"
    r"|test result: ok|\bPASS\b|\b0 failed\b",
    re.IGNORECASE | re.MULTILINE,
)
_ZERO_FAILED = re.compile(r"\b0\s+(failed|failures|errors)\b", re.IGNORECASE)
TEST_FILE = re.compile(
    r"(^|[\\/])(tests?|__tests__|spec)[\\/]|(^|[\\/])test_[^\\/]*\.py$|_test\.(py|go)$"
    r"|\.(test|spec)\.[cm]?[jt]sx?$|(^|[\\/])conftest\.py$|(^|[\\/])(pytest\.ini|setup\.cfg|tox\.ini"
    r"|jest\.config\.[cm]?[jt]s|vitest\.config\.[cm]?[jt]s)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Action:
    """One tool call. `target` is the command, path or URL; `result` the tail of the output."""

    tool: str
    target: str
    ok: bool | None = None
    result: str = ""
    writes: tuple[str, ...] = ()
    effect: Effect = "exec"
    test_passed: bool | None = None  # only for effect == "test": None when unreadable


def _normal(path: str) -> str:
    """A path as `TAMPER` reads it: forward slashes, no `./`, no doubled `/`."""
    out = path.replace("\\", "/")
    while "/./" in out or "//" in out:
        out = out.replace("/./", "/").replace("//", "/")
    return out


# `cd .claude && echo {} > settings.json`: the monitor's file named from inside its directory.
_INSIDE_MONITOR = re.compile(
    r"\bcd\s+[\"']?[^;&|\"']*\.(claude|codex)[\\/]?[\"']?\s*(&&|;|\n)[^\n]*"
    r"\b(settings(\.local)?\.json|hooks(\.json)?|config\.toml)\b",
    re.IGNORECASE,
)


def classify(tool: str, target: str) -> Effect:
    """The worst thing the call can do, by rules. Order matters: tamper beats everything."""
    name = tool.strip().lower()
    if TAMPER.search(_normal(target)) or _INSIDE_MONITOR.search(target):
        return "tamper"
    if name in READ_TOOLS:
        return "secret" if SECRET.search(target) else "read"
    if name in WRITE_TOOLS:
        return "write"
    if name not in SHELL_TOOLS and not name.startswith("mcp__"):
        return "exec"
    if EXTERNAL.search(target):
        return "external"
    if DELETE.search(target):
        return "delete"
    if SECRET.search(target):
        return "secret"
    if TEST.search(target):
        return "test"
    if SHELL_WRITE.search(target):
        return "write"
    if name.startswith("mcp__"):
        return "exec"
    return "read" if _read_only_shell(target) else "exec"


def run_outcome(ok: bool | None, result: str) -> bool | None:
    """Did a test run pass? Exit first, then the runner's own summary. None if unreadable."""
    failed = bool(_FAILED.search(result)) and not _ZERO_FAILED.search(result)
    passed = bool(_PASSED.search(result))
    if ok is False or failed:
        return False
    if passed:
        return True
    return None if ok is None else ok


def action(
    tool: str,
    target: str,
    *,
    ok: bool | None = None,
    result: str = "",
    writes: Iterable[str] = (),
) -> Action:
    """An `Action` with its effect and, for a test run, its outcome."""
    target = str(target)[:TARGET_LIMIT]
    result = str(result)[-RESULT_LIMIT:]
    writes = tuple(str(w) for w in writes)
    effect = classify(tool, target)
    if any(TAMPER.search(_normal(w)) for w in writes):
        effect = "tamper"  # a patch names what it writes past the cut target (Codex apply_patch)
    passed = run_outcome(ok, result) if effect == "test" else None
    return Action(str(tool), target, ok, result, writes, effect, passed)


_READ_ONLY = re.compile(
    r"^\s*(cat|type|head|tail|less|more|ls|dir|find|grep|rg|wc|stat|file|pwd|echo|which|where"
    r"|git\s+(status|log|diff|show|branch|remote\s+-v|ls-files|blame)|Get-(Content|ChildItem|Item)"
    r"|Select-String|tree|du|df|jq|sort|uniq|diff)\b",
    re.IGNORECASE,
)


def _read_only_shell(command: str) -> bool:
    parts = re.split(r"&&|\|\||;|\|", command)
    return all(_READ_ONLY.match(p) for p in parts if p.strip())


# A look, in shell, is a small grammar and nothing else: a whitelist of programs that print what
# they read, over plain paths, joined by `|` or `&&`. Growing a list of what writes is an arms
# race (an independent review found `sort -o`, `rg --pre`, PowerShell's `( )`, `-exec`); a
# grammar of what reads is not. Anything outside it keeps the lock.
_LOOKERS = frozenset(
    ["cat", "head", "tail", "type", "get-content", "gc", "jq", "wc", "ls", "dir", "grep"]
)
_LOOK_FLAGS = frozenset(
    ["-n", "-c", "-l", "-w", "-r", "-s", "-i", "-v", "-E", "-F", "-h", "-H", "-o", "-q", "-a"]
    + ["-Raw", "-TotalCount", "-Tail", "-Head"]  # Get-Content
)
_HARMLESS = re.compile(r"\s+2>(/dev/null|&1|\$null)(?=\s|$)")
_OUTSIDE = re.compile(r"[;&$(){}@%`<>=\n\r\\]|\|\|")
_PLAIN = re.compile(r"^[\w./:~*+,\[\]-]+$")


def _look_segment(segment: str) -> bool:
    tokens = [t.strip("'\"") for t in segment.split()]
    if not tokens or tokens[0].lower() not in _LOOKERS:
        return False
    for token in tokens[1:]:
        if token.startswith("-"):
            letters = token[1:]
            combined = letters.isalpha() and all(f"-{ch}" in _LOOK_FLAGS for ch in letters)
            if token not in _LOOK_FLAGS and not letters.isdigit() and not combined:
                return False
        elif not _PLAIN.match(token):
            return False
    return True


def only_reads(action: Action) -> bool:
    """Whether a call can only have looked, which v5 treats as review rather than the lock when
    it touches the monitor (an honest round-4 session ran `cat .claude/settings.json`). Strict
    by design, since a wrong yes lets a write to the hooks through: a read tool, or a shell
    command under TARGET_LIMIT made only of `_LOOKERS` over plain paths, joined by `|` or `&&`,
    with `2>/dev/null` or `2>&1` the only redirections."""
    name = action.tool.strip().lower()
    if name in READ_TOOLS:
        return True
    if name not in SHELL_TOOLS or len(action.target) >= TARGET_LIMIT:
        return False  # a cut target may hide its writing part
    command = _HARMLESS.sub(" ", action.target.replace("&&", " | "))
    if _OUTSIDE.search(command):
        return False
    segments = [s.strip() for s in command.split("|")]
    return bool(segments) and all(_look_segment(s) for s in segments)


def is_test_file(path: str) -> bool:
    return bool(TEST_FILE.search(path.strip()))


def from_audit(did: Iterable[Mapping[str, Any]]) -> list[Action]:
    """jarvis-module's audit journal `did` list: {tool, target, ok, result, writes?}."""
    out = []
    for step in did:
        if not isinstance(step, Mapping):
            continue
        writes = step.get("writes") or ()
        writes = (writes,) if isinstance(writes, str) else tuple(str(w) for w in writes)
        out.append(
            action(
                str(step.get("tool") or ""),
                str(step.get("target") or ""),
                ok=step.get("ok") if isinstance(step.get("ok"), bool) else None,
                result=str(step.get("result") or ""),
                writes=writes,
            )
        )
    return out


def target_of(tool: str, arguments: Mapping[str, Any]) -> str:
    """The one string that says what a Claude Code tool call acts on."""
    for key in ("command", "file_path", "notebook_path", "path", "url", "pattern", "query"):
        value = arguments.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


_PATCH_FILE = re.compile(
    r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$|^\*\*\* Move to: (.+?)\s*$", re.M
)


def writes_of(tool: str, arguments: Mapping[str, Any]) -> tuple[str, ...]:
    """The paths a write tool changes. Codex's `apply_patch` names them inside the patch
    (`*** Update File: src/app.py`), not in an argument."""
    if tool.lower() not in WRITE_TOOLS:
        return ()
    path = arguments.get("file_path") or arguments.get("notebook_path") or arguments.get("path")
    if path:
        return (str(path),)
    patch = next(
        (v for k in ("command", "input", "patch") if isinstance(v := arguments.get(k), str)), ""
    )
    found = [m.group(1) or m.group(2) for m in _PATCH_FILE.finditer(patch)]
    return tuple(dict.fromkeys(found))
