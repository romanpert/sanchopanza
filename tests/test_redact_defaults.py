"""Secrets are masked before a state leaves the machine, on every squire the package builds.

An audit of 2026-10-17 found that `squire_from_env` defaulted to `redact=False`, and that the
squire of `sanchopanza hook` (`guardian_from_env`: shell commands, searches, subagent reports),
the MCP server's and the `label`/`browse` commands' took that default: a command carrying a
token went to the provider unmasked. These tests send a shell command with secrets of each kind
the redactor knows down each path and check that none of them reaches the decider, pin the
safe default, and scan `src/` for a squire built without a redactor.
"""

from __future__ import annotations

import ast
import asyncio
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
    """A decider that keeps every state it is given and answers nothing (the caller fails
    open)."""

    name = "capture"
    model = "capture-1"

    def __init__(self) -> None:
        self.states: list[object] = []

    async def decide(self, point, state, questions):  # noqa: ANN001, ANN201
        self.states.append(state)
        return Decision(point, {}, "capture", "capture-1")


def _leaked(states: list[object]) -> list[str]:
    seen = json.dumps(states, ensure_ascii=False, default=str)
    return [secret for secret in SECRETS if secret in seen]


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
    assert captured.states and _leaked(captured.states) == []


def test_squire_from_env_sends_raw_only_when_asked(captured: Capture) -> None:
    squire = claude_code.squire_from_env({}, redact=False)
    asyncio.run(squire.decide("p", {"command": COMMAND}, {"q": Truth("q?")}))
    assert _leaked(captured.states) == list(SECRETS)


# --- each path -----------------------------------------------------------------------------------


def test_the_hooks_guardian_masks_a_shell_command(tmp_path: Path, captured: Capture) -> None:
    """`sanchopanza hook` on PreToolUse Bash, the way `main` builds it."""
    env = {"SANCHOPANZA_GUARD_PROFILE": "coding", "SANCHOPANZA_JOURNAL": str(tmp_path / "j")}
    event = {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": str(tmp_path),
             "tool_name": "Bash", "tool_input": {"command": COMMAND}}  # fmt: skip
    assert claude_code.needs_decision(event, claude_code.config_from_env(env))
    guardian = claude_code.guardian_from_env(env, decider=captured)
    asyncio.run(claude_code.handle(event, guardian))
    assert captured.states, "the guard asked nothing: the test would prove nothing"
    assert _leaked(captured.states) == []


def test_the_hooks_guardian_from_the_environment_masks_too(
    tmp_path: Path, captured: Capture
) -> None:
    """Without a decider passed in, as `main` calls it: the provider the environment names."""
    env = {"SANCHOPANZA_GUARD_PROFILE": "coding", "SANCHOPANZA_JOURNAL": str(tmp_path / "j")}
    event = {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": str(tmp_path),
             "tool_name": "Bash", "tool_input": {"command": COMMAND}}  # fmt: skip
    asyncio.run(claude_code.handle(event, claude_code.guardian_from_env(env)))
    assert captured.states and _leaked(captured.states) == []


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
    assert captured.states and _leaked(captured.states) == []


def test_the_mcp_keyed_squire_masks_a_shell_command(captured: Capture) -> None:
    """`_squire_if_keyed`: find, find_auto, label, browse and knowledge on the MCP server."""
    from sanchopanza.harness import mcp

    squire = mcp._squire_if_keyed()
    asyncio.run(squire.decide("p", {"command": COMMAND}, {"q": Truth("q?")}))
    assert captured.states and _leaked(captured.states) == []


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
    assert captured.states and _leaked(captured.states) == []


# --- the scan ------------------------------------------------------------------------------------

# A squire built in src/ without a redactor, each with why. Everything else redacts.
ALLOWED_RAW = {
    # `sanchopanza bench`: the decider measured on the case as written. The bench files are
    # authored and public, their recordings are keyed by the state as written, and a redactor
    # would rewrite 7 cases of agentdojo-injection.jsonl (AgentDojo's own fake passwords).
    ("eval/bench.py", "Squire"),
}


def _calls() -> list[tuple[str, int, str, ast.Call]]:
    found = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in ("Squire", "squire_from_env"):
                found.append((path.relative_to(SRC).as_posix(), node.lineno, name, node))
    return found


def _unsafe(name: str, call: ast.Call) -> str | None:
    given = {k.arg: k.value for k in call.keywords if k.arg}
    if any(k.arg is None for k in call.keywords):
        return None  # **kwargs: cannot tell, and src/ has none
    if "redact" not in given:
        return "no redact="
    value = given["redact"]
    if isinstance(value, ast.Constant) and value.value in (None, False):
        return f"redact={value.value!r}"
    return None


def test_every_squire_in_src_redacts() -> None:
    calls = _calls()
    assert len(calls) >= 10, "the scan found too few squires: it is not reading src/"
    bad = [
        f"{where}:{line} {name}(...): {why}"
        for where, line, name, call in calls
        if (why := _unsafe(name, call)) and (where, name) not in ALLOWED_RAW
    ]
    assert not bad, "a squire without a redactor sends secrets out:\n" + "\n".join(bad)


def test_every_allowed_raw_squire_still_exists() -> None:
    present = {(where, name) for where, _, name, call in _calls() if _unsafe(name, call)}
    assert not ALLOWED_RAW - present, f"stale entries: {sorted(ALLOWED_RAW - present)}"


def test_the_scan_catches_what_it_is_for() -> None:
    def call(source: str) -> ast.Call:
        node = ast.parse(source).body[0].value  # type: ignore[attr-defined]
        assert isinstance(node, ast.Call)
        return node

    assert _unsafe("squire_from_env", call("squire_from_env(env)")) == "no redact="
    assert _unsafe("squire_from_env", call("squire_from_env(redact=False)")) == "redact=False"
    assert _unsafe("Squire", call("Squire(d, redact=None)")) == "redact=None"
    assert _unsafe("Squire", call("Squire(d, redact=redact_secrets)")) is None
    assert _unsafe("squire_from_env", call("squire_from_env(redact=True)")) is None
