"""P1, P2 and P9 against Sonnet 5 through the Claude Code CLI, pinned. No network.

`docs/results/2026-09-28-cascade-sonnet/README.md` reports it.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "results" / "2026-09-28-cascade-sonnet"


def test_the_amendment_is_the_hashed_one():
    raw = (OUT / "prereg-cli.md").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == (OUT / "prereg-cli.sha256").read_text().strip()


def test_the_registered_verdicts():
    a = json.loads((OUT / "analysis.json").read_text(encoding="utf-8"))
    assert (a["P1_rjudge"], a["P2_register"], a["P9_codex"]) == (False, True, True)
    assert a["verdict_P1_P2"] == "partial"
    held = {name: e["cascade"]["held_out"] for name, e in a["sets"].items()}
    taus = {name: e["cascade"]["tau"] for name, e in a["sets"].items()}
    assert taus == {"rjudge": 0.8, "register": 0.9, "codex": 0.0}
    assert (held["rjudge"]["cascade_acc"], held["rjudge"]["alone_acc"]) == (0.9234, 0.9234)
    assert held["rjudge"]["cost_ratio"] == 0.5766
    assert (held["register"]["cascade_acc"], held["register"]["cost_ratio"]) == (0.814, 0.4596)
    assert (held["codex"]["cascade_acc"], held["codex"]["alone_acc"]) == (0.7851, 0.7893)
    robust = a["sets"]["rjudge"]["cascade"]["robustness_500_splits"]["cost_ratio_p50_p95"]
    assert robust == [0.4766, 0.5469]
