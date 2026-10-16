"""Lot A10: the local check_done classifier on checkdone114's 950 unseen stops. Free, no model
call, and it scores nothing on the test set unless the registration is sealed.

    python benchmarks/a10_local/eval.py hash                       # the digest a seal must hold
    python benchmarks/a10_local/eval.py overlap [--runs-root P]    # train/test overlap; no scoring
    python benchmarks/a10_local/eval.py seal                       # prereg.sha256: after review
    python benchmarks/a10_local/eval.py run [--data-root P]        # refuses unless sealed

Registered in docs/results/2026-10-16-a10-local/prereg.md.

THE SEAL is one sha256 over `SEALED` (LF-folded text) and the model file's bytes: the
registration, the CV report that fixed every knob, the model, this lot's code, the record builder
and loaders the stops go through, the statistics, and checkdone114's inputs, data seal and
recorded Jev rows. `run` checks it before reading a single test stop, then checks the 950 stops
against checkdone114's sealed `data.sha256`, then scores. `seal` is the owner's step, once the
registration is reviewed (`revisor-prereg`) and committed; scoring runs from a worktree detached
at the sealing commit.

Jev's recorded probabilities (checkdone114's `done-scored.jsonl`) are read only to score Jev's
own decisions at its cuts; they never reach the classifier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import a10_analysis as analysis  # noqa: E402
import a10_data as data  # noqa: E402
import a10_model as model  # noqa: E402

ROOT = data.ROOT
OUT = ROOT / "docs" / "results" / "2026-10-16-a10-local"
SEAL = OUT / "prereg.sha256"
MODEL = ROOT / "fixtures" / "a10_local" / "model.json"
CHECKDONE = ROOT / "docs" / "results" / "2026-10-16-checkdone114"
CD_ROWS = CHECKDONE / "done-scored.jsonl"
CD_DATA = CHECKDONE / "data.sha256"
EXPECTED_TEST = 950

SEALED = (
    "docs/results/2026-10-16-a10-local/prereg.md",
    "docs/results/2026-10-16-a10-local/cv.json",
    "benchmarks/a10_local/a10_analysis.py",
    "benchmarks/a10_local/a10_data.py",
    "benchmarks/a10_local/a10_features.py",
    "benchmarks/a10_local/a10_logreg.py",
    "benchmarks/a10_local/a10_model.py",
    "benchmarks/a10_local/eval.py",
    "benchmarks/a10_local/train.py",
    "benchmarks/completion/run.py",
    "benchmarks/jev114/checkdone114.py",
    "benchmarks/jev114/l4_stats.py",
    "benchmarks/jev114/lot_stats.py",
    "benchmarks/thresholds.py",
    "src/sanchopanza/points/completion.py",
    "src/sanchopanza/points/done_evidence.py",
    "src/sanchopanza/text.py",
    "src/sanchopanza/eval/stats.py",
    "docs/results/2026-10-16-checkdone114/inputs.jsonl",
    "docs/results/2026-10-16-checkdone114/data.sha256",
    "docs/results/2026-10-16-checkdone114/done-scored.jsonl",
)


def digest(root: Path = ROOT, model_path: Path = MODEL) -> str:
    h = hashlib.sha256()
    for rel in SEALED:
        path = root / rel
        if not path.exists():
            raise SystemExit(f"sealed file missing: {rel}")
        h.update(rel.encode() + b"\0" + path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    found = model.model_file(model_path)
    h.update(found.name.encode() + b"\0" + found.read_bytes())
    return h.hexdigest()


def require_seal(root: Path = ROOT, seal: Path = SEAL, model_path: Path = MODEL) -> str:
    """The registered digest, or SystemExit before any test stop is read."""
    if not seal.exists():
        raise SystemExit(f"not sealed ({seal.name} missing): nothing scored on the test set")
    registered = seal.read_text(encoding="utf-8").strip()
    now = digest(root, model_path)
    if registered != now:
        raise SystemExit(
            f"the seal does not match ({registered[:12]}... sealed, {now[:12]}... now): "
            "a sealed file changed; nothing scored on the test set"
        )
    return now


def cmd_hash(_: argparse.Namespace) -> int:
    print(digest())
    return 0


def cmd_seal(_: argparse.Namespace) -> int:
    if SEAL.exists():
        raise SystemExit(f"{SEAL.name} exists: a lot is sealed once")
    SEAL.write_text(digest() + "\n", encoding="utf-8")
    print(SEAL.read_text(encoding="utf-8").strip())
    return 0


def cmd_overlap(args: argparse.Namespace) -> int:
    """What the training and test stops share. Reads both sets' text; scores nothing."""
    train = data.load_train(args.runs_root)
    test, _ = data.load_test(args.data_root)
    report = data.overlap(train, test)
    (OUT / "overlap.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


def jev_rows() -> dict[str, dict]:
    rows = [json.loads(x) for x in CD_ROWS.read_text(encoding="utf-8").splitlines() if x.strip()]
    return {r["id"]: r for r in rows}


def cmd_run(args: argparse.Namespace) -> int:
    sealed = require_seal()
    fitted = model.load(MODEL)
    examples, inputs = data.load_test(args.data_root)
    if inputs != json.loads(CD_DATA.read_text(encoding="utf-8"))["done"]:
        raise SystemExit("the test stops differ from checkdone114's sealed inputs")
    if len(examples) != EXPECTED_TEST:
        raise SystemExit(f"{len(examples)} test stops, registered {EXPECTED_TEST}")
    jev = jev_rows()
    p = fitted.probabilities(examples)
    rows = []
    for e, x in zip(examples, p, strict=True):
        j = jev[e.id]
        if j["label"] != ("done" if e.done else "not_done"):
            raise SystemExit(f"label differs from checkdone114's row: {e.id}")
        rows.append({"id": e.id, "cluster": e.cluster, "label": j["label"],
                     "p_local": round(x, 6), "p_14": j["p_14"], "p_13r": j["p_13r"]})  # fmt: skip
    report = {"prereg_sha256": sealed, "model_sha256": model.file_sha256(MODEL),
              **analysis.analyse(rows, fitted.cut)}  # fmt: skip
    keep = ("id", "cluster", "label", "p_local")
    (OUT / "scored.jsonl").write_text(
        "".join(json.dumps({k: r[k] for k in keep}) + "\n" for r in rows), encoding="utf-8"
    )
    (OUT / "analysis.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("n", "cuts", "verdict")}, indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in (("hash", cmd_hash), ("seal", cmd_seal), ("overlap", cmd_overlap),
                     ("run", cmd_run)):  # fmt: skip
        p = sub.add_parser(name)
        p.add_argument("--data-root", type=Path, default=None)
        p.add_argument("--runs-root", type=Path, default=None)
        p.set_defaults(fn=fn)
    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
