"""Grading BrowseComp-Plus the official way where we can, and saying where we cannot.

The official grade (`scripts_evaluation/evaluate_run.py`, MIT, texttron/BrowseComp-Plus) asks a
judge model, Qwen3-32B served by vLLM (temperature 0.7, thinking off), with `GRADER_TEMPLATE`
below, and reads `correct: yes|no` from its reply. We have no Qwen3-32B. Ours, declared in the
report:

1. Exact match first (`exact_match`): the response's last "Exact Answer:" line against the gold
   answer after a SQuAD-style normalisation (case, punctuation, articles, whitespace), or equal
   as numbers. A match is graded correct without a judge; the official judge would say yes to
   every one of these (its template allows "string variations").
2. Everything else goes to a judge with the official template verbatim and the official parser:
   Claude Haiku 4.5 through `claude -p` on the subscription (`judge_argv`), one clean user per
   call, no tools, one turn, a hard cap per call, the prompt on stdin. Haiku is not Qwen3-32B:
   the leaderboard's two judges (GPT-4.1 and Qwen3-32B) differ by under 1 % on average, which
   is the size of disagreement to expect, not a bound.
3. The cases a person should read (`doubtful`): the judge said yes without an exact match, or
   gave no parseable verdict. They are exported for a blind read (no arm, shuffled) into the
   private cache; a hand verdict sits beside the judge's, as in GAIA.

Retrieval and citation metrics follow the official script: evidence recall over the docids the
agent's searches returned, and citation precision and recall of the `[docid]` the response cites.
"""

from __future__ import annotations

import re
import string
from collections.abc import Iterable, Sequence

# Verbatim from evaluate_run.py (the Qwen3-32B judge's template), MIT.
GRADER_TEMPLATE = """
Judge whether the following [response] to [question] is correct or not based on the precise and unambiguous [correct_answer] below.

[question]: {question}

[response]: {response}

[correct_answer]: {correct_answer}

Your judgement must be in the format and criteria specified below:

extracted_final_answer: The final exact answer extracted from the [response].

[correct_answer]: Repeat the [correct_answer] given above.

reasoning: Explain why the extracted_final_answer is correct or incorrect based on [correct_answer], in the context of this [question]. You should judge whether the extracted_final_answer is semantically equivalent to [correct_answer], allowing the extracted_final_answer to be string variations of [correct_answer]. You should also allow the extracted_final_answer to be more precise or verbose than [correct_answer], as long as its additional details are correct. Do not comment on any background to the problem, do not attempt to solve the problem, do not argue for any answer different than [correct_answer], focus only on whether the answers are semantically equivalent.

correct: Answer 'yes' if extracted_final_answer matches the [correct_answer] given above, or is within a small margin of error for numerical problems. Answer 'no' otherwise, i.e. if there if there is any inconsistency, ambiguity, non-equivalency, or if the extracted answer is incorrect.


confidence: The extracted confidence score between 0|\\%| and 100|\\%| from [response]. Put 100 if there is no confidence score available.
""".strip()  # noqa: E501, W291

# Verbatim from search_agent/prompts.py (QUERY_TEMPLATE), MIT: the agent's prompt.
QUERY_TEMPLATE = """
You are a deep research agent. You need to answer the given question by interacting with a search engine, using the search and get_document tools provided. Please perform reasoning and use the tools step by step, in an interleaved manner. You may use the search and get_document tools multiple times.

Question: {Question}

Your response should be in the following format:
Explanation: {{your explanation for your final answer. For this explanation section only, you should cite your evidence documents inline by enclosing their docids in square brackets [] at the end of sentences. For example, [20].}}
Exact Answer: {{your succinct, final answer}}
Confidence: {{your confidence score between 0% and 100% for your answer}}
""".strip()  # noqa: E501

JUDGE_MODEL = "claude-haiku-4-5-20251001"
JUDGE_CAP_USD = 0.05
# Line-bounded, last marker wins (`gaia_session.marker_line`'s rule): candor's status block
# after the answer in S is never part of it.
_EXACT = re.compile(r"^\W*exact answer\W*:[ \t]*([^\r\n]+?)[ \t]*\r?$", re.I | re.M)
_CONFIDENCE = re.compile(r"confidence\W*:\s*(\d+(?:\.\d+)?)\s*%?", re.I)
_ARTICLES = re.compile(r"\b(a|an|the)\b")


def prompt(question: str) -> str:
    return QUERY_TEMPLATE.format(Question=question)


def judge_prompt(question: str, response: str, gold: str) -> str:
    return GRADER_TEMPLATE.format(question=question, response=response, correct_answer=gold)


def exact_answer(response: str | None) -> str | None:
    """The last "Exact Answer:" line's value, markdown emphasis removed."""
    found = _EXACT.findall((response or "").replace("**", ""))
    return found[-1].strip().strip("*").strip() or None if found else None


def confidence(response: str | None) -> float | None:
    found = _CONFIDENCE.findall(response or "")
    return float(found[-1]) if found else None


def normalise(text: str) -> str:
    lowered = text.lower()
    no_punct = "".join(ch for ch in lowered if ch not in set(string.punctuation))
    return " ".join(_ARTICLES.sub(" ", no_punct).split())


def _number(text: str) -> float | None:
    try:
        return float(text.replace(",", "").replace("$", "").replace("%", "").strip())
    except ValueError:
        return None


def exact_match(answer: str | None, gold: str) -> bool:
    if not answer:
        return False
    if normalise(answer) == normalise(gold) and normalise(gold):
        return True
    a, g = _number(answer), _number(gold)
    return a is not None and g is not None and abs(a - g) <= 1e-9 * max(1.0, abs(g))


def parse_judge(reply: str | None) -> bool | None:
    """The official parser's order: **correct:** yes, **correct**: yes, then correct: yes."""
    text = reply or ""
    for pattern in (r"\*\*correct:\*\*\s*(yes|no)", r"\*\*correct\*\*:\s*(yes|no)",
                    r"correct:\s*(yes|no)"):  # fmt: skip
        found = re.search(pattern, text, re.I)
        if found:
            return found.group(1).lower() == "yes"
    return None


def citations(response: str | None) -> list[str]:
    """The official `extract_citations_from_response`: [12], [3, 4] and their full-width forms."""
    text = response or ""
    single = re.findall(r"\[(\d+)\]", text) + re.findall(r"【(\d+)】", text)
    found = set(single)
    for match in re.findall(r"\[([^\[\]]*?)\]", text) + re.findall(r"【([^【】]*?)】", text):
        if match not in single:
            found.update(re.findall(r"\d+", match))
    return sorted(found)


def citation_metrics(cited: Sequence[str], relevant: Sequence[str]) -> dict[str, float]:
    hit = set(cited) & set(relevant)
    return {
        "num_citations": len(cited),
        "precision": round(len(hit) / len(cited), 4) if cited else 0.0,
        "recall": round(len(hit) / len(relevant), 4) if cited and relevant else 0.0,
    }


def recall(retrieved: Iterable[str], relevant: Sequence[str]) -> float | None:
    if not relevant:
        return None
    return round(len(set(retrieved) & set(relevant)) / len(set(relevant)), 4)


def judge_argv(claude: str, mcp: str) -> list[str]:
    """`claude -p` as a bare judge: no tools, one turn, capped; the prompt goes on stdin."""
    return [
        claude, "-p", "--model", JUDGE_MODEL, "--setting-sources", "user",
        "--permission-mode", "default", "--mcp-config", mcp, "--strict-mcp-config",
        "--disallowedTools", "Bash Read Grep Glob Write Edit NotebookEdit WebSearch WebFetch "
        "Task Agent TodoWrite SendMessage ListAgents ScheduleWakeup CronCreate RemoteTrigger",
        "--max-turns", "1", "--output-format", "json", "--max-budget-usd", f"{JUDGE_CAP_USD:g}",
    ]  # fmt: skip


def verdict(em: bool, judged: bool | None, hand: bool | None = None) -> bool:
    """A row's grade: a hand verdict first, then exact match, then the judge."""
    if hand is not None:
        return hand
    return em or bool(judged)


def doubtful(em: bool, judged: bool | None) -> bool:
    return (judged is True and not em) or (judged is None and not em)
