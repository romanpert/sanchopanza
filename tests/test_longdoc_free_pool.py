"""Lot longdoc-free's pool (benchmarks/longdoc_free/pool.py): the items and novels, the dev draw
by whole novels from metadata only, the frozen table. No network."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pool = _load("lf_pool", "benchmarks/longdoc_free/pool.py")


def _raw(n_novels: int = 12, per: int = 5) -> list[dict]:
    out = []
    for n in range(n_novels):
        text = f"novel {n} " * 50
        for q in range(per):
            out.append({"id": n * per + q, "context": text, "input": f"q{n}.{q}?",
                        "answer": [f"a{n}.{q}"], "options": []})  # fmt: skip
    return out


def test_items_carry_one_key_per_novel_and_each_text_once():
    items, texts = pool.items(_raw())
    assert len(items) == 60 and len(texts) == 12
    assert len({i.novel for i in items[:5]}) == 1
    assert all(texts[i.novel] for i in items)
    assert items[0].answers == ("a0.0",)


def test_a_bare_answer_becomes_a_one_reference_tuple():
    row = {"id": 0, "context": "x", "input": "q?", "answer": "only", "options": []}
    assert pool.items([row])[0][0].answers == ("only",)


def test_the_dev_draw_takes_whole_novels_until_the_target():
    items, _ = pool.items(_raw(per=5))
    novel_of = {i.id: i.novel for i in items}
    dev = pool.draw_dev(novel_of, target=12)
    assert len(dev) == 3  # 5 + 5 < 12 <= 15: whole novels, never a split one
    assert pool.draw_dev(novel_of, target=12) == dev  # seeded


def test_the_dev_draw_reads_no_question_or_answer():
    """It takes ids and novel keys only: changing every question and answer changes nothing."""
    a, _ = pool.items(_raw())
    b, _ = pool.items([{**r, "input": "other", "answer": ["other"]} for r in _raw()])
    assert pool.draw_dev({i.id: i.novel for i in a}) == pool.draw_dev({i.id: i.novel for i in b})


def test_the_frozen_table_marks_every_item_dev_or_confirm_by_novel():
    items, _ = pool.items(_raw(n_novels=20, per=5))
    table = pool.frozen(items)
    phases = {(r["novel"], r["phase"]) for r in table["items"]}
    assert len({n for n, _ in phases}) == len(phases)  # one phase per novel
    dev = pool.phase_ids(table, "dev")
    assert len(dev) == pool.DEV_ITEMS and len(pool.phase_ids(table, "confirm")) == 60
    assert "question" not in table["items"][0] and "answers" not in table["items"][0]


def test_prepare_writes_each_novel_once_and_skips_a_good_copy(tmp_path: Path):
    _, texts = pool.items(_raw(n_novels=3))
    assert pool.prepare(texts, tmp_path) == 3
    assert pool.prepare(texts, tmp_path) == 0
    key = next(iter(texts))
    assert pool.novel_path(key, tmp_path).read_text("utf-8") == texts[key]


def test_the_pinned_file_when_cached():
    if not pool.RAW.exists():
        pytest.skip("∞Bench En.QA is not cached on this machine")
    pool.require_pinned()
    items, texts = pool.items(pool.rows())
    assert len(items) == pool.N_ITEMS and len(texts) == pool.N_NOVELS


def test_the_frozen_ids_when_frozen():
    if not pool.IDS_FILE.exists():
        pytest.skip("ids.json not frozen yet")
    table = pool.read_frozen()
    assert table["sha256"] == pool.SHA256 and len(table["items"]) == pool.N_ITEMS
    dev_novels = {r["novel"] for r in table["items"] if r["phase"] == "dev"}
    confirm_novels = {r["novel"] for r in table["items"] if r["phase"] == "confirm"}
    assert not dev_novels & confirm_novels
    assert len(pool.phase_ids(table, "dev")) >= pool.DEV_ITEMS
