"""Browse lean: a Claude Code `PostToolUse` hook that prunes browser snapshots on arrival.

An agent browsing reads the page's whole accessibility snapshot, and pays for it again on every
later turn. It arrives three ways (checked 2026-09-30 with Playwright MCP 0.0.83 and
`@playwright/cli` 0.1.18): inline in an MCP tool result, on `Bash` stdout from
`playwright-cli snapshot` (or agent-browser), or as a `.yml` file that `playwright-cli goto` and
Playwright MCP write by default and the agent then `Read`s. Wherever it is found
(`browse.snapshot_block`), this hook replaces a large one with the same YAML pruned
(`browse.prune_snapshot`): the elements `browse.rank` puts first for the task, every heading, the
text lines that bear on the task, and each kept line's ancestors, so the refs still work and
the tree still reads as the page. Everything outside the YAML block (the code Playwright ran,
the URL, the title, console messages) passes as it was. The full result goes to the archive and
the reply says where, so `search_archive`, `Read`, or a new snapshot recovers anything cut.

Opt-in. In `.claude/settings.json`:

    {"hooks": {"PostToolUse": [{"matcher": "Bash|Read|mcp__playwright__.*|mcp__plugin_playwright.*",
      "hooks": [{"type": "command", "command": "python -m sanchopanza.harness.browse_hook"}]}]}}

Environment (`SANCHOPANZA_<NAME>`): BROWSE_CHARS (snapshot size that triggers a cut, default
6000), BROWSE_KEEP (elements kept, default 20), BROWSE_TEXT (characters of text lines kept,
default 3000), BROWSE_MAX_ELEMENTS (past this many, BM25 shortlists what the decider ranks,
default 600), SESSION_MAX_USD (the autopilot's per-session ceiling, shared), and the usual
provider settings. Without a provider the ranking is BM25 (free). Fail open everywhere.

Measured (`docs/results/2026-09-30-browse/`, Phase 3): in 36 real Claude Code sessions browsing
with `playwright-cli`, it answered as often and **saved nothing** (+0.0095 USD a session,
[-0.006, +0.027]): it acted in 8 of 18, because playwright-cli's snapshots are already moderate
and the agent used `find` and `eval`. It paid on the one large snapshot. With Playwright MCP
(Phase 3b, 48 sessions) it saved nothing either, for three faults since fixed: Claude Code
replaces an MCP result past its token limit with a notice before any `PostToolUse` hook runs, so
the hook now reads the saved result behind the notice (only from its own session's
`tool-results` folder) and returns it pruned; the agent's own `find` results pass untouched; and
the goal is `browse_goal`, which keeps the question at the end of a request. Phase 3c found
two more (a `Read` with a limit and a targeted snapshot were cut; recovery read the whole
archive), fixed too. Registered results since, each on tasks it was not fixed on: with
Playwright MCP 12.9 % cheaper on six tasks (3d), 12.4 % on twelve with the interval crossing
zero (3h), nothing clear on twelve more (3f), 13.4 % on twelve more (3j); with playwright-cli
about 5 % on twelve (3g), nothing on twelve more (3i, 3k: in 3k the agent used `find` and the
hook cut nothing). Questions about position cost answers in 3h and 3i and now pass through
uncut (3j, 3k: 30 of 30 right in each arm). Which questions those are, the decider says
(`judged_position`, one Truth per request and session: 0.93 / 1.0 on goals sealed after it was
frozen, where the word rule `asks_for_position` scored 0.50 / 0.31); the rule decides without
one. 3i's losses (X2, X4) were a `Bash` output past
30,000 characters: Claude Code hands the hook that prefix and shows the model 2,000 characters
of the reply, so the hook ranks the whole saved output and replies with what fits
(`_persisted`, `_preview`; for a question about position, the content in page order). An infobox
the cut touches keeps its keys and values (`browse._key_value_rows`). Opt-in.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .. import _env

DEFAULT_CHARS = 6000
DEFAULT_KEEP = 20
DEFAULT_TEXT = 3000
DEFAULT_MAX_ELEMENTS = 600
SAVED_MAX_BYTES = 20_000_000
# What may replace Claude Code's notice. Its limit is 25,000 tokens by default, and the GitHub
# page it refused was 72,000 characters; past this the notice stays (review 2026-10-01).
OVERSIZE_RETURN_MAX = 60_000
# What Claude Code shows the model of a hook's output for a `Bash` result it saved to a file
# ("Preview (first 2KB)"; probed 2026-10-01: a marker at 3,000 characters was not seen).
PREVIEW_CHARS = 2000
# Claude Code's notice when an MCP result passes its token limit. The hook is handed this
# notice, never the result (probed 2026-09-30 with a recording hook and Playwright MCP 0.0.83).
_OVERSIZE = re.compile(
    r"^Error: result \([^)]*\) exceeds maximum allowed tokens\. "
    r"Output has been saved to (?P<path>.+?\.txt)\.\s*$",
    re.M,
)
# The CLI's `find` subcommand, after any flags; not the word inside a URL (`goto .../find-a-store`).
_CLI_FIND = re.compile(r"\b(?:playwright-cli|agent-browser)(?:\s+-\S+)*\s+find\b")


def _int(name: str, default: int) -> int:
    try:
        return max(0, int(_env.get(name, str(default))))
    except ValueError:
        return default


def _reads_the_archive(event: Mapping[str, Any], root: Any) -> bool:
    """A `Read` of a file under the archive root: the agent asking for what was cut."""
    from pathlib import Path

    if str(event.get("tool_name", "")) != "Read":
        return False
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), Mapping) else {}
    target = str(tool_input.get("file_path") or "")
    if not target:
        return False
    try:
        return Path(target).resolve().is_relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return False


_NARROWING = frozenset({"target", "ref", "selector", "element", "depth"})


def _is_search(tool: str, tool_input: Mapping[str, Any]) -> bool:
    """What the agent narrowed itself: `browser_find` or a browser CLI's `find` (pruning its
    answer sent the agent to the whole archive in 3 of 4 cases, Phase 3b), a `Read` of part of a
    file, and a snapshot of one element or depth (both cut in Phase 3c's M4, and the agent went
    looking for what the cut removed)."""
    if tool.endswith("browser_find"):
        return True
    if tool == "Read":
        return any(tool_input.get(k) not in (None, "") for k in ("offset", "limit"))
    if tool.endswith("browser_snapshot"):
        return any(tool_input.get(k) not in (None, "") for k in _NARROWING)
    return tool == "Bash" and bool(_CLI_FIND.search(str(tool_input.get("command") or "")))


_URL = re.compile(r"https?://([^/\s?#]+)\S*")
GOAL_LIMIT = 400  # what `points.browse` shows of the goal
STEP_LIMIT = 90
FOLLOW_UP_LIMIT = 110


def browse_goal(messages: Any) -> str:
    """What the ranking is for: the request, the latest one if it changed, and the agent's last
    stated step. Not `purpose_of`, which the arrival cut shares and was measured with: it keeps
    the first 130 characters of the request, and a request that opens with a URL and
    instructions ends with its question (a 2026-09-30 probe lost "which license" that way).
    URLs are cut to their host; a long request keeps its start and its end. The follow-up and
    the step are sized first and the request takes what is left, so no part falls off the end
    (review 2026-10-01: a long request and a follow-up used to push the step out)."""
    from ..context.transcript import is_prompt, message_text
    from ..points.context import head_tail
    from ..text import truncate

    def clean(text: str) -> str:
        return " ".join(_URL.sub(r"\1", text).split())

    def fit(text: str, limit: int) -> str:
        # head_tail adds a marker of about 30 characters to what it keeps
        return text if len(text) <= limit else head_tail(text, max(40, limit - 32))

    prompts = [clean(message_text(m)) for m in messages if is_prompt(m)]
    intent = next(
        (message_text(m) for m in reversed(messages)
         if m.get("role") == "assistant" and message_text(m)),
        "",
    )  # fmt: skip
    if not prompts:
        return ""
    tail = []
    if len(prompts) > 1 and prompts[-1] != prompts[0]:
        tail.append(f"Now asked: {fit(prompts[-1], FOLLOW_UP_LIMIT)}")
    if intent:
        tail.append(f"Agent's step: {truncate(clean(intent), STEP_LIMIT)}")
    room = GOAL_LIMIT - len("Task: ") - sum(len(t) + 1 for t in tail)
    return "\n".join([f"Task: {fit(prompts[0], room)}", *tail])


_ORDINAL = re.compile(
    r"\b(?:first|second|third|fourth|fifth|last|final|penultimate|next-to-last|topmost|top"
    r"|most recent|\d+(?:st|nd|rd|th))\b\s+(?P<next>[a-z]+)",
    re.I,
)
# A place on its own, whatever the words around it.
_AT_AN_END = re.compile(r"\bat the (?:top|bottom)\b", re.I)
# Where the facts come from, not a list: "according to the page", "per the infobox".
_SOURCE = re.compile(r"\b(?:according to|per)\s+(?:the|this|its|her|his)\s+\w+", re.I)
# What follows an ordinal when it is about time, not place in a list ("when did it first appear").
_NOT_A_PLACE = frozenset(
    {"appear", "appeared", "appears", "released", "release", "published", "introduced",
     "announced", "launched", "seen", "used", "written", "time", "came", "became",
     "edited", "updated", "modified"}
)  # fmt: skip


# A word that says the ordinal counts things on the page: "the first book listed", "the third
# one", "ranked first in the table". Without one, "the first ascent" is an event, not a place.
_LISTING = re.compile(
    r"\b(?:listed|lists?|table|page|there|on it|one|ranked|rank|rows?|entry|entries|items?"
    r"|results?|shown|appears?|category|answers?|comments?|posts?)\b",
    re.I,
)


def asks_for_position(goal: str) -> bool:
    """Whether the request asks for an element by its place: the first book listed, the 3rd quote.

    Phases 3c (M6), 3f (W12), 3h and 3i (X12): the cut kept the elements to act on and dropped
    the first one listed; in 3h and 3i three runs answered with the wrong author. Nothing in a
    snapshot line says it comes first, so for such a goal the hook does not cut. Only the
    request is read, never the agent's step ("First I'll open the page"), and the ordinal needs
    a word of listing beside it: Z2's "the first ascent" (3l) left a page uncut."""
    asked = "\n".join(line for line in goal.splitlines() if not line.startswith("Agent's step:"))
    if _AT_AN_END.search(asked):
        return True
    if not _LISTING.search(_SOURCE.sub(" ", asked)):
        return False
    return any(m["next"].lower() not in _NOT_A_PLACE for m in _ORDINAL.finditer(asked))


POSITION_POINT = "browse_position"
POSITION_CUT = 0.5
# Frozen in 6d3bbe5 and confirmed on goals sealed after it (14085fe, df595ba): precision 0.929,
# recall 1.0, where the word rule above scored 0.50 / 0.31 (and 0.30 / 0.20 on the set before).
POSITION_INSTRUCTIONS = (
    "Does this browsing request pick out an element by its place on the web page: the "
    "first, second, last, top or bottom one of a list, menu, table, sidebar, footer, grid "
    "or set of tabs, so that answering needs the order in which the page shows things?"
)
POSITION_CRITERIA = {
    "true": "The element wanted is identified by where it sits among others on the page "
    "(the 3rd link in the sidebar, the final item in the list, the story at the top).",
    "false": "An ordinal word describes something else: a time or an event (the first "
    "ascent, the final year, the last album), part of a name or a quantity (last name, "
    "top speed, first-class), or a fact the text states (the first president). Or there "
    "is no ordinal at all.",
}


def _request_of(goal: str) -> str:
    """The user's words in a `browse_goal`: never the agent's step, without the labels."""
    lines = [line for line in goal.splitlines() if not line.startswith("Agent's step:")]
    return "\n".join(line.removeprefix("Task: ") for line in lines).strip()


async def judged_position(goal: str, squire: Any, cache_dir: Path, *, over: bool) -> bool:
    """`asks_for_position`, decided by the decider when there is one and the session is under
    its ceiling. Asked once per request and session (`cache_dir/position.json`); a provider
    that is absent, down or out of budget leaves the word rule to decide."""
    from ..contract import Truth

    request = _request_of(goal)
    if over or not request:
        return asks_for_position(goal)
    cache = cache_dir / "position.json"
    known: dict[str, Any] = {}
    with contextlib.suppress(OSError, ValueError):
        known = dict(json.loads(cache.read_text(encoding="utf-8")))
    if isinstance(known.get(request), (int, float)):
        return float(known[request]) >= POSITION_CUT
    question = Truth(instructions=POSITION_INSTRUCTIONS, criteria=POSITION_CRITERIA)
    decision = await squire.decide(POSITION_POINT, {"request": request}, {"position": question})
    answer = decision.answer("position")
    if answer.empty or answer.truth is None:
        return asks_for_position(goal)
    squire.record(decision, request_chars=len(request))
    with contextlib.suppress(OSError):
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({**known, request: answer.truth}), encoding="utf-8")
    return answer.truth >= POSITION_CUT


def _oversized(text: str, event: Mapping[str, Any]) -> str | None:
    """The saved result behind Claude Code's too-large notice, or None."""
    match = _OVERSIZE.match(text.strip())
    return None if match is None else _session_file(match["path"], event)


def _persisted(response: Any, event: Mapping[str, Any]) -> tuple[bool, str | None]:
    """Whether Claude Code saved this output to a file, and the whole output if so.

    Past 30,000 characters a `Bash` output is saved to `tool-results`; the hook is handed
    `stdout` cut at 30,000 with `persistedOutputPath` (probed 2026-10-01). Phase 3i ranked and
    archived that prefix: 128 of France's 3,569 elements, and an archive without the answer."""
    if not isinstance(response, Mapping) or not response.get("persistedOutputPath"):
        return False, None
    return True, _session_file(str(response["persistedOutputPath"]), event)


def _session_file(path: str, event: Mapping[str, Any]) -> str | None:
    """A file Claude Code saved, read only from this session's own `tool-results` folder, next
    to its transcript: a notice is text, and a page can print one naming any file."""
    transcript = str(event.get("transcript_path") or "")
    if not transcript:
        return None
    allowed = Path(transcript).with_suffix("") / "tool-results"
    try:
        saved = Path(path).resolve()
        if not saved.is_relative_to(allowed.resolve()) or not saved.is_file():
            return None
        if saved.stat().st_size > SAVED_MAX_BYTES:
            return None
        return saved.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None


_CONTAINER = re.compile(r"^- [a-z]+(?: \[[^\]]*\])*:$")
_REF = re.compile(r"\[ref=([^\]]+)\]")


def preview_lines(pruned: str, first: frozenset[str] = frozenset()) -> list[str]:
    """The pruned snapshot's lines that carry something, flat: no bare containers, no `/url`,
    no `[cursor=pointer]`. The tree's shape costs characters a 2,000-character preview lacks.
    Lines of the elements in `first` (the ranked ones) come before the rest, each in page order:
    text lines that match the task can fill the preview before the element it needs."""
    ranked, rest = [], []
    for raw in pruned.splitlines():
        line = raw.strip()
        if not line.startswith("- ") or line.startswith("- /url:") or _CONTAINER.match(line):
            continue
        line = line[2:].replace(" [cursor=pointer]", "").removesuffix(":")
        ref = _REF.search(line)
        (ranked if ref and ref[1] in first else rest).append(line)
    return ranked + rest


def _preview(text: str, span: tuple[int, int], pruned: str, saved: Path, whole: Path,
             kept: frozenset[str], total: int) -> str:  # fmt: skip
    """What fits in the 2,000 characters Claude Code shows of a `Bash` output it saved: where
    the cut and the whole page are, then the kept lines that carry content, in page order."""
    page = [line for line in text[: span[0]].splitlines() if line.startswith("- Page ")]
    head = (
        f"# sanchopanza: the page ({total} elements) is too large to show here. The lines it "
        f"most likely needs are below; all {len(kept)} kept elements in context: Read {saved}; the "
        f"whole page: Grep {whole}.\n"
    )
    out = head + "".join(f"{line}\n" for line in page)
    for line in filter(_says_something, preview_lines(pruned, kept)):
        if len(out) + len(line) + 1 > PREVIEW_CHARS:
            break
        out += line + "\n"
    return out


_NOT_CONTENT = frozenset({"banner", "navigation", "contentinfo", "complementary", "search"})


def content_in_order(body: str) -> str:
    """The snapshot without the subtrees of its banner, navigation, footer and sidebars."""
    lines, out, skip_below = body.splitlines(), [], None
    for line in lines:
        depth = len(line) - len(line.lstrip())
        if skip_below is not None and depth > skip_below:
            continue
        skip_below = None
        role = re.match(r"\s*- ([a-z]+)", line)
        if role and role[1] in _NOT_CONTENT:
            skip_below = depth
            continue
        out.append(line)
    return "\n".join(out)


_SAYS_NOTHING = re.compile(r"^[a-z]+(?: \[[^\]]*\])*:?\s*(?P<rest>.*)$")
_NAMES_STRUCTURE = re.compile(r"\b(table|list)\b", re.I)
_ASKS_FOR_LAST = re.compile(r"\blast\b", re.I)


def _says_something(line: str) -> bool:
    """A flat preview line with a letter or digit in its name or text: not a row of star icons."""
    match = _SAYS_NOTHING.match(line)
    rest = match["rest"] if match else line
    return bool(re.search(r"[^\W_]", rest))


def position_lines(body: str, goal: str) -> list[str]:
    """The content lines a question about position reads, in page order: without navigation,
    from the first table or list when the question names one (Y5: Wikipedia's introduction
    filled the preview before "the first lake in the table")."""
    lines = content_in_order(body).splitlines()
    named = _NAMES_STRUCTURE.search(goal)
    if named:
        role = named[1].lower()
        start = next((i for i, line in enumerate(lines)
                      if re.match(rf"\s*- {role}\b", line)), 0)  # fmt: skip
        lines = lines[start:]
    return [line for line in preview_lines("\n".join(lines)) if _says_something(line)]


def _position_preview(text: str, span: tuple[int, int], whole: Path, total: int, goal: str) -> str:
    """For a question about position on a saved output: no ranking, the page's content lines in
    their own order, so the first stays first; for "the last", the end of the page. Passing it
    through would show the model the first 2,000 characters, which are the banner and the
    navigation (T6, W12, Y5, Y9)."""
    page = list(dict.fromkeys(
        line for line in text[: span[0]].splitlines() if line.startswith("- Page ")
    ))  # fmt: skip
    head = (
        f"# sanchopanza: the page ({total} elements) is too large to show here. Its content in "
        f"page order, without navigation, is below; the whole page: Grep {whole}.\n"
        + "".join(f"{line}\n" for line in page)
    )
    lines = position_lines(text[span[0] : span[1]], goal)
    room, shown = PREVIEW_CHARS - len(head), []
    for line in reversed(lines) if _ASKS_FOR_LAST.search(goal) else lines:
        if len(line) + 1 > room:
            break
        shown.append(line)
        room -= len(line) + 1
    if _ASKS_FOR_LAST.search(goal):
        shown.reverse()
    return head + "".join(f"{line}\n" for line in shown)


def _reply(response: Any, path: Any, new_text: str) -> dict[str, Any]:
    from . import autopilot

    updated = autopilot.replaced(response, path, new_text)
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": updated}}


def say(text: str) -> None:
    with contextlib.suppress(Exception):
        sys.stderr.write(f"sanchopanza browse: {text}\n")


async def post_tool_use(event: Mapping[str, Any], squire: Any) -> dict[str, Any]:
    """The hook body. `{}` means untouched."""
    from ..browse import elements_from_snapshot, prune_snapshot, rank, snapshot_block
    from ..context import archive as archive_mod
    from . import autopilot

    response = event.get("tool_response")
    found = autopilot.text_field(response)
    if found is None:
        return {}
    path, text = found
    tool = str(event.get("tool_name", ""))
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), Mapping) else {}
    searched = _is_search(tool, tool_input)
    if searched and not (isinstance(response, Mapping) and response.get("persistedOutputPath")):
        return {}  # the agent's own search: never cut (unless saved, where it is never seen)
    # Only an MCP result is ever replaced by Claude Code's notice; a `cat` or `curl` of a page
    # that prints one must not pull another file in (review 2026-10-01).
    saved_text = _oversized(text, event) if tool.startswith("mcp__") else None
    if saved_text is not None:  # the result itself replaces the notice, pruned, in its place
        text = saved_text
    persisted, whole = _persisted(response, event)
    if persisted:
        if whole is None:
            return {}  # only a 30,000-character prefix: never rank or archive a fragment
        text = whole
    span = snapshot_block(text)
    if span is None or span[1] - span[0] < _int("BROWSE_CHARS", DEFAULT_CHARS):
        return {}
    config = autopilot.config_from_env()
    root, session = autopilot._root(event, config), autopilot._session(event)
    if _reads_the_archive(event, root):
        return {}  # the way back to a full snapshot: never pruned again
    ledger = autopilot.read_ledger(root, session)
    body = text[span[0] : span[1]]
    elements = elements_from_snapshot(body)
    if not elements:
        return {}
    purpose = browse_goal(autopilot._messages(event))
    meta = {"tool": tool, "about": f"{tool} snapshot", "by": "browse"}
    over = autopilot._over_ceiling(ledger, config)
    position = not searched and await judged_position(
        purpose, squire, archive_mod.session_dir(root, session), over=over
    )
    if squire.meter.decisions:
        with contextlib.suppress(OSError):
            autopilot.write_ledger(root, session, autopilot._charged(ledger, squire))
    # The first, the third, the last, or the agent's own search: an order a cut cannot keep.
    # Uncut unless Claude Code saved the output, where the model would see 2,000 characters.
    if searched or position:
        if not persisted:
            return {}
        saved = archive_mod.write_entry(
            archive_mod.session_dir(root, session),
            f"browse-{event.get('tool_use_id') or tool}",
            text,
            meta,
        )
        squire.journal.record(
            "browse", {"tool": tool, "elements": len(elements), "kept": 0, "chars": len(body),
                       "kept_chars": 0, "ranked_by": "page order", "preview": True},
        )  # fmt: skip
        new_text = _position_preview(text, span, saved, len(elements), purpose)
        return _reply(response, path, new_text)
    if not purpose:
        return {}  # nothing to rank for: cutting blind could drop what the agent needs
    # Phase 3f (W4, W7): ranking every one of 2,000-3,000 elements cost Jev more than the cut
    # saved; past this many, BM25 shortlists what the decider sees (about 21 calls at most).
    most = _int("BROWSE_MAX_ELEMENTS", DEFAULT_MAX_ELEMENTS)
    ranked = await rank(
        purpose,
        elements,
        squire=None if over else squire,
        keep=_int("BROWSE_KEEP", DEFAULT_KEEP),
        shortlist=most if most and len(elements) > most else None,
    )
    pruned, left_out = prune_snapshot(
        body,
        [r.element.key for r in ranked],
        purpose=purpose,
        text_budget=_int("BROWSE_TEXT", DEFAULT_TEXT),
    )
    if len(pruned) >= 0.8 * len(body):
        return {}
    new_text_chars = len(text) - len(body) + len(pruned)
    if saved_text is not None and new_text_chars > OVERSIZE_RETURN_MAX:
        return {}  # still past Claude Code's limit: its notice and saved file stay
    saved = archive_mod.write_entry(
        archive_mod.session_dir(root, session),
        f"browse-{event.get('tool_use_id') or tool}",
        text,
        meta,
    )
    note = (
        f"# sanchopanza kept {len(ranked)} of {len(elements)} elements and {left_out} snapshot "
        f"lines were left out. If what you need is not here, Grep {saved} for it (never "
        "pruned; Read it whole only if a search will not do).\n"
    )
    squire.journal.record(
        "browse",
        {
            "tool": tool,
            "elements": len(elements),
            "kept": len(ranked),
            "chars": len(body),
            "kept_chars": len(pruned),
            "ranked_by": "bm25" if over else squire.provider,
            "preview": persisted,
        },
    )
    with contextlib.suppress(OSError):
        autopilot.write_ledger(root, session, autopilot._charged(ledger, squire))
    if persisted:  # the model sees 2,000 characters of this: the cut goes to a file it can Read
        cut = archive_mod.write_entry(
            archive_mod.session_dir(root, session),
            f"browse-{event.get('tool_use_id') or tool}-pruned",
            pruned,
            {**meta, "about": f"{tool} snapshot, pruned"},
        )
        keys = frozenset(r.element.key for r in ranked)
        new_text = _preview(text, span, pruned, cut, saved, keys, len(elements))
    else:
        new_text = text[: span[0]] + note + pruned + text[span[1] :]
    updated = autopilot.replaced(response, path, new_text)
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": updated}}


def main(argv: list[str] | None = None) -> int:
    # Bytes, decoded as UTF-8: Claude Code writes UTF-8, and on Windows `sys.stdin` decodes with
    # the console's code page, which turned playwright-cli's box-drawing banner into surrogates
    # and made every write of the event fail (Phase 3 pilot, 2026-09-30).
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0
    if not isinstance(event, dict) or event.get("hook_event_name") != "PostToolUse":
        return 0
    try:
        from .claude_code import squire_from_env

        output = asyncio.run(post_tool_use(event, squire_from_env(redact=True)))
    except Exception as error:  # fail open at the process boundary, never silently
        say(f"passed through unchanged ({error.__class__.__name__}: {error})")
        return 0
    if output:
        sys.stdout.buffer.write(json.dumps(output, ensure_ascii=False).encode("utf-8"))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
