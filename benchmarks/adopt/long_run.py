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

Exit codes: 0 ran to its end; 1 refused before any call; 2 the usage limit, a cap or the
ceiling; 3 a chain set aside (a cut call of a held-out chain); 4 the harness (a STOP file, a
broken invariant, Docker, the disk, a diff that vanished, Jev down).
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
import meter  # noqa: E402
import run  # noqa: E402

ROOT = Path(r"C:\sp-runs\L")  # outside the home folder: carry.refuse_unclean; short for MAX_PATH
WINDOW = "CLAUDE_CODE_AUTO_COMPACT_WINDOW"
EXIT = {"limit": 2, "cap": 2, "ceiling": 2, "wall": 2, "set aside": 3, "harness": 4}
# The sealed S line (docs/S-SEAL-DRAFT.md, S0 for code suites); its budget is the profile's.
S_FLAGS = ("--guard", "--guard-profile", "coding", "--memory", "--candor", "--find",
           "--find-auto", "--skill", "--scan-content", "--check-done", "--content-tools",
           "WebFetch,WebSearch,mcp__sanchopanza-fetch__fetch_passages", "--crawl", "--prune",
           "--fetch", "--provider", "jev")  # fmt: skip
S_ENV = (("SANCHOPANZA_GUARD_CHOOSER", "keep"), ("SANCHOPANZA_CANDOR_MODE", "observe"),
         ("SANCHOPANZA_CRAWL_LINE_VERSION", "6"), ("SANCHOPANZA_CRAWL_NOTES", "3"),
         ("SANCHOPANZA_CRAWL_ECHO", "short"), ("SANCHOPANZA_CRAWL_LINE_AT", "prompt"),
         ("SANCHOPANZA_CRAWL_NOTES_AT", "front"), ("SANCHOPANZA_CRAWL_SHOT", "snapshot-first"),
         ("SANCHOPANZA_FETCH_VERSION", "2"))  # fmt: skip
GATE_CALL_CAP = {"sonnet": 4.5, "opus": 8.0}  # owner USD; B2 ran 4.5 per call on Sonnet
GATE_CHAIN_CAP = {"sonnet": 38.0, "opus": 48.0}  # pre-mortem e: 2x38 + 2x48 = 172 <= 175
GATE_CEILING = 175.0
GATE_CHAINS = ("conan-io__conan-long60-1", "pydantic__pydantic-long60-1")
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
    window: int = 193_000  # N-early's window: S's for --context-budget 160000
    budget: int = 160_000  # S's --context-budget
    forced_timeouts: tuple[tuple[str, int, float], ...] = ()  # (arm, request, seconds)
    hours: Mapping[str, float] = field(default_factory=dict)  # expected per arm (midnight rule)


PROFILES = {
    "gate": Profile("gate", ("N",), ("sonnet", "opus"), GATE_CALL_CAP, GATE_CHAIN_CAP,
                    GATE_CEILING, GATE_CHAINS, hours={"sonnet": 1.6, "opus": 2.7}),
    "dev": Profile("dev", ("N", "Ne", "S"), ("sonnet", "opus"), GATE_CALL_CAP, GATE_CHAIN_CAP,
                   980.0, (), hours={"sonnet": 1.6, "opus": 2.7}),
    # Verification item 3: Haiku, 3 bugs, N-early at Claude Code's 100k floor (compacts near
    # 67k), S at --context-budget 67000, one N call cut at 90 s; hard cap 8 USD.
    "smoke": Profile("smoke", ("N", "Ne", "S"), ("haiku",), {"haiku": 1.0}, {"haiku": 2.0}, 8.0,
                     ("pydantic__pydantic-long40-1",), hard_cap=8.0, bugs=3, window=100_000,
                     budget=67_000, forced_timeouts=(("N", 2, 90.0),), hours={"haiku": 0.5}),
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


def log(message: str) -> None:
    """The runner's log: one line per event, to stdout (the launcher sends it to a file)."""
    print(f"{dt.datetime.now().strftime('%H:%M:%S')} {message}", flush=True)


# ---- arms ----------------------------------------------------------------------------------------


def arm_spec(arm: str, profile: Profile) -> run.Arm:
    if arm == "N":
        return run.ARM_SPECS["N"]
    if arm == "Ne":
        return run.Arm(None, env=((WINDOW, str(profile.window)),))
    if arm == "S":
        return run.Arm((*S_FLAGS, "--context-budget", str(profile.budget)), env=S_ENV)
    raise SystemExit(f"unknown arm {arm}: N, Ne or S")


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


# ---- money ---------------------------------------------------------------------------------------


def rows_under(layout: Layout) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(layout.runs.glob("*/*/row.json")):
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return rows


def spent(layout: Layout) -> float:
    """Owner USD of every call under the root, earlier runs included."""
    return round(sum(c.get("owner_usd", 0.0) for r in rows_under(layout) for c in r["calls"]), 6)


def blocks(profile: Profile, names: list[str], models: list[str]) -> list[tuple[str, str, float]]:
    return [(n, m, profile.chain_cap[m] * len(profile.arms)) for m in models for n in names]


def ceiling_of(profile: Profile, asked: float) -> float:
    ceiling = asked if asked > 0 else profile.ceiling
    if profile.hard_cap is not None and ceiling > profile.hard_cap:
        raise SystemExit(f"{profile.name}: the ceiling is at most {profile.hard_cap} USD (in code)")
    return ceiling


# ---- before anything runs ------------------------------------------------------------------------


def start_refusal(ctx: Ctx, names: list[str], known: Mapping[str, Any],
                  models: list[str]) -> str:  # fmt: skip
    """Why the run may not start ("" when it may). Free: no model is asked anything."""
    layout, profile = ctx.layout, ctx.profile
    if unknown := [n for n in names if n not in known]:
        return f"unknown chains {unknown}"
    if invalid := [n for n in names if not known[n].get("valid")]:
        return f"invalid chains {invalid}"
    if why := long_guard.stop_reason(layout.root, layout.limit):
        return why
    if why := long_guard.plan_refusal(blocks(profile, names, models), ctx.ceiling, spent(layout)):
        return why
    if why := docker_env.health():
        return why
    layout.root.mkdir(parents=True, exist_ok=True)
    if why := long_guard.disk_refusal(layout.root):
        return why
    carry.refuse_unclean(layout.root)  # no token, or memory files above the run root: exits
    carry.record_claude(layout.root, False, True, ctx.claude)  # not 2.1.287: exits
    return ""


def midnight_refusal(profile: Profile, model: str, allow: bool) -> str:
    hours = profile.hours.get(model, 4.0) * len(profile.arms)
    if not allow and long_guard.crosses_midnight(dt.datetime.now(), hours):
        return f"a chain of ~{hours:.1f} h started now would cross midnight (pre-mortem 6)"
    return ""


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
        run.install_sancho(work, evidence, key, spec.install)
    else:
        mcp.write_text('{"mcpServers": {}}\n', encoding="utf-8", newline="\n")
    if spec.env:
        arm_files.write_env_settings(work, spec.env)
        if spec.install is not None:  # else restore_install puts back the settings without it
            run.snapshot_install(work, evidence)
    return assemble(ctx, chain, arm, evidence, work, base)


def assemble(ctx: Ctx, chain: Mapping[str, Any], arm: str, evidence: Path, work: Path,
             base: str) -> Arm:  # fmt: skip
    import perbug

    name = run_name(chain["chain"], ctx.model)
    token = token_of(chain, arm)
    if leaked := perbug.token_absent(work, token):
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


def row_base(ctx: Ctx, a: Arm) -> dict[str, Any]:
    window = dict(arm_spec(a.arm, ctx.profile).env).get(WINDOW)
    return {"chain": a.chain["chain"], "run": a.name, "arm": a.arm, "model": run.MODELS[ctx.model],
            "profile": ctx.profile.name, "base": a.base, "token": a.chain["token"],
            "bugs": len(a.chain["bugs"]), "requests_planned": len(a.asks),
            "window": {"value": window, "source": "settings env" if window else "server default"},
            "config": str(a.config), "work": str(a.work)}  # fmt: skip


def run_arm(ctx: Ctx, chain: Mapping[str, Any], arm: str, status: Mapping[str, Any]) -> str:
    """The arm's calls in order; returns why it stopped early ("" when it ran to its end)."""
    a = prepare(ctx, chain, arm)
    base = row_base(ctx, a)
    rows: list[dict[str, Any]] = []
    state, stop = ArmState(), ""
    for k, ask in enumerate(a.asks, start=1):
        write_status(ctx.layout, status, chain=a.name, arm=arm, request=k,
                     spent_owner_usd=spent(ctx.layout))  # fmt: skip
        stop = before_call(ctx, a, rows)
        if stop:
            rows = [*rows, *not_run(a.asks[k - 1:], k, stop)]
            break
        state, row, stop = one_call(ctx, a, state, k, ask)
        rows = [*rows, row]
        arm_files.write_row(a.evidence, arm_files.partial_row(base, rows))
        log(f"{a.name} {arm} {k}/{len(a.asks)} {row['status']} {row.get('owner_usd', 0):.3f} USD "
            f"ctx {row.get('peak_context', 0)} compactions {len(row.get('compactions', []))}")
        if stop:
            rows = [*rows, *not_run(a.asks[k:], k + 1, stop)]
            break
    finish(ctx, a, base, rows, stop)
    return stop


def not_run(asks: tuple[Mapping[str, Any], ...], first: int, why: str) -> list[dict[str, Any]]:
    return [{"request": j, "kind": q["kind"], "instance_id": q["instance_id"],
             "status": f"NOT RUN ({why})", "owner_usd": 0.0} for j, q in enumerate(asks, first)]


def before_call(ctx: Ctx, a: Arm, rows: list[dict[str, Any]]) -> str:
    """Why the next call may not start: stop files, Docker, disk, caps, wall, ceiling."""
    layout, cap = ctx.layout, ctx.profile.call_cap[ctx.model]
    if why := long_guard.stop_reason(layout.root, layout.limit):
        return "limit" if "LIMIT" in why else "harness"
    if (why := docker_env.health()) or (why := long_guard.disk_refusal(layout.root)):
        log(f"{a.name} {a.arm}: {why}")
        (layout.root / long_guard.STOP_FILE).write_text(why, encoding="utf-8")
        return "harness"
    chain_spent = sum(r.get("owner_usd", 0.0) for r in rows)
    if chain_spent + cap > ctx.profile.chain_cap[ctx.model]:
        log(f"{a.name} {a.arm}: chain cap {ctx.profile.chain_cap[ctx.model]} reached (logged)")
        return "cap"
    if sum(r.get("wall_s", 0.0) for r in rows) > ctx.profile.wall_s:
        return "wall"
    if spent(layout) + cap > ctx.ceiling:
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
        attempt = {**attempt_call(ctx, a, state, k, ask, retry=True), "retried": True}
    return settle(ctx, a, k, ask, attempt)


def attempt_call(ctx: Ctx, a: Arm, state: ArmState, k: int, ask: Mapping[str, Any],
                 retry: bool) -> dict[str, Any]:  # fmt: skip
    restored = run.restore_install(a.work, a.evidence) if a.arm == "S" else []
    suffix = "-retry" if retry else ""
    stream = a.evidence / f"stream-{k}{suffix}.jsonl"
    cap = ctx.profile.call_cap[ctx.model]
    cmd = long_call.command(ctx.claude, run.MODELS[ctx.model], ask["prompt"], state.session,
                            meter.claude_code_cap(cap, run.MODELS[ctx.model]), a.mcp)  # fmt: skip
    timeout = timeout_for(ctx.profile, a.arm, k) if not retry else ctx.profile.timeout_s
    code, seconds, why = long_call.invoke(cmd, a.work, dict(a.env), ask["prompt"], stream,
                                          timeout, ctx.profile.idle_s)  # fmt: skip
    facts = long_call.stream_facts(stream)
    diff = docker_env.agent_diff(a.work, a.base)
    docker_env.remove_labelled(f"{a.name}-{a.arm}")
    cut = code == -9 or (facts["subtype"] is None and code != 0)
    decision = long_guard.resume_decision(facts["tool_uses"], state.diff, diff,
                                          a.chain["split"]) if cut else ""  # fmt: skip
    return {"code": code, "seconds": seconds, "why": why or (f"exit {code}" if cut else ""),
            "facts": facts, "diff": diff, "cut": cut, "decision": decision, "restored": restored,
            "state": replace(state, session=facts["session"] or state.session), "stream": stream}


def settle(ctx: Ctx, a: Arm, k: int, ask: Mapping[str, Any],
           attempt: Mapping[str, Any]) -> tuple[ArmState, dict[str, Any], str]:  # fmt: skip
    """The call's row, the state for the next call, and why the arm stops ("" to go on)."""
    facts, state = attempt["facts"], attempt["state"]
    (a.evidence / f"diff-{k}.patch").write_text(attempt["diff"], encoding="utf-8", newline="\n")
    money, state = meter_call(ctx, a, state, attempt)
    s_facts, state = s_arm_facts(a, state) if a.arm == "S" else ({}, state)
    row = {"request": k, "kind": ask["kind"], "instance_id": ask["instance_id"],
           "exit": attempt["code"], "wall_s": attempt["seconds"], "status": status_of(attempt),
           **{key: facts[key] for key in ("session", "subtype", "is_error", "init", "tools",
                                          "tool_uses", "compactions", "limits", "denials")},
           "cost_cc_cumulative": facts["cost_cc_cumulative"], "install_restored":
           attempt["restored"], "retried": bool(attempt.get("retried")),
           **({"deviation": f"cut ({attempt['why']}) after tools or changes: went on"}
              if attempt["cut"] and attempt["decision"] == "continue" else {}),
           **money, **s_facts}  # fmt: skip
    row = {**row, "breaks": list(call_breaks(a, row, attempt, state))}
    stop = stop_of(ctx, a, row, attempt)
    return replace(state, diff=attempt["diff"]), row, stop


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
             "hook_errors": errors}  # fmt: skip
    total_hooks = state.hook_lines + len(hook_rows)
    return facts, replace(state, journal_lines=len(lines), hook_lines=total_hooks,
                          decisions=(*state.decisions, *new))  # fmt: skip


def call_breaks(a: Arm, row: Mapping[str, Any], attempt: Mapping[str, Any],
                state: ArmState) -> tuple[str, ...]:  # fmt: skip
    """Invariants the call broke; any one stops the arm and writes the STOP file."""
    out = list(long_guard.init_breaks(row["init"], a.expect)) if not attempt["cut"] else []
    if long_guard.diff_vanished(state.diff, attempt["diff"]):
        out.append("the diff came back empty after a non-empty one (pre-mortem 13)")
    if a.arm == "S" and long_guard.jev_outage(list(state.decisions)):
        out.append("Jev: the first decisions all failed or null (pre-mortem 15)")
    hooks = row.get("hook_calls", 0)
    if hooks and row.get("hook_errors", 0) / hooks > HOOK_ERRORS:
        out.append(f"hooks: {row['hook_errors']} of {hooks} calls ended in error")
    return tuple(out)


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
           "jev_usd": run.jev_usd(a.evidence), "missing_transcripts": missing}  # fmt: skip
    arm_files.write_row(a.evidence, row)


# ---- chains --------------------------------------------------------------------------------------


def run_chain(ctx: Ctx, chain: Mapping[str, Any], status: Mapping[str, Any]) -> str:
    for arm in arm_order(chain["chain"], ctx.profile.arms):
        if (ctx.layout.runs / run_name(chain["chain"], ctx.model) / arm / "row.json").exists():
            log(f"{chain['chain']} {ctx.model} {arm}: a row exists; never run twice")
            continue
        stop = run_arm(ctx, chain, arm, status)
        if stop:
            return stop
        if why := cross_arm_breaks(ctx.layout, run_name(chain["chain"], ctx.model)):
            (ctx.layout.root / long_guard.STOP_FILE).write_text(why, encoding="utf-8")
            log(f"{chain['chain']}: STOP: {why}")
            return "harness"
    return ""


def cross_arm_breaks(layout: Layout, name: str) -> str:
    """Pre-mortems 9 and 10 across the arms run so far: first-request prefixes and modes."""
    prefix, modes = {}, {}
    for path in sorted((layout.runs / name).glob("*/row.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        ran = [c for c in row["calls"] if c.get("status") == "ran"]
        if ran:
            first = ran[0].get("first_request") or {}
            prefix[row["arm"]] = int(first.get("read", 0)) + int(first.get("write", 0))
        modes.update({f"{row['arm']}/{c['request']}": (c.get("init") or {}).get("permission_mode")
                      for c in ran})  # fmt: skip
    return "; ".join([*long_guard.prefix_breaks(prefix), *long_guard.permission_breaks(modes)])


def load_chains(path: Path | None) -> dict[str, Any]:
    if path is None:
        return run.chains()
    return json.loads(path.read_text(encoding="utf-8"))


def keyfile_for(profile: Profile, layout: Layout) -> Path | None:
    """The TypeSafe key for S's hooks, written under the root and removed at the end."""
    if "S" not in profile.arms:
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
    profile = PROFILES[args.profile]
    known = load_chains(Path(args.chains_file) if args.chains_file else None)
    names = [c for c in args.chains.split(",") if c] or list(profile.chains)
    models = [args.model] if args.model else list(profile.models)
    ctx = Ctx(layout, profile, models[0], tuple(json.loads(args.claude)),
              ceiling=ceiling_of(profile, args.ceiling))  # fmt: skip
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
        return run_all(ctx, names, known, models, args.allow_midnight)
    finally:
        if ctx.keyfile:
            ctx.keyfile.unlink(missing_ok=True)
        run.drop_arm_keys()


def plan(ctx: Ctx, names: list[str], known: Mapping[str, Any], models: list[str]) -> int:
    held = blocks(ctx.profile, names, models)
    for name, model, cap in held:
        found = known.get(name, {})
        log(f"{name} {model}: {len(found.get('bugs', []))} bugs, valid {found.get('valid')}, "
            f"arms {ctx.profile.arms}, caps held {cap:.2f} USD")
    why = long_guard.plan_refusal(held, ctx.ceiling, spent(ctx.layout))
    log(f"ceiling {ctx.ceiling} USD; {why or 'the caps fit'}")
    return 1 if why else 0


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("plan", "run", "grade", "kill"))
    parser.add_argument("--profile", default="gate", choices=sorted(PROFILES))
    parser.add_argument("--model", default=None, choices=sorted(run.MODELS))
    parser.add_argument("--chains", default="")
    parser.add_argument("--chains-file", default="")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--limit-flag", default=str(long_guard.LIMIT_FLAG))
    parser.add_argument("--ceiling", type=float, default=0.0, help="owner USD; the profile's")
    parser.add_argument("--claude", default='["claude"]', help="the command, as a JSON list")
    parser.add_argument("--allow-midnight", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
