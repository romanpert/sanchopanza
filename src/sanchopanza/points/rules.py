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

from ..contract import Choice, Question, Truth
from ..text import truncate

SENTENCE_MIN = 20
SENTENCE_MAX = 400
REQUEST_LIMIT = 1_500
CHANGE_LIMIT = 8_000
SENTENCES_MAX = 16
PROMPT_LINES = 20  # past these, a request is a paste: a rule is said in its first lines
# Tagged blocks are not the person typing: bash-mode output, an IDE selection, a notification,
# another session's message (review of v7, M4). Removed whole before splitting.
_TAGGED = re.compile(r"<([A-Za-z][\w-]*)\b[^>]*>.*?</\1\s*>", re.S)

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
                "Every database migration has to be reversible, with a working down step.",
                "User-facing strings always go through t() so the translators can find them.",
                "Never commit straight to main; everything goes through a pull request.",
                "New feature flags must default to off in production.",
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
                "rule: 'every migration must be reversible'; the change adds a migration whose "
                "down step drops the column the up step adds",
                "rule: 'user-facing strings go through t()'; the change adds a button labelled "
                "t('Save draft')",
                "rule: 'feature flags default to off'; the change edits a flag's description only",
            ],
        },
        "false": {
            "what": "`change` goes against `rule`: it renames, removes, reorders, reformats or "
            "rewords what the rule protects, adds what the rule forbids, or makes the code "
            "depend on what the rule excludes",
            "examples": [
                "rule: 'every migration must be reversible'; the change adds a migration that "
                "drops a table and has no down step",
                "rule: 'user-facing strings go through t()'; the change adds a button labelled "
                "'Save draft' written directly in the template",
                "rule: 'feature flags default to off'; the change adds a flag whose default is on",
            ],
        },
    },
)

# The audit asks one of three, not a yes/no: with a Truth `kept`, a rule that has nothing to do
# with the change was judged "broken" in 32 of 320 unrelated pairs (10 %; 8 rules per request
# would send most requests back), while the breaks it must catch sit between 0.03 and 0.42.
RELATION = Choice(
    "How does `change` relate to `rule`, which the person stated in an earlier session?",
    {
        "breaks": "The change goes against the rule: it renames, removes, reorders, reformats or "
        "rewords what the rule protects, adds what the rule forbids, or makes the code depend on "
        "what the rule excludes",
        "keeps": "The change touches what the rule is about and respects it (left as it was, "
        "kept under the same name or format, an alias kept for an old name)",
        "unrelated": "The change does not touch anything the rule is about",
    },
)


# Split after a full stop whatever case follows ("...with a test. legacy_total stays." was one
# sentence before, 2026-10-02), except after a few abbreviations.
_SPLIT = re.compile(r"(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\betc\.)(?<!\bvs\.)(?<=[.!?])\s+|\n+")


def sentences(text: str) -> list[str]:
    """The person's sentences worth asking about, in order (code blocks and long pastes left
    out: a rule is said, not pasted)."""
    clean = _TAGGED.sub(" ", re.sub(r"```.*?```", " ", text or "", flags=re.S))
    lines = [line for line in clean.splitlines() if line.strip()][:PROMPT_LINES]
    out = []
    for part in _SPLIT.split("\n".join(lines)):
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


def questions_for_relation(rule: str, change: str) -> tuple[Mapping[str, Any],
                                                            dict[str, Question]]:  # fmt: skip
    state = {"rule": truncate(rule, SENTENCE_MAX), "change": truncate(change, CHANGE_LIMIT)}
    return state, {"relation": RELATION}
