"""The context-pruning bench on a synthetic session. No network, nothing under ~/.claude.

Pins `docs/results/2026-09-28-context/prereg.md` and exercises the bench's pieces: the
dataset builder (admission, cut, redaction, the live-key drop), the lexical labels, the free
arms, the decider arms with a scripted decider, the metrics and the cost estimate.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import random
import string
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "context"
RESULTS = ROOT / "docs" / "results" / "2026-09-28-context"


def _load(name: str):
    key = f"context_bench_{name}"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, BENCH / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


build = _load("build")
labels_mod = _load("labels")
arms = _load("arms")
metrics = _load("metrics")
run = _load("run")
public = _load("public")

# prereg.md with Amendment 1 (public trajectories) and Amendment 2 (arrival and recall
# simulations), each written before any decider call it registers.
PREREG_SHA256 = "28bb1a3fcdbf85971bce1773b792b9659c2cd4a48fdfd87cbe675ae18d0bb98e"

N_CALLS = 80
FILLER = " ".join(["lorem ipsum dolor sit amet consectetur"] * 100)  # ~3,900 chars of prose


def _entry(role: str, content, **extra) -> dict:
    return {"type": role, "message": {"role": role, "content": content}, **extra}


def _session(secret: str = "") -> list[dict]:
    entries = [_entry("user", "Refactor the parser module.")]
    for i in range(N_CALLS):
        tid = f"toolu_{i:03d}"
        use = {"type": "tool_use", "id": tid, "name": "Read", "input": {"file_path": f"/r/m{i}.py"}}
        text = f"def unique_name_{i}():\n    shared_common_token = {i}\n{FILLER}"
        if i == 7:
            text += f"\nkey = {secret or 'sk-ant-aaaaaaaaaaaaaaaaaaaa'}"
        result = {"type": "tool_result", "tool_use_id": tid, "content": text}
        entries += [_entry("assistant", [use]), _entry("user", [result])]
        if i == 5:
            entries.append(_entry("assistant", [{"type": "text", "text": "unique_name_5 seen"}]))
            entries.append(_entry("user", "go on"))
    side = {"type": "tool_use", "id": "side", "name": "Bash", "input": {"command": "ls"}}
    entries.append(_entry("assistant", [side], isSidechain=True))
    again = {"type": "tool_use", "id": "again", "name": "Read", "input": {"file_path": "/r/m2.py"}}
    entries.append(_entry("assistant", [again]))
    entries.append(
        _entry("user", [{"type": "tool_result", "tool_use_id": "again", "content": "x" * 50}])
    )
    closing = "Done: unique_name_3 and unique_name_5 renamed; shared_common_token kept."
    entries.append(_entry("assistant", [{"type": "text", "text": closing}]))
    return entries


def _write(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")


@pytest.fixture()
def dataset(tmp_path: Path) -> dict:
    projects = tmp_path / "projects"
    _write(projects / "C--x-apps-sanchopanza" / "s1.jsonl", _session())
    _write(projects / "c--x-apps-indagis-sanchopanza" / "s2.jsonl", _session())
    rng = random.Random(1)
    live = "sk-" + "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(40))
    _write(projects / "C--x-sancho-other" / "s3.jsonl", _session(secret=live))
    out = tmp_path / "cache"
    manifest = build.build(projects, out, source="claude-code")
    units = [json.loads(p.read_text(encoding="utf-8")) for p in (out / "dataset").glob("*.json")]
    return {"manifest": manifest, "units": units, "out": out, "live": live}


# --- registration ----------------------------------------------------------------------------


def test_the_pre_registration_is_the_hashed_one():
    raw = (RESULTS / "prereg.md").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == PREREG_SHA256
    assert (RESULTS / "prereg.sha256").read_text().strip() == PREREG_SHA256
    assert run.prereg_hash() == PREREG_SHA256
    assert "## Amendment 1 (before any measurement)" in raw.decode("utf-8")
    assert "## Amendment 2 (before any measurement)" in raw.decode("utf-8")


# --- public source ---------------------------------------------------------------------------


def _openhands_row() -> dict:
    def call(i: int, name: str, args: dict) -> dict:
        return {
            "id": f"c{i}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        }

    trajectory = [
        {"role": "system", "content": "scaffold prompt", "tool_calls": None},
        {"role": "user", "content": "Fix the issue.", "tool_calls": None},
    ]
    for i in range(60):
        if i % 4 == 0:
            name, args = "execute_bash", {"command": f"grep -rn thing_{i} ."}
        elif i % 4 == 1:
            name, args = (
                "str_replace_editor",
                {"command": "view", "path": f"/w/m{i}.py", "view_range": [10, 29]},
            )
        elif i % 4 == 2:
            name, args = (
                "str_replace_editor",
                {"command": "str_replace", "path": f"/w/m{i}.py", "old_str": "a", "new_str": "b"},
            )
        else:
            name, args = "think", {"thought": "hmm"}
        trajectory.append({"role": "assistant", "content": "", "tool_calls": [call(i, name, args)]})
        body = f"value_{i}_marker " + FILLER
        trajectory.append({"role": "tool", "content": body, "tool_call_id": f"c{i}"})
    trajectory.append({"role": "tool", "content": "orphan", "tool_call_id": "nobody"})
    trajectory.append({"role": "assistant", "content": "Used value_5_marker.", "tool_calls": None})
    return {"trajectory_id": "t-1", "trajectory": trajectory}


def test_public_mapping_to_claude_code_tools():
    messages = public.to_messages(_openhands_row()["trajectory"])
    assert messages[0]["role"] == "user"  # the system message is dropped
    found = run.calls_of(messages)
    assert len(found) == 60  # the orphan tool message is dropped
    tools = {c.tool for c in found}
    assert tools == {"Bash", "Read", "Edit", "think"}
    read = next(c for c in found if c.tool == "Read")
    assert read.input == {"file_path": "/w/m1.py", "offset": 10, "limit": 20}
    assert public.map_call(
        "str_replace_editor", {"command": "create", "path": "/a", "file_text": "x"}
    ) == ("Write", {"file_path": "/a", "content": "x"})
    roles = [m["role"] for m in messages]
    assert all(a != b for a, b in zip(roles, roles[1:], strict=False))


def test_public_rows_become_units(tmp_path: Path):
    page = {"rows": [{"row": _openhands_row()}]}
    (tmp_path / "rows-000000.json").write_text(json.dumps(page), encoding="utf-8")
    manifest = build.build(tmp_path, tmp_path / "cache")
    assert manifest["source"] == "public"
    assert manifest["dataset"]["license"] == "CC-BY-4.0"
    assert len(manifest["units"]) == 1


def test_page_offsets_are_seeded_and_capped(tmp_path: Path):
    offsets = public.page_offsets()
    assert offsets == public.page_offsets() and len(offsets) == public.MAX_ROWS // public.PAGE
    assert len(set(offsets)) == len(offsets) and max(offsets) < public.TOTAL_ROWS
    with pytest.raises(ValueError):
        public.fetch(tmp_path / "never", n_rows=public.MAX_ROWS + 1)
    assert not (tmp_path / "never").exists()


# --- dataset ---------------------------------------------------------------------------------


def test_admission_is_by_public_name_and_private_words_win():
    assert build.project_admitted("C--Users-x-apps-sanchopanza")
    assert not build.project_admitted("c--Users-x-apps-indagis-sanchopanza")
    assert not build.project_admitted("C--Users-x-farmacia")


def test_build_keeps_one_unit_drops_the_live_key_and_redacts(dataset):
    stats = dataset["manifest"]["stats"]
    assert stats["projects_excluded"] == 1
    assert stats["sessions_dropped_live_key"] == 1
    assert len(dataset["units"]) == 1
    stored = json.dumps(dataset["units"][0])
    assert "sk-ant-aaaa" not in stored and "[secret]" in stored
    assert dataset["live"] not in stored
    assert '"side"' not in stored  # the sidechain call is not in the history or the future


def test_the_cut_reaches_sixty_percent_and_keeps_pairs(dataset):
    unit = dataset["units"][0]
    history, future = unit["history"], unit["future"]
    total = sum(build.size(m) for m in history + future)
    assert sum(build.size(m) for m in history) >= 0.6 * total
    assert history[-1]["role"] == "user"
    assert len(unit["labels"]) >= build.MIN_RESULTS


def test_the_split_puts_whole_sessions_on_one_side():
    units = [{"unit": f"u{i}", "session": f"s{i // 2}"} for i in range(10)]
    sides = build.split(units)
    for i in range(0, 10, 2):
        assert sides[f"u{i}"] == sides[f"u{i + 1}"]
    assert set(sides.values()) == {"dev", "test"}


# --- labels ----------------------------------------------------------------------------------


def test_labels_needed_outside_text_stoplist_and_reread(dataset):
    lab = dataset["units"][0]["labels"]
    assert lab["toolu_003"]["needed"]
    assert "unique_name_3" in lab["toolu_003"]["tokens"]
    assert not lab["toolu_005"]["needed"]  # named in the history's own text
    assert not lab["toolu_004"]["needed"]
    assert all("shared_common_token" not in v["tokens"] for v in lab.values())  # stop token
    assert lab["toolu_002"]["reread"] and not lab["toolu_003"]["reread"]


def test_tokens_are_code_shaped_not_prose():
    found = labels_mod.tokens("the parser because Function snake_case camelCase CONSTANT 12345")
    assert {"snake_case", "camelCase", "CONSTANT", "12345"} <= found
    assert not {"parser", "because", "Function"} & found


def test_needed_before_refetch_drops_a_token_shown_again_first():
    history = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "a", "name": "Read", "input": {"file_path": "/f.py"}}
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": "def load_config_v2(): pass"}
            ],
        },
    ]
    future = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "b", "name": "Read", "input": {"file_path": "/f.py"}}
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "b", "content": "def load_config_v2(): pass"}
            ],
        },
        {"role": "assistant", "content": [{"type": "text", "text": "call load_config_v2"}]},
    ]
    calls = run.calls_of(history)
    got = labels_mod.label(history, future, calls)["a"]
    assert got["needed"] and not got["needed_before_refetch"] and got["reread"]


# --- arms ------------------------------------------------------------------------------------


def _unit_calls(dataset):
    unit = dataset["units"][0]
    return unit, run.calls_of(unit["history"])


def test_free_arms(dataset):
    unit, calls = _unit_calls(dataset)
    assert set(arms.keep_all(calls).values()) == {"keep"}
    last = arms.last_n(calls)
    assert [cid for cid, a in last.items() if a == "keep"] == [c.id for c in calls[-3:]]
    masked = arms.mask(unit["history"], calls)
    assert sum(a == "keep" for a in masked.values()) == 10
    assert masked[calls[-1].id] == "keep" and masked[calls[0].id] == "stub"


def test_rules_and_decider_arms_run_free_end_to_end(dataset):
    unit, calls = _unit_calls(dataset)
    squire = arms.squire_for(arms.FakeDecider(), max_usd=0.01)
    for arm in ("rules", "fastjev", "sanchopanza"):
        result = asyncio.run(arms.run_arm(arm, unit["history"], calls, squire))
        assert set(result.actions) == {c.id for c in calls}
        assert set(result.actions.values()) <= {"keep", "stub", "truncate", "drop"}
    assert squire.meter.cost_usd == 0.0
    sp = asyncio.run(arms.run_arm("sanchopanza", unit["history"], calls, squire))
    kept = [sum(a == "keep" for a in arms.at_cut(sp, c).values()) for c in (0.0, 0.5, 1.0)]
    assert kept == sorted(kept, reverse=True)


def test_null_decider_keeps_what_the_rules_leave(dataset):
    unit, calls = _unit_calls(dataset)
    null = arms.squire_for(None, max_usd=0.0)
    sp = asyncio.run(arms.run_arm("sanchopanza", unit["history"], calls, null))
    rules = asyncio.run(arms.run_arm("rules", unit["history"], calls))
    assert arms.at_cut(sp, 0.5) == dict(rules.actions)


# --- metrics ---------------------------------------------------------------------------------


def test_unit_metrics_and_recoverable(dataset):
    unit, calls = _unit_calls(dataset)
    stub_all = {c.id: "stub" for c in calls}
    got = metrics.unit_metrics(unit["labels"], calls, stub_all, archives=True)
    assert got["freed"] == 1.0 and got["recall"] == 0.0
    assert got["recoverable"] == got["needed"] > 0
    kept = metrics.unit_metrics(unit["labels"], calls, arms.keep_all(calls), archives=False)
    assert kept["freed"] == 0.0 and kept["recall"] == 1.0 and kept["needed_chars_lost"] == 0


def test_pooled_bootstrap_and_mcnemar():
    rows = [
        {
            "chars": 100,
            "freed_chars": 50,
            "freed": 0.5,
            "needed": 2,
            "needed_kept": 1,
            "recall": 0.5,
            "needed_chars_lost": 10,
            "recoverable": 0,
        },
        {
            "chars": 300,
            "freed_chars": 0,
            "freed": 0.0,
            "needed": 2,
            "needed_kept": 2,
            "recall": 1.0,
            "needed_chars_lost": 0,
            "recoverable": 0,
        },
    ]
    p = metrics.pooled(rows)
    assert p["freed"] == 0.125 and p["recall"] == 0.75
    assert metrics.bootstrap(rows, "recall") == metrics.bootstrap(rows, "recall")
    assert metrics.mcnemar(0, 0) == 1.0
    assert metrics.mcnemar(0, 10) < 0.01


def test_analysis_and_estimate_on_the_synthetic_unit(dataset):
    units = [dict(dataset["units"][0], split=s) for s in ("dev", "test")]
    squires = {a: arms.squire_for(arms.FakeDecider(), max_usd=0.01) for a in arms.DECIDER_ARMS}
    rows = asyncio.run(run.run_units(units, arms.ARMS, squires))
    derived = run.derive_cut([r for r in rows if r["unit"]["split"] == "dev"])
    assert derived["cut"] in run.CUTS
    report = run.analyze(rows, arms.ARMS, derived["cut"])
    assert set(report["splits"]["test"]) == set(arms.ARMS)
    assert "sanchopanza_vs_fastjev" in report["test_comparisons"]
    est = run.estimate(units)
    assert est["arms"]["sanchopanza"]["calls"] >= 1
    assert 0 < est["arms"]["fastjev"]["usd"] < 0.01


# --- counted decider calls: no silent loss ----------------------------------------------------


class _Boom:
    name = "boom"

    async def decide(self, point, state, questions):
        raise RuntimeError("provider down")


def test_a_failed_call_is_counted_and_the_run_marked_incomplete():
    counter = arms.CountingDecider(_Boom())
    squire = arms.squire_for(counter, max_usd=0.01)
    from sanchopanza.points import chunks

    state, qs = chunks.context_questions(purpose="p", pages=[("a", "x"), ("b", "y")])
    decision = asyncio.run(squire.decide("triage_pages", state, qs))
    assert decision.failed  # the squire fails open, silently for the caller
    assert counter.errors == 1 and not counter.complete  # the bench does not


def test_calls_across_two_event_loops_mark_the_run_incomplete():
    """The ReplayFirst loss: a decider reused by a second asyncio.run. Caught, not trusted."""
    counter = arms.CountingDecider(arms.FakeDecider())
    squire = arms.squire_for(counter, max_usd=0.01)
    from sanchopanza.points import chunks

    state, qs = chunks.context_questions(purpose="p", pages=[("a", "x"), ("b", "y")])
    asyncio.run(squire.decide("triage_pages", state, qs))
    assert counter.complete
    asyncio.run(squire.decide("triage_pages", state, qs))
    assert counter.loops == 2 and not counter.complete


def test_the_runners_use_one_event_loop():
    for name in ("run.py", "simulate.py"):
        source = (BENCH / name).read_text(encoding="utf-8")
        assert source.count("asyncio.run(") == 1, name


# --- arrival baselines and criteria -----------------------------------------------------------


def test_baselines_respect_the_budget_and_keep_order():
    from sanchopanza.context.transcript import Call

    text = "".join(f"line {i} alpha_{i}\n" for i in range(400))
    call = Call(id="c", tool="Bash", input={"command": "x"}, result=text)
    got = _load("baselines").all_of(call, "alpha_7", 2_000, seed="s")
    assert set(got) == {"head_tail", "bm25", "random"}
    assert all(len(v) <= 2_000 for v in got.values())
    assert got["head_tail"].startswith("line 0 ") and got["head_tail"].endswith("alpha_399\n")
    assert "alpha_7\n" in got["bm25"]
    assert (
        got["random"]
        and got["random"] in text
        or all(line in text for line in got["random"].splitlines())
    )
    assert _load("baselines").all_of(call, "q", len(text), seed="s")["random"] == text


def _row(unit, split, needed, tokens, kept, cut=True, chars=10_000, shown=4_000):
    return {
        "unit": unit,
        "split": split,
        "eligible": True,
        "cut": cut,
        "needed": needed,
        "chars": chars,
        "shown": shown,
        "budget": shown - 300,
        "tokens": tokens,
        "arrival_tokens_kept": kept["arrival"],
        "head_tail_tokens_kept": kept["head_tail"],
        "bm25_tokens_kept": kept["bm25"],
        "random_tokens_kept": kept["random"],
    }


def test_arrival_criteria_on_hand_made_rows():
    good = {"arrival": 2, "head_tail": 0, "bm25": 1, "random": 0}
    rows = [_row(f"u{i}", "test", True, 2, good) for i in range(12)]
    verdict = _load("criteria").judge("arrival", rows)["test_verdicts"]
    assert verdict["A1"]["pass"] and verdict["A3"]["pass"]
    assert verdict["A2"]["pass"]  # 1 - (4,000 + 80) / 10,000 = 0.59


def test_recall_leakage_invalidates_r1():
    arm = {
        "needed_masked": 2,
        "hits": 2,
        "literal_hits": 2,
        "injected": 2,
        "injected_chars": 10,
        "leak_prompt": 0,
        "leak_assistant": 0,
    }
    weak = {**arm, "hits": 0, "injected_chars": 20}
    rows = [
        {"unit": f"u{i}", "split": "test", "arms": {"jev": arm, "bm25@1": weak, "bm25@3": weak}}
        for i in range(10)
    ]
    judged = _load("criteria").judge("recall", rows)
    assert judged["valid"] and judged["test_verdicts"]["R1"]["pass"]
    leaky = [{**r, "arms": {**r["arms"], "jev": {**arm, "leak_prompt": 1}}} for r in rows]
    judged = _load("criteria").judge("recall", leaky)
    assert not judged["valid"] and not judged["test_verdicts"]["R1"]["pass"]
