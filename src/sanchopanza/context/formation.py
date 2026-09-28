"""Memory formation at compaction: a stubbed result that holds a durable fact becomes a memory.

Off by default (`SANCHOPANZA_MEMORY_FORMATION=1` turns it on). At compaction the results being
stubbed leave the context; most are gone for good in the sense that nothing needs them, but a
few hold something the project will want in a later session (a version pinned, a decision, an
endpoint's shape). For each of at most `max_items` stubbed results, newest first,
`Squire.remember` is asked with `trust="untrusted"`: a tool result is text the agent read, so
it is scanned for instructions first and a flagged or not fully scanned one is never stored
(review finding M2). What `remember` stores is written as a Claude Code memory file (front
matter `name`, `description`, `type: reference`) in the project's memory directory, with the
reason and the probabilities in the file, and the archive path of the full text. `MEMORY.md`
is not touched: the recall gate reads the files directly, and the index belongs to the owner.

The question is about durability, not about future need in this session: the latter measured
at chance on coding trajectories (docs/results/2026-09-28-context/). This is unmeasured end
to end; it is an opt-in for that reason.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..points.context import head_tail
from . import archive as archive_mod
from .transcript import calls

if TYPE_CHECKING:
    from ..squire import Squire

MAX_ITEMS = 5
FACT_LIMIT = 1_500
PREFIX = "sanchopanza-"


def _about(arguments: Mapping[str, Any]) -> str:
    for key in ("file_path", "command", "pattern", "url", "query", "description"):
        if arguments.get(key):
            return str(arguments[key])[:120]
    return ""


def memory_text(name: str, description: str, body: str) -> str:
    def clean(value: str) -> str:
        return " ".join(value.split()).replace("---", "-")

    return (
        f"---\nname: {clean(name)}\ndescription: {clean(description)}\ntype: reference\n---\n\n"
        f"{body.strip()}\n"
    )


async def form(
    squire: Squire,
    messages: Sequence[Mapping[str, Any]],
    stubbed: Mapping[str, Path],
    memory_dir: Path,
    *,
    max_items: int = MAX_ITEMS,
) -> list[dict[str, Any]]:
    """Ask `remember` about stubbed results; write the stored ones. One record per result asked.

    `stubbed` maps a call id to the archive file of its full text. Never raises on a decider
    failure (`remember` fails closed: nothing stored); an unwritable directory raises OSError.
    """
    found = {c.id: c for c in calls(messages) if c.id in stubbed}
    newest = sorted(found.values(), key=lambda c: c.result_msg, reverse=True)[:max_items]
    records: list[dict[str, Any]] = []
    for call in newest:
        about = _about(call.input)
        source = f"{call.tool} {about}".strip()
        fact = f"Output of {source}:\n{head_tail(call.result, FACT_LIMIT)}"
        verdict = await squire.remember(fact, source=source, trust="untrusted")
        record = {
            "id": call.id,
            "tool": call.tool,
            "stored": verdict.store,
            "reason": verdict.reason,
            "durable": verdict.durable,
            "specific": verdict.specific,
            "derivable": verdict.derivable,
        }
        if verdict.store:
            memory_dir.mkdir(parents=True, exist_ok=True)
            path = memory_dir / f"{PREFIX}{archive_mod.safe_name(call.id)}.md"
            why = (
                f"Stored by sanchopanza at compaction: {verdict.reason} (durable "
                f"{verdict.durable:.2f}, specific {verdict.specific:.2f}, derivable "
                f"{verdict.derivable:.2f}). Full text: {stubbed[call.id]}"
            )
            body = f"{head_tail(call.result, FACT_LIMIT)}\n\n{why}"
            path.write_text(
                memory_text(source or call.tool, f"Tool output kept from {source}", body),
                encoding="utf-8",
            )
            record = {**record, "file": str(path)}
        records.append(record)
        squire.journal.record("memory_formation", record)
    return records
