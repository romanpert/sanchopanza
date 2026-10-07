"""Passages on arrival (`context.passages`): the pure cut, no decider, no hook.

Bet A of `docs/PLAN-GANAR-H2H.md`: a large shell output or Read keeps only what bears on the
agent's step, at a fraction of its size, with every failure line of a test log kept by rule.
"""

from __future__ import annotations

import re

from sanchopanza.context import passages as ps

OMITTED = re.compile(r"^\[\.\.\. sanchopanza omitted lines? (\d+)(?:-(\d+))? \(")


def pytest_log(passing: int = 300) -> str:
    lines = ["============================= test session starts ==============================",
             "platform linux -- Python 3.12.1, pytest-8.3.2", "collected 302 items", ""]
    lines += [f"tests/test_mod_{i // 20}.py::test_case_{i} PASSED" for i in range(passing)]
    lines += [
        "tests/test_app.py::test_add FAILED",
        "tests/test_app.py::test_parse FAILED",
        "",
        "=================================== FAILURES ===================================",
        "___________________________________ test_add ___________________________________",
        "",
        "    def test_add():",
        ">       assert add(1, 2) == 3",
        "E       assert -1 == 3",
        "E        +  where -1 = add(1, 2)",
        "",
        "tests/test_app.py:12: AssertionError",
        "__________________________________ test_parse __________________________________",
        "Traceback (most recent call last):",
        '  File "/repo/app/parse.py", line 40, in parse',
        "    return int(value)",
        "ValueError: invalid literal for int() with base 10: 'x'",
        "=========================== short test summary info ============================",
        "FAILED tests/test_app.py::test_add - assert -1 == 3",
        "FAILED tests/test_app.py::test_parse - ValueError: invalid literal",
        "======================== 2 failed, 300 passed in 3.21s =========================",
    ]
    return "\n".join(lines) + "\n"


def module_source(functions: int = 80) -> str:
    parts = ['"""A settings module."""\n\nimport os\nimport json\n\n\n']
    for i in range(functions):
        if i == 41:
            parts.append(
                "def parse_config(path):\n"
                "    \"\"\"Read the config file and merge the defaults.\"\"\"\n"
                "    raw = json.loads(open(path).read())\n"
                "    defaults = load_defaults()\n"
                "    return {**raw, **defaults}  # the bug: defaults win\n\n\n"
            )
        parts.append(
            f"def helper_{i}(value):\n"
            f"    total = value * {i} + {i}\n"
            f"    return total - {i}\n\n\n"
        )
    return "".join(parts)


def check_line_numbers(original: str, shown: str) -> None:
    """Every kept line is literal and every marker names the original lines it replaces."""
    lines = original.splitlines()
    cursor = 1
    for line in shown.splitlines():
        found = OMITTED.match(line)
        if found:
            first = int(found[1])
            last = int(found[2] or found[1])
            assert first == cursor, f"marker says {first}, the next original line is {cursor}"
            cursor = last + 1
            continue
        assert lines[cursor - 1] == line, f"line {cursor} is not literal: {line!r}"
        cursor += 1
    assert cursor - 1 <= len(lines)


def test_settings_turn_tokens_into_characters_at_the_measured_ratio():
    settings = ps.Settings()
    assert settings.tokens == 2000 and settings.fraction == 0.25
    assert settings.threshold_chars == 4400


def test_kinds_by_tool_command_and_suffix():
    assert ps.kind_of("Read", {"file_path": "/r/app/settings.py"}, "x") == "code"
    assert ps.kind_of("Read", {"file_path": "/r/README.md"}, "x") == "prose"
    assert ps.kind_of("Bash", {"command": "python -m pytest -q tests"}, "x") == "test"
    assert ps.kind_of("PowerShell", {"command": "npm test"}, "x") == "test"
    assert ps.kind_of("Bash", {"command": "ls -la"}, "x") == "shell"
    assert ps.kind_of("Bash", {"command": "make"}, pytest_log()) == "test", "by its shape"


def test_a_pytest_log_keeps_every_failure_line_and_the_summary():
    log = pytest_log()
    cut = ps.cut_free(log, "test", "why does test_add fail", ps.Settings())
    assert cut.text is not None, cut.reason
    must = [line for line in log.splitlines()
            if re.search(r"FAILED|^E |^>|Traceback|File \"|Error|short test summary|failed,", line)]
    for line in must:
        assert line in cut.text.splitlines(), f"lost a failure line: {line!r}"
    assert len(cut.text) < 0.5 * len(log)
    assert cut.report["must_lines"] >= len(must) - 1
    check_line_numbers(log, cut.text)


def test_a_large_python_read_keeps_the_pertinent_function_with_its_line_numbers():
    source = module_source()
    query = "the config parser ignores the defaults; look at parse_config and load_defaults"
    cut = ps.cut_free(source, "code", query, ps.Settings())
    assert cut.text is not None, cut.reason
    assert "def parse_config(path):" in cut.text
    assert "    return {**raw, **defaults}  # the bug: defaults win" in cut.text
    assert "def helper_70(" not in cut.text
    assert len(cut.text) <= 0.4 * len(source)
    check_line_numbers(source, cut.text)


def test_a_marker_in_code_names_the_definitions_it_left_out():
    source = module_source()
    cut = ps.cut_free(source, "code", "parse_config defaults", ps.Settings())
    assert cut.text is not None
    assert re.search(r"omitted lines \d+-\d+ \(\d+ chars; def helper_\d+", cut.text)


def test_a_fragment_of_a_long_function_keeps_its_signature():
    body = "".join(f"    step_{i} = compute(step_{i - 1})\n" for i in range(1, 160))
    source = "import os\n\n\ndef long_pipeline(x):\n" + body + "    return frozen_marker\n"
    source += "".join(f"\n\ndef other_{i}():\n    return {i}\n" for i in range(60))
    cut = ps.cut_free(source, "code", "where is frozen_marker returned", ps.Settings())
    assert cut.text is not None
    assert "    return frozen_marker" in cut.text
    assert "def long_pipeline(x):" in cut.text, "a kept fragment shows whose body it is"
    check_line_numbers(source, cut.text)


def test_shell_output_is_cut_by_blank_lines_and_headers():
    blocks = []
    for i in range(40):
        name = "needle_target.py" if i == 23 else f"file_{i}.py"
        blocks.append(f"==> src/{name} <==\n" + "".join(f"line {j} of {name}\n" for j in range(8)))
    text = "\n".join(blocks)
    cut = ps.cut_free(text, "shell", "show needle_target", ps.Settings())
    assert cut.text is not None
    assert "==> src/needle_target.py <==" in cut.text and "line 7 of needle_target.py" in cut.text
    check_line_numbers(text, cut.text)


def test_the_fraction_sets_the_size():
    source = module_source(120)
    quarter = ps.cut_free(source, "code", "parse_config", ps.Settings(fraction=0.25))
    tenth = ps.cut_free(source, "code", "parse_config", ps.Settings(fraction=0.10))
    assert quarter.text is not None and tenth.text is not None
    assert len(tenth.text) < len(quarter.text) <= 0.35 * len(source)
    assert "def parse_config(path):" in tenth.text


def test_small_output_and_a_cut_that_saves_little_pass_whole():
    assert ps.cut_free("short\n" * 10, "shell", "x", ps.Settings()).text is None
    every_line_fails = "".join(f"FAILED tests/t.py::test_{i} - boom\n" for i in range(400))
    cut = ps.cut_free(every_line_fails, "test", "x", ps.Settings())
    assert cut.text is None and "saves" in cut.reason


def test_no_query_terms_in_common_keeps_the_tail_of_a_log():
    text = "".join(f"compiling unit {i}\n\n" for i in range(600)) + "BUILD OK in 12s\n"
    cut = ps.cut_free(text, "shell", "zzzz qqqq", ps.Settings())
    assert cut.text is not None and "BUILD OK in 12s" in cut.text


def test_identifiers_match_their_words():
    assert ps.expand("parseConfig load_defaults") == (
        "parseConfig load_defaults parse config load defaults"
    )


def test_the_preview_fits_its_limit_and_starts_with_the_failures():
    log = pytest_log(3000)
    layout = ps.layout(log, "test", ps.budget_for(log, ps.Settings()))
    order = ps.bm25_order(log, layout, "test_add")
    shown = ps.fit(log, layout, order, 1500)
    assert len(shown) <= 1500
    assert "FAILED tests/test_app.py::test_add - assert -1 == 3" in shown
    assert "2 failed, 300 passed" in shown or "2 failed, 3000 passed" in shown


def test_a_gap_shorter_than_its_marker_is_kept():
    """A marker for one blank line costs more than the line (dry run, 2026-10-07)."""
    log = pytest_log()
    cut = ps.cut_free(log, "test", "test_add", ps.Settings())
    assert cut.text is not None
    for line in cut.text.splitlines():
        found = re.search(r"omitted lines? \d+(?:-\d+)? \((\d+) chars", line)
        if found:
            assert int(found[1]) >= ps.MARKER_CHARS, line
    check_line_numbers(log, cut.text)
