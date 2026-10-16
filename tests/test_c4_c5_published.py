"""The published C4 and C5 results replay from their recordings.

C4 (docs/results/2026-10-16-c4-written/): the 1,500 recorded answers give analysis.json again.
C5 (docs/results/2026-10-16-c5-free/): the gzipped recording has its hash; with the QASPER
validation export present (not on CI runners), the sealed setting replays analysis.json and the
squire's cap lifted replays analysis-postdata.json. No paid call.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
C4 = ROOT / "docs" / "results" / "2026-10-16-c4-written"
C5 = ROOT / "docs" / "results" / "2026-10-16-c5-free"
C4_RECORDING_SHA256 = "1c45677a70f4176919c4505a686af74391ad5329d59a47a16e258e7ffc67f144"  # LF
C5_GZ_SHA256 = "47fd32a761b699fc18a325dc9dd1306f65a091814ff511be7b36cb2f4fe4b6e0"
C5_RECORDING_SHA256 = "eb091b072b9b1674f2312e6eb9e1a98ac748514c45a6ea09e57074ffca9b9abf"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _without_head(report: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in report.items() if k != "head"}


def test_c4_replays_its_published_report() -> None:
    runner = _load("facts_written_run", ROOT / "benchmarks/facts_gate/written_run.py")
    lf = runner.FIXTURE.read_bytes().replace(b"\r\n", b"\n")  # a Windows run writes CRLF
    assert hashlib.sha256(lf).hexdigest() == C4_RECORDING_SHA256
    published = json.loads((C4 / "analysis.json").read_text(encoding="utf-8"))
    got = asyncio.run(runner.report(runner.load()))
    assert _without_head(json.loads(json.dumps(got))) == _without_head(published)
    assert published["result"]["verdict"] == "the gate beats the shipped policy"


def test_c5_ships_its_recording_gzipped() -> None:
    gz = ROOT / "fixtures" / "c5-free" / "recording.jsonl.gz"
    assert _sha(gz) == C5_GZ_SHA256
    assert hashlib.sha256(gzip.decompress(gz.read_bytes())).hexdigest() == C5_RECORDING_SHA256


def test_c5_replays_the_sealed_report_and_the_post_data_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fc = _load("free_confirm", ROOT / "benchmarks/passage_fit/free_confirm.py")
    if not fc.QASPER.exists():
        pytest.skip("the QASPER validation export is not here (free_confirm.py export)")
    plain = tmp_path / "recording.jsonl"
    plain.write_bytes(gzip.decompress((ROOT / "fixtures/c5-free/recording.jsonl.gz").read_bytes()))
    monkeypatch.setattr(fc, "FIXTURE", plain)
    sealed = json.loads((C5 / "analysis.json").read_text(encoding="utf-8"))
    post = json.loads((C5 / "analysis-postdata.json").read_text(encoding="utf-8"))
    replayed = json.loads(json.dumps(fc.analysis(fc.SEALED_SQUIRE_CAP_USD)))
    assert _without_head(replayed) == _without_head(sealed)
    lifted = json.loads(json.dumps(fc.postdata_reading(fc.analysis(fc.SQUIRE_CAP_USD))))
    assert _without_head(lifted) == _without_head(post)
    assert sealed["verdict"] == "FREE loses to page order"
    assert "verdict" not in post
    assert post["rule_applied_post_data"].startswith("FREE confirmed")
