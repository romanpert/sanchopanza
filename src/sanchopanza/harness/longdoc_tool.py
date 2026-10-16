"""`ask_document`: a multiple-choice question over one long local file, answered by Jev when it is
sure and handed back to the model otherwise. `points.longdoc` as an MCP tool. Opt-in: the
`longdoc` tool set of `python -m sanchopanza.harness.mcp`, nothing in `install`.

    claude mcp add-json --scope user sanchopanza-longdoc \\
        '{"command":"python","args":["-m","sanchopanza.harness.mcp","--tools","longdoc"]}'

**What it substitutes.** In Claude Code, a question about a long file costs the model turns:
it greps and reads parts of the file (lb162x: Opus 5.5 took 3.9 turns and 0.112 USD a LongBench
v2 task, a cost that barely grows with the document, 0.0017 USD per million characters). Every
excerpt read stays in the context and is read again from the cache on every later turn. When
Jev's top choice reaches the cut, the reply is the answer and none of that happens: one Jev call
over the whole file, about 0.005 USD for 400,000 characters (lb162: 0.874 USD over 162).

**What was measured, and nowhere else** (`points.longdoc` has the detail): LongBench v2
four-option questions over documents of more than 100,000 characters; Jev 1.14 with the long
window answering at a top choice of 0.6 or more, 37 % of the tasks. That was no worse than
Sonnet 5.5 alone (+1.2 points [-3.1, +5.6]) and within the -10-point margin of Opus 5.5 alone
(-3.7 [-8.0, +0.6]), saving 33.9 % and 29.5 % of their cost. So the tool hands back:

- a question with other than four options (`points.longdoc` escalates it);
- a file under `MIN_CHARS` (100,000 characters): never measured, and cheap for the model to read;
- an answer under the cut, any refusal, any failure, or no Jev key.

Each of these is a reply that says why and to answer it from the file, never a tool error.

**The cut** is the caller's, in code (`Asker(cut=)`) or `SANCHOPANZA_LONGDOC_CUT`, never the
model's. 0.8 looked closer to Opus post hoc on lb162x (-0.6 points at 17 % coverage); that is
not confirmed. A value in the environment that is not a number in (0, 1] is said on stderr in
one line and the default kept, so the other tool sets of the server still start.

**Money.** Every call goes through `CappedDecider` on the ledger of the day it is made
(`<cache>/longdoc/ask-YYYY-MM-DD.jsonl`, the date read at each call), capped at
`SANCHOPANZA_LONGDOC_CAP_USD` (default `CAP_USD`, 0.50 USD a day). The ledger is a file shared
by every process (`SpendLedger` locks it), so every Claude Code session that runs this server
draws on the same daily cap. A call that does not fit is not made, and the reply says to answer
from the file.

**Files only, local only.** A URL (anything with `://`) is refused before anything is read: a web
page is not the measured case, and the knowledge server's `read` exists for it. Paths only under
the knowledge server's roots, never through a hidden component (`knowledge_tool.Knowledge.load`).
A text file is sent as it is on disk, as LongBench's documents were. A PDF, DOCX or HTML file is
sent as its extracted text (`documents`), which was not measured.

**Cost per question, not per file.** Each question sends the whole file to Jev again: ten
questions on one file cost ten calls.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import math
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .. import _env, documents
from ..contract import DeciderUnavailable
from ..points import longdoc
from .knowledge_tool import Knowledge

TOOL = "ask_document"
DESCRIPTION = (
    "Answer a multiple-choice question about one long local file (txt, md, pdf, docx, html) "
    "without reading it: pass its path, the question and the four options. Returns the answer "
    "when a cheap calibrated model is sure, otherwise says to read the file yourself."
)
MIN_CHARS = 100_000  # LongBench v2's measured documents were all longer
CAP_USD = 0.50  # a day, on the day's ledger
BATCH = "ask_document"
_FROM_ENV = object()


def ledger_dir() -> Path:
    return _env.cache_dir() / "longdoc"


def valid_cut(value: float) -> bool:
    return math.isfinite(value) and 0.0 < value <= 1.0


def valid_cap(value: float) -> bool:
    return math.isfinite(value) and value > 0


def _setting(env: Mapping[str, str], name: str, default: float, valid: Callable) -> float:
    """`SANCHOPANZA_LONGDOC_<name>` as a number, or `default` with one line on stderr when it is
    set but not a valid number."""
    raw = _env.get(f"LONGDOC_{name}", "", env=env).strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if valid(value):
        return value
    sys.stderr.write(f"sanchopanza: SANCHOPANZA_LONGDOC_{name}={raw!r} is not valid; "
                     f"ask_document uses {default}\n")  # fmt: skip
    return default


def _checked(value: float, valid: Callable, what: str) -> float:
    if not valid(value):
        raise ValueError(f"{what} is out of range: {value}")
    return value


class Asker:
    """The tool's logic, with the file reader, the decider and the clock injectable."""

    def __init__(
        self,
        *,
        kit: Knowledge | None = None,
        decider: Any = _FROM_ENV,
        cut: float | None = None,
        cap_usd: float | None = None,
        ledger_dir: Path | None = None,
        env: Mapping[str, str] | None = None,
        min_chars: int = MIN_CHARS,
        today: Callable[[], dt.date] = dt.date.today,
    ) -> None:
        self.env = dict(os.environ) if env is None else dict(env)
        self.cut = (_checked(cut, valid_cut, "the cut (0 < cut <= 1)") if cut is not None
                    else _setting(self.env, "CUT", longdoc.CUT, valid_cut))  # fmt: skip
        self.cap_usd = (_checked(cap_usd, valid_cap, "cap_usd (finite, > 0)") if cap_usd is not None
                        else _setting(self.env, "CAP_USD", CAP_USD, valid_cap))  # fmt: skip
        self.kit = kit or Knowledge(env=self.env)
        self.min_chars = min_chars
        self.today = today
        self._ledger_dir = ledger_dir
        self._given = decider
        self._inner: Any = _FROM_ENV  # the measured JevDecider, built once on first use

    def _measured(self) -> Any:
        """The measured Jev decider, built once (None without a key)."""
        if self._inner is _FROM_ENV:
            key = self.env.get("TYPESAFE_API_KEY", "")
            self._inner = longdoc.measured_decider(key) if key else None
        return self._inner

    def decider_now(self) -> Any:
        """The decider given, or the measured one under the ledger of today (read now)."""
        if self._given is not _FROM_ENV:
            return self._given
        inner = self._measured()
        if inner is None:
            return None
        from ..budget import SpendLedger
        from ..providers.capped import CappedDecider

        folder = self._ledger_dir or ledger_dir()
        folder.mkdir(parents=True, exist_ok=True)
        ledger = SpendLedger(folder / f"ask-{self.today():%Y-%m-%d}.jsonl", cap_usd=self.cap_usd)
        return CappedDecider(inner, ledger=ledger, batch=BATCH, max_usd=self.cap_usd)

    def text_of(self, path: str) -> tuple[str, str]:
        """(the file's text, "") or ("", why it was not read). A URL is refused unread."""
        if "://" in path:
            return "", (f"Refused: {path} is not a local file. ask_document reads local files "
                        "only; use read(url, purpose) for a web page.")  # fmt: skip
        doc = self.kit.load(path)
        if isinstance(doc, str):
            return "", doc
        source = Path(doc.source)
        if documents.kind_of(name=source.name) == "text":
            return source.read_text(encoding="utf-8", errors="replace"), ""
        return "\n\n".join(chunk.text for chunk in doc.page.chunks), ""

    async def ask(self, path: str, question: str, choices: Sequence[str]) -> str:
        """The reply: the answer, a refusal or a handback, never an exception."""
        try:
            return await self._ask(path, question, choices)
        except Exception as error:  # noqa: BLE001 - every failure is a handback, never a tool error
            return _handback(f"{type(error).__name__}: {error}", path)

    async def _ask(self, path: str, question: str, choices: Sequence[str]) -> str:
        text, why = await asyncio.to_thread(self.text_of, path)
        if why:
            return why
        try:
            longdoc.questions(question, list(choices), text or " ")
        except ValueError as error:
            return _handback(str(error), path)
        if len(text) < self.min_chars:
            return _handback(f"{len(text):,} characters; the cut was measured on documents over "
                             f"{self.min_chars:,}", path)  # fmt: skip
        try:
            decider = await asyncio.to_thread(self.decider_now)
        except DeciderUnavailable as error:  # e.g. the jev extra (httpx) is not installed
            return _handback(str(error), path)
        if decider is None:
            return _handback("no decision model configured (TYPESAFE_API_KEY)", path)
        result = await longdoc.answer(decider, text, question, list(choices), cut=self.cut)
        if result.escalate:
            return _handback(result.reason, path)
        option = choices[result.index or 0]
        return (f"Answer: ({result.letter}) {option}. {result.model} chose it at p {result.p} "
                f"(cut {self.cut}), {result.cost_usd:.4f} USD; the file was not read into your "
                "context.")  # fmt: skip

    async def aclose(self) -> None:
        """Close the measured decider's connection, if one was built."""
        inner, self._inner = self._inner, _FROM_ENV
        close = getattr(inner, "aclose", None)
        if callable(close):
            await close()


def _handback(reason: str, path: str) -> str:
    return f"Not answered: {reason}. Read {path} and answer it yourself."


def add_longdoc(server: Any, asker: Asker | None = None) -> Any:
    """Register `ask_document` on an MCP server. The measured decider's connection is left to
    the process's exit: the stdio server has no shutdown hook here (`Asker.aclose` for a caller
    that has one)."""
    tool = asker or Asker()

    @server.tool(name=TOOL, description=DESCRIPTION)
    async def ask_document(path: str, question: str, choices: list[str]) -> str:
        return await tool.ask(path, question, choices)

    return server
