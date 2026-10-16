"""Carry pilot: does a fact the person said in an earlier session survive into a new one?

Per scene (`scenes.py`) and arm, a fresh git repository and the scene's sessions, each a NEW
`claude -p` session (no --resume), in this order: `thread` (F1 family iii: session 1a, starts a
line of work), `first` (a small task with the fact said in passing), `between` (F1 family ii:
session 1', which states a newer rule), `second` (a task that tempts breaking the fact). Only
`first` and `second` are required. With `worktree: True`, `first` runs in a sibling `git worktree`
of the repository and the others in the main checkout. Every session but the last is committed.
After the last: the repository's tests, the scene's `task` and `fact` checks, and its `stale`
check when it has one (the older rule held: three-way newer / stale / neither).

Arms: `N`, Claude Code as it ships, its own auto memory on (it is by default, keyed by the git
repository, so a later session loads what an earlier one saved); `M`, the same plus sanchopanza's
memory hooks as `sanchopanza install --memory` writes them (`install.MEMORY_HOOKS`), with the
decider when TYPESAFE_API_KEY is set; `S`, sanchopanza as a user installs it in the project
(`carry_s`: `install --scope project --memory`, every other flag at its default, the hooks
run from this checkout with the pair's own state and the key; V's decoys in its store). All arms
get the same tools, model, prompts and caps.

`--clean-user`: each pair gets its own fresh CLAUDE_CONFIG_DIR (`<pair>/claude-config`, kept
across that pair's sessions so auto memory can carry), with no plugins, skills, MCP servers,
hooks or user CLAUDE.md. It signs in with CLAUDE_CODE_OAUTH_TOKEN from the launcher's
environment or the .env file SANCHOPANZA_KEYS_ENV names, passed only in the claude process's
environment: never written, logged or put in the run folder (a pair's files are scanned for it
at its end and scrubbed if found).

Caps: `--max-budget-usd` per session (CALL_CAPS, per model) and TOTAL_CAP over the run, checked
before each pair against that pair's sessions at the cap, from the sessions' own `total_cost_usd`
(list price; the subscription pays). A session its own cap stops counts as run. Sessions run one
at a time; a usage limit stops the run. Arm S adds its decisions (the pair's journal) to what
was spent and holds `carry_s.JEV_RESERVE` per session for them; a pair where S did not run as S
(`carry_s` checks) is NOT RUN and stops the run. `--dry` builds every repository (worktrees
included) and prints what it would run, calling nothing.

    python benchmarks/memory_carry/carry.py --out DIR [--dry] [--models sonnet] [--repeats 1]
        [--first-repeat 0] [--scenes pilot|held|all|cross|principle|stale|parallel|f1|a,b]
        [--arms N,M] [--rotate] [--clean-user] [--total-cap USD] [--continue]
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1] / "src"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SRC))

import carry_s  # noqa: E402
from rules import RULES  # noqa: E402
from scenes import SCENES as PILOT  # noqa: E402
from scenes_cross import CROSS, CROSS_RULES  # noqa: E402
from scenes_held import HELD  # noqa: E402
from scenes_parallel import PARALLEL, PARALLEL_RULES  # noqa: E402

from sanchopanza.harness.install import MEMORY_HOOKS  # noqa: E402


def _optional(module: str, *names: str) -> tuple[dict[str, Any], ...]:
    """A scene set written in parallel (F1 families i and ii): empty until its module lands. Only
    the module's own absence is tolerated; an error inside it is raised."""
    try:
        loaded = __import__(module)
    except ModuleNotFoundError as error:
        if error.name != module:
            raise
        return tuple({} for _ in names)
    return tuple(getattr(loaded, n) for n in names)


PRINCIPLE, PRINCIPLE_RULES = _optional("scenes_principle", "PRINCIPLE", "PRINCIPLE_RULES")
STALE, STALE_RULES = _optional("scenes_stale", "STALE", "STALE_RULES")

CALL_CAP = 0.60  # per session, Haiku and Sonnet (as before)
CALL_CAPS = {"haiku": CALL_CAP, "sonnet": 0.60, "opus": 1.00}  # opus: gen-opus's top was 0.538
TOTAL_CAP = 9.00  # default; --total-cap raises it for a run the owner approved
SCENES = {**PILOT, **HELD, **CROSS, **PRINCIPLE, **STALE, **PARALLEL}
SETS = {"pilot": list(PILOT), "held": list(HELD), "all": [*PILOT, *HELD], "cross": list(CROSS),
        "principle": list(PRINCIPLE), "stale": list(STALE), "parallel": list(PARALLEL),
        "f1": [*PRINCIPLE, *STALE, *PARALLEL]}  # fmt: skip
# Family ii keeps both of a scene's rules ({"stale": A, "fact": A'}): its own rule is the newer,
# said in `between`; the older is apart, for a send-back that quotes it (counted as false).
STALE_OLD = {k: v["stale"] for k, v in STALE_RULES.items() if isinstance(v, dict)}
ALL_RULES = {**RULES, **CROSS_RULES, **PRINCIPLE_RULES, **PARALLEL_RULES,
             **{k: v["fact"] if isinstance(v, dict) else v for k, v in STALE_RULES.items()}}
# Decoys come from the rules v7 and v8 drew them from, so their decoys stay what they were: the
# F1 sets add rules (and family iii repeats the cross rules under new names).
DECOY_POOL = {**RULES, **CROSS_RULES}
# Arms: N plain; M memory with standing rules off (v6.2 behaviour); V memory v7; P placebo:
# memory v6.2, and session 1 says a neutral sentence where the rule was (nothing to remember);
# S, `sanchopanza install --scope project --memory` as a user runs it (`carry_s`), with V's decoys.
ARMS = ("N", "M", "V", "P", "S")
NEUTRAL = "For context: this module was written last spring by the platform team."
# V starts with DECOYS standing rules of other scenes already in its store, as a project that has
# been worked on carries rules unrelated to the task: the injection is not one conspicuous line,
# and every unrelated rule is held against the diff (the false sends-back a real project pays).
# A decoy never states the scene's own fact or a near one (SAME groups).
DECOYS = 7
# F1 (2026-10-05) adds its near pairs; their new names are outside DECOY_POOL, so v7 and v8's
# decoys do not move. p_dryrun is a weaker overlap with stdout, kept anyway.
SAME = ({"naive", "x_tz", "u_time"}, {"stdlib", "x_stdlib"}, {"stdout", "x_print", "p_json"},
        {"stdout", "x_print", "p_dryrun"}, {"ids", "x_zeros"}, {"envvar", "x_prefix"},
        {"legacy", "nulls"}, {"u_lang", "p_es"}, {"u_money", "x_cents"},
        {"u_sep", "fields"})  # fmt: skip
MODELS = {"haiku": "claude-haiku-4-5-20251001", "sonnet": "claude-sonnet-5-5",
          "opus": "claude-opus-5-5"}  # fmt: skip
PYTHON = sys.executable
TOOLS = ["Bash", "Read", "Edit", "Write", "Glob", "Grep"]
PROJECTS = Path.home() / ".claude" / "projects"
ORDER = ("thread", "first", "between", "second")
TOKEN = "CLAUDE_CODE_OAUTH_TOKEN"
# The .env file a launcher with no window variables (one started by WMI) reads secrets from;
# none unless SANCHOPANZA_KEYS_ENV names one.
HARNESS_ENV = (Path(os.environ["SANCHOPANZA_KEYS_ENV"])
               if os.environ.get("SANCHOPANZA_KEYS_ENV") else None)
BUDGET_STOP = "error_max_budget_usd"
PIN = "2.1.287"  # the pinned Claude Code (v8.1 Haiku and F1); a clean-user run refuses another
SESSION_TIMEOUT = 900


def project_name(cwd: Path) -> str:
    """The folder Claude Code keeps a project's transcripts and auto memory in."""
    return re.sub(r"[^a-zA-Z0-9]", "-", str(cwd))


def steps(scene: dict[str, Any]) -> list[tuple[str, bool]]:
    """(prompt key, runs in the sibling worktree) for each session of a scene, in order."""
    return [(key, key == "first" and bool(scene.get("worktree")))
            for key in ORDER if scene.get(key)]  # fmt: skip


def git(cwd: Path, *args: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "dev", "GIT_AUTHOR_EMAIL": "dev@example.org",
           "GIT_COMMITTER_NAME": "dev", "GIT_COMMITTER_EMAIL": "dev@example.org"}  # fmt: skip
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, env=env)
    if done.returncode:  # git's own words go to the log: v81h-all lost them on 2026-10-05
        sys.stderr.write(done.stderr.decode("utf-8", "replace"))
        raise subprocess.CalledProcessError(done.returncode, done.args, done.stdout, done.stderr)


def held(repo: Path, steps: list[tuple[str, ...]], tries: int = 3,
         undo: Callable[[], None] | None = None) -> None:  # fmt: skip
    """Git steps run again while git reports the index held (its 128). On Opus, 2026-10-02, the
    commit after a session failed once that way; on Haiku, 2026-10-05, the `add` that builds a
    fresh repository did, before any session, and the run stopped. `undo` clears what a failed
    try left behind before the next."""
    for attempt in range(tries):
        try:
            for step in steps:
                git(repo, *step)
            return
        except subprocess.CalledProcessError:
            if attempt == tries - 1:
                raise
            if undo:
                undo()
            time.sleep(3 * (attempt + 1))


def commit_wip(repo: Path, tries: int = 3) -> None:
    """A session's work as one commit."""
    held(repo, [("add", "-A"), ("commit", "-q", "--allow-empty", "-m", "wip")], tries)


def build(run: Path, scene: dict[str, Any],
          prepare: Callable[[Path], None] | None = None) -> Path:  # fmt: skip
    """The scene's repository; `prepare` (arm S's install) runs before the start commit, so a
    sibling worktree holds what it wrote too."""
    repo = run / "repo"
    for rel, text in scene["files"].items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8", newline="\n")
    if prepare is not None:
        prepare(repo)
    held(repo, [("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "start")])
    return repo


def worktree(repo: Path, tries: int = 3) -> Path:
    """A sibling `git worktree` of the scene's repository (`<pair>/repo-wt`, branch `side`, from
    the start commit), as the maintainer opens a parallel session. Beside the repository, not in
    it, so the repository's own tests never collect it."""
    tree = repo.parent / "repo-wt"

    def undo() -> None:  # a half-made worktree blocks the next try
        if tree.exists():
            shutil.rmtree(tree, onexc=_writable)
        subprocess.run(["git", "-C", str(repo), "worktree", "prune"], capture_output=True)
        subprocess.run(["git", "-C", str(repo), "branch", "-D", "side"], capture_output=True)

    held(repo, [("worktree", "add", "-q", "-b", "side", str(tree), "main")], tries, undo)
    return tree


def settings(run: Path, arm: str, keyfile: Path) -> str:
    """The `--settings` flag: empty for N and for S, whose hooks are in the project's own
    `.claude/settings.json`, as `sanchopanza install` left them (`carry_s.install`)."""
    if arm in ("N", "S"):
        return "{}"
    launcher = (HERE / "carry_hook.py").as_posix()
    rules = "rules-on" if arm == "V" else "rules-off"
    hook = {"type": "command", "command": f'"{Path(PYTHON).as_posix()}" "{launcher}" '
            f'"{run.as_posix()}" "{keyfile.as_posix()}" {rules}'}  # fmt: skip
    return json.dumps({"hooks": {event: [{"matcher": matcher, "hooks": [hook]}]
                                 for event, matcher in MEMORY_HOOKS.items()}})  # fmt: skip


def environment(config: Path | None = None,
                base: dict[str, str] | None = None) -> dict[str, str]:  # fmt: skip
    """The agent's environment, the same in every arm: no API key (the subscription pays), no
    TypeSafe key (only the hook arms read it, from a file), Claude Code's own memory on. With a
    clean user's `config`: no ANTHROPIC_* or CLAUDE_CODE_USE_* variable at all (no other
    endpoint, key or provider), that CLAUDE_CONFIG_DIR, and the OAuth token from this process's
    own environment, here and nowhere else. Over `base` when given (the long-chain runner passes
    `run.child_env`'s), else over this process's environment."""
    drop = ("ANTHROPIC_API_KEY", "TYPESAFE_", "SANCHOPANZA_", "CLAUDE_CODE_DISABLE_AUTO_MEMORY")
    if config is not None:
        drop = (*drop, "ANTHROPIC_", "CLAUDE_CODE_USE_", "CLAUDE_CONFIG_DIR", TOKEN)
    source = os.environ if base is None else base
    env = {k: v for k, v in source.items() if not k.upper().startswith(drop)}
    if config is None:
        return env
    return {**env, "CLAUDE_CONFIG_DIR": str(config), TOKEN: clean_token()}


def from_harness_env(name: str) -> str:
    """A secret from the environment, else from the SANCHOPANZA_KEYS_ENV file (a launcher started by
    WMI outside the session gets no window variables). Never printed."""
    value = os.environ.get(name, "").strip()
    if not value and HARNESS_ENV is not None and HARNESS_ENV.exists():
        for line in HARNESS_ENV.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                value = line.split("=", 1)[1].strip().strip('"')
    return value


def clean_token() -> str:
    """The subscription's token for clean-user runs (`claude setup-token`), from the launcher's
    environment or the SANCHOPANZA_KEYS_ENV file. Never printed: the refusal names the variable
    only."""
    token = from_harness_env(TOKEN)
    if not token:
        raise SystemExit(f"--clean-user needs {TOKEN} in the environment or the "
                         "SANCHOPANZA_KEYS_ENV file; refusing to start")  # fmt: skip
    return token


def clean_config(run: Path) -> Path:
    """A pair's own empty Claude Code configuration folder, kept across its sessions."""
    config = run / "claude-config"
    config.mkdir(parents=True, exist_ok=True)
    return config


def ancestors_memory(path: Path) -> list[str]:
    """Memory files in the folders above `path` that Claude Code's upward CLAUDE.md search could
    read whatever CLAUDE_CONFIG_DIR says (whether it reads them is not verified here). Under the
    home folder that includes `~/.claude/CLAUDE.md` and `~/.claude/rules/`, as the `.claude`
    folder of an ancestor."""
    found: list[str] = []
    for folder in [path, *path.parents]:
        for rel in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md"):
            if (folder / rel).is_file():
                found.append(str(folder / rel))
        rules = folder / ".claude" / "rules"
        if rules.is_dir() and any(rules.glob("*.md")):
            found.append(str(rules))
    return found


def keyfile_from_harness_env(out: Path) -> Path:
    """The TypeSafe key for the M arm's hook, from the environment or the SANCHOPANZA_KEYS_ENV
    file; never printed, and removed when the run ends."""
    key = from_harness_env("TYPESAFE_API_KEY")
    if not key:
        raise SystemExit("no TypeSafe key: the M arm would run without its decider")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "typesafe.key"
    path.write_text(key, encoding="utf-8")
    return path


def command(run: Path, prompt: str, model: str, arm: str, keyfile: Path) -> list[str]:
    return ["claude", "-p", prompt, "--model", MODELS[model], "--output-format", "stream-json",
            "--verbose", "--max-budget-usd", f"{CALL_CAPS[model]:.2f}",
            "--settings", settings(run, arm, keyfile), "--allowedTools", *TOOLS]  # fmt: skip


def session(run: Path, repo: Path, prompt: str, model: str, arm: str, tag: str,
            keyfile: Path, dry: bool, config: Path | None = None) -> dict[str, Any]:  # fmt: skip
    cmd = command(run, prompt, model, arm, keyfile)
    if dry:
        return {"dry": True}
    started = time.time()
    try:
        with (run / f"{tag}.jsonl").open("w", encoding="utf-8") as out:
            done = subprocess.run(cmd, cwd=repo, env=environment(config), stdout=out,
                                  stderr=subprocess.PIPE, text=True, timeout=SESSION_TIMEOUT,
                                  check=False)  # fmt: skip
    except subprocess.TimeoutExpired:  # the pair is cut and the run stops (run_plan)
        return {"returncode": None, "timeout": True, "stderr": "",
                "seconds": round(time.time() - started, 1),
                **read_stream(run / f"{tag}.jsonl")}  # fmt: skip
    seen = read_stream(run / f"{tag}.jsonl")
    return {"returncode": done.returncode, "stderr": (done.stderr or "")[-300:],
            "seconds": round(time.time() - started, 1), **seen}  # fmt: skip


def session_ran(result: dict[str, Any]) -> bool:
    """A session ended with a result: exit 0, or stopped by its own budget cap (F1 counts that
    as run, with its checks as found). No result, a timeout or another non-zero exit: cut."""
    if result.get("timeout") or not result.get("subtype"):
        return False
    return result.get("returncode") == 0 or result.get("subtype") == BUDGET_STOP


def init_facts(event: dict[str, Any]) -> dict[str, Any]:
    """What a session loaded, from its `init` event: model, version, and how much came from the
    user's setup (a clean user has no MCP servers, plugins or skills of its own). `mcp` names
    each server with its status ("connected", "failed", ...): the long-chain runner stops a chain
    whose S arm loses a server (B2's S ran with `sanchopanza` failed at init, unseen)."""
    paths = event.get("memory_paths")
    count = {k: len(event.get(k) or []) for k in ("mcp_servers", "plugins", "skills", "agents")}
    servers = [s for s in event.get("mcp_servers") or [] if isinstance(s, dict)]
    return {"model": event.get("model"), "version": event.get("claude_code_version"),
            "session_id": event.get("session_id"), "permission_mode": event.get("permissionMode"),
            "api_key_source": event.get("apiKeySource"), **count,
            "mcp": {str(s.get("name")): str(s.get("status")) for s in servers},
            "memory_auto": paths.get("auto") if isinstance(paths, dict) else None,
            "skill_names": skill_names(event)}  # fmt: skip


def skill_names(event: dict[str, Any]) -> list[str]:
    """The names of the skills a session's `init` lists (a name, or an object with one)."""
    out = []
    for s in event.get("skills") or []:
        name = s if isinstance(s, str) else s.get("name") if isinstance(s, dict) else None
        out += [str(name)] if name else []
    return out


def limited(event: dict[str, Any]) -> bool:
    """The subscription's usage limit, as Claude Code's stream reports it. Seen on 2026-10-01
    (adopt's `conan-io__conan-1-limit1`, 2.1.285): a `rate_limit_event` with status `rejected`,
    an assistant event with `error: rate_limit`, and a result with `api_error_status` 429 (its
    subtype still `success`). In 2.1.287's carry streams (v81h-all, 260 events) the same event
    only ever says `allowed`. Text that mentions a limit is not one."""
    kind = event.get("type")
    info = event.get("rate_limit_info")
    if kind == "rate_limit_event" and isinstance(info, dict):
        return info.get("status") == "rejected"
    if kind == "assistant":
        return event.get("error") == "rate_limit"
    return kind == "result" and event.get("api_error_status") == 429


def read_stream(path: Path) -> dict[str, Any]:
    cost, turns, final, limit, tools = 0.0, 0, "", False, 0
    subtype, init, result = "", {}, {}
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "result":
            cost = float(event.get("total_cost_usd") or 0.0)
            turns, final = event.get("num_turns") or 0, str(event.get("result") or "")
            subtype = str(event.get("subtype") or "")
            result = {k: event.get(k) for k in ("is_error", "api_error_status", "terminal_reason")}
        if event.get("type") == "system" and event.get("subtype") == "init" and not init:
            init = init_facts(event)
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        tools += sum(1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use") \
            if isinstance(content, list) else 0
        limit = limit or limited(event)
    return {"cost": cost, "turns": turns, "tools": tools, "final": final[-500:],
            "limit_hit": limit, "subtype": subtype, "init": init, **result}  # fmt: skip


def passes(repo: Path, code: str) -> bool | None:
    if not code:
        return None
    try:
        done = subprocess.run([PYTHON, "-c", code], cwd=repo, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:  # a hung check fails; it never ends a paid run
        return False
    return done.returncode == 0


def carried(fact: bool | None, stale: bool | None) -> str | None:
    """Family ii's three-way reading: the newer rule held, the older one, or neither."""
    if stale is None:
        return None
    return "newer" if fact else "stale" if stale else "neither"


def check(repo: Path, scene: dict[str, Any]) -> dict[str, Any]:
    try:
        tests = subprocess.run([PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                               cwd=repo, capture_output=True, text=True, timeout=300).returncode
    except subprocess.TimeoutExpired:  # hung tests fail; the pair keeps its row
        tests = -1
    fact = passes(repo, scene["fact"])
    stale = passes(repo, scene.get("stale", ""))
    found = {"tests_pass": tests == 0, "task_pass": passes(repo, scene["task"]),
             "fact_kept": fact}  # fmt: skip
    return {**found, "stale_kept": stale, "carried": carried(fact, stale)} if stale is not None \
        else found


def native_memory(repo: Path, projects: Path = PROJECTS, auto: str | None = None) -> list[str]:
    """Files Claude Code's own auto memory holds for this repository: its project folder under
    the configuration actually used, and the folder the session's `init` named, if any."""
    wanted = project_name(repo).casefold()
    folders = [d for d in projects.glob("*/memory") if d.parent.name.casefold() == wanted]
    folders += [Path(auto)] if auto else []
    files = {p.resolve() for d in folders if d.is_dir() for p in d.rglob("*") if p.is_file()}
    return sorted(_shown(p, projects) for p in files)


def _shown(path: Path, projects: Path) -> str:
    try:
        return str(path.relative_to(projects.resolve()))
    except ValueError:
        return str(path)


def given(run: Path) -> list[str]:
    """Records sanchopanza's memory gave in session 2 (from its hook log)."""
    path = run / "hook-log.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [f"{r.get('event')}:{','.join(r['shown'])}" for r in rows if r.get("shown")]


def own_rules(name: str) -> set[str]:
    """Every rule text that is the scene's own: its rule, and for family ii the older one too."""
    return {t for t in (ALL_RULES.get(name), STALE_OLD.get(name)) if t}


def decoys(name: str) -> list[str]:
    """DECOYS other scenes' rules, the same ones for a scene at every repetition. A family iii
    scene is near its cross twin (the same rule under another name); a family ii scene owns both
    its rules, the older and the newer."""
    twin = SCENES.get(name, {}).get("cross", name)
    near = set().union(*(group for group in SAME if name in group or twin in group))
    near |= {name, twin}
    own = own_rules(name)
    pool = sorted(k for k in DECOY_POOL if k not in near and DECOY_POOL[k] not in own)
    start = sum(map(ord, name)) % len(pool)
    return [DECOY_POOL[k] for k in (pool[start:] + pool[:start])[:DECOYS]]


def said_while(text: str) -> list[str]:
    """The files a decoy's own scene changes in its session 1, as `memory_rules.extract` would
    have recorded them (v8: the audit shows where each rule was said; v7 seeded `app/other.py`
    for every decoy, the audit bench used these, and so does v8's run)."""
    scene = SCENES[next(k for k, v in DECOY_POOL.items() if v == text)]
    return sorted(f for f in scene["files"]
                  if f.startswith(("app/", "tests/")) and not f.endswith("__init__.py"))


def seed(run: Path, repo: Path, name: str) -> None:
    """The decoy rules in V's store, as earlier sessions of this project left them."""
    rules = [{"text": text, "p": 0.9, "session": f"earlier-{i}", "index": 1,
              "at": 1_790_000_000.0 + i * 3600, "files": said_while(text)}
             for i, text in enumerate(decoys(name))]  # fmt: skip
    payload = json.dumps({"rules": rules[::-1], "asked": [], "audited": []})
    key = project_name(repo)
    for folder in {key, key[:1].lower() + key[1:], key[:1].upper() + key[1:]}:
        (run / "store" / folder).mkdir(parents=True, exist_ok=True)
        (run / "store" / folder / "rules.json").write_text(payload, encoding="utf-8")


def scrub(run: Path, secret: str) -> tuple[list[str], list[str]]:
    """Files of a pair that hold `secret`: rewritten without it, and, inside `.git` (never
    touched, never deleted), only named, loose objects read inflated. Claude Code is not expected
    to write the token anywhere; this makes sure the run folder never keeps it unnoticed."""
    needle, scrubbed, in_git = secret.encode(), [], []
    for path in run.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(run)
        data = path.read_bytes()
        if ".git" in rel.parts:
            with contextlib.suppress(zlib.error):
                data = zlib.decompress(data) if "objects" in rel.parts else data
            in_git += [str(rel)] if needle in data else []
        elif needle in data:
            path.write_bytes(data.replace(needle, b"[token]"))
            scrubbed.append(str(rel))
    return scrubbed, in_git


def redact(value: Any, secret: str) -> Any:
    """`value` (a row) with `secret` replaced in every string, before it is written or printed."""
    if isinstance(value, str):
        return value.replace(secret, "[token]")
    if isinstance(value, dict):
        return {k: redact(v, secret) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secret) for v in value]
    return value


def pair(out: Path, name: str, model: str, arm: str, rep: int, keyfile: Path,
         dry: bool, clean: bool = False) -> dict[str, Any]:  # fmt: skip
    run = out / f"{name}-{model}-{arm}-{rep}"
    scene = SCENES[name]
    run.mkdir(parents=True, exist_ok=True)
    prepare = (lambda repo: carry_s.install(run, repo, keyfile, environment())) \
        if arm == "S" else None  # fmt: skip
    repo = build(run, scene, prepare)
    tree = worktree(repo) if scene.get("worktree") else None
    config = clean_config(run) if clean else None
    if arm in ("V", "S"):
        seed(run, repo, name)
    plan = steps(scene)
    row: dict[str, Any] = {"scene": name, "model": model, "arm": arm, "repeat": rep,
                           "clean_user": clean, "planned": [k for k, _ in plan]}  # fmt: skip
    if dry:
        return {**row, "dry": True, "repo": str(repo), "worktree": str(tree) if tree else None,
                "where": ["worktree" if w else "main" for _, w in plan],
                "config": str(config) if config else None}  # fmt: skip
    found: tuple[list[str], list[str]] = ([], [])
    try:
        done = sessions_of(run, repo, tree, scene, name, plan, model, arm, keyfile, config)
    finally:  # whatever happened, the pair's files never keep the token
        found = scrub(run, clean_token()) if clean else found
    flags = {**({"token_scrubbed": found[0]} if found[0] else {}),
             **({"token_in_git": found[1]} if found[1] else {})}  # fmt: skip
    full = {**row, **done, **flags}
    return redact(full, clean_token()) if clean else full


def sessions_of(run: Path, repo: Path, tree: Path | None, scene: dict[str, Any], name: str,
                plan: list[tuple[str, bool]], model: str, arm: str, keyfile: Path,
                config: Path | None) -> dict[str, Any]:  # fmt: skip
    """A pair's sessions, then its checks when the last session ran."""
    said = scene["first"].replace(ALL_RULES[name], NEUTRAL) if arm == "P" else scene["first"]
    projects = config / "projects" if config else PROJECTS
    ran = run_sessions(run, repo, tree, {**scene, "first": said}, plan, model, arm, keyfile,
                       config, projects)  # fmt: skip
    by_key = {s["key"]: s for s in ran}
    first, second = by_key.get("first", {}), by_key.get("second", {})
    jev = carry_s.jev(run) if arm == "S" else {}
    cut = cut_reason(ran, len(plan))
    if arm == "S" and not cut:
        broken = carry_s.pair_breaks(jev)
        cut = f"harness: {'; '.join(broken)}" if broken else ""
    return {"sessions": ran, "first": first, "second": second,
            "native_after_1": first.get("native", []), "given": given(run), **jev,
            **({"cut": cut} if cut else check(repo, scene)),
            "cost": sum(float(s.get("cost") or 0.0) for s in ran),
            "limit_hit": any(s.get("limit_hit") for s in ran)}  # fmt: skip


def cut_reason(ran: list[dict[str, Any]], planned: int) -> str:
    """Why a pair is NOT RUN by the runner's own reading ("" when every session ran)."""
    for s in ran:
        if s.get("limit_hit"):
            return "usage limit"
        if s.get("timeout"):
            return "timeout"
        if s.get("harness"):
            return f"harness: session {s['key']}: {'; '.join(s['harness'])}"
        if not session_ran(s):
            got = f"exit {s.get('returncode')}, {s.get('subtype') or 'no result'}"
            return f"session {s['key']} did not end with a result ({got})"
    return "" if len(ran) == planned else "sessions missing"


def run_sessions(run: Path, repo: Path, tree: Path | None, prompts: dict[str, Any],
                 plan: list[tuple[str, bool]], model: str, arm: str, keyfile: Path,
                 config: Path | None, projects: Path) -> list[dict[str, Any]]:  # fmt: skip
    """A pair's sessions in order, each committed but the last. A usage limit, a timeout or a
    session without a result ends the pair."""
    done: list[dict[str, Any]] = []
    for index, (key, in_tree) in enumerate(plan, start=1):
        if done and cut_reason(done, len(done)):
            break
        cwd = tree if in_tree and tree else repo
        since = carry_s.hook_rows(run)
        result = session(run, cwd, prompts[key], model, arm, f"session-{index}", keyfile, False,
                         config)  # fmt: skip
        if index < len(plan):
            commit_wip(cwd)
        auto = (result.get("init") or {}).get("memory_auto")
        broken = carry_s.session_breaks(run, result, since) \
            if arm == "S" and session_ran(result) else []  # fmt: skip
        done.append({**result, "key": key, "where": "worktree" if cwd != repo else "main",
                     "native": native_memory(repo, projects, auto),
                     **({"harness": broken} if broken else {})})  # fmt: skip
    return done


def _writable(func: Any, path: str, _error: BaseException) -> None:
    """git keeps its objects read-only, and Windows will not unlink those."""
    os.chmod(path, 0o700)
    func(path)


def earlier(out: Path) -> list[dict[str, Any]]:
    path = out / "carry.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def ignore_interrupts() -> None:
    """A stray Ctrl+C does not end a paid, sealed run: phase A lost a batch to one reaching its
    console mid-grade (2026-10-02). The run is stopped by PID, never by a signal from a console."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def main(argv: list[str] | None = None) -> int:
    """0 when the plan ran to its end; 2 when the run's cap or the usage limit stopped it; 3
    when a session timed out (that pair is cut, and runs again whole under --continue); 4 when
    arm S did not run as S (`carry_s`); 1 when it refused to start."""
    ignore_interrupts()
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--models", default="sonnet")
    parser.add_argument("--scenes", default="pilot",
                        help="pilot, held, all, cross, principle, stale, parallel, f1 or names")
    parser.add_argument("--arms", default="N,M", help=f"of {','.join(ARMS)}")
    parser.add_argument("--total-cap", type=float, default=TOTAL_CAP)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--first-repeat", type=int, default=0,
                        help="number of the first repetition (F1: gate 0, full run 1)")
    parser.add_argument("--clean-user", action="store_true",
                        help=f"a fresh CLAUDE_CONFIG_DIR per pair, signed in with {TOKEN}")
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--continue", dest="carry_on", action="store_true",
                        help="keep the rows of carry.json; a pair cut by the runner runs again")
    parser.add_argument("--rotate", action="store_true",
                        help="alternate which arm of a pair runs first, pair after pair")
    args = parser.parse_args(argv)
    out = Path(args.out)
    if args.clean_user:
        refuse_unclean(out)  # before anything is built
    plan = build_plan(args.scenes, args.models, args.arms, args.repeats, args.first_repeat,
                      args.rotate)  # fmt: skip
    record_claude(out, args.dry, args.clean_user)
    hooks = any(arm != "N" for _, _, arm, _ in plan)
    keyfile = keyfile_from_harness_env(out) if hooks and not args.dry else out / "typesafe.key"
    try:
        spent = 0.0 if args.dry else jev_first(out, plan, keyfile)
        stop = run_plan(out, plan, keyfile, args.dry, args.total_cap, args.carry_on,
                        args.clean_user, spent)  # fmt: skip
    finally:
        keyfile.unlink(missing_ok=True)
    return EXIT.get(stop or "", 0)


EXIT = {"cap": 2, "limit": 2, "timeout": 3, "harness": 4}


def jev_first(out: Path, plan: list[tuple[str, str, str, int]], keyfile: Path) -> float:
    """Before a plan with arm S: one real Jev decision with the run's key (`carry_s.preflight`),
    written to `jev-preflight.json`; refused (exit 1) unless it answered. Returns its cost."""
    if not any(arm == "S" for _, _, arm, _ in plan):
        return 0.0
    found = carry_s.preflight(keyfile, environment())
    (out / "jev-preflight.json").write_text(json.dumps(found, indent=1), encoding="utf-8")
    if not found.get("ok"):
        raise SystemExit(f"Jev preflight failed ({found.get('reason')}): arm S would run "
                         "without its decider; refusing")  # fmt: skip
    return float(found.get("cost_usd") or 0.0)


def refuse_unclean(out: Path) -> None:
    """A clean user is refused when it would not be clean: no token, or a memory file above the
    run folder that Claude Code's upward CLAUDE.md search could load (2026-10-05: under the home
    folder that is the maintainer's own `~/.claude/CLAUDE.md` and `~/.claude/rules`)."""
    clean_token()
    found = ancestors_memory(out.resolve())
    if found:
        raise SystemExit("--clean-user refused: memory files above the run folder: "
                         + ", ".join(found) + ". Put --out where no folder above holds one.")


def record_claude(out: Path, dry: bool, clean: bool,
                  claude: tuple[str, ...] = ("claude",)) -> str:  # fmt: skip
    """Which `claude` the run starts, and its version, once, in `claude.txt`; returns the
    version. A dry run calls nothing, so it records the path only. A clean-user run refuses any
    version but PIN. `claude`: the command (a test passes a stand-in)."""
    out.mkdir(parents=True, exist_ok=True)
    where = shutil.which(claude[0]) or claude[0]
    version = "not asked (dry run)"
    if not dry:
        asked = subprocess.run([*claude, "--version"], capture_output=True, text=True,
                               timeout=120, env=environment(), check=False)  # fmt: skip
        version = (asked.stdout or asked.stderr).strip()
    with (out / "claude.txt").open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {where} {version}\n")
    if clean and not dry and not version.startswith(f"{PIN} "):
        raise SystemExit(f"--clean-user refused: claude on PATH is {version!r}, not {PIN}")
    return version


def build_plan(scenes: str, models: str, arms: str, repeats: int, first: int = 0,
               rotate: bool = False) -> list[tuple[str, str, str, int]]:  # fmt: skip
    """Every (scene, model, arm, repetition), the arms of a pair one after the other; with
    `rotate`, the order of the arms is reversed on every other pair, and flips again from one
    repetition to the next, so no scene keeps one order in every repetition."""
    names = SETS[scenes] if scenes in SETS else scenes.split(",")
    unknown = [n for n in names if n not in SCENES]
    if unknown:
        raise SystemExit(f"unknown scenes: {', '.join(unknown)}")
    order = arms.split(",")
    groups = [(name, model, rep) for rep in range(first, first + repeats)
              for model in models.split(",") for name in names]  # fmt: skip
    return [(name, model, arm, rep) for i, (name, model, rep) in enumerate(groups)
            for arm in (order[::-1] if rotate and (i + rep) % 2 else order)]  # fmt: skip


def cut_cost(cut: Path) -> float:
    """What a pair the runner cut had spent: its sessions' own results and its decisions, before
    it runs again."""
    claude = sum(read_stream(f)["cost"] for f in sorted(cut.glob("session-*.jsonl")))
    return claude + carry_s.jev(cut)["jev_usd"]


def reserve_of(name: str, model: str, arm: str) -> float:
    """What the next pair may spend at most: each session at its cap, and S's decisions."""
    sessions = len(steps(SCENES[name]))
    return sessions * (CALL_CAPS[model] + (carry_s.JEV_RESERVE if arm == "S" else 0.0))


def spent_of(row: dict[str, Any]) -> float:
    return float(row.get("cost") or 0.0) + float(row.get("jev_usd") or 0.0)


def run_plan(out: Path, plan: list[tuple[str, str, str, int]], keyfile: Path, dry: bool,
             total_cap: float, carry_on: bool = False, clean: bool = False,
             spent: float = 0.0) -> str:  # fmt: skip
    """Runs the plan; returns why it stopped early ("cap", "limit", "timeout", "harness") or "".
    Spent: `spent` (the Jev preflight), Claude Code's own cost and S's decisions."""
    rows = earlier(out) if carry_on else []
    done = {(r["scene"], r["model"], r["arm"], r["repeat"]) for r in rows}
    spent += sum(spent_of(r) for r in rows)
    for name, model, arm, rep in plan:
        if (name, model, arm, rep) in done:
            continue
        cut = out / f"{name}-{model}-{arm}-{rep}"
        if cut.exists():  # a pair the runner itself cut (no row): it runs again, whole
            if carry_on:
                lost = cut_cost(cut)
                spent += lost
                print(f"cut pair {cut.name}: its {lost:.2f} USD counted, it runs again", flush=True)
            shutil.rmtree(cut, onexc=_writable)
        if spent + reserve_of(name, model, arm) > total_cap:
            print(f"stop: {spent:.2f} USD spent, the next pair could pass {total_cap}", flush=True)
            return "cap"
        row = pair(out, name, model, arm, rep, keyfile, dry, clean)
        spent += spent_of(row)
        if row.get("cut") == "timeout":  # no row: --continue runs the pair again, whole
            print(f"stop: a session of {cut.name} timed out; {spent:.2f} USD spent", flush=True)
            return "timeout"
        rows.append(row)
        keys = ("scene", "model", "arm", "repeat", "tests_pass", "task_pass", "fact_kept",
                "carried", "cut", "cost", "jev_usd", "given", "native_after_1", "where")
        brief = {k: row.get(k) for k in keys if k in row}
        print(json.dumps(brief), f"spent {spent:.2f}", flush=True)
        (out / "carry.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
        if row.get("limit_hit"):
            print("stop: the subscription's usage limit", flush=True)
            return "limit"
        if str(row.get("cut") or "").startswith("harness"):  # S did not run as S: stop
            print(f"stop: {row['cut']}; {spent:.2f} USD spent", flush=True)
            return "harness"
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
