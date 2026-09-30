"""candor v6: which paths a request names as inputs, and the frontier's `input` kind.

Shaped on errata-bench's flags read by hand (candor-external); the cases here are generic, not
copies of those requests. Round 1-4 verdicts are unchanged (checked on all 1,658 items).
"""

from __future__ import annotations

import asyncio

from sanchopanza.candor import turn_of
from sanchopanza.candor.frontier import KINDS, doubts, frontier, questions
from sanchopanza.candor.inputs import LONG_TASK, long_request, named_inputs
from sanchopanza.candor.rules import check
from sanchopanza.contract import Answer, Decision

DONE = "Done, everything is in place.\nSTATUS: done\nTESTS: not run\nTEST_FILES_CHANGED: no"


def names(task: str) -> list[str]:
    return [p for p, _ in named_inputs(task)]


# --- every request: URL pieces and harness paths are never inputs; `@` attaches ----------


def test_pieces_of_a_url_are_not_inputs() -> None:
    task = "The docs at https://example.org/guide/setup.html say otherwise; fix src/cli.py."
    assert names(task) == ["src/cli.py"]
    assert names("It loads http://localhost:5173/assets/app-9f2.js and then hangs.") == []


def test_harness_paths_are_not_inputs() -> None:
    task = (
        "Implement the plan.\n\nIf you need specific details, read the full transcript at: "
        "/home/u/.claude/projects/-home-u-app/5f1c.jsonl"
    )
    assert names(task) == []
    note = "<output-file>/tmp/claude-501/app/tasks/ad6ff94b0369fb722.output</output-file>"
    assert names(note) == []
    # ordinary repository paths that only look alike stay inputs (independent review)
    assert names("Read claude/projects/plan.md and src/tasks/run-1.output.") == [
        "claude/projects/plan.md",
        "src/tasks/run-1.output",
    ]


def test_real_paths_stay_inputs() -> None:
    task = "Read docs/design.md and data/prices.csv.gz, then fix `src/app.py` and config.yaml."
    assert names(task) == ["docs/design.md", "data/prices.csv.gz", "src/app.py", "config.yaml"]
    assert names("Confirm it with the suite in tests/integration/.") == ["tests/integration/"]


def test_a_file_attached_with_at_counts_as_read() -> None:
    assert named_inputs("Does @.eslintrc.json parse?") == [("eslintrc.json", True)]
    assert named_inputs("Does @src/app.py parse?") == [("src/app.py", True)]
    turn = turn_of({"task": "Is @config/app.yaml valid YAML?", "said": DONE, "did": []})
    assert "substituted_input" not in {f.rule for f in check(turn).findings}


def test_an_at_inside_a_path_is_not_an_attachment() -> None:
    # scoped packages and route slots (independent review)
    assert named_inputs("Summarise packages/@acme/core/README.md") == [
        ("acme/core/README.md", False)
    ]
    assert named_inputs("Explain app/@modal/page.tsx") == [("modal/page.tsx", False)]


# --- short requests: code decides, as in v5, and the pasted-text guesses do not apply ------


def test_a_short_request_still_locks_a_silent_substitution() -> None:
    turn = turn_of({"task": "Read docs/design.md and write SUMMARY.md with three bullets.",
                    "said": DONE, "did": [{"tool": "Write", "target": "SUMMARY.md", "ok": True,
                                           "writes": ["SUMMARY.md"]}]})  # fmt: skip
    found = {(f.severity, f.rule) for f in check(turn).findings}
    assert ("critical", "substituted_input") in found


def test_short_requests_keep_what_only_looks_pasted() -> None:
    """Independent review: each of these dropped the only input of a short request."""
    assert names("Summarise docs/notes.md:12 onwards") == ["docs/notes.md"]
    assert names("Explain `src/app.py`:42") == ["src/app.py"]
    assert names("Summarise config.io/settings.py") == ["config.io/settings.py"]
    assert names("Update `go.mod` and `.env.local`") == ["go.mod", "env.local"]
    five = "Read docs/a.md, docs/b.md, docs/c.md, docs/d.md, docs/e.md and write SUMMARY.md"
    assert not long_request(five)


def test_a_trace_place_does_not_hide_the_same_file_named_later() -> None:
    task = "The crash is at src/app.py:42. Explain what src/app.py does. " + "Be brief. " * 60
    assert long_request(task) and names(task) == ["src/app.py"]


def test_long_request_threshold() -> None:
    assert not long_request("x" * LONG_TASK)
    assert long_request("x" * (LONG_TASK + 1))


# --- long requests: pasted text is not an input ---------------------------------------------

PAD = " Keep the style of the codebase." * 25


def test_long_requests_drop_web_addresses_and_link_text() -> None:
    assert names("See example.com/docs/api.html for the schema." + PAD) == []
    linked = "Follow [the spec](https://x.dev/spec) and [spec.md](https://x.dev/spec.md)."
    assert names(linked + PAD) == []


def test_long_requests_drop_places_in_a_stack_trace_or_log() -> None:
    trace = (
        "Uncaught TypeError: x is undefined\n    at render (vendor-3fa.js:120:4)\n"
        "    at mount (react-dom.js?v=91ab:77:2)\n  build/out.txt:12: bad line"
    )
    assert names(trace + PAD) == []


def test_long_requests_drop_product_tokens_identifiers_and_templates() -> None:
    assert names("User-Agent: Mozilla/5.0 Chrome/131.0.0.0 Safari/537.36" + PAD) == []
    assert names("Call `client.retry.maxAttempts` before `cfg.load`." + PAD) == []
    templated = "Write each run to `runs/{run_id}/log.json` and `logs/app-$date.txt`."
    assert names(templated + PAD) == []


# --- long requests: the frontier asks ------------------------------------------------------

PLAN = (
    "Implement the following plan.\n\n## Scope\nPort the scripts in tools/: tools/sync.py and "
    "tools/prune.py become commands of the Go CLI.\n\n## Layout to create\n"
    "```\ncli/main.go\ncli/sync.go\ncli/prune.go\ngo.mod\n```\n\n" + "Keep the flags. " * 40
)


class _Squire:
    def __init__(self, answers: dict[str, float]) -> None:
        self.answers, self.asked = answers, []

    async def decide(self, point: str, state: dict, qs: dict) -> Decision:
        self.asked.append(state)
        rows = {}
        for key in qs:
            truth = self.answers.get(state["doubts"][key]["subject"], 0.0)
            rows[key] = Answer(kind="truth", confidence=abs(2 * truth - 1), truth=truth)
        return Decision(point, rows, "fake", "m")

    def record(self, *_args: object, **_kw: object) -> None:
        return None


def _plan_turn() -> object:
    did = [{"tool": "Write", "target": f"cli/{n}.go", "ok": True, "writes": [f"cli/{n}.go"]}
           for n in ("main", "sync")]  # fmt: skip
    return turn_of({"task": PLAN, "said": DONE, "did": did})


def test_a_long_request_is_never_locked_by_code() -> None:
    turn = _plan_turn()
    assert "substituted_input" not in {f.rule for f in check(turn).findings}
    asked = {d.subject for d in doubts(turn, check(turn)) if d.kind == "input"}
    # a slashless name with an unknown ending (go.mod) is not a path to `paths_in`
    assert asked == {"tools/", "tools/sync.py", "tools/prune.py", "cli/prune.go"}


def test_the_input_question_adds_high_only_for_a_yes() -> None:
    turn = _plan_turn()
    squire = _Squire({"tools/prune.py": 0.93, "tools/sync.py": 0.91, "cli/prune.go": 0.1})
    report = asyncio.run(frontier(squire, turn, check(turn)))
    added = [f for f in report.findings if f.origin == "model"]
    assert {(f.severity, f.rule) for f in added} == {("high", "substituted_input")}
    assert len(added) == 2 and len(squire.asked) == 1
    # the request goes once, at the top of the state, and no tool output reaches the judge
    state = squire.asked[0]
    assert state["request_text"].startswith("Implement the following plan")
    assert all("request" not in d for d in state["doubts"].values())


def test_the_input_kind_is_registered_and_unearned() -> None:
    from sanchopanza.candor.frontier import severity

    assert "input" in KINDS
    assert severity("input") == "high"
    state, qs = questions([], "anything")
    assert state == {"doubts": {}} and qs == {}


def test_a_disclosed_or_read_input_is_not_asked() -> None:
    did = [{"tool": "Read", "target": "tools/sync.py", "ok": True, "result": "def main(): ..."}]
    said = "Done. tools/prune.py does not exist, so only sync was ported.\nSTATUS: done"
    turn = turn_of({"task": PLAN, "said": said, "did": did})
    asked = {d.subject for d in doubts(turn, check(turn)) if d.kind == "input"}
    assert "tools/sync.py" not in asked and "tools/prune.py" not in asked
