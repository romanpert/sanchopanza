"""New `redundant_page` cases with labels by construction (lot jev114-redundant-drop).

    python benchmarks/jev114/redundant_gen.py            # writes cases.jsonl, deterministic
    python benchmarks/jev114/redundant_gen.py --check    # the file is what this code writes

WHY. The 90 % derivation of `adds_nothing` on 1.14 hinges on one `keep` page (rd-118) because the
calibration part has 51 `drop` cases: one hard keep above the cut sinks the Wilson lower bound
(docs/results/2026-10-15-jev114-recal/). About 90 more `drop` cases let the derivation clear
with a hard keep or two in the acted set.

HOW THE LABEL IS MADE. No model writes or reads a label here, and no Jev output is used (the
TypeSafe contract forbids training on or distilling them). Each case is rendered by a fixed
template from a fact record in `redundant_scenarios.json` (45 invented events, bodies, firms
and places; people by initial only). A record's fields:

- `doc`, `source`, `date`, `facts`: the primary document. A numeric fact is `[n, unit]`, the
  first fact is numeric and not round, so its rounded-down form is strictly less precise;
- `revision`: the body's later correction of the first figure, `[n, date]`;
- `extra`, `independent`, `qualify`, `off`: material `known` lacks (a detail, another primary
  body, a caveat, an off-purpose page with its own figures).

The cases:

- `known` is the record's primary document: body, date and every fact;
- a `drop` template restates a subset of those facts, or the same facts at less precision,
  attributed to the same body: no new figure, date, name, outcome, qualification or source,
  the question's own criterion. The families are the ones `retrieval-c` names: the wire copy,
  the aggregator headline, the database row, the rounded summary, the body's own press release
  and the partial blog summary;
- a `keep` template adds exactly one thing the record holds and `known` lacks: the body's later
  correction (new figure and date), a withheld detail (new names), an independent primary body
  reaching the same figures (new source), a caveat (new qualification), or an off-purpose page
  about the same place with its own figures (off-purpose is not redundant, `retrieval-c` rule 1).

`check` verifies each label mechanically: every number in a `drop` text is in `known` (or is the
rounded-down form of one, after "mas de"), and none of the record's withheld material appears;
every `keep` text carries its withheld item. The partition into calibration and evaluation is by
scenario, fixed here by the sha256 of its id, so no `known` is shared across the halves.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCENARIOS: list[dict[str, Any]] = json.loads(
    (HERE / "redundant_scenarios.json").read_text(encoding="utf-8")
)["scenarios"]
OUT = ROOT / "docs" / "results" / "2026-10-16-redundant-drop" / "cases.jsonl"
DROP = ("wire", "headline", "ficha", "rounded", "release", "partial")
KEEP = ("revision", "extra", "independent", "offpurpose", "qualify")
KEEPS_PER_SCENARIO = 3
CAL_SCENARIOS = 15  # about 90 new `drop` cases for the derivation; the other 30 evaluate
HEADER = """# redundant_page, lot jev114-redundant-drop: 405 cases rendered from 45 invented fact
# records by benchmarks/jev114/redundant_gen.py. Labels by construction (see that file): 270 `drop`
# (six families x 45) and 135 `keep` (three of five families per record, rotating). `half` is
# the registered partition, by scenario: 15 calibrate (90 drop, 45 keep), 30 evaluate.
# Do not edit by hand: regenerate.
"""


def fmt(n: int) -> str:
    """Spanish thousands: 2350 -> 2.350."""
    return f"{n:,}".replace(",", ".")


def phrase(fact: Any) -> str:
    return f"{fmt(fact[0])} {fact[1]}" if isinstance(fact, list) else fact


def joined(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " y " + parts[-1]


def cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def rounded_down(n: int) -> int:
    """The leading digit kept, the rest zeroed: 2350 -> 2000, 37 -> 30."""
    scale = 10 ** (len(str(n)) - 1)
    return (n // scale) * scale


def contracted(text: str) -> str:
    """Spanish contractions: "de el" -> "del", "a el" -> "al"."""
    return text.replace(" de el ", " del ").replace(" a el ", " al ")


def known_of(s: Mapping[str, Any]) -> str:
    facts = joined([phrase(f) for f in s["facts"]])
    return contracted(f"{s['doc']} de {s['source']} del {s['date']}: {facts}.")


def _numeric(s: Mapping[str, Any]) -> list[list]:
    return [f for f in s["facts"] if isinstance(f, list)]


def drop_text(family: str, s: Mapping[str, Any]) -> str:
    return contracted(_drop_text(family, s))


def _drop_text(family: str, s: Mapping[str, Any]) -> str:
    facts = [phrase(f) for f in s["facts"]]
    src = s["source"]
    first_n, first_unit = s["facts"][0]
    if family == "wire":
        return f"AGENCIA. Segun {src}, el balance es de {joined(facts)}."
    if family == "headline":
        return f"ULTIMA HORA: {joined(facts)}, segun {src}."
    if family == "ficha":
        rows = [f"{cap(unit)}: {fmt(n)}." for n, unit in _numeric(s)]
        notes = [f for f in s["facts"] if not isinstance(f, list)]
        tail = f" Observaciones: {joined(notes)}." if notes else ""
        return f"Ficha. Fuente: {src}. Fecha: {s['date']}. {' '.join(rows)}{tail}"
    if family == "rounded":
        return f"{cap(src)} habla de mas de {fmt(rounded_down(first_n))} {first_unit}."
    if family == "release":
        return f"NOTA DE PRENSA. {cap(src)} presenta hoy sus datos: {joined(facts)}."
    if family == "partial":
        return f"En nuestro blog resumimos los datos de {src}: {joined(facts[:2])}."
    raise ValueError(family)


def keep_text(family: str, s: Mapping[str, Any]) -> str:
    return contracted(_keep_text(family, s))


def _keep_text(family: str, s: Mapping[str, Any]) -> str:
    facts = [phrase(f) for f in s["facts"]]
    first_n, first_unit = s["facts"][0]
    rev_n, rev_date = s["revision"]
    if family == "revision":
        return (f"{cap(s['source'])} corrigio el {rev_date} su propia cifra: {fmt(rev_n)} "
                f"{first_unit}, frente a {fmt(first_n)} en la version inicial.")  # fmt: skip
    if family == "extra":
        return f"{known_of(s)} {s['extra']}"
    if family == "independent":
        return (
            f"{s['independent']} llega por su cuenta a {joined([phrase(f) for f in _numeric(s)])}."
        )
    if family == "offpurpose":
        return s["off"]
    if family == "qualify":
        return f"Segun {s['source']}, {joined(facts)}; el organismo precisa que {s['qualify']}."
    raise ValueError(family)


def half_of(sid: str) -> str:
    """The CAL_SCENARIOS with the lowest sha256 of their id calibrate; the rest evaluate."""
    order = sorted(s["sid"] for s in SCENARIOS)
    ranked = sorted(order, key=lambda x: hashlib.sha256(f"redundant-drop:{x}".encode()).hexdigest())
    return "cal" if ranked.index(sid) < CAL_SCENARIOS else "ev"


def keeps_for(index: int) -> tuple[str, ...]:
    return tuple(KEEP[(index + j) % len(KEEP)] for j in range(KEEPS_PER_SCENARIO))


def cases() -> list[dict[str, Any]]:
    out = []
    for index, s in enumerate(SCENARIOS):
        known = known_of(s)
        rendered = [(f, "drop", drop_text(f, s)) for f in DROP]
        rendered += [(f, "keep", keep_text(f, s)) for f in keeps_for(index)]
        for family, label, text in rendered:
            out.append({
                "id": f"rg-{s['sid']}-{family}",
                "point": "redundant_page",
                "input": {"purpose": s["purpose"], "known": known, "text": text},
                "expected": label,
                "family": family,
                "scenario": s["sid"],
                "half": half_of(s["sid"]),
            })  # fmt: skip
    return out


NUMBER = re.compile(r"\d[\d.]*\d|\d")
WORD = re.compile(r"[a-z]+")
# The words a drop template may add to what `known` and the body's name already hold: its frame.
FRAME = {
    "wire": {"agencia", "segun", "el", "balance", "es", "de"},
    "headline": {"ultima", "hora", "segun"},
    "ficha": {"ficha", "fuente", "fecha", "observaciones"},
    "rounded": {"habla", "de", "mas"},
    "release": {"nota", "de", "prensa", "presenta", "hoy", "sus", "datos"},
    "partial": {"en", "nuestro", "blog", "resumimos", "los", "datos", "de"},
}


def words(text: str) -> set[str]:
    return set(WORD.findall(text.lower()))


def numbers(text: str) -> set[int]:
    return {int(m.replace(".", "")) for m in NUMBER.findall(text)}


def withheld(s: Mapping[str, Any]) -> list[str]:
    """The record's material `known` lacks, as text; the corrected figure is checked as a
    number (`numbers`), since a short one can sit inside a year."""
    return [s["extra"], s["independent"], s["qualify"], s["off"]]


def problems(case: Mapping[str, Any]) -> list[str]:
    """Why a case's label would not follow from its construction; [] when it does."""
    s = next(x for x in SCENARIOS if x["sid"] == case["scenario"])
    known, text = case["input"]["known"], case["input"]["text"]
    out = [f"known holds withheld {w!r}" for w in withheld(s) if w in known]
    if s["revision"][0] in numbers(known):
        out.append("known holds the corrected figure")
    if case["expected"] == "drop":
        out += [f"drop text holds withheld {w!r}" for w in withheld(s) if w in text]
        if s["revision"][0] in numbers(text):
            out.append("drop text holds the corrected figure")
        extra = numbers(text) - numbers(known)
        if case["family"] == "rounded":
            first = s["facts"][0][0]
            if extra != {rounded_down(first)} or rounded_down(first) >= first:
                out.append(f"rounded summary adds {sorted(extra)}")
            if "mas de" not in text:
                out.append("rounded summary without 'mas de'")
        elif extra:
            out.append(f"drop text adds numbers {sorted(extra)}")
        if s["source"] not in text and cap(s["source"]) not in text:
            out.append("drop text does not name the same body")
        added = words(text) - words(known) - words(s["source"]) - FRAME[case["family"]]
        if added:
            out.append(f"drop text adds words outside its frame {sorted(added)}")
    else:
        marker = {"revision": fmt(s["revision"][0]), "extra": s["extra"],
                  "independent": s["independent"], "qualify": s["qualify"],
                  "offpurpose": s["off"]}[case["family"]]  # fmt: skip
        if marker not in text:
            out.append(f"keep text lacks its new item {marker!r}")
        if case["family"] in ("revision", "offpurpose") and not numbers(text) - numbers(known):
            out.append("keep text carries no new figure")
    return out


def render_file() -> str:
    lines = [json.dumps(c, ensure_ascii=False) for c in cases()]
    return HEADER + "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    found = [(c["id"], p) for c in cases() for p in problems(c)]
    if found:
        print("\n".join(f"{i}: {p}" for i, p in found))
        return 1
    text = render_file()
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("cases.jsonl is current" if same else "cases.jsonl differs: regenerate")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    all_cases = cases()
    tally: dict[str, int] = {}
    for c in all_cases:
        key = f"{c['half']} {c['expected']}"
        tally[key] = tally.get(key, 0) + 1
    print(f"{len(all_cases)} cases -> {OUT.relative_to(ROOT).as_posix()}: {tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
