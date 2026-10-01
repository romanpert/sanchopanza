"""A shell command's statements, for what it shows (memory v6.1).

On SWE-chat (2026-10-01) 25 of the v6 shell touch's 37 unrelated records came from `git diff` or
`git show` output, and 2 from a message body (`gh api ... --field body="$(cat <<EOF ...)"`): a
diff shows history around the lines, a message quotes code the agent is not looking at. Which of
a command's parts are such is a property of each statement (`cat f && git log -1` shows `f`), so
the command is cut into statements by one linear pass that respects quotes and comments, and
each is judged by its program. No regular expression here can backtrack on a long command.
Bash and PowerShell differ in their escape: `\\` in Bash, a backtick in PowerShell (where it also
continues a line, and a backslash is an ordinary character).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SPECIAL = {"\\": re.compile(r"[\"'\\;|&()\n`$#]"), "`": re.compile(r"[\"'`;|&()\n$#]")}
_WORD_START = frozenset(" \t\n;&|(")
_ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
_PREFIXES = frozenset({"sudo", "time", "command", "env", "nohup", "exec", "builtin"})
INTERPRETER = re.compile(r"(?:python[\d.]*|py|node|deno|bun|ruby|perl|php)(?:\.exe)?", re.I)
SHELLS = re.compile(r"(?:bash|sh|zsh|dash|ksh|pwsh|powershell)(?:\.exe)?", re.I)
_FILE = re.compile(r"[\w@~./\\-]*[\w-]\.[A-Za-z]\w{0,7}")
_DRIVE = re.compile(r"^[A-Za-z]:[/\\]")
_GIT_VALUED = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"})
# History: around the lines, not the code as it is now. `show <rev>:<path>` prints a file and
# `diff --no-index` compares two files on disk: those are code.
_HISTORY = frozenset({"diff", "show", "log", "whatchanged", "format-patch", "range-diff"})
_GIT_MESSAGES = frozenset({"commit", "tag", "notes", "merge", "stash"})
_MESSENGERS = frozenset({"gh", "glab", "curl", "wget", "hub"})
# Statements whose output holds no lines of code: they neither show nor hide anything. (`head`
# and `tail` read a file when they stand alone; after a history command's pipe they are filters.)
_SILENT = frozenset({"cd", "pushd", "popd", "export", "set", "unset", "echo", "printf", "true",
                     "false", "sleep", "mkdir", "ls", "pwd", "wc", "which", "clear",
                     ":"})  # fmt: skip
_GIT_SILENT = frozenset({"status", "add", "branch", "rev-parse", "fetch", "checkout", "switch",
                         "restore", "reset", "push", "pull", "remote", "config", "init", "rm",
                         "mv", "commit", "tag", "notes", "merge", "stash", "worktree",
                         "merge-base", "rev-list", "describe", "ls-files"})  # fmt: skip


@dataclass(frozen=True)
class Statement:
    start: int
    end: int
    quotes: tuple[tuple[int, int], ...]  # absolute spans, quote characters included
    piped: bool  # its input is the previous statement's output


def split(text: str, escape: str = "\\") -> list[Statement]:
    """The statements of shell text: cut at `&&`, `||`, `;`, `|`, `|&`, `&`, `(`, `)`, `$(`
    and line breaks outside quotes (`2>&1` and `&>` are redirections; in Bash a backtick too).
    A `#` that starts a word comments to the end of the line. An unclosed quote runs to the
    end. `escape` is `\\` (Bash) or a backtick (PowerShell). One pass, linear."""
    special = _SPECIAL[escape]
    out: list[Statement] = []
    quotes: list[tuple[int, int]] = []
    start, piped, i, n = 0, False, 0, len(text)
    while True:
        match = special.search(text, i)
        if match is None:
            break
        i, c = match.start(), match.group()
        if c in "\"'":
            close = _close(text, i, c, escape)
            quotes.append((i, close))
            i = close
            continue
        if c == escape:
            i += 2
            continue
        if c == "#":
            if i == 0 or text[i - 1] in _WORD_START:
                out.append(Statement(start, i, tuple(quotes), piped))
                end = text.find("\n", i)
                quotes, start, piped = [], n if end < 0 else end, False
                i = start
            else:
                i += 1
            continue
        width = _separator(text, i, c)
        if not width:
            i += 1
            continue
        out.append(Statement(start, i, tuple(quotes), piped))
        piped = c == "|" and text[i : i + 2] != "||"
        quotes, start, i = [], i + width, i + width
    out.append(Statement(start, n, tuple(quotes), piped))
    return out


def _close(text: str, i: int, quote: str, escape: str) -> int:
    """The end (exclusive) of the quoted string opening at `i`, or of the text. Single quotes
    have no escape (PowerShell doubles them: `'don''t'`); in double quotes `escape` escapes."""
    n = len(text)
    if quote == "'":
        j = i + 1
        while True:
            end = text.find("'", j)
            if end < 0:
                return n
            if escape == "`" and text[end + 1 : end + 2] == "'":
                j = end + 2
                continue
            return end + 1
    j = i + 1
    while True:
        end = text.find('"', j)
        if end < 0:
            return n
        k = end - 1
        while k > i and text[k] == escape:
            k -= 1
        if (end - 1 - k) % 2 == 0:
            return end + 1
        j = end + 1


def _separator(text: str, i: int, c: str) -> int:
    two = text[i : i + 2]
    if two in ("&&", "||", "$(", "|&"):
        return 2
    if c == "&":
        return 0 if text[i - 1 : i] in (">", "<") or text[i + 1 : i + 2] == ">" else 1
    return 1 if c in ";|\n()`" else 0


def blanked(text: str, s: Statement) -> str:
    """The statement with its quoted strings as `""`."""
    parts, last = [], s.start
    for a, b in s.quotes:
        parts += [text[last:a], '""']
        last = b
    return "".join([*parts, text[last : s.end]])


def words(text: str, s: Statement) -> list[str]:
    """The statement's words, quotes blanked, without leading assignments and prefixes."""
    out = blanked(text, s).split()
    k = 0
    while k < len(out) and (_ASSIGNMENT.match(out[k]) or out[k] in _PREFIXES):
        k += 1
    return out[k:]


def program(ws: list[str]) -> str:
    return ws[0].replace("\\", "/").rsplit("/", 1)[-1].lower() if ws else ""


def _is_git(ws: list[str]) -> bool:
    return program(ws) in ("git", "git.exe")


def git_subcommand(ws: list[str]) -> tuple[str, list[str]]:
    """(the subcommand of a `git ...` statement, the words after it)."""
    k = 1
    while k < len(ws):
        if ws[k] in _GIT_VALUED:
            k += 2
        elif ws[k].startswith("-"):
            k += 1
        else:
            return ws[k], ws[k + 1 :]
    return "", []


def _revisions(rest: list[str]) -> list[str]:
    """The words before `--` that are not options."""
    head = rest[: rest.index("--")] if "--" in rest else rest
    return [w for w in head if not w.startswith("-")]


def _rev_paths(rest: list[str]) -> list[str]:
    """`<rev>:<path>` words (not a Windows drive's colon): their paths."""
    out = [w.split(":", 1)[1] for w in _revisions(rest) if ":" in w and not _DRIVE.match(w)]
    return [p for p in out if _FILE.fullmatch(p)]


def history(ws: list[str]) -> bool:
    name = program(ws)
    if name == "gh":
        return ws[1:3] == ["pr", "diff"]
    if not _is_git(ws):
        return False
    sub, rest = git_subcommand(ws)
    if sub == "stash":
        return rest[:1] == ["show"]
    if sub not in _HISTORY:
        return False
    if sub == "diff" and "--no-index" in rest:
        return False
    return not (sub == "show" and any(":" in w and not _DRIVE.match(w) for w in _revisions(rest)))


def messenger(ws: list[str]) -> bool:
    if _is_git(ws):
        return git_subcommand(ws)[0] in _GIT_MESSAGES
    return program(ws) in _MESSENGERS


def silent(ws: list[str]) -> bool:
    if not ws:
        return True
    if _is_git(ws):
        return git_subcommand(ws)[0] in _GIT_SILENT
    return program(ws) in _SILENT


def output_is_history(text: str, statements: list[Statement]) -> bool:
    """The output shows history only: a history command ran, and every other statement either
    reads its output through a pipe or prints no code (`cd`, `echo`, `git status`, `head`)."""
    seen_history = in_history_pipe = False
    for s in statements:
        ws = words(text, s)
        if ws and ws[0].startswith("-"):
            continue  # the arguments left after a `$(...)` inside a statement
        if history(ws):
            seen_history = in_history_pipe = True
            continue
        in_history_pipe = in_history_pipe and s.piped
        if not in_history_pipe and not silent(ws):
            return False
    return seen_history


def _kind(ws: list[str]) -> str:
    if messenger(ws):
        return ""
    if any(INTERPRETER.fullmatch(program([w])) for w in ws):
        return "code"
    return "shell" if ws and SHELLS.fullmatch(program(ws)) else ""


def body_kind(opener: str, marker: int, escape: str = "\\") -> str:
    """What reads the heredoc whose marker is at `marker` on its opening line: the statement
    holding the marker, or one it pipes into (`cat <<E | python3`). "code" (an interpreter: the
    body is source, with the old lines an edit replaces), "shell" (bash, sh, PowerShell: more
    commands), or "" (anything else: `cat > f`, `git commit -F -`, `gh --body`)."""
    parts = split(opener, escape)
    owner = next((k for k, s in enumerate(parts) if s.start <= marker < s.end), None)
    if owner is None:
        return ""
    kind = _kind(words(opener, parts[owner]))
    for s in parts[owner + 1 :]:
        if kind or not s.piped:
            break
        kind = _kind(words(opener, s))
    return kind


def quoted_at(text: str, position: int, escape: str = "\\") -> bool:
    """Whether `position` is inside a quoted string or a comment of `text` (one line)."""
    parts = split(text, escape)
    if not any(s.start <= position < s.end for s in parts):
        return True  # in no statement: a comment
    return any(a <= position < b for s in parts for a, b in s.quotes)


def git_show_paths(text: str, statements: list[Statement]) -> list[str]:
    """The files `git show <rev>:<path>` prints."""
    out = []
    for s in statements:
        ws = words(text, s)
        if _is_git(ws):
            sub, rest = git_subcommand(ws)
            out += _rev_paths(rest) if sub == "show" else []
    return out
