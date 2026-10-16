"""`ask_document` (harness/longdoc_tool.py): the longdoc point as an opt-in MCP tool over a local
file. No network: a scripted decider stands in for Jev."""

from __future__ import annotations

from pathlib import Path

import pytest

from sanchopanza.contract import Answer, Decision
from sanchopanza.harness import mcp
from sanchopanza.harness.knowledge_tool import Knowledge
from sanchopanza.harness.longdoc_tool import TOOL, Asker, add_longdoc
from sanchopanza.providers.capped import CappedDecider

MODEL = "jev-1.14.0"
OPTIONS = ["red", "green", "blue", "black"]


class Fake:
    """A decider with a long-context mode that answers one scripted Choice."""

    name = "jev"
    model = MODEL

    def __init__(self, letter: str = "C", p: float = 0.9) -> None:
        self.letter, self.p = letter, p
        self.calls: list[dict] = []

    def with_long_context(self, *, timeout_s: float | None = None) -> Fake:
        return self

    async def decide(self, point, state, questions):
        self.calls.append(state)
        rest = (1 - self.p) / 3
        probs = {k: (self.p if k == self.letter else rest) for k in "ABCD"}
        answer = Answer(kind="choice", confidence=self.p, choice=self.letter, probabilities=probs)
        return Decision(point, {"answer": answer}, "jev", MODEL, 1000, 0.003)


def _kit(root: Path) -> Knowledge:
    return Knowledge(fetcher=object(), searcher=object(), squire=None, roots=[root])


def _doc(root: Path, chars: int = 150_000, name: str = "report.txt") -> Path:
    path = root / name
    path.write_text(("The sky over the harbour was blue that day. " * (chars // 44 + 1))[:chars])
    return path


async def test_a_sure_answer_comes_from_jev_and_the_file_is_sent_whole(tmp_path):
    fake = Fake("C", 0.9)
    asker = Asker(kit=_kit(tmp_path), decider=fake)
    path = _doc(tmp_path)
    reply = await asker.ask(str(path), "What colour was the sky?", OPTIONS)
    assert reply.startswith("Answer: (C) blue.")
    assert "p 0.9" in reply
    assert fake.calls[0]["document"] == path.read_text()


async def test_an_unsure_answer_hands_the_question_back(tmp_path):
    asker = Asker(kit=_kit(tmp_path), decider=Fake("B", 0.4))
    reply = await asker.ask(str(_doc(tmp_path)), "What colour was the sky?", OPTIONS)
    assert reply.startswith("Not answered:")
    assert "under the cut 0.6" in reply
    assert "answer it yourself" in reply


async def test_the_cut_is_the_callers_in_code(tmp_path):
    asker = Asker(kit=_kit(tmp_path), decider=Fake("C", 0.7), cut=0.8)
    reply = await asker.ask(str(_doc(tmp_path)), "What colour was the sky?", OPTIONS)
    assert reply.startswith("Not answered:")


async def test_no_decider_means_no_call_and_says_why(tmp_path):
    asker = Asker(kit=_kit(tmp_path), env={})
    reply = await asker.ask(str(_doc(tmp_path)), "What colour was the sky?", OPTIONS)
    assert reply.startswith("Not answered:")
    assert "TYPESAFE_API_KEY" in reply


async def test_a_decider_that_cannot_be_built_is_a_handback(tmp_path, monkeypatch):
    from sanchopanza.contract import DeciderUnavailable
    from sanchopanza.points import longdoc

    def broken(*_: object, **__: object):
        raise DeciderUnavailable("install sanchopanza[jev] to use the Jev provider")

    monkeypatch.setattr(longdoc, "measured_decider", broken)
    asker = Asker(kit=_kit(tmp_path), env={"TYPESAFE_API_KEY": "k"}, ledger_dir=tmp_path)
    reply = await asker.ask(str(_doc(tmp_path)), "Sky colour?", OPTIONS)
    assert reply.startswith("Not answered: install sanchopanza[jev]")


async def test_a_short_document_is_left_to_the_model_without_a_call(tmp_path):
    fake = Fake()
    asker = Asker(kit=_kit(tmp_path), decider=fake)
    reply = await asker.ask(str(_doc(tmp_path, chars=20_000)), "Sky colour?", OPTIONS)
    assert reply.startswith("Not answered:")
    assert "100,000" in reply
    assert fake.calls == []


async def test_a_file_outside_the_roots_is_refused_without_a_call(tmp_path):
    inside, outside = tmp_path / "in", tmp_path / "out"
    inside.mkdir()
    outside.mkdir()
    fake = Fake()
    asker = Asker(kit=_kit(inside), decider=fake)
    reply = await asker.ask(str(_doc(outside)), "Sky colour?", OPTIONS)
    assert "outside the folders" in reply
    assert fake.calls == []


async def test_bad_options_are_a_reply_not_an_exception(tmp_path):
    fake = Fake()
    asker = Asker(kit=_kit(tmp_path), decider=fake)
    reply = await asker.ask(str(_doc(tmp_path)), "Sky colour?", ["only one"])
    assert reply.startswith("Not answered:")
    assert fake.calls == []


async def test_other_than_four_options_is_outside_the_measured_setup(tmp_path):
    fake = Fake()
    asker = Asker(kit=_kit(tmp_path), decider=fake)
    reply = await asker.ask(str(_doc(tmp_path)), "Sky colour?", OPTIONS[:3])
    assert "measured on 4 options" in reply
    assert fake.calls == []


def test_the_key_builds_the_measured_decider_under_a_daily_ledger(tmp_path):
    asker = Asker(kit=_kit(tmp_path), env={"TYPESAFE_API_KEY": "k"}, ledger_dir=tmp_path,
                  cap_usd=0.25)  # fmt: skip
    decider = asker.decider
    assert isinstance(decider, CappedDecider)
    assert decider._inner.model == MODEL
    assert decider._ledger.cap_usd == 0.25
    assert decider._ledger.path.parent == tmp_path


def test_the_tool_is_registered_and_is_an_opt_in_tool_set(tmp_path):
    registered: dict[str, object] = {}

    class Server:
        def tool(self, name=None, description=None):
            def wrap(fn):
                registered[name or fn.__name__] = description
                return fn

            return wrap

    add_longdoc(Server(), Asker(kit=_kit(tmp_path), decider=Fake()))
    assert TOOL in registered
    assert "longdoc" in mcp.TOOL_SETS


@pytest.mark.parametrize("cut", [0.0, 1.5])
def test_a_cut_outside_zero_to_one_is_refused(tmp_path, cut):
    with pytest.raises(ValueError):
        Asker(kit=_kit(tmp_path), decider=Fake(), cut=cut)
