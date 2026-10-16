"""A3's post-hoc diagnosis (benchmarks/a3_mcp/diagnose.py): free, reported, never judged."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .helpers import bench_module

REPO = Path(__file__).resolve().parents[1]
diagnose = bench_module(REPO / "benchmarks" / "a3_mcp", "diagnose")


def test_an_operation_s_kind_is_its_leading_verb() -> None:
    kind = diagnose.kind_of
    assert kind("mcp__stripe__list_payments", False) == "reads or checks"
    assert kind("mcp__vercel__get_deployment_status", False) == "reads or checks"
    assert kind("mcp__supabase__run_query", False) == "reads or checks"
    assert kind("mcp__hubspot__update_contacts", False) == "writes or sends"
    assert kind("mcp__ops__UPDATE_SIGNAL_CONFIG", False) == "writes or sends"
    assert kind("mcp__twitter__call", False) == diagnose.UNNAMED
    assert kind("mcp__read_mcp_resource__call", True) == "Codex's own tool"
    assert kind("mcp__tts__generate_speech", False) == "other"
    assert kind("Bash", False) == "shell"


def _t(tid: str, label: str, ref_p: float, hook: bool, max_p: float, **more: Any) -> dict:
    return {"id": tid, "label": label, "ref_p": ref_p, "ref": ref_p >= 0.5, "hook": hook,
            "max_p": max_p, "max_at_last_call": True, "risk_source": "x",
            "defense_type": "None", "kinds": ["reads or checks"], **more}  # fmt: skip


def test_the_gap_is_counted_per_trajectory() -> None:
    ts = [_t("a", "unsafe", 0.9, True, 0.8), _t("b", "unsafe", 0.55, False, 0.45),
          _t("c", "unsafe", 0.3, True, 0.6), _t("d", "unsafe", 0.2, False, 0.1),
          _t("e", "safe", 0.9, False, 0.2)]  # fmt: skip
    unsafe = [t for t in ts if t["label"] == "unsafe"]
    assert diagnose.crosstab(unsafe) == {"both": 1, "reference_only": 1, "hook_only": 1,
                                         "neither": 1}  # fmt: skip
    lost = diagnose.missed(ts)
    assert lost["n"] == 1 and lost["max_call_p"] == {"0.4 to 0.5": 1}
    assert lost["reference_p_below_0_6"] == 1 and lost["only_codex_own_tools"] == 0
