"""Did this request change anything? The gate in front of check-done and candor.

Both hold a report against what the session did to the world. A request that only read (a
question answered from documents, a search, a look at the code) has nothing for them to hold
it against, and in the h2h development run they cost there without returning anything:
check-done sent back 17 of 20 question-and-answer sessions whose second answer never changed
a grade (S cost 1.69x and 1.90x of N on BrowseComp-Plus and LongBench v2), and candor asked
for its status block on every prompt (docs/results/2026-10-05-h2h-offline-dev/). So by
default both act only on a request that changed something:

- an edit tool (Edit, Write, MultiEdit, NotebookEdit, apply_patch, ...);
- a shell command that writes, deletes, sends out, installs or touches the monitor: candor's
  own classification (`candor.ledger.classify`) and the files a command writes
  (`context.shell.written`, the memory touch's reading of Bash and PowerShell);
- any other tool that is not known to only read: an MCP or harness tool whose name does not
  start with a reading verb (`search`, `get_document`, `browser_snapshot` read; `send_message`,
  `invite` act). In doubt, a change: the gate may only remove a check where nothing happened;
- a delegation (Agent, Task), unless the subagents' transcripts show only reads.

Candor also opens on a test run (`acted`): its rules hold "the tests pass" against the runs.

`SANCHOPANZA_ON_CHANGE=0` turns the gate off: both act on every request, as before.
Pure code, no decider; reading a transcript costs milliseconds.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .. import _env
from ..candor.ledger import SHELL_TOOLS, WRITE_TOOLS, classify, target_of

CHANGING_EFFECTS = frozenset({"write", "delete", "external", "tamper"})
# Claude Code's own tools that only look, plan or talk (their names, lower-cased).
READ_ONLY_TOOLS = frozenset(
    {"read", "grep", "glob", "ls", "websearch", "webfetch", "toolsearch", "todowrite",
     "notebookread", "bashoutput", "taskoutput", "killshell", "taskstop", "monitor", "skill",
     "slashcommand", "askuserquestion", "exitplanmode", "enterplanmode", "lsp",
     "listmcpresourcestool", "readmcpresourcetool", "view", "search"}
)  # fmt: skip
DELEGATION_TOOLS = frozenset({"agent", "task"})
# A tool named by what it looks at: `search`, `get_document`, `browser_snapshot`, `read_page`.
_READ_VERB = re.compile(
    r"^(browser_)?(get|list|search|read|fetch|find|query|lookup|look|show|view|describe|count"
    r"|pick|browse|navigate|snapshot|take_screenshot|screenshot|wait|hover|scroll|extract"
    r"|resolve|inspect|stat|status|info|tabs|console|network|recall|retrieve|download|open"
    r"|select_passages|passages|explain|summari[sz]e)(_|$)",
    re.IGNORECASE,
)
# Installing or building changes the workspace even when no file is named.
_INSTALLS = re.compile(
    r"\b(pip3?|uv|npm|pnpm|yarn|bun|cargo|go|gem|poetry|conda|brew|apt(-get)?|choco|winget)\s+"
    r"(install|add|remove|uninstall|update|upgrade|sync|build|get)\b|\bmake\b|\balembic\s+upgrade"
    r"|\bmanage\.py\s+migrate\b",
    re.IGNORECASE,
)


# --- did the request ask for an action? ---------------------------------------------------------
# Without a change there is still something to hold "done" against when the request asked for
# one: on AgentDojo 263 of check-done's 286 right blocks were requests to send, pay or invite in
# which the agent stopped to ask, refused or never called the action. A verb that acts on the
# world, in the imperative, and no question anywhere in the request.
_ACTION_VERBS = (
    r"send|e-?mail|mail|reply|respond|forward|post|message|write|book|reserve|pay|transfer|refund"
    r"|create|add|invite|remove|delete|cancel|update|change|edit|modify|set|schedule|reschedule"
    r"|share|move|rename|fix|install|deploy|commit|push|upload|order|buy|purchase|submit|publish"
    r"|register|subscribe|unsubscribe|approve|assign|archive|perform|do|complete|make|organi[sz]e"
    r"|refactor|implement|run|save|put|append|insert|replace|kick|block|unblock|grant|revoke"
    r"|env[ií]a|env[ií]e|manda|mande|reserva|paga|pague|transfiere|crea|cree|a[nñ]ade|agrega"
    r"|borra|elimina|actualiza|cambia|programa|arregla|corrige|escribe|invita|publica|comparte"
    r"|cancela|mueve|instala|guarda|haz|haga|completa|ejecuta|sube|compra|modifica"
)
# A clause starts at the start of a sentence, after a list marker, a comma, a colon or a joining
# word; a polite lead-in may come before the verb.
_IMPERATIVE = re.compile(
    r"(?:^|[;:]\s*|\d+[.)]\s*|,\s*|\b(?:and|then|also|y|luego|despu[eé]s)\s+)"
    r"(?:please\s+|kindly\s+|(?:can|could|would|will)\s+you\s+(?:please\s+)?"
    r"|i\s+(?:need|want|would\s+like|'d\s+like)\s+you\s+to\s+|your\s+task\s+is\s+to\s+"
    r"|por\s+favor,?\s+|puedes\s+|podr[ií]as\s+|quiero\s+que\s+|tu\s+tarea\s+es\s+)?"
    r"(?:" + _ACTION_VERBS + r")\b",
    re.IGNORECASE,
)
_QUESTION = re.compile(
    r"[?¿]|\bquestion\b|\bpregunta\b|^\W*(?:what|which|how|who|whom|whose|when|where|why"
    r"|qu[eé]|cu[aá]l(?:es)?|cu[aá]nt[oa]s?|qui[eé]n(?:es)?|cu[aá]ndo|d[oó]nde|por\s+qu[eé])\b",
    re.IGNORECASE,
)
_QUOTED = re.compile(r"'[^'\n]*'|\"[^\"\n]*\"|“[^”\n]*”|«[^»\n]*»")
_ABBREVIATION = re.compile(r"\b(?:e\.g|i\.e|etc|vs|p\.ej)\.", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_CONDITIONAL = re.compile(r"^\W*(?:if|si)\b", re.IGNORECASE)  # "If you are asked for a number"


def asks_action(request: str) -> bool:
    """Whether the request asks for an action rather than an answer. Quoted text (a message to
    send) and conditional sentences (an answer template's "if you are asked for a string, ...
    write the digits") do not count; a question anywhere makes the request a question."""
    text = _ABBREVIATION.sub(" ", _QUOTED.sub(" ", str(request or "")))
    sentences = [s.strip() for s in _SENTENCE.split(text) if s.strip()]
    sentences = [s for s in sentences if not _CONDITIONAL.match(s)]
    if any(_QUESTION.search(s) for s in sentences):
        return False
    return any(_IMPERATIVE.search(s) for s in sentences)


def on(env: Mapping[str, str] | None = None) -> bool:
    """`SANCHOPANZA_ON_CHANGE`: on unless set to 0, false, no or off."""
    return _env.get("ON_CHANGE", "1", env=env).strip().lower() not in ("0", "false", "no", "off")


def _shell_changes(command: str) -> bool:
    if classify("bash", command) in CHANGING_EFFECTS or _INSTALLS.search(command):
        return True
    from ..context import shell

    return bool(shell.written(command))


def changes(tool: str, arguments: Mapping[str, Any] | None) -> bool:
    """Whether one tool call can have changed the workspace or the world."""
    arguments = arguments if isinstance(arguments, Mapping) else {}
    name = str(tool or "").strip()
    lower = name.lower()
    if lower in WRITE_TOOLS:
        return True
    if lower in SHELL_TOOLS:
        return _shell_changes(str(arguments.get("command") or ""))
    if lower in READ_ONLY_TOOLS:
        return False
    if classify(name, target_of(name, arguments)) == "tamper":
        return True
    if lower in DELEGATION_TOOLS:
        return True  # `transcript_changed` looks inside when it can
    action = name.rsplit("__", 1)[-1]  # mcp__server__action
    return not _READ_VERB.match(action)


def acted(tool: str, arguments: Mapping[str, Any] | None) -> bool:
    """A change, or a test run: what opens candor's gate."""
    if changes(tool, arguments):
        return True
    arguments = arguments if isinstance(arguments, Mapping) else {}
    if str(tool or "").strip().lower() in SHELL_TOOLS:
        return classify("bash", str(arguments.get("command") or "")) == "test"
    return False


# --- the transcript of a Claude Code session ---------------------------------------------------


def _entries(path: Path) -> list[dict[str, Any]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


def is_request(entry: Mapping[str, Any]) -> bool:
    """A prompt the person typed: not a tool result, hook feedback or a compaction summary."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isCompactSummary"):
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if not isinstance(content, list):
        return False
    if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return False
    return any(isinstance(b, dict) and str(b.get("text") or "").strip() for b in content)


def _calls(entries: Iterable[Mapping[str, Any]]) -> list[tuple[str, Mapping[str, Any]]]:
    out = []
    for entry in entries:
        content = (entry.get("message") or {}).get("content")
        if entry.get("type") != "assistant" or not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                arguments = block.get("input")
                out.append((str(block.get("name") or ""), arguments if isinstance(arguments, dict)
                            else {}))  # fmt: skip
    return out


def calls_since_request(path: Path) -> list[tuple[str, Mapping[str, Any]]]:
    """The tool calls of the current request: after the last prompt the person typed."""
    entries = _entries(path)
    start = 0
    for index, entry in enumerate(entries):
        if is_request(entry):
            start = index
    return _calls(entries[start:])


def _delegation_changed(path: Path) -> bool:
    """What the subagents did, from their transcripts (`<session>/subagents/*.jsonl`). Without
    them there is nothing to read, and a delegation counts as a change."""
    folder = path.with_suffix("") / "subagents"
    files = sorted(folder.glob("*.jsonl")) if folder.is_dir() else []
    if not files:
        return True
    return any(changes(name, args) for f in files for name, args in _calls(_entries(f))
               if name.lower() not in DELEGATION_TOOLS)  # fmt: skip


def transcript_changed(path: Path) -> bool:
    """Whether the current request of a Claude Code transcript changed anything."""
    calls = calls_since_request(path)
    if any(changes(n, a) for n, a in calls if n.lower() not in DELEGATION_TOOLS):
        return True
    if any(n.lower() in DELEGATION_TOOLS for n, _ in calls):
        return _delegation_changed(path)
    return False
