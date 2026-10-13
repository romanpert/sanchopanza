"""Long chains, one Claude Code session per arm, as a clean user (the long-session prereg draft).

    python benchmarks/adopt/long_run.py plan  --profile gate [--model sonnet] [--chains a,b]
    python benchmarks/adopt/long_run.py run   --profile gate --model sonnet [--chains a,b]
    python benchmarks/adopt/long_run.py run   --profile smoke
    python benchmarks/adopt/long_run.py grade --profile gate --model sonnet [--chains a,b]
    python benchmarks/adopt/long_run.py kill  [--root C:\\sp-runs\\L]

Arms: N, Claude Code alone in a fresh CLAUDE_CONFIG_DIR per chain and arm (`carry.py`'s clean
user: its token, its refusals, its pinned 2.1.287); Ne, N plus `CLAUDE_CODE_AUTO_COMPACT_WINDOW`
in the project settings' `env` block and nothing else; S, the sealed S line installed in the
working copy (`run.install_sancho`, hooks through `hook_env.py`), candor in observe mode, Jev at
most 0.50 USD per chain. The arms of a chain run one after another, in an order rotated by the
chain's name. Every prompt comes from `run.requests_of` (`long.requests`: the control token in
the first, numbered bugs, callbacks late), with a token per chain and arm.

Money is metered at the owner's prices (`meter.OWNER_RATES`) from each call's transcript and
`modelUsage`; caps are set in those dollars and passed to `--max-budget-usd` in Claude Code's
(`meter.claude_code_cap`). Every block's chain caps are held against the ceiling before the
first call. Between calls: LIMIT.flag and the STOP file, Docker, disk, the caps and the wall.
On every call: its init (version, model, permission mode, MCP servers), the usage limit, a diff
that vanished, Jev's outage, hook errors. `row.json` is written after every call.

Every call also writes the session's own `autocompact: ... effectiveWindow=` lines
(`long_window`, `--debug=autocompact` in every arm): each row carries the window it ran under and
its source, and `<root>/windows.json` N's server-set default per model. N-early's window is the
one S's install writes for the profile's budget (`install_defaults.window_for`). A run started
again resumes (`long_resume`): finished arms are skipped, a stopped or dead one goes on at its next
request, and the ceiling holds each chain at the larger of its caps and its spend. Before an S
arm, the hooks' decider is probed (free) and must be Jev. No chain runs without its manifest.

Exit codes: 0 ran to its end; 1 refused before any call; 2 the usage limit, a cap or the
ceiling; 3 a chain set aside (a cut call of a held-out chain); 4 the harness (a STOP file, a
broken invariant, Docker, the disk, a diff that vanished, Jev down); 5 a passages arm stopped by
its re-requests (`long_pilot`, the pilot of bet A: arms A and A10, `--arms`).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parent))  # appended: benchmarks/ holds names like agentdojo
sys.path.insert(0, str(HERE.parent / "memory_carry"))

import arm_files  # noqa: E402
import carry  # noqa: E402
import docker_env  # noqa: E402
import long_call  # noqa: E402
import long_guard  # noqa: E402
import long_money  # noqa: E402
import long_pilot  # noqa: E402
import long_resume  # noqa: E402
import long_window  # noqa: E402
import meter  # noqa: E402
import run  # noqa: E402
from long_money import blocks, ceiling_of, held, rows_under, spent  # noqa: E402,F401
from long_start import midnight_refusal, start_refusal  # noqa: E402

sys.path.insert(0, str(HERE.parents[1] / "src"))
from sanchopanza.harness.install_defaults import window_for  # noqa: E402

ROOT = Path(r"C:\sp-runs\L")  # outside the home folder: carry.refuse_unclean; short for MAX_PATH
WINDOW = "CLAUDE_CODE_AUTO_COMPACT_WINDOW"
EXIT = {"limit": 2, "cap": 2, "ceiling": 2, "wall": 2, "set aside": 3, "harness": 4,
        "rerequest": long_pilot.EXIT_REREQUEST}  # fmt: skip
# The sealed S line (docs/S-SEAL-DRAFT.md, S0 for code suites); its budget is the profile's.
S_FLAGS = ("--guard", "--guard-profile", "coding", "--memory", "--candor", "--find",
           "--find-auto", "--skill", "--scan-content", "--check-done", "--content-tools",
           "WebFetch,WebSearch,mcp__sanchopanza-fetch__fetch_passages", "--crawl", "--prune",
           "--fetch", "--provider", "jev")  # fmt: skip
# No guard chooser: the sealed install's default (cb0062e: struct over 6 parts; owner 10-06).
S_ENV = (("SANCHOPANZA_CANDOR_MODE", "observe"),
         ("SANCHOPANZA_CRAWL_LINE_VERSION", "6"), ("SANCHOPANZA_CRAWL_NOTES", "3"),
         ("SANCHOPANZA_CRAWL_ECHO", "short"), ("SANCHOPANZA_CRAWL_LINE_AT", "prompt"),
         ("SANCHOPANZA_CRAWL_NOTES_AT", "front"), ("SANCHOPANZA_CRAWL_SHOT", "snapshot-first"),
         ("SANCHOPANZA_FETCH_VERSION", "2"))  # fmt: skip
GATE_CALL_CAP = {"sonnet": 4.5, "opus": 8.0}  # owner USD; B2 ran 4.5 per call on Sonnet
GATE_CHAIN_CAP = {"sonnet": 38.0, "opus": 75.0}  # owner 2026-10-07 (twice): 2x38 + 2x75 = 226 <= 230
GATE_CEILING = 230.0  # owner 2026-10-07: Sonnet conan cost ~41 a whole chain (model: 25); Opus 1.67x
GATE_CHAINS = ("conan-io__conan-long60-1", "pydantic__pydantic-long60-1")
PILOT_CEILING = 80.0  # the pilot of bet A: one arm, 2 x 38 = 76 held, hard (2026-10-07)
NOISE_NE_CHAIN = 35.0  # N-early compacts at 193k: expected ~17 a chain (cost model), far from 35
NOISE_NE_CEILING = 2 * NOISE_NE_CHAIN  # 70, on the gate's two chains (owner 2026-10-07)
NOISE_N_CEILING = 40.0  # N again on pydantic (spent 23.55 the first time); 70 + 40 = the owner's 110
# The conan repeat round (owner, 2026-10-07 evening, 100 USD hard): N, Ne and A once more on
# conan, its own noise floor. N at the gate's 38; A one less (it stopped at 30.90 with 38);
# Ne spent 17.33 there, so 25 leaves it a tenth to spare. 38 + 37 + 25 = 100.
CONAN_N2_CEILING = 38.0
CONAN_A2_CEILING = 37.0
CONAN_NE2_CEILING = 25.0
# The context close-out (owner, 2026-10-13, 250 USD hard; prereg
# docs/results/2026-10-13-long-compact/prereg.md): N-early (Ne, compacts near 160k) against
# N-early-low (Nl: what `install --context-budget 67000` writes, a window of 100,000, Claude Code's
# floor, so it compacts near 67k), Sonnet 5.5, one run per arm and chain, both arms of a chain one
# after the other in `arm_order`'s rotation. 25 a run (Ne starts no call past ~18.9 and Nl past
# ~19.4: the call cap and one turn are held), 5 chains x 2 arms x 25 = 250.
COMPACT_LOW_BUDGET = 67_000
COMPACT_CHAIN_CAP = 25.0
COMPACT_CEILING = 250.0
COMPACT_CHAINS = ("conan-io__conan-long60-1", "pydantic__pydantic-long60-1",
                  "conan-io__conan-long60-2", "getmoto__moto-long60-1")  # fmt: skip
# The sixth chain, only if it validates in time and fits under the same ceiling (prereg, 3): its
# own profile, the same root, so the ceiling holds everything spent there.
COMPACT_EXTRA = ("iterative__dvc-long60-1",)
# Nl's compactions must fire where the prereg says (near 67k): a first-turn context at most one
# request past the threshold. Outside these bounds the arm is not the registered treatment.
LOW_PRE = (50_000, 110_000)  # a compaction's `pre` tokens
LOW_PEAK = 110_000  # a call's peak context (a window that never took: N passes it by call ~8-15)
SMOKE_CHAIN = "pydantic__pydantic-long60-1"  # validated first; Haiku, 3 bugs, its own root
MANIFESTS = HERE / "long60"  # long60/<chain>.json, written by `long.py manifests` once valid
JEV_MAX_USD = 0.50  # per chain (pre-mortem 15)
HOOK_ERRORS = 0.05  # hook calls ending in error, at most this share of a call's


@dataclass(frozen=True)
class Profile:
    name: str
    arms: tuple[str, ...]
    models: tuple[str, ...]
    call_cap: Mapping[str, float]  # owner USD per call
    chain_cap: Mapping[str, float]  # owner USD per chain and arm
    ceiling: float  # owner USD over everything under the root, earlier runs included
    chains: tuple[str, ...]
    hard_cap: float | None = None  # a ceiling no command line may raise
    bugs: int | None = None  # the first n bugs only
    timeout_s: float = 2700.0
    idle_s: float = 1200.0  # a stream that has not grown for this long is cut
    wall_s: float = 4 * 3600.0
    budget: int = 160_000  # S's --context-budget
    forced_timeouts: tuple[tuple[str, int, float], ...] = ()  # (arm, request, seconds)
    hours: Mapping[str, float] = field(default_factory=dict)  # expected per arm (midnight rule)
    choices: tuple[str, ...] = ()  # arms `--arms` may run instead of `arms`
    # Stops that end one arm only: the run goes on with the next arm and chain (the close-out runs
    # ten arms under one root; a run stopped by its own cap is compared on its common calls).
    local_stops: tuple[str, ...] = ()

    def with_arms(self, asked: tuple[str, ...]) -> Profile:
        """The profile with the arms asked for (none: its own), only among its choices."""
        if asked and not set(asked) <= set(self.choices or self.arms):
            raise SystemExit(f"{self.name}: arms {asked} not in {self.choices or self.arms}")
        return replace(self, arms=asked) if asked else self

    @property
    def window(self) -> int:
        """N-early's CLAUDE_CODE_AUTO_COMPACT_WINDOW: the value S's install writes for its
        --context-budget (`install_defaults.window_for`), so the two arms differ by the rest of S
        only (193,000 for 160,000; 100,000, Claude Code's floor, for the smoke's 67,000)."""
        return window_for(self.budget)


PROFILES = {
    "gate": Profile("gate", ("N",), ("sonnet", "opus"), GATE_CALL_CAP, GATE_CHAIN_CAP,
                    GATE_CEILING, GATE_CHAINS, hours={"sonnet": 1.6, "opus": 2.7}),
    "dev": Profile("dev", ("N", "Ne", "S"), ("sonnet", "opus"), GATE_CALL_CAP, GATE_CHAIN_CAP,
                   980.0, (), hours={"sonnet": 1.6, "opus": 2.7}),
    # Verification item 3: Haiku, 3 bugs, N-early at Claude Code's 100k floor (compacts near
    # 67k), S at --context-budget 67000, one N call cut at 90 s; hard cap 8 USD. A validated long60
    # chain with its manifest (the gate's path: guard, token, callbacks after bugs 2 and 3).
    "smoke": Profile("smoke", ("N", "Ne", "S"), ("haiku",), {"haiku": 1.0}, {"haiku": 2.0}, 8.0,
                     (SMOKE_CHAIN,), hard_cap=8.0, bugs=3, budget=67_000,
                     forced_timeouts=(("N", 2, 90.0),), hours={"haiku": 0.5}),
    # The pilot of bet A (long_pilot): arm A or A10 on the gate's chains, Sonnet and caps, its own
    # root and a hard ceiling; compared with the gate's N rows (pilot_a_compare.py).
    "pilot-a": Profile("pilot-a", ("A",), ("sonnet",), {"sonnet": GATE_CALL_CAP["sonnet"]},
                       {"sonnet": GATE_CHAIN_CAP["sonnet"]}, PILOT_CEILING, GATE_CHAINS,
                       hard_cap=PILOT_CEILING, hours={"sonnet": 1.6}, choices=long_pilot.ARMS),
    # The window and noise round (owner, 2026-10-07, 110 USD hard in all): N-early on the gate's
    # chains, and N once more on pydantic (most give-ups past 150k) to know how far
    # N moves against itself. 70 + 40 = 110 (N-early compacts, so it needs less than N).
    "noise-ne": Profile("noise-ne", ("Ne",), ("sonnet",), {"sonnet": GATE_CALL_CAP["sonnet"]},
                        {"sonnet": NOISE_NE_CHAIN}, NOISE_NE_CEILING, GATE_CHAINS,
                        hard_cap=NOISE_NE_CEILING, hours={"sonnet": 1.6}),
    "noise-n": Profile("noise-n", ("N",), ("sonnet",), {"sonnet": GATE_CALL_CAP["sonnet"]},
                       {"sonnet": NOISE_N_CEILING}, NOISE_N_CEILING, (GATE_CHAINS[1],),
                       hard_cap=NOISE_N_CEILING, hours={"sonnet": 1.6}),
    "conan-n2": Profile("conan-n2", ("N",), ("sonnet",), {"sonnet": GATE_CALL_CAP["sonnet"]},
                        {"sonnet": CONAN_N2_CEILING}, CONAN_N2_CEILING, (GATE_CHAINS[0],),
                        hard_cap=CONAN_N2_CEILING, hours={"sonnet": 1.6}),
    "conan-ne2": Profile("conan-ne2", ("Ne",), ("sonnet",), {"sonnet": GATE_CALL_CAP["sonnet"]},
                         {"sonnet": CONAN_NE2_CEILING}, CONAN_NE2_CEILING, (GATE_CHAINS[0],),
                         hard_cap=CONAN_NE2_CEILING, hours={"sonnet": 1.6}),
    "conan-a2": Profile("conan-a2", ("A",), ("sonnet",), {"sonnet": GATE_CALL_CAP["sonnet"]},
                        {"sonnet": CONAN_A2_CEILING}, CONAN_A2_CEILING, (GATE_CHAINS[0],),
                        hard_cap=CONAN_A2_CEILING, hours={"sonnet": 1.6}),
    "compact": Profile("compact", ("Ne", "Nl"), ("sonnet",), {"sonnet": GATE_CALL_CAP["sonnet"]},
                       {"sonnet": COMPACT_CHAIN_CAP}, COMPACT_CEILING, COMPACT_CHAINS,
                       hard_cap=COMPACT_CEILING, hours={"sonnet": 1.6},
                       local_stops=("cap", "wall")),
    "compact-extra": Profile("compact-extra", ("Ne", "Nl"), ("sonnet",),
                             {"sonnet": GATE_CALL_CAP["sonnet"]}, {"sonnet": COMPACT_CHAIN_CAP},
                             COMPACT_CEILING, COMPACT_EXTRA, hard_cap=COMPACT_CEILING,
                             hours={"sonnet": 1.6}, local_stops=("cap", "wall")),
}  # fmt: skip


@dataclass(frozen=True)
class Layout:
    root: Path
    limit: Path = long_guard.LIMIT_FLAG

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def work(self) -> Path:
        return self.root / "w"

    @property
    def config(self) -> Path:
        return self.root / "cfg"

    @property
    def status(self) -> Path:
        return self.root / "long-run.status.json"


@dataclass(frozen=True)
class Ctx:
    layout: Layout
    profile: Profile
    model: str  # a key of run.MODELS
    claude: tuple[str, ...] = ("claude",)
    keyfile: Path | None = None
    ceiling: float = 0.0
    manifests: Path = MANIFESTS


@dataclass(frozen=True)
class ArmState:
    """What one call hands the next."""

    session: str | None = None
    usage: Mapping[str, Any] = field(default_factory=dict)  # modelUsage accounted so far
    seen: frozenset[str] = frozenset()  # transcript request ids metered so far
    diff: str = ""
    journal_lines: int = 0
    decisions: tuple[Mapping[str, Any], ...] = ()
    hook_lines: int = 0
    context: int = 0  # the last call's peak context (how big the next first turn may be)
    window: int | None = None  # the window the session reported


def log(message: str) -> None:
    """The runner's log: one line per event, to stdout (the launcher sends it to a file)."""
    print(f"{dt.datetime.now().strftime('%H:%M:%S')} {message}", flush=True)


# ---- arms ----------------------------------------------------------------------------------------


def arm_spec(arm: str, profile: Profile) -> run.Arm:
    if arm == "N":
        return run.ARM_SPECS["N"]
    if arm == "Ne":
        return run.Arm(None, env=((WINDOW, str(profile.window)),))
    if arm == "Nl":  # N-early-low: the window `install --context-budget 67000` writes
        return run.Arm(None, env=((WINDOW, str(window_for(COMPACT_LOW_BUDGET))),))
    if arm == "S":
        return run.Arm((*S_FLAGS, "--context-budget", str(profile.budget)), env=S_ENV)
    if arm in long_pilot.ARMS:
        return long_pilot.arm_spec(arm)
    raise SystemExit(f"unknown arm {arm}: N, Ne, Nl, S, A or A10")


def installed(arm: str, profile: Profile) -> bool:
    """S and the passages arms run hooks: a key, the install restored, Jev's facts."""
    return arm_spec(arm, profile).install is not None


def arm_order(name: str, arms: tuple[str, ...]) -> tuple[str, ...]:
    """The arms rotated by the chain's name (pre-mortem 22): no arm always runs first."""
    shift = int(hashlib.sha256(name.encode()).hexdigest(), 16) % len(arms)
    return arms[shift:] + arms[:shift]


def run_name(name: str, model: str) -> str:
    return f"{name}-{model}"


def token_of(chain: Mapping[str, Any], arm: str) -> str:
    """The chain's and arm's own control token (pre-mortem 21: a foreign one proves a leak)."""
    import long

    return long.token_for(f"{chain['chain']}/{arm}", long.texts_of(chain["bugs"]))


def with_control(chain: Mapping[str, Any], token: str, bugs: int | None) -> dict[str, Any]:
    """The chain as asked: its first `bugs` bugs, the token, prompts by `long.requests`."""
    kept = list(chain["bugs"])[:bugs] if bugs else list(chain["bugs"])
    return {**chain, "bugs": kept, "token": token, "grader": "per_bug"}


def asks_of(chain: Mapping[str, Any]) -> list[dict[str, Any]]:
    return run.requests_of(dict(chain))


# ---- before anything runs (long_start: start_refusal, midnight_refusal) -----------------------


def write_status(layout: Layout, base: Mapping[str, Any], **now: Any) -> None:
    layout.status.write_text(json.dumps({**base, **now, "updated": time.time()}, indent=1),
                             encoding="utf-8")  # fmt: skip


def own_status(layout: Layout) -> dict[str, Any]:
    """This runner's PID, command line and creation date, for a verified kill (pre-mortem 18)."""
    info = long_guard.process_info(os.getpid()) or {}
    return {"pid": os.getpid(), "command_line": info.get("command_line", ""),
            "created": info.get("created", ""), "root": str(layout.root)}  # fmt: skip


# ---- one arm -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Arm:
    """One arm of one chain, set up."""

    name: str  # run name: chain and model
    arm: str
    chain: Mapping[str, Any]  # as asked: bugs kept, token, per_bug prompts
    evidence: Path
    work: Path
    config: Path
    base: str
    mcp: Path
    env: Mapping[str, str]
    expect: long_guard.Expect
    asks: tuple[Mapping[str, Any], ...]


def prepare(ctx: Ctx, chain: Mapping[str, Any], arm: str) -> Arm:
    """A fresh working copy, configuration and evidence folder, set up as the arm says."""
    layout, name = ctx.layout, run_name(chain["chain"], ctx.model)
    evidence, work = layout.runs / name / arm, layout.work / f"{name}-{arm}"
    for folder in (evidence, work, layout.config / f"{name}-{arm}"):
        docker_env.remove_tree(folder)
    evidence.mkdir(parents=True)
    base = docker_env.export(chain["tag"], work)
    if (work / "changes").exists():
        raise RuntimeError(f"{name} {arm}: the repository already has changes/ (pre-mortem 21)")
    spec = arm_spec(arm, ctx.profile)
    mcp = work / ".mcp.json"
    if spec.install is not None:
        if ctx.keyfile is None:
            raise RuntimeError("an S arm needs the TypeSafe key")
        key = run.arm_keyfile(ctx.keyfile, name, arm)
        install = long_pilot.install if arm in long_pilot.ARMS else run.install_sancho
        install(work, evidence, key, spec.install)
        log(f"{name} {arm}: {arm_files.guard_parts(work)} ({run.SANCHO})")
    else:
        mcp.write_text('{"mcpServers": {}}\n', encoding="utf-8", newline="\n")
    if spec.env:
        arm_files.write_env_settings(work, spec.env)
        if spec.install is not None:  # else restore_install puts back the settings without it
            run.snapshot_install(work, evidence)
    return assemble(ctx, chain, arm, evidence, work, base)


def assemble(ctx: Ctx, chain: Mapping[str, Any], arm: str, evidence: Path, work: Path,
             base: str, resumed: bool = False) -> Arm:  # fmt: skip
    import perbug

    name = run_name(chain["chain"], ctx.model)
    token = token_of(chain, arm)
    if not resumed and (leaked := perbug.token_absent(work, token)):
        raise RuntimeError(f"{name} {arm}: the token is already in {leaked[:3]}")
    asked = with_control(chain, token, ctx.profile.bugs)
    config = carry.clean_config(ctx.layout.config / f"{name}-{arm}")
    servers = tuple(json.loads((work / ".mcp.json").read_text(encoding="utf-8"))
                    .get("mcpServers", {}))  # fmt: skip
    env = {**carry.environment(config, base=run.child_env(chain["tag"], base)),
           "ADOPT_LABEL": f"{name}-{arm}", "ADOPT_JEV_MAX_USD": f"{JEV_MAX_USD:.2f}"}
    expect = long_guard.Expect(carry.PIN, run.MODELS[ctx.model], long_call.PERMISSION_MODE,
                               servers)  # fmt: skip
    return Arm(name, arm, asked, evidence, work, config, base, work / ".mcp.json", env, expect,
               tuple(asks_of(asked)))  # fmt: skip


def configured_window(a: Arm) -> str | None:
    """The window the arm's project settings set: N-early's, or the one S's install wrote."""
    settings = a.work / ".claude" / "settings.json"
    if not settings.exists():
        return None
    return (json.loads(settings.read_text(encoding="utf-8")).get("env") or {}).get(WINDOW)


def row_base(ctx: Ctx, a: Arm) -> dict[str, Any]:
    window = configured_window(a)
    return {"chain": a.chain["chain"], "run": a.name, "arm": a.arm, "model": run.MODELS[ctx.model],
            "profile": ctx.profile.name, "base": a.base, "token": a.chain["token"],
            "bugs": len(a.chain["bugs"]), "requests_planned": len(a.asks),
            "window": {"value": int(window) if window else None,
                       "configured": int(window) if window else None,
                       "source": "settings env" if window else "server default"},
            "config": str(a.config), "work": str(a.work)}  # fmt: skip


def run_arm(ctx: Ctx, chain: Mapping[str, Any], arm: str, status: Mapping[str, Any],
            previous: Mapping[str, Any] | None = None) -> str:  # fmt: skip
    """The arm's calls in order, from its first or, with the row of an earlier runner, from where
    that one stopped; returns why it stopped early ("" when it ran to its end)."""
    if previous is None:
        a, rows, state, first, stop = prepare(ctx, chain, arm), [], ArmState(), 1, ""
    else:
        a, rows, state, first, stop = resume(ctx, chain, arm, previous)
        log(f"{a.name} {arm}: resumed at request {first} of {len(a.asks)} ({len(rows)} kept)")
    base = row_base(ctx, a)
    for k in range(first, len(a.asks) + 1) if not stop else ():
        write_status(ctx.layout, status, chain=a.name, arm=arm, request=k,
                     spent_owner_usd=spent(ctx.layout))  # fmt: skip
        stop = before_call(ctx, a, rows, state)
        if stop:
            rows = [*rows, *not_run(a.asks[k - 1:], k, stop)]
            break
        state, row, stop = one_call(ctx, a, state, k, a.asks[k - 1])
        rows = [*rows, row]
        arm_files.write_row(a.evidence, arm_files.partial_row(base, rows))
        log(f"{a.name} {arm} {k}/{len(a.asks)} {row['status']} {row.get('owner_usd', 0):.3f} USD "
            f"ctx {row.get('peak_context', 0)} compactions {len(row.get('compactions', []))}")
        if stop:
            rows = [*rows, *not_run(a.asks[k:], k + 1, stop)]
            break
    finish(ctx, a, base, rows, stop)
    return stop


def resume(ctx: Ctx, chain: Mapping[str, Any], arm: str, row: Mapping[str, Any]
           ) -> tuple[Arm, list[dict[str, Any]], ArmState, int, str]:  # fmt: skip
    """The arm as the earlier runner left it (`long_resume`): its working copy, configuration
    and session, the calls kept, a half-done call settled, and the next request."""
    layout, name = ctx.layout, run_name(chain["chain"], ctx.model)
    evidence, work = layout.runs / name / arm, layout.work / f"{name}-{arm}"
    if not (work / ".git").exists():
        raise RuntimeError(f"{name} {arm}: no working copy at {work} to resume in")
    if arm_spec(arm, ctx.profile).install is not None:
        if ctx.keyfile is None:
            raise RuntimeError("an S arm needs the TypeSafe key")
        run.arm_keyfile(ctx.keyfile, name, arm)  # the hooks read it at this path again
    a = assemble(ctx, chain, arm, evidence, work, str(row["base"]), resumed=True)
    if a.chain["token"] != row.get("token"):
        raise RuntimeError(f"{name} {arm}: the row's token is not this arm's")
    rows = long_resume.ask_limited_again(long_resume.kept(row), evidence, a.chain["split"])
    journal, hooks = evidence / "journal.jsonl", evidence / "hooks.jsonl"
    state = ArmState(long_resume.session_of(rows), long_resume.usage_of(rows),
                     long_resume.seen_of(rows), docker_env.agent_diff(work, a.base),
                     _lines(journal), tuple(long_guard.decisions(journal)),
                     _lines(hooks), long_resume.context_of(rows),
                     long_resume.window_of(rows))  # fmt: skip
    k = long_resume.next_request(rows)
    dead = long_resume.dead_stream(evidence, k, rows) if k <= len(a.asks) else None
    if dead is None:
        return a, rows, state, k, ""
    return settle_dead(ctx, a, state, rows, k, dead)


def _lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0

def settle_dead(ctx: Ctx, a: Arm, state: ArmState, rows: list[dict[str, Any]], k: int,
                stream: Path) -> tuple[Arm, list[dict[str, Any]], ArmState, int, str]:  # fmt: skip
    """The call a dead runner left half done: a cut call (pre-mortem 4), charged its caps. Its
    stream is kept as `stream-<k>-dead.jsonl` (a retry writes `stream-<k>.jsonl` again)."""
    stream = stream.replace(stream.with_name(f"stream-{k}-dead.jsonl"))
    facts = long_call.stream_facts(stream)
    before = a.evidence / f"diff-{k - 1}.patch"
    previous = before.read_text(encoding="utf-8") if k > 1 and before.exists() else ""
    decision = long_guard.resume_decision(facts["tool_uses"], previous, state.diff,
                                          a.chain["split"])  # fmt: skip
    session = facts["session"] or state.session
    new = long_call.new_requests(long_call.transcript_of(arm_files.projects_root(a.env),
                                                         session or ""), state.seen)  # fmt: skip
    cap, model = ctx.profile.call_cap[ctx.model], run.MODELS[ctx.model]
    usage = long_call.usage_sum(dict(state.usage), long_call.usage_of(new))
    money = {**long_call.charged_cap(cap, meter.claude_code_cap(cap, model)),
             "metered_ids": sorted(r.id for r in new), "usage_after": usage}  # fmt: skip
    row = long_resume.dead_row(k, a.asks[k - 1], facts, decision, money, stream)
    log(f"{a.name} {a.arm} {k}: the runner died in this call; {decision}")
    if decision != "retry":
        (a.evidence / f"diff-{k}.patch").write_text(state.diff, encoding="utf-8", newline="\n")
    state = replace(state, session=session, usage=usage, seen=state.seen | {r.id for r in new})
    stop = "set aside" if decision == "set-aside" else ""
    return a, [*rows, row], state, k if decision == "retry" else k + 1, stop


def not_run(asks: tuple[Mapping[str, Any], ...], first: int, why: str) -> list[dict[str, Any]]:
    return [{"request": j, "kind": q["kind"], "instance_id": q["instance_id"],
             "status": f"NOT RUN ({why})", "owner_usd": 0.0} for j, q in enumerate(asks, first)]


def turn_over(ctx: Ctx, a: Arm, state: ArmState) -> float:
    """One turn past the budget the next call may spend (`long_money.overshoot`)."""
    window = configured_window(a)
    return long_money.overshoot(run.MODELS[ctx.model], state.context,
                                int(window) if window else state.window)  # fmt: skip


def before_call(ctx: Ctx, a: Arm, rows: list[dict[str, Any]], state: ArmState) -> str:
    """Why the next call may not start: stop files, Docker, disk, caps, wall, ceiling. Every cap
    holds room for the call's cap AND one more turn: Claude Code stops between turns only."""
    layout, cap = ctx.layout, ctx.profile.call_cap[ctx.model]
    if why := long_guard.stop_reason(layout.root, layout.limit):
        return "limit" if "LIMIT" in why else "harness"
    if (why := docker_env.health()) or (why := long_guard.disk_refusal(layout.root)):
        log(f"{a.name} {a.arm}: {why}")
        (layout.root / long_guard.STOP_FILE).write_text(why, encoding="utf-8")
        return "harness"
    over = turn_over(ctx, a, state)
    chain_spent = sum(r.get("owner_usd", 0.0) for r in rows)
    why = long_money.room_refusal(chain_spent, cap, over, ctx.profile.chain_cap[ctx.model],
                                  "chain cap") or ("call cap: no room for one turn" if cap - over
                                                   < long_money.MIN_BUDGET else "")  # fmt: skip
    if why:
        log(f"{a.name} {a.arm}: {why} (logged)")
        return "cap"
    if sum(r.get("wall_s", 0.0) for r in rows) > ctx.profile.wall_s:
        return "wall"
    if why := long_money.room_refusal(spent(layout), cap, over, ctx.ceiling, "ceiling"):
        log(f"{a.name} {a.arm}: {why}")
        return "ceiling"
    return ""


# ---- one call ------------------------------------------------------------------------------------


def timeout_for(profile: Profile, arm: str, k: int) -> float:
    forced = [s for a, r, s in profile.forced_timeouts if a == arm and r == k]
    return forced[0] if forced else profile.timeout_s


def one_call(ctx: Ctx, a: Arm, state: ArmState, k: int,
             ask: Mapping[str, Any]) -> tuple[ArmState, dict[str, Any], str]:  # fmt: skip
    """The call, retried once when a cut left nothing behind (pre-mortem 4)."""
    attempt = attempt_call(ctx, a, state, k, ask, retry=False)
    if attempt["cut"] and attempt["decision"] == "retry":
        log(f"{a.name} {a.arm} {k}: cut ({attempt['why']}) with no tool and no change: retried")
        state = attempt["state"]
        first = attempt["stream"].name
        attempt = {**attempt_call(ctx, a, state, k, ask, retry=True), "retried": True}
        attempt = {**attempt, "streams": [first, attempt["stream"].name]}
    return settle(ctx, a, k, ask, attempt)


def attempt_call(ctx: Ctx, a: Arm, state: ArmState, k: int, ask: Mapping[str, Any],
                 retry: bool) -> dict[str, Any]:  # fmt: skip
    restored = run.restore_install(a.work, a.evidence) if installed(a.arm, ctx.profile) else []
    suffix = "-retry" if retry else ""
    stream = a.evidence / f"stream-{k}{suffix}.jsonl"
    debug = long_window.debug_path(a.evidence, k, retry)
    cap = ctx.profile.call_cap[ctx.model]
    budget = round(cap - turn_over(ctx, a, state), 4)  # the call's last turn ends under `cap`
    cmd = long_call.command(ctx.claude, run.MODELS[ctx.model], ask["prompt"], state.session,
                            meter.claude_code_cap(budget, run.MODELS[ctx.model]), a.mcp,
                            debug)  # fmt: skip
    timeout = timeout_for(ctx.profile, a.arm, k) if not retry else ctx.profile.timeout_s
    code, seconds, why = long_call.invoke(cmd, a.work, dict(a.env), ask["prompt"], stream,
                                          timeout, ctx.profile.idle_s)  # fmt: skip
    facts = long_call.stream_facts(stream)
    long_window.trim_debug(debug)
    window = long_window.call_window(debug, a.config, configured_window(a))
    diff = docker_env.agent_diff(a.work, a.base)
    docker_env.remove_labelled(f"{a.name}-{a.arm}")
    cut = code == -9 or (facts["subtype"] is None and code != 0)
    decision = long_guard.resume_decision(facts["tool_uses"], state.diff, diff,
                                          a.chain["split"]) if cut else ""  # fmt: skip
    return {"code": code, "seconds": seconds, "why": why or (f"exit {code}" if cut else ""),
            "facts": facts, "diff": diff, "cut": cut, "decision": decision, "restored": restored,
            "window": window, "budget_owner": budget,
            "state": replace(state, session=facts["session"] or state.session), "stream": stream}


def settle(ctx: Ctx, a: Arm, k: int, ask: Mapping[str, Any],
           attempt: Mapping[str, Any]) -> tuple[ArmState, dict[str, Any], str]:  # fmt: skip
    """The call's row, the state for the next call, and why the arm stops ("" to go on)."""
    facts, state = attempt["facts"], attempt["state"]
    (a.evidence / f"diff-{k}.patch").write_text(attempt["diff"], encoding="utf-8", newline="\n")
    seen_before = state.seen
    money, state = meter_call(ctx, a, state, attempt)
    s_facts, state = s_arm_facts(a, state) if installed(a.arm, ctx.profile) else ({}, state)
    row = {"request": k, "kind": ask["kind"], "instance_id": ask["instance_id"],
           "exit": attempt["code"], "wall_s": attempt["seconds"], "status": status_of(attempt),
           **{key: facts[key] for key in ("session", "subtype", "is_error", "init", "tools",
                                          "tool_uses", "compactions", "limits", "denials")},
           "cost_cc_cumulative": facts["cost_cc_cumulative"], "install_restored":
           attempt["restored"], "retried": bool(attempt.get("retried")),
           **({"deviation": f"cut ({attempt['why']}) after tools or changes: went on"}
              if attempt["cut"] and attempt["decision"] == "continue" else {}),
           "result_tail": facts.get("result_tail", ""), "window_reported": attempt["window"],
           "budget_owner": attempt["budget_owner"],
           "streams": attempt.get("streams") or [attempt["stream"].name],
           **money, **s_facts, "usage_after": dict(state.usage),
           "metered_ids": sorted(state.seen - seen_before)}  # fmt: skip
    row = {**row, "breaks": list(call_breaks(a, row, attempt, state))}
    stop = stop_of(ctx, a, row, attempt)
    return replace(state, diff=attempt["diff"], context=int(row.get("peak_context") or 0) or
                   state.context, window=(attempt["window"] or {}).get("window") or
                   state.window), row, stop  # fmt: skip


def status_of(attempt: Mapping[str, Any]) -> str:
    facts = attempt["facts"]
    if facts["is_error"] and facts["limits"]:
        return "error result (limit)"
    if not attempt["cut"]:
        return "ran"
    return "SET ASIDE" if attempt["decision"] == "set-aside" else f"cut ({attempt['why']})"


def meter_call(ctx: Ctx, a: Arm, state: ArmState,
               attempt: Mapping[str, Any]) -> tuple[dict[str, Any], ArmState]:  # fmt: skip
    """Owner and Claude Code dollars of the call; a cut call is charged its caps."""
    facts, model = attempt["facts"], run.MODELS[ctx.model]
    root = arm_files.projects_root(a.env)
    new = long_call.new_requests(long_call.transcript_of(root, state.session or ""), state.seen)
    seen = state.seen | {r.id for r in new}
    if attempt["cut"] or not facts["model_usage"]:
        cap = ctx.profile.call_cap[ctx.model]
        usage = long_call.usage_sum(dict(state.usage), long_call.usage_of(new))
        money = long_call.charged_cap(cap, meter.claude_code_cap(cap, model))
        return money, replace(state, seen=seen, usage=usage)
    money = long_call.metered(new, facts["model_usage"], dict(state.usage))
    return money, replace(state, seen=seen, usage=facts["model_usage"])


def s_arm_facts(a: Arm, state: ArmState) -> tuple[dict[str, Any], ArmState]:
    """Jev's decisions and the hooks' errors during the call (S only)."""
    journal, hooks = a.evidence / "journal.jsonl", a.evidence / "hooks.jsonl"
    new = long_guard.decisions(journal, state.journal_lines)
    lines = journal.read_text(encoding="utf-8").splitlines() if journal.exists() else []
    hook_rows = [json.loads(x) for x in (hooks.read_text(encoding="utf-8").splitlines()
                                         if hooks.exists() else [])[state.hook_lines:] if x]
    errors = sum(1 for h in hook_rows if h.get("exit") not in (0, None))
    facts = {"jev_decisions": len(new), "jev_failed": sum(long_guard.failed(d) for d in new),
             "jev_usd_chain": round(run.jev_usd(a.evidence), 6), "hook_calls": len(hook_rows),
             "hook_errors": errors, **(long_pilot.call_facts(journal, state.journal_lines)
                                       if a.arm in long_pilot.ARMS else {})}  # fmt: skip
    total_hooks = state.hook_lines + len(hook_rows)
    return facts, replace(state, journal_lines=len(lines), hook_lines=total_hooks,
                          decisions=(*state.decisions, *new))  # fmt: skip


def call_breaks(a: Arm, row: Mapping[str, Any], attempt: Mapping[str, Any],
                state: ArmState) -> tuple[str, ...]:  # fmt: skip
    """Invariants the call broke; any one stops the arm and writes the STOP file."""
    out = list(long_guard.init_breaks(row["init"], a.expect)) if not attempt["cut"] else []
    if long_guard.diff_vanished(state.diff, attempt["diff"]):
        out.append("the diff came back empty after a non-empty one (pre-mortem 13)")
    if a.arm != "N" and long_guard.jev_outage(list(state.decisions)):
        out.append("Jev: the first decisions all failed or null (pre-mortem 15)")
    if a.arm == "Nl":
        out.extend(low_window_breaks(row))
    hooks = row.get("hook_calls", 0)
    if hooks and row.get("hook_errors", 0) / hooks > HOOK_ERRORS:
        out.append(f"hooks: {row['hook_errors']} of {hooks} calls ended in error")
    return tuple(out)


def low_window_breaks(row: Mapping[str, Any]) -> list[str]:
    """Nl not compacting where the prereg says: a compaction outside `LOW_PRE`, or a call whose
    context passed `LOW_PEAK` (the window never took)."""
    low, high = LOW_PRE
    out = [f"Nl compacted at {c.get('pre')} tokens, outside {low}-{high}"
           for c in row.get("compactions") or [] if not low <= int(c.get("pre") or 0) <= high]
    peak = int(row.get("peak_context") or 0)
    return [*out, *([f"Nl reached {peak} tokens of context, past {LOW_PEAK}"]
                    if peak > LOW_PEAK else [])]  # fmt: skip


def stop_of(ctx: Ctx, a: Arm, row: Mapping[str, Any], attempt: Mapping[str, Any]) -> str:
    if row["limits"]:
        long_guard.raise_limit(ctx.layout.limit, f"{a.name} {a.arm} {row['request']}: "
                               f"{row['limits']}")  # fmt: skip
        return "limit"
    if row["breaks"]:
        (ctx.layout.root / long_guard.STOP_FILE).write_text("\n".join(row["breaks"]),
                                                            encoding="utf-8")  # fmt: skip
        log(f"{a.name} {a.arm}: STOP: {row['breaks']}")
        return "harness"
    if attempt["cut"] and attempt["decision"] == "set-aside":
        return "set aside"
    if why := long_pilot.rerequest_stop((row.get("passages") or {}).get("arm") or {}):
        log(f"{a.name} {a.arm}: STOP: {why}")
        return "rerequest"
    if row.get("jev_usd_chain", 0.0) >= JEV_MAX_USD:
        log(f"{a.name} {a.arm}: Jev reached its {JEV_MAX_USD} USD ceiling; hooks fail open now")
    return ""


def finish(ctx: Ctx, a: Arm, base: Mapping[str, Any], rows: list[dict[str, Any]],
           stop: str) -> None:  # fmt: skip
    final = docker_env.agent_diff(a.work, a.base)
    (a.evidence / "final.patch").write_text(final, encoding="utf-8", newline="\n")
    sessions = [r.get("session") or "" for r in rows]
    missing = arm_files.copy_transcripts(sessions, a.evidence, arm_files.projects_root(a.env))
    ran = [r for r in rows if not str(r.get("status", "")).startswith("NOT RUN")]
    row = {**base, "calls": rows, "partial": False, "stopped": stop,
           "owner_usd": round(sum(r.get("owner_usd", 0.0) for r in rows), 6),
           "cc_usd": round(sum(r.get("cc_usd", 0.0) for r in rows), 6),
           "permission_modes": sorted({(r.get("init") or {}).get("permission_mode") or "?"
                                       for r in ran}),
           "jev_usd": run.jev_usd(a.evidence), "missing_transcripts": missing,
           **(long_pilot.row_facts(a.evidence) if a.arm in long_pilot.ARMS else {}),
           "window": {**base["window"], **long_window.arm_window(ran, configured_window(a))}}
    arm_files.write_row(a.evidence, row)
    long_window.record(ctx.layout.root, run.MODELS[ctx.model], a.arm, row["window"])


# ---- chains --------------------------------------------------------------------------------------


def run_chain(ctx: Ctx, chain: Mapping[str, Any], status: Mapping[str, Any]) -> str:
    for arm in arm_order(chain["chain"], ctx.profile.arms):
        row = long_resume.read_row(ctx.layout.runs / run_name(chain["chain"], ctx.model) / arm)
        if row is not None and not long_resume.may_resume(row):
            log(f"{chain['chain']} {ctx.model} {arm}: done ({row.get('stopped') or 'to its end'})"
                "; never run twice")
            continue
        stop = run_arm(ctx, chain, arm, status, row)
        if stop and stop in ctx.profile.local_stops:
            log(f"{chain['chain']} {ctx.model} {arm}: stopped ({stop}); the next arm goes on")
        elif stop:
            return stop
        if why := long_guard.cross_arm_breaks(ctx.layout.runs / run_name(chain["chain"],
                                                                         ctx.model)):
            (ctx.layout.root / long_guard.STOP_FILE).write_text(why, encoding="utf-8")
            log(f"{chain['chain']}: STOP: {why}")
            return "harness"
    return ""


def load_chains(path: Path | None) -> dict[str, Any]:
    if path is None:
        return run.chains()
    return json.loads(path.read_text(encoding="utf-8"))


def keyfile_for(profile: Profile, layout: Layout) -> Path | None:
    """The TypeSafe key for S's hooks, written under the root and removed at the end."""
    if not any(installed(arm, profile) for arm in profile.arms):
        return None
    key = carry.from_indagis_env("TYPESAFE_API_KEY")
    if not key:
        raise SystemExit("no TypeSafe key: the S arm would run without its decider")
    path = layout.root / f"typesafe-{os.getpid()}.key"
    path.write_text(key, encoding="utf-8")
    return path


def run_all(ctx: Ctx, names: list[str], known: Mapping[str, Any], models: list[str],
            allow_midnight: bool) -> int:  # fmt: skip
    status = own_status(ctx.layout)
    for model in models:
        c = replace(ctx, model=model)
        for name in names:
            if why := midnight_refusal(ctx.profile, model, allow_midnight):
                log(f"{name} {model}: refused: {why}")
                return 1
            log(f"{name} {model}: start, spent so far {spent(ctx.layout):.2f} USD")
            if stop := run_chain(c, known[name], status):
                log(f"{name} {model}: stopped ({stop})")
                return EXIT.get(stop, 4)
    log(f"done; spent under the root {spent(ctx.layout):.2f} USD (owner prices)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    layout = Layout(Path(args.root), Path(args.limit_flag))
    if args.action == "kill":
        status = json.loads(layout.status.read_text(encoding="utf-8"))
        log(long_guard.verified_kill(status))
        return 0
    profile = PROFILES[args.profile].with_arms(tuple(a for a in args.arms.split(",") if a))
    known = load_chains(Path(args.chains_file) if args.chains_file else None)
    names = [c for c in args.chains.split(",") if c] or list(profile.chains)
    models = [args.model] if args.model else list(profile.models)
    ctx = Ctx(layout, profile, models[0], tuple(json.loads(args.claude)),
              ceiling=ceiling_of(profile, args.ceiling), manifests=Path(args.manifests))
    if args.action == "plan":
        return plan(ctx, names, known, models)
    if args.action == "grade":
        import long_report

        return long_report.grade_all(layout, names, known, models, profile.arms)
    carry.ignore_interrupts()
    if why := start_refusal(ctx, names, known, models):
        log(f"refused: {why}")
        return 1
    ctx = replace(ctx, keyfile=keyfile_for(profile, layout))
    try:
        # Free (no question is sent). "JevDecider from <path>" is an editable install; the
        # launcher holds the paid runs to a frozen copy (`long_launch.frozen_sancho`).
        found = run.decider_probe(ctx.keyfile) if ctx.keyfile else run.HELD_DECIDER
        if found.split(" ", 1)[0] != run.HELD_DECIDER:
            log(f"refused: S's hooks would build {found}, not {run.HELD_DECIDER} ({run.SANCHO})")
            return 1
        return run_all(ctx, names, known, models, args.allow_midnight)
    finally:
        if ctx.keyfile:
            ctx.keyfile.unlink(missing_ok=True)
        run.drop_arm_keys()


def plan(ctx: Ctx, names: list[str], known: Mapping[str, Any], models: list[str]) -> int:
    holding, outside = held(ctx.layout, ctx.profile, names, models)
    for name, model, cap in holding:
        found = known.get(name, {})
        log(f"{name} {model}: {len(found.get('bugs', []))} bugs, valid {found.get('valid')}, "
            f"arms {ctx.profile.arms}, caps held {cap:.2f} USD")
    why = long_guard.plan_refusal(holding, ctx.ceiling, outside)
    log(f"ceiling {ctx.ceiling} USD; {why or 'the caps fit'}")
    return 1 if why else 0


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("plan", "run", "grade", "kill"))
    parser.add_argument("--profile", default="gate", choices=sorted(PROFILES))
    parser.add_argument("--model", default=None, choices=sorted(run.MODELS))
    parser.add_argument("--chains", default="")
    parser.add_argument("--arms", default="", help="the profile's arms instead (its choices)")
    parser.add_argument("--chains-file", default="")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--limit-flag", default=str(long_guard.LIMIT_FLAG))
    parser.add_argument("--ceiling", type=float, default=0.0, help="owner USD; the profile's")
    parser.add_argument("--claude", default='["claude"]', help="the command, as a JSON list")
    parser.add_argument("--allow-midnight", action="store_true")
    parser.add_argument("--manifests", default=str(MANIFESTS), help="long60/<chain>.json folder")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
