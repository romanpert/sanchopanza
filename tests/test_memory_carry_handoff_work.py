"""What the F2 agent sees, and a whole arm against a stand-in claude (no paid call).

The give-away test builds every arm of every scene as the runner does (S's install included)
and reads every path and file under the work root the agent works in: no scene name, arm name,
model name, name of the lot, or word that would give away the scene's C, D or step 2 (the scene
test's TELLS) appears, once the two paths every S install necessarily shows are set aside (this
checkout, whose sealed worktree's own name the launcher keeps neutral, and the Python that runs
the hooks)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from .helpers import bench_module
from .test_memory_carry_handoff import TELLS

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "memory_carry"
night = bench_module(BENCH, "handoff_night")
handoff = night.handoff
carry = handoff.carry

LOT_WORDS = ("handoff", "f2", "sonnet", "opus", "memory-f2", "claude-sonnet", "claude-opus")
ARM_TOKEN = re.compile(r"(?<![A-Za-z0-9])(N0|H|S)(?![A-Za-z0-9])")


def neutral(text: str) -> str:
    for path in (ROOT, Path(sys.executable).parent.parent):
        for form in (str(path), path.as_posix(), json.dumps(str(path))[1:-1]):
            text = text.replace(form, "<set aside>")
    return text


@pytest.mark.parametrize("name", sorted(handoff.HANDOFF))
def test_nothing_the_agent_sees_names_the_scene_the_arm_or_the_lot(
    name: str, tmp_path: Path
) -> None:
    work_root = tmp_path / "r2"
    for t, arm in enumerate(handoff.ARMS):
        work = work_root / handoff.folder_name("f2-sonnet", t, arm)
        handoff.arm_run(tmp_path / "lot", work, name, "sonnet", arm, 1, work_root / "typesafe.key",
                        dry=True)  # fmt: skip
    words = [*handoff.HANDOFF, *LOT_WORDS]
    for path in work_root.rglob("*"):
        if ".git" in path.relative_to(work_root).parts:  # git's own hashes and samples
            continue
        rel = path.relative_to(work_root).as_posix()
        assert not [w for w in words if w in rel.lower()], rel
        assert not [w for w in TELLS[name] if w in rel.lower()], rel
        assert not ARM_TOKEN.search(rel.replace("/", " ")), rel
        if path.is_file() and ".git" not in path.relative_to(work_root).parts:
            text = neutral(path.read_text(encoding="utf-8", errors="replace")).lower()
            assert not [w for w in words if w in text], rel
            installed = ("/repo/.claude/", "/repo/.mcp.json")  # sanchopanza's own generic files
            if not any(part in f"/{rel}" for part in installed):
                assert not [w for w in TELLS[name] if w in text], rel


def test_s_install_files_are_set_aside_from_the_agent_s_folder(tmp_path: Path) -> None:
    work = tmp_path / "r2" / handoff.folder_name("f2-sonnet", 0, "S")
    handoff.arm_run(tmp_path / "lot", work, "h_batch", "sonnet", "S", 1, tmp_path / "k", True)
    assert not (work / "install.txt").exists() and not (work / "install").exists()
    rec = tmp_path / "lot" / "arms" / work.name
    assert (rec / "install.txt").exists() and (rec / "install" / "rewired").is_dir()


# ---- a whole H arm against a stand-in claude ---------------------------------------------------

STEP1 = """def label_for(order):
    return {'to': order['name'], 'address': order['address'],
            'weight_kg': round(order['weight_g'] / 1000, 2)}
"""
STEP2 = """

def ship_all(orders, carrier):
    paid = [label_for(o) for o in orders if o['paid']]
    out = []
    for i in range(0, len(paid), 50):
        out += carrier.create_labels(paid[i:i + 50])
    return out
"""
FAKE = r"""
import json, os, pathlib, sys
prompt, resume = sys.argv[1], sys.argv[2]
here = pathlib.Path(__file__).parent
log = pathlib.Path(os.environ["FAKE_LOG"])
calls = json.loads(log.read_text()) if log.exists() else []
log.write_text(json.dumps(calls + [{"prompt": prompt, "resume": resume,
                                    "pythonpath": os.environ.get("PYTHONPATH")}]))
sid = resume or f"sid-{len(calls)}"
size = 40000 if resume else 20000
step1, step2 = (here / "step1.txt").read_text(), (here / "step2.txt").read_text()
if not resume:
    code = step1 if "Step 1" in prompt else step1 + step2
    pathlib.Path("app/labels.py").write_text(code)
    project = pathlib.Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "p"
    project.mkdir(parents=True, exist_ok=True)
    meta = {"type": "user", "isMeta": True, "message": {"content": "caveat"}}
    pasted = prompt + os.environ.get("FAKE_ALTER", "")
    user = {"type": "user", "message": {"role": "user", "content": pasted}}
    (project / f"{sid}.jsonl").write_text(json.dumps(meta) + "\n" + json.dumps(user) + "\n")
text = "HANDOFF: ship_all with create_labels, at most 50 per call." if resume else "done"
secret = os.environ.get("FAKE_SECRET", "")
if secret:
    pathlib.Path("leak.txt").write_text(secret)
    text = text + " " + secret
init = {"type": "system", "subtype": "init", "session_id": sid,
        "model": "claude-sonnet-5-5", "claude_code_version": "2.1.287"}
usage = {"input_tokens": 10, "cache_read_input_tokens": size}
said = {"type": "assistant", "message": {"content": [], "usage": usage}}
result = {"type": "result", "subtype": "success", "total_cost_usd": 0.05, "num_turns": 2,
          "result": text, "usage": {**usage, "output_tokens": 20,
                                    "cache_creation_input_tokens": 5}}
for e in (init, said, result):
    print(json.dumps(e))
"""


def test_a_whole_h_arm_resumes_pastes_the_handoff_and_checks(tmp_path: Path,
                                                             monkeypatch: Any) -> None:  # fmt: skip
    fake = tmp_path / "fake_claude.py"
    fake.write_text(FAKE)
    (tmp_path / "step1.txt").write_text(STEP1)
    (tmp_path / "step2.txt").write_text(STEP2)
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.json"))
    monkeypatch.setenv("PYTHONPATH", "C:/somewhere/src")
    monkeypatch.setenv(carry.TOKEN, "tok-test-123")
    monkeypatch.setattr(handoff, "command", lambda prompt, model, resume=None:
                        [sys.executable, str(fake), prompt, resume or ""])  # fmt: skip
    lot, work = tmp_path / "lot", tmp_path / "w" / "t00-b"
    got = handoff.arm_run(lot, work, "h_batch", "sonnet", "H", 0, tmp_path / "k", False)
    calls = json.loads((tmp_path / "calls.json").read_text())
    assert [c["resume"] for c in calls] == ["", "sid-0", ""]
    assert {c["pythonpath"] for c in calls} == {None}
    assert calls[1]["prompt"] == handoff.HANDOFF_REQUEST
    assert calls[2]["prompt"].startswith("HANDOFF:")
    assert (lot / "arms" / "t00-b" / "handoff.txt").read_text().startswith("HANDOFF:")
    assert not list(work.glob("*.jsonl")) and not (work / "handoff.txt").exists()
    assert not got.get("cut") and got["kept_all"] and got["intact_pass"]
    assert got["pasted_verbatim"] is True and got["folder"] == str(work)
    assert got["handoff"]["context_carried"] and got["handoff"]["names"] == {"C": True, "D": True}
    assert got["cost"] == pytest.approx(0.15) and got["tokens"]["output"] == 60
    n0 = handoff.arm_run(lot, tmp_path / "w" / "t00-a", "h_batch", "sonnet", "N0", 0,
                         tmp_path / "k", False)  # fmt: skip
    assert n0["kept_all"] and n0["cost"] == pytest.approx(0.10) and "pasted_verbatim" not in n0


def test_a_pasted_text_that_differs_is_recorded(tmp_path: Path) -> None:
    config = tmp_path / "cfg"
    (config / "projects" / "p").mkdir(parents=True)
    line = {"type": "user", "message": {"content": [{"type": "text", "text": "abc "}]}}
    (config / "projects" / "p" / "s1.jsonl").write_text(json.dumps(line) + "\n")
    assert handoff.hc.first_prompt_in_transcript(config, "s1") == "abc "
    assert handoff.hc.first_prompt_in_transcript(config, "s2") is None


def stand_in(tmp_path: Path, monkeypatch: Any, **env: str) -> None:
    fake = tmp_path / "fake_claude.py"
    fake.write_text(FAKE)
    (tmp_path / "step1.txt").write_text(STEP1)
    (tmp_path / "step2.txt").write_text(STEP2)
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.json"))
    monkeypatch.setenv(carry.TOKEN, "tok-test-123")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(handoff, "command", lambda prompt, model, resume=None:
                        [sys.executable, str(fake), prompt, resume or ""])  # fmt: skip


def test_a_paste_that_differs_cuts_the_h_arm(tmp_path: Path, monkeypatch: Any) -> None:
    stand_in(tmp_path, monkeypatch, FAKE_ALTER=" ")
    got = handoff.arm_run(tmp_path / "lot", tmp_path / "w" / "t00-c", "h_batch", "sonnet", "H", 1,
                          tmp_path / "k", False)  # fmt: skip
    assert got["pasted_verbatim"] is False
    assert got["cut"] == "handoff: session 2's first prompt differs from handoff.txt"
    assert "kept_all" not in got


def test_the_typesafe_key_is_scrubbed_and_redacted(tmp_path: Path, monkeypatch: Any) -> None:
    secret = "ts-key-0123456789-secret"
    stand_in(tmp_path, monkeypatch, FAKE_SECRET=secret)
    keyfile = tmp_path / "r2" / "typesafe.key"
    keyfile.parent.mkdir()
    keyfile.write_text(secret)
    lot, work = tmp_path / "lot", tmp_path / "r2" / "t00-a"
    got = handoff.arm_run(lot, work, "h_batch", "sonnet", "N0", 1, keyfile, False)
    assert secret not in json.dumps(got) and got.get("token_scrubbed")
    for folder in (work, lot / "arms" / "t00-a"):
        for path in folder.rglob("*"):
            if path.is_file() and ".git" not in path.parts:
                assert secret.encode() not in path.read_bytes(), path
