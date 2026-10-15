"""The GAIA head-to-head: the official grade, the set's loader, the deny hook, the session reader
and the runner's plan, arms and rows. No network, no session, no money."""

import importlib.util
import json
import pathlib
import re
import sys
import types
import warnings

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = _load("h2h_gaia_runner", "benchmarks/h2h/h2h_gaia.py")
scorer = runner.scorer
data = runner.data
reading = runner.reading
hook = runner.deny_hook
arms = runner.arms
OFFICIAL = data.CACHE / "official" / "scorer.py"


# --- the official grade -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "gold", "ok"),
    [
        ("17", "17", True),
        ("17.0", "17", True),
        ("$1,234", "1234", True),  # $, % and , are dropped from a numeric answer
        ("45%", "45", True),
        ("5 km", "5", False),  # anything else left makes it +inf
        ("five", "5", False),
        (" 3 ", "3", True),  # float() takes surrounding whitespace
        ("0.1", "0.10", True),
        (None, "3", False),
        ("Sea Gull", "seagull", True),  # whitespace removed in strings
        ("St. Petersburg", "St Petersburg", True),  # punctuation removed in strings
        ("Saint Petersburg", "St Petersburg", False),
        ("a, b, c", "a, b, c", True),
        ("a,b,c", "a; b; c", True),  # either separator on either side
        ("a, b", "a, b, c", False),  # lengths differ
        ("b, a, c", "a, b, c", False),  # order counts
        ("1, 2.0, x", "1, 2, x", True),  # a list element compared as a number when gold's is one
        ("Mr. X, y", "Mr X, y", False),  # punctuation KEPT inside list elements
        ("$5, a", "5, a", True),
        (None, "None", True),  # a missing answer is the string "None"
    ],
)
def test_question_scorer_follows_the_leaderboard_rule(answer, gold, ok):
    assert scorer.question_scorer(answer, gold) is ok


def test_number_normaliser_returns_inf_on_text():
    assert scorer.normalize_number_str("12 apples") == float("inf")
    assert scorer.normalize_number_str("1,000") == 1000.0


def test_normalize_str_keeps_or_drops_punctuation():
    assert scorer.normalize_str(" A.B c ") == "abc"
    assert scorer.normalize_str(" A.B c ", remove_punct=False) == "a.bc"


@pytest.mark.skipif(not OFFICIAL.exists(), reason="official scorer not in the local cache")
def test_same_verdicts_as_the_official_scorer(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "numpy", types.ModuleType("numpy"))  # imported, never used
    official = _load("gaia_official_scorer", OFFICIAL)
    cases = [
        ("17", "17"), ("$1,234", "1234"), ("5 km", "5"), ("Sea Gull", "seagull"),
        ("a,b,c", "a; b; c"), ("a, b", "a, b, c"), ("1, 2.0, x", "1, 2, x"),
        ("Mr. X, y", "Mr X, y"), ("St. Petersburg", "St Petersburg"), (None, "3"),
        ("inf", "5"), ("1e3", "1000"), ("nan", "nan"), ("", ""), ("x;", "x;"),
    ]  # fmt: skip
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the official one warns on lists of different lengths
        for answer, gold in cases:
            assert scorer.question_scorer(answer, gold) == official.question_scorer(answer, gold)
    capsys.readouterr()  # and prints on every call


@pytest.mark.parametrize(
    ("reply", "want"),
    [
        ("Thinking...\nFINAL ANSWER: 42", "42"),
        ("FINAL ANSWER: 1\nmore\nFINAL ANSWER: **Paris**", "Paris"),
        ("final answer: `x, y`", "x, y"),
        ("FINAL ANSWER: [3]", "3"),
        ("no template here", None),
        ("", None),
    ],
)
def test_final_answer_is_the_last_template_line(reply, want):
    assert scorer.final_answer(reply) == want


def test_review_flags_only_plausible_misses():
    assert scorer.needs_review("42", "42") is None
    assert scorer.needs_review(None, "42") == "no FINAL ANSWER line"
    assert scorer.needs_review("The answer is Paris", "Paris") == "the gold inside the answer"
    assert scorer.needs_review("5 km", "5") == "the gold's number with other text"
    assert scorer.needs_review("b, a", "a, b") == "the same list in another order"
    assert scorer.needs_review("London", "Paris") is None


# --- the set ------------------------------------------------------------------------------------


def _row(tid, level="1", name="", question="q", tools=""):
    return {"task_id": tid, "Question": question, "Level": level, "Final answer": "a",
            "file_name": name, "file_path": f"2023/validation/{name}" if name else "",
            "Annotator Metadata": {"Tools": tools}}  # fmt: skip


@pytest.mark.parametrize(
    ("name", "kind"),
    [("", "none"), ("x.PDF", "pdf"), ("x.xlsx", "xlsx"), ("x.png", "image"), ("x.jpg", "image"),
     ("x.mp3", "audio"), ("x.docx", "docx"), ("x.py", "py"), ("x.zip", "zip"),
     ("x.weird", "weird")],
)  # fmt: skip
def test_attachment_kinds(name, kind):
    assert data.attachment_kind(name) == kind


def test_video_from_the_question_or_the_annotator_tools():
    assert data.needs_video("see https://www.youtube.com/watch?v=x")
    assert data.needs_video("In the video, how many birds")
    assert data.needs_video("q", "1. Video recognition tools")
    assert not data.needs_video("a videogame-free question", "web browser")


def test_load_select_and_summary_print_no_text(tmp_path):
    root = tmp_path / "hf"
    (root / "2023/validation").mkdir(parents=True)
    (root / "2023/validation/b.xlsx").write_bytes(b"x")
    rows = [_row("a", "1"), _row("b", "2", "b.xlsx"), _row("c", "3", question="youtube.com/x")]
    tasks = [data.row_to_task(r, root) for r in rows]
    path = tmp_path / "tasks.jsonl"
    path.write_text("".join(json.dumps(t.__dict__) + "\n" for t in tasks), encoding="utf-8")
    loaded = data.load(path)
    assert [t.task_id for t in loaded] == ["a", "b", "c"]
    assert pathlib.Path(loaded[1].file_path).exists()
    out = data.summary(loaded)
    assert out["by_level"] == {1: 1, 2: 1, 3: 1}
    assert out["by_attachment"] == {"none": 2, "xlsx": 1}
    assert out["video_ids"] == ["c"] and out["attachments_missing"] == []
    assert "youtube" not in json.dumps(out)  # ids and counts only
    assert [t.task_id for t in data.select(loaded, levels=[1, 3], no_video=True)] == ["a"]
    assert [t.task_id for t in data.select(loaded, ids=["b"])] == ["b"]


def test_load_without_the_cache_says_how_to_fetch(tmp_path):
    with pytest.raises(FileNotFoundError, match="--fetch"):
        data.load(tmp_path / "missing.jsonl")


# --- the deny hook ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool_input", "deny"),
    [
        ({"url": "https://huggingface.co/datasets/x"}, True),
        ({"command": "curl -s https://datasets-server.huggingface.co/rows"}, True),
        ({"command": "python -c \"import requests; requests.get('https://hf.co/x')\""}, True),
        ({"url": "https://raw.githubusercontent.com/a/b/main/c.json"}, True),
        ({"url": "https://github.com/a/b/raw/main/c.json"}, True),
        ({"url": "https://www.kaggle.com/datasets/x"}, True),
        ({"url": "https://github.com/numpy/numpy/issues"}, False),
        ({"url": "https://en.wikipedia.org/wiki/Hugging_Face"}, False),
        ({"command": "ls -la"}, False),
    ],
)
def test_deny_hook_reads_the_whole_input(tool_input, deny):
    assert hook.denied(tool_input) is deny


def test_deny_hook_output_and_log(tmp_path, monkeypatch, capsys):
    log = tmp_path / "denied.jsonl"
    monkeypatch.setenv("H2H_DENY_LOG", str(log))
    event = {"tool_name": "Bash", "tool_input": {"command": "curl https://huggingface.co"}}
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(read=lambda: json.dumps(event)))
    assert hook.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "GAIA" not in json.dumps(out)
    assert json.loads(log.read_text())["tool"] == "Bash"
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(read=lambda: "{}"))
    assert hook.main() == 0 and capsys.readouterr().out == ""


def test_web_search_is_let_through_with_the_sets_hosts_blocked(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("H2H_DENY_LOG", str(tmp_path / "denied.jsonl"))
    event = {"tool_name": "WebSearch", "tool_input": {"query": "q", "blocked_domains": ["a.com"]}}
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(read=lambda: json.dumps(event)))
    assert hook.main() == 0
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["permissionDecision"] == "allow" and out["updatedInput"]["query"] == "q"
    assert out["updatedInput"]["blocked_domains"] == ["a.com", *hook.SEARCH_BLOCKED]
    assert not (tmp_path / "denied.jsonl").exists()  # a rewrite is not a denial
    assert hook.search_input({"query": "q", "allowed_domains": ["b.org"]}) is None
    assert set(hook.SEARCH_BLOCKED) <= {h.removeprefix("www.") for h in hook.DENIED_HOSTS}


# --- reading a session --------------------------------------------------------------------------

# Claude Code 2.1.287's modelUsage from a real one-turn Haiku session (2026-10-05).
HAIKU_USAGE = {"claude-haiku-4-5-20251001": {
    "inputTokens": 10, "outputTokens": 39, "cacheReadInputTokens": 0,
    "cacheCreationInputTokens": 6796, "webSearchRequests": 0, "costUSD": 0.013797,
    "canonicalModel": "claude-haiku-4-5", "costBasis": "list"}}  # fmt: skip


def test_our_price_matches_claude_codes_on_a_real_session():
    out = reading.usage_summary(HAIKU_USAGE)
    assert out["list_usd_ours"] == pytest.approx(0.013797, abs=1e-9)
    assert out["tokens"] == {"input": 10, "cache_read": 0, "cache_write": 6796, "output": 39,
                             "web_searches": 0}  # fmt: skip
    assert out["unpriced_models"] == []


def test_every_benchmark_model_has_a_price_and_unknown_ones_are_named():
    for model in runner.MODELS.values():
        assert reading.price_key(model) is not None
    out = reading.usage_summary({"claude-new-9": {"inputTokens": 5, "costUSD": 0.1}})
    assert out["unpriced_models"] == ["claude-new-9"]
    assert reading.our_usd("claude-sonnet-5-5", {"webSearchRequests": 3}) == pytest.approx(0.03)


def _transcript(folder, task_id="t-1", leak_text="nothing here"):
    folder.mkdir(parents=True, exist_ok=True)
    entries = [
        {"type": "assistant", "version": "2.1.287", "message": {"content": [
            {"type": "tool_use", "id": "u1", "name": "WebSearch", "input": {}},
            {"type": "tool_use", "id": "u2", "name": "Bash", "input": {}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "u1", "content": [{"type": "text",
                                                                       "text": leak_text}]},
            {"type": "tool_result", "tool_use_id": "u2", "content": "ok"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text",
                                                        "text": "FINAL ANSWER: 7"}]}},
        {"type": "assistant", "isSidechain": True,
         "message": {"content": [{"type": "text", "text": "FINAL ANSWER: 9"}]}},
    ]  # fmt: skip
    (folder / "s.jsonl").write_text("".join(json.dumps(e) + "\n" for e in entries), "utf-8")


def test_transcript_reading(tmp_path):
    folder = tmp_path / "p"
    _transcript(folder)
    assert reading.tool_calls(folder) == {"WebSearch": 1, "Bash": 1}
    assert reading.leaks(folder, "t-1") == []
    assert reading.last_assistant_texts(folder) == ["FINAL ANSWER: 7"]
    assert reading.version_of(folder) == "2.1.287"


@pytest.mark.parametrize("text", ["the GAIA benchmark", "id t-1 found"])
def test_leak_names_the_tool(tmp_path, text):
    folder = tmp_path / "p"
    _transcript(folder, leak_text=text)
    assert reading.leaks(folder, "t-1") == ["WebSearch"]


def test_gaia_spacecraft_is_not_a_leak(tmp_path):
    folder = tmp_path / "p"
    _transcript(folder, leak_text="the Gaia spacecraft")
    assert reading.leaks(folder, "t-1") == []


def test_denials_from_claude_code_and_the_hook(tmp_path):
    log = tmp_path / "d.jsonl"
    log.write_text('{"tool": "Bash"}\n', encoding="utf-8")
    out = reading.denials({"permission_denials": [{"tool_name": "WebFetch"}]}, log)
    assert out == {"denied": 1, "denied_tools": ["WebFetch"], "hook_denied": ["Bash"]}


# --- the runner ---------------------------------------------------------------------------------


def _task(tid="t-1", level=1, gold="7", name="", path=""):
    return data.Task(task_id=tid, level=level, question="How many?", gold=gold,
                     file_name=name, file_path=path, tools="")  # fmt: skip


def test_arms_and_models():
    assert runner.split_arm("SONNET-CC") == ("SONNET", "CC")
    with pytest.raises(ValueError):
        runner.split_arm("GPT-CC")
    assert set(runner.MODELS.values()) == {
        "claude-fable-5-1",
        "claude-opus-5-5",
        "claude-sonnet-5-5",
        "claude-haiku-4-5-20251001",
    }
    assert set(runner.CAPS) == set(runner.MODELS)


def test_cc_settings_deny_the_sources_and_wire_the_hook():
    both = runner.settings_for("CC")
    assert both["user"] == {}
    s = both["flag"]
    assert "Bash" in s["permissions"]["allow"]
    assert "WebFetch(domain:huggingface.co)" in s["permissions"]["deny"]
    assert "WebFetch(domain:raw.githubusercontent.com)" in s["permissions"]["deny"]
    command = s["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "deny_hook.py" in command


def test_sp_arm_is_the_install_line_on_the_same_flag_settings():
    cc, sp = runner.settings_for("CC"), runner.settings_for("SP")
    assert sp["flag"] == cc["flag"] and cc["user"] == {}
    line = arms.s_line.load()
    assert sp["user"] == {"install_flags": list(line.flags), "env": line.env_map}
    other = arms.s_line.parse({"flags": ["--candor", "--memory"],
                               "env": {"SANCHOPANZA_X": "1"}})  # fmt: skip
    assert runner.settings_for("SP", line=other)["user"] == {
        "install_flags": ["--candor", "--memory"],
        "env": {"SANCHOPANZA_X": "1"},
    }
    base = {"permissions": {"allow": ["Read"]}}
    assert runner.settings_for("CC", base)["flag"] == base
    with pytest.raises(ValueError):
        runner.settings_for("XX")


def _guard_unsplit(settings):
    """The settings with the guard's split hooks (guard-split, main cb0062e, merged after GAIA
    dev ran) folded back into the one `sanchopanza guard-hook` they replaced."""
    hooks = {}
    for event, entries in settings["hooks"].items():
        folded = []
        for entry in entries:
            seen, kept = False, []
            for hook in entry["hooks"]:
                command = re.sub(r" --part \d+| --parts \d+", "", hook["command"])
                if command == "sanchopanza guard-hook" and seen:
                    continue
                seen = seen or command == "sanchopanza guard-hook"
                kept.append({**hook, "command": command})
            folded.append({**entry, "hooks": kept})
        hooks[event] = folded
    return {**settings, "hooks": hooks}


def _without_memory(settings):
    """`settings` without memory's hooks, which the install wires by default since 2026-10-14
    (the memory cell, docs/results/2026-10-13-memory-cell) and GAIA dev ran without; entries
    and events left empty are dropped."""
    hooks = {}
    for event, entries in settings["hooks"].items():
        kept = [{**e, "hooks": [h for h in e["hooks"]
                                if h["command"] != "sanchopanza memory-hook"]}
                for e in entries]  # fmt: skip
        kept = [e for e in kept if e["hooks"]]
        if kept:
            hooks[event] = kept
    return {**settings, "hooks": hooks}


def test_the_real_default_install_writes_exactly_the_dev_phase_settings(tmp_path):
    src = ROOT / "src"
    installed = arms.prepare_config("SP", tmp_path / "config", src)  # a real install, free
    written = json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8"))
    arms.prepare_config("SP", tmp_path / "off", src, ("--no-memory",))
    off = json.loads((tmp_path / "off" / "settings.json").read_text(encoding="utf-8"))
    # The record of what GAIA dev ran with; today's install differs from it by the split guard
    # and by memory (on by default since 2026-10-14), and by nothing else.
    assert _guard_unsplit(off) == arms.SP_USER_SETTINGS
    assert _without_memory(written) == _without_memory(off) != written
    assert (tmp_path / "config" / arms.SKILL).is_file()
    assert installed.raw_mcp == {} and "sanchopanza" in installed.hinted  # a hint, not registered
    assert arms.prepare_config("CC", tmp_path / "empty", None) is None
    assert list((tmp_path / "empty").iterdir()) == []
    with pytest.raises(ValueError):
        arms.prepare_config("SP", tmp_path / "x", None)


def test_a_drifted_install_stops_the_phase(tmp_path):
    src = ROOT / "src"
    installed = arms.prepare_config("SP", tmp_path / "a", src)
    arms.check_sp(installed, installed.digest)
    with pytest.raises(RuntimeError):
        arms.check_sp(installed, "0" * 16)
    with pytest.raises(RuntimeError):
        arms.prepare_config("SP", tmp_path / "b", src, ["--candor"], installed.digest)


def test_env_cc_is_a_clean_user_and_sp_adds_jev_and_the_shim(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    monkeypatch.setenv("TYPESAFE_API_KEY", "key")
    base = {"ANTHROPIC_API_KEY": "x", "TYPESAFE_API_KEY": "y", "PYTHONPATH": "z",
            "CLAUDE_CONFIG_DIR": "mine", "CLAUDECODE": "1", "CLAUDE_EFFORT": "max",
            "SANCHOPANZA_PROVIDER": "jev", "PATH": "p"}  # fmt: skip
    cc = arms.session_env("CC", tmp_path / "c", tmp_path / "s", None, base)
    assert not {"ANTHROPIC_API_KEY", "TYPESAFE_API_KEY", "PYTHONPATH", "CLAUDECODE",
                "CLAUDE_EFFORT", "SANCHOPANZA_PROVIDER"} & set(cc)  # fmt: skip
    assert cc["CLAUDE_CONFIG_DIR"] == str(tmp_path / "c") and cc["CLAUDE_CODE_OAUTH_TOKEN"] == "tok"
    assert cc["H2H_DENY_LOG"].endswith("denied.jsonl") and cc["PATH"] == "p"
    sp = arms.session_env("SP", tmp_path / "c", tmp_path / "s", tmp_path / "bin", base)
    assert sp["TYPESAFE_API_KEY"] == "key" and sp["PATH"].startswith(str(tmp_path / "bin"))
    assert sp["SANCHOPANZA_JOURNAL"].endswith("journal.jsonl")
    assert set(sp) - set(cc) == {"TYPESAFE_API_KEY", "SANCHOPANZA_JOURNAL", "H2H_SP_HOME",
                                 "SANCHOPANZA_GUARD_LOG", "H2H_SHIM_LOG"}  # fmt: skip
    assert sp["H2H_SP_HOME"] == str(tmp_path / "s" / "home")
    lined = arms.session_env("SP", tmp_path / "c", tmp_path / "s", tmp_path / "bin", base,
                             {"SANCHOPANZA_MEMORY_KEEP": "0.8"})  # fmt: skip
    assert lined["SANCHOPANZA_MEMORY_KEEP"] == "0.8" and "SANCHOPANZA_MEMORY_KEEP" not in cc
    assert arms.secrets_of(sp) == ("tok", "key") or set(arms.secrets_of(sp)) == {"tok", "key"}
    with pytest.raises(ValueError):
        arms.session_env("SP", tmp_path, tmp_path, None, base)


def test_secret_comes_from_the_env_file_and_is_never_shown(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text('OTHER=1\nCLAUDE_CODE_OAUTH_TOKEN="abc"\n', encoding="utf-8")
    assert arms.secret("CLAUDE_CODE_OAUTH_TOKEN", env_file) == "abc"
    with pytest.raises(SystemExit) as stop:
        arms.secret("CLAUDE_CODE_OAUTH_TOKEN", tmp_path / "none")
    assert "abc" not in str(stop.value)


def test_scrub_takes_both_secrets_out_of_every_file(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "t.jsonl").write_text("x tok y key", encoding="utf-8")
    (tmp_path / "b.txt").write_text("nothing", encoding="utf-8")
    assert arms.scrub(tmp_path, ("tok", "key")) == 1
    assert (tmp_path / "a" / "t.jsonl").read_text(encoding="utf-8") == "x <redacted> y <redacted>"


def test_unclean_runs_are_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    (tmp_path / ".claude" / "rules" / "r.md").write_text("rule", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("memory", encoding="utf-8")
    found = arms.ancestors_memory(tmp_path / "runs" / "x")
    assert str(tmp_path / "CLAUDE.md") in found and str(tmp_path / ".claude" / "rules") in found
    with pytest.raises(SystemExit):
        arms.refuse_unclean(tmp_path / "runs")
    assert arms.ancestors_memory(runner.RUNS) == []  # the real run folder: nothing above it


def test_the_shim_runs_the_frozen_src(tmp_path):
    folder = arms.write_shim(tmp_path, "C:/py/python.exe")
    sh = (folder / "sanchopanza").read_text(encoding="utf-8")
    assert sh.startswith("#!/bin/sh\n") and (tmp_path / "src").resolve().as_posix() in sh
    assert '-m sanchopanza "$@"' in sh and "\r" not in sh
    assert 'export HOME="$H2H_SP_HOME" USERPROFILE="$H2H_SP_HOME"' in sh
    cmd = (folder / "sanchopanza.cmd").read_text(encoding="utf-8")
    assert "%*" in cmd and 'set "USERPROFILE=%H2H_SP_HOME%"' in cmd


def test_prompt_is_the_question_the_file_and_gaias_format(tmp_path):
    attached = tmp_path / runner.neutral_name("abc-123.xlsx")
    assert attached.name == "attachment.xlsx"
    text = runner.prompt(_task(), attached)
    assert text.startswith("How many?") and str(attached) in text
    assert text.endswith(runner.FORMAT) and "FINAL ANSWER: [YOUR FINAL ANSWER]" in text
    assert str(tmp_path) not in runner.prompt(_task(), None)
    assert runner.neutral_name("noext") == "attachment"


def test_argv_carries_the_cap_and_no_user_settings(tmp_path):
    argv = runner.argv_for("HAIKU", tmp_path / "s.json", tmp_path / "m.json", 0.75, "q")
    assert argv[argv.index("--model") + 1] == "claude-haiku-4-5-20251001"
    assert argv[argv.index("--max-budget-usd") + 1] == "0.75"
    assert argv[argv.index("--setting-sources") + 1] == "user"  # the user folder is clean
    assert "--strict-mcp-config" in argv and argv[-2:] == ["--", "q"]
    assert argv[argv.index("--permission-mode") + 1] == arms.PERMISSION_MODE == "default"
    assert "Bash" not in argv[argv.index("--disallowedTools") + 1]


def test_plan_interleaves_arms_within_each_task():
    steps = runner.planned([_task("a"), _task("b")], ["SONNET", "OPUS"], ["CC", "SP"])
    assert [(s[1][0], s[3]) for s in steps[:4]] == [
        ("a", "SONNET-CC"),
        ("a", "SONNET-SP"),
        ("a", "OPUS-CC"),
        ("a", "OPUS-SP"),
    ]
    assert {s[0] for s in steps[4:]} == {1}


def test_ceiling_is_bounded_in_code():
    assert runner.ceiling(10) == 10
    assert runner.ceiling(25, "dev") == 25
    with pytest.raises(SystemExit):
        runner.ceiling(25.01, "dev")
    with pytest.raises(SystemExit):
        runner.ceiling(runner.MAX_CEILING_USD + 1)
    with pytest.raises(SystemExit):
        runner.ceiling(0)


def test_model_ids_in_a_binary(tmp_path):
    binary = tmp_path / "claude.exe"
    binary.write_bytes(b'xx"claude-opus-5-5"yy')
    assert runner.model_ids_in(binary, ["claude-opus-5-5", "claude-x"]) == {
        "claude-opus-5-5": True,
        "claude-x": False,
    }


@pytest.mark.parametrize(
    ("reply", "stderr", "is_error", "want"),
    [
        ("You've hit your weekly limit", "", True, True),
        ("", "API Error: 429 Too Many Requests", True, True),
        ("FINAL ANSWER: 429", "", False, False),  # a right answer may be the number
        ("fine", "", False, False),
    ],
)
def test_limit_detection(reply, stderr, is_error, want):
    assert runner.limited(reply, stderr, is_error) is want


def _out(result="FINAL ANSWER: 7", usd=0.2, subtype="success", is_error=False):
    return {"result": result, "total_cost_usd": usd, "subtype": subtype, "is_error": is_error,
            "num_turns": 5, "modelUsage": HAIKU_USAGE,
            "permission_denials": [{"tool_name": "WebFetch"}]}  # fmt: skip


def test_build_row_grades_and_records(tmp_path, monkeypatch):
    monkeypatch.setattr(reading, "PROJECTS", tmp_path / "projects")
    work, side = tmp_path / "w", tmp_path / "s"
    side.mkdir()
    _transcript(reading.folder_of(work))
    row = runner.build_row(_task(), 1, "HAIKU-CC", _out(), "", work, side, 12.34)
    assert row["final_answer"] == "7" and row["ok_oficial"] and row["success"]
    assert row["model"] == "claude-haiku-4-5-20251001" and row["brazo"] == "CC"
    assert row["tokens"]["cache_write"] == 6796 and row["turns"] == 5
    assert row["tools"] == {"WebSearch": 1, "Bash": 1} and row["denied"] == 1
    assert not row["hit_cap"] and not row["leak"] and row["answer"] == ""
    assert row["wall_s"] == 12.3 and row["version"] == "2.1.287"


def test_build_row_falls_back_to_the_transcript_and_flags_the_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(reading, "PROJECTS", tmp_path / "projects")
    work, side = tmp_path / "w", tmp_path / "s"
    side.mkdir()
    _transcript(reading.folder_of(work))
    out = _out(result="", usd=0.75, subtype="error_max_budget_usd", is_error=True)
    row = runner.build_row(_task(gold="8"), 1, "HAIKU-CC", out, "", work, side, 1.0)
    assert row["final_answer"] == "7" and not row["ok_oficial"] and row["hit_cap"]


def test_a_limited_session_stops_the_phase_and_is_not_run(tmp_path, monkeypatch):
    calls = []

    def fake(task, run, arm, ctx):
        calls.append(arm)
        limit = "usage limit: hit your limit" if len(calls) == 2 else ""
        return {"task": task.task_id, "run": run, "arm": arm, "list_usd": 0.1, "answer": limit}

    monkeypatch.setattr(runner, "one_session", fake)
    sessions = tmp_path / "s.jsonl"
    steps = runner.planned([_task("a"), _task("b")], ["HAIKU"], ["CC"])
    limits = runner.phase.Limits(session_max_usd=0.75, ceiling_usd=10)
    code, rows = runner.phase.run_phase(
        steps, [], limits, runner.session_for(sessions, {"phase": "t"}), sessions
    )
    assert code == 2 and rows[-1]["not_run"] and len(calls) == 2
    assert "STOP-LIMIT" in sessions.with_suffix(".log").read_text(encoding="utf-8")
    code, _ = runner.phase.run_phase(
        steps, rows, limits, runner.session_for(sessions, {"phase": "t"}), sessions
    )
    assert len(calls) == 3  # resumed: only the refused session ran again


def test_the_ceiling_stops_before_a_session_could_cross_it(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "one_session", lambda t, r, a, c: {
        "task": t.task_id, "run": r, "arm": a, "list_usd": 0.5, "answer": ""})  # fmt: skip
    sessions = tmp_path / "s.jsonl"
    steps = runner.planned([_task(str(i)) for i in range(5)], ["HAIKU"], ["CC"])
    limits = runner.phase.Limits(session_max_usd=0.75, ceiling_usd=2.0)
    code, rows = runner.phase.run_phase(
        steps, [], limits, runner.session_for(sessions, {"phase": "t"}), sessions
    )
    assert code == 1 and len(rows) == 3  # 1.0 spent + 0.75 reserved fits; 1.5 + 0.75 does not


def _graded(task, arm, ok, review=None, level=1):
    return {"task": task, "arm": arm, "run": 1, "level": level, "ok_oficial": ok,
            "model_key": arm.split("-")[0],
            "review": review, "list_usd": 0.2, "wall_s": 10.0, "hit_cap": False, "leak": False,
            "final_answer": "x", "denied": 0, "hook_denied": []}  # fmt: skip


def test_review_and_report_keep_the_official_grade_beside_the_hand_one():
    rows = [_graded("a", "HAIKU-CC", True), _graded("b", "HAIKU-CC", False, "the gold inside",
                                                   level=2)]  # fmt: skip
    assert runner.to_review(rows, {}) == [
        {"task": "b", "arm": "HAIKU-CC", "run": 1, "why": "the gold inside"}
    ]
    hand = {("b", "HAIKU-CC", 1): True}
    assert runner.to_review(rows, hand) == []
    cell = runner.report(rows, hand)["by_arm"]["HAIKU-CC"]
    assert cell["ok_oficial"] == 1 and cell["ok_with_hand"] == 2
    assert cell["by_level"] == {"1": "1/1", "2": "0/1"}
    assert "x" not in json.dumps(runner.report(rows, hand))  # no answer text in the report


def test_plan_mode_is_free(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(runner, "PRIVATE", tmp_path)
    monkeypatch.setattr(runner.data, "load", lambda: [_task("a"), _task("b", level=2)])
    assert runner.main(["--plan", "--models", "HAIKU", "--levels", "2"]) == 0
    out = capsys.readouterr().out
    assert "b HAIKU-CC" in out and "b HAIKU-SP" in out and "2 sessions" in out
    ids = tmp_path / "ids.txt"
    ids.write_text("# c\nb\na\n", encoding="utf-8")
    assert runner.main(["--plan", "--models", "HAIKU", "--brazos", "CC", "--ids", str(ids)]) == 0
    assert [x.split()[1] for x in capsys.readouterr().out.splitlines()[:2]] == ["b", "a"]
    assert runner.main(["--plan", "--models", "HAIKU", "--brazos", "CC", "--exclude",
                        str(ids)]) == 0  # fmt: skip
    assert "0 sessions" in capsys.readouterr().out


def test_dev_draw_is_seeded_and_leaves_video_out():
    tasks = [_task(f"t{i:03d}") for i in range(40)]
    video = data.Task(task_id="v", level=1, question="see https://youtu.be/x", gold="1",
                      file_name="", file_path="", tools="")  # fmt: skip
    ids = runner.draw([*tasks, video], 20, 7)
    assert len(ids) == len(set(ids)) == 20 and "v" not in ids
    assert ids == runner.draw(list(reversed([*tasks, video])), 20, 7)


def test_dev_ids_file_holds_twenty_non_video_tasks():
    ids = runner.read_ids(runner.DEV_IDS)
    assert len(ids) == len(set(ids)) == runner.DEV_SIZE


def test_hook_runs_and_journal(tmp_path):
    folder = tmp_path / "p"
    folder.mkdir()
    lines = [{"type": "attachment", "attachment": {"type": "hook_success", "hookName":
              "PreToolUse:Bash", "command": "sanchopanza hook"}},
             {"type": "attachment", "attachment": {"type": "hook_success", "hookName":
              "PreToolUse:Bash", "command": '"sanchopanza/py" "deny_hook.py"'}},
             {"type": "attachment", "attachment": {"type": "file"}}]  # fmt: skip
    (folder / "s.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    shim = tmp_path / "shim.log"
    shim.write_text("hook\nguard-hook\nhook\n", encoding="utf-8")
    assert reading.shim_runs(shim) == {"hook": 2, "guard-hook": 1}
    assert reading.shim_runs(tmp_path / "none") == {}
    assert reading.hook_runs(folder) == {"PreToolUse:Bash sanchopanza": 1,
                                         "PreToolUse:Bash deny": 1}  # fmt: skip
    journal = tmp_path / "j.jsonl"
    events = [{"kind": "decision", "data": {"point": "guard", "provider": "jev",
                                            "cost_usd": 0.0001, "error": None}},
              {"kind": "decision", "data": {"point": "search", "provider": "jev",
                                            "cost_usd": 0.0002, "error": "timeout"}},
              {"kind": "note", "data": {}}]  # fmt: skip
    journal.write_text("\n".join(json.dumps(x) for x in events) + "\nbad", encoding="utf-8")
    got = reading.journal(journal)
    assert got["jev_calls"] == 2 and got["jev_usd"] == 0.0003 and got["jev_errors"] == 1
    assert got["jev_by_point"] == {"guard": 1, "search": 1}
    assert reading.journal(tmp_path / "none")["jev_calls"] == 0


def test_paired_stats_mcnemar_and_cost_bootstrap():
    rows = []
    for i in range(10):
        for arm, ok, usd in (("SONNET-SP", i < 6, 0.2), ("SONNET-CC", i < 4, 0.3)):
            rows.append({**_graded(f"t{i}", arm, ok), "list_usd": usd, "jev_usd": 0.001})
    out = runner.report(rows, {})
    pair = out["paired"]["SONNET"]
    assert pair["tasks"] == 10 and pair["oficial"]["a_only"] == 2 and pair["oficial"]["b_only"] == 0
    assert pair["oficial"]["a_only_tasks"] == ["t4", "t5"] and pair["oficial"]["p"] == 0.5
    assert pair["cost"]["mean_diff"] == -0.1 and pair["cost"]["diff_ci95"] == [-0.1, -0.1]
    assert out["by_arm"]["SONNET-SP"]["jev_usd"] == 0.01
    assert runner.stats.mcnemar([True] * 7, [False] * 7)[2] == pytest.approx(2 / 128)
    assert runner.stats.paired(rows, {}, "X-SP", "X-CC") == {"tasks": 0}


def test_isolation_permission_mode_and_a_user_folder_per_session(tmp_path):
    argv = runner.argv_for("SONNET", tmp_path / "s", tmp_path / "m", 1.0, "q")
    for brazo in ("CC", "SP"):
        flag = runner.settings_for(brazo)["flag"]
        assert flag["permissions"]["defaultMode"] == "default"
        assert runner.isolation_problems(flag, argv) == []
    assert runner.isolation_problems({"permissions": {}}, argv[:3]) == [
        "settings defaultMode is None, not 'default'",
        "the claude command line does not set --permission-mode",
    ]


def test_a_session_starts_from_a_new_user_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    seen = []

    def fake(argv, work, side, env):
        config = pathlib.Path(env["CLAUDE_CONFIG_DIR"])
        seen.append(sorted(p.name for p in config.iterdir()))
        (config / "projects").mkdir()  # what a session leaves: native memory, transcripts
        return {"result": "FINAL ANSWER: 7", "total_cost_usd": 0.1, "is_error": False}, ""

    monkeypatch.setattr(runner, "run_claude", fake)
    root = tmp_path / "root"
    row = lambda *a: {"task": "t", "run": 1, "arm": "HAIKU-CC", "list_usd": 0.1}  # noqa: E731
    ctx = {"phase": "t"}
    for _ in range(2):  # the same session again (a resume) starts from an empty user folder
        runner.clean_session(ctx, root, "HAIKU-CC", "q", flag_settings={}, make_row=row)
    assert seen == [[], []]


def test_session_folders_name_neither_the_task_nor_the_arm():
    root = runner.session_root("dev", "abc-123", "SONNET-SP", 1)
    assert "abc-123" not in str(root) and "SP" not in root.name and "SONNET" not in str(root)
    assert root == runner.session_root("dev", "abc-123", "SONNET-SP", 1)
    assert root != runner.session_root("dev", "abc-123", "SONNET-CC", 1)
    assert root.parent == runner.RUNS / "dev"


def _main_transcript(folder, entries):
    folder.mkdir(parents=True)
    (folder / "s.jsonl").write_text("".join(json.dumps(e) + "\n" for e in entries), "utf-8")


def _turn(mid, out=100):
    return {"type": "assistant", "message": {"id": mid, "model": "claude-sonnet-5-5",
            "usage": {"input_tokens": 0, "cache_read_input_tokens": 1000,
                      "cache_creation_input_tokens": 0, "output_tokens": out}}}  # fmt: skip


def test_components_count_outputs_by_owner_and_the_turns_a_return_cost(tmp_path):
    stop = {
        "type": "attachment",
        "attachment": {
            "type": "hook_blocking_error",
            "hookEvent": "Stop",
            "blockingError": "sanchopanza: the transcript does not show this request done (p=0.3)",
        },
    }
    entries = [
        {"type": "attachment", "attachment": {"type": "hook_additional_context",
         "content": "When you finish, end your final reply with exactly these four lines"}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True,
         "content": "PreToolUse:WebSearch hook error: Use mcp__sanchopanza-knowledge__search"}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True,
         "content": "PreToolUse:Bash hook error: This environment is offline"}]}},
        {"type": "attachment", "attachment": {"type": "hook_success", "stdout": "{}",
                                              "command": "sanchopanza/find_auto"}},
        _turn("m1"), _turn("m1"), stop, _turn("m2", 1000), _turn("m2", 1000), _turn("m3"),
        {**_turn("sub"), "isSidechain": True},
    ]  # fmt: skip
    _main_transcript(tmp_path / "t", entries)
    got = reading.components(tmp_path / "t")
    assert got["outputs"] == {"candor": 1, "knowledge": 1, "check-done": 1}
    assert got["returns"] == {"check-done": 1}
    assert got["turns_after"] == {"check-done": 2}  # one per message id, subagents left out
    assert got["usd_after"]["check-done"] == pytest.approx((0.2 * 2000 + 10 * 1100) / 1e6)


def _verdict_input(diff_ci, ratio_ci, p, a_only, b_only, b_ok, tasks):
    return {
        "tasks": tasks,
        "with_hand": {"a_ok": b_ok + a_only - b_only, "b_ok": b_ok, "a_only": a_only,
                      "b_only": b_only, "p": p, "diff_points_ci95": diff_ci},
        "cost": {"ratio_ci95": ratio_ci},
    }


def test_bootstrap_success_gives_points_with_a_paired_interval():
    a = [True] * 3 + [False] * 2 + [True] * 2 + [False] * 3  # 3 only a, 2 only b
    b = [False] * 3 + [True] * 2 + [True] * 2 + [False] * 3
    out = runner.stats.bootstrap_success(a, b)
    assert out["diff_points"] == 10.0
    lo, hi = out["diff_points_ci95"]
    assert lo <= 10.0 <= hi and lo < 0 < hi


def test_paired_carries_the_success_interval():
    rows = [{"task": f"t{i}", "arm": arm, "run": 1, "ok_oficial": ok, "list_usd": 0.1,
             "wall_s": 10.0} for i in range(4) for arm, ok in (("X-SP", True), ("X-CC", i < 2))]
    out = runner.stats.paired(rows, {}, "X-SP", "X-CC")
    assert out["with_hand"]["diff_points_ci95"][1] >= 50.0


def test_verdict_cost_win_needs_cheaper_and_non_inferior():
    v = runner.stats.verdict
    assert v(_verdict_input([-1.5, 3.0], [0.70, 0.95], 1.0, 2, 2, 60, 100)) == "gana (coste)"
    # cheaper but the success interval reaches below -2 points: not a win
    assert v(_verdict_input([-6.0, 3.0], [0.70, 0.95], 1.0, 2, 4, 60, 100)) == "no gana"
    # same success, cost interval crosses 1
    assert v(_verdict_input([-1.0, 1.0], [0.90, 1.10], 1.0, 1, 1, 60, 100)) == "no gana"


def test_verdict_success_win_needs_mcnemar_and_no_cost_loss():
    v = runner.stats.verdict
    assert v(_verdict_input([2.0, 12.0], [0.95, 1.20], 0.01, 9, 1, 60, 100)) == "gana (éxito)"
    # more right but significantly dearer: no win
    assert v(_verdict_input([2.0, 12.0], [1.10, 1.60], 0.01, 9, 1, 60, 100)) == "no gana"
    # N more right with p < 0.05 is not a win for S
    assert v(_verdict_input([-12.0, -2.0], [0.50, 0.80], 0.01, 1, 9, 60, 100)) == "no gana"


def test_verdict_without_headroom():
    """N wrong on fewer than 5 % of the tasks: there is nothing for S to win on success."""
    assert runner.stats.verdict(_verdict_input([-1.0, 1.0], [0.6, 0.8], 1.0, 0, 0, 97, 100)) == (
        "sin margen")


def test_blind_sheet_hides_the_arm_and_keeps_the_key_apart(tmp_path):
    items = [{"task": f"t{i}", "arm": arm, "run": 1, "answer": f"a{i}{arm}"}
             for i in range(5) for arm in ("SONNET-SP", "SONNET-CC")]
    sheet, key = tmp_path / "sheet.jsonl", tmp_path / "key.jsonl"
    assert runner.stats.blind_sheet(items, sheet, key) == 10
    text = sheet.read_text(encoding="utf-8")
    lines = [json.loads(x) for x in text.splitlines()]
    assert all(set(x) == {"id", "answer"} for x in lines)
    assert all("arm" not in x and "task" not in x for x in lines)
    keys = {k["id"]: k for k in map(json.loads, key.read_text(encoding="utf-8").splitlines())}
    assert len(keys) == 10 and all(x["id"] in keys for x in lines)
    # shuffled: the sheet does not follow the input order
    assert [keys[x["id"]]["task"] for x in lines] != [i["task"] for i in items]


def test_blind_verdicts_come_back_through_the_key(tmp_path):
    items = [{"task": "t1", "arm": "SONNET-SP", "run": 1, "answer": "x"},
             {"task": "t1", "arm": "SONNET-CC", "run": 1, "answer": "y"}]
    sheet, key = tmp_path / "sheet.jsonl", tmp_path / "key.jsonl"
    runner.stats.blind_sheet(items, sheet, key)
    ids = [json.loads(x)["id"] for x in sheet.read_text(encoding="utf-8").splitlines()]
    answers = tmp_path / "verdicts.jsonl"
    answers.write_text("\n".join(json.dumps({"id": i, "ok": n == 0}) for n, i in enumerate(ids)),
                       encoding="utf-8")
    got = runner.stats.blind_verdicts(answers, key)
    assert sorted((g["task"], g["arm"], g["run"]) for g in got) == [
        ("t1", "SONNET-CC", 1), ("t1", "SONNET-SP", 1)]
    assert sum(g["ok"] for g in got) == 1
    answers.write_text(json.dumps({"id": "nope", "ok": True}), encoding="utf-8")
    with pytest.raises(ValueError):
        runner.stats.blind_verdicts(answers, key)


def test_ne_arm_is_clean_n_with_only_the_compaction_window_s_writes(tmp_path, monkeypatch):
    """N-early (2026-10-07): a clean N whose user settings hold only the auto-compact window, the
    value S's install writes for its context budget, so NE and S differ by the rest of S alone
    (session 6c's Ne of the long bench)."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")  # never a file on this machine
    assert runner.split_arm("SONNET-NE") == ("SONNET", "NE")
    cc, ne = runner.settings_for("CC"), runner.settings_for("NE")
    assert ne["flag"] == cc["flag"]
    assert ne["user"] == {"env": {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": str(arms.NE_WINDOW)}}
    assert int(arms.SP_USER_SETTINGS["env"]["CLAUDE_CODE_AUTO_COMPACT_WINDOW"]) == arms.NE_WINDOW
    assert arms.prepare_config("NE", tmp_path / "config", None) is None
    written = json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8"))
    assert written == ne["user"]
    env = arms.session_env("NE", tmp_path / "config", tmp_path / "side", None,
                           base={"PATH": "x"})  # fmt: skip
    assert arms.JEV_KEY not in env and "SANCHOPANZA_JOURNAL" not in env
