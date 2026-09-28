"""The auto-memory recall gate, on synthetic memory directories and fake deciders. No network."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sanchopanza import Decision
from sanchopanza.harness import memory_gate as mg
from sanchopanza.points import chunks

from .helpers import squire, yes

GH_TOKEN = "ghp_" + "a" * 30


def write_memory(directory: Path, file: str, name: str, description: str, body: str) -> None:
    text = f"---\nname: {name}\ndescription: {description}\ntype: feedback\n---\n{body}\n"
    (directory / file).write_text(text, encoding="utf-8")


def memory_dir(tmp_path: Path, n: int = 3) -> Path:
    d = tmp_path / "memory"
    d.mkdir()
    (d / "MEMORY.md").write_text("- [index](a.md) - the index itself\n", encoding="utf-8")
    for i in range(n):
        write_memory(d, f"m{i:03d}.md", f"memory {i}", f"about topic {i}", f"body of memory {i}")
    return d


class Fake:
    """Answers `recall` with `recall_p` and every page with `page_p(index)`; logs states."""

    name = "fake"
    accepts_attachments = False

    def __init__(self, recall_p: float | None = 0.9, page_p: Any = None) -> None:
        self.recall_p = recall_p
        self.page_p = page_p or (lambda i: 0.9 if i == 1 else 0.1)
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    async def decide(self, point: str, state: Mapping[str, Any], questions: Mapping[str, Any]):
        self.calls = [*self.calls, (point, state)]
        if point == "recall":
            answers = {} if self.recall_p is None else {"needs_memory": yes(self.recall_p)}
            return Decision(point, answers, self.name, "t")
        if point == "memory_collision":
            return Decision(
                point, {"contradicts": yes(0.95), "adds_nothing": yes(0.05)}, self.name, "t"
            )
        answers = {}
        for key in questions:
            p = self.page_p(int(key[1:]) - 1)
            if p is not None:
                answers = {**answers, key: yes(p)}
        return Decision(point, answers, self.name, "t")


class Broken:
    name = "broken"
    accepts_attachments = False

    async def decide(self, point, state, questions):
        raise RuntimeError("boom")


# --- loading ----------------------------------------------------------------------------


def test_frontmatter_is_parsed_and_the_index_is_skipped(tmp_path):
    d = memory_dir(tmp_path)
    memories = mg.load_memories(d)
    assert [m.file for m in memories] == ["m000.md", "m001.md", "m002.md"]
    assert memories[0].name == "memory 0"
    assert memories[0].description == "about topic 0"
    assert memories[0].kind == "feedback"
    assert memories[0].body == "body of memory 0"


def test_a_file_without_frontmatter_is_all_body():
    meta, body = mg.parse_frontmatter("just text\nmore")
    assert meta == {} and body == "just text\nmore"


def test_crlf_frontmatter():
    meta, body = mg.parse_frontmatter("---\r\nname: x\r\n---\r\nbody\r\n")
    assert meta == {"name": "x"} and body == "body"


def test_missing_directory_is_empty(tmp_path):
    assert mg.load_memories(tmp_path / "nope") == ()


def test_secrets_are_redacted_at_load(tmp_path):
    d = memory_dir(tmp_path, 0)
    write_memory(d, "k.md", "key", "the token", f"use {GH_TOKEN} for pushes")
    (memory,) = mg.load_memories(d)
    assert GH_TOKEN not in memory.body and "[secret]" in memory.body


def test_memory_dir_comes_from_the_transcript_then_the_cwd(tmp_path):
    event = {"transcript_path": str(tmp_path / "proj" / "s.jsonl"), "cwd": "c:\\x"}
    assert mg.memory_dir_for(event) == tmp_path / "proj" / "memory"
    got = mg.memory_dir_for({"cwd": "C:\\Users\\r\\a.b"}, home=tmp_path)
    assert got == tmp_path / ".claude" / "projects" / "C--Users-r-a-b" / "memory"
    assert mg.memory_dir_for({}) is None


# --- rendering --------------------------------------------------------------------------


def test_render_never_exceeds_the_cap_and_lists_what_did_not_fit():
    big = [mg.Memory(f"f{i}.md", f"n{i}", "d", "x" * 2_000) for i in range(10)]
    context, shown, listed = mg.render(big, cap=5_000)
    assert len(context) <= 5_000
    assert shown and listed
    assert set(shown) | set(listed) == {m.file for m in big}
    for name in listed:
        assert name in context  # every kept memory is at least named


def test_render_empty():
    assert mg.render([], cap=1_000) == ("", (), ())


def test_order_kept_puts_unanswered_last():
    ms = [mg.Memory(f"{i}.md", "", "", "") for i in range(3)]
    ordered = mg.order_kept(ms, [(True, None), (True, 0.5), (True, 0.9)])
    assert [m.file for m, _ in ordered] == ["2.md", "1.md", "0.md"]


# --- the gate ---------------------------------------------------------------------------


async def test_injects_only_what_contributes(tmp_path):
    d = memory_dir(tmp_path)
    fake = Fake()
    s, _ = squire(fake)
    out = await mg.handle_user_prompt({"prompt": "do the thing"}, s, memory_dir=d)
    context = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "m001.md" in context and "m000.md" not in context
    assert [p for p, _ in fake.calls] == ["recall", "triage_pages"]


async def test_a_confident_no_skips_the_memory_call(tmp_path):
    d = memory_dir(tmp_path)
    fake = Fake(recall_p=0.05)
    s, _ = squire(fake)
    assert await mg.handle_user_prompt({"prompt": "what is 2+2"}, s, memory_dir=d) == {}
    assert [p for p, _ in fake.calls] == ["recall"]


async def test_recall_unanswered_still_looks(tmp_path):
    d = memory_dir(tmp_path)
    fake = Fake(recall_p=None)
    s, _ = squire(fake)
    out = await mg.handle_user_prompt({"prompt": "carry on"}, s, memory_dir=d)
    assert out and len(fake.calls) == 2


async def test_null_decider_injects_nothing(tmp_path, capsys):
    d = memory_dir(tmp_path)
    s, _ = squire(None)
    assert await mg.handle_user_prompt({"prompt": "carry on"}, s, memory_dir=d) == {}
    assert "nothing injected" in capsys.readouterr().err


async def test_a_broken_decider_fails_open(tmp_path):
    d = memory_dir(tmp_path)
    s, _ = squire(Broken())
    assert await mg.handle_user_prompt({"prompt": "carry on"}, s, memory_dir=d) == {}


async def test_a_bug_of_ours_fails_open_and_says_why(tmp_path, capsys, monkeypatch):
    d = memory_dir(tmp_path)
    s, _ = squire(Fake())

    def explode(_):
        raise ValueError("bad dir")

    monkeypatch.setattr(mg, "load_memories", explode)
    assert await mg.handle_user_prompt({"prompt": "carry on"}, s, memory_dir=d) == {}
    assert "failed open" in capsys.readouterr().err


async def test_no_memories_means_no_call(tmp_path):
    fake = Fake()
    s, _ = squire(fake)
    out = await mg.handle_user_prompt({"prompt": "x y z"}, s, memory_dir=tmp_path / "none")
    assert out == {} and fake.calls == []


async def test_secrets_never_reach_the_decider(tmp_path):
    d = memory_dir(tmp_path)
    write_memory(d, "k.md", "key", "the token", f"use {GH_TOKEN}")
    fake = Fake()
    s, _ = squire(fake)
    await mg.handle_user_prompt({"prompt": f"push with {GH_TOKEN}"}, s, memory_dir=d)
    sent = json.dumps([state for _, state in fake.calls])
    assert GH_TOKEN not in sent


async def test_more_than_one_call_holds_goes_to_the_tournament(tmp_path):
    d = memory_dir(tmp_path, chunks.PAGE_MAX + 5)
    fake = Fake(page_p=lambda i: 0.9 if i == 0 else 0.05)
    s, _ = squire(fake)
    out = await mg.handle_user_prompt({"prompt": "carry on"}, s, memory_dir=d)
    points = [p for p, _ in fake.calls]
    assert points[0] == "recall" and points.count("triage_pages") >= 2
    assert out  # something survived


async def test_a_superseded_memory_is_dropped(tmp_path):
    ms = [
        mg.Memory("old.md", "deploy", "deploy target", "deploy goes to server alpha", 1.0),
        mg.Memory("new.md", "deploy", "deploy target", "deploy goes to server beta", 2.0),
    ]
    s, _ = squire(Fake(page_p=lambda i: 0.9))
    result = await mg.gate(s, "deploy it", ms, check_conflicts=True)
    assert result.injected == ("new.md",)
    assert result.report["superseded"] == ["old.md"]


async def test_same_mtime_conflict_is_flagged_not_dropped(tmp_path):
    ms = [
        mg.Memory("a.md", "deploy", "deploy target", "deploy goes to server alpha", 1.0),
        mg.Memory("b.md", "deploy", "deploy target", "deploy goes to server beta", 1.0),
    ]
    s, _ = squire(Fake(page_p=lambda i: 0.9))
    result = await mg.gate(s, "deploy it", ms, check_conflicts=True)
    assert set(result.injected) == {"a.md", "b.md"}
    assert "may contradict" in result.context


def test_conflict_candidates_are_bounded():
    ms = [mg.Memory(f"{i}.md", "same words here", "", "same words here") for i in range(6)]
    assert len(mg.conflict_candidates(ms, max_pairs=3)) == 3


def test_hook_output_empty_context_is_nothing():
    assert mg.hook_output("") == {}


def test_nested_metadata_type_is_read():
    text = "---\nname: n\nmetadata:\n  type: project\n---\nbody"
    meta, body = mg.parse_frontmatter(text)
    assert meta["type"] == "project" and meta["name"] == "n" and body == "body"


def test_a_long_memory_is_judged_on_the_part_that_matches_the_prompt():
    body = "intro " * 300 + "the deploy key rotates every friday " + "filler " * 300
    (page,) = mg.pages_of([mg.Memory("a.md", "n", "d", body)], purpose="when does the key rotate")
    assert "rotates every friday" in page[1] and len(page[1]) <= chunks.PAGE_LIMIT
