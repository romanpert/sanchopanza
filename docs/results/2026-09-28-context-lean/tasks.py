"""The generated mini-repositories for the lean-compaction run. Deterministic, no data.

    python tasks.py build --out <dir>     # one folder per task, hidden tests beside them
    python tasks.py check --out <dir>     # free: hidden tests fail as generated and pass on the
                                          # reference; the one-shot tools work once; sizes

Each task is a small Python package: 24 modules under `pkg/` in a *reading order* (README
names the first module, each module's first line names the next, so the agent reads them one
per call and cannot batch), a visible pytest suite with one seeded bug, two one-shot tools and
hidden tests kept outside the task folder. Three facts are planted:

- `token` (early): `tools/issue_token.py`, run in phase A, prints a ~2 KB inventory report with
  the release token in it and deletes its seed. The fact exists only in that output.
- `check` (large, mid-session): `tools/build_report.py`, run at the start of phase B, prints a
  20-22 KB build log (~300-400 lines) with exactly one line `CHECK <ID> failed: expected <v> got
  <v>`, early, in the middle or late depending on the task (`Facts.check_position`), and
  deletes its state. Above the 6,000-character arrival cut, and old enough to be masked by the
  time the context reaches the compaction threshold.
- `limit` (re-readable control): `BATCH_CEILING`, defined in one module, with at most one decoy
  (`SOFT_BATCH_CEILING`) in another. Phase B implements `admission.admit` with it.

Module sizes are set by `calibration()` (see `SIZES`); `check` prints the table. Parts of the
module bodies (the filler functions, the pricing bug, the visible tests, the token script,
`run_tests`) come from `../2026-09-28-context-e2e/tasks.py`, imported, not copied.
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


def _load_e2e():
    path = HERE.parent / "2026-09-28-context-e2e" / "tasks.py"
    spec = importlib.util.spec_from_file_location("e2e_tasks", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["e2e_tasks"] = module
    spec.loader.exec_module(module)
    return module


e2e = _load_e2e()

SEED = "context-lean-2026-09-29"
N_TASKS = 10
DOMAINS = e2e.DOMAINS[:N_TASKS]
POSITIONS = ("early", "middle", "late")
POSITION_RANGE = {"early": (0.06, 0.18), "middle": (0.45, 0.55), "late": (0.84, 0.95)}
A_CHAIN = ("models", "parsing", "pricing", "store", "validation", "formatting", "reports", "scheduler")
B_MODULES = ("release", "buildcheck", "admission", "throttle", "quotas", "audit", "cache", "events",
             "ledger", "exports", "notify", "metrics", "search", "sync", "retry", "config")  # fmt: skip
LIMIT_HOMES = ("throttle", "quotas", "config", "ledger")
A_READS = len(A_CHAIN)
B_SMALL = 12  # the first twelve phase-B reads: the compaction must not fire before them
# Target characters per module (file text). Calibrated in `calibration()`; see `check`.
SIZES = {"a": 1150, "b_small": 950, "b_large": 4800}
LOG_CHARS = (20_000, 22_000)
LOG_MAX = 28_000  # Claude Code truncates Bash output at 30,000 characters


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


# ---- facts ----------------------------------------------------------------------------


def facts_for(index: int) -> tuple[Facts, random.Random, str, list[str]]:
    rng = random.Random(f"{SEED}-{index}")
    plural, noun = DOMAINS[index]
    seed_text = "".join(rng.choice("0123456789abcdef") for _ in range(32))
    position = POSITIONS[index % len(POSITIONS)]
    expected = rng.randint(1000, 9999) / 10_000
    got = expected - rng.randint(50, 900) / 10_000
    check_id = f"BR-{rng.randint(1000, 9999)}"
    log, line_at = build_log(rng, check_id, f"{expected:.4f}", f"{got:.4f}", position)
    home = rng.choice(LIMIT_HOMES)
    decoy_home = rng.choice([h for h in LIMIT_HOMES if h != home]) if index % 5 != 4 else None
    limit = rng.randint(40, 400)
    decoy = None if decoy_home is None else limit + rng.choice((-1, 1)) * rng.randint(7, 30)
    b_order = list(B_MODULES)
    rng.shuffle(b_order)
    chain = tuple(f"pkg/{m}.py" for m in (*A_CHAIN, *b_order))
    facts = Facts(
        task=f"t{index + 1:02d}-{plural}", domain=noun, token=e2e._token(seed_text),
        check_id=check_id, check_expected=f"{expected:.4f}", check_got=f"{got:.4f}",
        check_position=position, check_line=line_at, log_lines=len(log),
        log_chars=len("\n".join(log)) + 1, limit=limit, limit_home=home, decoy=decoy,
        decoy_home=decoy_home, bug=rng.choice(e2e.BUGS)[1], chain=chain,
    )  # fmt: skip
    return facts, rng, seed_text, log


STAGES = ("compile", "lint", "typecheck", "bundle", "link", "package", "sign", "verify")


def _noise(rng: random.Random, i: int) -> str:
    stamp = f"[{10 + i // 60:02d}:{i % 60:02d}:{rng.randint(0, 59):02d}.{rng.randint(0, 999):03d}]"
    kind = rng.randrange(6)
    if kind == 0:
        return f"{stamp} {rng.choice(STAGES)} pkg/{rng.choice(B_MODULES + A_CHAIN)}.py ok ({rng.randint(3, 900) / 1000:.3f}s)"
    if kind == 1:
        v = f"{rng.randint(1000, 9999) / 10_000:.4f}"
        return f"{stamp} CHECK BR-{rng.randint(1000, 9999)} passed: expected {v} got {v}"
    if kind == 2:
        return f"{stamp} cache {'hit' if rng.random() < 0.7 else 'miss'} {rng.getrandbits(32):08x} size={rng.randint(200, 90000)}B"
    if kind == 3:
        return f"{stamp} worker-{rng.randint(1, 8)} queued job {rng.getrandbits(24):06x} depth={rng.randint(0, 40)} lag={rng.randint(0, 250)}ms"
    if kind == 4:
        return f"{stamp} warning: deprecated option --{rng.choice(('fast', 'legacy', 'strict', 'vendored'))}-{rng.choice(('io', 'paths', 'hash'))} ignored"
    return f"{stamp} artifact dist/{rng.getrandbits(20):05x}.whl sha256={rng.getrandbits(64):016x} {rng.randint(10, 999)}KB"


def build_log(rng: random.Random, check_id: str, expected: str, got: str,
              position: str) -> tuple[list[str], int]:  # fmt: skip
    """~300 lines of build noise sized into LOG_CHARS, and the index of the failing line."""
    target = rng.randint(*LOG_CHARS)
    lines: list[str] = []
    while sum(len(x) + 1 for x in lines) < target - 90:
        lines.append(_noise(rng, len(lines)))
    lo, hi = POSITION_RANGE[position]
    at = int(len(lines) * rng.uniform(lo, hi))
    stamp = f"[{10 + at // 60:02d}:{at % 60:02d}:{rng.randint(0, 59):02d}.{rng.randint(0, 999):03d}]"
    failing = f"{stamp} CHECK {check_id} failed: expected {expected} got {got}"
    return [*lines[:at], failing, *lines[at:]], at


# ---- module bodies --------------------------------------------------------------------


def _heads(facts: Facts, rng: random.Random) -> dict[str, tuple[str, str, str]]:
    """(docstring, head code, imports) for the modules with behaviour; the rest are filler."""
    noun = facts.domain
    buggy = dict((tag, line) for line, tag in e2e.BUGS)[facts.bug]
    heads = {
        "models": (f"The {noun} record.", f"@dataclass(frozen=True)\nclass {noun.capitalize()}:\n    id: int\n    region: str\n    amount: float\n    created: date\n", "from dataclasses import dataclass\nfrom datetime import date"),
        "parsing": (f"Parsing {noun} lines: `id,region,amount,YYYY-MM-DD`.", "def parse_line(line):\n    raw_id, region, amount, created = [p.strip() for p in line.split(',')]\n    return int(raw_id), region, float(amount), date.fromisoformat(created)\n", "from datetime import date"),
        "pricing": ("Prices, discounts and tax.", f"def apply_discount(total, pct):\n    \"\"\"`total` less `pct` per cent, rounded to cents.\"\"\"\n    {buggy}\n\n\ndef add_tax(total, rate={rng.choice((0.07, 0.1, 0.19, 0.21))}):\n    return round(total * (1 + rate), 2)\n", ""),
        "store": (f"An in-memory store of {noun}s.", "class Store:\n    def __init__(self):\n        self._items = {}\n\n    def put(self, item):\n        self._items = {**self._items, item.id: item}\n        return item\n\n    def get(self, item_id):\n        return self._items.get(item_id)\n", ""),
        "validation": (f"Checks on {noun}s.", f"class ValidationError(ValueError):\n    pass\n\n\nKNOWN_REGIONS = {tuple(sorted(rng.sample(e2e.REGIONS, 5)))!r}\n\n\ndef validate(item):\n    if item.region not in KNOWN_REGIONS:\n        raise ValidationError(f'unknown region {{item.region!r}}')\n    if item.amount < 0:\n        raise ValidationError('negative amount')\n    return item\n", ""),
        "formatting": ("Labels and display strings.", f"def label(item):\n    return f'{noun[:3].upper()}-{{item.region[:2].upper()}}-{{item.id:06d}}'\n", ""),
        "reports": ("Totals by region.", "def totals_by_region(items):\n    out = {}\n    for item in items:\n        out = {**out, item.region: round(out.get(item.region, 0) + item.amount, 2)}\n    return out\n", ""),
        "scheduler": ("Calendar helpers.", "def plus_days(day, days):\n    return day + timedelta(days=days)\n", "from datetime import timedelta"),
        "release": ("Release metadata.", "# Set to the token tools/issue_token.py issues for this release.\nRELEASE_TOKEN = None\n\n\ndef release_header():\n    return f'release {RELEASE_TOKEN}'\n", ""),
        "buildcheck": ("The build gate.", "class BuildError(RuntimeError):\n    pass\n\n\ndef check_build():\n    \"\"\"Raise BuildError naming the check that failed in tools/build_report.py's report\n    (its id and its expected value).\"\"\"\n    raise NotImplementedError\n", ""),
        "admission": (f"Admission of {noun} batches.", "def admit(count):\n    \"\"\"True when `count` is at most the package's batch ceiling, False otherwise.\"\"\"\n    raise NotImplementedError\n", ""),
    }
    return heads


def _constants(facts: Facts, name: str, rng: random.Random) -> str:
    lines = [f"RETRY_LIMIT = {rng.randint(2, 9)}", f"PAGE_SIZE = {rng.choice((20, 25, 40, 50))}",
             f"TIMEOUT_SECONDS = {rng.choice((5, 10, 30, 60))}"]  # fmt: skip
    if name == facts.limit_home:
        lines.insert(1, f"BATCH_CEILING = {facts.limit}  # largest batch admitted, in {facts.domain}s")
    if name == facts.decoy_home:
        lines.insert(2, f"SOFT_BATCH_CEILING = {facts.decoy}  # warn above this; not a hard limit")
    return "\n".join(lines) + "\n"


def module_text(name: str, nxt: str | None, target: int, facts: Facts, rng: random.Random) -> str:
    doc, head, imports = _heads(facts, rng).get(name, (f"The {name} helpers.", "", ""))
    if name in LIMIT_HOMES:
        head = _constants(facts, name, rng) + ("\n\n" + head if head else "")
    pointer = f"# Reading order: the next module is {nxt}\n" if nxt else "# Reading order: this is the last module (none after it).\n"
    top = pointer + f'"""{doc}"""\n\nfrom __future__ import annotations\n'
    if imports:
        top += "\n" + imports + "\n"
    body = top + ("\n\n" + head.strip() + "\n" if head else "")
    i = 0
    while len(body) < target - 60:
        piece = e2e._filler(rng, facts.domain, f"{name}{i}", 1)
        if len(body) + len(piece) + 3 > target + 120 and i > 0:
            break
        body += "\n\n" + piece.rstrip() + "\n"
        i += 1
    return body


def modules(facts: Facts, rng: random.Random) -> dict[str, str]:
    out = {"pkg/__init__.py": f'"""The {facts.domain} service."""\n\n__version__ = "0.{rng.randint(1, 9)}.{rng.randint(0, 20)}"\n'}
    for i, path in enumerate(facts.chain):
        nxt = facts.chain[i + 1] if i + 1 < len(facts.chain) else None
        if i < A_READS:
            target = SIZES["a"]
        elif i < A_READS + B_SMALL:
            target = SIZES["b_small"]
        else:
            target = SIZES["b_large"]
        out[path] = module_text(Path(path).stem, nxt, target, facts, rng)
    return out


def readme(facts: Facts) -> str:
    return (
        f"# {facts.domain} service\n\n"
        "A small internal package. `pkg/` is the code, `tests/` the suite "
        "(`python -m pytest -q tests`), `tools/` one-shot release scripts that consume their "
        "state when run.\n\n"
        "## Reading order\n\n"
        f"Read the modules in order, starting with `{facts.chain[0]}`. The first line of each "
        "module names the next one; the last says so. `pkg/__init__.py` is not in the order.\n\n"
        "## Release checklist\n\n"
        "1. `tools/issue_token.py` issues the release token (once).\n"
        "2. `tools/build_report.py` prints the build log with every check (once).\n"
        "3. `pkg/release.py`, `pkg/buildcheck.py` and `pkg/admission.py` are completed from them.\n"
    )


def hidden_tests(facts: Facts) -> str:
    return textwrap.dedent(
        f"""\
        import pytest

        from pkg import admission, buildcheck, release


        def test_token():
            assert release.RELEASE_TOKEN == {facts.token!r}


        def test_check():
            with pytest.raises(buildcheck.BuildError) as info:
                buildcheck.check_build()
            assert {facts.check_id!r} in str(info.value)
            assert {facts.check_expected!r} in str(info.value)


        def test_limit_at():
            assert admission.admit({facts.limit}) is True


        def test_limit_over():
            assert admission.admit({facts.limit + 1}) is False
        """
    )


FACT_TESTS = {"token": ("test_token",), "check": ("test_check",),
              "limit": ("test_limit_at", "test_limit_over")}  # fmt: skip


def build_report_script(log: list[str], facts: Facts) -> tuple[str, str]:
    """The log without its failing line in the script; the line comes from the one-shot state."""
    state = {"at": facts.check_line, "line": log[facts.check_line]}
    noise = log[: facts.check_line] + log[facts.check_line + 1 :]
    return textwrap.dedent(
        f'''\
        """Print the build log with every check. Runs once: it consumes its state."""

        import json
        import pathlib
        import sys

        NOISE = {noise!r}
        STATE = pathlib.Path(__file__).with_name(".build_state")

        if not STATE.exists():
            print("error: the build report was already printed; its state is consumed")
            sys.exit(2)
        state = json.loads(STATE.read_text())
        STATE.unlink()
        lines = NOISE[: state["at"]] + [state["line"]] + NOISE[state["at"]:]
        print("\\n".join(lines))
        print("build report: 1 check failed")
        sys.exit(1)
        '''
    ), json.dumps(state)


def build_one(index: int, out: Path) -> Facts:
    facts, rng, seed_text, log = facts_for(index)
    repo, hidden = out / "repos" / facts.task, out / "hidden" / facts.task
    for path in (repo, hidden):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
    files = modules(facts, rng)
    files["tests/test_basics.py"] = e2e.visible_tests(e2e.Facts(**{**_e2e_blank(), "domain": facts.domain}))
    files["tools/issue_token.py"] = e2e.issue_token_script(None, rng)
    files["tools/.token_seed"] = seed_text + "\n"
    script, state = build_report_script(log, facts)
    files["tools/build_report.py"] = script
    files["tools/.build_state"] = state + "\n"
    files["README.md"] = readme(facts)
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    (hidden / "test_hidden.py").write_text(hidden_tests(facts), encoding="utf-8", newline="\n")
    return facts


def _e2e_blank() -> dict:
    return {k: "" for k in e2e.Facts.__dataclass_fields__} | {"window_days": 0}


def build(out: Path, n: int = N_TASKS) -> list[Facts]:
    all_facts = [build_one(i, out) for i in range(n)]
    (out / "facts.json").write_text(json.dumps([asdict(f) for f in all_facts], indent=1) + "\n",
                                    encoding="utf-8")  # fmt: skip
    return all_facts


def load_facts(out: Path) -> dict[str, dict]:
    return {f["task"]: f for f in json.loads((out / "facts.json").read_text("utf-8"))}


tree_digest = e2e.tree_digest


# ---- the reference solution and the tests ---------------------------------------------


def solve(repo: Path, facts: Facts | dict) -> None:
    f = facts if isinstance(facts, dict) else asdict(facts)
    pricing = repo / "pkg" / "pricing.py"
    buggy = dict((tag, line) for line, tag in e2e.BUGS)[f["bug"]]
    pricing.write_text(pricing.read_text("utf-8").replace(buggy, "return round(total * (1 - pct / 100), 2)"),
                       encoding="utf-8")  # fmt: skip
    (repo / "pkg" / "release.py").write_text(f"RELEASE_TOKEN = {f['token']!r}\n", encoding="utf-8")
    (repo / "pkg" / "buildcheck.py").write_text(
        "class BuildError(RuntimeError):\n    pass\n\n\ndef check_build():\n"
        f"    raise BuildError('check {f['check_id']} failed: expected {f['check_expected']}')\n",
        encoding="utf-8",
    )
    (repo / "pkg" / "admission.py").write_text(
        f"from pkg.{f['limit_home']} import BATCH_CEILING\n\n\ndef admit(count):\n"
        "    return count <= BATCH_CEILING\n",
        encoding="utf-8",
    )


def run_tests(repo: Path, hidden: Path, python: str = sys.executable) -> dict:
    return e2e.run_tests(repo, hidden, python)


def facts_passed(tests: dict[str, bool]) -> dict[str, bool]:
    out = {}
    for fact, names in FACT_TESTS.items():
        keys = [k for k in tests if k.startswith("hidden::") and k.split("::")[1].split("[")[0] in names]
        out[fact] = bool(keys) and all(tests[k] for k in keys)
    vis = [v for k, v in tests.items() if k.startswith("visible::")]
    out["visible"] = bool(vis) and all(vis)
    return out


# ---- calibration ----------------------------------------------------------------------

EMPTY_SESSION = 38_000  # measured, probe p2-p6 (Haiku 4.5, Claude Code 2.1.282)
THRESHOLD = 64_000  # min(floor(80,000 * 80 / 100), 80,000 - 13,000)
PER_CALL = 90  # tool_use block and result wrapper, per tool call
A_OUTPUT = 3_000  # phase A's own text, edits and kept thinking
B_PROMPT = 450
B_PER_TURN = 60  # phase B's short text between reads
PYTEST_CHARS = 2_600  # one failing and one passing run of the visible suite
ARRIVAL_KEPT = 9_500  # measured: lean arrival cut of t01-t03 logs kept 9,442-9,574 chars, failing line included
RATIOS = (0.30, 0.33, 0.36)  # tokens per character; 0.30 given, ~0.36 measured on code (e2e)


def _read_chars(text: str) -> int:
    """What a Read result carries: the text plus Claude Code's line-number prefix."""
    return len(text) + 7 * text.count("\n")


def calibration(repo: Path, facts: dict) -> dict:
    chain = facts["chain"]
    reads = [_read_chars((repo / p).read_text("utf-8")) for p in chain]
    readme_chars = _read_chars((repo / "README.md").read_text("utf-8"))
    a_chars = readme_chars + sum(reads[:A_READS]) + 2_200 + PYTEST_CHARS
    out: dict = {"a_result_chars": a_chars, "log_chars": facts["log_chars"],
                 "b_read_chars": sum(reads[A_READS:]), "large_reads": reads[A_READS + B_SMALL:]}  # fmt: skip
    for r in RATIOS:
        a_end = EMPTY_SESSION + A_OUTPUT + r * a_chars + PER_CALL * (A_READS + 5)
        after_log = a_end + B_PROMPT + r * facts["log_chars"] + PER_CALL
        ctx = after_log
        fire_at = None
        for k, chars in enumerate(reads[A_READS:], start=1):
            ctx += r * chars + PER_CALL + B_PER_TURN
            if fire_at is None and ctx >= THRESHOLD:
                fire_at = k
        cut = after_log - r * (facts["log_chars"] - ARRIVAL_KEPT)  # L: the log as cut on arrival
        l_end = cut + (ctx - after_log) + 2_500  # plus the edits and a test run
        out[f"r{r:.2f}"] = {
            "a_end": round(a_end), "after_log": round(after_log),
            "after_12": round(after_log + sum(r * c + PER_CALL + B_PER_TURN for c in reads[A_READS:A_READS + 12])),
            "after_all_reads": round(ctx), "fires_after_read": fire_at,
            "N_end_with_edits": round(ctx + 2_500), "L_end_with_edits": round(l_end),
        }  # fmt: skip
    return out


# ---- check ----------------------------------------------------------------------------


def _one_shot(tool: Path, cwd: Path) -> tuple[subprocess.CompletedProcess, subprocess.CompletedProcess]:
    first = subprocess.run([sys.executable, str(tool)], cwd=cwd, capture_output=True, text=True, timeout=60)
    second = subprocess.run([sys.executable, str(tool)], cwd=cwd, capture_output=True, text=True, timeout=60)
    return first, second


def check_one(out: Path, f: dict) -> dict:
    repo, hidden = out / "repos" / f["task"], out / "hidden" / f["task"]
    scratch = out / "solved" / f["task"]
    if scratch.exists():
        shutil.rmtree(scratch)
    shutil.copytree(repo, scratch)
    before = run_tests(scratch, hidden)
    tok1, tok2 = _one_shot(scratch / "tools" / "issue_token.py", scratch)
    log1, log2 = _one_shot(scratch / "tools" / "build_report.py", scratch)
    failing = [i for i, x in enumerate(log1.stdout.splitlines()) if " failed: expected " in x]
    solve(scratch, f)
    after = run_tests(scratch, hidden)
    chain_ok = all((repo / p).exists() for p in f["chain"]) and len(set(f["chain"])) == 24
    sizes = [len((repo / p).read_text("utf-8")) for p in f["chain"]]
    ok = {
        "hidden_fail_before": not any(facts_passed(before["tests"])[k] for k in FACT_TESTS),
        "visible_fail_before": not facts_passed(before["tests"])["visible"],
        "all_pass_after": after["passed"],
        "token_once": f["token"] in tok1.stdout and tok2.returncode == 2 and len(tok1.stdout) < 3_000,
        "log_once": log1.returncode == 1 and log2.returncode == 2,
        "log_size": 19_500 <= len(log1.stdout) <= LOG_MAX,
        "one_failing_line": len(failing) == 1 and failing[0] == f["check_line"],
        "chain": chain_ok,
    }
    return {
        "ok": ok, "passed": all(ok.values()), "log_chars": len(log1.stdout),
        "failing_line": failing, "log_lines": len(log1.stdout.splitlines()),
        "position": f["check_position"], "token_report_chars": len(tok1.stdout),
        "module_chars": {"a": sizes[:A_READS], "b": sizes[A_READS:]},
        "calibration": calibration(repo, f),
    }  # fmt: skip


def check(out: Path) -> dict:
    build(out)
    return {t: check_one(out, f) for t, f in load_facts(out).items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "check", "digest"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    if args.action == "build":
        build(out)
        print(tree_digest(out / "repos"))
        return 0
    if args.action == "digest":
        print(tree_digest(out / "repos"), tree_digest(out / "hidden"))
        return 0
    rows = check(out)
    print(json.dumps({t: {k: v for k, v in r.items() if k != "module_chars"} for t, r in rows.items()}, indent=1))
    return 0 if all(r["passed"] for r in rows.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
