"""Phase D's plan: which instances, from `validate_d.py`'s output, and in which order. Free.

- `instances`: a complete validation's `selected` list, in its table order (each with
  `instance_id`, `stratum` and `image`; a bare id is taken as one with no stratum).
- `order`: the run order, seeded (20261005) and interleaving the strata, so that no stratum is left
  to the end of the batch, or of the subscription's week.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
VALIDATED = HERE / "singles-validated.json"
ORDER_SEED = 20261005


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def instances(path: Path = VALIDATED) -> list[dict[str, Any]]:
    """The held-out singles in table order, as `validate_d.py` writes them: a complete
    validation's `selected` list (each with `instance_id` and `stratum`; a bare id is taken as
    one with no stratum). Everything that reads the plan reads it here."""
    if not path.exists():
        raise SystemExit(f"no {path.name}: validate the images first (validate_d.py)")
    data = read_json(path)
    if isinstance(data, dict) and data.get("complete") is False:
        raise SystemExit(f"{path.name}: the validation is not complete")
    chosen = data.get("selected") if isinstance(data, dict) else data
    if not isinstance(chosen, list) or not chosen:
        raise SystemExit(f"{path.name}: no `selected` list")
    out = [{"instance_id": item, "stratum": None, "image": None} if isinstance(item, str)
           else {"instance_id": item["instance_id"], "stratum": item.get("stratum"),
                 "image": item.get("image")}
           for item in chosen]  # fmt: skip
    names = [i["instance_id"] for i in out]
    if len(set(names)) != len(names):
        raise SystemExit(f"{path.name}: an instance is listed twice")
    return out


def order(items: list[dict[str, Any]], seed: int = ORDER_SEED) -> list[dict[str, Any]]:
    """The run order: each stratum (in the order they first appear) shuffled with one
    `random.Random(seed)`, then interleaved in proportion: the j-th of a stratum of n sits at
    (j + 0.5) / n, ties in stratum order. With 10 / 10 / 6 a hard instance comes about every
    fourth place, so no stratum is left to the end of the batch (or of the subscription)."""
    rng = random.Random(seed)
    strata = list(dict.fromkeys(str(i.get("stratum")) for i in items))
    placed: list[tuple[float, int, dict[str, Any]]] = []
    for rank, stratum in enumerate(strata):
        members = [i for i in items if str(i.get("stratum")) == stratum]
        rng.shuffle(members)
        placed += [((j + 0.5) / len(members), rank, i) for j, i in enumerate(members)]
    return [i for _, _, i in sorted(placed, key=lambda t: (t[0], t[1]))]
