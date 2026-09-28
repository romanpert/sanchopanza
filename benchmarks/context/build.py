"""Build the context-pruning dataset. Free; the public source downloads once, then offline.

    python benchmarks/context/build.py --fetch      # download the public sample (300 rows)
    python benchmarks/context/build.py              # build from the public trajectories
    python benchmarks/context/build.py --scan-only  # counts, writes nothing
    python benchmarks/context/build.py --source claude-code   # optional, off by default

Default source since Amendment 1 of `prereg.md`: public OpenHands trajectories
(`public.py`: nebius/SWE-rebench-openhands-trajectories, CC-BY-4.0). The Claude Code source
below stays available but is never used unless asked for by name.

Writes ONLY under ~/.cache/sanchopanza/context/dataset/ (never in the repository): one JSON
per unit with the history messages, the future messages and the labels, all passed through
`sanchopanza.redact.redact_secrets`, and a manifest that names units by hash, not by path.

Claude Code source. A project directory is admitted only when its name contains an allowlisted
public-repo word (`sanchopanza`, `sancho`) and none of the private words in `DENY`. Nothing
else is read past its directory name. There is deliberately no switch to admit sessions from
a private project's directory, even when they worked on the public repository: widening the
pool is the owner's decision, made by editing `ALLOW` and amending `prereg.md`.

A unit is one public trajectory, or one Claude Code context (a stretch between compactions).
The cut is the message where the cumulative characters reach 60 % of the unit; the history
before it must hold >= 30 tool results and >= 100,000 characters of them (Amendment 1; it was
40 / 150,000). A unit where the redactor fires on something that looks like a live key
(24+ characters, high entropy, no placeholder marker) is dropped, not masked.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import random
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))


def sibling(name: str):
    """A file of this directory as module `context_bench_<name>`: several benches ship a
    `labels.py` or a `run.py`, so a plain import could pick up another bench's file."""
    key = f"context_bench_{name}"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, HERE / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


label = sibling("labels").label
strings_of = sibling("labels").strings_of
segments = sibling("transcript").segments
public = sibling("public")

from sanchopanza.context.transcript import calls  # noqa: E402
from sanchopanza.redact import PATTERNS, redact_secrets  # noqa: E402

PROJECTS = Path.home() / ".claude" / "projects"
CACHE = Path.home() / ".cache" / "sanchopanza" / "context"
SEED = 20260928
TARGET = 40
DEV_SHARE = 15 / 40
CUT_SHARE = 0.60
# Amendment 1 of prereg.md: 40 / 150,000 admitted 19 of the 300 public trajectories, so the
# floor went to 30 results / 100,000 characters (124 of 300) before any measurement.
MIN_RESULTS = 30
MIN_RESULT_CHARS = 100_000
ALLOW = ("sanchopanza", "sancho")
DENY = (
    "indagis",
    "farmacia",
    "empresa",
    "labzero",
    "personal",
    "vida",
    "innovate",
    "redes-sociales",
    "investigacion",
    "memory",
)
PLACEHOLDER = ("xxxx", "your_", "your-", "example", "dummy", "placeholder", "...", "<", "redacted")


def project_admitted(name: str) -> bool:
    low = name.lower()
    return any(w in low for w in ALLOW) and not any(w in low for w in DENY)


def entropy(text: str) -> float:
    counts = Counter(text)
    n = len(text)
    return -sum(c / n * math.log2(c / n) for c in counts.values())


def looks_live(match: str) -> bool:
    if "PRIVATE KEY" in match:
        return True
    low = match.lower()
    if any(p in low for p in PLACEHOLDER) or len(match) < 24:
        return False
    return entropy(match) >= 3.5


def live_keys(messages: Sequence[Mapping[str, Any]]) -> int:
    found = 0
    for text in strings_of(list(messages)):
        for pattern in PATTERNS:
            found += sum(looks_live(m.group(0)) for m in pattern.finditer(text))
    return found


def size(message: Mapping[str, Any]) -> int:
    total = 0
    for block in message.get("content", []):
        if block.get("type") == "text":
            total += len(block.get("text", ""))
        elif block.get("type") == "tool_use":
            total += len(json.dumps(block.get("input"), ensure_ascii=False))
        elif block.get("type") == "tool_result":
            total += len(str(block.get("content", "")))
    return total


def cut_index(messages: Sequence[Mapping[str, Any]], share: float = CUT_SHARE) -> int:
    """History is messages[:index]: the first prefix reaching `share` of the characters,
    moved forward so a tool_use is never separated from its result."""
    sizes = [size(m) for m in messages]
    goal = share * sum(sizes)
    running = 0
    index = len(messages)
    for i, s in enumerate(sizes):
        running += s
        if running >= goal:
            index = i + 1
            break
    last = messages[index - 1] if index else None
    if (
        last
        and last["role"] == "assistant"
        and any(b.get("type") == "tool_use" for b in last["content"])
    ):
        index = min(index + 1, len(messages))
    return index


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def unit_from(messages: list[dict[str, Any]], session: str, part: int) -> dict[str, Any] | None:
    """One context as a unit, or None when it is too small or has no future."""
    index = cut_index(messages)
    history, future = messages[:index], messages[index:]
    if not any(m["role"] == "assistant" for m in future):
        return None
    before = calls(history)
    if len(before) < MIN_RESULTS or sum(c.chars for c in before) < MIN_RESULT_CHARS:
        return None
    history = redact_secrets(history)
    future = redact_secrets(future)
    return {
        "unit": digest(f"{session}:{part}"),
        "session": digest(session),
        "history": history,
        "future": future,
        "labels": label(history, future, calls(history)),
    }


def scan(root: Path, *, stats: Counter) -> Iterable[tuple[str, dict[str, Any]]]:
    """(project kind, unit) for every admitted unit under `root`."""
    for project in sorted(p for p in root.iterdir() if p.is_dir()):
        if not project_admitted(project.name):
            stats["projects_excluded"] += 1
            continue
        stats["projects_admitted"] += 1
        kind = next(w for w in ALLOW if w in project.name.lower())
        for path in sorted(project.glob("*.jsonl")):
            stats["sessions_scanned"] += 1
            contexts = segments(path)
            if any(live_keys(ctx) for ctx in contexts):
                stats["sessions_dropped_live_key"] += 1
                continue
            for part, messages in enumerate(contexts):
                unit = unit_from(messages, path.stem, part)
                if unit is None:
                    stats["contexts_too_small"] += 1
                    continue
                yield kind, unit


def scan_public(directory: Path, *, stats: Counter) -> Iterable[tuple[str, dict[str, Any]]]:
    """(source, unit) for every public trajectory that passes the floor."""
    for row in public.rows(directory):
        stats["trajectories_scanned"] += 1
        messages = public.to_messages(row.get("trajectory") or [])
        if live_keys(messages):
            stats["trajectories_dropped_live_key"] += 1
            continue
        unit = unit_from(messages, str(row.get("trajectory_id")), 0)
        if unit is None:
            stats["trajectories_too_small"] += 1
            continue
        yield "swe-rebench-openhands", unit


def split(units: Sequence[Mapping[str, Any]], seed: int = SEED) -> dict[str, str]:
    """unit -> "dev" | "test", whole sessions to one side, ordered by a seeded hash."""
    sessions = sorted({u["session"] for u in units}, key=lambda s: digest(f"{seed}:{s}"))
    goal = round(DEV_SHARE * len(units))
    dev: set[str] = set()
    taken = 0
    for s in sessions:
        if taken >= goal:
            break
        dev.add(s)
        taken += sum(u["session"] == s for u in units)
    return {u["unit"]: "dev" if u["session"] in dev else "test" for u in units}


def summary(unit: Mapping[str, Any]) -> dict[str, Any]:
    labels = unit["labels"].values()
    return {
        "results": len(unit["labels"]),
        "result_chars": sum(v["chars"] for v in labels),
        "needed": sum(v["needed"] for v in labels),
        "needed_before_refetch": sum(v["needed_before_refetch"] for v in labels),
        "reread": sum(v["reread"] for v in labels),
    }


def build(
    root: Path, out: Path, *, write: bool = True, seed: int = SEED, source: str = "public"
) -> dict[str, Any]:
    """`root` is the public sample directory, or ~/.claude/projects for `claude-code`."""
    stats: Counter = Counter()
    if source == "public":
        found = list(scan_public(root, stats=stats))
    elif source == "claude-code":
        found = list(scan(root, stats=stats))
    else:
        raise ValueError(f"unknown source {source!r}")
    rng = random.Random(seed)
    if len(found) > TARGET:
        found = rng.sample(sorted(found, key=lambda x: x[1]["unit"]), TARGET)
    units = [u for _, u in found]
    sides = split(units, seed)
    manifest = {
        "seed": seed,
        "source": source,
        "dataset": (
            {"name": public.DATASET, "license": public.LICENSE, "revision": public.REVISION}
            if source == "public"
            else None
        ),
        "rule": {
            "allow": ALLOW if source == "claude-code" else None,
            "deny": DENY if source == "claude-code" else None,
            "cut_share": CUT_SHARE,
            "min_results": MIN_RESULTS,
            "min_result_chars": MIN_RESULT_CHARS,
        },
        "stats": dict(stats),
        "units": [
            {"unit": u["unit"], "session": u["session"], "kind": k, "split": sides[u["unit"]]}
            | summary(u)
            for k, u in found
        ],
    }
    if write:
        data = out / "dataset"
        data.mkdir(parents=True, exist_ok=True)
        for old in data.glob("*.json"):
            old.unlink()
        for kind, u in found:
            body = {**u, "kind": kind, "split": sides[u["unit"]]}
            (data / f"{u['unit']}.json").write_text(
                json.dumps(body, ensure_ascii=False), encoding="utf-8"
            )
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--source", choices=("public", "claude-code"), default="public")
    p.add_argument("--fetch", action="store_true", help="download the public sample first")
    p.add_argument("--projects", type=Path, default=None)
    p.add_argument("--out", type=Path, default=CACHE)
    p.add_argument("--scan-only", action="store_true")
    args = p.parse_args()
    if ROOT in args.out.resolve().parents or args.out.resolve() == ROOT:
        raise SystemExit("the dataset never goes inside the repository")
    if args.fetch:
        public.fetch()
    default = public.DIR if args.source == "public" else PROJECTS
    root = args.projects or default
    manifest = build(root, args.out, write=not args.scan_only, source=args.source)
    units = manifest["units"]
    print(json.dumps(manifest["stats"]))
    print(f"units {len(units)}: " + json.dumps(Counter(u["kind"] for u in units)))
    print("split " + json.dumps(Counter(u["split"] for u in units)))
    sessions = {u["session"] for u in units}
    print(f"sessions {len(sessions)}")


if __name__ == "__main__":
    main()
