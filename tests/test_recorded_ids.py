"""Recording keys from question ids: opt in, and nothing recorded before moves.

`key_of` signs the question text, so a consumer that translates or rewords a question loses
every recording made with it. `id_key_of` signs the versioned id of each question, its kind
and its option names, and the state: the language of the text is not in it. It is opt in
(`keys="id"`), and the text key every fixture in this repository uses is written and read
exactly as before.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from sanchopanza import catalog
from sanchopanza.contract import Answer, Choice, Decision, Score, Truth
from sanchopanza.points import entities, graph, guard, routing, triage
from sanchopanza.providers import FallbackDecider, create
from sanchopanza.providers.jev_models import keyed_by_model
from sanchopanza.providers.recorded import (
    RecordedDecider,
    RecordingDecider,
    id_key_of,
    key_of,
)

ROOT = Path(__file__).resolve().parents[1]
STATE, QS = {"task": "t"}, {"q": Truth("Is it?")}
LEGACY_KEY = "2e2d6af86d168381"  # key_of("routing", STATE, QS) before models were keyed

SPANISH_ROUTING = {
    "complexity": Score(
        "¿Cuánto exige `task` a un asistente de investigación con búsqueda web?",
        ("Consulta o extracción", "Investigación acotada", "Análisis abierto o delicado"),
    ),
    "needs_browser": Truth("¿Hace falta manejar un sitio web interactivo para hacer `task`?"),
    "person_risk": Truth("¿Afirma `task` algo sobre una persona física identificable?"),
}


class Answering:
    """A live decider stand-in: answers every question with the same truth."""

    name = "jev"

    def __init__(self, model: str = "jev-1.13.0", truth: float = 0.9) -> None:
        self.model, self.truth, self.calls = model, truth, 0

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        self.calls += 1
        answers = {k: Answer("truth", 0.8, truth=self.truth) for k in questions}
        return Decision(point, answers, self.name, self.model, 300, 1e-5)


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


# --- the text key does not move ---------------------------------------------------------


def test_the_text_key_is_unchanged_and_ignores_the_ids() -> None:
    assert key_of("routing", STATE, QS) == LEGACY_KEY
    assert key_of("routing", STATE, catalog.with_ids(QS, {"q": "routing.person_risk@1"})) == (
        LEGACY_KEY
    )
    state, tagged = routing.questions("List the rulings since 2020")
    assert key_of("routing", state, tagged) == key_of("routing", state, dict(tagged))


def test_a_default_recording_line_has_the_shape_it_always_had(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    run(RecordingDecider(Answering(), path).decide("routing", STATE, QS))
    line = json.loads(path.read_text(encoding="utf-8"))
    assert line["key"] == LEGACY_KEY
    assert "id_key" not in line


def _fixture_lines() -> list[dict[str, Any]]:
    lines = []
    for path in sorted((ROOT / "fixtures").rglob("*.jsonl")):
        for raw in path.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                row = json.loads(raw)
                if isinstance(row, dict) and row.get("key"):
                    lines.append(row)
    return lines


def test_every_fixture_line_is_still_indexed_under_its_own_key_in_both_modes() -> None:
    lines = _fixture_lines()
    if not lines:
        pytest.skip("no fixtures in this checkout")
    by_model: dict[str | None, list[dict[str, Any]]] = {}
    for row in lines:
        model = str(row.get("model") or "")
        by_model.setdefault(model if keyed_by_model(model) else None, []).append(row)
    for model, rows in by_model.items():
        text = RecordedDecider(rows, model=model)
        ids = RecordedDecider(rows, model=model, keys="id")
        assert len(text) == len(ids)
        assert text.indexed_keys() == ids.indexed_keys()
        assert {str(r["key"]) for r in rows} == text.indexed_keys()


# --- the id key ----------------------------------------------------------------------------


def test_the_id_key_does_not_depend_on_the_language_of_the_text() -> None:
    state, english = routing.questions("Lista las sentencias desde 2020")
    assert id_key_of("routing", state, english) == id_key_of("routing", state, SPANISH_ROUTING)
    assert key_of("routing", state, english) != key_of("routing", state, SPANISH_ROUTING)


def test_the_id_key_does_not_depend_on_the_point_name_once_every_question_has_an_id() -> None:
    state, english = routing.questions("t")
    assert id_key_of("routing", state, english) == id_key_of("my_trace_name", state, english)


def test_the_id_key_moves_with_the_state_the_version_the_options_and_the_set() -> None:
    state, english = routing.questions("t")
    base = id_key_of("routing", state, english)
    assert id_key_of("routing", {**state, "task": "u"}, english) != base
    bumped = catalog.with_ids(english, {**english.ids, "person_risk": "routing.person_risk@2"})
    assert id_key_of("routing", state, bumped) != base
    fewer = catalog.narrowed(english, ["complexity", "person_risk"])
    assert id_key_of("routing", state, fewer) != base
    _, classify = entities.classification_questions(field="f", text="x", options={"a": 1, "b": 2})
    _, other = entities.classification_questions(field="f", text="x", options={"a": 1, "c": 2})
    _, swapped = entities.classification_questions(field="f", text="x", options={"b": 2, "a": 1})
    keys = {id_key_of("classify", {}, q) for q in (classify, other, swapped)}
    assert len(keys) == 3  # option names and their order are in the key


def test_option_descriptions_are_signed_only_where_they_are_input() -> None:
    """A classify vocabulary is the caller's: its descriptions decide the answer. The source
    kinds of triage are the package's wording, and a translation of them keeps the key."""
    _, mine = entities.classification_questions(
        field="f", text="x", options={"a": "civil cases", "b": "criminal cases"}
    )
    _, swapped = entities.classification_questions(
        field="f", text="x", options={"a": "criminal cases", "b": "civil cases"}
    )
    assert id_key_of("classify", {}, mine) != id_key_of("classify", {}, swapped)
    state, english = triage.questions(purpose="p", text="x")
    kinds = english["source_kind"].options
    spanish = {**english, "source_kind": Choice("¿Qué tipo de fuente es?", dict.fromkeys(kinds))}
    assert id_key_of("triage", state, english) == id_key_of("triage", state, spanish)


@pytest.mark.parametrize(
    ("point", "build", "other"),
    [
        (
            "guard",
            lambda: guard.coding_questions("ls", environment=guard.coding_environment(".")),
            lambda: guard.questions("ls", environment=guard.coding_environment(".")),
        ),
        (
            "facts",
            lambda: entities.fact_questions(fact_a="a", fact_b="b", unrelated_examples=True),
            lambda: entities.fact_questions(fact_a="a", fact_b="b"),
        ),
        (
            "edge",
            lambda: graph.edge_questions(
                subject="s", relation="r", obj="o", text="t", direction_by_roles=False
            ),
            lambda: graph.edge_questions(subject="s", relation="r", obj="o", text="t"),
        ),
    ],
)
def test_an_untagged_variant_never_takes_another_variants_id_key(
    point: str, build: Any, other: Any
) -> None:
    state, tagged = build()
    other_state, other_tagged = other()
    assert state == other_state
    taken = {id_key_of(point, state, tagged), id_key_of(point, state, other_tagged)}
    for untagged in ({**tagged}, {k: q for k, q in tagged.items()}, {**other_tagged}):
        assert id_key_of(point, state, untagged) not in taken


def test_variants_with_the_same_state_do_not_share_an_id_key() -> None:
    env = guard.coding_environment(".")
    state, sandbox = guard.questions("ls", environment=env)
    coding_state, coding = guard.coding_questions("ls", environment=env)
    assert state == coding_state
    assert id_key_of("guard", state, sandbox) != id_key_of("guard", state, coding)
    edge_state, by_roles = graph.edge_questions(subject="s", relation="r", obj="o", text="t")
    _, possession = graph.edge_questions(
        subject="s", relation="r", obj="o", text="t", direction_by_roles=False
    )
    assert id_key_of("edge", edge_state, by_roles) != id_key_of("edge", edge_state, possession)


def test_a_question_without_an_id_signs_its_text_and_the_point() -> None:
    mine = {"q": Truth("Is it?")}
    translated = {"q": Truth("¿Lo es?")}
    assert id_key_of("mine", STATE, mine) != id_key_of("mine", STATE, translated)
    assert id_key_of("mine", STATE, mine) != id_key_of("other", STATE, mine)


def test_the_model_enters_the_id_key_from_jev_1_14_on_as_it_does_the_text_key() -> None:
    state, english = triage.questions(purpose="p", text="x")
    legacy = id_key_of("triage", state, english)
    assert id_key_of("triage", state, english, model="jev-1.13.0") == legacy
    assert id_key_of("triage", state, english, model="jev-1.14.0") != legacy


# --- recording and replaying by id ----------------------------------------------------------


def test_an_id_recording_replays_a_translated_question(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    state, english = routing.questions("Lista las sentencias desde 2020")
    live = Answering(truth=0.25)
    run(RecordingDecider(live, path, keys="id").decide("routing", state, english))
    line = json.loads(path.read_text(encoding="utf-8"))
    assert line["key"] == key_of("routing", state, english)  # the text key is still written
    assert line["id_key"] == id_key_of("routing", state, english)

    by_id = RecordedDecider.from_file(path, keys="id")
    replayed = run(by_id.decide("routing", state, SPANISH_ROUTING))
    assert replayed.answer("person_risk").truth == 0.25
    by_text = RecordedDecider.from_file(path)
    assert run(by_text.decide("routing", state, english)).answer("person_risk").truth == 0.25
    assert run(by_text.decide("routing", state, SPANISH_ROUTING)).answer("person_risk").empty


def test_an_id_replay_still_answers_from_text_keyed_lines(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    run(RecordingDecider(Answering(truth=0.7), path).decide("routing", STATE, QS))
    replayed = run(RecordedDecider.from_file(path, keys="id").decide("routing", STATE, QS))
    assert replayed.answer("q").truth == 0.7


def test_an_id_replay_answers_by_text_first_and_by_id_only_when_the_text_misses(
    tmp_path: Path,
) -> None:
    """Two wordings under the same ids: the wording asked replays its own line, and the id
    line (the last one written) answers only a wording that was never recorded."""
    path = tmp_path / "r.jsonl"
    state, english = routing.questions("t")
    reworded = catalog.with_ids(
        {**english, "person_risk": Truth("Is `task` about a named private person?")},
        english.ids,
    )
    run(RecordingDecider(Answering(truth=0.9), path, keys="id").decide("routing", state, english))
    run(RecordingDecider(Answering(truth=0.5), path, keys="id").decide("routing", state, reworded))
    replay = RecordedDecider.from_file(path, keys="id")
    assert run(replay.decide("routing", state, english)).answer("person_risk").truth == 0.9
    assert run(replay.decide("routing", state, reworded)).answer("person_risk").truth == 0.5
    unseen = run(replay.decide("routing", state, SPANISH_ROUTING))
    assert unseen.answer("person_risk").truth == 0.5


def test_id_keys_follow_the_model_split(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    state, english = triage.questions(purpose="p", text="x")
    run(RecordingDecider(Answering("jev-1.14.0", 0.3), path, keys="id").decide(
        "triage", state, english))  # fmt: skip
    assert run(RecordedDecider.from_file(path, keys="id").decide(
        "triage", state, english)).answer("relevant").empty  # fmt: skip
    for_14 = RecordedDecider.from_file(path, model="jev-1.14.0", keys="id")
    assert run(for_14.decide("triage", state, english)).answer("relevant").truth == 0.3


def test_create_passes_the_key_scheme(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    state, english = routing.questions("t")
    run(RecordingDecider(Answering(truth=0.4), path, keys="id").decide("routing", state, english))
    made = create("recorded", path=path, keys="id")
    assert run(made.decide("routing", state, SPANISH_ROUTING)).answer("needs_browser").truth == 0.4


def test_an_unknown_key_scheme_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        RecordedDecider([], keys="words")
    with pytest.raises(ValueError):
        RecordingDecider(Answering(), tmp_path / "r.jsonl", keys="words")


def test_a_fallback_chain_keeps_the_ids_of_what_it_passes_on(tmp_path: Path) -> None:
    """The chain asks the next decider only for what is left: the variant's id must survive."""
    path = tmp_path / "r.jsonl"
    env = guard.coding_environment(".")
    state, coding = guard.coding_questions("ls", environment=env)
    recorder = RecordingDecider(Answering(truth=0.1), path, keys="id")
    chain = FallbackDecider([RecordedDecider([], keys="id"), recorder])
    run(chain.decide("guard", state, coding))
    line = json.loads(path.read_text(encoding="utf-8"))
    assert line["id_key"] == id_key_of("guard", state, coding)
    _, sandbox = guard.questions("ls", environment=env)
    assert line["id_key"] != id_key_of("guard", state, sandbox)


def test_a_box_question_has_a_shape_too() -> None:
    from sanchopanza.contract import Box

    tagged = catalog.with_ids({"where": Box("the logo")}, {"where": "mine.where@1"})
    reworded = catalog.with_ids({"where": Box("el logotipo")}, {"where": "mine.where@1"})
    assert id_key_of("mine", STATE, tagged) == id_key_of("mine", STATE, reworded)
