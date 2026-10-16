"""The B6 result, replayed from `fixtures/b6-es.jsonl.gz`. No network, no paid call.

The recordings ship gzipped and are decompressed here into a temporary folder: the sealed
runner reads plain JSON lines. Needs the bench built by `benchmarks/b6_es/b6_build.py` (not
redistributed) in SANCHOPANZA_B6_DATA or ~/.cache/sanchopanza/b6-es, matching the manifest, or
skips. Pins `docs/results/2026-10-16-b6-es/README.md`.
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKED = ROOT / "fixtures" / "b6-es.jsonl.gz"
PACKED_SHA256 = "a2d0156d9ba05aa8834ce164bae7834790131efda965d9a1544673e1879e13b7"
PLAIN_SHA256 = "e200d7f2432045bfb928e0bb9289dd94fa2ccc4d6bb868108c3a9ac921da0e4c"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "benchmarks/b6_es" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run = _load("b6_run")


def _built() -> bool:
    manifest = json.loads((run.OUT / "bench-manifest.json").read_text(encoding="utf-8"))
    for name in ("pages", "docs"):
        path = run.bb.DEFAULT_DATA / f"{name}.jsonl"
        if not path.exists() or run.bb.sha256_of(path) != manifest[name]["sha256"]:
            return False
    return True


def test_the_packed_recordings_are_the_ones_the_readme_names():
    if not PACKED.exists():
        pytest.skip("fixtures/b6-es.jsonl.gz is not here")
    packed = PACKED.read_bytes()
    assert hashlib.sha256(packed).hexdigest() == PACKED_SHA256
    assert hashlib.sha256(gzip.decompress(packed)).hexdigest() == PLAIN_SHA256


@pytest.fixture
def replayed(tmp_path, monkeypatch):
    if not PACKED.exists() or not _built():
        pytest.skip("the B6 bench is not built here, or its recordings are absent")
    plain = tmp_path / "b6-es.jsonl"
    plain.write_bytes(gzip.decompress(PACKED.read_bytes()))
    manifest = (run.OUT / "bench-manifest.json").read_bytes()
    (tmp_path / "bench-manifest.json").write_bytes(manifest)  # read from OUT; written there too
    monkeypatch.setattr(run, "FIXTURE", plain)
    monkeypatch.setattr(run, "OUT", tmp_path)
    monkeypatch.setattr(run, "RUN_DIR", tmp_path / "run")

    def one(bench: str) -> dict:
        assert run.run(run.bb.DEFAULT_DATA, bench, live=False, smoke=False) == 0
        return json.loads((tmp_path / f"analysis-{bench}.json").read_text(encoding="utf-8"))

    return one


def test_the_pages_result_replays(replayed):
    report = replayed("pages")
    h1 = report["H1_pages_es_vs_en"]
    assert (h1["n"], h1["a"], h1["b"], h1["ci95"]) == (264, 0.9545, 0.9886, [-0.0606, -0.0076])
    assert (h1["verdict"], h1["only_a"], h1["only_b"]) == ("inconclusive", 2, 11)
    assert report["C1_consumer_cut_900"]["difference"] == -0.03
    assert report["bm25_at_same_text"] == {"es": 0.61, "en": 0.7067}


def test_the_docs_result_replays(replayed):
    report = replayed("docs")
    h2 = report["H2_docs_es_vs_en"]
    assert (h2["n"], h2["a"], h2["b"], h2["ci95"]) == (614, 0.8583, 0.9169, [-0.0896, -0.0293])
    assert (h2["verdict"], h2["only_a"], h2["only_b"]) == ("inconclusive", 26, 62)
    assert h2["text"]["within_margin"] is True
    c2 = report["C2_bm25_90_descriptive"]
    assert (c2["n"], c2["difference"]) == (86, -0.0116)
    assert c2["preselection_keeps_gold_paragraph_all_built"]["rate"] == 0.9767
    assert report["sensitivity_both_exact"]["difference"] == -0.0524
