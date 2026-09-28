"""Our own evaluation harness, for the few results whose answers came from a generative model.

Those runs answered through an evaluation harness of ours that is not distributed with this
package. Their recorded answers ship in each results folder, so the published numbers replay
without it; a new live run needs it installed as the module named by
`SANCHOPANZA_EVAL_HARNESS` (default `sanchopanza_eval_harness`), exposing `ClaudeCLI`,
`SessionCache` and `CeilingReached`. Numbers answered this way are not directly comparable with
numbers obtained through the API.
"""

from __future__ import annotations

import importlib
import os
from types import ModuleType

DEFAULT_MODULE = "sanchopanza_eval_harness"


def load() -> ModuleType:
    """The harness module, or a clear exit that says what is missing and why."""
    name = os.environ.get("SANCHOPANZA_EVAL_HARNESS") or DEFAULT_MODULE
    try:
        return importlib.import_module(name)
    except ImportError as error:
        raise SystemExit(
            f"this run answers through our own evaluation harness, which is not distributed "
            f"(module `{name}` not found). The recorded answers in its results folder replay "
            "the published numbers without it."
        ) from error
