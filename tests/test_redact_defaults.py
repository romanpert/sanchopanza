"""Secrets are masked before a state leaves the machine, on every squire the package builds.

An audit of 2026-10-17 found that `squire_from_env` defaulted to `redact=False`, and that the
squire of `sanchopanza hook` (`guardian_from_env`: shell commands, searches, subagent reports),
the MCP server's and the `label`/`browse` commands' took that default: a command carrying a
token went to the provider unmasked. `ask_document` (`points.longdoc`) asked Jev with no squire
at all. These tests send a shell command with secrets of each kind the redactor knows down each
path and check that none of them reaches the decider, in the state or in the questions; pin the
safe default; and scan `src/` for a squire built without a redactor and for a decider asked
directly, failing closed on what the scan cannot read.
"""

from __future__ import annotations

import ast
import asyncio
import io
import json
from pathlib import Path

import pytest

from sanchopanza.contract import Decision, Truth
from sanchopanza.harness import claude_code
from sanchopanza.redact import redact_secrets

SRC = Path(__file__).resolve().parents[1] / "src" / "sanchopanza"

# Shapes the redactor masks (`redact.PATTERNS`); none of them is a real credential.
SECRETS = (
    "AKIAABCDEFGHIJKLMNOP",
    "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "sk-proj-abcdefghijklmnopqrstuvwx",
    "hunter2-not-a-real-one",
)
COMMAND = (
    f"AWS_ACCESS_KEY_ID={SECRETS[0]} curl -H 'Authorization: token {SECRETS[1]}' "
    f"-H 'X-Api-Key: {SECRETS[2]}' -d password={SECRETS[3]} https://api.example.test/upload"
)


class Capture:
    """A decider that keeps every state and every question (as they go on the wire) it is
    given, and answers nothing (the caller fails open)."""

    name = "capture"
    model = "capture-1"

    def __init__(self) -> None:
        self.states: list[object] = []
        self.questions: list[object] = []

    def with_long_context(self, *, timeout_s: float | None = None) -> Capture:
        return self  # for `points.longdoc`, which asks only a long-context decider

    async def decide(self, point, state, questions):  # noqa: ANN001, ANN201
        from sanchopanza.providers.jev import to_wire

        self.states.append(state)
        self.questions.append({k: to_wire(q) for k, q in questions.items()})
        return Decision(point, {}, "capture", self.model)


def _leaked(sent: list[object]) -> list[str]:
    seen = json.dumps(sent, ensure_ascii=False, default=str)
    return [secret for secret in SECRETS if secret in seen]


def _clean(decider: Capture) -> bool:
    assert decider.states, "nothing was asked: the test would prove nothing"
    return _leaked(decider.states) == [] and _leaked(decider.questions) == []


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Capture:
    """The environment's decider, wherever a path asks for it, is a `Capture`."""
    decider = Capture()
    monkeypatch.setattr(claude_code, "decider_from_env", lambda env=None: decider)
    monkeypatch.setenv("SANCHOPANZA_JOURNAL", str(tmp_path / "journal.jsonl"))
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    return decider


def test_the_command_carries_every_secret_and_the_redactor_masks_them_all() -> None:
    assert _leaked([COMMAND]) == list(SECRETS)
    assert _leaked([redact_secrets({"command": COMMAND})]) == []


# --- the default ---------------------------------------------------------------------------------


def test_squire_from_env_redacts_by_default(captured: Capture) -> None:
    squire = claude_code.squire_from_env({})
    asyncio.run(squire.decide("p", {"command": COMMAND}, {"q": Truth("q?")}))
    assert _clean(captured)


def test_squire_from_env_sends_raw_only_when_asked(captured: Capture) -> None:
    squire = claude_code.squire_from_env({}, redact=False)
    asyncio.run(squire.decide("p", {"command": COMMAND}, {"q": Truth("q?")}))
    assert _leaked(captured.states) == list(SECRETS)


# --- each path -----------------------------------------------------------------------------------


def _bash(tmp_path: Path) -> dict:
    return {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": str(tmp_path),
            "tool_name": "Bash", "tool_input": {"command": COMMAND}}  # fmt: skip


def test_the_hooks_main_masks_a_shell_command(
    tmp_path: Path, captured: Capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`sanchopanza hook` itself: the event on stdin, the settings in the process environment,
    the squire built by `main` (with the autopilot off, `guardian_from_env`'s alone)."""
    from sanchopanza.harness import hookio

    monkeypatch.setenv("SANCHOPANZA_GUARD_PROFILE", "coding")
    monkeypatch.setattr(hookio, "stdin_text", lambda: json.dumps(_bash(tmp_path)))
    monkeypatch.setattr("sys.stdout", io.StringIO())
    assert claude_code.main([]) == 0
    assert _clean(captured)


def test_the_hooks_guardian_masks_a_shell_command(tmp_path: Path, captured: Capture) -> None:
    """`guardian_from_env` with a decider passed in, as the recorded replays build it."""
    env = {"SANCHOPANZA_GUARD_PROFILE": "coding", "SANCHOPANZA_JOURNAL": str(tmp_path / "j")}
    event = _bash(tmp_path)
    assert claude_code.needs_decision(event, claude_code.config_from_env(env))
    guardian = claude_code.guardian_from_env(env, decider=captured)
    asyncio.run(claude_code.handle(event, guardian))
    assert _clean(captured)


class FakeServer:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}
        self.ran = False

    def tool(self, **_: object):  # noqa: ANN201
        def register(fn):  # noqa: ANN001, ANN202
            self.tools[fn.__name__] = fn
            return fn

        return register

    def run(self) -> None:
        self.ran = True


def test_the_mcp_servers_decision_tools_mask_a_shell_command(
    monkeypatch: pytest.MonkeyPatch, captured: Capture
) -> None:
    """`python -m sanchopanza.harness.mcp --tools decisions`, its squire built by `main`."""
    from sanchopanza.harness import mcp

    server = FakeServer()
    monkeypatch.setattr(mcp, "_server", lambda *a, **k: server)
    assert mcp.main(["--tools", "decisions"]) == 0 and server.ran
    options = json.dumps({"deploy": "ships code", "other": "anything else"})
    asyncio.run(server.tools["classify_field"](field="kind", text=COMMAND, options=options))
    assert _clean(captured)


def test_the_mcp_keyed_squire_masks_a_shell_command(captured: Capture) -> None:
    """`_squire_if_keyed`: find, find_auto, label, browse and knowledge on the MCP server."""
    from sanchopanza.harness import mcp

    squire = mcp._squire_if_keyed()
    asyncio.run(squire.decide("p", {"command": COMMAND}, {"q": Truth("q?")}))
    assert _clean(captured)


def test_sanchopanza_label_masks_a_shell_command(
    tmp_path: Path, captured: Capture, capsys: pytest.CaptureFixture[str]
) -> None:
    """`sanchopanza label` (cli_corpus), whose squire `browse` shares."""
    import argparse

    from sanchopanza import cli_corpus

    items = tmp_path / "items.jsonl"
    items.write_text(json.dumps({"key": "1", "text": COMMAND}) + "\n", encoding="utf-8")
    rubric = tmp_path / "rubric.json"
    rubric.write_text(json.dumps({"field": "kind", "options": {"deploy": "d", "other": "o"}}))
    args = argparse.Namespace(items=str(items), rubric=str(rubric), out=str(tmp_path / "o.csv"),
                              max_usd=0.01, cache="", max_age_days=30.0, concurrency=1)  # fmt: skip
    assert cli_corpus._label(args) == 0
    capsys.readouterr()
    assert _clean(captured)


def _long_document(tmp_path: Path) -> Path:
    path = tmp_path / "runbook.txt"
    filler = "The deploy runs from the release branch after the checks pass. " * 2_000
    path.write_text(f"{filler}\nTo deploy: {COMMAND}\n{filler}", encoding="utf-8")
    return path


def test_ask_document_masks_a_shell_command_in_the_document(tmp_path: Path) -> None:
    """`ask_document` (harness/longdoc_tool.py), which asks Jev through `points.longdoc` with no
    squire: the question, the document and the options."""
    from sanchopanza.harness.knowledge_tool import Knowledge
    from sanchopanza.harness.longdoc_tool import Asker

    decider = Capture()
    decider.model = "jev-1.14.0"
    kit = Knowledge(fetcher=object(), searcher=object(), squire=None, roots=[tmp_path])
    asker = Asker(kit=kit, decider=decider)
    options = ["curl", f"password={SECRETS[3]}", "scp", "rsync"]
    reply = asyncio.run(
        asker.ask(str(_long_document(tmp_path)), f"Which tool uploads with {SECRETS[1]}?", options)
    )
    assert reply.startswith("Not answered")  # the capture answers nothing
    assert _clean(decider)


def test_longdoc_sends_raw_only_when_asked() -> None:
    from sanchopanza.points import longdoc

    decider = Capture()
    decider.model = longdoc.MEASURED_MODEL
    asyncio.run(longdoc.answer(decider, COMMAND, "Which?", list("abcd"), redact=False))
    assert _leaked(decider.states) == list(SECRETS)


# --- the scan ------------------------------------------------------------------------------------

SQUIRE_NAMES = frozenset({"Squire", "squire_from_env"})
# A redactor the scan accepts by name: `redact`'s functions and a squire's own (`fork`).
SAFE_REDACTORS = frozenset({"redact_secrets", "mask", "mask_strict", "_redact"})

# A squire built in src/ without a redactor: (file, enclosing function, callee) -> how many.
ALLOWED_RAW = {
    # `sanchopanza bench`: the decider measured on the case as written. The bench files are
    # authored and public, their recordings are keyed by the state as written, and a redactor
    # would rewrite 7 cases of agentdojo-injection.jsonl (AgentDojo's own fake passwords).
    ("eval/bench.py", "run_bench.one", "Squire"): 1,
    # The switch itself, `redact_secrets if redact else None`: `redact` defaults to True and
    # every caller in src/ passes True (the scan), so None is reached only by a caller outside
    # src/ that asks for it (the recorded replays keyed raw).
    ("harness/claude_code.py", "squire_from_env", "Squire"): 1,
}

# A decider asked directly, not through a squire, outside a decider's own `decide` (a wrapper
# passes on what a squire gave it): (file, enclosing function) -> how many.
# A decider's own parameters: a call naming these is a decider's, whatever its receiver.
DECIDE_ARGS = frozenset({"point", "state", "questions"})
ALLOWED_DIRECT = {
    # `ask_document` and the library point: redacts the question, the document and the options
    # itself before the call (`redact=True` by default; the ask_document test above).
    ("points/longdoc.py", "answer"): 1,
}


def _scope(tree: ast.AST) -> dict[ast.AST, str]:
    """Each call node's enclosing function, dotted (`run_bench.one`); "" at module level."""
    where: dict[ast.AST, str] = {}

    def visit(node: ast.AST, name: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = name
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                inner = f"{name}.{child.name}" if name else child.name
            if isinstance(child, ast.Call):
                where[child] = name
            visit(child, inner)

    visit(tree, "")
    return where


def _aliases(tree: ast.AST) -> dict[str, str]:
    """Local names for `Squire` and `squire_from_env`, `import ... as ...` included."""
    names = {n: n for n in SQUIRE_NAMES}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in SQUIRE_NAMES:
                    names[alias.asname or alias.name] = alias.name
    return names


def _callee(call: ast.Call) -> str:
    func = call.func
    return func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")


def _files() -> list[tuple[str, ast.AST]]:
    return [(p.relative_to(SRC).as_posix(), ast.parse(p.read_text(encoding="utf-8")))
            for p in sorted(SRC.rglob("*.py"))]  # fmt: skip


def _squire_calls() -> list[tuple[str, str, str, int, ast.Call]]:
    found = []
    for where, tree in _files():
        names, scope = _aliases(tree), _scope(tree)
        for call, function in scope.items():
            if (name := names.get(_callee(call))) is not None:
                found.append((where, function, name, call.lineno, call))
    return found


def _safe(value: ast.expr) -> bool:
    if isinstance(value, ast.Constant):
        return value.value is True
    if isinstance(value, ast.Name):
        return value.id in SAFE_REDACTORS
    if isinstance(value, ast.Attribute):
        return value.attr in SAFE_REDACTORS
    if isinstance(value, ast.IfExp):
        return _safe(value.body) and _safe(value.orelse)
    return False


def _unsafe(call: ast.Call) -> str | None:
    """Why this squire may send states raw; None when the scan can tell it redacts."""
    if any(k.arg is None for k in call.keywords) or any(
        isinstance(a, ast.Starred) for a in call.args
    ):
        return "**kwargs or *args: the scan cannot tell"
    given = {k.arg: k.value for k in call.keywords}
    if "redact" not in given:
        return "no redact="
    if not _safe(given["redact"]):
        return f"redact={ast.unparse(given['redact'])}"
    return None


def _counts(rows: list[tuple[str, str, str]]) -> dict[tuple[str, str, str], int]:
    out: dict[tuple[str, str, str], int] = {}
    for row in rows:
        out[row] = out.get(row, 0) + 1
    return out


def test_every_squire_in_src_redacts() -> None:
    calls = _squire_calls()
    assert len(calls) >= 10, "the scan found too few squires: it is not reading src/"
    raw = [(w, f, n, line, why) for w, f, n, line, c in calls if (why := _unsafe(c))]
    found = _counts([(w, f, n) for w, f, n, _, _ in raw])
    unexpected = [r for r in raw if (r[0], r[1], r[2]) not in ALLOWED_RAW]
    assert not unexpected, "a squire without a redactor sends secrets out:\n" + "\n".join(
        f"{w}:{line} {n}(...) in {f or '<module>'}: {why}" for w, f, n, line, why in unexpected
    )
    assert found == ALLOWED_RAW, f"allowed raw squires changed: {found}"


def _direct_calls() -> list[tuple[str, str, int]]:
    """`x.decide(point, state, questions)` / `x.adecide(...)` that is not a squire's own, not
    inside a decider's `decide` and not in squire.py. A point's pure `decide(decision, ...)`
    takes fewer than three positional arguments and is not counted."""
    found = []
    for where, tree in _files():
        if where == "squire.py":
            continue
        for call, function in _scope(tree).items():
            func = call.func
            if not isinstance(func, ast.Attribute) or func.attr not in ("decide", "adecide"):
                continue
            starred = any(isinstance(a, ast.Starred) for a in call.args)
            if (
                len(call.args) + sum(k.arg in DECIDE_ARGS for k in call.keywords) < 3
                and not starred
            ):
                continue
            receiver = func.value
            if isinstance(receiver, ast.Name) and receiver.id == "squire":
                continue
            if function.rsplit(".", 1)[-1] in ("decide", "adecide"):
                continue  # a decider wrapper (cache, cap, chain, recorder) passes it on
            found.append((where, function, call.lineno))
    return found


def test_no_decider_is_asked_past_a_squire_outside_the_allowed() -> None:
    calls = _direct_calls()
    unexpected = [c for c in calls if (c[0], c[1]) not in ALLOWED_DIRECT]
    assert not unexpected, "a decider asked with no squire (no redactor):\n" + "\n".join(
        f"{w}:{line} in {f}" for w, f, line in unexpected
    )
    found: dict[tuple[str, str], int] = {}
    for w, f, _ in calls:
        found[(w, f)] = found.get((w, f), 0) + 1
    assert found == ALLOWED_DIRECT, f"allowed direct calls changed: {found}"


def _call(source: str) -> ast.Call:
    node = ast.parse(source).body[0].value  # type: ignore[attr-defined]
    assert isinstance(node, ast.Call)
    return node


@pytest.mark.parametrize(
    ("source", "why"),
    [
        ("squire_from_env(env)", "no redact="),
        ("squire_from_env(redact=False)", "redact=False"),
        ("squire_from_env(env, redact=flag)", "redact=flag"),
        ("squire_from_env(**options)", "**kwargs or *args: the scan cannot tell"),
        ("Squire(d, redact=None)", "redact=None"),
        ("Squire(d, redact=lambda s: s)", "redact=lambda s: s"),
        ("Squire(d, redact=redact_secrets if on else None)",
         "redact=redact_secrets if on else None"),
        ("Squire(d, redact=redact_secrets)", None),
        ("Squire(d, redact=redact.mask_strict)", None),
        ("Squire(d, redact=self._redact)", None),
        ("Squire(d, redact=mask if strict is False else mask_strict)", None),
        ("squire_from_env(redact=True)", None),
    ],
)  # fmt: skip
def test_the_scan_fails_closed(source: str, why: str | None) -> None:
    assert _unsafe(_call(source)) == why


def test_the_scan_sees_through_an_import_alias() -> None:
    tree = ast.parse(
        "from sanchopanza.squire import Squire as S\n"
        "from .claude_code import squire_from_env as env_squire\n"
        "def build():\n    return S(d), env_squire()\n"
    )
    names, scope = _aliases(tree), _scope(tree)
    seen = sorted(names[_callee(c)] for c in scope if _callee(c) in names)
    assert seen == ["Squire", "squire_from_env"]
