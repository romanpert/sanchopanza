"""C4: `facts` pairs of fa-17's kinds, written out, with labels that follow from their values.

    python benchmarks/facts_gate/written.py   # writes written.jsonl and its sha256, seeded

A5 (docs/results/2026-10-16-a5-unrelated/) licensed a proposal: `decide_facts(unrelated_at=0.65)`
as the default. Its batch held no pair of the one kind the gate ever got wrong, fa-17 in
`benches/graph.jsonl` ("El nuevo Codigo Penal entro en vigor el 3 de agosto de 2026." against
"La Ley 74-25 se promulgo el 3 de agosto de 2025.", `agree`, read as `unrelated` at 0.63 and
0.59). This batch is made of that kind, three ways, over invented entities:

- `dated`: two dated events of one entity that must come in order (enacted, then in force;
  works begun, then opened; signed, then ratified; born, then died; launched, then retired;
  founded, then dissolved).
- `role`: a role and an act done in it (first appointed in one year; in another year, holding
  the role, did something).
- `subset`: a figure and a part of it (homes damaged, and how many of the damaged homes are
  badly damaged; students, and the foreign ones among them; ...).

The label rule, checkable by hand from the values stored with each case: two facts that
constrain each other are `agree` when their values respect the constraint (the second event
after the first, the act in or after the year of the first appointment, the part smaller than
the whole) and `conflict` when they break it, since then they cannot both be true as stated.
`unrelated` controls pair two facts about the same entity that no values could make
contradict (a law's date and its number of articles, a person's birth and the languages she
speaks), the shape A5 found the gate's verdicts in. Half the `dated` pairs name the entity
two ways, as fa-17 does, with the identity stated in the first fact. Mix 40 % `unrelated`,
30 % `agree`, 30 % `conflict` (A5's and the fifth batch's); languages alternate. Nothing here
is drawn from a model and no label is read off a model's answer.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import random
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "written.jsonl"
SEED = 20261017
PER_KIND = 150  # agree and conflict each, per related kind
UNRELATED = 600
FIRST_NAMES = {
    "f": ("Lucía", "Marta", "Elena", "Irene", "Nuria", "Carmen", "Alba", "Rocío", "Teresa"),
    "m": ("Tomás", "Andrés", "Jorge", "Ramón", "Óscar", "Héctor", "Iván", "Rubén", "Félix"),
}
SURNAMES = ("Valdera", "Morosa", "Tarilla", "Belueda", "Casaral", "Neronte", "Ostima",
            "Lumorca", "Arada", "Quinmosa", "Ferena", "Salonte")  # fmt: skip
PLACES = ("Valdemora", "Torreluz", "Castamar", "Peñalba", "Sanorte", "Villaterra", "Robledal",
          "Montecal", "Aguasol", "Fuenclara", "Riomar", "Navalta")  # fmt: skip
MONTHS = {
    "es": ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
           "septiembre", "octubre", "noviembre", "diciembre"),
    "en": ("January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"),
}  # fmt: skip

# fmt: off
# kind -> domain -> (entity es, entity en, first event es/en, second event es/en). The first
# event must precede the second. `{e}` is the entity, `{d}` a date.
DATED = {
    "law": ("la Ley {n}", "Law {n}",
            ("{E} se promulgó el {d}.", "{E} was enacted on {d}."),
            ("{E} entró en vigor el {d}.", "{E} came into force on {d}.")),
    "bridge": ("el puente de {p}", "the {p} bridge",
               ("Las obras de {e} comenzaron el {d}.", "Work on {e} began on {d}."),
               ("{E} se abrió al tráfico el {d}.", "{E} opened to traffic on {d}.")),
    "treaty": ("el tratado de {p}", "the treaty of {p}",
               ("{E} se firmó el {d}.", "{E} was signed on {d}."),
               ("El parlamento ratificó {e} el {d}.", "Parliament ratified {e} on {d}.")),
    "person": ("{name}", "{name}",
               ("{E} nació el {d}.", "{E} was born on {d}."),
               ("{E} murió el {d}.", "{E} died on {d}.")),
    "ship": ("el buque {s}", "the ship {s}",
             ("{E} fue botado el {d}.", "{E} was launched on {d}."),
             ("{E} fue dado de baja el {d}.", "{E} was withdrawn from service on {d}.")),
    "company": ("la empresa {c}", "the company {c}",
                ("{E} se fundó el {d}.", "{E} was founded on {d}."),
                ("{E} se disolvió el {d}.", "{E} was dissolved on {d}.")),
}
# The second name of a `dated` entity, stated in the first fact as fa-17's pair needs it.
ALIASES = {
    "law": ("el nuevo código de {area}", "the new {area} code"),
    "bridge": ("el puente {s}", "the {s} bridge"),
    "company": ("la antigua naviera de {p}", "the old {p} shipping line"),
}
AREAS = (("aguas", "water"), ("tráfico", "traffic"), ("comercio", "trade"), ("minas", "mining"))
# role -> (role es (f, m), role en, act es, act en)
ROLES = {
    "minister": (("ministra de Sanidad", "ministro de Sanidad"), "Health Minister",
                 "firmó el decreto de vacunación", "signed the vaccination decree"),
    "mayor": (("alcaldesa de {p}", "alcalde de {p}"), "Mayor of {p}",
              "inauguró el mercado municipal", "opened the municipal market"),
    "court": (("presidenta del tribunal de {p}", "presidente del tribunal de {p}"),
              "President of the {p} court", "leyó la sentencia del caso del puerto",
              "read out the ruling in the harbour case"),
    "museum": (("directora del museo de {p}", "director del museo de {p}"),
               "Director of the {p} museum", "abrió la exposición de cerámica",
               "opened the ceramics exhibition"),
    "rector": (("rectora de la Universidad de {p}", "rector de la Universidad de {p}"),
               "Rector of the University of {p}", "entregó los títulos de la primera promoción",
               "handed out the degrees of the first graduating class"),
    "chair": (("presidenta de la cooperativa de {p}", "presidente de la cooperativa de {p}"),
              "Chair of the {p} cooperative", "presentó las cuentas anuales",
              "presented the annual accounts"),
}
# subset -> (whole es/en, part es/en), `{w}` and `{m}` numbers, low and high of the whole.
SUBSETS = {
    "homes": ("El terremoto de {p} dañó {w} viviendas.", "The {p} earthquake damaged {w} homes.",
              "{m} de las viviendas dañadas por el terremoto de {p} tienen daños estructurales "
              "graves.", "{m} of the homes damaged by the {p} earthquake have severe structural "
              "damage.", 300, 9_000),
    "students": ("La Universidad de {p} tiene {w} estudiantes matriculados.",
                 "The University of {p} has {w} enrolled students.",
                 "{m} de los estudiantes matriculados en la Universidad de {p} son extranjeros.",
                 "{m} of the students enrolled at the University of {p} are from abroad.",
                 2_000, 40_000),
    "passengers": ("El aeropuerto de {p} atendió a {w} pasajeros en 2025.",
                   "{p} airport handled {w} passengers in 2025.",
                   "{m} de los pasajeros del aeropuerto de {p} en 2025 viajaban al extranjero.",
                   "{m} of the passengers at {p} airport in 2025 were flying abroad.",
                   50_000, 3_000_000),
    "patients": ("El hospital de {p} atendió a {w} pacientes en 2025.",
                 "{p} hospital treated {w} patients in 2025.",
                 "{m} de los pacientes atendidos en el hospital de {p} en 2025 ingresaron en "
                 "la UCI.",
                 "{m} of the patients treated at {p} hospital in 2025 were admitted to intensive "
                 "care.", 1_000, 60_000),
    "votes": ("En las elecciones municipales de {p} se emitieron {w} votos.",
              "{w} votes were cast in the {p} municipal election.",
              "La candidata ganadora en {p} obtuvo {m} de los votos emitidos.",
              "The winning candidate in {p} won {m} of the votes cast.", 4_000, 200_000),
    "staff": ("La empresa de transportes de {p} emplea a {w} personas.",
              "The {p} transport company employs {w} people.",
              "{m} de los empleados de la empresa de transportes de {p} son conductores.",
              "{m} of the employees of the {p} transport company are drivers.", 150, 8_000),
}
# unrelated -> (fact 1 es/en with {d} or {w}, fact 2 es/en with {k}): the same entity, two
# facts that no values could make contradict.
UNRELATED_PAIRS = {
    "law": ("La Ley {n} se promulgó el {d}.", "Law {n} was enacted on {d}.",
            "La Ley {n} tiene {k} artículos.", "Law {n} has {k} articles.", 20, 400),
    "bridge": ("Las obras del puente de {p} comenzaron el {d}.",
               "Work on the {p} bridge began on {d}.",
               "El puente de {p} mide {k} metros.", "The {p} bridge is {k} metres long.",
               80, 2_000),
    "person": ("{name} nació el {d}.", "{name} was born on {d}.",
               "{name} habla {k} idiomas.", "{name} speaks {k} languages.", 2, 6),
    "homes": ("El terremoto de {p} dañó {w} viviendas.", "The {p} earthquake damaged {w} homes.",
              "El terremoto de {p} duró {k} segundos.", "The {p} earthquake lasted {k} seconds.",
              10, 90),
    "students": ("La Universidad de {p} tiene {w} estudiantes matriculados.",
                 "The University of {p} has {w} enrolled students.",
                 "La biblioteca de la Universidad de {p} abre {k} horas al día.",
                 "The University of {p}'s library is open {k} hours a day.", 8, 24),
    "minister": ("{name} fue {made} {title} de Sanidad por primera vez en {y}.",
                 "{name} was first appointed Health Minister in {y}.",
                 "{name} estudió {k} años de Medicina en {p}.",
                 "{name} studied medicine in {p} for {k} years.", 5, 8),
}
# fmt: on


def date_text(day: dt.date, lang: str) -> str:
    month = MONTHS[lang][day.month - 1]
    return (
        f"{day.day} de {month} de {day.year}" if lang == "es" else f"{day.day} {month} {day.year}"
    )


def number(value: int, lang: str) -> str:
    if value < 10_000:
        return str(value)
    return f"{value:,}".replace(",", "." if lang == "es" else ",")


def contract(text: str) -> str:
    """Spanish "de el" and "a el" as written: "del", "al"."""
    return text.replace(" de el ", " del ").replace(" a el ", " al ")


def capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def person(rng: random.Random) -> tuple[str, str]:
    gender = rng.choice("fm")
    return f"{rng.choice(FIRST_NAMES[gender])} {rng.choice(SURNAMES)}", gender


def names(rng: random.Random) -> dict[str, str]:
    name, gender = person(rng)
    return {"p": rng.choice(PLACES), "n": str(rng.randrange(100, 1000)),
            "s": rng.choice(SURNAMES), "c": f"{rng.choice(SURNAMES)} {rng.choice(PLACES)}",
            "name": name, "gender": gender}  # fmt: skip


def a_date(rng: random.Random, low: int = 1950, high: int = 2020) -> dt.date:
    return dt.date(low, 1, 1) + dt.timedelta(days=rng.randrange((high - low) * 365))


def dated(rng: random.Random, label: str, lang: str) -> dict[str, Any]:
    domain = rng.choice(sorted(DATED))
    n = names(rng)
    entity_es, entity_en, first, second = DATED[domain]
    k = 0 if lang == "es" else 1
    entity = (entity_es if lang == "es" else entity_en).format(**n)
    born = domain == "person"
    start = a_date(rng, 1900 if born else 1950, 1960 if born else 2015)
    days = rng.randrange(20 * 365, 90 * 365) if born else rng.randrange(60, 12 * 365)
    end = start + dt.timedelta(days=days) if label == "agree" else start - dt.timedelta(days=days)
    named = entity
    a_subject, a_object = capital(entity), entity
    if domain in ALIASES and rng.randrange(2):  # fa-17's shape: the second fact uses an alias
        alias = ALIASES[domain][k]
        named = alias.format(
            area=rng.choice(AREAS)[k], p=rng.choice(PLACES), s=rng.choice(SURNAMES)
        )
        a_subject, a_object = f"{capital(entity)}, {named},", f"{entity} ({named})"
    a = first[k].format(E=a_subject, e=a_object, d=date_text(start, lang))
    b = second[k].format(E=capital(named), e=named, d=date_text(end, lang))
    return {"domain": domain, "entity": named, "a": a, "b": b,
            "values": {"first": start.isoformat(), "second": end.isoformat()},
            "shown": [date_text(start, lang), date_text(end, lang)]}  # fmt: skip


def role(rng: random.Random, label: str, lang: str) -> dict[str, Any]:
    domain = rng.choice(sorted(ROLES))
    n = names(rng)
    (title_f, title_m), title_en, act_es, act_en = ROLES[domain]
    appointed = rng.randrange(1990, 2022)
    act = appointed + rng.randrange(0, 6) if label == "agree" else appointed - rng.randrange(1, 9)
    if lang == "es":
        title = (title_f if n["gender"] == "f" else title_m).format(p=n["p"])
        made = "nombrada" if n["gender"] == "f" else "nombrado"
        article = "la" if n["gender"] == "f" else "el"
        a = f"{n['name']} fue {made} {title} por primera vez en {appointed}."
        b = f"En {act}, {article} {title} {n['name']} {act_es}."
    else:
        title = title_en.format(p=n["p"])
        a = f"{n['name']} was first appointed {title} in {appointed}."
        b = f"In {act}, {title} {n['name']} {act_en}."
    return {"domain": domain, "entity": n["name"], "a": a, "b": b,
            "values": {"appointed": appointed, "act": act},
            "shown": [str(appointed), str(act)]}  # fmt: skip


def subset(rng: random.Random, label: str, lang: str) -> dict[str, Any]:
    domain = rng.choice(sorted(SUBSETS))
    n = names(rng)
    whole_es, whole_en, part_es, part_en, low, high = SUBSETS[domain]
    whole = rng.randrange(low, high)
    share = rng.uniform(0.05, 0.6) if label == "agree" else rng.uniform(1.2, 3.0)
    part = max(1, round(whole * share))
    w, m = number(whole, lang), number(part, lang)
    a = (whole_es if lang == "es" else whole_en).format(p=n["p"], w=w)
    b = capital((part_es if lang == "es" else part_en).format(p=n["p"], m=m))
    return {"domain": domain, "entity": n["p"], "a": a, "b": b,
            "values": {"whole": whole, "part": part}, "shown": [w, m]}  # fmt: skip


def unrelated(rng: random.Random, lang: str) -> dict[str, Any]:
    domain = rng.choice(sorted(UNRELATED_PAIRS))
    n = names(rng)
    first_es, first_en, second_es, second_en, low, high = UNRELATED_PAIRS[domain]
    day = a_date(rng)
    female = n["gender"] == "f"
    fill = {**n, "d": date_text(day, lang), "w": number(rng.randrange(300, 40_000), lang),
            "made": "nombrada" if female else "nombrado",
            "title": "ministra" if female else "ministro",
            "y": str(rng.randrange(1990, 2022)),
            "k": str(rng.randrange(low, high + 1))}  # fmt: skip
    a = (first_es if lang == "es" else first_en).format(**fill)
    b = (second_es if lang == "es" else second_en).format(**fill)
    entity = {"law": f"{n['n']}", "person": n["name"], "minister": n["name"]}.get(domain, n["p"])
    return {"domain": domain, "entity": entity, "a": a, "b": b, "values": {}, "shown": [fill["k"]]}


MAKERS = {"dated": dated, "role": role, "subset": subset}


def one(rng: random.Random, label: str, kind: str, lang: str) -> dict[str, Any]:
    case = unrelated(rng, lang) if kind == "unrelated" else MAKERS[kind](rng, label, lang)
    case = {**case, "a": contract(case["a"]), "b": contract(case["b"])}
    if rng.randrange(2):
        case = {**case, "a": case["b"], "b": case["a"]}
    return case


def build(seed: int = SEED) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    plan = [(label, kind) for kind in MAKERS for label in ("agree", "conflict")
            for _ in range(PER_KIND)] + [("unrelated", "unrelated")] * UNRELATED  # fmt: skip
    rng.shuffle(plan)
    cases, seen = [], set()
    for i, (label, kind) in enumerate(plan):
        lang = "es" if i % 2 == 0 else "en"
        case = one(rng, label, kind, lang)
        while frozenset((case["a"], case["b"])) in seen:  # no pair twice, in either order
            case = one(rng, label, kind, lang)
        seen.add(frozenset((case["a"], case["b"])))
        cases.append({
            "id": f"fw-{i + 1:04d}", "point": "facts",
            "input": {"fact_a": case["a"], "fact_b": case["b"]},
            "expected": label, "lang": lang, "kind": kind, "attributes": case["domain"],
            "entity": case["entity"], "values": case["values"], "shown": case["shown"],
        })  # fmt: skip
    return cases


def text_of(cases: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    text = text_of(build())
    OUT.write_bytes(text.encode("utf-8"))
    OUT.with_suffix(".sha256").write_bytes((digest(text) + "\n").encode())
    print(digest(text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
