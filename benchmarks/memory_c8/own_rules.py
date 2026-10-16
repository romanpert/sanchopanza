"""`memory_rules.is_plan` on standing rules stored from real sessions, counted only.

The input is a private file on its owner's machine (rules v8 extracted from his own sessions,
`{"projects": [{"rules": [{"text": ...}, ...]}, ...]}`): only the two counts leave this module,
never a rule's text or a project's name.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from sanchopanza.harness import memory_rules as mr  # noqa: E402


def run(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    stored = [r for project in data.get("projects") or [] for r in project.get("rules") or []]
    texts = [str(r.get("text") or "") if isinstance(r, dict) else str(r) for r in stored]
    return {"rules": len(texts), "plan_shaped": sum(1 for t in texts if mr.is_plan(t))}
