"""Public labelled sets for the label bench: download once, sample evenly, keep outside the repo.

python benchmarks/label/data.py      # free, network; needs pyarrow (dev only)

AG News (4 topics) and DBpedia-14 (14 entity types), test splits, `PER_SET` items each at evenly
spaced row positions: DBpedia's test split is sorted by class, so a head or a random draw with
a chosen seed is not what is registered. Rubrics are the datasets' own class names, each with a
one-line description written before any model saw an item (`RUBRICS`).
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import urllib.request

PER_SET = 300
CACHE = pathlib.Path(
    os.environ.get("SANCHOPANZA_CACHE", pathlib.Path.home() / ".cache" / "sanchopanza")
)
OUT = CACHE / "label"
SOURCES = {
    "agnews": "https://huggingface.co/datasets/fancyzhx/ag_news/resolve/refs%2Fconvert%2Fparquet/"
    "default/test/0000.parquet",
    "dbpedia": "https://huggingface.co/datasets/fancyzhx/dbpedia_14/resolve/refs%2Fconvert%2F"
    "parquet/dbpedia_14/test/0000.parquet",
}
RUBRICS = {
    "agnews": {
        "field": "topic of the news article",
        "options": {
            "World": "International news: politics, conflicts, diplomacy, events abroad",
            "Sports": "Sport: games, athletes, teams, competitions",
            "Business": "Business and economy: companies, markets, earnings, trade, jobs",
            "Sci/Tech": "Science and technology: research, computing, internet, space, health "
            "science",
        },
        "add_other": False,
    },
    "dbpedia": {
        "field": "type of thing the encyclopedia entry is about",
        "options": {
            "Company": "A business or company",
            "EducationalInstitution": "A school, college or university",
            "Artist": "A musician, painter, writer or other artist",
            "Athlete": "A sportsperson",
            "OfficeHolder": "A politician or holder of a public office",
            "MeanOfTransportation": "A vehicle, ship, aircraft, train or rocket",
            "Building": "A building or structure",
            "NaturalPlace": "A mountain, river, lake or other natural place",
            "Village": "A village or small settlement",
            "Animal": "An animal species",
            "Plant": "A plant species",
            "Album": "A music album",
            "Film": "A film",
            "WrittenWork": "A book, journal, newspaper or other written work",
        },
        "add_other": False,
    },
}


def evenly(total: int, n: int) -> list[int]:
    step = total / n
    return [int(i * step) for i in range(n)]


def rows_of(name: str) -> list[dict]:
    import pyarrow.parquet as pq

    with urllib.request.urlopen(SOURCES[name], timeout=300) as response:
        table = pq.read_table(io.BytesIO(response.read())).to_pylist()
    names = list(RUBRICS[name]["options"])
    out = []
    for i in evenly(len(table), PER_SET):
        row = table[i]
        text = row.get("text") or f"{row.get('title', '')}. {row.get('content', '')}"
        out.append({"key": f"{name}-{i}", "text": text.strip(), "gold": names[int(row["label"])]})
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in SOURCES:
        rows = rows_of(name)
        (OUT / f"{name}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )
        (OUT / f"{name}.rubric.json").write_text(json.dumps(RUBRICS[name], indent=1))
        golds = {}
        for r in rows:
            golds[r["gold"]] = golds.get(r["gold"], 0) + 1
        print(name, len(rows), golds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
