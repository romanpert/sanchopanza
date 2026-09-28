"""The generated mini-repositories for the compaction end-to-end run. Deterministic, no data.

    python tasks.py build --out <dir>            # one folder per task, plus hidden tests
    python tasks.py check --out <dir>            # free: hidden tests fail as generated and
                                                 # pass on the reference solution

Each task is a small Python package (`pkg/`, 16 modules), a visible pytest suite with one
seeded bug it catches, and two one-shot tools. Four facts are planted for phase B:

- `token`: `tools/issue_token.py` prints an inventory report (~2.5 KB) with the release token
  in the middle, then deletes its seed. It cannot be run again: the fact exists only in that
  command output.
- `probe`: `tools/probe.py` prints a calibration dump and fails (exit 1) with a line naming a
  tolerance and an error code, then deletes its state. Command output only, and an error.
- `window`: the grace window in days, a constant defined in one module among decoys with
  similar names. Re-readable.
- `helper`: the name and keyword-only parameter of the business-day helper in
  `pkg/scheduler.py`, next to a calendar-day decoy. Re-readable.

The hidden tests live outside the task folder and are copied nowhere the agent can see; they
are run after phase B. Everything comes from `random.Random(f"{SEED}-{index}")`.
"""

# ruff: noqa: E501  (long lines are generated source inside string literals)
from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import subprocess
import sys
import textwrap
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

SEED = "context-e2e-2026-09-28"
N_TASKS = 16

DOMAINS = (
    ("orders", "order"), ("shipments", "shipment"), ("invoices", "invoice"),
    ("sensors", "reading"), ("tickets", "ticket"), ("bookings", "booking"),
    ("payroll", "payslip"), ("loans", "loan"), ("fleet", "vehicle"),
    ("warehouse", "pallet"), ("subscriptions", "plan"), ("meters", "meter"),
    ("courses", "enrolment"), ("parking", "permit"), ("recipes", "batch"),
    ("repairs", "job"),
)  # fmt: skip
REGIONS = ("north", "south", "east", "west", "central", "coast", "valley", "harbour")
HELPERS = (
    ("advance_business_days", "business_days"),
    ("roll_forward_workdays", "workdays"),
    ("add_working_days", "count"),
    ("shift_business_days", "span"),
)
DECOY_HELPERS = ("add_calendar_days", "shift_calendar_days", "plus_days")
WINDOW_HOMES = ("limits.py", "audit.py", "cache.py", "events.py")
BUGS = (
    ("return round(total * (1 - pct / 10), 2)", "tenths"),
    ("return round(total * (1 + pct / 100), 2)", "sign"),
    ("return round(total - pct, 2)", "absolute"),
)
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


@dataclass(frozen=True)
class Facts:
    task: str
    domain: str
    token: str
    tolerance: str
    code: str
    drift: str
    window_days: int
    window_home: str
    helper: str
    helper_kw: str
    bug: str


def _token(seed_text: str) -> str:
    digest = hashlib.sha256(seed_text.encode("ascii")).digest()
    return "RT-" + "".join(ALPHABET[b % len(ALPHABET)] for b in digest[:10])


def facts_for(index: int) -> tuple[Facts, random.Random, str]:
    rng = random.Random(f"{SEED}-{index}")
    plural, noun = DOMAINS[index % len(DOMAINS)]
    seed_text = "".join(rng.choice("0123456789abcdef") for _ in range(32))
    tolerance = rng.randint(120, 480) / 10_000
    drift = tolerance + rng.randint(40, 300) / 10_000
    helper, kw = rng.choice(HELPERS)
    facts = Facts(
        task=f"t{index + 1:02d}-{plural}",
        domain=noun,
        token=_token(seed_text),
        tolerance=f"{tolerance:.4f}",
        code=f"PRB-{rng.randint(1000, 9999)}",
        drift=f"{drift:.4f}",
        window_days=rng.randint(11, 59),
        window_home=rng.choice(WINDOW_HOMES),
        helper=helper,
        helper_kw=kw,
        bug=rng.choice(BUGS)[1],
    )
    return facts, rng, seed_text


# ---- module bodies -------------------------------------------------------------------


def _decoy_constants(rng: random.Random, facts: Facts, here: str) -> str:
    lines = [
        f"GRACE_WINDOW_HOURS = {rng.randint(6, 72)}",
        f"RETRY_WINDOW_DAYS = {rng.randint(2, 9)}",
        f"GRACE_NOTICE_DAYS = {rng.randint(1, 10)}",
        f"ARCHIVE_WINDOW_DAYS = {rng.randint(60, 400)}",
        f"MAX_BATCH_SIZE = {rng.choice((50, 100, 250, 500))}",
        f"PAGE_SIZE = {rng.choice((20, 25, 40, 50))}",
        f"DEFAULT_CURRENCY = {rng.choice(('EUR', 'GBP', 'USD'))!r}",
    ]
    rng.shuffle(lines)
    if facts.window_home == here:
        at = rng.randint(2, len(lines) - 1)
        lines.insert(at, f"GRACE_WINDOW_DAYS = {facts.window_days}  # calendar days")
    return "\n".join(lines)


def _filler(rng: random.Random, noun: str, stem: str, n: int) -> str:
    """Ordinary, correct helper functions: the bulk an agent reads while exploring."""
    kinds = [
        (
            "def {s}_{k}_count(items):\n"
            '    """How many {noun}s in `items` have a positive amount."""\n'
            "    return sum(1 for item in items if getattr(item, 'amount', 0) > 0)\n"
        ),
        (
            "def {s}_{k}_key(item):\n"
            '    """Sort key for a {noun}: region first, then id."""\n'
            "    return (getattr(item, 'region', ''), getattr(item, 'id', 0))\n"
        ),
        (
            "def {s}_{k}_scale(values, factor={f}):\n"
            '    """Each value times `factor`, rounded to two places."""\n'
            "    return [round(v * factor, 2) for v in values]\n"
        ),
        (
            "def {s}_{k}_window(values, size={w}):\n"
            '    """Moving sums of `size` consecutive values."""\n'
            "    return [sum(values[i:i + size]) for i in range(0, max(len(values) - size + 1, 0))]\n"
        ),
        (
            "def {s}_{k}_tag(name):\n"
            '    """A lower-case tag for a {noun} name, spaces to dashes."""\n'
            "    return '-'.join(str(name).strip().lower().split())\n"
        ),
        (
            "def {s}_{k}_bucket(amount, edges=({a}, {b}, {c})):\n"
            '    """Index of the first edge `amount` is below, or len(edges)."""\n'
            "    for index, edge in enumerate(edges):\n"
            "        if amount < edge:\n"
            "            return index\n"
            "    return len(edges)\n"
        ),
    ]
    out = []
    for k in range(n):
        template = rng.choice(kinds)
        a = rng.randint(5, 40)
        out.append(
            template.format(
                s=stem,
                k=k,
                noun=noun,
                f=rng.choice((0.5, 1.1, 1.25, 2.0)),
                w=rng.randint(2, 5),
                a=a,
                b=a * 3,
                c=a * 9,
            )  # fmt: skip
        )
    return "\n\n".join(out)


def _module(doc: str, body: str, imports: str = "") -> str:
    head = f'"""{doc}"""\n\nfrom __future__ import annotations\n'
    if imports:
        head += "\n" + imports + "\n"
    return head + "\n\n" + body.strip() + "\n"


def modules(facts: Facts, rng: random.Random) -> dict[str, str]:
    noun = facts.domain
    buggy = dict((tag, line) for line, tag in BUGS)[facts.bug]
    decoy = rng.choice(DECOY_HELPERS)
    m: dict[str, str] = {}
    m["pkg/__init__.py"] = (
        f'"""The {noun} service, a small internal package."""\n\n__version__ = "0.{rng.randint(1, 9)}.{rng.randint(0, 20)}"\n'  # noqa: E501
    )
    m["pkg/limits.py"] = _module(
        "Limits and defaults.", _decoy_constants(rng, facts, "limits.py") + "\n\n\n"
        + _filler(rng, noun, "limit", 9)
    )  # fmt: skip
    m["pkg/models.py"] = _module(
        f"The {noun} record.",
        f"@dataclass(frozen=True)\nclass {noun.capitalize()}:\n    id: int\n    region: str\n"
        f"    amount: float\n    created: date\n\n\n" + _filler(rng, noun, "model", 9),
        "from dataclasses import dataclass\nfrom datetime import date",
    )
    m["pkg/pricing.py"] = _module(
        "Prices, discounts and tax.",
        "def apply_discount(total, pct):\n"
        '    """`total` less `pct` per cent, rounded to cents."""\n'
        f"    {buggy}\n\n\n"
        f"def add_tax(total, rate={rng.choice((0.07, 0.1, 0.19, 0.21))}):\n"
        "    return round(total * (1 + rate), 2)\n\n\n" + _filler(rng, noun, "price", 10),
    )
    m["pkg/store.py"] = _module(
        f"An in-memory store of {noun}s.",
        "class Store:\n    def __init__(self):\n        self._items = {}\n\n"
        "    def put(self, item):\n        self._items = {**self._items, item.id: item}\n"
        "        return item\n\n    def get(self, item_id):\n        return self._items.get(item_id)\n\n"
        "    def all(self):\n        return sorted(self._items.values(), key=lambda i: i.id)\n\n\n"
        + _filler(rng, noun, "store", 9),
    )  # fmt: skip
    m["pkg/parsing.py"] = _module(
        f"Parsing {noun} lines: `id,region,amount,YYYY-MM-DD`.",
        "def parse_line(line):\n    raw_id, region, amount, created = [p.strip() for p in line.split(',')]\n"
        "    return int(raw_id), region, float(amount), date.fromisoformat(created)\n\n\n"
        + _filler(rng, noun, "parse", 9),
        "from datetime import date",
    )  # fmt: skip
    m["pkg/validation.py"] = _module(
        f"Checks on {noun}s.",
        "class ValidationError(ValueError):\n    pass\n\n\n"
        f"KNOWN_REGIONS = {tuple(sorted(rng.sample(REGIONS, 5)))!r}\n\n\n"
        "def validate(item):\n    if item.region not in KNOWN_REGIONS:\n"
        "        raise ValidationError(f'unknown region {item.region!r}')\n"
        "    if item.amount < 0:\n        raise ValidationError('negative amount')\n    return item\n\n\n"
        + _filler(rng, noun, "valid", 9),
    )  # fmt: skip
    m["pkg/formatting.py"] = _module(
        "Labels and display strings.",
        f"def label(item):\n    return f'{noun[:3].upper()}-{{item.region[:2].upper()}}-{{item.id:06d}}'\n\n\n"
        + _filler(rng, noun, "fmt", 10),
    )  # fmt: skip
    m["pkg/reports.py"] = _module(
        "Totals by region.",
        "def totals_by_region(items):\n    out = {}\n    for item in items:\n"
        "        out = {**out, item.region: round(out.get(item.region, 0) + item.amount, 2)}\n"
        "    return out\n\n\n" + _filler(rng, noun, "report", 10),
    )
    m["pkg/scheduler.py"] = _module(
        "Calendar helpers. Weekends are Saturday and Sunday; there is no holiday table.",
        f"def {decoy}(day, days):\n"
        '    """`day` plus `days` calendar days."""\n'
        "    return day + timedelta(days=days)\n\n\n"
        f"def {facts.helper}(day, *, {facts.helper_kw}):\n"
        f'    """`day` moved forward by `{facts.helper_kw}` working days (Mon-Fri)."""\n'
        f"    left = {facts.helper_kw}\n    current = day\n    while left > 0:\n"
        "        current = current + timedelta(days=1)\n        if current.weekday() < 5:\n"
        "            left -= 1\n    return current\n\n\n" + _filler(rng, noun, "sched", 9),
        "from datetime import timedelta",
    )  # fmt: skip
    for name, doc, stem in (
        ("audit.py", "An append-only audit trail.", "audit"),
        ("cache.py", "A tiny memo cache.", "cache"),
        ("events.py", "Event names and a dispatcher.", "event"),
    ):
        m[f"pkg/{name}"] = _module(
            doc, _decoy_constants(rng, facts, name) + "\n\n\n" + _filler(rng, noun, stem, 10)
        )
    m["pkg/release.py"] = _module(
        "Release metadata.",
        "# Set to the token tools/issue_token.py issues for this release.\nRELEASE_TOKEN = None\n\n\n"
        "def release_header():\n    return f'release {RELEASE_TOKEN}'\n",
    )  # fmt: skip
    m["pkg/guard.py"] = _module(
        "Drift guard for the calibration probe.",
        "class GuardError(RuntimeError):\n    pass\n\n\n"
        "# Set from the tolerance tools/probe.py reports.\nDRIFT_TOLERANCE = None\n\n\n"
        "def check_drift(value):\n    raise NotImplementedError\n",
    )  # fmt: skip
    m["pkg/deadlines.py"] = _module(
        f"Deadlines for {noun}s.",
        "def grace_deadline(start):\n    raise NotImplementedError\n",
    )
    return m


def visible_tests(facts: Facts) -> str:
    noun = facts.domain.capitalize()
    return textwrap.dedent(
        f"""\
        from datetime import date

        import pytest

        from pkg import formatting, parsing, pricing, reports, validation
        from pkg.models import {noun}


        def test_parse_line():
            assert parsing.parse_line("7, north, 12.5, 2026-01-02") == (7, "north", 12.5, date(2026, 1, 2))


        def test_discount():
            assert pricing.apply_discount(200.0, 15) == 170.0


        def test_totals():
            items = [{noun}(1, "a", 1.5, date(2026, 1, 1)), {noun}(2, "a", 2.0, date(2026, 1, 1))]
            assert reports.totals_by_region(items) == {{"a": 3.5}}


        def test_label():
            assert formatting.label({noun}(42, "north", 1.0, date(2026, 1, 1))).endswith("-000042")


        def test_validation_rejects_negative():
            region = validation.KNOWN_REGIONS[0]
            with pytest.raises(validation.ValidationError):
                validation.validate({noun}(1, region, -1.0, date(2026, 1, 1)))
        """
    )


def _business(day: date, n: int) -> date:
    current = day
    while n > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            n -= 1
    return current


def hidden_tests(facts: Facts) -> str:
    starts = (date(2026, 3, 6), date(2026, 11, 18))
    expected = [(s.isoformat(), _business(s, facts.window_days).isoformat()) for s in starts]
    tol = float(facts.tolerance)
    return textwrap.dedent(
        f"""\
        from datetime import date

        import pytest

        from pkg import deadlines, guard, release


        def test_token():
            assert release.RELEASE_TOKEN == {facts.token!r}


        def test_probe_tolerance():
            assert guard.DRIFT_TOLERANCE == pytest.approx({tol!r})


        def test_probe_raises_with_code():
            with pytest.raises(guard.GuardError, match={facts.code!r}):
                guard.check_drift({tol + 0.001!r})


        def test_probe_passes_below():
            assert guard.check_drift({tol - 0.001!r}) is None


        @pytest.mark.parametrize("start,end", {expected!r})
        def test_window(start, end):
            assert deadlines.grace_deadline(date.fromisoformat(start)) == date.fromisoformat(end)
        """
    )


FACT_TESTS = {
    "token": ("test_token",),
    "probe": ("test_probe_tolerance", "test_probe_raises_with_code", "test_probe_passes_below"),
    "window": ("test_window",),
}


def issue_token_script(facts: Facts, rng: random.Random) -> str:
    rows = []
    for _ in range(48):
        rows.append(
            f"SKU-{rng.randint(10000, 99999)}  {rng.choice(REGIONS):<8}  "
            f"qty={rng.randint(0, 900):>4}  bin={rng.choice('ABCDEFGH')}{rng.randint(1, 40):02d}"
        )
    middle = rng.randint(18, 30)
    return textwrap.dedent(
        f'''\
        """Issue this release's token. It can be issued once: the seed is consumed."""

        import hashlib
        import pathlib
        import sys

        ALPHABET = {ALPHABET!r}
        ROWS = {rows!r}
        SEED = pathlib.Path(__file__).with_name(".token_seed")

        if not SEED.exists():
            print("error: the release token was already issued; tokens are issued once")
            sys.exit(2)
        digest = hashlib.sha256(SEED.read_text().strip().encode("ascii")).digest()
        token = "RT-" + "".join(ALPHABET[b % len(ALPHABET)] for b in digest[:10])
        SEED.unlink()
        print("inventory snapshot before release")
        for index, row in enumerate(ROWS):
            if index == {middle}:
                print("release token: " + token)
            print(row)
        print("snapshot complete: " + str(len(ROWS)) + " rows")
        '''
    )


def probe_script(facts: Facts, rng: random.Random) -> str:
    channels = []
    for i in range(36):
        value = rng.randint(1, int(float(facts.tolerance) * 10_000) - 1) / 10_000
        channels.append(
            f"channel {i:02d}  gain={rng.randint(90, 110) / 100:.2f}  drift={value:.4f}  ok"
        )
    state = {"drift": facts.drift, "tolerance": facts.tolerance, "code": facts.code}
    return textwrap.dedent(
        f'''\
        """Calibration probe. Reads its one-shot state, reports, and consumes the state."""

        import json
        import pathlib
        import sys

        CHANNELS = {channels!r}
        STATE = pathlib.Path(__file__).with_name(".probe_state")

        if not STATE.exists():
            print("error: probe state already consumed; the probe runs once per calibration")
            sys.exit(2)
        state = json.loads(STATE.read_text())
        STATE.unlink()
        for line in CHANNELS:
            print(line)
        print("channel 36  aggregate  drift=" + state["drift"] + "  FAIL")
        print(
            "ProbeError: drift " + state["drift"] + " exceeds tolerance " + state["tolerance"]
            + " (code " + state["code"] + ")"
        )
        sys.exit(1)
        '''
    ), json.dumps(state)


def build_one(index: int, out: Path) -> Facts:
    facts, rng, seed_text = facts_for(index)
    repo = out / "repos" / facts.task
    hidden = out / "hidden" / facts.task
    for path in (repo, hidden):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
    files = modules(facts, rng)
    files["tests/test_basics.py"] = visible_tests(facts)
    files["tools/issue_token.py"] = issue_token_script(facts, rng)
    probe, state = probe_script(facts, rng)
    files["tools/probe.py"] = probe
    files["tools/.token_seed"] = seed_text + "\n"
    files["tools/.probe_state"] = state + "\n"
    files["README.md"] = (
        f"# {facts.domain} service\n\nA small internal package. `pkg/` is the code, `tests/` "
        "the suite (`python -m pytest -q tests`), `tools/` one-shot release scripts.\n"
    )
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    (hidden / "test_hidden.py").write_text(hidden_tests(facts), encoding="utf-8", newline="\n")
    return facts


def build(out: Path, n: int = N_TASKS) -> list[Facts]:
    all_facts = [build_one(i, out) for i in range(n)]
    (out / "facts.json").write_text(
        json.dumps([asdict(f) for f in all_facts], indent=1) + "\n", encoding="utf-8"
    )
    return all_facts


def tree_digest(root: Path) -> str:
    """sha256 over every file's relative path and bytes, sorted: the generator's fingerprint."""
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        h.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


# ---- the reference solution, for the free check ---------------------------------------


def solve(repo: Path, facts: Facts) -> None:
    """What a correct phase A + B leaves: bug fixed, three changes made."""
    pricing = repo / "pkg" / "pricing.py"
    buggy = dict((tag, line) for line, tag in BUGS)[facts.bug]
    pricing.write_text(
        pricing.read_text("utf-8").replace(buggy, "return round(total * (1 - pct / 100), 2)"),
        encoding="utf-8",
    )
    (repo / "pkg" / "release.py").write_text(f"RELEASE_TOKEN = {facts.token!r}\n", encoding="utf-8")
    (repo / "pkg" / "guard.py").write_text(
        "class GuardError(RuntimeError):\n    pass\n\n\n"
        f"DRIFT_TOLERANCE = {facts.tolerance}\n\n\n"
        "def check_drift(value):\n    if value > DRIFT_TOLERANCE:\n"
        f"        raise GuardError('drift exceeds tolerance (code {facts.code})')\n    return None\n",
        encoding="utf-8",
    )  # fmt: skip
    (repo / "pkg" / "deadlines.py").write_text(
        f"from pkg.scheduler import {facts.helper}\n"
        f"from pkg.{facts.window_home[:-3]} import GRACE_WINDOW_DAYS\n\n\n"
        f"def grace_deadline(start):\n    return {facts.helper}(start, {facts.helper_kw}=GRACE_WINDOW_DAYS)\n",
        encoding="utf-8",
    )  # fmt: skip


def run_tests(repo: Path, hidden: Path, python: str = sys.executable) -> dict:
    """Hidden and visible suites against `repo`; per-test outcome and the overall verdict."""
    report = repo.parent / f".{repo.name}-junit.xml"
    proc = subprocess.run(
        [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={report}",
         str(hidden / "test_hidden.py"), str(repo / "tests")],
        cwd=repo, capture_output=True, text=True, timeout=120,
        env={**_clean_env(), "PYTHONPATH": str(repo), "PYTHONDONTWRITEBYTECODE": "1"},
    )  # fmt: skip
    outcomes = _junit(report)
    report.unlink(missing_ok=True)
    return {"exit": proc.returncode, "passed": proc.returncode == 0, "tests": outcomes,
            "tail": proc.stdout[-600:]}  # fmt: skip


def _clean_env() -> dict:
    import os

    return {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST", "PYTHONPATH"))}


def _junit(path: Path) -> dict[str, bool]:
    import xml.etree.ElementTree as ET

    if not path.exists():
        return {}
    out: dict[str, bool] = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        name = case.get("name", "")
        klass = case.get("classname", "")
        key = f"{'hidden' if klass.split('.')[-1] == 'test_hidden' else 'visible'}::{name}"
        out[key] = not any(child.tag in ("failure", "error") for child in case)
    return out


def facts_passed(tests: dict[str, bool]) -> dict[str, bool]:
    """Per planted fact: every hidden test for it passed. `visible`: the whole visible suite."""
    out = {}
    for fact, names in FACT_TESTS.items():
        keys = [
            k for k in tests if k.startswith("hidden::") and k.split("::")[1].split("[")[0] in names
        ]
        out[fact] = bool(keys) and all(tests[k] for k in keys)
    vis = [v for k, v in tests.items() if k.startswith("visible::")]
    out["visible"] = bool(vis) and all(vis)
    return out


def check(out: Path) -> dict:
    """Free: every task's hidden tests fail as generated and pass on the reference solution."""
    facts = build(out)
    rows = {}
    for f in facts:
        repo, hidden = out / "repos" / f.task, out / "hidden" / f.task
        scratch = out / "solved" / f.task
        if scratch.exists():
            shutil.rmtree(scratch)
        shutil.copytree(repo, scratch)
        before = run_tests(scratch, hidden)
        solve(scratch, f)
        after = run_tests(scratch, hidden)
        rows[f.task] = {"before": before["passed"], "after": after["passed"],
                        "before_facts": facts_passed(before["tests"])}  # fmt: skip
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "check", "digest"))
    parser.add_argument("--out", required=True)
    parser.add_argument("-n", type=int, default=N_TASKS)
    args = parser.parse_args(argv)
    out = Path(args.out)
    if args.action == "build":
        build(out, args.n)
        print(tree_digest(out / "repos"))
    elif args.action == "digest":
        print(tree_digest(out / "repos"), tree_digest(out / "hidden"))
    else:
        rows = check(out)
        print(json.dumps(rows, indent=1))
        bad = [t for t, r in rows.items() if r["before"] or not r["after"]]
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
