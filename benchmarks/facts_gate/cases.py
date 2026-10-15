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

Mix 40 % `unrelated`, 30 % `agree`, 30 % `conflict`, the fifth batch's (12/9/9). Languages
alternate. Nothing here is drawn from a model, and no label is read off a model's answer.
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
SHAPES = (
    ("unrelated", "same", 150),
    ("unrelated", "twin", 50),
    ("agree", "restated", 75),
    ("agree", "detail", 75),
    ("conflict", "values", 150),
)
HEADS = ("Val", "Mor", "Tar", "Bel", "Cas", "Ner", "Ost", "Lum", "Ar", "Quin", "Fer", "Sal")
TAILS = ("dera", "mosa", "illa", "ena", "ueda", "aral", "onte", "ima", "orca", "ada")

# kind: (Spanish entity, English entity, {attribute: (low, high, step, [es1, es2, en1, en2])})
KINDS: dict[str, tuple[str, str, dict[str, tuple[int, int, int, list[str]]]]] = {
    "plant": (
        "la planta desaladora de {p}",
        "the {p} desalination plant",
        {
            "output": (
                20_000,
                90_000,
                1_000,
                [
                    "{E} produce {v} metros cubicos de agua al dia.",
                    "La produccion diaria de {e} es de {v} metros cubicos.",
                    "{E} produces {v} cubic metres of water a day.",
                    "The daily output of {e} is {v} cubic metres.",
                ],
            ),
            "year": (
                1985,
                2020,
                1,
                [
                    "{E} se inauguro en {v}.",
                    "{E} entro en servicio el ano {v}.",
                    "{E} opened in {v}.",
                    "{E} went into service in {v}.",
                ],
            ),
            "staff": (
                40,
                400,
                1,
                [
                    "{E} tiene una plantilla de {v} trabajadores.",
                    "En {e} trabajan {v} personas.",
                    "{E} has a staff of {v}.",
                    "{v} people work at {e}.",
                ],
            ),
        },
    ),
    "museum": (
        "el museo municipal de {p}",
        "the {p} municipal museum",
        {
            "visitors": (
                20_000,
                300_000,
                1_000,
                [
                    "{E} recibio {v} visitantes en 2025.",
                    "En 2025 pasaron por {e} {v} visitantes.",
                    "{E} received {v} visitors in 2025.",
                    "In 2025, {v} visitors went through {e}.",
                ],
            ),
            "works": (
                800,
                20_000,
                100,
                [
                    "La coleccion de {e} reune {v} obras.",
                    "{E} conserva {v} piezas en su coleccion.",
                    "The collection of {e} holds {v} works.",
                    "{E} keeps {v} pieces in its collection.",
                ],
            ),
            "year": (
                1950,
                2015,
                1,
                [
                    "{E} abrio sus puertas en {v}.",
                    "{E} se fundo en {v}.",
                    "{E} opened its doors in {v}.",
                    "{E} was founded in {v}.",
                ],
            ),
        },
    ),
    "reservoir": (
        "el embalse de {p}",
        "the {p} reservoir",
        {
            "capacity": (
                20,
                900,
                1,
                [
                    "{E} tiene una capacidad de {v} hectometros cubicos.",
                    "La capacidad maxima de {e} es de {v} hectometros cubicos.",
                    "{E} holds up to {v} cubic hectometres.",
                    "The maximum capacity of {e} is {v} cubic hectometres.",
                ],
            ),
            "height": (
                30,
                140,
                1,
                [
                    "La presa de {e} mide {v} metros de altura.",
                    "La altura de la presa de {e} es de {v} metros.",
                    "The dam of {e} is {v} metres high.",
                    "The height of the dam of {e} is {v} metres.",
                ],
            ),
            "year": (
                1950,
                2005,
                1,
                [
                    "Las obras de {e} terminaron en {v}.",
                    "{E} se termino de construir en {v}.",
                    "Work on {e} was completed in {v}.",
                    "{E} was finished in {v}.",
                ],
            ),
        },
    ),
    "company": (
        "la empresa Transportes {p}",
        "the haulier {p} Freight",
        {
            "revenue": (
                5,
                900,
                1,
                [
                    "{E} factura {v} millones de euros al ano.",
                    "La facturacion anual de {e} es de {v} millones de euros.",
                    "{E} has annual revenue of {v} million euros.",
                    "The yearly revenue of {e} is {v} million euros.",
                ],
            ),
            "employees": (
                30,
                5_000,
                1,
                [
                    "{E} tiene {v} empleados.",
                    "La plantilla de {e} es de {v} personas.",
                    "{E} has {v} employees.",
                    "The workforce of {e} is {v} people.",
                ],
            ),
            "year": (
                1950,
                2020,
                1,
                [
                    "{E} se fundo en {v}.",
                    "{E} fue constituida en {v}.",
                    "{E} was founded in {v}.",
                    "{E} was incorporated in {v}.",
                ],
            ),
        },
    ),
    "bridge": (
        "el puente de {p}",
        "the {p} bridge",
        {
            "length": (
                120,
                3_000,
                10,
                [
                    "{E} mide {v} metros de longitud.",
                    "La longitud de {e} es de {v} metros.",
                    "{E} is {v} metres long.",
                    "The length of {e} is {v} metres.",
                ],
            ),
            "year": (
                1960,
                2022,
                1,
                [
                    "{E} se abrio al trafico en {v}.",
                    "{E} entro en servicio en {v}.",
                    "{E} opened to traffic in {v}.",
                    "{E} went into service in {v}.",
                ],
            ),
            "lanes": (
                2,
                8,
                1,
                [
                    "{E} tiene {v} carriles.",
                    "Por {e} circulan vehiculos en {v} carriles.",
                    "{E} has {v} lanes.",
                    "Traffic crosses {e} on {v} lanes.",
                ],
            ),
        },
    ),
    "hospital": (
        "el hospital comarcal de {p}",
        "the {p} district hospital",
        {
            "beds": (
                80,
                1_400,
                1,
                [
                    "{E} dispone de {v} camas.",
                    "El numero de camas de {e} es de {v}.",
                    "{E} has {v} beds.",
                    "The bed count of {e} is {v}.",
                ],
            ),
            "year": (
                1960,
                2020,
                1,
                [
                    "{E} se inauguro en {v}.",
                    "{E} abrio en el ano {v}.",
                    "{E} was inaugurated in {v}.",
                    "{E} opened in {v}.",
                ],
            ),
            "theatres": (
                4,
                40,
                1,
                [
                    "{E} cuenta con {v} quirofanos.",
                    "El bloque quirurgico de {e} tiene {v} quirofanos.",
                    "{E} has {v} operating theatres.",
                    "The surgical block of {e} has {v} operating theatres.",
                ],
            ),
        },
    ),
    "cooperative": (
        "la cooperativa agricola de {p}",
        "the {p} farming cooperative",
        {
            "members": (
                100,
                5_000,
                1,
                [
                    "{E} tiene {v} socios.",
                    "El numero de socios de {e} es de {v}.",
                    "{E} has {v} members.",
                    "The membership of {e} is {v}.",
                ],
            ),
            "hectares": (
                200,
                20_000,
                10,
                [
                    "{E} cultiva {v} hectareas.",
                    "La superficie cultivada por {e} es de {v} hectareas.",
                    "{E} farms {v} hectares.",
                    "The land farmed by {e} covers {v} hectares.",
                ],
            ),
            "year": (
                1950,
                2015,
                1,
                [
                    "{E} se fundo en {v}.",
                    "{E} nacio en {v}.",
                    "{E} was founded in {v}.",
                    "{E} was set up in {v}.",
                ],
            ),
        },
    ),
    "festival": (
        "el festival de musica de {p}",
        "the {p} music festival",
        {
            "attendance": (
                5_000,
                400_000,
                1_000,
                [
                    "{E} reunio a {v} asistentes en su ultima edicion.",
                    "La ultima edicion de {e} tuvo {v} asistentes.",
                    "{E} drew {v} attendees at its last edition.",
                    "The last edition of {e} had {v} attendees.",
                ],
            ),
            "editions": (
                5,
                70,
                1,
                [
                    "{E} ha celebrado {v} ediciones.",
                    "{E} va por su edicion numero {v}.",
                    "{E} has been held {v} times.",
                    "{E} is on its edition number {v}.",
                ],
            ),
            "days": (
                2,
                10,
                1,
                [
                    "{E} dura {v} dias.",
                    "Los conciertos de {e} se reparten en {v} dias.",
                    "{E} lasts {v} days.",
                    "The concerts of {e} are spread over {v} days.",
                ],
            ),
        },
    ),
}
SOURCES = {
    "es": ("segun su memoria anual", "segun el ultimo informe publicado",
           "de acuerdo con el registro oficial"),
    "en": ("according to its annual report", "according to the latest published report",
           "according to the official register"),
}  # fmt: skip


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
    low, high, step, _ = KINDS[kind][2][attribute]
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
    else:  # twin: the same attribute of another entity of the same kind
        b = say(kind, twin, attribute, other_value(rng, kind, attribute, value), lang, 1 - first)
    if rng.randrange(2):
        a, b = b, a
    return {"label": label, "shape": shape, "lang": lang, "kind": kind, "a": a, "b": b}


def build(seed: int = SEED) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    pool = places(rng, 60)
    plan = [(label, shape) for label, shape, n in SHAPES for _ in range(n)]
    rng.shuffle(plan)
    cases = []
    for i, (label, shape) in enumerate(plan):
        lang = "es" if i % 2 == 0 else "en"
        case = one(rng, label, shape, lang, pool)
        cases.append(
            {
                "id": f"fg-{i + 1:03d}",
                "point": "facts",
                "input": {"fact_a": case["a"], "fact_b": case["b"]},
                "expected": label,
                "shape": shape,
                "lang": lang,
                "kind": case["kind"],
            }
        )
    return cases


def text_of(cases: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases)


def main() -> int:
    text = text_of(build())
    OUT.write_text(text, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    OUT.with_suffix(".sha256").write_text(digest + "\n", encoding="utf-8")
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
