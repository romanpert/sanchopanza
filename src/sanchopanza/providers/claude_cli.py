"""Claude through the Claude Code CLI (`claude -p`), billed to the logged-in account, not a key.

The API path (`llm.anthropic_completer`, the benches' Batch API) bills an API key. This path
runs the same model as a one-shot Claude Code session and bills whatever account `claude` is
logged into, usually a subscription. It exists so that evaluations and tests that need a
generative model do not spend API money.

What makes a session cheap, measured on 2026-09-27 with Claude Code 2.1.282 and Haiku 4.5:
`--system-prompt` replaces Claude Code's own prompt, `--tools ""` removes every tool, and
`--setting-sources ""` with `--strict-mcp-config` keeps CLAUDE.md, hooks and MCP servers out.
The prefix drops from ~55k tokens to ~730; a one-word answer costs 0.002 USD at list price.
`--json-schema` forces a structured answer, at the price of one extra internal turn.

Four guards, because a subscription that runs out stops the owner's own work:

- **No API key reaches the session.** `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` and
  `ANTHROPIC_BASE_URL` are removed, so a stray key in the shell never turns this path into the
  API path it was meant to avoid.
- **Thinking off** (`MAX_THINKING_TOKENS=0`), matching the API default the benches used.
- **A hard ceiling** on the list-price cost of the sessions a `ClaudeCLI` starts, checked
  before each spawn, plus `--max-budget-usd` per session, which the CLI enforces itself.
- **A cache on disk**: a prompt already answered is replayed, never asked again, so a rerun of
  a bench after a crash or a code change to the analysis costs nothing.

The reported cost is Claude Code's estimate at list price (`costBasis: list`): what the same
tokens would cost on the API, not what the subscription charges. It is the unit the ceiling and
the reports use.

Comparability: a session is not the Messages API. The system prompt and tool set are ours, but
the CLI may add its own framing. A bench that compares arms must run every arm through the same
path; a number from this path is not placed beside a number from the API without a check.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import pathlib
import shutil
import subprocess
import tempfile
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .llm import Completer, Completion

Spawn = Callable[
    [list[str], bytes, dict[str, str], str, float], Awaitable[tuple[int, bytes, bytes]]
]

# Every route by which a session could bill something other than the logged-in account: API
# keys and base URLs, and the switches to Bedrock, Vertex or Foundry with their credentials.
_STRIPPED_PREFIXES = ("ANTHROPIC_", "CLAUDE_CODE_USE_", "AWS_BEARER_TOKEN_BEDROCK")
# The prompt goes as the last argument, after `--` so that text starting with `-` is never read
# as an option. Measured with twelve sessions at once on Windows: the CLI waits 3 s for stdin
# and then exits with "Input must be provided", so stdin lost half the answers. The Windows
# command line holds 32,767 characters as quoted by `list2cmdline`, flags included; a longer
# one sends the prompt on stdin instead.
COMMAND_LINE_LIMIT = 30_000
NUL = chr(0)
# Below this a session cannot answer anything useful: the ceiling counts as reached.
MIN_SESSION_USD = 0.001


class CeilingReached(RuntimeError):
    """The sessions of one `ClaudeCLI` reached their list-price ceiling. Nothing was spawned."""


@dataclass(frozen=True)
class Session:
    ok: bool
    text: str = ""
    structured: Mapping[str, Any] | None = None
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    list_cost_usd: float = 0.0
    reason: str = ""
    cached: bool = False


def build_argv(
    executable: str,
    *,
    model: str,
    system: str,
    max_budget_usd: float,
    schema: Mapping[str, Any] | None = None,
    effort: str | None = None,
) -> list[str]:
    """The argv of one isolated, tool-less, one-shot session, without the prompt."""
    argv = [
        executable,
        "-p",
        "--model",
        model,
        "--system-prompt",
        system,
        "--tools",
        "",
        "--setting-sources",
        "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
        "--output-format",
        "json",
        "--max-budget-usd",
        f"{max_budget_usd:g}",
    ]
    if schema is not None:
        argv += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    if effort:
        argv += ["--effort", effort]
    return argv


def clean_env(base: Mapping[str, str]) -> dict[str, str]:
    """The session's environment: no API credentials, no other provider, no thinking."""
    env = {k: v for k, v in base.items() if not k.startswith(_STRIPPED_PREFIXES)}
    env["MAX_THINKING_TOKENS"] = "0"
    return env


def parse_result(stdout: bytes, model: str) -> Session:
    """One `--output-format json` result into a `Session`. Anything unexpected is not ok."""
    try:
        data = json.loads(stdout.decode("utf-8", errors="replace"))
    except ValueError:
        return Session(ok=False, model=model, reason="unparseable output")
    if not isinstance(data, dict):
        return Session(ok=False, model=model, reason="unparseable output")
    usage = data.get("usage") or {}
    structured = data.get("structured_output")
    return Session(
        ok=not data.get("is_error", True) and data.get("subtype") == "success",
        text=str(data.get("result") or ""),
        structured=structured if isinstance(structured, dict) else None,
        model=model,
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
        cache_write_tokens=int(usage.get("cache_creation_input_tokens") or 0),
        list_cost_usd=float(data.get("total_cost_usd") or 0.0),
        reason="" if not data.get("is_error") else str(data.get("subtype") or "error"),
    )


async def spawn_process(
    argv: list[str], stdin: bytes, env: dict[str, str], cwd: str, timeout_s: float
) -> tuple[int, bytes, bytes]:
    """Run the CLI and wait. A timeout kills the process and reads as exit 124.

    A cancellation (a sibling raised `CeilingReached` inside a `gather`, the run was
    interrupted) kills it too: a session nobody waits for must not keep spending.
    """
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=cwd,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(stdin), timeout=timeout_s)
    except TimeoutError:
        return 124, b"", b"timeout"
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    return process.returncode or 0, out, err


class SessionCache:
    """Answered sessions on disk, one JSON line each, keyed by everything that shapes them."""

    def __init__(self, path: str | pathlib.Path) -> None:
        self.path = pathlib.Path(path)
        self._rows: dict[str, Session] = {}
        self.skipped = 0
        if self.path.exists():
            for raw in self.path.read_text(encoding="utf-8").splitlines():
                # A run killed mid-write leaves NUL padding, and the next run may append a
                # whole row after it on the same line: the padding is dropped, a row that is
                # still broken is counted and skipped. Losing one answer is right; refusing
                # to open every other one is not.
                line = raw.replace(NUL, "").strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    self._rows[row["key"]] = Session(**row["session"])
                except (ValueError, KeyError, TypeError):
                    self.skipped += 1

    @staticmethod
    def key(
        model: str,
        system: str,
        schema: Mapping[str, Any] | None,
        prompt: str,
        effort: str | None = None,
    ) -> str:
        # `effort` joins the key only when set, so caches written before it existed still hit.
        parts: list[Any] = [model, system, schema, prompt] + ([effort] if effort else [])
        blob = json.dumps(parts, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Session | None:
        return self._rows.get(key)

    def total_cost_usd(self) -> float:
        return sum(s.list_cost_usd for s in self._rows.values())

    def put(self, key: str, session: Session) -> None:
        self._rows[key] = session
        self.path.parent.mkdir(parents=True, exist_ok=True)
        torn = False
        if self.path.exists() and self.path.stat().st_size:
            with self.path.open("rb") as existing:
                existing.seek(-1, 2)
                torn = existing.read(1) != b"\n"
        with self.path.open("a", encoding="utf-8") as out:
            if torn:  # a crash left half a row: start this one on its own line
                out.write("\n")
            out.write(json.dumps({"key": key, "session": asdict(session)}, ensure_ascii=False))
            out.write("\n")


class ClaudeCLI:
    """One model, one system prompt, a ceiling, and optionally a cache: `await cli.run(prompt)`."""

    def __init__(
        self,
        *,
        model: str,
        system: str,
        ceiling_usd: float,
        max_budget_usd: float = 0.05,
        concurrency: int = 4,
        timeout_s: float = 180.0,
        effort: str | None = None,
        cache: SessionCache | None = None,
        count_cached: bool = False,
        executable: str | None = None,
        spawn: Spawn | None = None,
    ) -> None:
        # NaN passes `<= 0` and then `spent >= nan` is never true: a ceiling that is not a
        # finite positive number is no ceiling.
        for name, value in (("ceiling_usd", ceiling_usd), ("max_budget_usd", max_budget_usd)):
            if not (isinstance(value, int | float) and math.isfinite(value) and value > 0):
                raise ValueError(f"{name} must be a finite positive number, got {value!r}")
        resolved = executable or shutil.which("claude") or "claude"
        if pathlib.PurePath(resolved).suffix.lower() in (".cmd", ".bat"):
            # cmd.exe re-parses a batch file's arguments (quotes, &, %): a prompt could run
            # commands. Point `executable` at the real binary instead of the npm shim.
            raise ValueError(f"refusing a batch shim as the CLI: {resolved}")
        self.model = model
        self.system = system
        self.ceiling_usd = ceiling_usd
        self.max_budget_usd = max_budget_usd
        self.timeout_s = timeout_s
        self.effort = effort
        self.cache = cache
        # With `count_cached`, what the cache already cost counts: a run resumed after a stop
        # does not get a fresh ceiling. Off for long-lived caches that only grow.
        self.spent_usd = cache.total_cost_usd() if cache is not None and count_cached else 0.0
        self.spawned = 0
        self._reserved = 0.0
        self._executable = resolved
        self._spawn = spawn or spawn_process
        self._gate = asyncio.Semaphore(concurrency)
        self._cwd = tempfile.mkdtemp(prefix="sancho-cli-")

    async def run(
        self,
        prompt: str,
        *,
        system: str | None = None,
        schema: Mapping[str, Any] | None = None,
    ) -> Session:
        system = self.system if system is None else system
        key = SessionCache.key(self.model, system, schema, prompt, self.effort)
        if self.cache is not None and (hit := self.cache.get(key)) is not None:
            return Session(**{**asdict(hit), "cached": True})
        async with self._gate:
            # Each session in flight holds its budget until it reports what it cost, so
            # concurrency cannot carry the total past the ceiling. The last sessions get what
            # is left, and the CLI enforces that budget itself (--max-budget-usd).
            left = self.ceiling_usd - self.spent_usd - self._reserved
            budget = round(min(self.max_budget_usd, left), 6)
            if budget < MIN_SESSION_USD:
                raise CeilingReached(
                    f"{self.spent_usd:.4f} USD spent and {self._reserved:.4f} in flight, "
                    f"of a {self.ceiling_usd:.2f} USD ceiling"
                )
            self._reserved += budget
            argv = build_argv(
                self._executable,
                model=self.model,
                system=system,
                max_budget_usd=budget,
                schema=schema,
                effort=self.effort,
            )
            stdin = b""
            if len(subprocess.list2cmdline([*argv, "--", prompt])) <= COMMAND_LINE_LIMIT:
                argv += ["--", prompt]
            else:
                stdin = prompt.encode("utf-8")
            self.spawned += 1
            try:
                code, out, err = await self._spawn(
                    argv, stdin, clean_env(os.environ), self._cwd, self.timeout_s
                )
            except BaseException:
                self._reserved -= budget
                self.spent_usd += budget  # it may have spent; nobody knows how much
                raise
            session = parse_result(out, self.model) if out else Session(ok=False, model=self.model)
            known = session.list_cost_usd > 0 or (session.ok and code == 0)
            self._reserved -= budget
            # A timeout or an unreadable reply may still have spent up to its budget.
            self.spent_usd += session.list_cost_usd if known else budget
        if code != 0:
            reason = f"exit {code}" + (f": {session.reason}" if session.reason else "")
            session = Session(**{**asdict(session), "ok": False, "reason": reason})
        if session.ok and self.cache is not None:
            self.cache.put(key, session)
        return session

    def completer(self) -> Completer:
        """A `Completer` for `LLMDecider`: the decision's schema becomes `--json-schema`."""

        async def complete(system: str, user: str, schema: dict[str, Any]) -> Completion:
            session = await self.run(user, system=system, schema=schema)
            if not session.ok:
                raise RuntimeError(f"claude cli: {session.reason or 'no answer'}")
            return session.structured, session.input_tokens, session.output_tokens

        return complete


def decider(
    *,
    model: str,
    ceiling_usd: float,
    cache_path: str | pathlib.Path | None = None,
    **options: Any,
) -> Any:
    """`create("claude-cli", model=..., ceiling_usd=...)`: an `LLMDecider` over the CLI."""
    from .llm import LLMDecider

    cache = SessionCache(cache_path) if cache_path else None
    cli = ClaudeCLI(model=model, system="", ceiling_usd=ceiling_usd, cache=cache, **options)
    return LLMDecider(cli.completer(), model=f"claude-cli:{model}")
