"""The offline head-to-head suites and the S install line: BrowseComp-Plus (cipher, qrels,
retrieval server, grading, runner) and LongBench v2 (draw, official grade, runner), the local
hook, and `s_line` (the line, its proof flag by flag, its MCP servers). No network, no session,
no money: the sanchopanza installs are real and free, the claude sessions are fakes."""

import argparse
import importlib.util
import io
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
H2H = ROOT / "benchmarks" / "h2h"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bcp = _load("h2h_bcp_runner", "benchmarks/h2h/h2h_bcp.py")
longdoc = _load("h2h_longdoc_runner", "benchmarks/h2h/h2h_longdoc.py")
bcp_data, grade, server, common = bcp.bcp_data, bcp.bcp_grade, bcp.bcp_server, bcp.common
ld_data = longdoc.longdoc_data
gaia = common.gaia
s_line = gaia.arms.s_line
hook = gaia._load("h2h_local_hook_t", H2H / "local_hook.py")
SRC = ROOT / "src"


# --- s_line: the file -----------------------------------------------------------------------------


def test_the_line_file_parses_and_refuses_what_the_runner_owns():
    line = s_line.parse({"sealed": True, "flags": ["--memory", "--guard-profile", "sandbox"],
                         "env": {"SANCHOPANZA_MEMORY_KEEP": "0.8"}})  # fmt: skip
    assert line.sealed and line.env_map == {"SANCHOPANZA_MEMORY_KEEP": "0.8"}
    assert s_line.options(line.flags) == [("--memory",), ("--guard-profile", "sandbox")]
    assert s_line.without(line.flags, ("--memory",)) == ["--guard-profile", "sandbox"]
    assert s_line.negation(("--guard",)) == ("--no-guard",)
    assert s_line.negation(("--guard-profile", "sandbox")) is None
    for bad in ({"flags": ["--write"]}, {"flags": ["--path=x"]}, {"flags": ["memory"]},
                {"env": {"OTHER": "1"}}, {"env": {"SANCHOPANZA_JOURNAL": "x"}}):  # fmt: skip
        with pytest.raises(ValueError):
            s_line.parse(bad)


def test_the_committed_line_is_unsealed_and_paid_runs_refuse_it():
    line = s_line.load()
    assert not line.sealed  # sealed by the owner's session, not here
    with pytest.raises(SystemExit):
        s_line.require_sealed(line)
    s_line.require_sealed(line, allow_unsealed=True)
    s_line.require_sealed(s_line.parse({"sealed": True}))


def test_add_json_hints_are_parsed():
    out = (
        "find_in_repo for every project: claude mcp add-json --scope user sanchopanza "
        '\'{"command":"sanchopanza","args":["find-mcp"],"alwaysLoad":true}\'\n'
    )
    assert s_line.mcp_from_output(out) == {
        "sanchopanza": {"command": "sanchopanza", "args": ["find-mcp"], "alwaysLoad": True}
    }


def test_session_mcp_runs_the_frozen_python_with_the_sessions_home(tmp_path):
    raw = {
        "sanchopanza": {
            "command": "sanchopanza",
            "args": ["find-mcp", "--auto"],
            "alwaysLoad": True,
        },
        "other": {"command": "node", "args": ["x"]},
    }
    out = s_line.session_mcp(raw, tmp_path / "src", tmp_path / "home", "C:/py.exe")
    assert out["sanchopanza"]["command"] == "C:/py.exe"
    assert out["sanchopanza"]["args"] == ["-m", "sanchopanza", "find-mcp", "--auto"]
    assert out["sanchopanza"]["env"]["USERPROFILE"] == str(tmp_path / "home")
    assert out["sanchopanza"]["alwaysLoad"] is True and out["other"]["command"] == "node"


# --- s_line: the proof, with real (free) installs ----------------------------------------------


def test_verify_proves_an_empty_line_and_a_default_on_flag(tmp_path):
    full, problems, hints = s_line.verify(s_line.parse({"flags": []}), SRC, tmp_path / "a")
    assert problems == [] and hints == ()
    _, problems, _ = s_line.verify(s_line.parse({"flags": ["--guard"]}), SRC, tmp_path / "b")
    assert problems == []  # on by default: proved through --no-guard


HELP = (
    "usage: sanchopanza install [--guard-profile {coding,sandbox}]\n"
    "  --guard-profile {coding,sandbox}\n  --context-budget CONTEXT_BUDGET\n"
    "  --provider PROVIDER\n"
)


def test_an_option_at_its_default_value_gets_another_value_to_prove_it():
    assert s_line.alternate(("--guard-profile", "coding"), HELP) == ("--guard-profile", "sandbox")
    assert s_line.alternate(("--guard-profile", "sandbox"), HELP) == ("--guard-profile", "coding")
    assert s_line.alternate(("--context-budget", "160000"), HELP) == ("--context-budget", "160001")
    assert s_line.alternate(("--provider", "jev"), HELP) is None  # free text: no other value
    assert s_line.alternate(("--memory",), HELP) is None


def test_verify_proves_valued_options_written_at_their_defaults(tmp_path):
    line = s_line.parse({"flags": ["--guard-profile", "coding", "--context-budget", "160000"]})
    _, problems, _ = s_line.verify(line, SRC, tmp_path)
    assert problems == []  # each one changes the install with another value


def test_verify_catches_an_unread_variable_and_registers_asked_servers(tmp_path):
    line = s_line.parse({"flags": ["--candor", "--fetch"],
                         "env": {"SANCHOPANZA_NO_SUCH_KNOB": "1"}})  # fmt: skip
    full, problems, hints = s_line.verify(line, SRC, tmp_path)
    assert problems == ["SANCHOPANZA_NO_SUCH_KNOB is not read by the frozen src"]
    assert hints == ("sanchopanza-fetch",)  # printed for --fetch, not by the bare install
    assert "sanchopanza-fetch" in s_line.registered(full, hints)
    assert "sanchopanza" not in s_line.registered(full, hints)  # find's hint: not asked for


def test_a_dropped_option_fails_the_full_install(tmp_path):
    with pytest.raises(RuntimeError, match="dropped"):
        s_line.run_install(tmp_path / "c", SRC, ["--find-auto"], tmp_path / "cwd")


# --- the local hook -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "args", "denied"),
    [
        ("Bash", {"command": "grep -n revenue document.txt | head"}, False),
        ("Bash", {"command": "python -c \"print(open('document.txt').read()[:100])\""}, False),
        ("Bash", {"command": "wc -c C:/sp-runs/x/work/document.txt"}, False),
        ("Bash", {"command": "curl -s https://example.com"}, True),
        ("Bash", {"command": "python -c 'import urllib.request'"}, True),
        ("Bash", {"command": "cat ../side/mcp.json"}, True),
        ("Bash", {"command": "ls ~/.cache"}, True),
        ("Bash", {"command": "cat /c/Users/x/.cache/sanchopanza/bcp/queries.enc.jsonl"}, True),
        ("Bash", {"command": "ls /etc"}, True),
        ("Bash", {"command": "echo x > /dev/null"}, False),
        ("PowerShell", {"command": "Invoke-WebRequest http://x"}, True),
        ("PowerShell", {"command": "Get-Content $env:USERPROFILE\\x"}, True),
        ("Read", {"file_path": "C:\\sp-runs\\x\\work\\document.txt"}, False),
        ("Read", {"file_path": "C:\\sp-runs\\x\\side\\bcp.jsonl"}, True),
        ("Grep", {"pattern": "x", "path": "C:/Users/someone"}, True),
        ("Grep", {"pattern": "x"}, False),
        ("Glob", {"pattern": "**/*.txt"}, False),
        ("Glob", {"pattern": "C:/Users/**/*.jsonl"}, True),
        ("WebFetch", {"url": "https://x"}, True),
        ("mcp__bcp__get_document", {"docid": "1"}, False),
        ("mcp__bcp__search", {"query": "a 1990s band from Leeds"}, False),
        # S's web tools: the fetch server is the web by another name, a URL to any server too
        ("mcp__sanchopanza-fetch__fetch_passages", {"url": "https://x", "purpose": "y"}, True),
        ("mcp__sanchopanza-fetch__fetch_passages", {"purpose": "y"}, True),
        ("mcp__other__open", {"target": "see https://x.org/a"}, True),
        ("mcp__sanchopanza__find_in_repo", {"query": "revenue table"}, False),
        # S1's knowledge server: search is the web; read and pick only inside the folder
        ("mcp__sanchopanza-knowledge__search", {"query": "a 1990s band"}, True),
        (
            "mcp__sanchopanza-knowledge__read",
            {"url_or_path": "document.txt", "purpose": "y"},
            False,
        ),
        (
            "mcp__sanchopanza-knowledge__read",
            {"url_or_path": "https://x.org", "purpose": "y"},
            True,
        ),
        (
            "mcp__sanchopanza-knowledge__read",
            {"url_or_path": "C:/sp-runs/x/side/a", "purpose": "y"},
            True,
        ),
        ("mcp__sanchopanza-knowledge__pick", {"purpose": "y", "sources": ["*.txt", "."]}, False),
        ("mcp__sanchopanza-knowledge__pick", {"purpose": "y", "sources": [".", "../side"]}, True),
        ("Task", {"prompt": "read ../x"}, False),
    ],
)
def test_local_hook(tool, args, denied):
    assert hook.denied(tool, args, "C:/sp-runs/x/work") is denied


def test_local_hook_probes_pass():
    assert common.local_hook_problems() == []


# --- BrowseComp-Plus: data ----------------------------------------------------------------------


def test_the_official_cipher_round_trips_and_the_password_is_read_from_the_script():
    blob = bcp_data.encrypt("a question with ü", "pw")
    assert blob != "a question with ü" and bcp_data.decrypt(blob, "pw") == "a question with ü"
    script = 'x = 1\nDEFAULT_CANARY = "SECRET canary GUID x:1"\n'
    assert bcp_data.canary_of(script) == "SECRET canary GUID x:1"
    with pytest.raises(ValueError):
        bcp_data.canary_of("nothing")


def test_qrels_and_summary_hold_ids_and_counts_only(tmp_path):
    qrel = tmp_path / "q.txt"
    qrel.write_text("1 0 10 1\n1 0 11 1\n2 0 12 0\n", encoding="utf-8")
    table = bcp_data.read_qrels(qrel)
    assert table == {"1": ["10", "11"]}
    queries = [bcp_data.Query("1", bcp_data.encrypt("secret q", "p"), "x"),
               bcp_data.Query("2", "y", "z")]  # fmt: skip
    out = bcp_data.summary(queries, {"evidence": table})
    assert out["queries"] == 2 and out["evidence_queries"] == 1 and out["evidence_docs"] == 2
    assert "secret" not in json.dumps(out)


def test_draw_is_seeded_and_the_ids_file_holds_a_hundred():
    queries = [bcp_data.Query(str(i), "q", "a") for i in range(300)]
    assert bcp.draw(queries, 10, 1) == bcp.draw(list(reversed(queries)), 10, 1)
    ids = gaia.read_ids(bcp.IDS)
    assert len(ids) == len(set(ids)) == bcp.SIZE


# --- BrowseComp-Plus: the server -----------------------------------------------------------------


class FakeRetriever:
    docs = {"10": "alpha " * 1000, "11": "beta"}

    def search(self, query, k):
        return [("10", 2.5), ("11", 1.0)][:k]

    def text(self, docid):
        return self.docs.get(docid)


def _call(srv, name, args, msg_id=3):
    return srv.handle({"jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
                       "params": {"name": name, "arguments": args}})  # fmt: skip


def test_server_speaks_mcp_and_logs_every_call(tmp_path):
    log = tmp_path / "log.jsonl"
    srv = server.Server(FakeRetriever, log)
    init = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2025-03-26"}})  # fmt: skip
    assert init["result"]["protocolVersion"] == "2025-03-26"
    assert srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert [t["name"] for t in tools] == ["search", "get_document"]
    assert tools[1]["description"] == "Retrieve a full document by its docid."
    hits = json.loads(_call(srv, "search", {"query": "x", "k": 1})["result"]["content"][0]["text"])
    assert hits == [{"docid": "10", "score": 2.5, "snippet": ("alpha " * 1000)[:2048]}]
    doc = json.loads(_call(srv, "get_document", {"docid": "11"})["result"]["content"][0]["text"])
    assert doc == {"docid": "11", "text": "beta"}
    missing = _call(srv, "get_document", {"docid": "99"})["result"]["content"][0]["text"]
    assert missing == "null"
    assert _call(srv, "nope", {})["result"]["isError"]
    assert srv.handle({"jsonrpc": "2.0", "id": 9, "method": "x/y"})["error"]["code"] == -32601
    logged = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert [e["tool"] for e in logged] == ["search", "get", "get"]
    assert bcp.server_log(log) == {"search_calls": 1, "get_calls": 2,
                                   "retrieved": ["10", "11", "99"]}  # fmt: skip


def test_k_is_clamped_and_stdio_round_trips():
    assert (
        server.clamp_k(50) == server.K_MAX and server.clamp_k("x") == 5 and server.clamp_k(0) == 1
    )
    stdin = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"ping"}\nnot json\n\n')
    stdout = io.StringIO()
    server.Server(FakeRetriever).serve(stdin, stdout)
    assert json.loads(stdout.getvalue()) == {"jsonrpc": "2.0", "id": 1, "result": {}}


def test_server_entry_runs_in_its_own_venv(tmp_path):
    entry = server.entry("C:/v/python.exe", tmp_path / "d", tmp_path / "i", tmp_path / "l")
    assert entry["command"] == "C:/v/python.exe" and entry["args"][0].endswith("bcp_server.py")
    assert "--log" in entry["args"]


# --- BrowseComp-Plus: grading --------------------------------------------------------------------


REPLY = (
    "Explanation: the club was founded in 1902 [12]. It moved twice [3, 4].\n"
    "**Exact Answer:** The Rovers\nConfidence: 85%"
)


def test_answer_confidence_and_citations_follow_the_official_format():
    assert grade.exact_answer(REPLY) == "The Rovers"
    assert grade.exact_answer("no format") is None
    assert grade.confidence(REPLY) == 85.0
    assert grade.citations(REPLY) == ["12", "3", "4"]
    assert grade.citation_metrics(["12", "3"], ["12", "99"]) == {
        "num_citations": 2,
        "precision": 0.5,
        "recall": 0.5,
    }
    assert grade.recall(["1", "2"], ["2", "3"]) == 0.5 and grade.recall(["1"], []) is None


@pytest.mark.parametrize(
    ("answer", "gold", "ok"),
    [
        ("The Rovers", "rovers", True),
        ("Rovers F.C.", "Rovers FC", True),
        ("1,902", "1902", True),
        ("Rangers", "Rovers", False),
        (None, "x", False),
        ("", "", False),
    ],
)
def test_exact_match(answer, gold, ok):
    assert grade.exact_match(answer, gold) is ok


def test_judge_template_parser_and_verdict():
    text = grade.judge_prompt("Q?", "R", "G")
    assert "[question]: Q?" in text and "[correct_answer]: G" in text and "|\\%|" in text
    assert grade.parse_judge("reasoning: x\n**correct:** yes") is True
    assert grade.parse_judge("correct: No") is False and grade.parse_judge("hm") is None
    assert grade.verdict(False, True) and grade.verdict(True, None)
    assert not grade.verdict(True, True, hand=False)
    assert grade.doubtful(False, True) and not grade.doubtful(True, True)
    argv = grade.judge_argv("claude", "m.json")
    assert argv[argv.index("--model") + 1] == grade.JUDGE_MODEL and "--max-turns" in argv
    assert "Bash" in argv[argv.index("--disallowedTools") + 1]


def test_prompt_is_the_official_template():
    text = grade.prompt("Which club?")
    assert "Question: Which club?" in text and "search and get_document tools" in text
    assert text.endswith("Confidence: {your confidence score between 0% and 100% for your answer}")


# --- BrowseComp-Plus: the runner -----------------------------------------------------------------


def _fake_claude(reply):
    def fake(argv, work, side, env):
        (side / "bcp.jsonl").write_text('{"tool":"search","docids":["10","11"]}\n', "utf-8")
        return {
            "result": reply,
            "total_cost_usd": 0.3,
            "is_error": False,
            "num_turns": 4,
            "subtype": "success",
        }, ""

    return fake


def test_a_bcp_session_end_to_end_with_a_fake_claude(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    monkeypatch.setattr(gaia, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(bcp_data, "password", lambda: "pw")
    captured = {}

    def fake(argv, work, side, env):
        captured["argv"], captured["mcp"] = argv, json.loads((side / "mcp.json").read_text())
        captured["settings"] = json.loads((side / "settings.json").read_text())
        captured["prompt"] = argv[-1]
        return _fake_claude(REPLY)(argv, work, side, env)

    monkeypatch.setattr(gaia, "run_claude", fake)
    query = bcp_data.Query("q1", bcp_data.encrypt("Which club?", "pw"),
                           bcp_data.encrypt("Rovers", "pw"))  # fmt: skip
    ctx = {"phase": "t", "qrels": {"evidence": {"q1": ["10", "12"]}, "gold": {"q1": ["10"]}}}
    row = bcp.one_session(query, 1, "SONNET-CC", ctx)
    assert "Which club?" in captured["prompt"] and "Rovers" not in captured["prompt"]
    assert list(captured["mcp"]["mcpServers"]) == ["bcp"]
    allowed = captured["argv"][captured["argv"].index("--allowedTools") + 1]
    disallowed = captured["argv"][captured["argv"].index("--disallowedTools") + 1]
    assert "WebSearch" in disallowed and "WebFetch" not in allowed
    assert "mcp__bcp__search" in captured["settings"]["permissions"]["allow"]
    assert "local_hook" in json.dumps(captured["settings"]["hooks"])
    assert row["final_answer"] == "The Rovers" and row["em"] and row["judged"] is None
    assert row["search_calls"] == 1 and row["evidence_recall"] == 0.5 and row["gold_recall"] == 1.0
    assert row["citations"]["precision"] == pytest.approx(1 / 3, abs=1e-4)
    assert row["cap_usd"] == bcp.CAPS["SONNET"] == 3.0


def _row(task, arm, em, judged=None, usd=0.3, **extra):
    return {
        "task": task,
        "arm": arm,
        "run": 1,
        "model_key": arm.split("-")[0],
        "em": em,
        "judged": judged,
        "list_usd": usd,
        "wall_s": 10.0,
        "hit_cap": False,
        "leak": False,
        "final_answer": "x",
        "denied": 0,
        "hook_denied": [],
        "search_calls": 3,
        "get_calls": 1,
        "evidence_recall": 0.5,
        "gold_recall": 0.5,
        "phase": "t",
        "citations": {"precision": 1.0, "recall": 0.5, "num_citations": 1},
        **extra,
    }


def test_report_grades_em_then_judge_then_hand_and_holds_no_text():
    rows = [_row("a", "SONNET-SP", True), _row("a", "SONNET-CC", False, True, judge_done=True),
            _row("b", "SONNET-SP", False, False, judge_done=True),
            _row("b", "SONNET-CC", False)]  # fmt: skip
    out = bcp.report(rows, {("a", "SONNET-CC", 1): False})
    sp, cc = out["by_arm"]["SONNET-SP"], out["by_arm"]["SONNET-CC"]
    assert sp["ok_oficial"] == 1 and sp["em"] == 1 and cc["ok_oficial"] == 0
    assert cc["judge_yes_without_em"] == 1 and cc["unjudged"] == 1
    assert out["paired"]["SONNET"]["oficial"]["a_only"] == 1
    assert "Rovers" not in json.dumps(out) and "Qwen3-32B" in out["grading"]


def test_the_judge_runs_only_on_unsettled_rows_under_its_ceiling(monkeypatch):
    calls = []

    def fake(row, query, secret):
        calls.append(row["task"])
        return {"judged": True, "judge_usd": 0.02, "judge_limited": False}

    monkeypatch.setattr(bcp, "judge_row", fake)
    monkeypatch.setattr(bcp_data, "load", lambda: [bcp_data.Query(t, "q", "a") for t in "abcd"])
    monkeypatch.setattr(bcp_data, "password", lambda: "pw")
    rows = [_row("a", "X-CC", True), _row("b", "X-CC", False), _row("c", "X-CC", False),
            _row("d", "X-CC", False, judge_done=True)]  # fmt: skip
    code, out = bcp.judge_pending(rows, ceiling=0.06)
    assert calls == ["b"] and code == 1  # 0.02 spent + 0.05 reserved crosses 0.06 at c
    assert out[1]["judged"] is True and out[1]["judge_done"] and len(out) == 4


def test_blind_review_shuffles_and_hides_the_arm(tmp_path, monkeypatch):
    monkeypatch.setattr(bcp_data, "load", lambda: [bcp_data.Query(
        "a", bcp_data.encrypt("Q", "pw"), bcp_data.encrypt("G", "pw"))])  # fmt: skip
    monkeypatch.setattr(bcp_data, "password", lambda: "pw")
    rows = [_row("a", "SONNET-SP", False, True, judge_done=True),
            _row("a", "SONNET-CC", True, None)]  # fmt: skip
    path = tmp_path / "r.jsonl"
    assert bcp.blind_review(rows, {}, path) == 1
    item = json.loads(path.read_text(encoding="utf-8"))
    assert item["question"] == "Q" and item["gold"] == "G" and "arm" not in item


def test_bcp_plan_is_free(capsys):
    assert bcp.main(["--plan", "--limit", "2"]) == 0
    out = capsys.readouterr().out
    assert "4 sessions" in out and "SONNET-SP" in out


# --- long documents ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reply", "want"),
    [
        ("The correct answer is (B)", "B"),
        ("**The correct answer is (C)**", "C"),
        ("The correct answer is D.", "D"),
        ("I think B", None),
        (None, None),
    ],
)
def test_longbench_extract_answer(reply, want):
    assert ld_data.extract_answer(reply) == want


def test_last_answer_takes_the_last_line():
    reply = "First: The correct answer is (A)\n...\nThe correct answer is (C)"
    assert ld_data.last_answer(reply) == "C" and ld_data.extract_answer(reply) == "A"


def _ld_row(i, domain="Single-Document QA", chars=200_000):
    return {
        "_id": f"id{i:03d}",
        "domain": domain,
        "sub_domain": "s",
        "difficulty": "hard",
        "length": "long",
        "question": "q?",
        "choice_A": "a",
        "choice_B": "b",
        "choice_C": "c",
        "choice_D": "d",
        "answer": "B",
        "context": "x" * chars,
    }


def test_draw_is_seeded_and_eligible_only(tmp_path):
    rows = [_ld_row(i) for i in range(80)] + [_ld_row(100, chars=50_000),
                                              _ld_row(101, domain="Code Repository")]  # fmt: skip
    ids = ld_data.draw_ids(rows, 60, 3)
    assert len(set(ids)) == 60 and "id100" not in ids and "id101" not in ids
    assert ids == ld_data.draw_ids(list(reversed(rows)), 60, 3)
    tasks = ld_data.write_draw(rows, tmp_path / "docs", tmp_path / "tasks.jsonl")
    loaded = ld_data.load(tmp_path / "tasks.jsonl")
    assert loaded == tasks and pathlib.Path(tasks[0].doc_path).stat().st_size == 200_000
    assert "x" * 100 not in json.dumps(ld_data.summary(loaded))


def test_the_drawn_tasks_are_sixty_long_documents():
    if not ld_data.TASKS.exists():
        pytest.skip("long-document tasks not in the local cache")
    out = ld_data.summary(ld_data.load())
    assert out["tasks"] == 60 and out["chars_min"] > ld_data.MIN_CHARS


def test_longdoc_prompt_points_at_the_file(tmp_path):
    task = ld_data.to_task(_ld_row(1), tmp_path)
    text = longdoc.prompt(task)
    assert "document.txt" in text and "xxxx" not in text
    assert "(B) b" in text and text.endswith('"The correct answer is (insert answer here)".')


def test_a_longdoc_session_end_to_end_with_a_fake_claude(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    monkeypatch.setattr(gaia, "RUNS", tmp_path / "runs")
    task = ld_data.write_draw([_ld_row(i) for i in range(60)], tmp_path / "d",
                              tmp_path / "t.jsonl")[0]  # fmt: skip
    seen = {}

    def fake(argv, work, side, env):
        seen["doc"] = (work / "document.txt").stat().st_size
        seen["mcp"] = json.loads((side / "mcp.json").read_text())
        return {"result": "The correct answer is (B)", "total_cost_usd": 0.4,
                "is_error": False}, ""  # fmt: skip

    monkeypatch.setattr(gaia, "run_claude", fake)
    row = longdoc.one_session(task, 1, "SONNET-CC", {"phase": "t"})
    assert seen == {"doc": 200_000, "mcp": {"mcpServers": {}}}
    assert row["final_answer"] == "B" and row["ok_oficial"] and row["length"] == "long"
    out = longdoc.report([row, {**row, "arm": "SONNET-SP", "brazo": "SP"}])
    assert out["by_arm"]["SONNET-CC"]["by_length"] == {"long": "1/1"}
    assert out["paired"]["SONNET"]["tasks"] == 1


def test_an_sp_session_gets_the_lines_install_and_its_servers(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    monkeypatch.setenv("TYPESAFE_API_KEY", "key")
    monkeypatch.setattr(gaia, "RUNS", tmp_path / "runs")
    task = ld_data.write_draw([_ld_row(i) for i in range(60)], tmp_path / "d",
                              tmp_path / "t.jsonl")[0]  # fmt: skip
    line = s_line.parse({"sealed": True, "flags": ["--fetch"],
                         "env": {"SANCHOPANZA_CONTEXT_BUDGET": "150000"}})  # fmt: skip
    full, problems, hints = s_line.verify(line, SRC, tmp_path / "verify")
    assert problems == []
    seen = {}

    def fake(argv, work, side, env):
        seen["argv"], seen["env"] = argv, env
        seen["mcp"] = json.loads((side / "mcp.json").read_text())
        return {"result": "The correct answer is (A)", "total_cost_usd": 0.4,
                "is_error": False}, ""  # fmt: skip

    monkeypatch.setattr(gaia, "run_claude", fake)
    ctx = {"phase": "t", "src": SRC, "shim": tmp_path / "bin", "line": line,
           "s_digest": full.digest, "s_hints": hints, "commit": "abc"}  # fmt: skip
    row = longdoc.one_session(task, 1, "SONNET-SP", ctx)
    assert list(seen["mcp"]["mcpServers"]) == ["sanchopanza-fetch"]
    assert "mcp__sanchopanza-fetch" in seen["argv"][seen["argv"].index("--allowedTools") + 1]
    assert seen["env"]["SANCHOPANZA_CONTEXT_BUDGET"] == "150000"
    assert row["s_digest"] == full.digest and not row["ok_oficial"]


def test_a_paid_phase_refuses_an_unsealed_line(tmp_path):
    unsealed = tmp_path / "s.json"
    unsealed.write_text(json.dumps({"sealed": False, "flags": ["--candor"]}), encoding="utf-8")
    args = argparse.Namespace(s_line=str(unsealed), brazos=["CC", "SP"], unsealed_ok=False)
    with pytest.raises(SystemExit, match="not sealed"):
        gaia.live_line(args)
    assert gaia.live_line(argparse.Namespace(**{**vars(args), "brazos": ["CC"]})).flags == (
        "--candor",
    )
    assert gaia.live_line(argparse.Namespace(**{**vars(args), "unsealed_ok": True})).flags


# --- answers with candor's status block behind them (S), the same rule in both arms ---------------

CANDOR = (
    "\n\n---\ncandor: 3 claims held against the transcript and the disk\n"
    "status: consistent\nlock: none\nnext: nothing to release\n"
)


@pytest.mark.parametrize(
    ("reply", "want"),
    [
        ("Work...\nFINAL ANSWER: 42" + CANDOR, "42"),
        ("FINAL ANSWER: 1\nthen\nFINAL ANSWER: Paris\r" + CANDOR, "Paris"),
        ("FINAL ANSWER: a, b" + CANDOR.replace("\n", "\r\n"), "a, b"),
        ("no marker" + CANDOR, None),
    ],
)
def test_the_answer_is_the_last_markers_line_only(reply, want):
    assert gaia.reading.marker_line(reply) == want
    assert gaia.scorer.final_answer(reply) == want


# candor's real block: the four lines `candor.claims.BLOCK_REQUEST` asks for, as agents write them.
STATUS_BLOCK = "STATUS: done\nTESTS: not run\nTEST_FILES_CHANGED: no\nFILES_READ: none\n"


@pytest.mark.parametrize(
    ("reply", "want"),
    [
        ("Work...\nFINAL ANSWER:\n\n  Paris  \n" + STATUS_BLOCK, "Paris"),
        ("FINAL ANSWER: \r\n**42**\r\n" + STATUS_BLOCK.replace("\n", "\r\n"), "42"),
        ("FINAL ANSWER:\n\n" + STATUS_BLOCK, ""),
        ("FINAL ANSWER:\n- **STATUS:** done\nTESTS: not run\n", ""),
        ("FINAL ANSWER:", ""),
        ("FINAL ANSWER: x\nFINAL ANSWER:\nRome\n" + STATUS_BLOCK, "Rome"),
        ("FINAL ANSWER: 7\n" + STATUS_BLOCK, "7"),
    ],
)
def test_an_empty_marker_line_takes_the_next_line_but_never_candors_block(reply, want):
    assert gaia.reading.marker_line(reply) is not None
    assert gaia.reading.marker_line(reply).strip("*") == want
    assert gaia.scorer.final_answer(reply) == want


def test_bcp_and_longdoc_answers_ignore_a_candor_block():
    reply = "Explanation: x [1]\nExact Answer: The Rovers\nConfidence: 80%" + CANDOR
    assert grade.exact_answer(reply) == "The Rovers" and grade.confidence(reply) == 80.0
    assert grade.exact_answer("Exact Answer: A\nExact Answer: B" + CANDOR) == "B"
    assert ld_data.last_answer("The correct answer is (C)" + CANDOR) == "C"


# --- the dev draw and the joint ceiling of suites run side by side --------------------------------


def test_the_dev_draw_is_seeded_and_left_out_of_every_other_phase(tmp_path):
    pool = [str(i) for i in range(100)]
    dev = common.draw_dev(pool)
    assert dev == common.draw_dev(list(reversed(pool))) and len(set(dev)) == common.DEV_SIZE
    path = tmp_path / "x-dev-ids.txt"
    common.write_ids(path, dev, "ten dev ids")
    assert gaia.read_ids(path) == dev
    assert common.leave_out_dev(pool, tmp_path / "all.txt", path) == [
        i for i in pool if i not in dev
    ]
    assert common.leave_out_dev(dev, path, path) == dev  # the dev phase itself
    assert common.leave_out_dev(pool, None, tmp_path / "none.txt") == pool


def _spend(path, *usd):
    path.write_text("".join(json.dumps({"list_usd": u}) + "\n" for u in usd), encoding="utf-8")


def test_the_joint_ceiling_counts_the_other_suites_spend_and_its_session_in_flight(tmp_path):
    own, other = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    _spend(own, 10.0, 10.0)
    _spend(other, 23.0)
    calls = []
    guarded = common.joint_guard(lambda *a: calls.append(a) or {"ok": 1}, own, [other], 3.0, 50.0)
    assert guarded("t", 1, "SONNET-CC") == {"ok": 1}  # 43 spent + 2 x 3 reserved = 49
    _spend(other, 24.5)
    with pytest.raises(common.JointCeiling, match="joint ceiling"):
        guarded("t", 1, "SONNET-SP")  # 44.5 + 6 > 50
    assert len(calls) == 1


def test_a_joint_stop_ends_the_phase_with_its_rows(tmp_path):
    sessions, other = tmp_path / "s.jsonl", tmp_path / "o.jsonl"
    _spend(other, 45.0)
    limits = gaia.phase.Limits(session_max_usd=3.0, ceiling_usd=50.0)
    item = ("q1", "", "", None)
    steps = [(0, item, 1, "SONNET-CC"), (0, item, 1, "SONNET-SP")]

    def session(task, run, arm):
        return {"task": task[0], "run": run, "arm": arm, "list_usd": 0.5}

    guarded = common.joint_guard(session, sessions, [other], 3.0, 50.0)
    code, rows = common.run_guarded(steps, [], limits, guarded, sessions)
    assert code == 1 and rows == []
    assert "joint ceiling" in sessions.with_suffix(".log").read_text(encoding="utf-8")


def test_longdoc_runs_an_ids_file_in_order_and_leaves_the_dev_ids_out(tmp_path, monkeypatch):
    tasks = ld_data.write_draw([_ld_row(i) for i in range(60)], tmp_path / "d",
                               tmp_path / "t.jsonl")  # fmt: skip
    dev_ids = [tasks[5].task_id, tasks[0].task_id]
    dev = tmp_path / "longdoc-dev-ids.txt"
    common.write_ids(dev, dev_ids, "dev")
    monkeypatch.setattr(longdoc, "DEV_IDS", dev)
    rest = [t.task_id for t in longdoc.chosen(tasks, None)]
    assert rest == [t.task_id for t in tasks if t.task_id not in dev_ids]
    assert [t.task_id for t in longdoc.chosen(tasks, str(dev))] == dev_ids


def test_suites_run_side_by_side_prove_the_line_in_folders_of_their_own():
    one, two = gaia.verify_scratch("abc", "bcp-dev"), gaia.verify_scratch("abc", "longdoc-dev")
    assert one != two and one.parent == two.parent == gaia.RUNS / "verify"


def test_an_install_a_busy_file_stopped_is_tried_again_a_few_times(tmp_path, monkeypatch):
    real = s_line.subprocess.run
    calls = []

    def flaky(argv, **kw):
        calls.append(argv)
        if len(calls) == 1:
            return s_line.subprocess.CompletedProcess(
                argv, 2, "", "could not write x ([WinError 32] ...)"
            )
        return real(argv, **kw)

    monkeypatch.setattr(s_line.subprocess, "run", flaky)
    monkeypatch.setattr(s_line, "BUSY_WAIT_S", 0.0)
    assert s_line.run_install(tmp_path / "c", SRC, ["--candor"], tmp_path / "cwd").settings
    assert len(calls) == 2

    def busy(argv, **kw):
        calls.append(argv)
        return s_line.subprocess.CompletedProcess(argv, 2, "", "WinError 32")

    monkeypatch.setattr(s_line.subprocess, "run", busy)
    calls.clear()
    with pytest.raises(RuntimeError, match="install failed"):
        s_line.run_install(tmp_path / "d", SRC, ["--candor"], tmp_path / "cwd2")
    assert len(calls) == s_line.INSTALL_TRIES


def test_the_preflight_proves_the_line_the_run_uses(monkeypatch):
    """`--s-line` reaches the preflight: before 2026-10-06 it proved s_install.json whatever the
    run was given, and an S1 line the live run refused passed it."""
    seen = []

    def arms_preflight(brazos, line=None, phase_name=""):
        seen.append((line, phase_name))
        return []

    monkeypatch.setattr(gaia, "arms_preflight", arms_preflight)
    monkeypatch.setattr(gaia, "claude_problems", lambda: [])
    line = s_line.load(H2H / "s1_install.json")
    common.preflight(["SP"], {}, [], line, "bcp-dev-s1")
    gaia.preflight(["SP"], line, "dev-s1")
    # and each phase proves it in folders of its own, so suites started together do not collide
    assert seen == [(line, "bcp-dev-s1"), (line, "dev-s1")]
