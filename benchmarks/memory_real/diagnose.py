"""Where the decider's probabilities fall for related and unrelated records (development). Free:
reads the cached answers of score.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))

from score import _answers, _key, load_items  # noqa: E402

from sanchopanza.harness import memory_hook as mh  # noqa: E402


def auc(pos: list[float], neg: list[float]) -> float | None:
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 3)


def main() -> None:
    cached = _answers()
    rows = []
    for item in load_items("dev"):
        found = mh.candidates(item["request"], item["pool"], mh.K)
        probs = cached.get(_key(item["request"], [e.key for e in found]))
        if not probs:
            continue
        short = len(item["request"]) < 40
        for e in found:
            p = probs.get(e.key)
            if p is not None:
                rows.append((p, item["labels"][e.key], short, item["request"][:60]))
    for name, keep in (("all", lambda r: True), ("short prompt", lambda r: r[2]),
                       ("long prompt", lambda r: not r[2])):  # fmt: skip
        sub = [r for r in rows if keep(r)]
        pos = [r[0] for r in sub if r[1] != "none"]
        lin = [r[0] for r in sub if r[1] == "lineage"]
        neg = [r[0] for r in sub if r[1] == "none"]
        print(f"{name}: {len(sub)} judged, related {len(pos)}, AUC any {auc(pos, neg)}, "
              f"AUC lineage {auc(lin, neg)}")
        for cut in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7):
            kept = [r for r in sub if r[0] >= cut]
            good = sum(r[1] != "none" for r in kept)
            print(f"  >= {cut}: kept {len(kept)}, related {good}, "
                  f"precision {good / len(kept):.3f}" if kept else f"  >= {cut}: none")
    top = sorted((r for r in rows if r[1] == "none"), key=lambda r: -r[0])[:12]
    print("highest unrelated:", json.dumps([(round(r[0], 2), r[3]) for r in top],
                                           ensure_ascii=False))  # fmt: skip


if __name__ == "__main__":
    main()
