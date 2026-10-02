"""Standing rules: what the person said that later work must keep, and whether a change kept it.

Memory v6 gives an earlier request back verbatim when a later one touches the same file or names
it. Two gaps remained, both measured on the carry bench (`docs/results/2026-10-02-memory-carry/`):
a rule said while changing one file and broken in another, which no file match finds; and a rule
the agent was given and still bent (the error message whose prefix it kept and whose text it
extended). Published work agrees on both: retrieval is the bottleneck (InMind 2026: 84 % correct
with the memory in context, 14 % when it had to be retrieved), and one feedback message quoting
the violated rule verbatim lifts compliance to 90-100 % where a generic reminder does not
(RepoComplianceBench 2026).

So two questions, both on the person's own words, never on a summary:
- `standing`, per sentence of a request: is it a lasting rule about the project? The sentences
  that are become the project's standing rules, kept verbatim and given at every new session.
- `kept`, per standing rule at a request's end: does the request's diff still respect it? A
  confident "no" sends the agent back once, with the rule quoted.

Rules come only from the person's prompt text: never from tool output or file content, which an
attacker can write (MemSecBench 2026: a poisoned memory persists in 84 % of cases).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from ..contract import Question, Truth
from ..text import truncate

SENTENCE_MIN = 20
SENTENCE_MAX = 400
REQUEST_LIMIT = 1_500
CHANGE_LIMIT = 8_000
SENTENCES_MAX = 16

STANDING = Truth(
    "Is `sentence`, written by the person directing a coding agent in `request`, a standing "
    "rule or fact about their project that work in later sessions must keep respecting?",
    criteria={
        "true": {
            "what": "A lasting constraint beyond this request: something outside the code depends "
            "on a name, format, field, order, wording or behaviour; a limit of where the code "
            "runs (versions, platforms, no network, allowed libraries); or an 'always' or "
            "'never' about how the project may be changed",
            "examples": [
                "The billing service parses these CSV headers, so they can't change.",
                "We still deploy on Node 18, nothing newer.",
                "Never commit straight to main; everything goes through a pull request.",
                "Keep the old /v1/orders route: two partners still call it.",
            ],
        },
        "false": {
            "what": "The work of this request or a step of it, a question, a status report, a "
            "wish about this one answer, or a fact that only describes the present moment",
            "examples": [
                "Add a test for the date parser.",
                "Can you find out why the build fails on CI?",
                "Commit all the changes we just made.",
                "The import crashes when the file is empty.",
                "Use a shorter name for this variable.",
            ],
        },
    },
)

KEPT = Truth(
    "Does `change` still respect `rule`, which the person stated in an earlier session?",
    criteria={
        "true": {
            "what": "Nothing in `change` goes against `rule`: what the rule protects is left as "
            "it was, or is changed in a way the rule allows (kept under the same name, kept in "
            "the same format, an alias kept for an old name)",
            "examples": [
                "rule: 'the billing service reads price_cents, keep it'; the change adds a "
                "discount field and leaves price_cents as it was",
                "rule: 'this job must never write to stdout'; the change adds progress messages "
                "through the logging module",
            ],
        },
        "false": {
            "what": "`change` goes against `rule`: it renames, removes, reorders, reformats or "
            "rewords what the rule protects, adds what the rule forbids, or makes the code "
            "depend on what the rule excludes",
            "examples": [
                "rule: 'the billing service reads price_cents, keep it'; the change drops "
                "price_cents as redundant with price",
                "rule: 'error codes are parsed by a partner, do not change them'; the change "
                "rewrites the messages to be friendlier",
                "rule: 'this job must never write to stdout'; the change adds print() calls to "
                "report progress",
            ],
        },
    },
)

# Split after a full stop whatever case follows ("...with a test. legacy_total stays." was one
# sentence before, 2026-10-02), except after a few abbreviations.
_SPLIT = re.compile(r"(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\betc\.)(?<!\bvs\.)(?<=[.!?])\s+|\n+")


def sentences(text: str) -> list[str]:
    """The person's sentences worth asking about, in order (code blocks and long pastes left
    out: a rule is said, not pasted)."""
    clean = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    out = []
    for part in _SPLIT.split(clean):
        part = part.strip(" -*\t")
        if SENTENCE_MIN <= len(part) <= SENTENCE_MAX and not part.startswith(("<", "{", "[")):
            out.append(part)
    return out[:SENTENCES_MAX]


def questions_for_sentence(sentence: str, request: str) -> tuple[Mapping[str, Any],
                                                                 dict[str, Question]]:  # fmt: skip
    state = {"sentence": sentence, "request": truncate(request, REQUEST_LIMIT)}
    return state, {"rule": STANDING}


def questions_for_change(rule: str, change: str) -> tuple[Mapping[str, Any],
                                                          dict[str, Question]]:  # fmt: skip
    state = {"rule": truncate(rule, SENTENCE_MAX), "change": truncate(change, CHANGE_LIMIT)}
    return state, {"kept": KEPT}
