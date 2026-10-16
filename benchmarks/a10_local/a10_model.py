"""The local check_done classifier of lot A10: a configuration, its fit, and its file.

`Config` holds every knob. `fit` builds the vocabulary and idf on the training stops only and
fits the logistic regression. `save` writes a small JSON (sorted keys, weights rounded to 6
significant digits, gzip with a zero mtime past 2 MB) so the same model gives the same bytes;
`load` reads it back, and the file's sha256 is what the seal covers.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import a10_features as features
import a10_logreg as logreg
from a10_data import Example

GZIP_ABOVE = 2_000_000


@dataclass(frozen=True)
class Config:
    families: tuple[str, ...]
    word_n: int
    c: float
    min_df: int = 2

    @property
    def name(self) -> str:
        return f"{'+'.join(self.families)}|w{self.word_n}|C={self.c:g}"


@dataclass(frozen=True)
class Model:
    config: Config
    vectorizer: features.Vectorizer
    weights: tuple[float, ...]
    intercept: float
    cut: float  # block (p(done) < cut) at this cut
    meta: dict[str, Any]

    def probabilities(self, examples: Sequence[Example]) -> list[float]:
        rows = self.vectorizer.transform_all(counts_of(examples, self.config))
        return logreg.predict(rows, self.weights, self.intercept)


def counts_of(examples: Sequence[Example], config: Config) -> list[Any]:
    return [features.tokens(e.task, e.record, config.families, config.word_n) for e in examples]


def fit(
    examples: Sequence[Example], config: Config, counts: Sequence[Any] | None = None
) -> tuple[features.Vectorizer, list[float], float, dict[str, float]]:
    counts = counts_of(examples, config) if counts is None else counts
    vec = features.Vectorizer.fit(counts, config.min_df)
    rows = vec.transform_all(counts)
    w, b, info = logreg.fit(rows, [e.done for e in examples], len(vec.terms), config.c)
    return vec, w, b, info


def _round(x: float) -> float:
    return float(f"{x:.6g}")


def to_json(model: Model) -> bytes:
    body = {
        "config": asdict(model.config),
        "cut": model.cut,
        "intercept": _round(model.intercept),
        "meta": model.meta,
        "terms": list(model.vectorizer.terms),
        "idf": [_round(x) for x in model.vectorizer.idf],
        "weights": [_round(x) for x in model.weights],
    }
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def save(model: Model, path: Path) -> Path:
    """Writes `path` (.json) or, past GZIP_ABOVE bytes, `path` + .gz; removes the other one.
    Returns the file written."""
    data = to_json(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    gz = path.with_name(path.name + ".gz")
    if len(data) > GZIP_ABOVE:
        buffer = io.BytesIO()
        with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0, compresslevel=9) as f:
            f.write(data)
        gz.write_bytes(buffer.getvalue())
        path.unlink(missing_ok=True)
        return gz
    path.write_bytes(data)
    gz.unlink(missing_ok=True)
    return path


def model_file(path: Path) -> Path:
    gz = path.with_name(path.name + ".gz")
    if path.exists():
        return path
    if gz.exists():
        return gz
    raise SystemExit(f"no model at {path} (or .gz): run train.py fit first")


def load(path: Path) -> Model:
    found = model_file(path)
    raw = found.read_bytes()
    body = json.loads(gzip.decompress(raw) if found.suffix == ".gz" else raw)
    config = Config(**{**body["config"], "families": tuple(body["config"]["families"])})
    vec = features.Vectorizer(tuple(body["terms"]), tuple(body["idf"]))
    return Model(config, vec, tuple(body["weights"]), body["intercept"], body["cut"], body["meta"])


def file_sha256(path: Path) -> str:
    return hashlib.sha256(model_file(path).read_bytes()).hexdigest()
