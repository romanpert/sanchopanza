"""The decision points an agent asks for on purpose, exposed as MCP tools.

Hooks cover what happens without the model asking (model per subtask, search tier, shell
guard, thread review). These are the ones the orchestrator calls deliberately:

- `verify_citation`: quote present in code, meaning by the decider, doubt to review.
- `evaluate_plan`: priority, saturation, tier and dependency waves for a round's lines.
- `align_entities`: same real-world entity or not, with a grey zone.
- `classify_field`: free text to a closed vocabulary, with `other` and abstention.
- `triage_text`: is this text worth the large model's context for this purpose?

And one that needs no decider at all, served on its own (`sanchopanza archive-mcp`):

- `search_archive`: BM25 over `.sanchopanza/archive` (what the autopilot cut on arrival or
  masked at compaction), returning each hit's path, meta line and best ~600-character window.
  Pull recall: the agent asks when it needs something, instead of a hook injecting it. Starts
  without `TYPESAFE_API_KEY` and builds no squire.

Requires `pip install sanchopanza[mcp]` (mcp 1.x `FastMCP` or 2.x `MCPServer`). Works with any
MCP client: Claude Code, Cursor, Codex, Copilot, Hermes or a custom harness.

    from sanchopanza.harness.mcp import build_server
    build_server(squire).run()          # stdio
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..squire import Squire

MAX_LINES = 25
# Every session pays for this text in its tool list: one line.
SEARCH_DESCRIPTION = (
    "Search earlier tool output that was cut or masked out of context (kept on disk). "
    "Returns up to k (max 5) file paths with a matching excerpt; Read a path for the full text."
)


def parse_lines(raw: Any) -> list[dict[str, str]]:
    """Accept JSON (list of {title, goal}) or plain text with one line per line."""
    if isinstance(raw, list):
        lines = raw
    else:
        text = str(raw or "").strip()
        try:
            lines = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            lines = [
                {"title": row.strip(" -*"), "goal": ""} for row in text.splitlines() if row.strip()
            ]
    if not isinstance(lines, list):
        return []
    return [
        {"title": str(row.get("title", "")), "goal": str(row.get("goal", ""))}
        for row in lines
        if isinstance(row, Mapping) and str(row.get("title", "")).strip()
    ][:MAX_LINES]


def parse_options(raw: Any) -> dict[str, str]:
    """Accept a JSON {name: description}, a JSON list of names, or names separated by |."""
    if isinstance(raw, Mapping):
        return {str(k): str(v) for k, v in raw.items()}
    text = str(raw or "").strip()
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        value = [part.strip() for part in text.split("|") if part.strip()]
    if isinstance(value, Mapping):
        return {str(k): str(v) for k, v in value.items()}
    if isinstance(value, list):
        return {str(v): "" for v in value}
    return {}


def _server(name: str) -> Any:
    """An MCP server object with a `tool()` decorator and `run()`: mcp 2.x or 1.x."""
    try:
        from mcp.server.mcpserver import MCPServer

        return MCPServer(name)
    except ImportError:
        pass
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:  # pragma: no cover
        raise RuntimeError("install sanchopanza[mcp] to expose MCP tools") from error
    return FastMCP(name)


FIND_DESCRIPTION = (
    "Find what bears on a task: kind=code (default), symbol, file, skill, agent, memory, "
    "archive or tool. Returns keys (path:lines) with an excerpt; Read a path for the full text."
)


def build_archive_server(
    root: Path,
    *,
    name: str = "sanchopanza-archive",
    find: bool | None = None,
    repo: Path | None = None,
    squire: Any = None,
) -> Any:
    """`search_archive` over the archive at `root`. With `find` (default: `SANCHOPANZA_FIND`
    set), also `find_in_repo` over the repository the server runs in (`repo`, default the
    working directory): a BM25 shortlist judged with `squire` when one is given or a key is
    set, BM25 alone otherwise. Off by default, so the lean catalog stays one tool."""
    from .. import _env

    server = add_archive(_server(name), root)
    if find is None:
        find = _env.get("FIND", "") in ("1", "true", "yes")
    if find:
        add_find(server, repo=repo, squire=squire)
    return server


def add_archive(server: Any, root: Path) -> Any:
    """`search_archive`: BM25 over the archive at `root`. No squire, no key."""
    from ..context.archive import search

    @server.tool(description=SEARCH_DESCRIPTION)
    def search_archive(query: str, k: int = 3) -> str:
        return search(root, query, k)

    return server


def add_find(server: Any, *, repo: Path | None = None, squire: Any = None) -> Any:
    """`find_in_repo`: fragments of the repository for a request (`context.repo`)."""
    from ..context.repo import find as find_fragments

    @server.tool(description=FIND_DESCRIPTION)
    async def find_in_repo(query: str, k: int = 8, kind: str = "code") -> str:
        where = repo or Path.cwd()
        judge = squire or _squire_if_keyed()
        return await find_fragments(query, where, squire=judge, k=k, kind=kind)

    return server


def _squire_if_keyed() -> Any:
    """A squire from the environment when it names a real provider, else None (free BM25)."""
    from .claude_code import decider_from_env, squire_from_env

    decider = decider_from_env()
    return None if getattr(decider, "name", "null") == "null" else squire_from_env()


def build_server(squire: Squire, *, name: str = "sanchopanza") -> Any:
    """The five decision tools on a server of their own."""
    return add_decisions(_server(name), squire)


def add_decisions(server: Any, squire: Squire) -> Any:
    """Register the five decision tools (they need a squire) on `server`."""
    from ..points.citation import ADVICE

    @server.tool()
    async def verify_citation(claim: str, quote: str, source_text: str, url: str = "") -> str:
        """Check that a quote exists in the source text and that the source supports the claim.
        Returns supported | contradicted | unsupported | fabricated | review with confidence."""
        verdict, confidence = await squire.verify_citation(
            claim=claim, quote=quote, source=source_text
        )
        return f"Verdict: {verdict} (confidence {confidence:.2f}) for {url}. {ADVICE[verdict]}"

    @server.tool()
    async def evaluate_plan(lines: str, findings: str = "") -> str:
        """Prioritize a plan before launching it. `lines` is JSON [{"title", "goal"}].
        Returns each line with priority (0-1), parallel, saturated, tier, source kind,
        dependencies and wave. Call it once per round."""
        parsed = parse_lines(lines)
        if not parsed:
            return 'No lines received. Pass JSON [{"title", "goal"}].'
        return json.dumps(
            await squire.evaluate_plan(parsed, findings=findings), ensure_ascii=False, indent=1
        )

    @server.tool()
    async def align_entities(a: str, context_a: str, b: str, context_b: str) -> str:
        """Decide whether two mentions (person, organization, law, ruling, place) are the same
        entity, reading each one's context. Returns same | different | not_sure with probability."""
        same, p = await squire.same_entity(a=a, context_a=context_a, b=b, context_b=context_b)
        label = "not_sure" if same is None else ("same" if same else "different")
        advice = {
            "same": "Merge the records.",
            "different": "Do not merge.",
            "not_sure": "Note the doubt and do not merge.",
        }[label]
        return f"Verdict: {label} (probability of same entity {p:.2f}). {advice}"

    @server.tool()
    async def classify_field(field: str, text: str, options: str, context: str = "") -> str:
        """Assign free text to one category of a closed vocabulary. `options` is JSON
        {category: description} or a list. Returns the category with probability, or
        not_sure below threshold: then leave the field null and note why."""
        opts = parse_options(options)
        if len(opts) < 2:
            return "At least two options are needed: {category: description} as JSON."
        category, p, dist = await squire.classify(
            field=field, text=text, options=opts, context=context
        )
        top = ", ".join(f"{k} {v:.2f}" for k, v in sorted(dist.items(), key=lambda kv: -kv[1])[:3])
        if category is None:
            return f"not_sure. Distribution: {top}. Leave the field null and note the doubt."
        return f"{category} (probability {p:.2f}). Distribution: {top}."

    @server.tool()
    async def triage_text(purpose: str, text: str, title: str = "", url: str = "") -> str:
        """Say whether a fetched text is worth reading for `purpose`: relevance, evidence,
        injection and source kind. In doubt it says keep."""
        result = await squire.triage_page(purpose=purpose, title=title, url=url, text=text)
        return json.dumps(
            {
                "keep": result.keep,
                "reason": result.reason,
                "relevance": round(result.relevance, 2),
                "evidence": round(result.evidence, 2),
                "injection": round(result.injection, 2),
                "source_kind": result.source_kind,
            }
        )

    return server


LABEL_DESCRIPTION = (
    "Label every item of a file (.jsonl/.csv/.txt) with a closed rubric JSON {field, options}; "
    "writes out (csv/jsonl) with label, p, margin. Cached; max_usd caps spend."
)
RANK_DESCRIPTION = (
    "Rank a page's elements for the next action toward goal. page: Playwright snapshot text, "
    "HTML, or a file path. Returns the top elements with their refs."
)


def add_label(server: Any, squire: Any = None) -> Any:
    """`label_file`: `sanchopanza.label` over a file, for an agent that has a corpus to tag."""

    @server.tool(description=LABEL_DESCRIPTION)
    async def label_file(path: str, rubric: str, out: str, max_usd: float = 0.5) -> str:
        from dataclasses import replace

        from ..label import LabelCache, Rubric, label, read_items, summary, write_rows

        base = squire or _squire_if_keyed()
        if base is None:
            return "No decision provider is configured (TYPESAFE_API_KEY): nothing labelled."
        judge = base.fork(thresholds=replace(base.thresholds, max_usd=max_usd))
        try:
            parsed = Rubric.from_mapping(json.loads(rubric))
            items = read_items(path)
        except (OSError, ValueError) as error:
            return f"Could not read the rubric or the items: {error}"
        cache = LabelCache(Path(path).with_name(".sanchopanza-label-cache.jsonl"))
        rows = await label(items, parsed, squire=judge, cache=cache)
        write_rows(out, rows)
        report = {**summary(rows), "spent_usd": round(judge.meter.cost_usd, 6), "out": out}
        return json.dumps(report, ensure_ascii=False)

    return server


def add_browse(server: Any, squire: Any = None) -> Any:
    """`rank_elements`: `sanchopanza.browse.rank` over a snapshot or HTML the agent holds."""

    @server.tool(description=RANK_DESCRIPTION)
    async def rank_elements(goal: str, page: str, done: str = "", keep: int = 15) -> str:
        from ..browse import rank, render
        from ..cli_corpus import page_elements

        candidate = Path(page) if len(page) < 400 and "\n" not in page else None
        if candidate is not None and candidate.is_file():
            page = candidate.read_text(encoding="utf-8", errors="replace")
        elements = page_elements(page)
        if not elements:
            return "No elements found: pass a Playwright snapshot (with [ref=...]) or HTML."
        steps = [line.strip() for line in done.splitlines() if line.strip()]
        judge = squire or _squire_if_keyed()
        ranked = await rank(goal, elements, squire=judge, done=steps, keep=max(1, keep))
        return render(ranked, total=len(elements), page=elements)

    return server


TOOL_SETS = ("archive", "find", "decisions", "label", "browse")


def main(argv: list[str] | None = None) -> int:
    """`python -m sanchopanza.harness.mcp --tools archive,find,decisions`: one stdio server with
    the chosen tool sets, for any MCP client (Claude Code `.mcp.json`, Codex `config.toml`,
    Cursor). `decisions` needs a provider (`SANCHOPANZA_PROVIDER` or `TYPESAFE_API_KEY`); the
    other two work without one."""
    import argparse

    from .. import _env
    from .claude_code import squire_from_env

    parser = argparse.ArgumentParser(prog="python -m sanchopanza.harness.mcp")
    parser.add_argument("--tools", default="archive,find")
    parser.add_argument("--archive", default="")
    parser.add_argument("--name", default="sanchopanza")
    args = parser.parse_args(argv)
    wanted = [t for t in args.tools.split(",") if t]
    unknown = sorted(set(wanted) - set(TOOL_SETS))
    if unknown:
        parser.error(f"unknown tool sets {unknown}; known: {list(TOOL_SETS)}")
    server = _server(args.name)
    if "archive" in wanted:
        from ..context.archive import root_for

        add_archive(server, root_for(Path.cwd(), override=args.archive or _env.get("ARCHIVE")))
    if "find" in wanted:
        add_find(server)
    if "decisions" in wanted:
        add_decisions(server, squire_from_env())
    if "label" in wanted:
        add_label(server)
    if "browse" in wanted:
        add_browse(server)
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
