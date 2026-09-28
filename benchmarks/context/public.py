"""Public agent trajectories as Messages-API messages: the bench's default source.

Dataset: `nebius/SWE-rebench-openhands-trajectories` on Hugging Face, license CC-BY-4.0,
67,074 trajectories (train), revision `35455389ab51bf5e2306bfd436ef72d0f98bf882`.
Qwen3-Coder-480B-A35B-Instruct in OpenHands v0.54.0 resolving real GitHub issues from
nebius/SWE-rebench. Each trajectory is an OpenAI-style message list with structured
`tool_calls` and full tool outputs, so no ReAct text parsing is needed.

`fetch` downloads a seeded sample of pages through the public datasets-server rows API (no
account, no key) into ~/.cache/sanchopanza/context/public/, at most `MAX_ROWS` rows.

Conversion (`to_messages`), recorded here because the rules read Claude Code tool names:

- `execute_bash {command}` -> `Bash {command}`
- `str_replace_editor` `view` -> `Read {file_path, offset, limit}`
- `str_replace_editor` `create` -> `Write {file_path, content}`
- `str_replace_editor` `str_replace` / `insert` / `undo_edit` -> `Edit {file_path, ...rest}`
- anything else (`think`, `finish`, ...) keeps its name and its arguments

`view_range [a, b]` becomes `offset = a`, `limit = b - a + 1` (`b = -1`: to the end, no
limit). The system message is dropped (it is the scaffold's, identical in every row), the
`tool` role becomes a user message of tool_result blocks, consecutive same-role messages
merge. Parallel tool calls stay in one assistant message. A tool message whose id matches no
call is dropped; a call with no result is left out by `calls()`.
"""

from __future__ import annotations

import json
import random
import time
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sanchopanza.context.transcript import merge_consecutive

DATASET = "nebius/SWE-rebench-openhands-trajectories"
LICENSE = "CC-BY-4.0"
REVISION = "35455389ab51bf5e2306bfd436ef72d0f98bf882"
TOTAL_ROWS = 67_074
ROWS_API = "https://datasets-server.huggingface.co/rows"
PAGE = 20
MAX_ROWS = 300
SEED = 20260928
DIR = Path.home() / ".cache" / "sanchopanza" / "context" / "public"
EDITS = frozenset({"str_replace", "insert", "undo_edit"})


def page_offsets(n_rows: int = MAX_ROWS, seed: int = SEED) -> list[int]:
    """Seeded, non-overlapping page starts across the whole split."""
    pages = TOTAL_ROWS // PAGE
    rng = random.Random(seed)
    return sorted(p * PAGE for p in rng.sample(range(pages), n_rows // PAGE))


def fetch(out: Path = DIR, n_rows: int = MAX_ROWS) -> list[Path]:
    """Download the sample, page by page; pages already on disk are not fetched again."""
    if n_rows > MAX_ROWS:
        raise ValueError(f"at most {MAX_ROWS} rows")
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for offset in page_offsets(n_rows):
        path = out / f"rows-{offset:06d}.json"
        if not path.exists():
            url = (
                f"{ROWS_API}?dataset={DATASET}&config=default&split=train"
                f"&offset={offset}&length={PAGE}"
            )
            with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - fixed host
                body = response.read()
            json.loads(body)  # refuse to store an error page as data
            path.write_bytes(body)
            time.sleep(1.0)
        paths.append(path)
    return paths


def rows(directory: Path = DIR) -> list[dict[str, Any]]:
    out = []
    for path in sorted(directory.glob("rows-*.json")):
        page = json.loads(path.read_text(encoding="utf-8"))
        out.extend(r["row"] for r in page.get("rows", []))
    return out


def _arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {"raw": str(raw)}
    return value if isinstance(value, dict) else {"raw": value}


def map_call(name: str, args: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """An OpenHands call as the Claude Code tool the rules know (table in the docstring)."""
    if name == "execute_bash":
        return "Bash", {"command": str(args.get("command", ""))}
    if name != "str_replace_editor":
        return name, dict(args)
    command = args.get("command")
    path = str(args.get("path", ""))
    rest = {k: v for k, v in args.items() if k not in ("command", "path")}
    if command == "view":
        out: dict[str, Any] = {"file_path": path}
        span = args.get("view_range")
        if isinstance(span, Sequence) and len(span) == 2:
            start, end = span
            out["offset"] = start
            if isinstance(end, int) and isinstance(start, int) and end >= start:
                out["limit"] = end - start + 1
        return "Read", out
    if command == "create":
        return "Write", {"file_path": path, "content": str(args.get("file_text", ""))}
    if command in EDITS:
        return "Edit", {"file_path": path, "command": command, **rest}
    return name, dict(args)


def to_messages(trajectory: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    known: set[str] = set()
    for message in trajectory:
        role = message.get("role")
        text = message.get("content") or ""
        if role == "user":
            out.append({"role": "user", "content": [{"type": "text", "text": str(text)}]})
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            if text:
                blocks.append({"type": "text", "text": str(text)})
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                name, args = map_call(
                    str(function.get("name", "")), _arguments(function.get("arguments"))
                )
                known.add(str(call.get("id")))
                blocks.append(
                    {"type": "tool_use", "id": str(call.get("id")), "name": name, "input": args}
                )
            out.append({"role": "assistant", "content": blocks})
        elif role == "tool" and str(message.get("tool_call_id")) in known:
            result = {
                "type": "tool_result",
                "tool_use_id": str(message.get("tool_call_id")),
                "content": str(text),
                "is_error": False,
            }
            out.append({"role": "user", "content": [result]})
    return merge_consecutive(out)
