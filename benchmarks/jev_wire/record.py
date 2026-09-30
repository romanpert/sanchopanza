"""Record one raw Jev response, exactly as the wire returned it: one Truth, one Choice, one Score.

    python benchmarks/jev_wire/record.py [--env-file PATH]

Writes `fixtures/jev-wire-raw.json`. Every other recording in this repository stores answers
after `providers.jev.from_wire` has converted them, so none can say what the provider sends; a
test over those recordings once passed for a claim about the wire that it could not check
(retracted 2026-09-30). `tests/test_jev_wire.py` reads this file instead. Re-record it when the
pinned model changes. One call, a few hundred input tokens (about 0.00003 USD).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from sanchopanza.contract import Choice, Score, Truth
from sanchopanza.providers.jev import DEFAULT_MODEL, JevDecider, to_wire

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "fixtures" / "jev-wire-raw.json"
STATE = {"text": "The invoice was paid on 3 March, two days after the reminder was sent."}
QUESTIONS = {
    "paid": Truth("Does `text` say the invoice was paid?"),
    "when": Choice("When was the invoice paid, relative to the reminder?",
                   options={"before": "paid before the reminder", "after": "paid after it",
                            "unknown": "`text` does not say"}),  # fmt: skip
    "urgency": Score("How urgent does `text` make the matter sound?",
                     levels=["not urgent", "somewhat urgent", "very urgent"]),  # fmt: skip
}


def key_from(env_file: str) -> str:
    key = os.environ.get("TYPESAFE_API_KEY", "")
    if not key and env_file:
        for line in Path(env_file).read_text(encoding="utf-8").splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
    if not key:
        raise SystemExit("no TYPESAFE_API_KEY")
    return key


async def main(env_file: str) -> None:
    decider = JevDecider(key_from(env_file))
    body = {"model": DEFAULT_MODEL, "state": STATE,
            "questions": {k: to_wire(q) for k, q in QUESTIONS.items()}}  # fmt: skip
    try:
        raw = await decider._send(body)
    finally:
        await decider.aclose()
    OUT.write_text(json.dumps({"request": body, "response": raw}, indent=1) + "\n",
                   encoding="utf-8")  # fmt: skip
    print(f"wrote {OUT} ({(raw.get('usage') or {}).get('input_tokens')} input tokens)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default="")
    asyncio.run(main(parser.parse_args().env_file))
