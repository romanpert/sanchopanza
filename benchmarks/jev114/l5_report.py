"""The analysis sealed in docs/results/2026-10-15-jev114-l5/prereg.md, from the rows `l5.py`
writes (rows-b1.jsonl, rows-b2.jsonl, rows-t13rec.jsonl) and the steps' labels. Free, no network.

Paired statistics are lot L4's (`l4_stats`): exact McNemar, a paired item bootstrap (10,000
replicas, seed 20261015), Holm. Verdicts: "mejora" (difference > 0, Holm p < 0.05), "peor"
(difference < 0, Holm p < 0.05), "no peor" (CI lower bound above -2 points), otherwise
"no concluyente".
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import l4_stats as st  # noqa: E402

MIND2WEB = Path.home() / ".cache" / "sanchopanza" / "mind2web"
KS = (1, 5, 10, 20, 30)
FUSE_K = 10
B2_PRIMARY = {"image_effect_r10": ("i14", "t14", 10), "model_effect_r10": ("i14", "i13", 10)}
B2_ARMS = ("t14", "i14", "i13")
MIN_N = 20  # fewer paired steps than this: "no medido"


def read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def labels(path: Path = MIND2WEB / "steps-confirm.jsonl") -> dict[str, dict[str, Any]]:
    out = {}
    for row in read_rows(path):
        names = {e["key"]: e.get("name", "") for e in row["elements"]}
        out[row["id"]] = {"positives": set(row["positives"]),
                          "wordless": all(not names.get(p, "").strip()
                                          for p in row["positives"])}  # fmt: skip
    return out


def verdict(result: Mapping[str, Any], adjusted_p: float) -> str:
    if result.get("diff") is None or result.get("ci95") is None:
        return "no medido"
    if result.get("n", 0) < MIN_N:
        return "no medido"
    if result["diff"] > 0 and adjusted_p < st.ALPHA:
        return "mejora"
    if result["diff"] < 0 and adjusted_p < st.ALPHA:
        return "peor"
    if result["ci95"][0] > st.NOT_WORSE:
        return "no peor"
    return "no concluyente"


def fuse(text_top: Sequence[str], by_box: Sequence[Sequence[Any]], k: int = FUSE_K) -> str | None:
    """Among the text ranking's first `k`, the element whose box best overlaps the Box answer
    (ties: the better text rank); the text's first when none overlaps it at all."""
    if not text_top:
        return None
    overlap = {key: float(score) for key, score in by_box}
    head = list(text_top[:k])
    best = max(head, key=lambda key: (overlap.get(key, 0.0), -head.index(key)))
    return best if overlap.get(best, 0.0) > 0 else head[0]


def first_of(by_box: Sequence[Sequence[Any]] | None) -> str | None:
    return by_box[0][0] if by_box else None


def compare(new: Sequence[bool], old: Sequence[bool], clusters: Sequence[str]) -> dict[str, Any]:
    return st.paired_binary(list(new), list(old), list(clusters))


def b1(rows: list, text13: Mapping[str, Any], b2_rows: list, truth: Mapping) -> dict[str, Any]:
    by_id = {r["id"]: r for r in rows}
    ids = [i for i in by_id if i in text13 and i in truth]
    pos = {i: truth[i]["positives"] for i in ids}
    web = [by_id[i]["website"] for i in ids]

    def hit(key: str | None, i: str) -> bool:
        return key is not None and key in pos[i]

    box1 = [hit(first_of(by_id[i].get("by_box")), i) for i in ids]
    zoom1 = [hit(first_of(by_id[i].get("by_zoom")), i) for i in ids]
    t13 = [hit((text13[i]["top"] or [None])[0], i) for i in ids]
    fuse13 = [hit(fuse(text13[i]["top"], by_id[i].get("by_box") or []), i) for i in ids]
    primary = compare(box1, t13, web)
    out: dict[str, Any] = {
        "steps": len(ids),
        "failed_steps": sum(bool(by_id[i].get("failed")) for i in ids),
        "no_box": sum(not by_id[i].get("by_box") for i in ids),
        "box_top1": round(sum(box1) / len(ids), 4) if ids else None,
        "text13rec_top1": round(sum(t13) / len(ids), 4) if ids else None,
        "primary_box_minus_text13rec": {**primary, "verdict": verdict(primary, primary["p"])},
        "zoom_minus_text13rec": compare(zoom1, t13, web),
        "zoom_minus_box": compare(zoom1, box1, web),
        "fuse10_13_minus_text13rec": {**(f := compare(fuse13, t13, web)),
                                      "verdict_unadjusted": verdict(f, f["p"])},
        "box_recall": {f"@{k}": round(sum(
            any(key in pos[i] for key, _ in (by_id[i].get("by_box") or [])[:k]) for i in ids
        ) / len(ids), 4) for k in KS} if ids else {},  # fmt: skip
    }
    b2_by_id = {r["id"]: r for r in b2_rows
                if all(a in r and not r[a].get("failed") for a in B2_ARMS)}
    sub = [i for i in ids if i in b2_by_id]
    if sub:
        t14 = [hit((b2_by_id[i]["t14"]["top"] or [None])[0], i) for i in sub]
        box_s = [hit(first_of(by_id[i].get("by_box")), i) for i in sub]
        fuse14 = [hit(fuse(b2_by_id[i]["t14"]["top"], by_id[i].get("by_box") or []), i)
                  for i in sub]  # fmt: skip
        sub_web = [by_id[i]["website"] for i in sub]
        out["box_minus_text14"] = compare(box_s, t14, sub_web)
        out["fuse10_14_minus_text14"] = compare(fuse14, t14, sub_web)
    shown = [(by_id[i].get("shown"), b) for i, b in zip(ids, box1, strict=True)]
    scored = [(p, b) for p, b in shown if p is not None]
    out["shown_auc_for_box_top1"] = st.auc([p for p, b in scored if b], [p for p, b in scored if not b])
    out["usd"] = round(sum(by_id[i].get("usd", 0.0) for i in ids), 6)
    return out


def recall_at(row: Mapping[str, Any], k: int) -> bool:
    return row["position"] is not None and row["position"] <= k


def b2(rows: list, text13: Mapping[str, Any], truth: Mapping) -> dict[str, Any]:
    arms = B2_ARMS
    done = [r for r in rows if r["id"] in truth and all(a in r for a in arms)]
    whole = [r for r in done if not any(r[a]["failed"] for a in arms)]
    web = [r["website"] for r in whole]
    out: dict[str, Any] = {"steps": len(done), "complete": len(whole),
                           "excluded_failed": len(done) - len(whole)}  # fmt: skip
    if not whole:
        return out
    out["recall"] = {
        arm: {f"@{k}": round(sum(recall_at(r[arm], k) for r in whole) / len(whole), 4)
              for k in KS}
        for arm in arms
    }  # fmt: skip
    t13 = [text13.get(r["id"]) for r in whole]
    if all(t is not None for t in t13):
        out["recall"]["t13rec"] = {
            f"@{k}": round(sum(recall_at(t, k) for t in t13) / len(whole), 4) for k in KS
        }
    primary = {name: compare([recall_at(r[a], k) for r in whole],
                             [recall_at(r[b], k) for r in whole], web)
               for name, (a, b, k) in B2_PRIMARY.items()}  # fmt: skip
    adjusted = st.holm({name: res["p"] for name, res in primary.items()})
    out["primary"] = {name: {**res, "p_holm": adjusted[name],
                             "verdict": verdict(res, adjusted[name])}
                      for name, res in primary.items()}  # fmt: skip
    secondary: dict[str, Any] = {}
    for k in (1, 20, 30):
        secondary[f"image_effect_r{k}"] = compare([recall_at(r["i14"], k) for r in whole],
                                                 [recall_at(r["t14"], k) for r in whole], web)
        secondary[f"model_effect_r{k}"] = compare([recall_at(r["i14"], k) for r in whole],
                                                 [recall_at(r["i13"], k) for r in whole], web)
    if all(t is not None for t in t13):
        for k in (1, 10, 20):
            secondary[f"image_on_113_vs_rec_r{k}"] = compare(
                [recall_at(r["i13"], k) for r in whole], [recall_at(t, k) for t in t13], web)
            secondary[f"text14_vs_rec_r{k}"] = compare(
                [recall_at(r["t14"], k) for r in whole], [recall_at(t, k) for t in t13], web)
    out["secondary"] = secondary
    wordless = [r for r in whole if truth[r["id"]]["wordless"]]
    out["wordless"] = {"steps": len(wordless), **{
        arm: {f"@{k}": sum(recall_at(r[arm], k) for r in wordless) for k in (1, 10, 20)}
        for arm in arms}}  # fmt: skip
    out["usd_per_step"] = {arm: round(sum(r[arm]["usd"] for r in whole) / len(whole), 6)
                           for arm in arms}  # fmt: skip
    out["calls_per_step"] = {arm: round(sum(r[arm]["calls"] for r in whole) / len(whole), 2)
                             for arm in arms}  # fmt: skip
    return out


def product(out: Mapping[str, Any]) -> dict[str, Any]:
    """The sealed product rule: a vision mode is recommended when, with Holm across the three,
    BOX or FUSE10 beats TEXT13 at top 1, or the image lifts R@10 (i14 against t14)."""
    family: dict[str, Mapping[str, Any]] = {}
    if out.get("b1"):
        family["box_minus_text13rec"] = out["b1"]["primary_box_minus_text13rec"]
        family["fuse10_13_minus_text13rec"] = out["b1"]["fuse10_13_minus_text13rec"]
    if out.get("b2") and out["b2"].get("primary"):
        family["image_effect_r10"] = out["b2"]["primary"]["image_effect_r10"]
    adjusted = st.holm({name: res["p"] for name, res in family.items()}) if family else {}
    verdicts = {name: verdict(res, adjusted[name]) for name, res in family.items()}
    complete = set(family) == {"box_minus_text13rec", "fuse10_13_minus_text13rec",
                               "image_effect_r10"}  # fmt: skip
    build = any(v == "mejora" for v in verdicts.values())
    return {"p_holm": adjusted, "verdicts": verdicts, "complete": complete,
            "vision_mode": "recomendado" if build else "no recomendado"}  # fmt: skip


def centre_in(rect: Sequence[float] | None, boxes: Mapping[str, Sequence[float]],
              positives: set[str]) -> bool:  # fmt: skip
    """The predicted box's centre lies inside a positive's box (pointing accuracy)."""
    if not rect:
        return False
    cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
    for key in positives:
        box = boxes.get(key)
        if box and box[0] <= cx <= box[0] + box[2] and box[1] <= cy <= box[1] + box[3]:
            return True
    return False


def report(out_dir: Path, shots: Path | None = None,
           read_labels: Callable[[], Mapping] = labels) -> dict[str, Any]:  # fmt: skip
    truth = read_labels()
    text13 = {r["id"]: r for r in read_rows(out_dir / "rows-t13rec.jsonl")}
    b1_rows = read_rows(out_dir / "rows-b1.jsonl")
    b2_rows = read_rows(out_dir / "rows-b2.jsonl")
    if shots is not None and (shots / "boxes.jsonl").exists():
        boxes = {r["id"]: r["boxes"] for r in read_rows(shots / "boxes.jsonl")}
        b1_rows = [{**r, "centre_in_positive": centre_in(
            r.get("rect"), boxes.get(r["id"], {}), truth.get(r["id"], {}).get("positives", set()))}
            for r in b1_rows]  # fmt: skip
    out: dict[str, Any] = {"b1": b1(b1_rows, text13, b2_rows, truth) if b1_rows else None,
                           "b2": b2(b2_rows, text13, truth) if b2_rows else None}  # fmt: skip
    if b1_rows and out["b1"] and out["b1"]["steps"]:
        out["b1"]["box_centre_in_positive"] = round(
            sum(bool(r.get("centre_in_positive")) for r in b1_rows) / len(b1_rows), 4)
    out["product"] = product(out)
    return out
