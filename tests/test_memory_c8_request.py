"""ROADMAP C8: a record kept the prompt's first 1,000 characters, so a plan said at the end of a
long prompt was lost: head and tail now, in the same budget (`episodes.REQUEST_CHARS`)."""

from __future__ import annotations

import time
from typing import Any

from sanchopanza.context import episodes as ep

CWD = "C:/work/repo"


def _stamp(at: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at))


def prompt(text: str, at: float) -> dict[str, Any]:
    return {"type": "user", "cwd": CWD, "timestamp": _stamp(at),
            "message": {"role": "user", "content": text}}  # fmt: skip


def say(text: str) -> dict[str, Any]:
    message = {"role": "assistant", "content": [{"type": "text", "text": text}]}
    return {"type": "assistant", "message": message}


# ---- b: a long prompt keeps its head and its tail --------------------------------------------


def test_a_long_prompt_s_record_keeps_its_head_and_its_tail_within_the_budget() -> None:
    middle = "Some background about the module that does not matter much. " * 40
    text = f"Write label_for(order) in app/labels.py. {middle}Step 2, next session: ship_all."
    found, _ = ep.episodes_of([prompt(text, 1_800_000_000.0), say("done")], session="s")
    request = found[0].request
    assert len(request) <= ep.REQUEST_CHARS
    assert request.startswith("Write label_for(order)") and request.endswith("ship_all.")
    assert ep.CUT in request
    # the page the decider reads still opens with the prompt's head, as before
    assert "Request: Write label_for(order) in app/labels.py." in found[0].page()


def test_a_prompt_that_fits_is_kept_whole_and_a_secret_is_masked_before_the_cut() -> None:
    short = "Add a test for the date parser."
    assert ep.episodes_of([prompt(short, 1.0), say("ok")], session="s")[0][0].request == short
    token = "ghp_" + "c" * 36
    long = token + " " + "x" * 3_000
    request = ep.episodes_of([prompt(long, 1.0), say("ok")], session="s")[0][0].request
    assert token not in request and "ghp_" + "c" * 8 not in request


def test_m3_the_cut_falls_between_words_and_sentences() -> None:
    words = " ".join(f"word{i:04d}" for i in range(400))  # 3,599 characters, no full stop
    kept = ep.head_tail(words, ep.REQUEST_CHARS)
    head, tail = kept.split(ep.CUT)
    assert len(kept) <= ep.REQUEST_CHARS
    assert all(w.startswith("word") and len(w) == 8 for w in [*head.split(), *tail.split()])
    sentences = "".join(f"Sentence number {i:03d} says one thing. " for i in range(100)).strip()
    head, tail = ep.head_tail(sentences, ep.REQUEST_CHARS).split(ep.CUT)
    assert head.endswith("thing.") and tail.startswith("Sentence number")


def test_l1_a_budget_smaller_than_the_mark_still_holds() -> None:
    assert ep.head_tail("x" * 50, 4) == "xxxx"


def test_m6_a_secret_across_the_cut_is_masked_whole() -> None:
    token = "ghp_" + "c" * 36  # 40 characters at 480-520 of a 3,000-character prompt
    text = "a " * 240 + token + " " + "b " * 1_240
    assert text.index(token) == 480 and len(text) > 2_900
    request = ep.episodes_of([prompt(text, 1.0), say("ok")], session="s")[0][0].request
    assert "cccccccc" not in request and "ghp_" not in request
