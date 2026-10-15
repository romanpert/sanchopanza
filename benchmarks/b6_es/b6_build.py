"""Build the B6 bench: page triage and passage selection in Spanish, labels by construction.

    python -I benchmarks/b6_es/b6_build.py [--data DIR]           # rebuild from the manifest
    python -I benchmarks/b6_es/b6_build.py [--data DIR] --fresh   # draw anew, write it

DIR defaults to $SANCHOPANZA_B6_DATA, else ~/.cache/sanchopanza/b6-es; `b6_run.py` reads the
same default and takes the same `--data`.

Run with `-I`: the inputs are downloaded and untrusted, and the script puts this repository's
`src` on the path itself. Nothing here calls a model.

Source: MLQA v1.0 (Lewis et al., 2020, facebookresearch/MLQA), CC BY-SA 3.0. Its Spanish
contexts are native Spanish Wikipedia paragraphs; each question was written in English and
translated by professionals, and its answer span was marked in the Spanish paragraph. Every
Spanish test item has the same id in the English test file, with its English question, answer
and English Wikipedia paragraph: a paired English control on the same questions. The archive is
downloaded to the data directory and checked against its SHA-256; it is never committed.

Two benches, disjoint by article:

- **pages** (`triage_pages`, HotpotQA's shape): the question's own MLQA paragraph and nine
  distractor paragraphs of the same split, chosen by BM25 in both languages at once (rank sum),
  none holding the answer string in either language. The gold page is the question's own
  paragraph, by construction; the same ten units, in the same order, in each language.
- **docs** (`select_passages`, QASPER's shape): the whole Wikipedia article, Spanish and
  English, at a revision pinned in the manifest. The gold sentence is the one holding the
  answer: the MLQA sentence around the answer span (its anchor) is located in the article by
  its letters and digits only, and must occur exactly once; an article where it does not is
  excluded and the reason counted.

Committed: `docs/results/2026-10-16-b6-es/bench-manifest.json` (ids, revision ids, counts,
exclusion reasons, SHA-256 of the built files). Not committed: the archive, the article cache
and the built files, under `--data`.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import random
import re
import sys
import urllib.request
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

import b6_wiki as wiki  # noqa: E402

from sanchopanza.select import Candidate, index_of  # noqa: E402
from sanchopanza.text import BM25Index, split_sentences  # noqa: E402

MLQA_URL = "https://dl.fbaipublicfiles.com/MLQA/MLQA_V1.zip"
MLQA_SHA256 = "246e8089933d13007fe80684d5c5c0713d6834cf8b3b4a0ec7c66f0a0d2baac8"
MLQA_LICENCE = "CC BY-SA 3.0 (MLQA v1.0); article text CC BY-SA 4.0 (Wikipedia)"
MEMBERS = {
    ("test", "es"): "MLQA_V1/test/test-context-es-question-es.json",
    ("test", "en"): "MLQA_V1/test/test-context-en-question-en.json",
    ("dev", "es"): "MLQA_V1/dev/dev-context-es-question-es.json",
    ("dev", "en"): "MLQA_V1/dev/dev-context-en-question-en.json",
}
LANGS = ("es", "en")
SEED = 20261016
PAGES_N = 300  # questions in the pages bench
DOCS_N = 400  # questions in the docs bench; the pre-registration says how many are asked
SMOKE_N = 2  # dev questions per bench for a smoke run
PAGES_PER_SET = 10
MIN_ANCHOR_KEY = 20  # letters and digits an anchor needs to be located without ambiguity
MIN_PARAGRAPHS = 20  # a long document: at least this many paragraphs, in both languages
FOOTNOTE = re.compile(r"\[[^\[\]]{1,15}\]")
# The fuzzy fallback for an anchor edited since 2019: matched blocks of at least MIN_BLOCK
# letters must cover FUZZY_MIN of it inside a stretch of the paragraph at most FUZZY_SPAN times
# its length, in one paragraph only (the next best under FUZZY_MIN), and the answer must lie in
# one matched block or occur exactly once near the stretch.
FUZZY_MIN = 0.85
FUZZY_SPAN = 1.5
MIN_BLOCK = 8
MANIFEST = REPO / "docs" / "results" / "2026-10-16-b6-es" / "bench-manifest.json"
DEFAULT_DATA = Path(
    os.environ.get("SANCHOPANZA_B6_DATA") or Path.home() / ".cache" / "sanchopanza" / "b6-es"
)


# ---- text helpers ------------------------------------------------------------------------------


def collapse_with_map(text: str) -> tuple[str, list[int]]:
    """`text` with whitespace runs collapsed, footnote marks and zero-width characters dropped
    (as `wiki.collapse`) and the ends stripped, and for each original position the position it
    maps to in the result (a dropped or stripped character maps to the next kept one, or the
    nearest edge)."""
    marks = {i for m in wiki.MARK.finditer(text) for i in range(m.start(), m.end())}
    out: list[str] = []
    where: list[int] = []
    pending_space = False
    for i, ch in enumerate(text):
        if ch in wiki.ZERO_WIDTH or i in marks:
            where.append(len(out) + (1 if pending_space else 0))
            continue
        if ch.isspace():
            pending_space = bool(out)
            where.append(len(out) + (1 if pending_space else 0))
            continue
        if pending_space:
            out.append(" ")
            pending_space = False
        where.append(len(out))
        out.append(ch)
    flat = "".join(out)
    return flat, [min(w, len(flat)) for w in where]


def key_of(text: str) -> tuple[str, list[int]]:
    """Letters and digits only, case-folded, with each one's position in `text`. A short
    bracketed mark (`[22]`, `[n. 3]`) is skipped: MLQA's paragraphs keep footnote marks that
    today's HTML holds in `<sup>`, and their digits would break every match."""
    masked = FOOTNOTE.sub(lambda m: " " * len(m.group(0)), text)
    chars: list[str] = []
    positions: list[int] = []
    for i, ch in enumerate(masked):
        if ch.isalnum():
            folded = ch.casefold()
            chars.append(folded)
            positions.extend([i] * len(folded))
    return "".join(chars), positions


def sentence_ranges(paragraph: str) -> list[tuple[int, int]]:
    """Character ranges of `split_sentences(paragraph)` in a whitespace-collapsed paragraph."""
    ranges, start = [], 0
    for sentence in split_sentences(paragraph):
        at = paragraph.find(sentence, start)
        if at < 0:
            raise ValueError("split_sentences changed the text of a collapsed paragraph")
        ranges.append((at, at + len(sentence)))
        start = at + len(sentence)
    return ranges


def overlapping(ranges: Sequence[tuple[int, int]], a: int, b: int) -> list[bool]:
    return [s < b and e > a for s, e in ranges]


# ---- MLQA --------------------------------------------------------------------------------------


def download(data: Path) -> Path:
    """The MLQA archive under `data/mlqa`, downloaded once and checked against its SHA-256."""
    target = data / "mlqa" / "MLQA_V1.zip"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(MLQA_URL, headers={"User-Agent": wiki.USER_AGENT})
        with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310 - fixed https
            target.write_bytes(response.read())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != MLQA_SHA256:
        raise SystemExit(f"{target} has SHA-256 {digest}, not MLQA v1.0's: nothing built")
    return target


def one_item(title: str, context: str, qa: Mapping[str, Any]) -> dict[str, Any] | None:
    """An MLQA item, whitespace-collapsed, with its answer span and anchor sentence located
    in the collapsed paragraph; None when the span does not check out."""
    answer = qa["answers"][0]
    flat, where = collapse_with_map(context)
    text = wiki.collapse(answer["text"])
    start = int(answer["answer_start"])
    if not text or start >= len(where):
        return None
    a = where[start]
    if flat[a : a + len(text)] != text:
        hits = [i for i in range(len(flat)) if flat.startswith(text, i)]
        if not hits:
            return None
        a = min(hits, key=lambda i: abs(i - a))
    b = a + len(text)
    ranges = sentence_ranges(flat)
    inside = [i for i, hit in enumerate(overlapping(ranges, a, b)) if hit]
    if not inside:
        return None
    anchor = (ranges[inside[0]][0], ranges[inside[-1]][1])
    return {
        "title": wiki.collapse(title),
        "context": flat,
        "question": wiki.collapse(qa["question"]),
        "answer": text,
        "answer_span": [a, b],
        "anchor_span": list(anchor),
    }


def load_mlqa(archive: Path, split: str) -> dict[str, dict[str, dict[str, Any]]]:
    """`{id: {"es": item, "en": item}}` for every id present and well-formed in both files."""
    by_lang: dict[str, dict[str, dict[str, Any]]] = {}
    with zipfile.ZipFile(archive) as z:
        for lang in LANGS:
            raw = json.loads(z.read(MEMBERS[(split, lang)]).decode("utf-8"))
            items: dict[str, dict[str, Any]] = {}
            for article in raw["data"]:
                for paragraph in article["paragraphs"]:
                    for qa in paragraph["qas"]:
                        item = one_item(article["title"], paragraph["context"], qa)
                        if item is not None:
                            items[str(qa["id"])] = item
            by_lang[lang] = items
    shared = sorted(set(by_lang["es"]) & set(by_lang["en"]))
    return {i: {lang: by_lang[lang][i] for lang in LANGS} for i in shared}


def draw_order(ids: Iterable[str], seed: int = SEED) -> list[str]:
    order = sorted(ids)
    random.Random(seed).shuffle(order)
    return order


def one_per_title(order: Sequence[str], items: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """The first id of each Spanish article title, in draw order: one question per article."""
    seen: set[str] = set()
    out = []
    for i in order:
        title = items[i]["es"]["title"]
        if title not in seen:
            seen.add(title)
            out.append(i)
    return out


# ---- pages bench -------------------------------------------------------------------------------


def contains_answer(text: str, answer: str) -> bool:
    needle = key_of(answer)[0]
    return bool(needle) and needle in key_of(text)[0]


class Pool:
    """The distractor pool: one unit per distinct Spanish paragraph, with its English twin."""

    def __init__(self, items: Mapping[str, Mapping[str, Any]]) -> None:
        seen: set[str] = set()
        self.ids: list[str] = []
        for i in sorted(items):
            if items[i]["es"]["context"] not in seen:
                seen.add(items[i]["es"]["context"])
                self.ids.append(i)
        self.items = items
        self.index = {
            lang: BM25Index([items[i][lang]["context"] for i in self.ids]) for lang in LANGS
        }
        self.keys = {
            lang: [key_of(items[i][lang]["context"])[0] for i in self.ids] for lang in LANGS
        }

    def ranks(self, lang: str, question: str) -> list[int]:
        scores = self.index[lang].scores(question)
        order = sorted(range(len(scores)), key=lambda k: (-scores[k], k))
        out = [0] * len(scores)
        for rank, k in enumerate(order):
            out[k] = rank
        return out

    def distractors(self, qid: str, count: int) -> list[str]:
        gold = self.items[qid]
        ranks = {lang: self.ranks(lang, gold[lang]["question"]) for lang in LANGS}
        answers = {lang: key_of(gold[lang]["answer"])[0] for lang in LANGS}
        own = {lang: gold[lang]["context"] for lang in LANGS}
        order = sorted(range(len(self.ids)), key=lambda k: (ranks["es"][k] + ranks["en"][k], k))
        out: list[str] = []
        for k in order:
            unit = self.items[self.ids[k]]
            if any(unit[lang]["context"] == own[lang] for lang in LANGS):
                continue
            if any(answers[lang] and answers[lang] in self.keys[lang][k] for lang in LANGS):
                continue
            if any(unit[lang]["context"] == self.items[o][lang]["context"]
                   for o in out for lang in LANGS):  # fmt: skip
                continue
            out.append(self.ids[k])
            if len(out) == count:
                break
        return out


def page_row(qid: str, pool: Pool, seed: int = SEED) -> dict[str, Any] | None:
    """One pages-bench question: ten units in a seeded order, the same in both languages."""
    others = pool.distractors(qid, PAGES_PER_SET - 1)
    if len(others) < PAGES_PER_SET - 1:
        return None
    units = [qid, *others]
    random.Random(f"{seed}-{qid}").shuffle(units)
    gold_at = units.index(qid)
    row: dict[str, Any] = {"id": qid, "units": units, "gold": gold_at}
    for lang in LANGS:
        item = pool.items[qid][lang]
        row[lang] = {
            "question": item["question"],
            "answer": item["answer"],
            "answer_span": item["answer_span"],
            "pages": [
                [pool.items[u][lang]["title"], pool.items[u][lang]["context"]] for u in units
            ],
        }
    return row


# ---- docs bench --------------------------------------------------------------------------------


def _fuzzy(needle: str, hay: str) -> tuple[float, list[tuple[int, int, int]]]:
    """Coverage of `needle` by blocks of at least MIN_BLOCK shared letters, in order, inside a
    stretch of `hay` at most FUZZY_SPAN times its length; and those blocks `(a, b, size)`."""
    matcher = difflib.SequenceMatcher(None, needle, hay, autojunk=False)
    blocks = [(m.a, m.b, m.size) for m in matcher.get_matching_blocks() if m.size >= MIN_BLOCK]
    if not blocks:
        return 0.0, []
    stretch = blocks[-1][1] + blocks[-1][2] - blocks[0][1]
    if stretch > FUZZY_SPAN * len(needle):
        return 0.0, []
    return sum(size for _, _, size in blocks) / len(needle), blocks


def _answer_in(blocks, inside: Sequence[int], needle: str, hay: str) -> tuple[int, int] | None:
    """The answer's `[start, end)` in `hay`'s key: inside one matched block, else the answer's
    letters occurring exactly once within the matched stretch (60 letters either side)."""
    i0, i1 = inside[0], inside[-1] + 1
    for a, b, size in blocks:
        if a <= i0 and i1 <= a + size:
            return b + i0 - a, b + i1 - a
    answer = needle[i0:i1]
    lo = max(0, blocks[0][1] - 60)
    hi = blocks[-1][1] + blocks[-1][2] + 60
    found = [m.start() + lo for m in re.finditer(re.escape(answer), hay[lo:hi])]
    return (found[0], found[0] + len(answer)) if len(found) == 1 else None


def locate(anchor: str, answer_offset: tuple[int, int], paragraphs: Sequence[tuple[str, str]]):
    """Where the anchor's answer lies in the article: `(paragraph, start, end, how)`, or a reason.

    The anchor is matched on letters and digits only (footnote marks, quotes and spacing differ
    between MLQA's extraction and today's HTML). `how` is "exact" when it occurs exactly once in
    the article; failing any exact occurrence, "fuzzy" when one paragraph alone holds it edited
    (`_fuzzy`) and the answer is still there, letter for letter (`_answer_in`)."""
    needle, positions_in_anchor = key_of(anchor)
    if len(needle) < MIN_ANCHOR_KEY:
        return "anchor too short"
    a_off, b_off = answer_offset
    inside = [k for k, p in enumerate(positions_in_anchor) if a_off <= p < b_off]
    if not inside:
        return "answer has no letters or digits"
    keyed = [key_of(text) for _, text in paragraphs]
    hits = []
    for j, (hay, _) in enumerate(keyed):
        start = hay.find(needle)
        while start >= 0:
            hits.append((j, start))
            start = hay.find(needle, start + 1)
    if len(hits) > 1:
        return "anchor more than once"
    if hits:
        j, start = hits[0]
        positions = keyed[j][1]
        return j, positions[start + inside[0]], positions[start + inside[-1]] + 1, "exact"
    scored = sorted(((*_fuzzy(needle, hay), j) for j, (hay, _) in enumerate(keyed)),
                    key=lambda t: -t[0])  # fmt: skip
    if not scored or scored[0][0] < FUZZY_MIN:
        return "anchor not in the article"
    if len(scored) > 1 and scored[1][0] >= FUZZY_MIN:
        return "anchor more than once"
    _, blocks, j = scored[0]
    span = _answer_in(blocks, inside, needle, keyed[j][0])
    if span is None:
        return "answer not in the edited anchor"
    positions = keyed[j][1]
    return j, positions[span[0]], positions[span[1] - 1] + 1, "fuzzy"


def doc_side(item: Mapping[str, Any], article: wiki.Article) -> dict[str, Any] | str:
    a, b = item["answer_span"]
    s, e = item["anchor_span"]
    anchor = item["context"][s:e]
    found = locate(anchor, (a - s, b - s), article.paragraphs)
    if isinstance(found, str):
        return found
    j, start, end, how = found
    paragraphs = [[section, text] for section, text in article.paragraphs]
    gold = []
    for k, (_, text) in enumerate(paragraphs):
        ranges = sentence_ranges(text)
        gold.append(overlapping(ranges, start, end) if k == j else [False] * len(ranges))
    if not any(gold[j]):
        return "answer outside every sentence"
    return {
        "question": item["question"],
        "answer": item["answer"],
        "title": article.title,
        "revid": article.revid,
        "pages": paragraphs,
        "gold_paragraph": j,
        "gold_s": gold,
        "match": how,
    }


def doc_row(qid: str, pair: Mapping[str, Mapping[str, Any]], fetcher: wiki.Fetcher,
            revids: Mapping[str, int] | None = None) -> dict[str, Any] | str:  # fmt: skip
    """One docs-bench question in both languages, or the reason it is excluded."""
    row: dict[str, Any] = {"id": qid}
    for lang in LANGS:
        try:
            if revids is not None:
                article = fetcher.article(lang, revid=int(revids[lang]))
            else:
                article = fetcher.article(lang, title=pair[lang]["title"])
        except (LookupError, OSError, ValueError) as error:
            return f"{lang}: article unavailable ({type(error).__name__})"
        side = doc_side(pair[lang], article)
        if isinstance(side, str):
            return f"{lang}: {side}"
        if len(side["pages"]) < MIN_PARAGRAPHS:
            return f"{lang}: under {MIN_PARAGRAPHS} paragraphs"
        row[lang] = side
    return row


def preselect(question: str, pages: Sequence[Sequence[str]], most: int) -> list[int]:
    """The consumer's preselection past `most` paragraphs: the `most` best by BM25 over
    section and text (the package's `select.index_of`), ties and zero scores by page order,
    returned in page order. A document of `most` paragraphs or fewer is returned whole."""
    if len(pages) <= most:
        return list(range(len(pages)))
    index = index_of([Candidate(str(k), s, t) for k, (s, t) in enumerate(pages)])
    scores = index.scores(question)
    best = sorted(range(len(pages)), key=lambda k: (-scores[k], k))[:most]
    return sorted(best)


# ---- build -------------------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Bytes with LF line ends: the SHA-256 in the manifest must hold on any system.
    path.write_bytes("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode())
    return sha256_of(path)


def build_docs(
    order: Sequence[str],
    items: Mapping[str, Any],
    fetcher: wiki.Fetcher,
    n: int,
    pinned: Mapping[str, Mapping[str, int]] | None,
) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    rows: list[dict[str, Any]] = []
    excluded: dict[str, int] = {}
    tried: list[str] = []
    ids = list(pinned) if pinned is not None else order
    for qid in ids:
        if len(rows) == n:
            break
        tried.append(qid)
        got = doc_row(qid, items[qid], fetcher, pinned[qid] if pinned is not None else None)
        if isinstance(got, str):
            excluded[got] = excluded.get(got, 0) + 1
            continue
        rows.append(got)
        print(f"docs {len(rows)}/{n} (tried {len(tried)})", file=sys.stderr)
    return rows, excluded, tried


def build(data: Path, *, fresh: bool, pages_n: int = PAGES_N, docs_n: int = DOCS_N,
          offline: bool = False) -> dict[str, Any]:  # fmt: skip
    archive = download(data)
    fetcher = wiki.Fetcher(data / "wiki", offline=offline)
    out: dict[str, Any] = {
        "source": MLQA_URL,
        "sha256": MLQA_SHA256,
        "licence": MLQA_LICENCE,
        "seed": SEED,
        "language_pairs": "es with its en twin, same MLQA id",
    }
    manifest = None if fresh else json.loads(MANIFEST.read_text(encoding="utf-8"))
    for split, n_pages, n_docs, name in (
        ("test", pages_n, docs_n, ""),
        ("dev", SMOKE_N, SMOKE_N, "smoke-"),
    ):
        items = load_mlqa(archive, split)
        order = one_per_title(draw_order(items), items)
        key = f"{name}docs"
        pinned = None
        if manifest is not None:
            pinned = {q: manifest[key]["revids"][q] for q in manifest[key]["ids"]}
        docs, excluded, tried = build_docs(order, items, fetcher, n_docs, pinned)
        doc_titles = {items[r["id"]]["es"]["title"] for r in docs}
        doc_tried_titles = {items[q]["es"]["title"] for q in tried}
        pool = Pool(items)
        if manifest is not None:
            page_ids = manifest[f"{name}pages"]["ids"]
        else:
            page_ids = [q for q in order if items[q]["es"]["title"] not in doc_tried_titles]
        pages: list[dict[str, Any]] = []
        for qid in page_ids:
            if len(pages) == n_pages:
                break
            row = page_row(qid, pool)
            if row is not None and items[qid]["es"]["title"] not in doc_titles:
                pages.append(row)
        files = {
            f"{name}pages": write_jsonl(data / f"{name}pages.jsonl", pages),
            f"{name}docs": write_jsonl(data / f"{name}docs.jsonl", docs),
        }
        out[f"{name}pages"] = {"ids": [r["id"] for r in pages], "sha256": files[f"{name}pages"]}
        out[key] = {
            "ids": [r["id"] for r in docs],
            "revids": {r["id"]: {lang: r[lang]["revid"] for lang in LANGS} for r in docs},
            "tried": len(tried),
            "excluded": dict(sorted(excluded.items())),
            "sha256": files[key],
        }
    out["fetched_now"] = fetcher.fetched
    if manifest is not None:
        for name in ("pages", "docs", "smoke-pages", "smoke-docs"):
            if out[name]["sha256"] != manifest[name]["sha256"]:
                raise SystemExit(f"{name}: rebuilt file differs from the manifest's SHA-256")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--fresh", action="store_true", help="draw anew and write the manifest")
    ap.add_argument("--offline", action="store_true", help="articles from the cache only")
    args = ap.parse_args()
    if not args.fresh and not MANIFEST.exists():
        raise SystemExit(f"no manifest at {MANIFEST}: run with --fresh first")
    if args.fresh and (MANIFEST.parent / "prereg.sha256").exists():
        raise SystemExit("the pre-registration is sealed: a fresh draw would change its bench")
    out = build(args.data, fresh=args.fresh, offline=args.offline)
    if args.fresh:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_bytes((json.dumps(out, indent=1) + "\n").encode())
    summary = {k: (len(v["ids"]) if isinstance(v, dict) and "ids" in v else v)
               for k, v in out.items()}  # fmt: skip
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
