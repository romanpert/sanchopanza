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
- an answer under the cut, any refusal, or no Jev key.

Each of these is a reply that says why and to answer it from the file, never an error.

**The cut** is the caller's, in code (`Asker(cut=)`) or `SANCHOPANZA_LONGDOC_CUT`, never the
model's. 0.8 looked closer to Opus post hoc on lb162x (-0.6 points at 17 % coverage); that is
not confirmed.

**Money.** Every call goes through `CappedDecider` on a ledger of the day
(`~/.cache/sanchopanza/longdoc/ask-YYYY-MM-DD.jsonl`), capped at `SANCHOPANZA_LONGDOC_CAP_USD`
(default `CAP_USD`, 0.50 USD a day). A call that does not fit is not made, and the reply says to
answer from the file.

**Files.** Only under the knowledge server's roots, never through a hidden component
(`knowledge_tool.Knowledge.load`). A text file is sent as it is on disk, as LongBench's documents
were. A PDF, DOCX or HTML file is sent as its extracted text (`documents`), which was not
measured.

**Cost per question, not per file.** Each question sends the whole file to Jev again: ten
questions on one file cost ten calls.
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Mapping, Sequence
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
    return Path.home() / ".cache" / "sanchopanza" / "longdoc"


def _float(raw: str, default: float) -> float:
    try:
        return float(raw) if raw.strip() else default
    except ValueError:
        return default


class Asker:
    """The tool's logic, with the file reader and the decider injectable."""

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
    ) -> None:
        self.env = dict(os.environ) if env is None else dict(env)
        self.cut = cut if cut is not None else _float(_env.get("LONGDOC_CUT", "", env=self.env),
                                                      longdoc.CUT)  # fmt: skip
        if not 0.0 < self.cut <= 1.0:
            raise ValueError(f"the cut is a probability in (0, 1], not {self.cut}")
        self.cap_usd = cap_usd if cap_usd is not None else _float(
            _env.get("LONGDOC_CAP_USD", "", env=self.env), CAP_USD)  # fmt: skip
        self.kit = kit or Knowledge(env=self.env)
        self.min_chars = min_chars
        self._ledger_dir = ledger_dir
        self._decider = decider

    @property
    def decider(self) -> Any:
        """The decider given, or the measured one under the day's ledger when a key is set
        (None without a key)."""
        if self._decider is _FROM_ENV:
            self._decider = self._from_env()
        return self._decider

    def _from_env(self) -> Any:
        key = self.env.get("TYPESAFE_API_KEY", "")
        if not key:
            return None
        from ..budget import SpendLedger
        from ..providers.capped import CappedDecider

        folder = self._ledger_dir or ledger_dir()
        folder.mkdir(parents=True, exist_ok=True)
        ledger = SpendLedger(folder / f"ask-{dt.date.today():%Y-%m-%d}.jsonl", cap_usd=self.cap_usd)
        return CappedDecider(longdoc.measured_decider(key), ledger=ledger, batch=BATCH,
                             max_usd=self.cap_usd)  # fmt: skip

    def text_of(self, path: str) -> tuple[str, str]:
        """(the file's text, "") or ("", why it was not read)."""
        doc = self.kit.load(path)
        if isinstance(doc, str):
            return "", doc
        source = Path(doc.source)
        if documents.kind_of(name=source.name) == "text":
            return source.read_text(encoding="utf-8", errors="replace"), ""
        return "\n\n".join(chunk.text for chunk in doc.page.chunks), ""

    async def ask(self, path: str, question: str, choices: Sequence[str]) -> str:
        text, why = self.text_of(path)
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
            decider = self.decider
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


def _handback(reason: str, path: str) -> str:
    return f"Not answered: {reason}. Read {path} and answer it yourself."


def add_longdoc(server: Any, asker: Asker | None = None) -> Any:
    """Register `ask_document` on an MCP server."""
    tool = asker or Asker()

    @server.tool(name=TOOL, description=DESCRIPTION)
    async def ask_document(path: str, question: str, choices: list[str]) -> str:
        return await tool.ask(path, question, choices)

    return server
