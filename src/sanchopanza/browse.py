"""Browse cheaply: from a page to the few elements the next action needs.

A browsing agent reads the whole page on every step: Playwright MCP's accessibility snapshot,
or the HTML, is tens of thousands of tokens, and the model's job on it is often a closed choice
(which of these links, buttons and fields to act on next). That choice is the decision model's
shape. This module does three things, each usable alone:

1. **Read the page into elements, by code.** `elements_from_snapshot` parses Playwright MCP's
   YAML snapshot (roles, names, `[ref=eN]`, `/url` children, the heading each sits under);
   `elements_from_html` parses HTML with the standard library (every element carrying a
   `backend_node_id`, as Mind2Web's pages do, or else every interactive one). No dependency.
2. **Rank them for a goal** (`rank`). Without a squire, BM25 over each element's line: free.
   With one, a top-k tournament of in-context calls (`points.browse`): every element judged
   beside `GROUP_MAX - 1` others, the best `finalists` judged again together, and the two
   rounds' probabilities mixed (`blend`, LATTICE's path relevance). Unanswered
   elements keep their round-one probability; a failed decider degrades to BM25.
3. **Render a lean page** (`render`): the kept elements with their refs, so the agent can act
   on them directly, and one line saying how many were left out and where the full page is.

Measured on Mind2Web in `docs/results/2026-09-30-browse/`. The decider never writes: it only
orders what code read from the page, and a kept ref is always one the page actually has.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from .points import browse as questions_mod
from .text import BM25Index, truncate

NAME_LIMIT = 160
# Round one's weight in a finalist's score. On Mind2Web's 169 registered steps (the development
# set, docs/results/2026-09-30-browse/) the final round alone ranked worse than round one alone
# (Recall@10 70.4 % against 76.9 %) and the even mix best at every k (77.5 %, R@20 85.8 %):
# rejudged among 29 strong rivals, the target loses probability it had among ordinary ones.
# Chosen on that set, so confirmed on new steps before any number is claimed (prereg-confirm.md).
BLEND = 0.5
TEXT_CAP = 300

INTERACTIVE_ROLES = frozenset(
    {
        "link", "button", "textbox", "searchbox", "checkbox", "radio", "combobox", "option",
        "menuitem", "menuitemcheckbox", "menuitemradio", "tab", "switch", "slider",
        "spinbutton", "listbox", "treeitem", "gridcell", "columnheader",
    }
)  # fmt: skip
INTERACTIVE_TAGS = frozenset(
    {"a", "button", "input", "select", "textarea", "option", "label", "summary"}
)
_VOID = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
     "source", "track", "wbr"}
)  # fmt: skip
_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_SKIP_TEXT = frozenset({"script", "style", "noscript", "template"})
_ATTRS_SHOWN = ("type", "name", "placeholder", "aria-label", "title", "alt", "value", "role")
# Class words that say nothing about what an element does. A word with no vowel is dropped too
# (`svg`, `btn`, `jsx`, library prefixes like `mntl`), as is any with a digit (build hashes).
_CLASS_NOISE = frozenset(
    {"icon", "icons", "button", "new", "item", "items", "wrapper", "container", "inner",
     "outer", "component", "element", "block", "content", "active", "default", "small",
     "large", "medium", "left", "right", "image", "img", "link", "text", "label"}
)  # fmt: skip
CLASS_WORDS = 4


@dataclass(frozen=True, slots=True)
class Element:
    """One thing on a page an agent can act on. `key` is the page's own handle for it: a
    Playwright ref (`e12`) or a `backend_node_id`, so an action can name it back."""

    key: str
    role: str
    name: str
    context: str = ""

    def line(self) -> str:
        """What a reader (BM25 or the decider) sees: role, name, where it sits."""
        name = f' "{self.name}"' if self.name else ""
        where = f" | {self.context}" if self.context else ""
        return f"{self.role}{name}{where}"

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "role": self.role, "name": self.name, "context": self.context}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> Element:
        return cls(
            str(raw["key"]), str(raw.get("role", "")), str(raw.get("name", "")),
            str(raw.get("context", "")),
        )  # fmt: skip


# --- reading a page -----------------------------------------------------------------------


class _Collector(HTMLParser):
    def __init__(self, *, all_with_ids: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.all_with_ids = all_with_ids
        self.records: list[dict[str, Any]] = []
        self.stack: list[tuple[str, int | None]] = []  # (tag, record index or None)
        self.heading = ""
        self._heading_open: int | None = None
        self._skip = 0
        self._counter = 0

    def _wanted(self, tag: str, attrs: Mapping[str, str]) -> bool:
        if self.all_with_ids:
            return "backend_node_id" in attrs
        return (
            tag in INTERACTIVE_TAGS
            or attrs.get("role", "") in INTERACTIVE_ROLES
            or "onclick" in attrs
            or (attrs.get("tabindex", "-1") not in ("-1", ""))
        )

    def _feed_text(self, text: str) -> None:
        for _, index in self.stack:
            if index is None:
                continue
            record = self.records[index]
            if len(record["text"]) < TEXT_CAP:
                record["text"] += text
        if self._heading_open is not None:
            self.heading = (self.heading + text)[:120]

    def handle_starttag(self, tag: str, raw: list[tuple[str, str | None]]) -> None:
        attrs = {k: (v or "") for k, v in raw}
        if tag in _SKIP_TEXT:
            self._skip += 1
        if tag in _HEADINGS:
            self.heading = ""
            self._heading_open = len(self.stack)
        index = None
        if self._wanted(tag, attrs):
            self._counter += 1
            key = attrs.get("backend_node_id") or f"h{self._counter}"
            parent = next((i for _, i in reversed(self.stack) if i is not None), None)
            self.records.append({"key": key, "tag": tag, "attrs": attrs, "text": "",
                                 "under": self.heading.strip(), "parent": parent})  # fmt: skip
            index = len(self.records) - 1
        for label in ("alt", "aria-label", "placeholder", "value", "title"):
            if attrs.get(label) and (tag in _VOID or label == "aria-label"):
                self._feed_text(" " + attrs[label] + " ")
                if index is not None and tag in _VOID:
                    self.records[index]["text"] += " " + attrs[label] + " "
                break
        if tag not in _VOID:
            self.stack.append((tag, index))

    def handle_startendtag(self, tag: str, raw: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, raw)
        if tag not in _VOID and self.stack:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TEXT and self._skip:
            self._skip -= 1
        for depth in range(len(self.stack) - 1, -1, -1):
            if self.stack[depth][0] == tag:
                del self.stack[depth:]
                break
        if self._heading_open is not None and len(self.stack) <= self._heading_open:
            self._heading_open = None

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = " ".join(data.split())
        if text:
            self._feed_text(" " + text)


def _role_of(tag: str, attrs: Mapping[str, str]) -> str:
    if attrs.get("role"):
        return attrs["role"]
    if tag == "a":
        return "link"
    if tag == "input":
        kind = attrs.get("type", "text")
        return {"submit": "button", "button": "button", "checkbox": "checkbox",
                "radio": "radio", "search": "searchbox"}.get(kind, "textbox")  # fmt: skip
    if tag == "select":
        return "combobox"
    return tag


def _class_words(classes: str) -> list[str]:
    """What an element's CSS classes say it does: `add-wishlist-new__icon` -> add, wishlist."""
    words: list[str] = []
    for raw in re.split(r"[\s_\-]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", classes)):
        word = raw.lower()
        if (
            len(word) < 3
            or word in _CLASS_NOISE
            or word in words
            or any(c.isdigit() for c in word)
            or not any(c in "aeiouy" for c in word)
        ):
            continue  # fmt: skip
        words.append(word)
    return words[:CLASS_WORDS]


def _unnamed_hints(record: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> list[str]:
    """For an element with no name: what its classes say, and the element holding it.

    Mind2Web's development misses (docs/results/2026-09-30-browse/, misses.py) included unnamed
    SVG icons whose classes said what they do (`add-wishlist-new__icon` for "save to
    wishlist", `save-icon-favorite` inside a "Save" button) and the reader threw that away."""
    hints = []
    words = _class_words(str(record["attrs"].get("class", "")))
    if words:
        hints.append("looks like: " + " ".join(words))
    parent = record.get("parent")
    if parent is not None:
        holder = records[parent]
        name = " ".join(str(holder["text"]).split())
        if name:
            role = _role_of(holder["tag"], holder["attrs"])
            hints.append(f'inside {role} "{truncate(name, 60)}"')
    return hints


def elements_from_html(html: str, *, all_with_ids: bool | None = None) -> list[Element]:
    """Every element of an HTML page an agent could act on, in document order.

    With `backend_node_id` attributes in the page (Mind2Web's cleaned HTML, a CDP dump) every
    element carrying one is read, because the page's own candidate list decides what counts;
    otherwise the interactive ones (links, buttons, fields, ARIA widgets, click handlers).
    """
    if all_with_ids is None:
        all_with_ids = "backend_node_id=" in html
    parser = _Collector(all_with_ids=all_with_ids)
    parser.feed(html)
    parser.close()
    out = []
    for record in parser.records:
        attrs = record["attrs"]
        name = " ".join(str(record["text"]).split())
        shown = [f"{k}={attrs[k]}" for k in _ATTRS_SHOWN if attrs.get(k) and attrs[k] not in name]
        hints = [] if name else _unnamed_hints(record, parser.records)
        context = "; ".join(
            part for part in (f"under {record['under']}" if record["under"] else "",
                              " ".join(shown), *hints) if part
        )  # fmt: skip
        out.append(
            Element(
                key=str(record["key"]),
                role=_role_of(record["tag"], attrs),
                name=truncate(name, NAME_LIMIT),
                context=truncate(context, NAME_LIMIT),
            )
        )
    return out


_SNAPSHOT_LINE = re.compile(
    r"^(?P<indent>\s*)- (?P<role>[A-Za-z][\w-]*)"
    r'(?: "(?P<name>(?:[^"\\]|\\.)*)")?'
    r"(?P<rest>[^:]*?)(?::\s*(?P<text>.*))?$"
)
_REF = re.compile(r"\[ref=([\w-]+)\]")
_URL = re.compile(r"^\s*- /url:\s*(?P<url>\S+)")


def elements_from_snapshot(snapshot: str, *, interactive_only: bool = True) -> list[Element]:
    """The elements of a Playwright MCP accessibility snapshot (YAML), in page order.

    Each keeps its `ref`, so `browser_click(ref=...)` works on what is returned. The heading an
    element sits under and a link's `/url` go into its context.
    """
    out: list[dict[str, str]] = []
    heading = ""
    for raw in snapshot.splitlines():
        url = _URL.match(raw)
        if url and out:
            out[-1]["context"] = (out[-1]["context"] + f" url={url['url']}").strip()
            continue
        match = _SNAPSHOT_LINE.match(raw)
        if not match:
            continue
        role = match["role"]
        name = (match["name"] or "").replace('\\"', '"')
        ref = _REF.search(match["rest"] or "")
        if role == "heading":
            heading = name or (match["text"] or "")
        if ref is None or (interactive_only and role not in INTERACTIVE_ROLES):
            continue
        text = (match["text"] or "").strip()
        out.append({"key": ref.group(1), "role": role,
                    "name": truncate(name or text, NAME_LIMIT),
                    "context": f"under {truncate(heading, 100)}" if heading else ""})  # fmt: skip
    return [Element(**record) for record in out]


# --- ranking ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Ranked:
    element: Element
    p: float | None  # the last probability the decider gave it; None with no decider
    bm25: float


def _bm25_order(goal: str, done: Sequence[str], elements: Sequence[Element]) -> list[float]:
    index = BM25Index([e.line() for e in elements])
    return index.scores(" ".join([goal, *list(done)[-2:]]))


async def rank(
    goal: str,
    elements: Sequence[Element],
    *,
    squire: Any = None,
    done: Sequence[str] = (),
    keep: int = 10,
    finalists: int = questions_mod.GROUP_MAX,
    shortlist: int | None = None,
    blend: float = BLEND,
) -> list[Ranked]:
    """The `keep` elements most likely to be acted on next, best first.

    `shortlist` sends only that many BM25-best elements to the decider (None: all of them).
    `blend` is the weight of round one in a finalist's score: 0 uses the final round alone, 1
    skips the final round. With no squire, or when every call fails, the BM25 order is returned.
    """
    if not 0.0 <= blend <= 1.0:
        raise ValueError("blend must be within [0, 1]")
    if not elements or keep <= 0:
        return []
    bm25 = _bm25_order(goal, done, elements)
    by_bm25 = sorted(range(len(elements)), key=lambda i: -bm25[i])
    if squire is None:
        return [Ranked(elements[i], None, bm25[i]) for i in by_bm25[:keep]]
    pool = by_bm25[:shortlist] if shortlist else list(range(len(elements)))
    probs = await _tournament(squire, goal, done, elements, pool, finalists, blend)
    if all(probs.get(i) is None for i in pool):
        return [Ranked(elements[i], None, bm25[i]) for i in by_bm25[:keep]]
    order = sorted(pool, key=lambda i: (-(probs.get(i) or 0.0), -bm25[i]))
    return [Ranked(elements[i], probs.get(i), bm25[i]) for i in order[:keep]]


async def _judge(
    squire: Any, goal: str, done: Sequence[str], elements: Sequence[Element], ids: Sequence[int]
) -> list[float | None]:
    state, qs = questions_mod.questions(
        goal=goal, done=done, lines=[elements[i].line() for i in ids]
    )
    decision = await squire.decide("browse", state, qs)
    squire.record(decision, elements=len(ids))
    return questions_mod.probabilities(decision, len(ids))


async def _tournament(
    squire: Any,
    goal: str,
    done: Sequence[str],
    elements: Sequence[Element],
    pool: Sequence[int],
    finalists: int,
    blend: float,
) -> dict[int, float | None]:
    """Round one: groups of `GROUP_MAX` in page order. Round two: the best `finalists`
    together, when round one had more than one group, mixed with round one by `blend`. A
    finalist the final round did not answer keeps its round-one probability."""
    size = questions_mod.GROUP_MAX
    parts = [list(pool[i : i + size]) for i in range(0, len(pool), size)]
    answers = await asyncio.gather(*(_judge(squire, goal, done, elements, p) for p in parts))
    probs: dict[int, float | None] = {}
    for part, ps in zip(parts, answers, strict=True):
        probs.update(zip(part, ps, strict=True))
    if len(parts) == 1 or blend >= 1.0:
        return probs
    best = sorted(pool, key=lambda i: -(probs.get(i) or 0.0))[: min(finalists, size)]
    final = await _judge(squire, goal, done, elements, best)
    for i, p in zip(best, final, strict=True):
        if p is not None:
            probs[i] = blend * (probs.get(i) or 0.0) + (1.0 - blend) * p
    return probs


# --- a lean snapshot ------------------------------------------------------------------------

_INDENT = re.compile(r"^(\s*)")
_YAML_BLOCK = re.compile(r"```yaml\n(?P<body>.*?)```", re.S)


_REF_LINE = re.compile(r"^\s*- .*\[ref=[\w-]+\]", re.M)
MIN_REF_LINES = 10


def snapshot_block(text: str) -> tuple[int, int] | None:
    """The (start, end) of an accessibility snapshot inside a tool result, or None.

    Three ways one arrives, all measured on 2026-09-30: inside a ```yaml fence (Playwright MCP
    inline, `playwright-cli snapshot` on stdout), or as the whole text (a `.yml` snapshot file
    that `playwright-cli`, or Playwright MCP 0.0.83 by default, writes and the agent then
    `Read`s). A fence with no ref in it is not a snapshot; neither is a text where fewer than a
    third of the lines, or fewer than `MIN_REF_LINES`, carry a ref (`/url` and `text` children
    carry none: Wikipedia's article on Python has refs on 51 % of its 7,274 lines).
    """
    for match in _YAML_BLOCK.finditer(text):
        if _REF_LINE.search(match.group("body")):
            return (match.start("body"), match.end("body"))
    refs = len(_REF_LINE.findall(text))
    lines = sum(1 for line in text.splitlines() if line.strip())
    if refs >= MIN_REF_LINES and refs * 3 >= lines:
        return (0, len(text))
    return None


def prune_snapshot(
    snapshot: str,
    keep_refs: Sequence[str],
    *,
    purpose: str = "",
    text_budget: int = 3000,
) -> tuple[str, int]:
    """The snapshot with only the kept elements, headings and the most relevant text lines.

    Every kept line brings its ancestors (by indentation), so the tree stays a tree and each
    ref sits where the page put it. A kept element brings its `/url` child. Text lines (no ref
    of an interactive role) are ranked by BM25 against `purpose` and kept in page order up to
    `text_budget` characters. Returns the pruned text and the number of lines left out.
    """
    lines = snapshot.splitlines()
    wanted = set(keep_refs)
    depth = [len(_INDENT.match(line).group(1)) for line in lines]
    keep: set[int] = set()
    text_lines: list[int] = []
    for i, line in enumerate(lines):
        match = _SNAPSHOT_LINE.match(line)
        ref = _REF.search(line)
        if ref and ref.group(1) in wanted:
            keep.add(i)
            j = i + 1
            while j < len(lines) and depth[j] > depth[i] and _URL.match(lines[j]):
                keep.add(j)
                j += 1
        elif match and match["role"] == "heading":
            keep.add(i)
        elif match and match["role"] not in INTERACTIVE_ROLES and (match["text"] or match["name"]):
            text_lines.append(i)
    if text_lines and text_budget > 0:
        scores = BM25Index([lines[i] for i in text_lines]).scores(purpose) if purpose else []
        ranked = sorted(range(len(text_lines)), key=lambda k: -scores[k]) if scores else []
        used = 0
        for k in ranked:
            if scores[k] <= 0:
                break
            cost = len(lines[text_lines[k]])
            if used + cost > text_budget:
                continue
            keep.add(text_lines[k])
            used += cost
    for i in sorted(keep):  # bring every ancestor, nearest first
        level = depth[i]
        for j in range(i - 1, -1, -1):
            if depth[j] < level:
                keep.add(j)
                level = depth[j]
                if level == 0:
                    break
    kept = [lines[i] for i in sorted(keep)]
    return "\n".join(kept) + ("\n" if snapshot.endswith("\n") else ""), len(lines) - len(kept)


# --- a lean page ----------------------------------------------------------------------------

AFTER_LIMIT = 60


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def in_page_order(ranked: Sequence[Ranked], page: Sequence[Element]) -> list[tuple[Ranked, str]]:
    """The kept elements in the order the page has them, each with a note when its line is not
    unique on the page: which of the alike it is, and the nearest different element before it.

    Why: on Phase 2c's 60 steps (docs/results/2026-09-30-browse/, diagnose-2c.jsonl) Sonnet
    shown Jev's top 20 in rank order lost 7 steps the whole page won, and in 6 of them the target
    was among the 20. Two were identical lines (two "View more" buttons, two unnamed phone
    fields) that the page's order tells apart and a ranked list does not; three picked one of the
    first three rows. Elements not on `page` keep their rank order at the end.
    """
    where = {e.key: i for i, e in enumerate(page)}
    seen: dict[str, int] = {}
    ordinal: dict[int, int] = {}
    for i, e in enumerate(page):
        seen[e.line()] = seen.get(e.line(), 0) + 1
        ordinal[i] = seen[e.line()]
    on_page = sorted(
        (r for r in ranked if r.element.key in where), key=lambda r: where[r.element.key]
    )
    off_page = [r for r in ranked if r.element.key not in where]
    out: list[tuple[Ranked, str]] = []
    for r in on_page:
        i = where[r.element.key]
        line = r.element.line()
        if seen[line] < 2:
            out.append((r, ""))
            continue
        note = f"{_ordinal(ordinal[i])} of {seen[line]} alike"
        before = next((page[j] for j in range(i - 1, -1, -1) if page[j].line() != line), None)
        if before is not None:
            name = f' "{truncate(before.name, AFTER_LIMIT)}"' if before.name else ""
            note += f", after {before.role}{name}"
        out.append((r, note))
    return out + [(r, "") for r in off_page]


def render(
    ranked: Sequence[Ranked],
    *,
    total: int,
    title: str = "",
    url: str = "",
    archive: str = "",
    page: Sequence[Element] | None = None,
) -> str:
    """The kept elements as the agent will read them, refs intact, plus what was left out.
    Given the `page` they came from, they follow its order and repeated lines say which one
    they are (`in_page_order`); without it, rank order."""
    head = " ".join(part for part in (title, url) if part)
    lines = [f"Page: {head}"] if head else []
    order = "in page order" if page is not None else "best first"
    lines.append(
        f"Elements most likely needed next ({len(ranked)} of {total}, chosen by sanchopanza, "
        f"{order}; refs are the page's own):"
    )
    shown = in_page_order(ranked, page) if page is not None else [(r, "") for r in ranked]
    for r, note in shown:
        e = r.element
        name = f' "{e.name}"' if e.name else ""
        extra = "; ".join(part for part in (e.context, note) if part)
        where = f"  ({extra})" if extra else ""
        lines.append(f"- {e.role}{name} [ref={e.key}]{where}")
    left = total - len(ranked)
    if left > 0:
        tail = f" The full page is archived at {archive}." if archive else ""
        lines.append(
            f"[{left} other elements not shown.{tail} Take a new snapshot to see them all.]"
        )
    return "\n".join(lines)
