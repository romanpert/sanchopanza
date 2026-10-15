"""Items for the Jev 1.14 label comparison (docs/results/2026-10-15-jev114-l3).

python -I benchmarks/label/data114.py      # free, network; needs pyarrow (dev only)

Third-party data: the parquet files are read with `python -I` and kept outside the repository,
in `~/.cache/sanchopanza/label-jev114/`.

- **AG News and DBpedia-14, 1,000 items each.** The 300 positions of the 2026-09-30 run (so
  that run's recorded 1.13 answers line up with today's on those items) and 700 more, evenly
  spaced over the test rows the 300 did not take. Rubrics: `data.RUBRICS`, unchanged.
- **SIB-200** (Adelani et al., 2024; topic classification of FLORES-200 sentences, 7 topics,
  CC BY-SA 4.0): the whole test split, 204 sentences, in six languages. The sentences are
  translations of one another, so the same `index_id` is the same sentence in every language.
  Rubric: `SIB_RUBRIC`, in English for every language (a fixed rubric over a multilingual
  corpus), written before any model saw an item.
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import sys
import urllib.request
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from data import RUBRICS, SOURCES, evenly  # noqa: E402

ORIGINAL_PER_SET = 300
PER_SET = 1000
SIB_LANGS = ("eng_Latn", "spa_Latn", "fra_Latn", "deu_Latn", "zho_Hans", "arb_Arab")
SIB_URL = (
    "https://huggingface.co/datasets/Davlan/sib200/resolve/refs%2Fconvert%2Fparquet/"
    "{lang}/test/0000.parquet"
)
SIB_RUBRIC: dict[str, Any] = {
    "field": "topic of the sentence",
    "options": {
        "science/technology": "Science and technology: research, nature and biology, physics, "
        "computing, inventions",
        "travel": "Travel and tourism: trips, destinations, transport for travellers, "
        "accommodation, travel advice",
        "politics": "Politics and government: elections, leaders, laws, wars, international "
        "relations",
        "sports": "Sport: games, athletes, teams, competitions",
        "health": "Health and medicine: diseases, the body, treatments, wellbeing",
        "entertainment": "Entertainment and culture: music, film, festivals, games, arts, "
        "celebrations",
        "geography": "Geography: countries, regions, landforms, climate, population of places",
    },
    "add_other": False,
}
CACHE = pathlib.Path(
    os.environ.get("SANCHOPANZA_CACHE", pathlib.Path.home() / ".cache" / "sanchopanza")
)
OUT = CACHE / "label-jev114"


def positions(total: int) -> list[int]:
    """The 2026-09-30 positions, plus 700 evenly spaced over the rows they did not take."""
    original = evenly(total, ORIGINAL_PER_SET)
    taken = set(original)
    rest = [i for i in range(total) if i not in taken]
    extra = [rest[k] for k in evenly(len(rest), PER_SET - ORIGINAL_PER_SET)]
    return sorted(taken | set(extra))


def _table(url: str) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    with urllib.request.urlopen(url, timeout=300) as response:
        return pq.read_table(io.BytesIO(response.read())).to_pylist()


def english_rows(name: str) -> list[dict[str, Any]]:
    table = _table(SOURCES[name])
    names = list(RUBRICS[name]["options"])
    original = set(evenly(len(table), ORIGINAL_PER_SET))
    out = []
    for i in positions(len(table)):
        row = table[i]
        text = row.get("text") or f"{row.get('title', '')}. {row.get('content', '')}"
        out.append({"key": f"{name}-{i}", "text": text.strip(),
                    "gold": names[int(row["label"])], "original": i in original})  # fmt: skip
    return out


def sib_rows() -> list[dict[str, Any]]:
    options = set(SIB_RUBRIC["options"])
    out = []
    for lang in SIB_LANGS:
        for row in _table(SIB_URL.format(lang=lang)):
            if row["category"] not in options:
                raise SystemExit(f"unexpected SIB-200 category {row['category']!r}")
            out.append({"key": f"sib-{lang}-{row['index_id']}", "text": str(row["text"]).strip(),
                        "gold": row["category"], "lang": lang,
                        "sentence": int(row["index_id"])})  # fmt: skip
    return out


def write(name: str, rows: list[dict[str, Any]], rubric: dict[str, Any]) -> None:
    (OUT / f"{name}.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    (OUT / f"{name}.rubric.json").write_text(json.dumps(rubric, indent=1), encoding="utf-8")
    golds: dict[str, int] = {}
    for r in rows:
        golds[r["gold"]] = golds.get(r["gold"], 0) + 1
    print(name, len(rows), golds)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in SOURCES:
        write(name, english_rows(name), RUBRICS[name])
    write("sib", sib_rows(), SIB_RUBRIC)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
