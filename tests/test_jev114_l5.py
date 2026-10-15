"""Lot L5 (Jev 1.14, vision): the screenshot helpers, the analysis and the ranking's picture
hook, with no network and no third-party data."""

from __future__ import annotations

import asyncio
import importlib.util
import io
import sys
from pathlib import Path

import pytest

from sanchopanza.browse import Element, rank
from sanchopanza.contract import Answer, Decision
from sanchopanza.media import Attachment, attachments_in, image_size
from sanchopanza.points import browse as points

PIL = pytest.importorskip("PIL.Image")
ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


vision = _load("vision", "benchmarks/browse/vision.py")
l5 = _load("jev114_l5", "benchmarks/jev114/l5.py")
report = _load("l5_report", "benchmarks/jev114/l5_report.py")


def _page(width: int = 1280, height: int = 3000):
    return PIL.new("RGB", (width, height), (240, 240, 240))


# ---- vision ---------------------------------------------------------------------------------


def test_tiles_cover_the_page_and_merge_a_short_last_piece():
    assert vision.tiles(3000) == [(0, 1280), (1280, 2560), (2560, 3000)]
    assert vision.tiles(2660) == [(0, 1280), (1280, 2660)]  # a 100 px piece joins the tile above
    assert vision.tiles(900) == [(0, 900)]
    assert len(vision.tiles(50_000)) == vision.MAX_TILES


def test_rect_of_drops_boxes_without_area():
    assert vision.rect_of([10, 20, 30, 40]) == (10.0, 20.0, 40.0, 60.0)
    assert vision.rect_of([10, 20, 0, 40]) is None
    assert vision.rect_of([10, 20, float("nan"), 4]) is None


def test_page_rect_maps_fractions_of_a_region_back_to_page_pixels():
    tile = (0.0, 1280.0, 1280.0, 2560.0)
    assert vision.page_rect((0.5, 0.75, 0.25, 0.5), tile) == (320.0, 1920.0, 640.0, 2240.0)
    zoom = (100.0, 200.0, 740.0, 840.0)
    assert vision.page_rect((0.0, 1.0, 0.0, 1.0), zoom) == zoom


def test_iou_and_by_box_order_candidates_by_overlap_then_centre():
    a = (0.0, 0.0, 10.0, 10.0)
    assert vision.iou(a, a) == 1.0
    assert vision.iou(a, (5.0, 0.0, 15.0, 10.0)) == pytest.approx(50 / 150)
    assert vision.iou(a, (20.0, 20.0, 30.0, 30.0)) == 0.0
    ranked = vision.by_box(
        a,
        {
            "far": (100.0, 100.0, 110.0, 110.0),
            "near": (20.0, 0.0, 30.0, 10.0),
            "half": (5.0, 0.0, 15.0, 10.0),
        },
    )
    assert [k for k, _ in ranked] == ["half", "near", "far"]


def test_zoom_region_stays_inside_the_page():
    assert vision.zoom_region((0.0, 0.0, 10.0, 10.0), 1280, 3000) == (0.0, 0.0, 640.0, 640.0)
    assert vision.zoom_region((1270.0, 2990.0, 1280.0, 3000.0), 1280, 3000) == (
        640.0,
        2360.0,
        1280.0,
        3000.0,
    )
    assert vision.zoom_region((600.0, 600.0, 680.0, 640.0), 1280, 400) == (320.0, 0.0, 960.0, 400.0)


def test_window_holds_most_rects_within_the_span():
    rects = [(0.0, 100.0, 10.0, 120.0), (0.0, 300.0, 10.0, 320.0), (0.0, 9000.0, 10.0, 9020.0)]
    top, bottom = vision.window(rects, 10_000)
    assert top <= 100 and bottom >= 320 and bottom - top <= vision.SPAN
    assert vision.window([], 500) == (0, 500)


def test_images_are_jpeg_inside_jevs_bounds():
    page = _page(1280, 9000)
    for data in (
        vision.tile_image(page, (0, 1280), vision.PRESENCE_PIXELS),
        vision.tile_image(page, (0, 1280), vision.BOX_PIXELS),
        vision.region_image(page, (0.0, 0.0, 640.0, 640.0)),
    ):
        fmt, w, h = image_size(data)
        assert fmt == "jpeg" and min(w, h) >= 256 and max(w, h) <= 1568
        assert 78_400 <= w * h <= 2_458_624
    data, drawn = vision.marked_region(
        page,
        [("E01", (10.0, 10.0, 200.0, 40.0)), ("E02", None), ("E03", (5.0, 8000.0, 50.0, 8020.0))],
    )
    fmt, w, h = image_size(data)
    assert drawn == 1 and w * h <= vision.REGION_PIXELS and min(w, h) >= 256


def test_picture_for_labels_elements_in_call_order():
    page = _page()
    rects = {"a": (10.0, 10.0, 100.0, 40.0), "b": (10.0, 60.0, 100.0, 90.0)}
    seen = []

    def label(i: int) -> str:
        seen.append(i)
        return points.element_id(i)

    picture = vision.picture_for(page, rects, label)
    shot = picture([Element("b", "button", "B"), Element("a", "link", "A")])
    assert isinstance(shot, Attachment) and shot.media_type == "image/jpeg"
    assert seen == [0, 1]


# ---- the ranking's picture hook -------------------------------------------------------------


def test_a_text_only_state_is_unchanged_and_a_screenshot_is_added():
    plain, _ = points.questions(goal="g", done=[], lines=["link A"])
    assert set(plain) == {"goal", "done", "elements"}
    shot = Attachment(media_type="image/jpeg", data=b"\xff\xd8x")
    state, qs = points.questions(goal="g", done=[], lines=["link A"], screenshot=shot)
    assert state["screenshot"] is shot and state["screenshot_note"] == points.SCREENSHOT_NOTE
    assert qs == points.questions(goal="g", done=[], lines=["link A"])[1]


class _Squire:
    def __init__(self) -> None:
        self.states = []

    async def decide(self, point, state, questions):
        self.states.append(state)
        answers = {k: Answer(kind="truth", confidence=0.9, truth=0.1) for k in questions}
        return Decision(point, answers, "fake", "fake")

    def record(self, decision, **_):
        return None


def test_rank_puts_one_picture_in_every_call_when_asked():
    elements = [Element(str(i), "link", f"item {i}") for i in range(45)]
    squire = _Squire()
    calls = []

    def picture(group):
        calls.append([e.key for e in group])
        return Attachment(media_type="image/jpeg", data=b"\xff\xd8x")

    asyncio.run(rank("goal", elements, squire=squire, keep=5, picture=picture))
    assert len(squire.states) == 3  # two groups and the final round
    assert all(len(attachments_in(s)) == 1 for s in squire.states)
    assert calls[0] == [str(i) for i in range(30)]
    squire = _Squire()
    asyncio.run(rank("goal", elements, squire=squire, keep=5))
    assert all(not attachments_in(s) for s in squire.states)


# ---- runner and analysis --------------------------------------------------------------------


def test_rotation_puts_each_arm_first_a_third_of_the_time():
    firsts = [l5.rotation(i)[0] for i in range(6)]
    assert firsts == ["t14", "i14", "i13", "t14", "i14", "i13"]
    assert all(sorted(l5.rotation(i)) == sorted(l5.B2_ARMS) for i in range(3))


def test_b2_steps_takes_the_first_of_each_split_in_order():
    steps = [{"id": f"{s}{i}", "split": s} for s in reversed(l5.SPLIT_ORDER) for i in range(3)]
    assert [s["id"] for s in l5.b2_steps(steps, 2)] == [
        "test_website0",
        "test_website1",
        "test_domain0",
        "test_domain1",
        "test_task0",
        "test_task1",
    ]


def test_fuse_prefers_the_best_overlap_among_the_text_head():
    text = ["a", "b", "c"]
    assert report.fuse(text, [["c", 0.6], ["b", 0.2]]) == "c"
    assert report.fuse(text, [["z", 0.9]]) == "a"  # nothing in the head overlaps: text first
    assert report.fuse(text, [["b", 0.5], ["c", 0.5]]) == "b"  # a tie goes to the text order
    assert report.fuse([], []) is None


def test_verdicts_follow_the_sealed_rule():
    assert report.verdict({"n": 50, "diff": 0.1, "ci95": (0.02, 0.2)}, 0.01) == "mejora"
    assert report.verdict({"n": 50, "diff": -0.1, "ci95": (-0.2, -0.02)}, 0.01) == "peor"
    assert report.verdict({"n": 50, "diff": 0.0, "ci95": (-0.01, 0.02)}, 1.0) == "no peor"
    assert report.verdict({"n": 50, "diff": 0.0, "ci95": (-0.1, 0.1)}, 1.0) == "no concluyente"
    assert report.verdict({"n": 5, "diff": 0.0, "ci95": (0.0, 0.0)}, 1.0) == "no medido"
    assert report.verdict({"diff": None, "ci95": None}, 1.0) == "no medido"


def test_b2_report_pairs_complete_steps_only():
    def arm(position, failed=False):
        return {"position": position, "top": [], "calls": 1, "usd": 0.001, "failed": failed}

    rows = [
        {"id": "s1", "website": "w", "t14": arm(12), "i14": arm(3), "i13": arm(4)},
        {"id": "s2", "website": "w", "t14": arm(None), "i14": arm(1), "i13": arm(None)},
        {"id": "s3", "website": "w", "t14": arm(1), "i14": arm(1, True), "i13": arm(1)},
    ]
    truth = {i: {"positives": {"x"}, "wordless": i == "s2"} for i in ("s1", "s2", "s3")}
    out = report.b2(rows, {}, truth)
    assert out["complete"] == 2 and out["excluded_failed"] == 1
    assert out["recall"]["i14"]["@10"] == 1.0 and out["recall"]["t14"]["@10"] == 0.0
    assert out["primary"]["image_effect_r10"]["diff"] == 1.0
    assert out["wordless"]["steps"] == 1


def test_centre_in_positive():
    boxes = {"x": [0, 0, 10, 10]}
    assert report.centre_in([2, 2, 6, 6], boxes, {"x"})
    assert not report.centre_in([20, 20, 30, 30], boxes, {"x"})
    assert not report.centre_in(None, boxes, {"x"})


def test_box_image_round_trips_through_pillow():
    data = vision.tile_image(_page(1280, 1500), (0, 1280), vision.BOX_PIXELS)
    picture = PIL.open(io.BytesIO(data))
    assert picture.size == (1280, 1280)


class _Served:
    """A live decider that answers every question from `model`."""

    name = "fake"

    def __init__(self, model: str, answer_all: bool = True) -> None:
        self.model, self.answer_all = model, answer_all

    async def decide(self, point, state, questions):
        keys = list(questions)[: None if self.answer_all else 1]
        answers = {k: Answer(kind="truth", confidence=0.9, truth=0.2) for k in keys}
        return Decision(point, answers, "jev", self.model)


def test_an_answer_from_another_model_is_flagged_and_not_used(tmp_path):
    gate = asyncio.Semaphore(1)
    arm = l5.Arm("i14", tmp_path / "rec.jsonl", "jev-1.14.0", _Served("jev-1.13.0"), gate)
    elements = [Element(str(i), "link", f"item {i}") for i in range(40)]
    from sanchopanza.squire import Squire

    asyncio.run(rank("goal", elements, squire=Squire(arm), keep=5))
    assert arm.mismatch == "i14: asked jev-1.14.0, served jev-1.13.0"
    assert arm.failures == 3


def test_a_partial_answer_counts_as_a_failure(tmp_path):
    from sanchopanza.contract import Truth

    gate = asyncio.Semaphore(1)
    arm = l5.Arm("t14", tmp_path / "rec.jsonl", "jev-1.14.0", _Served("jev-1.14.0", False), gate)
    asyncio.run(arm.decide("p", {"x": 1}, {"a": Truth("a?"), "b": Truth("b?")}))
    assert arm.failures == 1 and not arm.mismatch


def test_calls_expected_matches_the_tournament():
    assert l5.calls_expected(30) == 1
    assert l5.calls_expected(31) == 3
    assert l5.calls_expected(559) == 20


def test_the_product_rule_needs_a_holm_mejora():
    good = {"n": 142, "diff": 0.1, "ci95": (0.05, 0.15), "p": 0.001}
    flat = {"n": 142, "diff": 0.0, "ci95": (-0.05, 0.05), "p": 1.0}
    out = {
        "b1": {"primary_box_minus_text13rec": flat, "fuse10_13_minus_text13rec": good},
        "b2": {"primary": {"image_effect_r10": flat}},
    }
    decided = report.product(out)
    assert decided["vision_mode"] == "recomendado" and decided["complete"]
    out["b1"]["fuse10_13_minus_text13rec"] = {**good, "p": 0.03}  # 0.09 after Holm
    assert report.product(out)["vision_mode"] == "no recomendado"


def test_a_band_is_never_thinner_than_jev_takes():
    top, bottom = vision.window([(0.0, 500.0, 10.0, 520.0)], 3000)
    assert bottom - top >= vision.MIN_BAND >= 280
    top, bottom = vision.window([(0.0, 2990.0, 10.0, 2999.0)], 3000)
    assert bottom == 3000 and bottom - top >= vision.MIN_BAND
