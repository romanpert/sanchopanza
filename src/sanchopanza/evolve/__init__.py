"""An evolution interface: what a self-improving harness may tune in the squire, and how.

Built for outer loops in the style of RRSI (Regularized Recursive Self-Improvement of Agent
Harnesses, arXiv 2609.24972): a proposer edits a configuration, candidates are scored on an
evolution set, and the incumbent is replaced only by an ADMISSIBLE candidate. This package
supplies the pieces and encodes this repository's method rules in them; it does not supply a
proposer. See `docs/evolve.md`.

    from sanchopanza.evolve import Evaluator, Knobs, Ledger, Split, admit, edit_budget

Everything here replays recordings and costs nothing, except an explicit live decider.
"""

from .critics import DormantGate, LeakCheck, dormant_gates, leak_check
from .evaluator import (
    RUNNER_FIXED,
    Evaluator,
    FreshSplitSpent,
    QuestionOverrides,
    RecordingInvalidated,
    RecordingMiss,
    Score,
    UnexercisedEdit,
)
from .knobs import Edit, Knobs, diff, edits_hash
from .ledger import Ledger, LedgerEntry
from .regularizers import (
    Admission,
    NoiseFloor,
    admit,
    drift_magnitude,
    edit_budget,
    noise_floor,
)
from .split import Split

__all__ = [
    "RUNNER_FIXED",
    "Admission",
    "DormantGate",
    "Edit",
    "Evaluator",
    "FreshSplitSpent",
    "Knobs",
    "LeakCheck",
    "Ledger",
    "LedgerEntry",
    "NoiseFloor",
    "QuestionOverrides",
    "RecordingInvalidated",
    "RecordingMiss",
    "Score",
    "Split",
    "UnexercisedEdit",
    "admit",
    "diff",
    "dormant_gates",
    "drift_magnitude",
    "edit_budget",
    "edits_hash",
    "leak_check",
    "noise_floor",
]
