"""The long-document point (`points.longdoc`), with no network: the request is lot L6's and
lot lb162's to the byte, the 0.6 cut, the escalations, the middle cut, the shorter retries,
and, where the LongBench v2 cache is on this machine, a free replay of lb162's recorded answers.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from sanchopanza.contract import Answer, DeciderOutOfFunds, DeciderUnavailable, Decision
from sanchopanza.points import longdoc
from sanchopanza.providers.capped import SpendCapReached
from sanchopanza.providers.recorded import RecordedDecider, key_of

from .helpers import bench_module

ROOT = Path(__file__).resolve().parents[1]
LB162 = ROOT / "docs" / "results" / "2026-10-15-lb162"
JEV114 = ROOT / "benchmarks" / "jev114"
MODEL = "jev-1.14.0"

l6 = bench_module(JEV114, "l6")
lb162_stats = bench_module(JEV114, "lb162_stats")

# ---- fakes ---------------------------------------------------------------------------------


def _choice(letter: str, probs: dict[str, float]) -> Answer:
    return Answer(kind="choice", confidence=0.5, choice=letter, probabilities=probs)


class Fake:
    """A decider with a long-context mode: answers from a script, records what it was asked."""

    name = "jev"

    def __init__(self, script, *, model: str | None = MODEL, served: str | None = None) -> None:
        self.script = list(script)
        self.model = model
        self.served = served or model or "-"
        self.calls: list[tuple[str, dict, dict]] = []
        self.timeouts: list[float | None] = []

    def with_long_context(self, *, timeout_s: float | None = None) -> Fake:
        self.timeouts.append(timeout_s)
        return self

    async def decide(self, point, state, questions):
        self.calls.append((point, state, questions))
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        letter, probs = NO_LETTER if step is None else step
        answer = _choice(letter, probs)
        return Decision(point, {"answer": answer}, self.name, self.served, 1000, 0.002)


class NoLong:
    """A decider with no long-context mode at all (a CLM server, a local model)."""

    name = "plain"
    model = MODEL

    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, point, state, questions):
        self.calls += 1
        raise AssertionError("must not be called")


class Refuses(NoLong):
    def with_long_context(self, **_: object):
        raise AttributeError("clm at http://localhost:8000 has no long-context mode")


class Replay:
    """lb162's recordings behind the long-context mode a recording does not have."""

    def __init__(self, inner: RecordedDecider) -> None:
        self.inner, self.name, self.model = inner, inner.name, inner.model

    def with_long_context(self, **_: object) -> Replay:
        return self

    async def decide(self, point, state, questions):
        return await self.inner.decide(point, state, questions)


OPTS = ("first", "second", "third", "fourth")
NO_LETTER = ("E", {"A": 0.5, "B": 0.5})  # answered, but the pick has no probability
SURE = ("B", {"A": 0.1, "B": 0.6, "C": 0.2, "D": 0.1})
UNSURE = ("C", {"A": 0.1, "B": 0.2, "C": 0.59, "D": 0.11})


# ---- the request is the measured one ------------------------------------------------------


def test_constants_are_the_measured_ones():
    assert longdoc.POINT == l6.B3_POINT == "longbench_choice"
    assert longdoc.INSTRUCTIONS == l6.B3_INSTRUCTIONS
    assert longdoc.WINDOW_CHARS == l6.CUT_CHARS["L"] == 900_000
    assert longdoc.SHRINK == l6.SHRINK
    assert longdoc.CUT == lb162_stats.TAU == 0.6
    assert longdoc.MEASURED_MODEL == MODEL
    assert l6.TIMEOUT_S["L"] == longdoc.LONG_TIMEOUT_S


def test_questions_are_l6s_byte_for_byte_and_so_is_the_key():
    task = SimpleNamespace(question="  Who wins?\n", choices=OPTS)
    document = "x" * 1_000_000 + "y" * 500_000
    state, qs = longdoc.questions(task.question, task.choices, document)
    measured_qs = l6.b3_question(task)
    measured_state = {"question": task.question.strip(),
                      "document": l6.middle_cut(document, l6.CUT_CHARS["L"])}  # fmt: skip
    assert dict(qs) == measured_qs
    assert json.dumps(state) == json.dumps(measured_state)
    assert key_of(longdoc.POINT, state, qs, MODEL) == key_of(
        l6.B3_POINT, measured_state, measured_qs, MODEL
    )


@pytest.mark.parametrize("size", [0, 10, 899_999, 900_000, 900_001, 2_652_493])
def test_middle_cut_is_l6s(size):
    text = "".join(chr(97 + i % 26) for i in range(size))
    assert longdoc.middle_cut(text, 900_000) == l6.middle_cut(text, 900_000)


def test_middle_cut_beyond_the_window_keeps_head_and_tail():
    document = "h" * 600_000 + "m" * 600_000 + "t" * 600_000
    state, _ = longdoc.questions("q", OPTS, document)
    shown = state["document"]
    assert len(shown) == 900_000 + len("\n[...]\n")
    assert shown.startswith("h" * 450_000) and shown.endswith("t" * 450_000)
    assert "m" not in shown
    whole, _ = longdoc.questions("q", OPTS, "short document")
    assert whole["document"] == "short document"


def test_two_to_n_options_get_letters_in_order():
    _, qs = longdoc.questions("q", ("yes", "no"), "doc")
    assert dict(qs["answer"].options) == {"A": "yes", "B": "no"}
    _, qs = longdoc.questions("q", [f"o{i}" for i in range(6)], "doc")
    assert list(qs["answer"].options) == ["A", "B", "C", "D", "E", "F"]


@pytest.mark.parametrize(
    "options",
    [(), ("only",), tuple(str(i) for i in range(27)), "ABCD", ("a", ""), ("a", "  "), ("a", 3)],
)
def test_bad_options_are_refused(options):
    with pytest.raises(ValueError):
        longdoc.questions("q", options, "doc")


@pytest.mark.parametrize("window", [0, 1, -5, 1.5, True, "900000"])
def test_a_window_that_is_not_an_int_of_at_least_two_is_refused(window):
    with pytest.raises(ValueError):
        longdoc.questions("q", OPTS, "doc", window_chars=window)


async def test_answer_refuses_bad_input_before_any_call():
    fake = Fake([SURE])
    with pytest.raises(ValueError):
        await longdoc.answer(fake, "doc", "q", "ABCD")
    with pytest.raises(ValueError):
        await longdoc.answer(fake, "doc", "q", OPTS, window_chars=1)
    assert fake.calls == []


def test_empty_question_or_document_is_refused():
    with pytest.raises(ValueError):
        longdoc.questions("  ", OPTS, "doc")
    with pytest.raises(ValueError):
        longdoc.questions("q", OPTS, "")


# ---- the cut ------------------------------------------------------------------------------


def _decision(letter, probs, model=MODEL):
    return Decision("longbench_choice", {"answer": _choice(letter, probs)}, "jev", model)


def test_at_the_cut_jev_answers():
    result = longdoc.decide(_decision(*SURE))
    assert not result.escalate
    assert (result.letter, result.top, result.p) == ("B", "B", 0.6)
    assert result.index == 1


def test_below_the_cut_it_escalates_with_jevs_reading_kept():
    result = longdoc.decide(_decision(*UNSURE))
    assert result.escalate and result.letter is None and result.index is None
    assert (result.top, result.p) == ("C", 0.59)
    assert "0.59" in result.reason and "0.6" in result.reason


def test_the_probability_is_read_as_measured_rounded_to_four_places():
    # l6.top_of rounds to 4 places before lb162 compared with 0.6.
    result = longdoc.decide(_decision("A", {"A": 0.59996, "B": 0.40004}))
    assert not result.escalate and result.p == 0.6


def test_a_caller_can_raise_the_cut():
    assert longdoc.decide(_decision(*SURE), cut=0.8).escalate
    with pytest.raises(ValueError):
        longdoc.decide(_decision(*SURE), cut=0.0)
    with pytest.raises(ValueError):
        longdoc.decide(_decision(*SURE), cut=1.5)


def test_no_usable_answer_escalates():
    empty = Decision("longbench_choice", {}, "jev", MODEL)
    assert longdoc.decide(empty).escalate
    off_scale = _decision("E", {"A": 0.5, "B": 0.5})  # the pick has no probability
    result = longdoc.decide(off_scale)
    assert result.escalate and result.p is None


def test_probabilities_cannot_be_changed():
    result = longdoc.decide(_decision(*SURE))
    assert isinstance(result.probabilities, MappingProxyType)
    with pytest.raises(TypeError):
        result.probabilities["A"] = 1.0  # type: ignore[index]
    assert isinstance(longdoc.LongdocAnswer(True, "x").probabilities, MappingProxyType)


def test_another_model_escalates_even_when_sure():
    result = longdoc.decide(_decision(*SURE, model="jev-1.13.0"))
    assert result.escalate and "jev-1.13.0" in result.reason and MODEL in result.reason
    assert not longdoc.decide(_decision(*SURE, model="jev-1.13.0"), model=None).escalate


# ---- asking -------------------------------------------------------------------------------


async def test_answer_asks_once_with_the_long_window_and_answers():
    fake = Fake([SURE])
    result = await longdoc.answer(fake, "the document", "Who?", OPTS)
    assert not result.escalate and result.letter == "B"
    assert fake.timeouts == [longdoc.LONG_TIMEOUT_S]
    point, state, qs = fake.calls[0]
    assert point == "longbench_choice"
    assert state == {"question": "Who?", "document": "the document"}
    assert (result.tries, result.cost_usd, result.shown_chars) == (1, 0.002, 12)


async def test_answer_escalates_below_the_cut():
    result = await longdoc.answer(Fake([UNSURE]), "doc", "q", OPTS)
    assert result.escalate and result.top == "C" and result.cost_usd == 0.002


async def test_no_long_context_mode_escalates_without_a_call():
    plain = NoLong()
    result = await longdoc.answer(plain, "doc", "q", OPTS)
    assert result.escalate and "long-context" in result.reason and plain.calls == 0
    refusing = Refuses()
    result = await longdoc.answer(refusing, "doc", "q", OPTS)
    assert result.escalate and "long-context" in result.reason and refusing.calls == 0


async def test_a_decider_on_another_model_escalates_before_spending():
    fake = Fake([SURE], model="jev-1.13.0")
    result = await longdoc.answer(fake, "doc", "q", OPTS)
    assert result.escalate and "jev-1.13.0" in result.reason and fake.calls == []
    assert result.cost_usd == 0.0


async def test_served_by_another_model_escalates_after_the_call():
    fake = Fake([SURE], model=None, served="jev-1.15.0")  # a wrapper that does not say
    result = await longdoc.answer(fake, "doc", "q", OPTS)
    assert result.escalate and "jev-1.15.0" in result.reason and result.cost_usd == 0.002


async def test_another_served_model_is_not_asked_again_shorter():
    fake = Fake([None, SURE], model=None, served="jev-1.15.0")  # no letter, wrong model
    result = await longdoc.answer(fake, "doc", "q", OPTS)
    assert result.escalate and "jev-1.15.0" in result.reason
    assert len(fake.calls) == 1 and result.tries == 1


async def test_a_question_with_other_than_four_options_escalates_unless_asked():
    fake = Fake([SURE])
    result = await longdoc.answer(fake, "doc", "q", ("yes", "no"))
    assert result.escalate and "4 options" in result.reason and fake.calls == []
    result = await longdoc.answer(fake, "doc", "q", ("yes", "no"), measured_only=False)
    assert not result.escalate and result.letter == "B" and len(fake.calls) == 1


async def test_model_none_accepts_any_model():
    fake = Fake([SURE], model="jev-1.13.0")
    assert not (await longdoc.answer(fake, "doc", "q", OPTS, model=None)).escalate


async def test_refused_calls_are_asked_again_shorter_as_measured():
    document = "a" * 2_000_000
    fake = Fake([DeciderUnavailable("jev did not answer: HTTP 400 (max_tokens_exceeded)"),
                 DeciderUnavailable("jev unreachable: ReadTimeout"), SURE])  # fmt: skip
    result = await longdoc.answer(fake, document, "q", OPTS)
    assert not result.escalate and result.tries == 3
    shown = [len(state["document"]) - len("\n[...]\n") for _, state, _ in fake.calls]
    assert shown == [900_000, 720_000, 576_000]
    assert result.shown_chars == 576_000


async def test_refused_at_every_length_escalates():
    refusal = DeciderUnavailable("jev did not answer: HTTP 400 (max_tokens_exceeded)")
    fake = Fake([refusal, refusal, refusal])
    result = await longdoc.answer(fake, "doc", "q", OPTS)
    assert result.escalate and result.tries == 3 and "HTTP 400" in result.reason


@pytest.mark.parametrize(
    "error",
    [
        DeciderOutOfFunds("jev did not answer: HTTP 402 (out of funds)"),
        DeciderUnavailable("jev did not answer: HTTP 503"),
        DeciderUnavailable("jev did not answer: HTTP 429"),
        SpendCapReached("jev: 0.0012 USD would pass the batch cap (not called)"),
    ],
)
async def test_out_of_funds_a_cap_a_limit_or_an_outage_escalates_at_once(error):
    fake = Fake([error, SURE])
    result = await longdoc.answer(fake, "doc", "q", OPTS)
    assert result.escalate and len(fake.calls) == 1
    assert result.reason == str(error)  # said once, not under a second prefix


async def test_paid_tries_add_up_when_a_later_one_fails():
    fake = Fake([None, DeciderUnavailable("jev did not answer: HTTP 503")])
    result = await longdoc.answer(fake, "doc", "q", OPTS)
    assert result.escalate and result.tries == 2 and result.cost_usd == 0.002
    assert result.reason == "jev did not answer: HTTP 503"


async def test_an_exception_that_is_not_the_decider_unavailable_propagates():
    with pytest.raises(RuntimeError):
        await longdoc.answer(Fake([RuntimeError("a bug")]), "doc", "q", OPTS)


async def test_measured_decider_is_jev_114_with_the_header(monkeypatch):
    pytest.importorskip("httpx")
    monkeypatch.setenv("SANCHOPANZA_JEV_MODEL", "jev-1.13.0")
    decider = longdoc.measured_decider(api_key="test-key")
    assert decider.model == MODEL and decider.long_context and not decider.images


# ---- a free replay of lb162 ---------------------------------------------------------------


def _lb162_tasks():
    data = bench_module(ROOT / "benchmarks" / "h2h", "longdoc_data")
    path = data.CACHE / "lb162" / "tasks.jsonl"
    if not path.is_file():
        pytest.skip("the LongBench v2 cache of lot lb162 is not on this machine")
    tasks = {t.task_id: t for t in data.load(path)}
    if not all(Path(t.doc_path).is_file() for t in tasks.values()):
        pytest.skip("lot lb162's documents are not all on this machine")
    return tasks


async def test_replays_every_lb162_answer_and_its_coverage():
    """The point's requests hit lb162's recorded keys, and its reading is lb162's: the same
    letter, probability, number of tries and cost on all 162 tasks, 60 covered at 0.6."""
    tasks = _lb162_tasks()
    replay = Replay(RecordedDecider.from_file(LB162 / "jev-answers-j14-L.jsonl", model=MODEL))
    rows = [json.loads(x) for x in (LB162 / "jev-scored.jsonl").read_text("utf-8").splitlines()]
    covered = 0
    for row in rows:
        task = tasks[row["id"]]
        document = Path(task.doc_path).read_text(encoding="utf-8")
        result = await longdoc.answer(replay, document, task.question, task.choices)
        cell = row["j14-L"]
        assert (result.top, result.p, result.tries) == (cell["letter"], cell["p"], cell["tries"])
        assert result.shown_chars == cell["shown_chars"]
        assert round(result.cost_usd, 6) == cell["usd"]
        assert result.escalate is not lb162_stats.is_covered(row)
        covered += not result.escalate
    assert (len(rows), covered) == (162, 60)
