"""The generated mini-repositories for the compaction-guard run. Deterministic, no data.

    python tasks.py build --out <dir>     # one folder per task, hidden tests beside them
    python tasks.py check --out <dir>     # free: hidden tests fail as generated and pass on the
                                          # reference; the one-shot tools work once

Built on the lean run's generator (`../2026-09-28-context-lean/tasks.py`, imported with its seed
replaced by this run's, so no task repeats one the guard's rules were looked at on). Each task
is that run's repository plus two one-shot facts and one standing rule:

| fact | where | can it be had again? |
|---|---|---|
| `token` | `tools/issue_token.py`, phase A: a release MANIFEST (48 artifact lines, each with its own random hash, so no line shape repeats) with the token line in the middle | no |
| `probe` | `tools/probe.py`, end of phase A: 36 channel lines, then the failing aggregate and `ProbeError: ... tolerance T (code PRB-n)` | no |
| `check` | `tools/build_report.py`, start of phase B: a 20-22 KB build log with one failing check | no |
| `rule` | phase A's prompt only: every exception message written in this repository must end with `[ref OPS-n]`; phase A writes no exception, phase B writes two | no (never in a file, never repeated) |
| `limit` | a constant in one module, one decoy (control) | yes |

The manifest is new on purpose: the token output of the earlier runs repeats one line shape 48
times, which is what the guard's rarity rule was written against
(docs/results/2026-09-29-context-guard/offline/replay.py). Here every artifact line has a unique
shape, so rarity cannot find the token line.
"""

# ruff: noqa: E501
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import shutil
import subprocess
import sys
import textwrap
from dataclasses import asdict, dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = "context-guard-2026-09-29"
N_TASKS = 10


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lean = _load("guard_lean_tasks", HERE.parent / "2026-09-28-context-lean" / "tasks.py")
lean.SEED = SEED  # this run's tasks, not the lean run's: facts_for reads the module global
e2e = lean.e2e


@dataclass(frozen=True)
class Facts:
    task: str
    domain: str
    token: str
    check_id: str
    check_expected: str
    check_got: str
    check_position: str
    check_line: int
    log_lines: int
    log_chars: int
    limit: int
    limit_home: str
    decoy: int | None
    decoy_home: str | None
    bug: str
    chain: tuple[str, ...]
    probe_code: str
    tolerance: str
    drift: str
    rule_ref: str


def facts_for(index: int):
    base, rng, seed_text, log = lean.facts_for(index)
    extra = random.Random(f"{SEED}-extra-{index}")
    tolerance = extra.randint(120, 480) / 10_000
    drift = tolerance + extra.randint(40, 300) / 10_000
    facts = Facts(
        **asdict(base), probe_code=f"PRB-{extra.randint(1000, 9999)}",
        tolerance=f"{tolerance:.4f}", drift=f"{drift:.4f}", rule_ref=f"OPS-{extra.randint(1000, 9999)}",
    )  # fmt: skip
    return facts, rng, seed_text, log, extra


CALIBRATION = '''"""Calibration guard for the channel probe."""

from __future__ import annotations


class CalibrationError(RuntimeError):
    pass


# Set to the drift tolerance tools/probe.py reported for this calibration.
DRIFT_TOLERANCE = None


def check_drift(drift):
    """Raise CalibrationError, with the probe's error code in the message, when `drift` exceeds
    DRIFT_TOLERANCE; return None otherwise."""
    raise NotImplementedError
'''


def manifest_script(rng: random.Random) -> str:
    rows = []
    for _ in range(48):
        name = rng.choice(("core", "api", "cli", "worker", "sdk", "web", "etl", "auth"))
        rows.append(
            f"artifact {name}-{rng.randint(1, 9)}.{rng.randint(0, 30)}.{rng.randint(0, 99)}.whl "
            f"sha256={rng.getrandbits(64):016x} size={rng.randint(10, 9999)}KB"
        )
    middle = rng.randint(18, 30)
    return textwrap.dedent(
        f'''\
        """Issue this release's token. It can be issued once: the seed is consumed."""

        import hashlib
        import pathlib
        import sys

        ALPHABET = {e2e.ALPHABET!r}
        ROWS = {rows!r}
        SEED = pathlib.Path(__file__).with_name(".token_seed")

        if not SEED.exists():
            print("error: the release token was already issued; tokens are issued once")
            sys.exit(2)
        digest = hashlib.sha256(SEED.read_text().strip().encode("ascii")).digest()
        token = "RT-" + "".join(ALPHABET[b % len(ALPHABET)] for b in digest[:10])
        SEED.unlink()
        print("release manifest")
        for index, row in enumerate(ROWS):
            if index == {middle}:
                print("release token: " + token)
            print(row)
        print("manifest complete: " + str(len(ROWS)) + " artifacts")
        '''
    )


def probe_facts(facts: Facts) -> object:
    """The e2e probe script reads `tolerance`, `drift` and `code` off its facts."""
    return e2e.Facts(**{**lean._e2e_blank(), "domain": facts.domain, "tolerance": facts.tolerance,
                        "drift": facts.drift, "code": facts.probe_code})  # fmt: skip


def hidden_tests(facts: Facts) -> str:
    tol = float(facts.tolerance)
    ref = f"[ref {facts.rule_ref}]"
    return lean.hidden_tests(facts) + textwrap.dedent(
        f"""

        from pkg import calibration


        def test_probe_tolerance():
            assert calibration.DRIFT_TOLERANCE == pytest.approx({tol!r})


        def test_probe_raises_with_code():
            with pytest.raises(calibration.CalibrationError, match={facts.probe_code!r}):
                calibration.check_drift({tol + 0.001!r})


        def test_probe_passes_below():
            assert calibration.check_drift({tol - 0.001!r}) is None


        def test_rule_build():
            with pytest.raises(buildcheck.BuildError) as info:
                buildcheck.check_build()
            assert str(info.value).rstrip().endswith({ref!r})


        def test_rule_calibration():
            with pytest.raises(calibration.CalibrationError) as info:
                calibration.check_drift({tol + 0.001!r})
            assert str(info.value).rstrip().endswith({ref!r})
        """
    )


FACT_TESTS = {
    **lean.FACT_TESTS,
    "probe": ("test_probe_tolerance", "test_probe_raises_with_code", "test_probe_passes_below"),
    "rule": ("test_rule_build", "test_rule_calibration"),
}


def readme(facts: Facts) -> str:
    return lean.readme(facts).replace(
        "2. `tools/build_report.py`",
        "2. `tools/probe.py` runs the calibration probe (once).\n3. `tools/build_report.py`",
    ).replace("3. `pkg/release.py`", "4. `pkg/release.py`, `pkg/calibration.py`")


def build_one(index: int, out: Path) -> Facts:
    facts, rng, seed_text, log, extra = facts_for(index)
    repo, hidden = out / "repos" / facts.task, out / "hidden" / facts.task
    for path in (repo, hidden):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
    files = lean.modules(facts, rng)
    files["pkg/calibration.py"] = CALIBRATION
    files["tests/test_basics.py"] = e2e.visible_tests(e2e.Facts(**{**lean._e2e_blank(), "domain": facts.domain}))
    files["tools/issue_token.py"] = manifest_script(extra)
    files["tools/.token_seed"] = seed_text + "\n"
    probe, state = e2e.probe_script(probe_facts(facts), extra)
    files["tools/probe.py"] = probe
    files["tools/.probe_state"] = state + "\n"
    script, build_state = lean.build_report_script(log, facts)
    files["tools/build_report.py"] = script
    files["tools/.build_state"] = build_state + "\n"
    files["README.md"] = readme(facts)
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    (hidden / "test_hidden.py").write_text(hidden_tests(facts), encoding="utf-8", newline="\n")
    return facts


def build(out: Path, n: int = N_TASKS) -> list[Facts]:
    all_facts = [build_one(i, out) for i in range(n)]
    (out / "facts.json").write_text(json.dumps([asdict(f) for f in all_facts], indent=1) + "\n",
                                    encoding="utf-8")  # fmt: skip
    return all_facts


def load_facts(out: Path) -> dict[str, dict]:
    return {f["task"]: f for f in json.loads((out / "facts.json").read_text("utf-8"))}


tree_digest = e2e.tree_digest


def solve(repo: Path, facts: Facts | dict) -> None:
    """The reference solution: the lean one, then the probe and the rule."""
    f = facts if isinstance(facts, dict) else asdict(facts)
    lean.solve(repo, f)
    ref = f"[ref {f['rule_ref']}]"
    build = repo / "pkg" / "buildcheck.py"
    text = build.read_text("utf-8")
    marker = "raise BuildError("
    at = text.index(marker)
    close = text.index("\n", at)
    line = text[at:close]
    body = line[len(marker):-1]
    build.write_text(text[:at] + f"{marker}{body} + ' {ref}')" + text[close:], "utf-8")
    calib = repo / "pkg" / "calibration.py"
    calib.write_text(
        calib.read_text("utf-8")
        .replace("DRIFT_TOLERANCE = None", f"DRIFT_TOLERANCE = {float(f['tolerance'])!r}")
        .replace(
            "    raise NotImplementedError",
            "    if drift > DRIFT_TOLERANCE:\n"
            f"        raise CalibrationError('drift ' + str(drift) + ' exceeds tolerance, code {f['probe_code']} {ref}')\n"
            "    return None",
        ),
        "utf-8",
    )


def run_tests(repo: Path, hidden: Path, python: str = sys.executable) -> dict:
    return lean.run_tests(repo, hidden, python)


def facts_passed(tests: dict[str, bool]) -> dict[str, bool]:
    """Per fact: every hidden test of it passed (keys are `hidden::<test>[param]`)."""
    out = {}
    for fact, names in FACT_TESTS.items():
        keys = [k for k in tests if k.startswith("hidden::") and k.split("::")[1].split("[")[0] in names]
        out[fact] = bool(keys) and all(tests[k] for k in keys)
    visible = [v for k, v in tests.items() if k.startswith("visible::")]
    out["visible"] = bool(visible) and all(visible)
    return out


def _run(tool: Path, cwd: Path) -> tuple[subprocess.CompletedProcess, subprocess.CompletedProcess]:
    first = subprocess.run([sys.executable, str(tool)], cwd=cwd, capture_output=True, text=True)
    second = subprocess.run([sys.executable, str(tool)], cwd=cwd, capture_output=True, text=True)
    return first, second


CUT = 5_000  # Claude Code 2.1.282 keeps this many characters at each end of a failing result


def harness_sees(proc: subprocess.CompletedProcess) -> str:
    """What the agent is shown of a shell result: a failing one longer than twice `CUT` loses its
    middle (found in this run: the failing check of the "middle" tasks never reached any arm)."""
    text = proc.stdout + proc.stderr
    if proc.returncode != 0 and len(text) > 2 * CUT:
        return text[:CUT] + text[-CUT:]
    return text


def check_one(out: Path, f: dict) -> dict:
    task = f["task"]
    work = out / "check" / task
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(out / "repos" / task, work)
    generated = run_tests(work, out / "hidden" / task)
    token1, token2 = _run(work / "tools" / "issue_token.py", work)
    probe1, probe2 = _run(work / "tools" / "probe.py", work)
    build1, build2 = _run(work / "tools" / "build_report.py", work)
    solved = out / "check" / f"{task}-solved"
    shutil.rmtree(solved, ignore_errors=True)
    shutil.copytree(out / "repos" / task, solved)
    solve(solved, f)
    reference = run_tests(solved, out / "hidden" / task)
    ok = {
        "hidden_fail_generated": not generated["passed"],
        "reference_passes": reference["passed"],
        "token_once": f["token"] in token1.stdout and token2.returncode != 0,
        "token_mid_manifest": "release token: " + f["token"] in token1.stdout,
        "probe_once": f["probe_code"] in probe1.stdout and probe2.returncode != 0,
        "check_once": f["check_id"] in build1.stdout and build2.returncode != 0,
        # amendment A2: the facts must survive the harness's own cut, or no arm can see them
        "token_deliverable": f["token"] in harness_sees(token1),
        "probe_deliverable": f["probe_code"] in harness_sees(probe1),
        "check_deliverable": f["check_id"] in harness_sees(build1) and f["check_expected"] in harness_sees(build1),
        "rule_absent_from_repo": f["rule_ref"] not in "".join(
            p.read_text("utf-8", "replace") for p in (out / "repos" / task).rglob("*") if p.is_file()
        ),
    }
    return {"task": task, "ok": ok, "passed": all(ok.values()), "reference": reference["tests"],
            "token_report_chars": len(token1.stdout), "probe_chars": len(probe1.stdout),
            "log_chars": len(build1.stdout)}  # fmt: skip


def check(out: Path) -> dict:
    return {f["task"]: check_one(out, f) for f in load_facts(out).values()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "check"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "build":
        build(args.out)
        print(tree_digest(args.out / "repos"))
        return 0
    table = check(args.out)
    print(json.dumps({t: {"passed": r["passed"], "failed": [k for k, v in r["ok"].items() if not v]}
                      for t, r in table.items()}, indent=1))  # fmt: skip
    return 0 if all(r["passed"] for r in table.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
