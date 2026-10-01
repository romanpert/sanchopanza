"""What a shell command shows and what it writes, for the memory touch (v6).

An agent that reads and edits through Bash or PowerShell (Sonnet 5.5 in phase B2, 2026-10-01)
names files in its commands and shows their lines in the output. `view` gives the files a
command names, prints of the lines it shows, and the folder it ran in; `written` gives the files
it writes. Parsing only, no execution; every pattern is bounded so a 200,000-character command
or output costs milliseconds.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from . import episodes as ep
from . import statements as st

SCAN = 200_000  # characters of a command's output read for lines in view
PATHS = 20
_EXT = r"\.[A-Za-z]\w{0,7}"
# A file: a path with an extension, a Windows drive allowed in front.
PATH = re.compile(rf"(?<![\w@~./\\:-])(?:[A-Za-z]:)?[\w@~./\\-]*[\w-]{_EXT}(?![\w./\\-])")
_GREP_PREFIX = re.compile(rf"^((?:[A-Za-z]:)?[^\s:]{{1,400}}{_EXT})[:-]\d+[:-]", re.M)
_LINE_PREFIX = re.compile(
    rf"^(?:(?:[A-Za-z]:)?[^\s:]{{1,400}}{_EXT}[:-])?\s{{0,12}}\d{{1,9}}(?:[:\t→-]|\s{{2,}})",
    re.M,
)
_CD = re.compile(r"^\s*cd\s+(\"[^\"]+\"|'[^']+'|\S+)\s*(?:&&|;)")
_TRIPLE = re.compile(r"\"\"\"|'''")
_HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*['\"]?(\w+)['\"]?")
_INTERPRETER = re.compile(r"\b(python[\d.]*|py|node|deno|ruby|perl|php)\b")
_INLINE = re.compile(r"\s-[ce]\s+(\"(?:[^\"\\]|\\.){0,20000}\"|'[^']{0,20000}')")
_OPEN = re.compile(r"\bopen\(\s*([^,()\n]{1,300}?)\s*,\s*['\"](?:w|a|x|r\+)b?\+?['\"]")
_METHOD = re.compile(r"(Path\(\s*['\"][^'\"\n]{1,300}['\"]\s*\)|[A-Za-z_]\w{0,60})\s*"
                     r"\.write_(?:text|bytes)\(")  # fmt: skip
_NODE = re.compile(r"\b(?:writeFileSync|appendFileSync|writeFile)\(\s*([^,()\n]{1,300}?)\s*,")
_LITERAL = re.compile(r"^(?:Path\(\s*)?['\"]([^'\"\n]{1,300})['\"]\s*\)?$")
_IN_PLACE = re.compile(r"\bsed\s+(?:-\S+\s+){0,6}?(?:-\w*i\S*|--in-place\S*)|"
                       r"\bperl\s+(?:-\S+\s+){0,6}?-\w*i")  # fmt: skip
_PS_WRITE = re.compile(r"\b(?:Set-Content|Out-File|Add-Content)\b"
                       r"(?:\s+-(?:Path|FilePath|LiteralPath))?\s+['\"]?([^\s'\"|;]{1,400})",
                       re.I)  # fmt: skip
_REDIRECT = re.compile(r"(?<![<>&\d])>>?\s*['\"]?([\w@~./\\:-]{1,400})|"
                       r"\btee\s+(?:-a\s+)?['\"]?([\w@~./\\:-]{1,400})")  # fmt: skip
_COPY = re.compile(r"\b(?:cp|mv|Copy-Item|Move-Item)\b[^|;&\n]{0,2000}?\s['\"]?"
                   rf"((?:[A-Za-z]:)?[\w@~./\\-]{{1,400}}{_EXT})['\"]?\s*$")  # fmt: skip
_QUOTED = re.compile(r"\"(?:[^\"\\\n]|\\.){0,2000}\"|'[^'\n]{0,2000}'")


_HERE_STRING = re.compile(r"@(['\"])[ \t]*\r?$")  # PowerShell: `@'` ends the line, `'@` closes


def _opening(line: str, escape: str) -> tuple[str, int] | None:
    """(the line that closes the heredoc this line opens, where its marker is), or None. A
    `<<` inside quotes or a comment opens nothing (`grep -n "<<EOF" run.sh`); `<<<` is shell."""
    found: list[tuple[str, int]] = []
    if "<<" in line:
        found = [(m.group(1), m.start()) for m in _HEREDOC.finditer(line)]
    here = _HERE_STRING.search(line) if escape == "`" else None
    if here:
        found.append((here.group(1) + "@", here.start()))
    if not found:
        return None
    parts = st.split(line, escape)
    for closing, position in found:
        inside = [s for s in parts if s.start <= position < s.end]
        if inside and not any(a <= position < b for a, b in inside[0].quotes):
            return closing, position
    return None


def _heredocs(command: str, escape: str = "\\") -> tuple[list[str], list[tuple[str, int, str]]]:
    """(the shell's own lines, (opening line, marker position, body) of each heredoc or
    PowerShell here-string)."""
    shell: list[str] = []
    bodies: list[tuple[str, int, list[str]]] = []
    closing = ""
    for line in command.split("\n"):
        if closing:
            done = line.startswith(closing) if closing.endswith("@") else line.strip() == closing
            if done:
                closing = ""
            else:
                bodies[-1][2].append(line + "\n")
            continue
        shell.append(line)
        opened = _opening(line, escape)
        if opened:
            closing = opened[0]
            bodies.append((line, opened[1], []))
    return shell, [(opener, at, "".join(body)) for opener, at, body in bodies]


def _parts(command: str) -> tuple[list[str], list[str]]:
    """(the shell's own lines, the bodies of its heredocs)."""
    shell, bodies = _heredocs(command)
    return shell, [body for _, _, body in bodies]


def _target(argument: str, code: str) -> str | None:
    """A write call's file: a string literal, or a name assigned one in the same code."""
    argument = argument.strip()
    literal = _LITERAL.match(argument)
    if literal:
        return literal.group(1)
    if re.fullmatch(r"[A-Za-z_]\w{0,60}", argument):
        assigned = re.findall(rf"\b{argument}\s*=\s*(?:Path\(\s*)?['\"]([^'\"\n]{{1,300}})['\"]",
                              code)  # fmt: skip
        return assigned[-1] if assigned else None
    return None


def _code_targets(code: str) -> list[str]:
    found = [_target(m.group(1), code) for m in _OPEN.finditer(code)]
    found += [_target(m.group(1), code) for m in _METHOD.finditer(code)]
    found += [_target(m.group(1), code) for m in _NODE.finditer(code)]
    return [f for f in found if f and PATH.fullmatch(f)]


def written(command: Any) -> list[str]:
    """The files a command writes, as it names them: the target of a redirection, `tee`, `cp`
    or `mv`, the files of an in-place `sed`/`perl`, the target of PowerShell's `Set-Content`/
    `Out-File`, and the file an interpreter's code (a heredoc or `-c`/`-e`) opens for writing.
    A file the code only reads is not written."""
    if not isinstance(command, str):
        return []
    shell, bodies = _parts(command)
    text = "\n".join(shell)
    out: list[str] = []
    if _INTERPRETER.search(text):
        codes = [*bodies, *(m.group(1)[1:-1] for m in _INLINE.finditer(text))]
        for code in codes:
            out += _code_targets(code)
    bare = _QUOTED.sub('""', text)  # a `>` or a path inside quotes is not the shell's
    for segment in re.split(r"&&|\|\||;|\||\n", bare):
        if _IN_PLACE.search(segment):
            out += PATH.findall(segment)
        out += [m.group(1) for m in _PS_WRITE.finditer(segment)]
        for match in _REDIRECT.finditer(segment):
            target = match.group(1) or match.group(2)
            if PATH.fullmatch(target):
                out.append(target)
        copied = _COPY.search(segment)
        if copied:
            out.append(copied.group(1))
    return list(dict.fromkeys(out))


def view(
    command: Any, response: Any, cwd: str, powershell: bool = False
) -> tuple[list[str], set[str], str]:
    """(the files a command names, prints of the lines it shows, the folder it ran in).
    Files: paths with an extension in the command and at the head of grep-style output lines.
    Lines: the output's (`stdout`), without grep's `path:12:` or `cat -n`'s numbering, and the
    command's own, split at triple quotes, and what it quotes (a `python - <<E` edit carries the
    old lines in its `s.replace`, a `grep -F "line"` the line). A leading `cd DIR &&` moves
    the folder. Not in view (v6.1): the output of a history command (`git diff/show/log`,
    `gh pr diff`), a heredoc body no interpreter runs (`gh pr create --body "$(cat <<EOF`),
    and the quoted strings of a messaging command (`git commit -m`, `gh`, `curl -d`). PowerShell
    escapes with a backtick and has here-strings (`@'...'@`)."""
    if not isinstance(command, str) or not command.strip():
        return [], set(), cwd
    own, quoted, history, extra = _own(command[:SCAN], "`" if powershell else "\\")
    out = response.get("stdout") if isinstance(response, Mapping) else response
    out = out[:SCAN] if isinstance(out, str) and history != "only" else ""
    out = without_diffs(out) if history == "mixed" else out
    base = cwd
    moved = _CD.match(command)
    if moved:
        folder = moved.group(1).strip("\"'")
        absolute = folder.startswith(("/", "\\")) or bool(re.match(r"^[A-Za-z]:", folder))
        base = folder if absolute or not cwd else f"{cwd.rstrip('/')}/{folder}"
    raws = list(dict.fromkeys([*PATH.findall(own), *extra, *_GREP_PREFIX.findall(out)]))
    lines = "\n".join([_LINE_PREFIX.sub("", out), *_TRIPLE.split(own), *quoted])
    return raws[:PATHS], ep.line_prints(lines), base


def _own(command: str, escape: str) -> tuple[str, list[str], str, list[str]]:
    """(the command's own text in view, its quoted strings in view, whether history is in its
    output (`statements.history_in`), paths `git show <rev>:<path>` prints). A heredoc's body is
    source when an interpreter runs it and more shell when a shell does; anything else (`cat >
    f`, a commit or PR body) is not in view, and neither are the quoted strings of a messaging
    statement (v6.1)."""
    shell_lines, bodies = _heredocs(command, escape)
    kinds = [(st.body_kind(opener, at, escape), body) for opener, at, body in bodies]
    text = "\n".join([*shell_lines, *(body for kind, body in kinds if kind == "shell")])
    code = [body for kind, body in kinds if kind == "code"]
    parts = st.split(text, escape)
    own: list[str] = []
    quoted: list[str] = []
    for s in parts:
        if st.messenger(st.words(text, s)):
            own.append(st.blanked(text, s))
            continue
        own.append(text[s.start : s.end])
        quoted += [text[a + 1 : b - 1] for a, b in s.quotes if b - a <= 2002]
    quoted += [q[1:-1] for body in code for q in _QUOTED.findall(body)]
    history = st.history_in(text, parts)
    return "\n".join([*own, *code]), quoted, history, st.git_show_paths(text, parts)


_DIFF_START = re.compile(r"^(?:diff --git |@@ )")
_DIFF_LINE = re.compile(
    r"^(?:[ +\-]|index |new file|deleted file|similarity|rename |old mode|new mode)"
)


def without_diffs(out: str) -> str:
    """The output without its unified-diff blocks: from a `diff --git` or `@@` line, every line
    a diff writes (context, `+`, `-`, headers) until one it would not (v6.1: in B2, `sed -n
    176,200p f; git diff g` showed f's lines and g's history in one output)."""
    keep: list[str] = []
    inside = False
    for line in out.split("\n"):
        if _DIFF_START.match(line):
            inside = True
            continue
        if inside and _DIFF_LINE.match(line):
            continue
        inside = False
        keep.append(line)
    return "\n".join(keep)
