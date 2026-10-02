"""Amendment 5 of the adoption confirmation: the held-out S arms run with the decider the
pre-registration names. Phase A's frozen copy was installed without the `jev` extra, so no
`httpx`, so every hook built the null decider and said so only on a stderr `hook_env` swallowed.
These tests hold the fix: the frozen copy carries the extra, a held-out run refuses to start when
the S arms' hooks would not build Jev, every runner has its own key file, a hook's stderr is
kept, and the verdict code does not read an arm without the decider as treated.
No Docker, no network, no model."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

ADOPT = pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "adopt"
sys.path.append(str(ADOPT))


def _load(name: str, file: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ADOPT / file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _purge() -> None:
    """Drop the bench's modules registered under bare names: other benchmarks have modules of
    the same names and would import these instead."""
    for name, module in list(sys.modules.items()):
        where = getattr(module, "__file__", None) or ""
        if not name.startswith("adopt_") and pathlib.Path(where).parent == ADOPT:
            del sys.modules[name]


run = _load("adopt_run_decider", "run.py")
confirm = _load("adopt_confirm_decider", "confirm.py")
freeze = _load("adopt_freeze_decider", "freeze.py")
hook_env = _load("adopt_hook_env_decider", "hook_env.py")
_purge()

HAIKU = confirm.PHASE_MODEL["A"]


# ---- freeze.py -----------------------------------------------------------------------------------


def test_the_frozen_copy_is_installed_with_the_jev_extra(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):  # noqa: ANN001, ANN003, ANN202
        calls.append([str(a) for a in argv])
        out = b"" if kwargs.get("text") is None else "0.3.0"
        return SimpleNamespace(stdout=out, returncode=0)

    monkeypatch.setattr(freeze, "ROOT", tmp_path)
    monkeypatch.setattr(freeze, "git", lambda *a: "e" * 40)
    monkeypatch.setattr(freeze.venv, "create", lambda *a, **k: None)
    monkeypatch.setattr(freeze.subprocess, "run", fake_run)
    exe = freeze.freeze("eebdfa6")
    pip = next(c for c in calls if "pip" in c)
    assert pip[-1].endswith("[jev,mcp]")
    assert exe.parents[1].name == "e" * 12 + "-jev-mcp"  # never the copy phase A ran
    stamp = json.loads((exe.parents[1] / "stamp.json").read_text(encoding="utf-8"))
    assert stamp["extras"] == ["jev", "mcp"]


# ---- run.py --------------------------------------------------------------------------------------


def _frozen(monkeypatch: pytest.MonkeyPatch, extras: list[str], probe: str) -> None:
    monkeypatch.setattr(run, "frozen_stamp", lambda: {"commit": run.HELD_COMMIT, "extras": extras})
    monkeypatch.setattr(run, "decider_probe", lambda keyfile: probe)


def test_a_held_out_run_refuses_a_frozen_copy_without_the_decider(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    key = tmp_path / "k"
    _frozen(monkeypatch, ["jev", "mcp"], "JevDecider")
    assert run.decider_refusal(key) is None
    _frozen(monkeypatch, [], "JevDecider")  # phase A's copy: no extra recorded
    assert "jev" in run.decider_refusal(key)
    _frozen(monkeypatch, ["jev"], "JevDecider")  # find_in_repo's server cannot start
    assert "mcp" in run.decider_refusal(key)
    _frozen(monkeypatch, ["jev", "mcp"], "NullDecider")
    assert "NullDecider" in run.decider_refusal(key)


def test_the_probe_asks_the_frozen_copy_with_the_hooks_environment(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    key = tmp_path / "typesafe.key"
    key.write_text("secret", encoding="utf-8")
    seen: dict = {}

    package = tmp_path / "frozen" / "Lib" / "site-packages" / "sanchopanza" / "__init__.py"
    answer = {"where": package}

    def fake_run(argv, **kwargs):  # noqa: ANN001, ANN003, ANN202
        seen["argv"], seen["env"] = argv, kwargs["env"]
        return SimpleNamespace(stdout=f"{answer['where']}\nJevDecider\n", stderr="", returncode=0)

    monkeypatch.setattr(run, "SANCHO", tmp_path / "frozen" / "Scripts" / "sanchopanza.exe")
    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setenv("SANCHOPANZA_PROVIDER", "null")  # the runner's own, never the hooks'
    assert run.decider_probe(key) == "JevDecider"
    assert pathlib.Path(seen["argv"][0]).parent == tmp_path / "frozen" / "Scripts"
    assert seen["env"]["TYPESAFE_API_KEY"] == "secret"
    assert "SANCHOPANZA_PROVIDER" not in seen["env"]  # child_env drops it, as for Claude Code
    assert "decider_from_env" in seen["argv"][-1]
    answer["where"] = tmp_path / "src" / "sanchopanza" / "__init__.py"  # a PYTHONPATH answered
    assert run.decider_probe(key) != "JevDecider"


def test_a_probe_that_fails_names_why(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    def failing(argv, **kwargs):  # noqa: ANN001, ANN003, ANN202
        return SimpleNamespace(stdout="", stderr="ModuleNotFoundError: sanchopanza", returncode=1)

    monkeypatch.setattr(run.subprocess, "run", failing)
    assert "ModuleNotFoundError" in run.decider_probe(tmp_path / "k")


def test_each_runner_writes_its_own_key_file(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.setenv("TYPESAFE_API_KEY", "secret")
    path = run.keyfile_from_indagis()
    assert path.parent == tmp_path
    assert path.name != "typesafe.key"  # shared, any runner's `finally` took it from the others
    assert str(run.os.getpid()) in path.name
    assert path.read_text(encoding="utf-8") == "secret"


def test_an_arms_key_path_survives_its_runner(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    """A `--continue` by a later runner reuses the hooks `install` wrote, which name the key's
    path: that path is the arm's, written again by whichever runner starts or resumes it."""
    monkeypatch.setattr(run, "KEYS", tmp_path / "keys")
    first, later = tmp_path / "typesafe-1.key", tmp_path / "typesafe-2.key"
    first.write_text("secret", encoding="utf-8")
    path = run.arm_keyfile(first, "pydantic__pydantic-1", "Sm")
    run.drop_arm_keys()
    assert not path.exists()  # the first runner's end takes it
    later.write_text("secret", encoding="utf-8")
    again = run.arm_keyfile(later, "pydantic__pydantic-1", "Sm")
    assert again == path and again.read_text(encoding="utf-8") == "secret"
    run.drop_arm_keys()


def test_a_held_out_arm_does_not_start_when_its_hooks_lack_the_decider(tmp_path, monkeypatch) -> None:  # noqa: ANN001, E501
    monkeypatch.setattr(run, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(run, "WORK", tmp_path / "work")
    monkeypatch.setattr(run, "KEYS", tmp_path / "keys")
    monkeypatch.setattr(run, "CLAUDE_PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(run, "decider_probe", lambda keyfile: "NullDecider")
    chain = {"chain": "c", "split": "held", "tag": "t", "bugs": []}
    with pytest.raises(RuntimeError, match="NullDecider"):
        run.one_chain(chain, "Sm", "m", 1.0, tmp_path / "key")
    assert not (tmp_path / "runs" / "c").exists()
    run.drop_arm_keys()


# ---- hook_env.py ---------------------------------------------------------------------------------


def test_a_hooks_stderr_is_kept_in_its_log(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    warning = b"sanchopanza: provider 'jev' unavailable (install sanchopanza[jev]); no decider\n"

    def fake_run(argv, **kwargs):  # noqa: ANN001, ANN003, ANN202
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=warning)

    monkeypatch.setattr(hook_env.subprocess, "run", fake_run)
    payload = json.dumps({"hook_event_name": "UserPromptSubmit"}).encode()
    monkeypatch.setattr(hook_env.sys, "stdin", SimpleNamespace(buffer=SimpleNamespace(
        read=lambda: payload)))  # fmt: skip
    out = SimpleNamespace(write=lambda b: None)
    monkeypatch.setattr(hook_env.sys, "stdout", SimpleNamespace(buffer=out))
    monkeypatch.setattr(hook_env.sys, "stderr", SimpleNamespace(buffer=out))
    assert hook_env.main([str(tmp_path), str(tmp_path / "k"), "memory-hook"]) == 0
    row = json.loads((tmp_path / "hooks.jsonl").read_text(encoding="utf-8"))
    assert "no decider" in row["stderr"]
    assert row["key"] is False  # no key file: said on every line


def test_an_mcp_server_start_is_logged_with_its_key(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    (tmp_path / "k").write_text("secret", encoding="utf-8")
    monkeypatch.setattr(hook_env.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    assert hook_env.main([str(tmp_path), str(tmp_path / "k"), "find-mcp"]) == 0
    lines = (tmp_path / "hooks.jsonl").read_text(encoding="utf-8").splitlines()
    start, end = (json.loads(x) for x in lines)
    assert start == {"sub": "find-mcp", "event": "server start", "key": True}
    assert end == {"sub": "find-mcp", "event": "server end", "key": True, "exit": 0}


# ---- confirm.py ----------------------------------------------------------------------------------


def _arm(
    folder: pathlib.Path,
    extras: list[str] | None = ("jev", "mcp"),  # type: ignore[assignment]
    providers: tuple[str, ...] = ("jev",),
    probes: tuple[str, ...] = ("JevDecider",),
    keys: tuple[bool, ...] = (True,),
    errors: int = 0,
    servers: tuple[str, ...] = ("connected",),
) -> pathlib.Path:
    folder.mkdir(parents=True, exist_ok=True)
    for k, status in enumerate(servers, start=1):  # each request's init line
        init = {"type": "system", "subtype": "init",
                "mcp_servers": [{"name": "sanchopanza", "status": status}]}  # fmt: skip
        (folder / f"stream-{k}.jsonl").write_text(json.dumps(init) + "\n", encoding="utf-8")
    frozen = {"commit": "abc", **({"extras": list(extras)} if extras is not None else {})}
    row = {
        "model": HAIKU,
        "jev_usd": 0.0,
        "sanchopanza": {"exe": "x", "frozen": frozen},
        "calls": [{"request": 1, "subtype": "success", "exit": 0, "cost_usd": 0.5}],
        **({"decider": list(probes)} if probes else {}),
    }
    (folder / "row.json").write_text(json.dumps(row), encoding="utf-8")
    grade = {"resolved": 1, "bugs": [{"instance_id": "b", "resolved": True}]}
    (folder / "grade.json").write_text(json.dumps(grade), encoding="utf-8")
    lines = [{"kind": "decision", "data": {"point": "guard", "provider": p,
                                           "error": "HTTP 401" if i < errors else None}}
             for i, p in enumerate(providers)]  # fmt: skip
    (folder / "journal.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines),
                                          encoding="utf-8")  # fmt: skip
    hooks = [{"sub": "hook", "key": k} for k in keys]
    (folder / "hooks.jsonl").write_text("".join(json.dumps(x) + "\n" for x in hooks) + "[1]\n",
                                        encoding="utf-8")  # fmt: skip  (a junk line is skipped)
    return folder


def _counts(folder: pathlib.Path) -> bool:
    return confirm.arm_result(folder, HAIKU, "abc") is not None


def test_a_sanchopanza_arm_counts_only_with_the_decider_shown(tmp_path: pathlib.Path) -> None:
    assert _counts(_arm(tmp_path / "a" / "Sm", providers=("jev", "jev", "budget")))
    # the guard's own deny list journals as "code" (seen in the smoke test of 2026-10-02)
    assert _counts(_arm(tmp_path / "a2" / "Sm", providers=("code", "jev")))
    assert _counts(_arm(tmp_path / "b" / "Sm", providers=()))  # no decision, but shown wired
    # phase A as it ran: no extra, every decision on the null decider
    assert not _counts(_arm(tmp_path / "c" / "Sm", extras=None, providers=("null",)))
    # the extra installed, yet a decision that fell to the null decider
    assert not _counts(_arm(tmp_path / "d" / "Sf", providers=("jev", "null")))
    # no decision journalled and nothing showing the decider: not the treatment
    assert not _counts(_arm(tmp_path / "e" / "Sm", providers=(), probes=()))
    assert not _counts(_arm(tmp_path / "f" / "Sm", probes=("JevDecider", "NullDecider")))
    assert not _counts(_arm(tmp_path / "g" / "Sm", keys=(True, False)))  # a hook with no key
    assert not _counts(_arm(tmp_path / "h" / "Sm", keys=()))
    # phase A as it ran: find_in_repo's server failed in every request (no mcp in the copy)
    assert not _counts(_arm(tmp_path / "h2" / "Sm", servers=("failed",)))
    assert not _counts(_arm(tmp_path / "h3" / "Sm", servers=()))  # no init line to show it
    control = _arm(tmp_path / "i" / "N", extras=None, providers=(), probes=(), keys=(),
                   servers=())  # fmt: skip
    assert _counts(control)  # Claude Code alone


def test_decisions_jev_did_not_answer_are_bounded(tmp_path: pathlib.Path) -> None:
    ten = ("jev",) * 10
    assert _counts(_arm(tmp_path / "a" / "Sm", providers=ten, errors=1))
    assert not _counts(_arm(tmp_path / "b" / "Sm", providers=ten, errors=2))  # a revoked key
    # the hooks' cap answers "budget" with an error: the product as installed, not Jev failing
    capped = _arm(tmp_path / "c" / "Sm", providers=("budget", "budget", *ten), errors=2)
    assert _counts(capped)


def test_a_resumed_arm_installed_before_amendment_5_is_refused(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    """Its hooks name a key path no runner writes any more: the probe would pass on the arm's
    path while every resumed call ran keyless (the review of fff04b6)."""
    monkeypatch.setattr(run, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(run, "WORK", tmp_path / "work")
    monkeypatch.setattr(run, "KEYS", tmp_path / "keys")
    monkeypatch.setattr(run, "decider_probe", lambda keyfile: "JevDecider")
    evidence = tmp_path / "runs" / "c" / "Sm"
    evidence.mkdir(parents=True)
    calls = [{"request": 1, "status": "NOT RUN (cap)", "cost_usd": 0.0}]
    (evidence / "row.json").write_text(json.dumps({"calls": calls, "session": "s", "base": "b"}),
                                       encoding="utf-8")  # fmt: skip
    settings = tmp_path / "work" / "c-Sm" / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text('{"hooks": "... C:/old/typesafe.key hook"}', encoding="utf-8")
    chain = {"chain": "c", "split": "dev", "tag": "t", "bugs": [{"instance_id": "b"}]}
    with pytest.raises(RuntimeError, match="key"):
        run.one_chain(chain, "Sm", "m", 1.0, tmp_path / "key", carry_on=True)
    run.drop_arm_keys()
