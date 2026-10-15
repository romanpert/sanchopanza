"""Memory v6.1: what a shell command shows that is not the code in view.

Diagnosis on SWE-chat (2026-10-01, `benchmarks/memory_real/v6_diag_sources.py`): of 54 records
the v6 shell touch gave on four seen sets, 28 came from `git diff`/`git show` output and 25 of
those were unrelated; 2 more came from a `gh api ... "$(cat <<EOF ...)"` body. A diff or a log
shows history around the lines, and a message body quotes code it is not looking at.
"""

# ruff: noqa: F811  (tests take the imported `store` fixture as a parameter)
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sanchopanza.context import episodes as ep
from sanchopanza.context import shell
from sanchopanza.harness import memory_hook as mh

from .test_memory_hook import (
    HEX_LINE,
    _bash_setup,
    bash_event,
    context_of,
    store,  # noqa: F401  (the fixture)
)

CARBON = "pygments/lexers/carbon.py"


@pytest.fixture(autouse=True)
def _shell_reads_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests exercise what a shell read shows (v6, v6.1); v6.2 turns reads off by
    default (tests/test_memory_shell_v62.py)."""
    monkeypatch.setattr(mh, "SHELL_READS", True)


DIFF = f"@@ -10,3 +10,4 @@ class CarbonLexer:\n     {HEX_LINE}\n+    (r'0[oO][0-7]+', Number.Oct),"


@pytest.mark.parametrize(
    "command",
    [
        f"git diff {CARBON}",
        f"git diff HEAD -- {CARBON} | head -40",
        f'cd "C:/work/repo" && git diff -- {CARBON}',
        f"git --no-pager diff main...HEAD -- {CARBON}",
        f"git -C C:/work/repo diff --cached {CARBON}",
        f"git show 50cbaec -- {CARBON}",
        f"git log -p -3 -- {CARBON}",
        f"git stash show -p stash@{{0}} -- {CARBON}",
        f"gh pr diff 12 | grep -A3 {CARBON}",
    ],
)
def test_history_output_is_not_code_in_view(store: Path, command: str) -> None:
    new = _bash_setup(store)
    assert mh.handle(bash_event(new, "s2", command, DIFF)) == {}


def test_a_read_beside_git_status_still_counts(store: Path) -> None:
    new = _bash_setup(store)
    out = mh.handle(bash_event(new, "s2", f"git status --short && cat {CARBON}", HEX_LINE))
    assert "session s1" in context_of(out)


def test_a_plain_diff_of_two_files_still_counts(store: Path) -> None:
    # `diff a b` compares files on disk: both are the code as it is now.
    new = _bash_setup(store)
    out = mh.handle(bash_event(new, "s2", f"diff {CARBON} /tmp/carbon.orig", DIFF))
    assert "session s1" in context_of(out)


@pytest.mark.parametrize(
    "command",
    [
        f"gh pr create --title fix --body \"$(cat <<'EOF'\nChanged {CARBON}:\n{HEX_LINE}\nEOF\n)\"",
        f"git commit -q -m \"$(cat <<'EOF'\nfix: hex in {CARBON}\n\n{HEX_LINE}\nEOF\n)\"",
        f"gh api repos/o/r/issues/1/comments -X PATCH --field "
        f"body=\"$(cat <<'B'\nIn {CARBON}:\n{HEX_LINE}\nB\n)\"",
        f'git commit -m "fix: hex in {CARBON}\n\n{HEX_LINE}"',
        f'curl -s https://example.com/hook -d "{CARBON}:\n{HEX_LINE}\n"',
        f'gh pr create --title "fix (carbon)" --body "see {CARBON}\n{HEX_LINE}\n"',
        f"git commit -F - <<'E'\nfix {CARBON}\n{HEX_LINE}\nE",
        # second review, H1: the heredoc belongs to the commit, not to the tests before it
        f"python -m pytest -q && git commit -F - <<'E'\nfix {CARBON}\n{HEX_LINE}\nE",
        f"uv run python -m pytest && gh pr create --body \"$(cat <<'EOF'\n{CARBON}\n{HEX_LINE}"
        '\nEOF\n)"',
    ],
)
def test_a_message_body_is_not_code_in_view(store: Path, command: str) -> None:
    new = _bash_setup(store)
    assert mh.handle(bash_event(new, "s2", command, "")) == {}


def test_an_interpreter_heredoc_still_shows_the_lines_it_replaces(store: Path) -> None:
    new = _bash_setup(store)
    command = (f"python3 - <<'E'\nfrom pathlib import Path\np = Path('{CARBON}')\n"
               f's = p.read_text().replace("""{HEX_LINE}""", "x")\nE')  # fmt: skip
    assert "session s1" in context_of(mh.handle(bash_event(new, "s2", command)))


def test_a_grep_for_a_quoted_line_still_counts(store: Path) -> None:
    new = _bash_setup(store)
    out = mh.handle(bash_event(new, "s2", f'grep -nF "{HEX_LINE}" {CARBON}', ""))
    assert "session s1" in context_of(out)


def test_view_parts() -> None:
    # history: paths stay (a later rule may want them), lines from the output go
    paths, seen, _ = shell.view(f"git diff {CARBON}", DIFF, "C:/work/repo")
    assert paths == [CARBON] and not ep.line_prints(DIFF) & seen
    # a message: neither its paths nor its lines
    command = f"gh pr create --body \"$(cat <<'EOF'\nsee {CARBON}\n{HEX_LINE}\nEOF\n)\""
    paths, seen, _ = shell.view(command, "", "")
    assert paths == [] and not ep.line_prints(HEX_LINE) & seen


# ---- review of v6.1 (2026-10-01): what the first version lost or let through ----------------


@pytest.mark.parametrize(
    "command",
    [
        f"cat {CARBON} && git log --oneline -1",  # H1: cat's lines are current code
        f'grep -rn "git log" {CARBON}',  # H1: a quoted pattern is not a command
        f'echo "now run git diff"; cat {CARBON}',
        f"git show HEAD:{CARBON}",  # M5: the committed file, not a diff
        f"git diff --no-index {CARBON} /tmp/carbon.orig",  # M5: two files on disk
        f"bash <<'E'\ncat {CARBON}\nE",  # M4: a shell heredoc is shell
        f"curl -s https://example.com -o o.json & cat {CARBON}",  # M6: `&` ends a statement
    ],
)
def test_review_current_code_beside_history_or_messages_counts(store: Path, command: str) -> None:
    new = _bash_setup(store)
    assert "session s1" in context_of(mh.handle(bash_event(new, "s2", command, HEX_LINE)))


def test_review_a_quoted_grep_line_after_a_background_curl_counts(store: Path) -> None:
    new = _bash_setup(store)  # M6: `&` is a separator, the grep's quote is not a message
    command = f'curl -s https://example.com -o o.json & grep -nF "{HEX_LINE}" {CARBON}'
    assert "session s1" in context_of(mh.handle(bash_event(new, "s2", command, "")))


def test_review_a_history_pipe_and_a_silent_statement_still_hide_the_output(store: Path) -> None:
    new = _bash_setup(store)
    command = f'cd "C:/work/repo" && git status --short && git diff -- {CARBON} | head -40'
    assert mh.handle(bash_event(new, "s2", command, DIFF)) == {}


def test_review_a_file_written_by_cat_is_not_read_from_its_body() -> None:
    # L7: `.py` in the target is not an interpreter; the body is what the write rule replaces
    paths, seen, _ = shell.view(f"cat > fix.py <<'E'\nsee {CARBON}\n{HEX_LINE}\nE", "", "")
    assert paths == ["fix.py"] and not ep.line_prints(HEX_LINE) & seen


@pytest.mark.parametrize(
    "command",
    [
        "git" + " -C x" * 400 + " diff",  # H2: exponential backtracking in the first version
        "git" + " -a" * 400 + ' x "q"',
        '"' + '\\"' * 50_000,  # M3: unclosed escaped quotes
        "gh pr create --body '" + "x(" * 50_000,
        "A=1 " * 50_000 + "git diff",  # second review, H2: prefixes stripped one copy at a time
        "sudo " * 40_000 + "cat f.py",
        "x <<E\n" * 20_000,
    ],
    ids=[
        "git-C",
        "git-flags",
        "escaped-quotes",
        "open-quote",
        "assignments",
        "sudo",
        "heredocs",
    ],  # an id is an env variable  # fmt: skip
)
def test_review_long_adversarial_commands_parse_quickly(command: str) -> None:
    import time

    start = time.perf_counter()
    shell.view(command, "out", "C:/work/repo")
    assert time.perf_counter() - start < 2.0  # linear: ~0.1 s; the regexes it replaced took 6-9 s


# ---- second review of v6.1 (2026-10-01) ----------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        f'uv run --with rich python - <<\'E\'\ns = s.replace("""{HEX_LINE}""", \'x\')\nE',  # M1
        f'docker exec -i c python - <<\'E\'\ns = s.replace("""{HEX_LINE}""", \'x\')\nE',
        f'cat <<\'E\' | python3 -\ns = s.replace("""{HEX_LINE}""", \'x\')\nE',
    ],
)
def test_second_review_an_interpreter_anywhere_in_the_heredoc_s_statement(
    store: Path, command: str
) -> None:
    new = _bash_setup(store)
    assert "session s1" in context_of(mh.handle(bash_event(new, "s2", f"cat {CARBON}; " + command)))


@pytest.mark.parametrize(
    "command",
    [
        f"git show abc123 -- C:/work/repo/{CARBON}",  # M2: a drive's colon is not rev:path
        f"git diff -- {CARBON} |& head -40",  # L: `|&` pipes stderr too
        f"git diff $(git merge-base HEAD main) -- {CARBON}",
    ],
)
def test_second_review_history_output_still_hidden(store: Path, command: str) -> None:
    new = _bash_setup(store)
    assert mh.handle(bash_event(new, "s2", command, DIFF)) == {}


@pytest.mark.parametrize(
    "command",
    [
        f"git diff --stat  # what's new\ncat {CARBON}",  # M3: a comment's apostrophe
        f"curl -s https://x.org  # don't cache\ncat {CARBON}",
        f'grep -n "<<EOF" run.sh\ncat {CARBON}',  # L: `<<` inside quotes is not a heredoc
    ],
)
def test_second_review_current_code_after_a_comment_or_a_quoted_marker(
    store: Path, command: str
) -> None:
    new = _bash_setup(store)
    assert "session s1" in context_of(mh.handle(bash_event(new, "s2", command, HEX_LINE)))


def test_second_review_powershell_backticks_escape_and_continue(store: Path) -> None:
    new = _bash_setup(store)
    read = f'git commit -m "a`"b"; Get-Content {CARBON}'  # M4: `" is an escaped quote
    assert "session s1" in context_of(mh.handle(ps_event(new, "s2", read, HEX_LINE)))
    other = _bash_setup(store)
    continued = f"git diff `\n  -- {CARBON}"  # a backtick at the end of a line continues it
    assert mh.handle(ps_event(other, "s2", continued, DIFF)) == {}


def test_second_review_a_powershell_here_string_body_is_a_message(store: Path) -> None:
    new = _bash_setup(store)  # with an apostrophe in it
    command = f"gh pr create --body @'\ndon't break {CARBON}\n{HEX_LINE}\n'@"
    assert mh.handle(ps_event(new, "s2", command, "")) == {}


def ps_event(path: Path, session: str, command: str, stdout: str = "") -> dict[str, Any]:
    return {**bash_event(path, session, command, stdout), "tool_name": "PowerShell"}


def test_second_review_git_show_paths_are_files_only() -> None:
    paths, _, _ = shell.view("git -C C:/w show HEAD:f.py", "", "")
    assert "/w" not in paths and "f.py" in paths
    paths, _, _ = shell.view('git show HEAD:"a b.py"', "", "")
    assert '""' not in paths and "" not in paths


# ---- B2, post hoc (2026-10-01): a read and a diff in one command ----------------------------

OTHER = "class OtherThing:\n    def method_with_a_long_name(self):"
GIT_DIFF = (
    "diff --git a/pkg/other.py b/pkg/other.py\nindex 1..2 100644\n--- a/pkg/other.py\n"
    f"+++ b/pkg/other.py\n@@ -1,3 +1,3 @@\n     {HEX_LINE}\n-    old_line_of_the_other_file = 1\n"
    "+    new_line_of_the_other_file = 2\n"
)


def test_counts_and_a_diff_are_history_only(store: Path) -> None:
    new = _bash_setup(store)  # Sonnet in B2: `wc -l a b; grep -c t a b; git diff f | head -60`
    command = f"wc -l /tmp/b.txt /tmp/a.txt; grep -c test_main /tmp/b.txt; git diff {CARBON} | head"
    assert mh.handle(bash_event(new, "s2", command, "3 /tmp/b.txt\n" + GIT_DIFF)) == {}


def test_a_read_beside_a_diff_keeps_the_read_and_drops_the_diff(store: Path) -> None:
    # `sed -n 176,200p f; git diff g`: the sed lines are in view, the diff's are not
    new = _bash_setup(store)
    command = f"sed -n 1,40p {CARBON}; git diff pkg/other.py"
    shown = f"tokens = {{\n    {HEX_LINE}\n}}\n"
    assert "session s1" in context_of(mh.handle(bash_event(new, "s2", command, shown + GIT_DIFF)))


def test_a_read_beside_a_diff_does_not_give_from_the_diff(store: Path) -> None:
    new = _bash_setup(store)  # the sed shows other code; only the diff shows the record's line
    command = f"sed -n 1,5p README.md; git diff {CARBON}"
    assert mh.handle(bash_event(new, "s2", command, OTHER + "\n" + GIT_DIFF)) == {}


def test_without_history_a_unified_diff_in_the_output_stays() -> None:
    # `diff -u a b` compares files on disk: no history command, nothing stripped
    _, seen, _ = shell.view(f"diff -u {CARBON} /tmp/carbon.orig", GIT_DIFF, "")
    assert ep.line_prints(HEX_LINE) <= seen
