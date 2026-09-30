"""sanchopanza's `clm` provider against a real clm-serve (CPU embedder), free."""
import asyncio
import os
import sys
import time

sys.path.insert(0, r"C:\Users\roman\Desktop\proyectos\apps\sanchopanza\src")
os.environ["SANCHOPANZA_CLM_URL"] = "http://127.0.0.1:18392"
os.environ["SANCHOPANZA_CLM_MODEL"] = "clm-latest"

from sanchopanza.contract import Choice, Score, Truth  # noqa: E402
from sanchopanza.providers import create  # noqa: E402

CASES = [
    # CLM's own model card example: department -> billing 0.93878 (vLLM encoder)
    ("card", "Customer: my invoice was charged twice and nobody answers the phone!",
     {"urgency": Truth("Is this urgent?"),
      "department": Choice("Which team should handle this?",
                           {"billing": "Charges, invoices, refunds",
                            "technical": "Bugs and outages"}),
      "frustration": Score("How frustrated is the customer?",
                           ["Calm", "Frustrated", "Very angry"])}),
    ("email", {"email": "Hi, the invoice for March is attached. No action needed on your side."},
     {"reply": Truth("Does `email` need a reply?"),
      "kind": Choice("What kind of message is `email`?",
                     {"invoice": {"what": "billing"}, "support": {"what": "a problem to fix"},
                      "spam": {"what": "unsolicited"}})}),
    ("report", {"report": "All 42 tests pass.", "last_run": "FAILED tests/test_pay.py::test_refund"},
     {"misstates": Truth("Does `report` claim something `last_run` contradicts?")}),
    ("page", {"page": "The ministry awarded the contract to Obras Norte SL on 3 May for 1.2 M EUR.",
              "purpose": "who won the 2024 road contract and for how much"},
     {"useful": Score("How useful is `page` for `purpose`?",
                      ["useless", "weak", "useful", "decisive"])}),
]


async def main() -> None:
    decider = create("clm", timeout_s=1800.0)
    for name, state, qs in CASES:
        t = time.time()
        d = await decider.decide("probe", state, qs)
        print(name, d.error or "", f"{time.time() - t:.1f}s")
        for k, a in d.answers.items():
            print(f"   {k}: choice={a.choice} truth={a.truth} score={a.score} "
                  f"probs={dict(a.probabilities)}")


asyncio.run(main())

