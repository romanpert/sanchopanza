"""BrowseComp-Plus (Chen et al., 2025), cached outside the repository, never shown in plain text.

  <bcp venv>/python benchmarks/h2h/bcp_data.py --fetch    # network: queries, qrels, corpus
  <bcp venv>/python benchmarks/h2h/bcp_data.py --build    # the doc store and the BM25 index
  python benchmarks/h2h/bcp_data.py                        # free: counts and ids only

The set is `Tevatron/browsecomp-plus` (830 queries, MIT) over `Tevatron/browsecomp-plus-corpus`
(100,195 documents). Its queries and answers are published encrypted, as BrowseComp's are, and
stay encrypted on this disk: `queries.enc.jsonl` keeps the ciphertext, and the runner decrypts a
query in memory only to put it in a session's prompt and to grade it. The password is the
canary string of the official `decrypt_dataset.py`, read from the official repository by
`--fetch` into the cache (never into this repository). Only the three columns we need are read
from the 2.8 GB query parquet (range reads); the qrels come from the official repository.

The corpus (plain text) and its index live under `CACHE`. The official BM25 is Pyserini's
Lucene index (k1 0.9, b 0.4, Porter stemmer, Lucene's English stop words); Pyserini needs Java 21
and this PC has 17, so `--build` makes a `bm25s` index with the same k1, b, stemmer and stop
words (method "lucene"): close to the official ranking, not bit-identical (tokeniser). The heavy
imports (bm25s, pyarrow, huggingface_hub) live in a venv of their own, `VENV`; this module
imports them only inside the functions that need them, so the runner and the tests stay stdlib.

Nothing printed here is text of the set: counts, ids and sizes.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import pathlib
import re
import sqlite3
import sys
import urllib.request
from array import array
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

CACHE = pathlib.Path.home() / ".cache" / "sanchopanza" / "bcp"
VENV_PYTHON = CACHE / "venv" / "Scripts" / "python.exe"
QUERIES = CACHE / "queries.enc.jsonl"
QRELS = {"evidence": CACHE / "qrel_evidence.txt", "gold": CACHE / "qrel_golds.txt"}
CANARY = CACHE / "canary.txt"
CORPUS_DIR = CACHE / "hf" / "corpus"
DOCS = CACHE / "docs.sqlite"
INDEX = CACHE / "bm25s"
QUERY_REPO = "Tevatron/browsecomp-plus"
CORPUS_REPO = "Tevatron/browsecomp-plus-corpus"
OFFICIAL = "https://raw.githubusercontent.com/texttron/BrowseComp-Plus/main"
# Lucene's EnglishAnalyzer stop set (ENGLISH_STOP_WORDS_SET), the one Pyserini's default uses.
LUCENE_STOP = (
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if", "in", "into", "is", "it",
    "no", "not", "of", "on", "or", "such", "that", "the", "their", "then", "there", "these",
    "they", "this", "to", "was", "will", "with",
)  # fmt: skip
K1, B = 0.9, 0.4  # Pyserini's BM25 defaults


@dataclass(frozen=True)
class Query:
    query_id: str
    query: str  # ciphertext (base64)
    answer: str  # ciphertext (base64)


# --- the official cipher (decrypt_dataset.py: SHA-256 of the password, repeated, XOR) ---------


def derive_key(password: str, length: int) -> bytes:
    key = hashlib.sha256(password.encode("utf-8")).digest()
    return key * (length // len(key)) + key[: length % len(key)]


def decrypt(ciphertext_b64: str, password: str) -> str:
    blob = base64.b64decode(ciphertext_b64)
    return bytes(a ^ b for a, b in zip(blob, derive_key(password, len(blob)), strict=True)).decode(
        "utf-8"
    )


def encrypt(plain: str, password: str) -> str:
    """The inverse, for tests only."""
    blob = plain.encode("utf-8")
    key = derive_key(password, len(blob))
    return base64.b64encode(bytes(a ^ b for a, b in zip(blob, key, strict=True))).decode()


def password(path: pathlib.Path = CANARY) -> str:
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: run bcp_data.py --fetch first")
    return path.read_text(encoding="utf-8").strip()


def canary_of(script: str) -> str:
    """DEFAULT_CANARY from the official decrypt_dataset.py's text."""
    found = re.search(r'^DEFAULT_CANARY\s*=\s*"([^"]+)"', script, re.M)
    if not found:
        raise ValueError("no DEFAULT_CANARY in the official decrypt script")
    return found.group(1)


# --- reading the cache --------------------------------------------------------------------------


def load(path: pathlib.Path = QUERIES) -> list[Query]:
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: run bcp_data.py --fetch first")
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [Query(**r) for r in rows]


def read_qrels(path: pathlib.Path) -> dict[str, list[str]]:
    """TREC qrels (`qid 0 docid rel`): the docids per query with rel > 0."""
    out: dict[str, list[str]] = {}
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    for line in lines:
        parts = line.split()
        if len(parts) >= 4 and int(parts[3]) > 0:
            out = {**out, parts[0]: [*out.get(parts[0], []), parts[2]]}
    return out


def summary(queries: Sequence[Query], qrels: Mapping[str, Mapping[str, list[str]]]) -> dict:
    """Counts only: never a query, an answer or a document."""
    ids = [q.query_id for q in queries]
    out = {"queries": len(ids), "unique_ids": len(set(ids))}
    for name, table in qrels.items():
        with_docs = [i for i in ids if table.get(i)]
        out[f"{name}_queries"] = len(with_docs)
        out[f"{name}_docs"] = sum(len(table[i]) for i in with_docs)
    out["docs_in_store"] = doc_count() if DOCS.exists() else 0
    out["index_built"] = (INDEX / "params.index.json").exists()
    return out


def doc_count(path: pathlib.Path = DOCS) -> int:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        return int(db.execute("SELECT COUNT(*) FROM docs").fetchone()[0])


# --- fetch and build (network / heavy: the bcp venv) --------------------------------------------


def _get(url: str) -> str:  # pragma: no cover - network
    with urllib.request.urlopen(url, timeout=60) as reply:
        return reply.read().decode("utf-8")


def fetch() -> None:  # pragma: no cover - network
    import pyarrow.parquet as pq
    from huggingface_hub import HfFileSystem, snapshot_download

    CACHE.mkdir(parents=True, exist_ok=True)
    CANARY.write_text(canary_of(_get(f"{OFFICIAL}/scripts_build_index/decrypt_dataset.py")),
                      encoding="utf-8")  # fmt: skip
    for name, rel in (("evidence", "qrel_evidence.txt"), ("gold", "qrel_golds.txt")):
        QRELS[name].write_text(_get(f"{OFFICIAL}/topics-qrels/{rel}"), encoding="utf-8")
    fs = HfFileSystem()
    rows: list[dict] = []
    for path in sorted(fs.glob(f"datasets/{QUERY_REPO}/data/*.parquet")):
        with fs.open(path, "rb") as handle:
            table = pq.read_table(handle, columns=["query_id", "query", "answer"])
        rows = [*rows, *table.to_pylist()]
    QUERIES.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    snapshot_download(CORPUS_REPO, repo_type="dataset", local_dir=CORPUS_DIR,
                      allow_patterns=["data/*.parquet"])  # fmt: skip


def corpus_batches() -> Iterable[list[dict]]:  # pragma: no cover - heavy
    import pyarrow.parquet as pq

    for path in sorted((CORPUS_DIR / "data").glob("*.parquet")):
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=2000, columns=["docid", "text", "url"]):
            yield batch.to_pylist()


def build_docs() -> int:  # pragma: no cover - heavy
    """docid -> (text, url) in SQLite, for `get` and the search snippets."""
    if DOCS.exists():
        DOCS.unlink()
    n = 0
    with sqlite3.connect(DOCS) as db:
        db.execute(
            "CREATE TABLE docs (n INTEGER PRIMARY KEY, docid TEXT UNIQUE, text TEXT, url TEXT)"
        )
        for batch in corpus_batches():
            db.executemany(
                "INSERT INTO docs (docid, text, url) VALUES (?, ?, ?)",
                [(str(r["docid"]), r["text"] or "", r["url"] or "") for r in batch],
            )
            n += len(batch)
    return n


def build_index() -> None:  # pragma: no cover - heavy
    """bm25s over the doc store, in its row order (row n-1 is document n)."""
    import bm25s
    import Stemmer

    stemmer = Stemmer.Stemmer("porter")
    tokenizer = bm25s.tokenization.Tokenizer(stopwords=list(LUCENE_STOP), stemmer=stemmer)
    with sqlite3.connect(f"file:{DOCS}?mode=ro", uri=True) as db:
        texts = (row[0] for row in db.execute("SELECT text FROM docs ORDER BY n"))
        # 4 bytes a token instead of a Python int: the corpus is ~500M words.
        corpus_ids = [array("I", ids) for ids in tokenizer.streaming_tokenize(texts)]
    tokens = bm25s.tokenization.Tokenized(ids=corpus_ids, vocab=tokenizer.get_vocab_dict())
    model = bm25s.BM25(method="lucene", k1=K1, b=B)
    model.index(tokens, show_progress=True)
    model.save(INDEX)
    tokenizer.save_vocab(INDEX)
    tokenizer.save_stopwords(INDEX)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--build", action="store_true")
    args = ap.parse_args(argv)
    if args.fetch:
        fetch()
    if args.build:
        print(f"{build_docs()} documents stored", file=sys.stderr)
        build_index()
    qrels = {name: read_qrels(path) for name, path in QRELS.items()}
    print(json.dumps(summary(load(), qrels), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
