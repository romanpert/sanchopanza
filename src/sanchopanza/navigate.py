"""A navigation loop in which the ranking replaces the large model's reading of the page.

The hook in `harness/browse_hook.py` is avoidance: the large model still takes every step and
the hook only trims what it reads. Measured as avoidance should be (17-22 % on pages whose
snapshot arrives inline, nothing past Claude Code's limit), and its ceiling is the session's
own prefix, read back every turn, which no cut touches.

This is the other economy. Each step is a *stateless* question: the goal, the actions already
taken, and the elements `browse.rank` puts first, in the page's order. The page's history is
not in the prompt, so a step's cost does not grow with the step number; and because the
shortlist is short, the model that answers it can be a small one. What the ranking buys is the
right to ask a small model a short question: on 142 new Mind2Web steps the element the step
needed was in its top 20 in 89.4 % of them, and a model choosing from those 20 in page order
chose as well as from the whole page at an eighth of the cost (`docs/results/2026-09-30-browse/`).

Nothing here is measured yet. The loop is the instrument, not the result.

The browser and the model are injected, so the loop can be unit-tested with neither:

    outcome = await navigate("the price of the third book under Travel",
                             browser=browser, actor=actor, squire=squire)

- `Browser`: `snapshot()` returns (snapshot, url, title); `act(action)` performs one action and
  returns what it printed, or an error.
- `Actor`: called with one prompt, returns the model's text. A second `big_actor` is called
  instead when the ranking is unsure (`escalate_below`), which is the cascade's shape: the
  cheap stage reports a calibrated probability, so "unsure" is a number and not a guess.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .browse import Element, Ranked, elements_from_snapshot, prune_snapshot, rank, render

KINDS = ("click", "fill", "select", "back", "answer", "give_up")
TEXT_BUDGET = 3000
KEEP = 20
MAX_STEPS = 20
STUCK_REPEATS = 3  # the same action on the same page this many times: the loop is going nowhere


@dataclass(frozen=True, slots=True)
class Action:
    """One step's decision, as the actor gave it."""

    kind: str
    ref: str = ""
    text: str = ""
    answer: str = ""
    quote: str = ""
    raw: str = ""

    @property
    def final(self) -> bool:
        return self.kind in ("answer", "give_up")

    def line(self) -> str:
        if self.kind == "fill":
            return f'fill {self.ref} "{self.text}"'
        if self.kind == "select":
            return f'select {self.ref} "{self.text}"'
        if self.kind in ("click", "back"):
            return f"{self.kind} {self.ref}".strip()
        return self.kind


@dataclass(frozen=True, slots=True)
class Step:
    index: int
    url: str
    title: str
    elements: int
    shown: int
    top_p: float | None
    margin: float | None
    escalated: bool
    action: Action
    result: str
    note: str = ""


@dataclass(slots=True)
class Outcome:
    goal: str
    answer: str = ""
    quote: str = ""
    url: str = ""
    stopped: str = ""  # answered | give_up | max_steps | stuck | unparsed | browser
    steps: list[Step] = field(default_factory=list)

    @property
    def answered(self) -> bool:
        return bool(self.answer)


@runtime_checkable
class Browser(Protocol):
    async def snapshot(self) -> tuple[str, str, str]: ...

    async def act(self, action: Action) -> str: ...


Actor = Callable[[str], Awaitable[str]]


# --- the step's question ---------------------------------------------------------------------

REPLY_RULES = """Reply with one line of JSON and nothing else, one of:
{"act": "click", "ref": "e12"}                 click that element
{"act": "fill", "ref": "e12", "text": "..."}   type into that field
{"act": "select", "ref": "e12", "text": "..."} choose that option in that dropdown
{"act": "back"}                                go back to the previous page
{"act": "answer", "answer": "...", "quote": "..."}   the page answers the goal; quote text \
copied from the page that shows it
{"act": "give_up", "answer": "why"}            the goal cannot be reached from here
Refs are the page's own; use one shown above. Prefer answering as soon as the page shows the \
answer."""


def prompt_for(
    goal: str,
    *,
    done: Sequence[str],
    url: str,
    title: str,
    lean: str,
    elements_shown: str,
    step: int,
    max_steps: int,
) -> str:
    """One step's whole prompt. The pages already visited are not in it: only what was done."""
    history = (
        "\n".join(f"  {i + 1}. {line}" for i, line in enumerate(done)) if done else "  (none yet)"
    )
    return "\n".join(
        [
            f"Goal: {goal}",
            "",
            f"Actions taken so far (step {step} of at most {max_steps}):",
            history,
            "",
            f"Page: {title} {url}".strip(),
            lean,
            "",
            elements_shown,
            "",
            REPLY_RULES,
        ]
    )


_OBJECT = re.compile(r"\{.*\}", re.S)
_REF_WORD = re.compile(r"\b(e\d+)\b")


def parse_action(text: str) -> Action:
    """The actor's reply as an action. An unparsable reply is `kind=""`, which stops the loop:
    a loop that guesses what the model meant measures the guess as well as the model."""
    found = _OBJECT.search(text or "")
    raw = (text or "").strip()[:400]
    if not found:
        return Action(kind="", raw=raw)
    try:
        data = json.loads(found.group(0))
    except ValueError:
        return Action(kind="", raw=raw)
    if not isinstance(data, dict):
        return Action(kind="", raw=raw)
    kind = str(data.get("act") or data.get("action") or "").strip().lower()
    if kind not in KINDS:
        return Action(kind="", raw=raw)
    ref = str(data.get("ref") or "").strip()
    if kind in ("click", "fill", "select"):
        word = _REF_WORD.search(ref)
        if word is None:
            return Action(kind="", raw=raw)
        ref = word.group(1)
    return Action(
        kind=kind,
        ref=ref,
        text=str(data.get("text") or ""),
        answer=str(data.get("answer") or ""),
        quote=str(data.get("quote") or ""),
        raw=raw,
    )


def _margin(ranked: Sequence[Ranked]) -> tuple[float | None, float | None]:
    """The first element's probability and its distance from the second's. None with no decider."""
    ps = [r.p for r in ranked if r.p is not None]
    if not ps:
        return None, None
    return ps[0], (ps[0] - ps[1] if len(ps) > 1 else ps[0])


def _lean(snapshot: str, kept: Sequence[Element], goal: str, text_budget: int) -> str:
    if text_budget <= 0:
        return ""
    body, _ = prune_snapshot(snapshot, [e.key for e in kept], purpose=goal, text_budget=text_budget)
    return "\n".join(["What the page says (trimmed):", "```yaml", body.rstrip("\n"), "```"])


# --- the loop --------------------------------------------------------------------------------


async def navigate(
    goal: str,
    *,
    browser: Browser,
    actor: Actor,
    squire: Any = None,
    big_actor: Actor | None = None,
    escalate_below: float | None = None,
    keep: int = KEEP,
    max_steps: int = MAX_STEPS,
    text_budget: int = TEXT_BUDGET,
    shortlist: int | None = None,
    on_step: Callable[[Step], None] | None = None,
) -> Outcome:
    """Act towards `goal` until the page answers it, the steps run out or the loop is stuck.

    `escalate_below` sends the step to `big_actor` when the ranking's best element scores below
    it (so the shortlist is probably missing the right element), and `big_actor` is also the
    one asked for the final answer when it is given. With no `squire` the ranking is BM25,
    which is the control arm.
    """
    out = Outcome(goal=goal)
    done: list[str] = []
    seen: dict[tuple[str, str], int] = {}
    for index in range(1, max_steps + 1):
        try:
            snapshot, url, title = await browser.snapshot()
        except Exception as error:  # a browser that died is not a measurement of the loop
            out.stopped = "browser"
            out.quote = f"{error.__class__.__name__}: {error}"
            return out
        page = elements_from_snapshot(snapshot)
        ranked = await rank(goal, page, squire=squire, done=done, keep=keep, shortlist=shortlist)
        top_p, margin = _margin(ranked)
        unsure = escalate_below is not None and (top_p is None or top_p < escalate_below)
        ask = big_actor if (unsure and big_actor is not None) else actor
        body = render(ranked, total=len(page), title=title, url=url, page=page)
        text = await ask(
            prompt_for(
                goal,
                done=done,
                url=url,
                title=title,
                lean=_lean(snapshot, [r.element for r in ranked], goal, text_budget),
                elements_shown=body,
                step=index,
                max_steps=max_steps,
            )
        )
        action = parse_action(text)
        note = ""
        if action.kind == "":
            out.stopped = "unparsed"
            out.quote = action.raw
            out.steps.append(
                Step(index, url, title, len(page), len(ranked), top_p, margin, unsure and
                     big_actor is not None, action, "", "reply not understood")
            )  # fmt: skip
            return out
        if action.final:
            out.answer, out.quote, out.url = action.answer, action.quote, url
            out.stopped = "answered" if action.kind == "answer" else "give_up"
            out.steps.append(
                Step(index, url, title, len(page), len(ranked), top_p, margin, unsure and
                     big_actor is not None, action, "", note)
            )  # fmt: skip
            return out
        here = (url, action.line())
        seen[here] = seen.get(here, 0) + 1
        if seen[here] > 1:
            note = f"the {seen[here]}th time this action is taken on this page"
        result = await browser.act(action)
        step = Step(
            index, url, title, len(page), len(ranked), top_p, margin,
            unsure and big_actor is not None, action, result[:400], note,
        )  # fmt: skip
        out.steps.append(step)
        if on_step is not None:
            on_step(step)
        if seen[here] >= STUCK_REPEATS:
            out.stopped = "stuck"
            return out
        done.append(action.line() + (f" -> {result[:120]}" if result else ""))
    out.stopped = "max_steps"
    return out
