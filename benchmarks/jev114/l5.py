"""Jev 1.14, lot L5: vision on Multimodal-Mind2Web (B1: Box; B2: the ranking with a screenshot).

    python -I benchmarks/jev114/l5.py --seal                  # prereg.sha256
    python -I benchmarks/jev114/l5.py --run b1|b2 [--live] [--smoke] [--limit N]
    python -I benchmarks/jev114/l5.py                         # analysis of the rows, free

Pre-registered in docs/results/2026-10-15-jev114-l5/prereg.md. Steps: the 142 confirmation
steps of docs/results/2026-09-30-browse (`~/.cache/sanchopanza/mind2web/steps-confirm.jsonl`);
screenshots and candidate boxes from `benchmarks/browse/data.py --shots` in DATA (outside the
repo). `--smoke` reads the development steps (`steps.jsonl`, Phase 1's) and writes nothing in
the repo.

Arms (live arms through `CappedDecider` on the shared ledger, this lot's cap, at most
CONCURRENCY requests in flight; each arm's answers recorded under FIXTURES, keys and numbers
only, so a relaunch asks only what is missing):
- `box14` (B1): jev-1.14.0, images on: a presence Truth per page tile, Box on the best tile,
  then Box again on a 640 px square around that box (the zoom).
- `t14`, `i14`, `i13` (B2): `browse.rank` as confirmed on 2026-09-30, text only (`t14`), or with
  each call's band of the page in the state, its elements outlined and labelled (`i14`, `i13`).
- `t13rec`: jev-1.13.0's recording of 2026-09-30 (`fixtures/browse-jev-confirm.jsonl`), replayed.

The key comes from TYPESAFE_API_KEY or the `.env` file SANCHOPANZA_KEYS_ENV names (never
printed).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for extra in ("src", "benchmarks/browse"):
    sys.path.insert(0, str(REPO / extra))
sys.path.insert(0, str(HERE))

import vision  # noqa: E402

from sanchopanza.contract import Box, Decision, Truth  # noqa: E402
from sanchopanza.points import browse as points  # noqa: E402
from sanchopanza.text import truncate  # noqa: E402

OUT = REPO / "docs" / "results" / "2026-10-15-jev114-l5"
PREREG = OUT / "prereg.md"
FIXTURES = REPO / "fixtures" / "jev114"
RUN_DIR = Path(os.environ.get("SANCHOPANZA_JEV114_RUN", "C:/sp-runs/jev114"))
DATA = RUN_DIR / "l5" / "data"
SMOKE_DIR = RUN_DIR / "l5" / "smoke"
MIND2WEB = Path.home() / ".cache" / "sanchopanza" / "mind2web"
LEDGER_PATH = RUN_DIR / "ledger.json"
LEDGER_CAP_USD = 4.50
BATCH = "jev114-l5"
BATCH_CAP_USD = 1.50
CONCURRENCY = 4
KEEP = 50  # positions past this count as not found, as in run.py
B2_PER_SPLIT = 16  # B2: the first 16 confirmation steps of each split, in file order
SPLIT_ORDER = ("test_website", "test_domain", "test_task")
ARMS = {  # name: (model, images)
    "box14": ("jev-1.14.0", True),
    "t14": ("jev-1.14.0", False),
    "i14": ("jev-1.14.0", True),
    "i13": ("jev-1.13.0", True),
}
B2_ARMS = ("t14", "i14", "i13")
# Stop rule: a run halts when its live spend passes this many times its estimate so far.
B1_USD_PER_STEP = 0.0008
B2_USD_PER_STEP = {"t14": 0.0070, "i14": 0.0089, "i13": 0.0089}  # per 559 elements
OVERRUN = 1.5
INSTRUMENT = ("src", "benchmarks", "pyproject.toml")  # all committed before a live run

TILES_NOTE = (
    "The page's screenshot, cut top to bottom: tile_1 is the top of the page and each next "
    "tile continues below the one before."
)
PRESENT = (
    "Does `{tile}` show the element to act on next (click it, type into it, or pick from it) "
    "to carry out `goal`, given the actions in `done`?"
)
PRESENT_CRITERIA = {
    "true": "The tile shows the link, button, tab, option, filter or field that is the next "
    "step toward the goal",
    "false": "The tile shows only elements unrelated to the goal, steps already in `done`, or "
    "steps that only make sense later",
}
WHERE = (
    "The element of the page in `screenshot` to act on next (click it, type into it, or pick "
    "from it) to carry out `goal`, given the actions in `done`"
)
SHOWN = (
    "Does `screenshot` show the element to act on next (click it, type into it, or pick from "
    "it) to carry out `goal`, given the actions in `done`?"
)


# ---- data -----------------------------------------------------------------------------------


def load_steps(smoke: bool) -> list[dict[str, Any]]:
    """The steps in file order within each split, splits in SPLIT_ORDER, with a screenshot."""
    source = MIND2WEB / ("steps.jsonl" if smoke else "steps-confirm.jsonl")
    shots = DATA / ("dev" if smoke else "confirm")
    meta = {}
    for line in (shots / "boxes.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            meta[row["id"]] = row
    rows = [json.loads(x) for x in source.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = sorted(rows, key=lambda r: SPLIT_ORDER.index(r["split"]))
    missing = [r["id"] for r in rows if r["id"] not in meta]
    if missing:
        print(f"{len(missing)} steps without a screenshot, left out: {missing}", file=sys.stderr)
    return [{**r, "shot": meta[r["id"]], "shot_path": str(shots / f"{r['id']}.jpg")}
            for r in rows if r["id"] in meta]  # fmt: skip


def b2_steps(steps: Sequence[dict[str, Any]], per_split: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for split in SPLIT_ORDER:
        out.extend([s for s in steps if s["split"] == split][:per_split])
    return out


def page_of(step: Mapping[str, Any]) -> Any:
    from PIL import Image

    page = Image.open(step["shot_path"])
    page.load()
    return page


def rects_of(step: Mapping[str, Any]) -> dict[str, vision.Rect | None]:
    """The step's own elements (the ones the ranking ranks) to their page boxes."""
    boxes = step["shot"]["boxes"]
    return {e["key"]: vision.rect_of(boxes[e["key"]]) if e["key"] in boxes else None
            for e in step["elements"]}  # fmt: skip


def goal_and_done(step: Mapping[str, Any]) -> dict[str, str]:
    """`goal` and `done` exactly as the ranking's state shows them."""
    recent = list(step["previous"])[-points.DONE_MAX :]
    return {
        "goal": truncate(step["task"], 400),
        "done": "\n".join(truncate(a, 160) for a in recent) or "(nothing yet)",
    }


# ---- arms -----------------------------------------------------------------------------------


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def complete(decision: Decision, questions: Mapping[str, Any]) -> bool:
    """Every question answered with a usable value."""
    if decision.failed or not decision.answers:
        return False
    return all(not decision.answer(key).empty for key in questions)


class Halt(Exception):
    """Stop scheduling: cap refused, model mismatch, too many failures or overspend."""


class Arm:
    """Recorded answers first; on a miss one live call through the cap, recorded on success."""

    def __init__(self, name: str, path: Path, model: str, live: Any, gate: Any) -> None:
        from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider

        self.name, self.path, self.model, self.gate = name, path, model, gate
        self.recorded = RecordedDecider.from_file(path, model=model)
        self.writer = RecordingDecider(live, path) if live is not None else None
        self.failures = 0
        self.errors: list[str] = []
        self.mismatch = ""  # set on an answer from another model; the runner halts on it
        self.live_calls = 0
        self.live_usd = 0.0

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Decision:
        found = await self.recorded.decide(point, state, questions)
        if found.answers:
            return found
        if self.writer is None:
            self.failures += 1
            return Decision(point, {}, self.name, "-", error="not recorded, no live decider")
        async with self.gate:
            try:
                decision = await self.writer.decide(point, state, questions)
            except Exception as error:  # noqa: BLE001 - a refusal or outage is counted
                self.failures += 1
                self.errors.append(f"{type(error).__name__}: {str(error)[:200]}")
                return Decision(point, {}, self.name, "-", error=type(error).__name__)
        self.live_calls += 1
        self.live_usd += decision.cost_usd
        if decision.model != self.model and not decision.failed:
            # Not raised: inside `browse.rank` the Squire would turn it into a failed decision.
            self.failures += 1
            self.mismatch = f"{self.name}: asked {self.model}, served {decision.model}"
            return Decision(point, {}, self.name, "-", error="model mismatch")
        if not complete(decision, questions):
            self.failures += 1
            self.errors.append(str(decision.error or "answers missing")[:200])
        return decision


def make_arms(names: Sequence[str], live: bool, fixtures: Path) -> dict[str, Any]:
    gate = asyncio.Semaphore(CONCURRENCY)
    capped: dict[str, Any] = {}
    if live:
        from sanchopanza.budget import SpendLedger
        from sanchopanza.providers import CappedDecider
        from sanchopanza.providers.jev import JevDecider

        ledger = SpendLedger(LEDGER_PATH, cap_usd=LEDGER_CAP_USD)
        for name in names:
            model, images = ARMS[name]
            inner = JevDecider(model=model, long_context=False, images=images)
            capped[name] = CappedDecider(inner, ledger=ledger, batch=BATCH, max_usd=BATCH_CAP_USD)
    return {name: Arm(name, fixtures / f"browse-l5-{name}.jsonl", ARMS[name][0],
                      capped.get(name), gate)
            for name in names}  # fmt: skip


def replay_113(smoke: bool = False) -> Any:
    """jev-1.13.0's answers of 2026-09-30, served in recorded order (run.py's InOrder): the
    confirmation's recording, or Phase 1's for the development steps."""
    run = _load("browse_run", REPO / "benchmarks" / "browse" / "run.py")
    name = "browse-jev.jsonl" if smoke else "browse-jev-confirm.jsonl"
    return run.InOrder(REPO / "fixtures" / name)


# ---- B1: Box --------------------------------------------------------------------------------


def presence_request(step: Mapping[str, Any], page: Any) -> tuple[list, dict, dict]:
    from sanchopanza.media import image

    spans = vision.tiles(page.height)
    state: dict[str, Any] = {**goal_and_done(step), "tiles_note": TILES_NOTE}
    questions: dict[str, Any] = {}
    for k, span in enumerate(spans, 1):
        data = vision.tile_image(page, span, vision.PRESENCE_PIXELS)
        state[f"tile_{k}"] = image(data=data, media_type="image/jpeg")
        questions[f"T{k}"] = Truth(PRESENT.format(tile=f"tile_{k}"), criteria=PRESENT_CRITERIA)
    return spans, state, questions


async def box_step(step: Mapping[str, Any], arm: Arm) -> dict[str, Any]:
    from sanchopanza.media import image

    page = page_of(step)
    spans, state, questions = presence_request(step, page)
    first = await arm.decide("browse_presence", state, questions)
    asked = [(first, questions)]
    presence = [first.answer(f"T{k}").truth for k in range(1, len(spans) + 1)]
    best = max(range(len(spans)), key=lambda k: (-1.0 if presence[k] is None else presence[k], -k))
    shot = image(data=vision.tile_image(page, spans[best], vision.BOX_PIXELS),
                 media_type="image/jpeg")  # fmt: skip
    pair = {"where": Box(WHERE), "shown": Truth(SHOWN)}
    second = await arm.decide("browse_box", {**goal_and_done(step), "screenshot": shot}, pair)
    asked.append((second, pair))
    where = second.answer("where")
    row: dict[str, Any] = {
        "id": step["id"], "split": step["split"], "website": step["website"],
        "height": page.height, "tiles": len(spans), "presence": presence, "best": best,
        "shown": second.answer("shown").truth, "box": list(where.box) if where.box else None,
        "box_confidence": where.confidence if where.box else None,
    }  # fmt: skip
    decisions = [first, second]
    rects = {k: r for k, r in rects_of(step).items() if r is not None}
    if where.box is not None:
        tile = (0.0, float(spans[best][0]), float(page.width), float(spans[best][1]))
        predicted = vision.page_rect(where.box, tile)
        row |= {"rect": [round(v, 1) for v in predicted],
                "by_box": overlapping(vision.by_box(predicted, rects))}  # fmt: skip
        region = vision.zoom_region(predicted, page.width, page.height)
        third = await arm.decide(
            "browse_box_zoom",
            {**goal_and_done(step),
             "screenshot": image(data=vision.region_image(page, region), media_type="image/jpeg")},
            pair,
        )  # fmt: skip
        decisions.append(third)
        asked.append((third, pair))
        zoomed = third.answer("where")
        row |= {"zoom_region": list(region), "zoom_shown": third.answer("shown").truth,
                "zoom_box": list(zoomed.box) if zoomed.box else None}  # fmt: skip
        if zoomed.box is not None:
            fine = vision.page_rect(zoomed.box, region)
            row |= {"zoom_rect": [round(v, 1) for v in fine],
                    "by_zoom": overlapping(vision.by_box(fine, rects))}  # fmt: skip
    return {**row, "failed": not all(complete(d, q) for d, q in asked),
            "usd": round(sum(d.cost_usd for d in decisions), 7),
            "tokens": [d.input_tokens for d in decisions]}  # fmt: skip


def overlapping(ranked: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """What a row keeps of a box's candidate order: every candidate it overlaps, and at least
    the first KEEP (FUSE10 needs the overlap of any of the text's first 10)."""
    return [pair for i, pair in enumerate(ranked) if i < KEEP or pair[1] > 0]


# ---- B2: the ranking ------------------------------------------------------------------------


async def rank_step(step: Mapping[str, Any], arm: Any, images: bool) -> dict[str, Any]:
    from sanchopanza.browse import BLEND, Element, rank
    from sanchopanza.policy import Thresholds
    from sanchopanza.squire import Squire

    elements = [Element.from_dict(e) for e in step["elements"]]
    picture = None
    if images:
        picture = vision.picture_for(page_of(step), rects_of(step), points.element_id)
    before = getattr(arm, "failures", 0)
    squire = Squire(arm, thresholds=Thresholds(max_usd=0.05, max_decisions=80))
    expected = calls_expected(len(elements))
    ranked = await rank(step["task"], elements, squire=squire, done=step["previous"],
                        keep=KEEP, blend=BLEND, picture=picture)  # fmt: skip
    keys = [r.element.key for r in ranked]
    positives = set(step["positives"])
    position = next((i for i, k in enumerate(keys, 1) if k in positives), None)
    return {
        "position": position,
        "top": keys,
        "calls": squire.meter.decisions,
        "usd": round(squire.meter.cost_usd, 7),
        "answered": sum(r.p is not None for r in ranked),
        # A call the Squire's own cap kept from being made never reaches the arm: count calls.
        "failed": getattr(arm, "failures", 0) > before or squire.meter.decisions < expected,
    }


def calls_expected(n: int) -> int:
    """`browse.rank`'s calls for n elements: one per group of 30, and a final round past one."""
    groups = -(-n // points.GROUP_MAX)
    return groups + (1 if groups > 1 else 0)


def rotation(index: int) -> tuple[str, ...]:
    """B2's order of the live arms for the index-th step: rotated, so each goes first a third."""
    k = index % len(B2_ARMS)
    return B2_ARMS[k:] + B2_ARMS[:k]


# ---- running --------------------------------------------------------------------------------


def preflight_or_stop() -> None:
    from sanchopanza.providers.jev import apreflight

    for model in sorted({m for m, _ in ARMS.values()}):
        result = asyncio.run(apreflight(model=model))
        if not result.ok or result.model != model:
            raise SystemExit(f"preflight {model}: {result.reason}, served {result.model}")
        print(f"preflight {model}: ok", file=sys.stderr)


def load_key() -> None:
    if os.environ.get("TYPESAFE_API_KEY"):
        return
    named = os.environ.get("SANCHOPANZA_KEYS_ENV", "")
    if not named or not Path(named).is_file():
        raise SystemExit("TYPESAFE_API_KEY unset and SANCHOPANZA_KEYS_ENV names no file")
    for line in Path(named).read_text(encoding="utf-8").splitlines():
        name, _, value = line.strip().partition("=")
        if name.strip() == "TYPESAFE_API_KEY" and value.strip():
            os.environ["TYPESAFE_API_KEY"] = value.strip().strip('"').strip("'")
            return
    raise SystemExit("no TYPESAFE_API_KEY line in the file SANCHOPANZA_KEYS_ENV names")


def digest(path: Path = PREREG) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_sealed() -> None:
    sealed = PREREG.with_suffix(".sha256")
    if not sealed.exists() or sealed.read_text().strip() != digest():
        raise SystemExit("prereg.md missing or changed since it was sealed: nothing spent")
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *INSTRUMENT, str(PREREG)],
                           cwd=REPO, capture_output=True, text=True, check=True).stdout  # fmt: skip
    if dirty.strip():
        raise SystemExit(f"instrument not committed: {dirty.strip()}: nothing spent")


def provenance() -> dict[str, Any]:
    """What a run ran: the commit, Pillow (the JPEG bytes, so the recording keys, depend on it),
    the ledger."""
    from PIL import __version__ as pillow

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                          text=True, check=False).stdout.strip()  # fmt: skip
    return {"head": head, "pillow": pillow, "ledger": str(LEDGER_PATH)}


def write_rows(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def stop_file() -> bool:
    return (RUN_DIR / "l5" / "STOP").exists()


async def run_b1(steps: list, arms: dict[str, Any], live: bool, rows: list) -> None:
    """Appends one row per step to `rows`, so a halt keeps the steps already done."""
    arm = arms["box14"]
    for start in range(0, len(steps), CONCURRENCY):
        if stop_file():
            raise Halt("STOP file")
        chunk = steps[start : start + CONCURRENCY]
        rows.extend(await asyncio.gather(*(box_step(s, arm) for s in chunk)))
        if live and arm.live_usd > OVERRUN * B1_USD_PER_STEP * len(rows) + 0.01:
            raise Halt(f"B1 overspend: {arm.live_usd:.4f} USD after {len(rows)} steps")
        if arm.mismatch:
            raise Halt(arm.mismatch)
        if arm.failures > 5 or any("SpendCap" in e for e in arm.errors):
            raise Halt(f"B1 failures: {arm.errors[-3:]}")
        print(f"B1 {len(rows)}/{len(steps)} live {arm.live_usd:.4f} USD", file=sys.stderr)


async def run_b2(steps: list, arms: dict[str, Any], live: bool, rows: list) -> None:
    """Appends one row per step (every arm) to `rows`, so a halt keeps the steps already done."""
    estimate = 0.0
    for index, step in enumerate(steps):
        if stop_file():
            raise Halt("STOP file")
        row: dict[str, Any] = {"id": step["id"], "split": step["split"],
                               "website": step["website"], "elements": len(step["elements"]),
                               "order": list(rotation(index))}  # fmt: skip
        for name in rotation(index):
            row[name] = await rank_step(step, arms[name], ARMS[name][1])
        rows.append(row)
        spent = sum(arms[n].live_usd for n in B2_ARMS)
        estimate += sum(B2_USD_PER_STEP.values()) * len(step["elements"]) / 559
        if live and spent > OVERRUN * estimate + 0.02:
            raise Halt(f"B2 overspend: {spent:.4f} USD against {estimate:.4f} estimated")
        errors = [e for n in B2_ARMS for e in arms[n].errors]
        if any(arms[n].mismatch for n in B2_ARMS):
            raise Halt("; ".join(arms[n].mismatch for n in B2_ARMS if arms[n].mismatch))
        if sum(arms[n].failures for n in B2_ARMS) > 10 or any("SpendCap" in e for e in errors):
            raise Halt(f"B2 failures: {errors[-3:]}")
        print(f"B2 {index + 1}/{len(steps)} live {spent:.4f} USD", file=sys.stderr)


async def add_text_113(steps: Sequence[Mapping[str, Any]], smoke: bool) -> dict[str, Any]:
    """The recorded jev-1.13.0 ranking of each step (free); the replay runs the steps in the
    order of 2026-09-30's run so repeated calls get their recorded answers."""
    replay = replay_113(smoke)
    out: dict[str, Any] = {}
    for step in steps:
        out[step["id"]] = await rank_step(step, replay, False)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seal", action="store_true")
    ap.add_argument("--run", choices=("b1", "b2", "t13"))
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    if args.seal:
        PREREG.with_suffix(".sha256").write_text(digest() + "\n", encoding="utf-8")
        print(digest())
        return 0
    if not args.run:
        import l5_report

        report = l5_report.report(OUT, DATA / "confirm")
        (OUT / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(json.dumps(report, indent=1))
        return 0
    steps = load_steps(args.smoke)
    out_dir, fixtures = (SMOKE_DIR, SMOKE_DIR) if args.smoke else (OUT, FIXTURES)
    if args.run == "t13":
        rows = asyncio.run(add_text_113(steps, args.smoke))
        write_rows(out_dir / "rows-t13rec.jsonl", [{"id": k, **v} for k, v in rows.items()])
        return 0
    if args.live:
        if not args.smoke:
            require_sealed()
        load_key()
        preflight_or_stop()
    names = ("box14",) if args.run == "b1" else B2_ARMS
    arms = make_arms(names, args.live, fixtures)
    if args.run == "b2":
        steps = b2_steps(steps, B2_PER_SPLIT)
    if args.limit:
        steps = steps[: args.limit]
    runner = run_b1 if args.run == "b1" else run_b2
    rows: list[dict[str, Any]] = []
    halted = ""
    if args.live:
        print(f"ledger {LEDGER_PATH}, batch {BATCH} cap {BATCH_CAP_USD}", file=sys.stderr)
    try:
        asyncio.run(runner(steps, arms, args.live, rows))
    except Halt as error:
        halted = str(error)
    finally:
        write_rows(out_dir / f"rows-{args.run}.jsonl", rows)
        summary = {"run": args.run, "live": args.live, "steps_planned": len(steps),
                   "steps": len(rows), "halted": halted,
                   "live_usd": {n: round(a.live_usd, 6) for n, a in arms.items()},
                   "live_calls": {n: a.live_calls for n, a in arms.items()},
                   "failures": {n: a.failures for n, a in arms.items()},
                   **provenance()}  # fmt: skip
        (out_dir / f"summary-{args.run}.json").write_text(json.dumps(summary, indent=1),
                                                          encoding="utf-8")  # fmt: skip
        print(json.dumps(summary))
    return 2 if halted else 0


if __name__ == "__main__":
    raise SystemExit(main())
