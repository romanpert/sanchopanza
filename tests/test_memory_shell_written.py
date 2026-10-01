# ruff: noqa: F811  (tests take the imported `store` fixture as a parameter)
"""What a shell command writes (`shell.written`), after the review of v6.2 (2026-10-01).

With shell reads off (v6.2) the shell touch acts only on writes, so a file `written` names but
the command does not write gives a record by mistake. The review probed these.
"""

from __future__ import annotations

import pytest

from sanchopanza.context import shell
from sanchopanza.harness import memory_hook as mh

from .test_memory_hook import (  # noqa: F401  (`store` is the fixture)
    CWD,
    HEX_LINE,
    _bash_setup,
    bash_event,
    context_of,
    store,
    touch_event,
)

PY = "pygments/lexers/carbon.py"


@pytest.mark.parametrize(
    "command",
    [
        f"perl -Mstrict -e 'print 1' {PY}",  # -M is not -i
        f"cat > notes.md <<'E'\nopen('{PY}', 'w')\nE\npython other.py",  # nobody runs that body
        f"cp -t backup/ {PY}",  # -t names the target folder: the file is the source
        f"ls # > {PY}",  # a comment
        f"echo a -> {PY}",  # not a redirection
        f'python -c "\nprint(1)\n# x > {PY}\n"',  # inside a multi-line string
        "Set-Content -Path $f -Value x",  # a variable is not a file name
    ],
)
def test_not_written(command: str) -> None:
    assert PY not in shell.written(command)
    assert all(not w.startswith(("$", "-")) for w in shell.written(command))


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (f"sed -i 's/Hex/Hexadecimal/' {PY}", PY),
        (f"perl -pi -e 's/a/b/' {PY}", PY),
        (f"echo x > {PY}", PY),
        (f"cat >> {PY} <<'E'\nx = 1\nE", PY),
        (f"python - <<'E'\np = '{PY}'\ns = open(p).read()\nopen(p, 'w').write(s)\nE", PY),
        (f"python3 -c \"open('{PY}', 'w').write('x')\"", PY),
        # a script written to /tmp and run in the same command: its writes count (audit #5, #6)
        (
            f"cat > /tmp/fix.py <<'P'\np = '{PY}'\nopen(p, 'w').write('x')\nP\npython /tmp/fix.py",
            PY,
        ),  # fmt: skip
        (f"bash <<'E'\nsed -i 's/a/b/' {PY}\nE", PY),
        (f"cp /tmp/new.py {PY}", PY),
        ('"x" | Out-File -Encoding utf8 b.py', "b.py"),
    ],
)
def test_written(command: str, expected: str) -> None:
    assert expected in shell.written(command)


def test_a_shell_write_after_a_file_tool_edit_still_gives_the_record(store) -> None:
    # v6.1's gate (no shell touch after a file-tool edit) is gone in v6.2
    new = _bash_setup(store)
    mh.handle(touch_event(new, "s2", "Edit", f"{CWD}/README.md", "nothing of s1"))
    out = mh.handle(bash_event(new, "s2", f"sed -i 's/Hex/Hexadecimal/' {PY}"))
    assert "request 1 of session s1" in context_of(out)
    assert HEX_LINE  # the record is the lexer's
