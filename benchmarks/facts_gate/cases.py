"""A5: a batch of `facts` pairs whose labels come from how they are built, not from a reader.

    python benchmarks/facts_gate/cases.py     # writes cases.jsonl and its sha256, seeded

Invented entities (a kind and an invented place name), each with three numeric attributes
written two ways in Spanish and two in English. Five shapes, each a label by construction:

- `conflict`: the same attribute of the same entity, two different values.
- `agree` (restated): the same attribute and value, the other wording.
- `agree` (detail): the same attribute and value, the other wording plus where it comes from.
- `unrelated` (same entity): two different attributes of one entity. Where the decider
  hesitates between `agree` and `unrelated` (fa-26, fa-34, fa-42 in `benches/graph-c.jsonl`).
- `unrelated` (twin): the same attribute of two entities of the same kind, other places.

The two wordings of an attribute name the same event or the same magnitude, never two (founded
against incorporated, the festival's length against the days its concerts span): a conflict
between them is a conflict by construction. `EVENT_STEMS` holds, for every one of the 24
attributes, the words both wordings must share; a test checks every template against it.

Mix 40 % `unrelated`, 30 % `agree`, 30 % `conflict`, the fifth batch's (12/9/9). Languages
alternate. Nothing here is drawn from a model, and no label is read off a model's answer.
Written after the recorded answers on `graph`, `graph-c` and `graph-e` had been looked at.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import random
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "cases.jsonl"
SEED = 20261016
# Sized for power (prereg.md, "Power"): 600 `unrelated`, 560 of them the same-entity shape where
# the band lives, so the gate's added verdicts number about 56-75; `agree` and `conflict` keep
# the 40/30/30 mix, so the added verdicts' precision is read against the same mix as before.
SHAPES = (
    ("unrelated", "same", 560),
    ("unrelated", "twin", 40),
    ("agree", "restated", 225),
    ("agree", "detail", 225),
    ("conflict", "values", 450),
)
HEADS = ("Val", "Mor", "Tar", "Bel", "Cas", "Ner", "Ost", "Lum", "Ar", "Quin", "Fer", "Sal")
TAILS = ("dera", "mosa", "illa", "ena", "ueda", "aral", "onte", "ima", "orca", "ada")

Attribute = tuple[int, int, int, list[str]]  # low, high, step, [es1, es2, en1, en2]

# fmt: off
KINDS: dict[str, tuple[str, str, dict[str, Attribute]]] = {
    "plant": ("la planta desaladora de {p}", "the {p} desalination plant", {
        "output": (20_000, 90_000, 1_000, [
            "{E} produce {v} metros cubicos de agua al dia.",
            "La produccion de {e} es de {v} metros cubicos al dia.",
            "{E} produces {v} cubic metres of water per day.",
            "The output of {e} is {v} cubic metres per day."]),
        "year": (1985, 2020, 1, [
            "{E} se inauguro en {v}.",
            "La inauguracion de {e} tuvo lugar en {v}.",
            "{E} was inaugurated in {v}.",
            "The inauguration of {e} took place in {v}."]),
        "staff": (40, 400, 1, [
            "{E} tiene una plantilla de {v} trabajadores.",
            "La plantilla de {e} es de {v} trabajadores.",
            "{E} has a staff of {v}.",
            "The staff of {e} numbers {v}."]),
    }),
    "museum": ("el museo municipal de {p}", "the {p} municipal museum", {
        "visitors": (20_000, 300_000, 1_000, [
            "{E} recibio {v} visitantes en 2025.",
            "Por {e} pasaron {v} visitantes en 2025.",
            "{E} received {v} visitors in 2025.",
            "In 2025, {v} visitors went through {e}."]),
        "works": (800, 20_000, 100, [
            "La coleccion de {e} reune {v} obras.",
            "{E} conserva {v} obras en su coleccion.",
            "The collection of {e} holds {v} works.",
            "{E} keeps {v} works in its collection."]),
        "year": (1950, 2015, 1, [
            "{E} abrio sus puertas al publico por primera vez en {v}.",
            "{E} abrio al publico por primera vez en {v}.",
            "{E} first opened its doors to the public in {v}.",
            "{E} first opened to the public in {v}."]),
    }),
    "reservoir": ("el embalse de {p}", "the {p} reservoir", {
        "capacity": (20, 900, 1, [
            "{E} tiene una capacidad maxima de {v} hectometros cubicos.",
            "La capacidad maxima de {e} es de {v} hectometros cubicos.",
            "{E} has a maximum capacity of {v} cubic hectometres.",
            "The maximum capacity of {e} is {v} cubic hectometres."]),
        "height": (30, 140, 1, [
            "La presa de {e} tiene una altura de {v} metros.",
            "La altura de la presa de {e} es de {v} metros.",
            "The dam of {e} has a height of {v} metres.",
            "The height of the dam of {e} is {v} metres."]),
        "year": (1950, 2005, 1, [
            "La construccion de {e} termino en {v}.",
            "{E} termino su construccion en {v}.",
            "Construction of {e} was completed in {v}.",
            "{E} completed its construction in {v}."]),
    }),
    "company": ("la empresa Transportes {p}", "the haulier {p} Freight", {
        "revenue": (5, 900, 1, [
            "{E} factura {v} millones de euros al ano.",
            "La facturacion anual de {e} es de {v} millones de euros.",
            "{E} has annual revenue of {v} million euros.",
            "The annual revenue of {e} is {v} million euros."]),
        "employees": (30, 5_000, 1, [
            "{E} tiene {v} empleados.",
            "El numero de empleados de {e} es de {v}.",
            "{E} has {v} employees.",
            "The number of employees of {e} is {v}."]),
        "year": (1950, 2020, 1, [
            "{E} se fundo en {v}.",
            "La fundacion de {e} data de {v}.",
            "{E} was founded in {v}.",
            "The founding of {e} dates from {v}."]),
    }),
    "bridge": ("el puente de {p}", "the {p} bridge", {
        "length": (120, 3_000, 10, [
            "{E} tiene una longitud de {v} metros.",
            "La longitud de {e} es de {v} metros.",
            "{E} has a length of {v} metres.",
            "The length of {e} is {v} metres."]),
        "year": (1960, 2022, 1, [
            "{E} se abrio al trafico en {v}.",
            "La apertura al trafico de {e} fue en {v}.",
            "{E} opened to traffic in {v}.",
            "{E} was opened to traffic in {v}."]),
        "lanes": (2, 8, 1, [
            "{E} tiene {v} carriles.",
            "El numero de carriles de {e} es de {v}.",
            "{E} has {v} lanes.",
            "The number of lanes of {e} is {v}."]),
    }),
    "hospital": ("el hospital comarcal de {p}", "the {p} district hospital", {
        "beds": (80, 1_400, 1, [
            "{E} dispone de {v} camas.",
            "El numero de camas de {e} es de {v}.",
            "{E} has {v} beds.",
            "The number of beds of {e} is {v}."]),
        "year": (1960, 2020, 1, [
            "{E} se inauguro en {v}.",
            "La inauguracion de {e} fue en {v}.",
            "{E} was inaugurated in {v}.",
            "The inauguration of {e} took place in {v}."]),
        "theatres": (4, 40, 1, [
            "{E} cuenta con {v} quirofanos.",
            "El numero de quirofanos de {e} es de {v}.",
            "{E} has {v} operating theatres.",
            "The number of operating theatres of {e} is {v}."]),
    }),
    "cooperative": ("la cooperativa agricola de {p}", "the {p} farming cooperative", {
        "members": (100, 5_000, 1, [
            "{E} tiene {v} socios.",
            "El numero de socios de {e} es de {v}.",
            "{E} has {v} members.",
            "The number of members of {e} is {v}."]),
        "hectares": (200, 20_000, 10, [
            "{E} cultiva {v} hectareas.",
            "La superficie que cultiva {e} es de {v} hectareas.",
            "{E} farms {v} hectares.",
            "The land {e} farms covers {v} hectares."]),
        "year": (1950, 2015, 1, [
            "{E} se fundo en {v}.",
            "La fundacion de {e} fue en {v}.",
            "{E} was founded in {v}.",
            "{E} dates its founding to {v}."]),
    }),
    "festival": ("el festival de musica de {p}", "the {p} music festival", {
        "attendance": (5_000, 400_000, 1_000, [
            "{E} reunio a {v} asistentes en su ultima edicion.",
            "La ultima edicion de {e} tuvo {v} asistentes.",
            "{E} drew {v} attendees at its last edition.",
            "The last edition of {e} had {v} attendees."]),
        "editions": (5, 70, 1, [
            "{E} ha celebrado {v} ediciones.",
            "Hasta hoy se han celebrado {v} ediciones de {e}.",
            "{E} has been held {v} times.",
            "{E} has so far been held {v} times."]),
        "days": (2, 10, 1, [
            "{E} dura {v} dias.",
            "La duracion de {e} es de {v} dias.",
            "{E} lasts {v} days.",
            "The duration of {e} is {v} days."]),
    }),
}
# For every attribute, the words both wordings share, (Spanish, English): they name the same
# event or the same magnitude (one founding, one daily output, one count of operating theatres),
# so two values of it are a conflict by construction. A test checks every template against it.
EVENT_STEMS: dict[tuple[str, str], tuple[str, str]] = {
    ("plant", "output"): ("al dia", "per day"),
    ("plant", "year"): ("inaugur", "inaugur"),
    ("plant", "staff"): ("plantilla", "staff"),
    ("museum", "visitors"): ("visitantes en 2025", "visitors"),
    ("museum", "works"): ("obras", "works"),
    ("museum", "year"): ("por primera vez", "first opened"),
    ("reservoir", "capacity"): ("capacidad maxima", "maximum capacity"),
    ("reservoir", "height"): ("altura de", "height of"),
    ("reservoir", "year"): ("construccion", "construction"),
    ("company", "revenue"): ("factura", "revenue"),
    ("company", "employees"): ("empleados", "employees"),
    ("company", "year"): ("fund", "found"),
    ("bridge", "length"): ("longitud de", "length of"),
    ("bridge", "year"): ("trafico", "traffic"),
    ("bridge", "lanes"): ("carriles", "lanes"),
    ("hospital", "beds"): ("camas", "beds"),
    ("hospital", "year"): ("inaugur", "inaugur"),
    ("hospital", "theatres"): ("quirofanos", "operating theatres"),
    ("cooperative", "members"): ("socios", "members"),
    ("cooperative", "hectares"): ("hectareas", "hectares"),
    ("cooperative", "year"): ("fund", "found"),
    ("festival", "attendance"): ("asistentes", "attendees"),
    ("festival", "editions"): ("ediciones", "held"),
    ("festival", "days"): ("dias", "days"),
}
SOURCES = {
    "es": ("segun su memoria anual", "segun el ultimo informe publicado",
           "de acuerdo con el registro oficial"),
    "en": ("according to its annual report", "according to the latest published report",
           "according to the official register"),
}
# fmt: on


def number(value: int, lang: str, attribute: str) -> str:
    if attribute == "year" or value < 1_000:
        return str(value)
    return f"{value:,}".replace(",", "." if lang == "es" else ",")


def capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def say(kind: str, place: str, attribute: str, value: int, lang: str, wording: int) -> str:
    es, en, attributes = KINDS[kind]
    entity = (es if lang == "es" else en).format(p=place)
    template = attributes[attribute][3][wording + (0 if lang == "es" else 2)]
    text = template.format(E=capital(entity), e=entity, v=number(value, lang, attribute))
    return text.replace(" de el ", " del ").replace(" a el ", " al ")


def draw(rng: random.Random, kind: str, attribute: str) -> int:
    low, high, step, _ = KINDS[kind][2][attribute]
    return rng.randrange(low, high + 1, step)


def other_value(rng: random.Random, kind: str, attribute: str, value: int) -> int:
    """A value plainly different from `value` within the attribute's range."""
    _, _, step, _ = KINDS[kind][2][attribute]
    while True:
        candidate = draw(rng, kind, attribute)
        gap = abs(candidate - value)
        if attribute == "year" and gap >= 2:
            return candidate
        if attribute != "year" and gap >= max(step, 1) and gap >= 0.15 * value:
            return candidate


def places(rng: random.Random, n: int) -> list[str]:
    names = [h + t for h in HEADS for t in TAILS]
    rng.shuffle(names)
    return names[:n]


def one(rng: random.Random, label: str, shape: str, lang: str, pool: list[str]) -> dict:
    kind = rng.choice(sorted(KINDS))
    attributes = sorted(KINDS[kind][2])
    attribute = rng.choice(attributes)
    place, twin = rng.sample(pool, 2)
    value = draw(rng, kind, attribute)
    first = rng.randrange(2)
    a = say(kind, place, attribute, value, lang, first)
    attrs = [attribute, attribute]
    if shape == "values":
        b = say(kind, place, attribute, other_value(rng, kind, attribute, value), lang, 1 - first)
    elif shape == "restated":
        b = say(kind, place, attribute, value, lang, 1 - first)
    elif shape == "detail":
        source = rng.choice(SOURCES[lang])
        said = say(kind, place, attribute, value, lang, 1 - first)
        b = f"{capital(source)}, {said[:1].lower()}{said[1:]}"
    elif shape == "same":
        second = rng.choice([x for x in attributes if x != attribute])
        b = say(kind, place, second, draw(rng, kind, second), lang, rng.randrange(2))
        attrs = [attribute, second]
    else:  # twin: the same attribute of another entity of the same kind
        b = say(kind, twin, attribute, other_value(rng, kind, attribute, value), lang, 1 - first)
    if rng.randrange(2):
        a, b = b, a
    pair = "+".join(sorted(attrs))
    return {
        "label": label,
        "shape": shape,
        "lang": lang,
        "kind": kind,
        "a": a,
        "b": b,
        "pair": pair,
    }


def build(seed: int = SEED) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    pool = places(rng, len(HEADS) * len(TAILS))
    plan = [(label, shape) for label, shape, n in SHAPES for _ in range(n)]
    rng.shuffle(plan)
    cases = []
    seen: set[frozenset[str]] = set()
    for i, (label, shape) in enumerate(plan):
        lang = "es" if i % 2 == 0 else "en"
        case = one(rng, label, shape, lang, pool)
        while frozenset((case["a"], case["b"])) in seen:  # no pair twice, in either order
            case = one(rng, label, shape, lang, pool)
        seen.add(frozenset((case["a"], case["b"])))
        cases.append(
            {
                "id": f"fg-{i + 1:04d}",
                "point": "facts",
                "input": {"fact_a": case["a"], "fact_b": case["b"]},
                "expected": label,
                "shape": shape,
                "lang": lang,
                "kind": case["kind"],
                "attributes": case["pair"],
            }
        )
    return cases


def text_of(cases: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases)


def main() -> int:
    text = text_of(build())
    OUT.write_text(text, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    OUT.with_suffix(".sha256").write_text(digest + "\n", encoding="utf-8", newline="\n")
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
