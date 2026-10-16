"""A multiple-choice question over one long document: Jev answers when it is sure, the caller's
own model otherwise. Opt-in: nothing in `install`, `policy` or the `Squire` calls it.

    from sanchopanza.budget import SpendLedger
    from sanchopanza.providers import CappedDecider

    jev = longdoc.measured_decider()  # TYPESAFE_API_KEY from the environment
    ledger = SpendLedger("longdoc-ledger.json", cap_usd=1.00)
    decider = CappedDecider(jev, ledger=ledger, batch="longdoc", max_usd=1.00)
    try:
        result = await longdoc.answer(decider, document, question, options)
    finally:
        await jev.aclose()
    letter = result.letter if not result.escalate else await ask_my_own_model(...)

A long call is about 0.005 USD (lb162: 0.874 USD over 162 documents, retries included), and
grows with the document; the cap is the caller's to set, in code.

It is the cascade of `navigate`'s `escalate_below`: the cheap stage reports a calibrated
probability, so "unsure" is a number. One Choice (the options lettered A, B, ...) is asked of
Jev 1.14 over the whole document with the long-context header, the document middle-cut to its
first and last 450,000 characters past `WINDOW_CHARS`. When Jev's top choice has a probability
of at least `CUT` (0.6) the point gives that letter; otherwise it says `escalate`, with Jev's
reading and the reason, and the caller asks its own model.

**What was measured, and nowhere else.** LongBench v2 multiple-choice questions with four
options, graded by the letter, over one long document: Single- and Multi-Document QA, contexts
over 100,000 characters (shorter documents were not measured); jev-1.14.0 with the
long-context header and this 900,000-character middle cut; the expensive model in clean Claude
Code 2.1.287. Lot lb162 (docs/results/2026-10-15-lb162, pre-registered, 162 fresh tasks) and lot
lb162x (docs/results/2026-10-16-lb162x):

- Jev answered 37 % of the tasks (60 of 162) at 0.6.
- Against Sonnet 5.5 alone: +1.2 points [-3.1, +5.6], "no peor" at -10 points, for 33.9 %
  [24.0, 44.0] of Sonnet's cost saved, measured.
- Against Opus 5.5 alone: -3.7 points [-8.0, +0.6], "no peor" at -10 points, for 29.5 %
  [21.7, 37.7] of Opus's cost saved. On the tasks Jev answered, Opus was right more often (37
  against 31 of 60; McNemar 10 against 4, p 0.18, not significant): the point estimate is a
  loss. A higher cut (0.8) looked closer to Opus post hoc (-0.6 points at 27 tasks covered);
  that is not confirmed, and `cut=` is the caller's.
- One draw: one set of 162 tasks, one session per task and model. The -10-point margin was a
  product decision fixed before the data, not a statistical one. Open-ended answers, other
  document kinds and other decision models were not measured.

**The request is the measured one, to the byte.** `POINT`, `INSTRUCTIONS`, the state
(`question` stripped, `document` middle-cut) and the Choice are lot L6's `b3_question` and
lot lb162's phase J (benchmarks/jev114/l6.py, lb162.py), so a recording key of one is the key
of the other: tests/test_longdoc_point.py replays all 162 of lb162's recorded answers through
this point. A call refused (HTTP 400, a read timeout) or answered without a usable letter is
asked again at 0.8 and then 0.64 of the window, as lb162 did; a document shorter than the
shrunk window is sent again unchanged, as it was there.

**Outside the measured setup, escalated unless the caller opts out.** A question with other
than four options escalates unless `measured_only=False`; another model escalates unless
`model=None`. Both opt-outs are for a caller who has measured its own case.

**The model.** The cut is jev-1.14.0's. `JevDecider`'s default is jev-1.13.0 (`DEFAULT_MODEL`,
which this point does not change), so `measured_decider()` builds the measured one: jev-1.14.0,
the long-context header, no images, the measured 180 s timeout. With any other decider the
point checks the model before the call (a `model` attribute) and after it (the model the
provider says answered), and escalates on another one, without asking again shorter.

**Escalation, never a silent default.** Besides the cut, it escalates with a reason when the
decider has no long-context mode (`providers.long_context`: Jev at TypeSafe's address, or a
`CappedDecider` or `CachedDecider` around it; a CLM server, a recording or a general LLM has
none), on another model, out of funds, over a spend cap, on a 429 or another outage, or when
every length was refused.
"""

from __future__ import annotations

import string
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any

from ..contract import Choice, DeciderUnavailable, Decision, Question
from ..providers.long_context import long_context_twin

POINT = "longbench_choice"  # the point name lots L6 and lb162 asked under: recordings key on it
INSTRUCTIONS = (
    "Which option is the correct answer to `question`? The answer is in `document`: read it "
    "to decide."
)
KEY = "answer"
CUT = 0.6  # lb162's registered cut on jev-1.14.0
MEASURED_MODEL = "jev-1.14.0"
MEASURED_OPTIONS = 4  # LongBench v2's four options, A to D
WINDOW_CHARS = 900_000  # L6's long window, head half and tail half
SHRINK = (1.0, 0.8, 0.64)  # a refused call is asked again at these fractions of the window
LONG_TIMEOUT_S = 180.0  # L6's and lb162's timeout for the long window
CUT_MARK = "\n[...]\n"
LETTERS = string.ascii_uppercase
# lb162's task failures (`TASK_FAILURES`), word for word: a call that fails with one of these is
# asked again shorter. Any other failure (out of funds, a spend cap, a 429 or 5xx, another
# network error) escalates at once.
SHORTER_ON = ("HTTP 400", "jev unreachable: ReadTimeout")


def _frozen(probabilities: Mapping[str, float] | None = None) -> Mapping[str, float]:
    return MappingProxyType(dict(probabilities or {}))


@dataclass(frozen=True, slots=True)
class LongdocAnswer:
    """What the point decided. `letter` is the answer to use, None when `escalate`; `top` and
    `p` are Jev's pick and its probability either way, for the record. `cost_usd` is the billed
    cost of the tries that returned; a try that timed out may also have been billed."""

    escalate: bool
    reason: str
    letter: str | None = None
    top: str | None = None
    p: float | None = None
    probabilities: Mapping[str, float] = field(default_factory=_frozen)
    model: str = ""
    cost_usd: float = 0.0
    tries: int = 0
    shown_chars: int = 0

    @property
    def index(self) -> int | None:
        """The position of `letter` among the options; None when escalating."""
        return None if self.letter is None else LETTERS.index(self.letter)


def middle_cut(text: str, limit: int) -> str:
    """The first and last `limit // 2` characters around a mark; the text whole within it."""
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + CUT_MARK + text[-half:]


def _check_options(options: Sequence[str]) -> None:
    if isinstance(options, str | bytes):
        raise ValueError("options are a sequence of option texts, not one string")
    if not 2 <= len(options) <= len(LETTERS):
        raise ValueError(f"between 2 and {len(LETTERS)} options, not {len(options)}")
    if not all(isinstance(o, str) and o.strip() for o in options):
        raise ValueError("every option is a non-empty string")


def _check_window(window_chars: int) -> None:
    if isinstance(window_chars, bool) or not isinstance(window_chars, int) or window_chars < 2:
        raise ValueError(f"window_chars is a whole number of at least 2, not {window_chars!r}")


def questions(
    question: str, options: Sequence[str], document: str, *, window_chars: int = WINDOW_CHARS
) -> tuple[dict[str, Any], dict[str, Question]]:
    """The measured state and Choice: options lettered A, B, ... in the caller's order."""
    if not question.strip():
        raise ValueError("the question is empty")
    if not document:
        raise ValueError("the document is empty")
    _check_options(options)
    _check_window(window_chars)
    state = {"question": question.strip(), "document": middle_cut(document, window_chars)}
    return state, {KEY: Choice(INSTRUCTIONS, dict(zip(LETTERS, options, strict=False)))}


def read(decision: Decision) -> tuple[str | None, float | None, dict[str, float]]:
    """(Jev's pick, its probability, the distribution), rounded to four places as L6's
    `top_of`; Nones when unanswered or when the pick has no probability."""
    answer = decision.answer(KEY) if decision.answers else None
    if answer is None or answer.empty:
        return None, None, {}
    probs = {k: round(float(v), 4) for k, v in answer.probabilities.items()}
    if answer.choice not in probs:
        return None, None, probs
    return answer.choice, probs[answer.choice], probs


def _check_cut(cut: float) -> None:
    if not 0.0 < cut <= 1.0:
        raise ValueError(f"the cut is a probability in (0, 1], not {cut}")


def _served_elsewhere(decision: Decision, required: str | None) -> str:
    """Why an answered decision does not count: another model served it ("" when it counts).
    An empty decision (a recording that misses) names no model and is not judged here."""
    if required is None or not decision.answers or decision.model == required:
        return ""
    return f"answered by {decision.model or 'an unnamed model'}; the cut was measured on {required}"


def decide(
    decision: Decision, *, cut: float = CUT, model: str | None = MEASURED_MODEL
) -> LongdocAnswer:
    """Pure: Jev's letter when its probability is at least `cut` and `model` served it."""
    _check_cut(cut)
    top, p, probs = read(decision)
    common = {"top": top, "p": p, "probabilities": _frozen(probs), "model": decision.model,
              "cost_usd": decision.cost_usd}  # fmt: skip
    if other := _served_elsewhere(decision, model):
        return LongdocAnswer(True, other, **common)
    if top is None or p is None:
        why = decision.error or "no usable answer"
        return LongdocAnswer(True, f"Jev gave no letter with a probability ({why})", **common)
    if p < cut:
        return LongdocAnswer(True, f"Jev's top choice {top} at {p} is under the cut {cut}",
                             **common)  # fmt: skip
    return LongdocAnswer(False, f"Jev's top choice {top} at {p} reaches the cut {cut}",
                         letter=top, **common)  # fmt: skip


def _unmeasured(twin: Any, options: Sequence[str], model: str | None, measured_only: bool) -> str:
    """Why this call is outside the measured setup before it is made ("" when it is not)."""
    if measured_only and len(options) != MEASURED_OPTIONS:
        return (f"{len(options)} options; the cut was measured on {MEASURED_OPTIONS} options "
                "(measured_only=False to ask anyway)")  # fmt: skip
    declared = getattr(twin, "model", None)
    if isinstance(declared, str) and model is not None and declared != model:
        return f"the decider asks {declared}; the cut was measured on {model}"
    return ""


async def answer(
    decider: Any,
    document: str,
    question: str,
    options: Sequence[str],
    *,
    cut: float = CUT,
    model: str | None = MEASURED_MODEL,
    measured_only: bool = True,
    window_chars: int = WINDOW_CHARS,
) -> LongdocAnswer:
    """Ask Jev once over the document (shorter only after a refusal) and apply `decide`.

    Bad input (`questions`: an empty question or document, options that are not 2 to 26
    non-empty strings, a window that is not a whole number of at least 2) raises `ValueError`
    before any call. A `window_chars` other than 900,000 is outside the measured setup.
    A decider that cannot answer (`DeciderUnavailable`, which covers out of funds and a spend
    cap) is an escalation with the reason; any other exception is a bug and propagates."""
    _check_cut(cut)
    questions(question, options, document, window_chars=window_chars)
    twin, why = long_context_twin(decider, LONG_TIMEOUT_S)
    if twin is None:
        return LongdocAnswer(True, why)
    if why := _unmeasured(twin, options, model, measured_only):
        return LongdocAnswer(True, why, model=str(getattr(twin, "model", "") or ""))
    paid, tries, limit = 0.0, 0, window_chars
    result = LongdocAnswer(True, "not asked")
    for factor in SHRINK:
        limit = int(window_chars * factor)
        state, qs = questions(question, options, document, window_chars=limit)
        tries += 1
        try:
            decision = await twin.decide(POINT, state, qs)
        except DeciderUnavailable as error:
            result = LongdocAnswer(True, str(error) or error.__class__.__name__)
            if any(mark in str(error) for mark in SHORTER_ON):
                continue
            break
        paid += decision.cost_usd
        result = decide(decision, cut=cut, model=model)
        if result.top is not None or _served_elsewhere(decision, model):
            break
    else:
        result = replace(result, reason=f"refused or unanswered at every length; last: "
                                        f"{result.reason}")  # fmt: skip
    return replace(result, cost_usd=paid, tries=tries, shown_chars=min(len(document), limit))


def measured_decider(api_key: str | None = None, **kwargs: Any) -> Any:
    """The decider the cut was measured with: Jev jev-1.14.0, the long-context header on, no
    images, the 180 s timeout. `kwargs` go to `JevDecider` (a `client`, a `base_url`). It holds
    a connection: `await decider.aclose()` when done. It caps nothing: wrap it in a
    `CappedDecider` (the module's example) to bound what it spends."""
    from ..providers.jev import JevDecider

    settings = {"model": MEASURED_MODEL, "long_context": True, "images": False,
                "timeout_s": LONG_TIMEOUT_S, **kwargs}  # fmt: skip
    return JevDecider(api_key, **settings)
