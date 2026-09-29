"""The compaction side of the autopilot: the mask arm, the experimental tournament arm, memory
formation, `install --autopilot` and the plugin's auto trigger. No network."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from sanchopanza import Squire
from sanchopanza.cli import main
from sanchopanza.context import compact
from sanchopanza.context.formation import form
from sanchopanza.context.transcript import blocks_of
from sanchopanza.harness import install
from sanchopanza.harness.generic import HarnessConfig
from tests.context_helpers import BrokenDecider, ScriptedDecider

BIG = "line of output\n" * 60


def _session(turns: int) -> list[dict]:
    messages = [{"role": "user", "content": [{"type": "text", "text": "Refactor the module"}]}]
    for i in range(turns):
        messages.append(
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": f"step {i}"},
                    {
                        "type": "tool_use",
                        "id": f"t{i}",
                        "name": "Bash",
                        "input": {"command": f"c{i}"},
                    },
                ],
            }
        )
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": f"t{i}", "content": BIG + str(i)}
                ],
            }
        )
    return messages


def _pairs_intact(messages: list[dict]) -> bool:
    uses = {b["id"] for m in messages for b in blocks_of(m) if b.get("type") == "tool_use"}
    results = {
        b["tool_use_id"] for m in messages for b in blocks_of(m) if b.get("type") == "tool_result"
    }
    return uses == results


async def test_mask_stubs_everything_outside_the_last_turns_and_asks_nothing(tmp_path):
    messages = _session(20)
    decider = ScriptedDecider(lambda *a: 0.9)
    plan = await compact.plan(Squire(decider), messages, arm="mask", keep_recent=4, mask_turns=5)
    actions = {s.id: s.action for s in plan.steps}
    assert decider.calls == [] and plan.decisions == 0
    assert all(actions[f"t{i}"] == "stub" for i in range(15))
    assert all(actions[f"t{i}"] == "keep" for i in range(15, 20))
    pruned = compact.apply(messages, plan, tmp_path)
    assert len(pruned) == len(messages) and _pairs_intact(pruned)
    stub = pruned[2]["content"][0]["content"]
    path = Path(stub.split("saved at ")[1].split(";")[0])
    assert path.read_text(encoding="utf-8") == BIG + "0"
    meta = json.loads(path.with_name(path.stem + ".meta.json").read_text(encoding="utf-8"))
    assert meta == {**meta, "tool": "Bash", "about": "c0", "by": "compaction"}


async def test_mask_keeps_structural_invariants(tmp_path):
    messages = _session(3)
    messages[0]["content"].append({"type": "tool_use", "id": "first", "name": "Read", "input": {}})
    messages.insert(
        1,
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "first", "content": BIG}],
        },
    )
    plan = await compact.plan(Squire(), messages, arm="mask", keep_recent=0, mask_turns=0)
    reasons = {s.id: s.reason for s in plan.steps}
    assert reasons["first"] == "first_message"


async def test_the_tournament_arm_asks_everything_but_the_invariants(tmp_path):
    messages = _session(12)

    def answer(point, key, state):
        return 0.9 if key in ("C01", "C02") else 0.1

    decider = ScriptedDecider(answer)
    plan = await compact.plan(Squire(decider), messages, arm="tournament", keep_recent=4)
    assert {p for p, *_ in decider.calls} == {"context"}
    by = plan.by_id()
    assert by["t0"].action == "keep" and by["t1"].action == "keep"
    assert by["t5"].action == "stub" and by["t5"].reason == "not_needed"
    assert by["t11"].reason == "recent"
    assert _pairs_intact(compact.apply(messages, plan, tmp_path))


async def test_the_tournament_arm_keeps_everything_in_an_outage(tmp_path):
    plan = await compact.plan(Squire(BrokenDecider()), _session(8), arm="tournament")
    assert all(s.action == "keep" for s in plan.steps)


# --- memory formation ---------------------------------------------------------------------------


async def test_formation_writes_only_what_remember_stores(tmp_path):
    messages = _session(4)
    stubbed = {f"t{i}": tmp_path / f"t{i}.txt" for i in range(4)}

    def answer(point, key, state):
        if point == "injection":
            return 0.01
        if point == "memory_write":
            durable = "c3" in json.dumps(state)
            return {"durable": 0.9 if durable else 0.1, "specific": 0.9, "derivable": 0.1}.get(key)
        return None

    squire = Squire(ScriptedDecider(answer))
    records = await form(squire, messages, stubbed, tmp_path / "memory", max_items=3)
    assert [r["id"] for r in records] == ["t3", "t2", "t1"]  # newest first, capped
    stored = [r for r in records if r["stored"]]
    assert [r["id"] for r in stored] == ["t3"]
    text = Path(stored[0]["file"]).read_text(encoding="utf-8")
    assert text.startswith("---\nname: Bash c3\n") and "type: reference" in text
    assert "Stored by sanchopanza at compaction" in text and str(stubbed["t3"]) in text


async def test_formation_stores_nothing_in_an_outage(tmp_path):
    records = await form(
        Squire(BrokenDecider()), _session(2), {"t0": tmp_path / "t0.txt"}, tmp_path / "memory"
    )
    assert records and not any(r["stored"] for r in records)
    assert not (tmp_path / "memory").exists()


def test_cli_mask_arm_and_formation_off_by_default(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SANCHOPANZA_MEMORY_FORMATION", raising=False)
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps({"session": "s", "messages": _session(16)})))
    code = main(["compact", "--stdin", "--arm", "mask", "--provider", "null", "--keep-recent", "2"])
    assert code == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["report"]["actions"]["stub"] >= 5
    assert any((tmp_path / ".sanchopanza" / "archive" / "s").glob("*.txt"))
    assert "memory formation" not in captured.err


class _Stdin:
    def __init__(self, text: str) -> None:
        self.buffer = _Buffer(text.encode("utf-8"))


class _Buffer:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


# --- install --autopilot --------------------------------------------------------------------------


def test_install_autopilot_wires_everything_and_is_idempotent(tmp_path, capsys):
    settings = tmp_path / "settings.json"
    plugin = tmp_path / "plugin"
    args = [
        "install",
        "--autopilot",
        "--path",
        str(settings),
        "--plugin-dir",
        str(plugin),
        "--write",
    ]
    assert main(args) == 0
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["hooks"]["PostToolUse"][0]["matcher"] == "*"
    assert data["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"] == "sanchopanza hook"
    assert data["env"]["SANCHOPANZA_AUTOPILOT"] == "1"
    assert data["env"]["SANCHOPANZA_COMPACT_COMMAND"].endswith("--arm mask")
    assert data["env"]["SANCHOPANZA_COMPACT_AT_PERCENT"] == "60"
    assert data["env"]["CLAUDE_CODE_ENABLE_FUNCTION_HOOKS"] == "1"
    assert data["enabledPlugins"][install.PLUGIN_KEY] is True
    assert (plugin / "hooks" / install.HOOK_MODULE).exists()
    capsys.readouterr()
    assert main(args) == 0
    assert "already wired" in capsys.readouterr().out
    assert json.loads(settings.read_text(encoding="utf-8")) == data


def test_install_autopilot_keeps_the_owners_percentage(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"env": {"SANCHOPANZA_COMPACT_AT_PERCENT": "75"}}), "utf-8")
    plan = install.plan(settings, HarnessConfig(), compact_root=tmp_path, autopilot=True)
    assert plan.merged["env"]["SANCHOPANZA_COMPACT_AT_PERCENT"] == "75"


def test_install_without_autopilot_removes_its_pieces(tmp_path):
    settings = tmp_path / "settings.json"
    plugin = tmp_path / "plugin"
    main(
        ["install", "--autopilot", "--path", str(settings), "--plugin-dir", str(plugin), "--write"]
    )
    main(["install", "--path", str(settings), "--write"])
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "UserPromptSubmit" not in data["hooks"] or not data["hooks"]["UserPromptSubmit"]
    assert not any(k in data["env"] for k in install.AUTOPILOT_ENV)
    assert install.PLUGIN_KEY not in data.get("enabledPlugins", {})
    assert data["hooks"]["PostToolUse"][0]["matcher"] != "*"


def test_autopilot_without_a_plugin_root_is_refused(tmp_path):
    with pytest.raises(ValueError):
        install.plan(tmp_path / "s.json", HarnessConfig(), autopilot=True)


# --- the plugin's auto trigger, run under node -------------------------------------------

DRIVER = r"""
import { register, shouldCompact, threshold } from './compact_hook.ts';
const out = {};
out.threshold = [threshold(undefined), threshold('60'), threshold('abc'), threshold('150')];
out.should = [
  shouldCompact({}, 61, 60), shouldCompact({}, 59, 60),
  shouldCompact({ agentId: 'a' }, 90, 60), shouldCompact({ reason: 'aborted' }, 90, 60),
  shouldCompact({}, undefined, 60), shouldCompact({}, 99, 0),
];
const handlers = {};
register((name, fn) => { handlers[name] = fn; });
let compacted = 0;
const host = (percent, at) => ({
  env: { get: async (n) => (n === 'SANCHOPANZA_COMPACT_AT_PERCENT' ? at : undefined) },
  fs: { read: async () => '', write: async () => {} },
  process: { run: async () => ({ exitCode: 1, stdout: '', stderr: '' }) },
  session: {
    id: async () => 's',
    usage: async () => ({ context: { percent } }),
    compact: async () => { compacted += 1; },
  },
  ui: { log: () => {} },
});
const next = async (e) => ({ text: 'next' });
await handlers['turn.complete'](host(70, '60'), {}, next);
await handlers['turn.complete'](host(40, '60'), {}, next);
await handlers['turn.complete'](host(70, undefined), {}, next);
await handlers['turn.complete'](host(70, '60'), { agentId: 'sub' }, next);
out.compacted = compacted;
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_plugin_compacts_by_itself_at_the_threshold(tmp_path):
    source = Path(__file__).parents[1] / "src" / "sanchopanza" / "harness" / install.HOOK_MODULE
    shutil.copy(source, tmp_path / install.HOOK_MODULE)
    (tmp_path / "driver.mts").write_text(DRIVER, encoding="utf-8")
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    run = subprocess.run(
        ["node", "--experimental-strip-types", "--no-warnings", "driver.mts"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if run.returncode != 0 and "strip-types" in run.stderr:
        pytest.skip("this node cannot strip TypeScript types")
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["threshold"] == [0, 60, 0, 0]
    assert out["should"] == [True, False, False, False, False, False]
    assert out["compacted"] == 1


HANDLE_DRIVER = r"""
import { fromApi, toApi } from './compact_hook.ts';
const input = [
  { role: 'user', text: 'task', toolUses: [], handle: 'h0', extra: 1 },
  { role: 'assistant', text: '', toolUses: [{ tool_use_id: 't1', tool: 'Read', input: {} }], handle: 'h1' },
  { role: 'user', text: '', toolUses: [], toolResults: [{ tool_use_id: 't1', text: 'long', isError: false }], handle: 'h2' },
];
const api = toApi(input);
api[2].content[0].content = '[stub]';
const out = fromApi(api, input);
console.log(JSON.stringify({ handles: out.map((m) => m.handle ?? null), extra: out[0].extra,
  same: out[0] === input[0], stub: out[2].toolResults[0].text }));
"""  # noqa: E501


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_returned_messages_never_carry_the_engine_handle(tmp_path):
    """A returned `handle` makes Claude Code chain what it writes after the compaction to the old
    transcript entry, so `--resume` rebuilds the unmasked history (found end to end,
    docs/results/2026-09-28-context-lean/probe). Unchanged messages keep every other field."""
    source = Path(__file__).parents[1] / "src" / "sanchopanza" / "harness" / install.HOOK_MODULE
    shutil.copy(source, tmp_path / install.HOOK_MODULE)
    (tmp_path / "driver.mts").write_text(HANDLE_DRIVER, encoding="utf-8")
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    run = subprocess.run(
        ["node", "--experimental-strip-types", "--no-warnings", "driver.mts"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if run.returncode != 0 and "strip-types" in run.stderr:
        pytest.skip("this node cannot strip TypeScript types")
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out == {"handles": [None, None, None], "extra": 1, "same": False, "stub": "[stub]"}


def test_every_host_capability_in_the_hook_module_is_called_never_read():
    """Claude Code's function-hook compiler refuses a module that reads `$.noun.event` as a value
    (e.g. `if (!$.session.usage)`): the plugin silently never loads, and a debug-log line is the
    only trace (found end to end). Every `$.a.b` must be followed by a call."""
    import re
    from pathlib import Path

    source = Path(__file__).parents[1] / "src" / "sanchopanza" / "harness" / "compact_hook.ts"
    code = "\n".join(
        line
        for line in source.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith(("*", "//", "/*"))
    )
    uses = re.findall(r"\$\.[A-Za-z_]+\.[A-Za-z_]+(!?)(\s*\(?)", code)
    assert uses, "the module no longer uses the host API: update this test"
    assert all(call.strip() == "(" for _, call in uses), uses
