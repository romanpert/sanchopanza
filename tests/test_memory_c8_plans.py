"""ROADMAP C8: plan and next-step sentences ("For step 2, ...") were stored as standing rules
and crowded the 8-rule slot every session start gives (F2: 40 of the 118 rules its 72 S arms
stored). They stay out of the rules (`memory_rules.is_plan`): not asked about at Stop, not given
at a session start; they live in the record of the request that said them. No network."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from sanchopanza import Decision
from sanchopanza.context import episodes as ep
from sanchopanza.harness import memory_rules as mr
from sanchopanza.squire import Squire

from .helpers import yes

# ---- c: plan sentences stay out of the standing rules ----------------------------------------

# F2's stored rules (72 S arms), read from the night's logs: the plans and decisions about step 2
# went into the 8-rule slot beside the scenes' standing constraints.
F2_PLANS = [
    "For step 2, move the stale accounts into data/archived.json (append to it) instead of "
    "deleting them outright.",
    "For step 2, cap the discount at 20 % of the subtotal.",
    "For step 2, a ticket from a customer on the enterprise plan is always urgent, whatever it "
    "says.",
    "Step 2, in the next session: is_urgent(ticket) in the same file, telling whether a ticket "
    "needs someone now (an outage, data loss, a blocked payment).",
    "For step 2, when someone is in both lists keep the existing record as it is, name "
    "included; don't take the new one.",
    "And we had planned offset paging for step 2; scratch that, use the cursor: pass the 'next' "
    "value it returns as 'after' until it comes back empty.",
    "And a change to what we planned: we said step 2 would write one file per month; now they "
    "want a single file at path with every month, oldest first.",
    "And for step 2: return every problem at once as a list of messages, not just the first one.",
    "Next session we will add the retry queue.",
    "Tomorrow we'll wire the exporter into the CLI.",
    "En la próxima sesión hacemos el paso 2: la exportación.",
]
F2_RULES = [
    "By the way, the carrier's API rejects any request that carries more than 50 labels.",
    "A standing rule here: any script that changes data does nothing by default and only "
    "writes when it's given --apply; without it, it just reports what it would do.",
    "How we work here: anything that changes what a customer pays ships behind a FEATURE_* "
    "environment variable, off by default, so we can turn it on shop by shop.",
    "One thing about that service: it breaks on pages bigger than 100, so never ask for a limit "
    "above 100.",
    "About the coupon: we first said READ10 would take 10 % off the whole cart; marketing "
    "changed that this morning, it's 10 % off the 'books' lines only.",
    "Good to know: payroll is run by the US office, so our weeks go from Sunday to Saturday.",
    "Every database migration has to be reversible, with a working down step.",
    "Never commit straight to main; everything goes through a pull request.",
    "Lo que ven los clientes va siempre en español; el código, en inglés.",
    "Esta mañana cambiaron el formato: el CSV va con punto y coma.",
]


@pytest.mark.parametrize("text", F2_PLANS)
def test_a_plan_sentence_is_a_plan(text: str) -> None:
    assert mr.is_plan(text)


@pytest.mark.parametrize("text", F2_RULES)
def test_a_standing_rule_is_not_a_plan(text: str) -> None:
    assert not mr.is_plan(text)


class Asked:
    """Every sentence is a rule (0.9); the sentences it was asked about are kept."""

    name = "scripted"
    accepts_attachments = False

    def __init__(self) -> None:
        self.sentences: list[str] = []

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        self.sentences = [*self.sentences, state["sentence"]]
        return Decision(point, {k: yes(0.9) for k in questions}, self.name, "t")


def test_extraction_asks_nothing_about_a_plan_sentence_and_stores_only_the_rule(
    tmp_path: Path,
) -> None:
    rule, plan = F2_RULES[0], F2_PLANS[0]
    request = f"Write label_for(order) in app/labels.py, with tests. {rule} {plan}"
    episode = ep.Episode(session="s1", index=1, request=request, report="done",
                         changed=("app/labels.py",), at=1_790_900_000.0)  # fmt: skip
    asked = Asked()
    added = asyncio.run(mr.extract(Squire(asked), tmp_path, [episode]))
    assert plan not in asked.sentences and rule in asked.sentences
    assert plan not in added and rule in added


def test_a_plan_stored_before_this_is_not_given_at_a_session_start(tmp_path: Path) -> None:
    rules = [
        {"text": F2_PLANS[0], "p": 0.9, "session": "s1", "index": 1, "at": 2.0, "files": []},
        {"text": F2_RULES[0], "p": 0.9, "session": "s1", "index": 1, "at": 1.0, "files": []},
    ]
    (tmp_path / mr.RULES).write_text(json.dumps({"rules": rules, "asked": []}), "utf-8")
    text = mr.render(tmp_path)
    assert F2_RULES[0] in text and F2_PLANS[0] not in text
