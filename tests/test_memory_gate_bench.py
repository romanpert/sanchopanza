"""The memory-gate benchmark: pre-registration pinned, labels and metrics on synthetic
transcripts. No network, no real transcripts."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks" / "memory_gate"))

import labels  # noqa: E402
import run  # noqa: E402

from sanchopanza import Decision  # noqa: E402
from sanchopanza.harness import memory_gate as mg  # noqa: E402
from sanchopanza.points import chunks  # noqa: E402

from .helpers import yes  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-28-memory-gate"
PROJECT = "C--p-demo"
MEM = f"C:\\Users\\u\\.claude\\projects\\{PROJECT}\\memory\\"


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_the_pre_registration_is_the_one_hashed_before_the_run():
    expected = (RESULTS / "prereg.sha256").read_text(encoding="utf-8").strip()
    assert _sha(RESULTS / "prereg.md") == expected == run.prereg_hash()


def test_the_cache_is_outside_the_repository():
    assert ROOT not in run.CACHE.parents
    assert pathlib.Path.home() / ".cache" / "sanchopanza" / "memory_gate" == run.CACHE


# --- labels -----------------------------------------------------------------------------


def user(text, ts="2026-09-10T10:00:00Z", **extra):
    return {"type": "user", "timestamp": ts, "message": {"content": text}, **extra}


def assistant(*blocks, ts="2026-09-10T10:00:01Z", **extra):
    return {"type": "assistant", "timestamp": ts, "message": {"content": list(blocks)}, **extra}


def text(t):
    return {"type": "text", "text": t}


def tool(name, **args):
    return {"type": "tool_use", "name": name, "input": args}


def result(t):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "content": t}]}}


BORN = {"a.md": 1.0, "b.md": 1.0, "late.md": 2e12}
TOKENS = {"a.md": {"deploy_alpha.sh"}, "b.md": {"svc-beta-9"}, "late.md": {"late_token_1"}}


def cases(rows):
    return list(
        labels.cases_of_session(rows, project=PROJECT, session="s", born=BORN, tokens=TOKENS)
    )


def test_first_level_prompts_only():
    rows = [
        user("<command-name>/clear</command-name>"),
        user("real prompt"),
        result("tool output"),
        user("meta", isMeta=True),
        user("[Request interrupted by user]"),
        user("\n\n<pasted_content id='x'>kept</pasted_content>"),
    ]
    assert [c.prompt for c in cases(rows)] == [
        "real prompt",
        "<pasted_content id='x'>kept</pasted_content>",
    ]


def test_a_read_labels_and_a_write_does_not():
    rows = [
        user("go"),
        assistant(tool("Read", file_path=MEM + "a.md"), tool("Write", file_path=MEM + "b.md")),
    ]
    (case,) = cases(rows)
    assert case.read == ("a.md",) and case.written == ("b.md",)
    assert case.relevant == ("a.md",)


def test_a_quoted_token_labels_unless_it_was_seen_before():
    rows = [user("go"), assistant(text("run deploy_alpha.sh now"))]
    assert cases(rows)[0].relevant == ("a.md",)
    # a tool result before the prompt is part of the history
    rows = [
        user("first"),
        result("deploy_alpha.sh"),
        user("go"),
        assistant(text("deploy_alpha.sh")),
    ]
    assert cases(rows)[1].relevant == ()
    rows = [
        user("go"),
        assistant(tool("Bash", command="ls")),
        result("deploy_alpha.sh"),
        assistant(text("deploy_alpha.sh")),
    ]
    assert cases(rows)[0].relevant == ()


def test_the_prompt_and_the_environment_are_not_evidence():
    assert cases([user("use svc-beta-9"), assistant(text("svc-beta-9"))])[0].relevant == ()
    rows = [user("go", gitBranch="svc-beta-9"), assistant(text("on svc-beta-9"))]
    assert cases(rows)[0].relevant == ()


def test_a_memory_not_yet_born_is_not_a_candidate():
    rows = [user("go"), assistant(text("late_token_1"))]
    (case,) = cases(rows)
    assert "late.md" not in case.available and case.relevant == ()


def test_the_window_is_bounded():
    filler = [assistant(text("nothing")) for _ in range(labels.WINDOW)]
    rows = [user("go"), *filler, assistant(text("deploy_alpha.sh"))]
    assert cases(rows)[0].relevant == ()


def test_memory_paths_match_any_slash_and_case():
    assert labels.memory_file_of(MEM.lower() + "a.md", PROJECT) == "a.md"
    assert labels.memory_file_of(MEM.replace("\\", "/") + "a.md", PROJECT) == "a.md"
    assert labels.memory_file_of(MEM + "MEMORY.md", PROJECT) is None
    assert labels.memory_file_of("C:/elsewhere/memory/a.md", PROJECT) is None


def test_distinctive_tokens_are_identifier_shaped():
    got = labels.distinctive_tokens("the deployment uses deploy_alpha.sh and 2026-09-28 at fooBar")
    assert "deploy_alpha.sh" in got and "fooBar" in got
    assert "deployment" not in got and "2026-09-28" not in got


def test_recallable_tokens_drop_general_and_older_vocabulary():
    tokens = {"a.md": {"node_modules", "old_path", "fresh_one"}}
    kept = labels.recallable_tokens(
        tokens,
        born={"a.md": 100.0},
        used_here={"old_path": 50.0, "fresh_one": 150.0},
        other_projects={"node_modules": 3},
        elsewhere=1,
    )
    assert kept == {"a.md": {"fresh_one"}}


def test_unique_tokens_exclude_shared_text():
    got = labels.unique_tokens({"a": "xx_one yy_two", "b": "yy_two zz_three"}, "zz_three")
    assert got == {"a": {"xx_one"}, "b": set()}


# --- metrics, sample, estimate ----------------------------------------------------------


def row(relevant, shown, context="x" * 10, read=(), quoted=None):
    return {
        "relevant": list(relevant),
        "read": list(read),
        "quoted": list(relevant if quoted is None else quoted),
        "arms": {"arm": (context if shown else "", tuple(shown))},
    }


def test_metrics():
    rows = [row(["a", "b"], ["a", "c"]), row([], []), row([], ["d"])]
    m = run.metrics(rows, "arm")
    assert m["recall"] == 0.5 and m["precision"] == round(1 / 3, 4)
    assert m["complete"] == 0.0 and m["quiet"] == 0.5
    assert m["chars"] == round(20 / 3, 1)


def fake_cases(n_pos, n_neg):
    return [
        {"project": "p", "session": "s", "index": i, "relevant": ["a"] if i < n_pos else []}
        for i in range(n_pos + n_neg)
    ]


def test_the_sample_rule():
    assert len(run.sample(fake_cases(10, 10))) == 20
    chosen = run.sample(fake_cases(200, 400))
    assert len(chosen) == run.SAMPLE
    assert sum(bool(c["relevant"]) for c in chosen) == run.POSITIVES
    assert chosen == run.sample(fake_cases(200, 400))  # seeded


def memories(n):
    return [mg.Memory(f"m{i}.md", f"n{i}", "d", "body " * 20) for i in range(n)]


def test_estimate_counts_the_calls_of_the_pre_registered_run():
    case = {"prompt": "carry on"}
    assert run.estimate_case(case, memories(5))[0] == 2
    groups = len(run.hierarchy.groups(chunks.PAGE_MAX + 5, chunks.PAGE_MAX))
    assert run.estimate_case(case, memories(chunks.PAGE_MAX + 5))[0] == 1 + groups + 1


async def test_the_dry_gate_injects_nothing():
    squire = run.Squire(run.NullDecider())
    case = {"prompt": "carry on", "project": "p", "available": []}
    arms = await run.arm_gate(squire, case, memories(3))
    assert arms == {"triage": ("", ()), "gate": ("", ())}


def test_bm25_arm_ranks_and_caps():
    ms = [mg.Memory("a.md", "alpha", "", "deploy alpha server"), mg.Memory("b.md", "b", "", "zzz")]
    context, shown = run.arm_bm25({"prompt": "deploy alpha"}, ms, 3)
    assert shown == ("a.md",) and len(context) <= run.GATE_CAP


def test_no_committed_result_names_a_project():
    for path in RESULTS.glob("*"):
        body = path.read_text(encoding="utf-8")
        assert "C--Users" not in body and "c--Users" not in body
        json.dumps(body)  # text, not binary


# --- part A: LongMemEval (synthetic question; the dataset is not needed) ------------------

import longmemeval as lme  # noqa: E402


def test_the_longmemeval_pre_registration_is_pinned():
    expected = (RESULTS / "prereg-longmemeval.sha256").read_text(encoding="utf-8").strip()
    assert _sha(RESULTS / "prereg-longmemeval.md") == expected == lme.prereg_hash()
    assert expected == "00cc07b46caa930b75422f71f4b64dad83a188747ef842b9748aa2b8670f2610"


def test_part_b_needs_the_owners_consent(monkeypatch):
    import pytest

    monkeypatch.setattr(sys, "argv", ["run.py", "--live"])
    with pytest.raises(SystemExit, match="consent"):
        run.main()


def lme_question(qid="q1", gold=("answer_x",)):
    turns = [
        [{"role": "user", "content": "my cat is called Miso", "has_answer": True}],
        [{"role": "user", "content": "recipe for bread " * 5}],
        [{"role": "user", "content": "weather talk"}],
    ]
    return {
        "question_id": qid,
        "question_type": "single-session-user",
        "question": "what is my cat called",
        "answer_session_ids": list(gold),
        "haystack_session_ids": ["answer_x", "s_b", "s_c"],
        "haystack_dates": ["2023/01/01", "2023/01/02", "2023/01/03"],
        "haystack_sessions": turns,
    }


def test_session_ids_never_reach_the_decider():
    ms = lme.memories_of(lme_question())
    assert [m.title for m in ms] == ["s01: 2023/01/01", "s02: 2023/01/02", "s03: 2023/01/03"]
    assert all("answer" not in t + x for t, x in mg.pages_of(ms, purpose="cat"))


def test_gold_and_baseline_arms():
    q = lme_question()
    ms = lme.memories_of(q)
    assert lme.gold_of(q) == {0}
    assert lme.arm_bm25(q, ms, 1) == {0}
    assert lme.arm_all(q, ms) == {0, 1, 2}  # all fit, newest first
    assert lme.excerpt_ceiling(q) == (1, 1)


def test_slices_are_disjoint_and_seeded():
    qs = [lme_question(f"q{i:03d}") for i in range(200)] + [
        lme_question(f"a{i:02d}_abs") for i in range(30)
    ]
    parts = lme.slices(qs)
    assert [len(parts[k]) for k in ("dev", "test", "abstention")] == [10, 120, 20]
    ids = [q["question_id"] for k in ("dev", "test") for q in parts[k]]
    assert len(set(ids)) == len(ids)
    assert parts == lme.slices(list(reversed(qs)))


async def test_longmemeval_dry_gate_selects_nothing_and_metrics_work():
    rows = await lme.evaluate([lme_question()], run.Squire(run.NullDecider()))
    (row,) = rows
    assert row["chosen"]["gate"] == [] and row["chosen"]["bm25@1"] == [0]
    assert lme.recall(rows, "bm25@1") == 1.0 and lme.any_hit(rows, "gate") == 0.0
    report = lme.report(rows)
    assert report["bm25@1"]["recall"][0] == 1.0


def test_longmemeval_estimate_uses_real_states():
    got = lme.estimate_question(lme_question())
    assert got["recall"][0] == 1 and got["triage_central"] == got["triage_pessimistic"]
    assert got["hybrid"][0] == 1 and got["hybrid"][1] > 0


class KeepFirst:
    """Answers every page: the first one 0.9, the rest 0.1; recall 0.9."""

    name = "fake"
    accepts_attachments = False

    async def decide(self, point, state, questions):
        answers = {k: (yes(0.9) if k in ("P01", "needs_memory") else yes(0.1)) for k in questions}
        return Decision(point, answers, self.name, "t")


async def test_the_hybrid_judges_only_the_bm25_candidates():
    q = lme_question()
    ms = lme.memories_of(q)
    assert await lme.arm_hybrid(run.Squire(KeepFirst()), q, ms) == {lme.bm25_ranked(q, ms)[0]}
    assert await lme.arm_hybrid(run.Squire(run.NullDecider()), q, ms) == set()
    rows = await lme.evaluate([q], run.Squire(KeepFirst()))
    assert rows[0]["chosen"]["hybrid"] == rows[0]["chosen"]["hybrid+recall"] == [0]
    assert rows[0]["excerpt_seen_hybrid"] == 1
    report = lme.report(rows)
    assert report["hybrid"]["recall"][0] == 1.0
    assert report["excerpt_ceiling"]["seen_among_hybrid_candidates"] == 1


# --- amendment 3: the passage cascade ---------------------------------------------------

import cascade as cas  # noqa: E402


def test_paragraphs_pack_across_turns_and_never_exceed_the_limit():
    turns = [
        {"role": "user", "content": "short one"},
        {"role": "assistant", "content": "short reply"},
        {"role": "assistant", "content": "A long answer. " * 200},
        {"role": "user", "content": "first part\n\nsecond part"},
    ]
    pages = cas.paragraphs_of(turns)
    assert all(len(text) <= cas.PARAGRAPH_LIMIT for _, text in pages)
    assert pages[0][1].startswith("user: short one\nassistant: ")
    assert pages[0][0].startswith("turns 1-") and pages[-1][0].endswith("4")
    joined = " ".join(text for _, text in pages)
    assert "second part" in joined and "first part" in joined


class Sentences:
    """Paragraph tournament: keeps P01 at 0.9. Sentences: keeps S1 only."""

    name = "fake"
    accepts_attachments = False

    async def decide(self, point, state, questions):
        answers = {k: yes(0.9 if k in ("P01", "S1") else 0.05) for k in questions}
        return Decision(point, answers, self.name, "t")


async def test_the_cascade_injects_kept_sentences_only():
    q = lme_question()
    hit, chars, paragraphs, sent = await cas.cascade_session(
        run.Squire(Sentences()), q["question"], q["haystack_sessions"][0]
    )
    assert hit and chars == len("user: my cat is called Miso") + 1
    assert (paragraphs, sent) == (1, 1)
    miss = await cas.cascade_session(
        run.Squire(run.NullDecider()), q["question"], q["haystack_sessions"][0]
    )
    assert miss[0] is False and miss[1] == 0


async def test_cascade_rows_and_report():
    rows = await cas.evaluate([lme_question()], run.Squire(Sentences()))
    (row,) = rows
    assert row["chosen"]["cascade"] == [0] and row["injected"]["cascade"] > 0
    assert lme.chars(rows, "cascade") == row["injected"]["cascade"]
    report = cas.report(rows)
    assert report["cascade"]["recall"][0] == 1.0
    assert report["ceiling_gold_in_candidates"] == {"in_candidates": 1, "gold": 1}


def test_the_plan_fits_the_budget_and_takes_a_prefix():
    qs = [lme_question(f"q{i}") for i in range(5)]
    n, spent = cas.plan(qs, [], share=0.1, budget=10.0)
    assert n == 5 and spent > 0
    one = cas.question_cost(cas.estimate_question(qs[0]), 0.2, True)
    n, spent = cas.plan(qs, [], share=0.1, budget=one * 2.5)
    assert n == 2 and spent <= one * 2.5
    assert cas.sentence_share([{"paragraphs": 10, "paragraphs_sent": 2}]) == 0.2


# --- the lost-calls defect of the first cascade run ---------------------------------------


class _Live:
    name = "fake"

    async def decide(self, point, state, questions):
        return Decision(point, {"x": yes(0.5)}, self.name, "m")


def _replay():
    from sanchopanza.providers.recorded import RecordedDecider

    return lme._Counted(run.triage_run.ReplayFirst(RecordedDecider([]), _Live()))


async def _burst(guard, tag):
    import asyncio

    await asyncio.gather(
        *(guard.decide("p", {"t": tag, "i": i}, {}) for i in range(5)), return_exceptions=True
    )


def test_a_second_event_loop_loses_calls_and_guarded_counts_them():
    import asyncio

    guard = _replay()
    asyncio.run(_burst(guard, "a"))
    asyncio.run(_burst(guard, "b"))
    assert guard.failed > 0 and guard.missing == 0  # what the first cascade run hid


def test_one_event_loop_loses_nothing():
    import asyncio

    guard = _replay()

    async def both():
        await _burst(guard, "a")
        await _burst(guard, "b")

    asyncio.run(both())
    assert guard.failed == 0 and guard.asked == 10
