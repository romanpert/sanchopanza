"""v4.1 candidate rules (the v4 review's fixes, each a switch) on items of build_v4b.py. Free.

    python benchmarks/memory_real/variants_v4b.py [--items F]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build_v4b import tokens  # noqa: E402
from score import CACHE, OUT, metrics  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402

COMMON = re.compile(r"^(import |from \S+ import |#include|using |require\(|package |@\w|"
                    r"export \* from|const \w+ = require\()")  # fmt: skip


@dataclass(frozen=True)
class Rule:
    name: str
    newest_k: int = 0  # v3: the k newest, nothing else
    per_file: bool = True
    blame: bool = True
    token_norm: bool = False
    skip_common: bool = False
    least: int = 1
    empty_read: bool = False  # at a Read with no hit: the newest record with no lines here
    partial_read: bool = False  # at a partial Read with no hit: the newest
    edit_once: bool = False  # the edit fallback only if nothing was given for the path
    fraction: bool = False  # score = lines in view / lines the record wrote in the file


def load(path: Path) -> list[dict[str, Any]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if item["pool"]:
            out.append({**item, "pool": [ep.Episode.from_dict(d) for d in item["pool"]]})
    return out


def run(items: list[dict[str, Any]], rule: Rule) -> tuple[dict[int, list[str]], int]:
    shown: dict[int, list[str]] = {}
    given: dict[str, set[str]] = {}
    given_path: dict[str, set[str]] = {}
    chars = 0
    for n in sorted(range(len(items)), key=lambda n: (items[n]["session"], items[n]["index"])):
        item = items[n]
        at = {e.key: e.at for e in item["pool"]}
        size = {e.key: len(e.text()) for e in item["pool"]}
        changed = {e.key: set(e.changed_raw or e.changed) for e in item["pool"]}
        seen_keys = given.setdefault(item["session"], set())
        seen_paths = given_path.setdefault(item["session"], set())
        out: list[str] = []
        for touch in item["touches"]:
            path, tool = touch["path"], touch["tool"]
            matching = [k for k in at if path in changed[k]]
            fresh = [k for k in matching if k not in seen_keys]
            if not fresh:
                continue
            newest = sorted(fresh, key=lambda k: -at[k])
            if rule.newest_k:
                pick = newest[: rule.newest_k]
            else:
                norm = tokens if rule.token_norm else (lambda s: s)

                def lines_of(k: str, item: dict[str, Any] = item, path: str = path,
                             norm: Any = norm) -> set[str]:  # fmt: skip
                    f = item["per_file"].get(k, {})
                    raw = f.get(path, []) if rule.per_file else [x for v in f.values() for x in v]
                    return {norm(x) for x in raw if not (rule.skip_common and COMMON.match(x))}

                view = {norm(x) for x in touch["seen"]
                        if not (rule.skip_common and COMMON.match(x))}  # fmt: skip
                written = {k: lines_of(k) & view for k in matching}
                if rule.blame:  # each line to the newest record that wrote it
                    owner: dict[str, str] = {}
                    for k in sorted(matching, key=lambda k: at[k]):
                        for x in written[k]:
                            owner[x] = k
                    score = {k: sum(1 for o in owner.values() if o == k) for k in fresh}
                else:
                    score = {k: len(written[k]) for k in fresh}
                if rule.fraction:
                    score = {k: score[k] / max(1, len(lines_of(k))) for k in fresh}
                hits = [k for k in newest if score[k] > 0 and len(written[k]) >= rule.least]
                pick = sorted(hits, key=lambda k: -score[k])[:1]
                if not pick and tool != "Read" and not (rule.edit_once and path in seen_paths):
                    pick = newest[:1]
                if not pick and tool == "Read" and rule.partial_read and touch["partial"]:
                    pick = newest[:1]
                if not pick and tool == "Read" and rule.empty_read:
                    pick = [k for k in newest if not lines_of(k)][:1]
            for k in pick:
                seen_keys.add(k)
                seen_paths.add(path)
                out.append(k)
                chars += size[k]
        shown[n] = out
    return shown, chars


RULES = [
    Rule("v3: newest x2", newest_k=2),
    Rule("v4.0: flat lines, most overlap", per_file=False, blame=False),
    Rule("per file", blame=False),
    Rule("per file + blame"),
    Rule("per file + blame + skip common", skip_common=True),
    Rule("per file + blame + tokens", token_norm=True),
    Rule("per file + blame + skip common + tokens", skip_common=True, token_norm=True),
    Rule("... + least 2", skip_common=True, token_norm=True, least=2),
    Rule("... + empty read", skip_common=True, token_norm=True, empty_read=True),
    Rule("... + partial read", skip_common=True, token_norm=True, partial_read=True),
    Rule("... + edit once", skip_common=True, token_norm=True, edit_once=True),
    Rule("per file + blame + common + tokens, fraction", skip_common=True, token_norm=True,
         fraction=True),
    Rule("per file + common + tokens, fraction (no blame)", skip_common=True, token_norm=True,
         fraction=True, blame=False),
    Rule("... + empty read + partial + edit once", skip_common=True, token_norm=True,
         empty_read=True, partial_read=True, edit_once=True),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", default=str(CACHE / "items-v4b.jsonl"))
    parser.add_argument("--tag", default="dev")
    args = parser.parse_args(argv)
    items = load(Path(args.items))
    rows = {}
    for rule in RULES:
        shown, chars = run(items, rule)
        m = metrics(items, shown)
        rows[rule.name] = {**m, "chars_per_request": round(chars / len(items))}
        print(rule.name.ljust(44), " | ".join(
            f"{s}: R {m[s]['recall']} P {m[s]['precision']} N {m[s]['noise']}"
            for s in ("all/any", "all/lineage")), f"| ch {round(chars / len(items))}")
    target = OUT / f"variants-v4b-{args.tag}.json"
    target.write_text(json.dumps(rows, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
