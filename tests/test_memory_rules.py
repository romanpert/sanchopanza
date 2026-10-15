"""v7 standing rules (`harness.memory_rules`, `points.rules`): extracted from the person's words
at Stop, given at every session start, and a request's diff held against them before it stops.
A scripted decider stands in for Jev; git is real."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from sanchopanza import Decision
from sanchopanza.context import episodes as ep
from sanchopanza.harness import memory_hook as mh
from sanchopanza.harness import memory_rules as mr
from sanchopanza.points.rules import sentences
from sanchopanza.squire import Squire

from .context_helpers import ScriptedDecider
from .helpers import choice, yes

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="no git")
RULE = "Ops sets PAYMENT_TIMEOUT by that exact name in every deployment, it can't be renamed."
MINE = ["app/config.py"]


def by_words(point: str, key: str, state: Any) -> float | None:
    """Standing: a sentence with 'can't' or 'never' is a rule. Kept: a change that drops the
    protected name breaks it."""
    if key == "rule":
        return 0.9 if ("can't" in state["sentence"] or "never" in state["sentence"]) else 0.1
    if key == "kept":
        return 0.1 if "APP_PAYMENT_TIMEOUT" in state["change"] else 0.9
    return None


class RuleDecider:
    """`by_words` for the Truth questions. The side-by-side `broken` Choice names, with
    probability `named`, every option that quotes a rule the change drops the name of; else
    `none`."""

    name = "scripted"
    accepts_attachments = False

    def __init__(self, named: float = 0.9, relation: str = "breaks") -> None:
        self.named = named
        self.relation = relation
        self.calls: list[tuple[str, Any, dict[str, Any]]] = []

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        self.calls.append((point, state, dict(questions)))
        answers = {}
        for key, question in questions.items():
            if key == "broken":
                hit = [
                    k
                    for k, v in question.options.items()
                    if "PAYMENT_TIMEOUT" in v and "APP_PAYMENT_TIMEOUT" in state["change"]
                ]
                probs = {k: 0.0 for k in question.options}
                probs.update({k: self.named for k in hit})
                probs["none"] = 1.0 - sum(probs.values())
                answers[key] = choice(max(probs, key=probs.get), 0.5, **probs)
            elif key == "relation":
                first = self.relation if "APP_PAYMENT_TIMEOUT" in state["change"] else "unrelated"
                probs = {k: (0.8 if k == first else 0.1) for k in question.options}
                answers[key] = choice(first, 0.6, **probs)
            else:
                p = by_words(point, key, state)
                if p is not None:
                    answers[key] = yes(p)
        return Decision(point=point, answers=answers, provider=self.name, model="scripted-1")


def squire(named: float = 0.9) -> Squire:
    return Squire(RuleDecider(named))


def episode(text: str, session: str = "s1", index: int = 1) -> ep.Episode:
    return ep.Episode(session=session, index=index, request=text, report="done",
                      changed=("app/config.py",), at=1_790_900_000.0)  # fmt: skip


def test_sentences_split_after_a_stop_whatever_case_follows() -> None:
    text = "Add items_count to order_dict, with a test. legacy_total stays, e.g. for the app."
    assert sentences(text) == ["Add items_count to order_dict, with a test.",
                               "legacy_total stays, e.g. for the app."]  # fmt: skip


def test_rules_come_from_the_persons_sentences_once_per_request(tmp_path: Path) -> None:
    text = f"Make load() raise ValueError on a bad APP_RETRIES. {RULE}"
    added = asyncio.run(mr.extract(squire(), tmp_path, [episode(text)]))
    assert added == [RULE]
    again = asyncio.run(mr.extract(squire(), tmp_path, [episode(text)]))
    assert again == []
    data = mr.load(tmp_path)
    assert [r["text"] for r in data["rules"]] == [RULE] and data["asked"] == ["s1-001"]


def test_the_rules_are_given_in_the_persons_words_newest_first(tmp_path: Path) -> None:
    assert mr.render(tmp_path) == ""
    asyncio.run(mr.extract(squire(), tmp_path, [episode(RULE)]))
    asyncio.run(mr.extract(squire(), tmp_path, [
        ep.Episode(session="s2", index=1, request="We never print from the cron job.",
                   report="", at=1_790_990_000.0)]))  # fmt: skip
    text = mr.render(tmp_path)
    assert text.startswith(mr.HEADER) and text.endswith(mr.CLOSING)
    assert text.index("never print") < text.index(RULE)
    assert "while changing app/config.py" in text


def _repo(root: Path) -> str:
    (root / "app").mkdir(parents=True)
    (root / "app" / "config.py").write_text(
        "def load():\n    return {\n    'timeout': env('PAYMENT_TIMEOUT'),\n    }\n", "utf-8"
    )
    for args in (
        ["init", "-q"],
        ["config", "user.email", "t@example.org"],
        ["config", "user.name", "t"],
        ["add", "."],
        ["commit", "-qm", "base"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()  # fmt: skip
    return head


@needs_git
def test_a_diff_that_breaks_a_rule_is_found_once_per_request(tmp_path: Path) -> None:
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    asyncio.run(mr.extract(squire(), store, [episode(RULE, session="old")]))
    (repo / "app" / "config.py").write_text(
        "def load():\n    return {\n    'timeout': env('APP_PAYMENT_TIMEOUT'),\n    }\n", "utf-8"
    )
    broken, found = asyncio.run(mr.audit(squire(), store, "new", 1, str(repo), head, MINE))
    assert [r["text"] for r in broken] == [RULE]
    assert list(found.values()) == [{"named": 0.9, "kept": 0.1, "breaks_first": True}]
    assert asyncio.run(mr.audit(squire(), store, "new", 1, str(repo), head, MINE)) == ([], {})
    assert "in their words" in mr.block_reason(broken) and RULE in mr.block_reason(broken)


@needs_git
def test_a_new_file_git_does_not_track_is_part_of_the_change(tmp_path: Path) -> None:
    # sim of 2026-10-02: a new module was invisible to `git diff`, so the check never ran
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    asyncio.run(mr.extract(squire(), store, [episode(RULE, session="old")]))
    (repo / "app" / "mailer.py").write_text("HOST = env('APP_PAYMENT_TIMEOUT')\n", "utf-8")
    (repo / ".env.local").write_text("SECRET=1\n", "utf-8")
    mine = ["app/mailer.py", ".env.local"]
    assert "+++ b/app/mailer.py (new file)" in mr._diff(str(repo), head, mine)
    assert ".env.local" not in mr._diff(str(repo), head, mine)
    broken, _ = asyncio.run(mr.audit(squire(), store, "new", 1, str(repo), head, mine))
    assert [r["text"] for r in broken] == [RULE]


@needs_git
def test_a_rule_is_not_held_against_the_request_that_stated_it(tmp_path: Path) -> None:
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    asyncio.run(mr.extract(squire(), store, [episode(RULE, session="s1", index=1)]))
    (repo / "app" / "config.py").write_text("def load():\n    return {}\n", "utf-8")
    assert asyncio.run(mr.audit(squire(), store, "s1", 1, str(repo), head, MINE)) == ([], {})


@needs_git
def test_no_change_no_question(tmp_path: Path) -> None:
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    asyncio.run(mr.extract(squire(), store, [episode(RULE, session="old")]))
    decider = RuleDecider()
    assert asyncio.run(mr.audit(Squire(decider), store, "new", 1, str(repo), head, MINE)) == (
        [],
        {},
    )
    assert decider.calls == []


# ---- through the hook ----------------------------------------------------------------------------


@pytest.fixture
def hook_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE", str(tmp_path / "memory"))
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE_LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("SANCHOPANZA_PROVIDER", "scripted")
    for name in ("SANCHOPANZA_MEMORY_SELECT", "SANCHOPANZA_MEMORY_RULES", "TYPESAFE_API_KEY",
                 "SANCHOPANZA_MEMORY_TREE", "SANCHOPANZA_MEMORY_PROMPT",
                 "SANCHOPANZA_MEMORY_RULES_AUDIT"):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("sanchopanza.harness.claude_code.squire_from_env",
                        lambda env=None, redact=False: squire())  # fmt: skip
    return tmp_path


def _transcript(path: Path, cwd: str, text: str, edit: bool) -> Path:
    use = {
        "type": "tool_use",
        "id": "t1",
        "name": "Edit",
        "input": {"file_path": f"{cwd}/app/config.py", "old_string": "a", "new_string": "b"},
    }
    entries = [{"type": "user", "cwd": cwd, "timestamp": "2026-10-02T10:00:00Z",
                "message": {"role": "user", "content": text}}]  # fmt: skip
    if edit:
        entries += [{"type": "assistant", "message": {"role": "assistant", "content": [use]}},
                    {"type": "user", "message": {"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": "t1",
                         "content": "ok"}]}}]  # fmt: skip
    entries.append({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "Done."}]}})  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


@needs_git
def test_the_hook_learns_a_rule_gives_it_at_the_next_start_and_sends_a_break_back(
    hook_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_RULES_AUDIT", "on")  # opt-in since 2026-10-14
    repo = hook_env / "repo"
    _repo(repo)
    cwd = str(repo).replace("\\", "/")
    project = hook_env / "projects" / "p"
    first = {"session_id": "s1", "cwd": cwd, "transcript_path": str(project / "s1.jsonl")}
    text1 = f"Make load() raise ValueError on a bad APP_RETRIES. {RULE}"
    mh.handle({**first, "hook_event_name": "UserPromptSubmit", "prompt": text1})
    _transcript(project / "s1.jsonl", cwd, text1, edit=False)
    assert mh.handle({**first, "hook_event_name": "Stop"}) == {}

    second = {"session_id": "s2", "cwd": cwd, "transcript_path": str(project / "s2.jsonl")}
    out = mh.handle({**second, "hook_event_name": "SessionStart", "source": "startup"})
    assert RULE in out["hookSpecificOutput"]["additionalContext"]
    text2 = "Give every environment variable an APP_ prefix."
    mh.handle({**second, "hook_event_name": "UserPromptSubmit", "prompt": text2})
    (repo / "app" / "config.py").write_text(
        "def load():\n    return {\n    'timeout': env('APP_PAYMENT_TIMEOUT'),\n    }\n", "utf-8"
    )
    _transcript(project / "s2.jsonl", cwd, text2, edit=True)
    sent = mh.handle({**second, "hook_event_name": "Stop"})
    assert sent["decision"] == "block" and RULE in sent["reason"]
    again = mh.handle({**second, "hook_event_name": "Stop", "stop_hook_active": True})
    assert again == {}


@needs_git
def test_by_default_the_hook_keeps_and_gives_the_rule_but_never_audits_or_sends_back(
    hook_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-10-14 (docs/results/2026-10-14-memory-stop): the Stop audit is opt-in. Extraction at
    Stop and the rules at the next start, the mechanism the memory cell measured, are unchanged;
    no audit question is asked, so the default spends nothing on it and blocks no Stop."""
    decider = RuleDecider()
    monkeypatch.setattr("sanchopanza.harness.claude_code.squire_from_env",
                        lambda env=None, redact=False: Squire(decider))  # fmt: skip
    repo = hook_env / "repo"
    _repo(repo)
    cwd = str(repo).replace("\\", "/")
    project = hook_env / "projects" / "p"
    first = {"session_id": "s1", "cwd": cwd, "transcript_path": str(project / "s1.jsonl")}
    text1 = f"Make load() raise ValueError on a bad APP_RETRIES. {RULE}"
    mh.handle({**first, "hook_event_name": "UserPromptSubmit", "prompt": text1})
    _transcript(project / "s1.jsonl", cwd, text1, edit=False)
    assert mh.handle({**first, "hook_event_name": "Stop"}) == {}

    second = {"session_id": "s2", "cwd": cwd, "transcript_path": str(project / "s2.jsonl")}
    out = mh.handle({**second, "hook_event_name": "SessionStart", "source": "startup"})
    assert RULE in out["hookSpecificOutput"]["additionalContext"]
    text2 = "Give every environment variable an APP_ prefix."
    mh.handle({**second, "hook_event_name": "UserPromptSubmit", "prompt": text2})
    (repo / "app" / "config.py").write_text(
        "def load():\n    return {\n    'timeout': env('APP_PAYMENT_TIMEOUT'),\n    }\n", "utf-8"
    )
    _transcript(project / "s2.jsonl", cwd, text2, edit=True)
    assert mh.handle({**second, "hook_event_name": "Stop"}) == {}
    points = {point for point, _, _ in decider.calls}
    assert "memory_standing_rule" in points
    assert not points & {"memory_rule_all", "memory_rule_check", "memory_rule_relation",
                         "memory_rule_superseded"}  # fmt: skip
    rows = [json.loads(x) for x in (hook_env / "log.jsonl").read_text("utf-8").splitlines()]
    assert [r["audit"] for r in rows if r.get("event") == "rules" and "audit" in r] == \
        ["off", "off"]  # fmt: skip


@pytest.mark.parametrize(("value", "on"), [(None, False), ("", False), ("off", False),
                                           ("0", False), ("on", True), ("ON", True),
                                           ("1", True), ("block", True)])  # fmt: skip
def test_the_stop_audit_is_off_unless_asked_for(
    value: str | None,
    on: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SANCHOPANZA_MEMORY_RULES_AUDIT", raising=False)
    monkeypatch.delenv("SANCHO_MEMORY_RULES_AUDIT", raising=False)
    if value is not None:
        monkeypatch.setenv("SANCHOPANZA_MEMORY_RULES_AUDIT", value)
    assert mr.audit_on() is on


def test_the_rules_can_be_turned_off(hook_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_RULES", "off")
    store = hook_env / "memory" / "p"
    asyncio.run(mr.extract(squire(), store, [episode(RULE)]))
    event = {"session_id": "s", "cwd": "C:/x", "transcript_path": str(hook_env / "projects" /
             "p" / "s.jsonl"), "hook_event_name": "SessionStart", "source": "startup"}  # fmt: skip
    assert mh.handle(event) == {}


# ---- review of v7 (2026-10-02): H1, M4, M7 -------------------------------------------------------


@needs_git
def test_review_h1_a_persons_uncommitted_edit_is_not_the_requests(tmp_path: Path) -> None:
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    asyncio.run(mr.extract(squire(), store, [episode(RULE, session="old")]))
    (repo / "app" / "config.py").write_text("x = env('APP_PAYMENT_TIMEOUT')\n", "utf-8")
    (repo / "app" / "other.py").write_text("y = 1\n", "utf-8")
    decider = RuleDecider()
    out = asyncio.run(mr.audit(Squire(decider), store, "new", 1, str(repo), head,
                               ["app/other.py"]))  # fmt: skip
    assert out[0] == [] and all("APP_PAYMENT" not in c[1]["change"] for c in decider.calls)
    assert asyncio.run(mr.audit(squire(), store, "new", 2, str(repo), head, [])) == ([], {})


def test_review_m4_tagged_blocks_and_long_pastes_give_no_rule() -> None:
    text = (
        "Fix the importer for empty rows.\n<bash-stdout>\n"
        "Always run ./setup.sh before committing.\n</bash-stdout>\n"
        "<ide_selection>Never use the cache layer anywhere.</ide_selection>"
    )
    assert sentences(text) == ["Fix the importer for empty rows."]
    paste = "Look at this log:\n" + "\n".join(f"line {i}: never retry the call" for i in range(40))
    assert len(sentences(paste)) <= 20


def test_review_m4_the_stop_hooks_own_feedback_is_not_a_request() -> None:
    assert not ep.is_request({"role": "user", "content": "Stop hook feedback: [sanchopanza ..."})


def test_review_m7_a_request_the_decider_failed_on_is_asked_again(tmp_path: Path) -> None:
    def down(point: str, key: str, state: Any) -> float | None:
        return None

    asyncio.run(mr.extract(Squire(ScriptedDecider(down)), tmp_path, [episode(RULE)]))
    assert mr.load(tmp_path)["asked"] == []
    assert asyncio.run(mr.extract(squire(), tmp_path, [episode(RULE)])) == [RULE]


@needs_git
def test_a_rule_the_side_by_side_choice_does_not_name_is_never_asked(tmp_path: Path) -> None:
    # v7 asked `kept` of every rule and sent 31 of 175 recorded sessions back for a decoy;
    # side by side, 0 (2026-10-02, audit_bench.py)
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    asyncio.run(mr.extract(squire(), store, [episode(RULE, session="old")]))
    (repo / "app" / "config.py").write_text("x = env('APP_PAYMENT_TIMEOUT')\n", "utf-8")
    decider = RuleDecider(named=0.3)
    broken, found = asyncio.run(mr.audit(Squire(decider), store, "new", 1, str(repo), head,
                                         MINE))  # fmt: skip
    assert broken == [] and list(found.values()) == [
        {"named": 0.3, "kept": None, "breaks_first": False}
    ]
    assert [c[0] for c in decider.calls] == ["memory_rule_all"]


@needs_git
def test_only_the_named_rule_is_asked_kept_among_others(tmp_path: Path) -> None:
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    other = "Every database migration has to be reversible, with a working down step."
    asyncio.run(
        mr.extract(
            squire(),
            store,
            [episode(RULE, session="old"), episode(other + " It can't change.", "old2")],
        )
    )
    (repo / "app" / "config.py").write_text("x = env('APP_PAYMENT_TIMEOUT')\n", "utf-8")
    decider = RuleDecider()
    broken, _ = asyncio.run(mr.audit(Squire(decider), store, "new", 1, str(repo), head, MINE))
    assert [r["text"] for r in broken] == [RULE]
    checked = [c for c in decider.calls if c[0] == "memory_rule_check"]
    assert len(checked) == 1 and checked[0][1]["rule"] == RULE
    options = decider.calls[0][2]["broken"].options
    assert "none" in options and any("(said while changing app/config.py)" in v
                                     for v in options.values())  # fmt: skip


def test_the_shuffle_is_fixed_per_request_and_moves_rules() -> None:
    assert mr._order("s-001", 8) == mr._order("s-001", 8)
    assert sorted(mr._order("s-001", 8)) == list(range(8))
    assert len({tuple(mr._order(f"s-{n:03d}", 8)) for n in range(20)}) > 10


LETTERS = "ABCDEFGH"


class PickDecider(RuleDecider):
    """The side-by-side Choice names the option quoting rule `pick` (by its words, wherever the
    shuffle put it); `kept` says that rule is broken and every other kept."""

    def __init__(self, pick: str, kept_fails: bool = False) -> None:
        super().__init__()
        self.pick, self.kept_fails = pick, kept_fails

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        self.calls.append((point, state, dict(questions)))
        if "broken" in questions:
            options = questions["broken"].options
            probs = {k: (0.9 if f"Rule {self.pick} " in v else 0.0) for k in options
                     for v in [options[k]]}  # fmt: skip
            probs["none"] = 0.1
            return Decision(point=point, answers={"broken": choice(max(probs, key=probs.get),
                                                                     0.8, **probs)},
                            provider=self.name, model="scripted-1")  # fmt: skip
        if "relation" in questions:
            first = "breaks" if state["rule"].startswith(f"Rule {self.pick} ") else "unrelated"
            probs = {k: (0.8 if k == first else 0.1) for k in questions["relation"].options}
            return Decision(point=point, answers={"relation": choice(first, 0.6, **probs)},
                            provider=self.name, model="scripted-1")  # fmt: skip
        if self.kept_fails:
            return Decision(point=point, answers={}, provider=self.name, model="scripted-1",
                            error="down")  # fmt: skip
        hit = state["rule"].startswith(f"Rule {self.pick} ")
        return Decision(point=point, answers={"kept": yes(0.1 if hit else 0.9)},
                        provider=self.name, model="scripted-1")  # fmt: skip


def _eight_rules(store: Path) -> None:
    rules = [{"text": f"Rule {c} can never change in this project.", "session": f"old{c}",
              "index": 1, "at": 1_790_000_000.0 + n, "files": [f"app/{c.lower()}.py"]}
             for n, c in enumerate(LETTERS)]  # fmt: skip
    mr._save(store, {"rules": rules, "asked": [], mr.AUDITED: []})


@needs_git
def test_review_m2_the_rule_sent_back_is_the_one_named_wherever_the_shuffle_puts_it(
        tmp_path: Path) -> None:  # fmt: skip
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    (repo / "app" / "config.py").write_text("x = 1\n", "utf-8")
    moved = 0
    for n, pick in enumerate("CFAH"):
        _eight_rules(store)
        decider = PickDecider(pick)
        broken, _ = asyncio.run(mr.audit(Squire(decider), store, f"s{n}", 1, str(repo), head,
                                         MINE))  # fmt: skip
        assert [r["text"] for r in broken] == [f"Rule {pick} can never change in this project."]
        options = list(decider.calls[0][2]["broken"].options.values())
        moved += not options[LETTERS.index(pick)].startswith(f'"Rule {pick} ')
    assert moved  # the shuffle really moved the picked rule in at least one request


@needs_git
def test_review_m1_a_named_rule_kept_failed_on_is_asked_again(tmp_path: Path) -> None:
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    (repo / "app" / "config.py").write_text("x = 1\n", "utf-8")
    _eight_rules(store)
    out = asyncio.run(mr.audit(Squire(PickDecider("C", kept_fails=True)), store, "new", 1,
                               str(repo), head, MINE))  # fmt: skip
    assert out == ([], {"_failed": "memory_rule_check"}) and mr.load(store)[mr.AUDITED] == []
    broken, _ = asyncio.run(mr.audit(Squire(PickDecider("C")), store, "new", 1, str(repo), head,
                                     MINE))  # fmt: skip
    assert [r["text"] for r in broken] == ["Rule C can never change in this project."]


@needs_git
def test_review_h1_a_secret_in_a_rule_never_reaches_the_decider(tmp_path: Path) -> None:
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    mr._save(
        store,
        {
            "rules": [
                {
                    "text": f"Never rotate the key {secret}, ops depends on it.",
                    "session": "old",
                    "index": 1,
                    "at": 1.0,
                    "files": ["app/config.py"],
                }
            ],
            "asked": [],
            mr.AUDITED: [],
        },
    )
    (repo / "app" / "config.py").write_text("x = 1\n", "utf-8")
    decider = RuleDecider()
    asyncio.run(mr.audit(Squire(decider), store, "new", 1, str(repo), head, MINE))
    sent = json.dumps([str(c[2]["broken"].options) for c in decider.calls if "broken" in c[2]])
    assert decider.calls and secret not in sent


@needs_git
def test_a_rule_kept_calls_broken_is_not_sent_back_when_relation_says_it_keeps(
        tmp_path: Path) -> None:  # fmt: skip
    """2026-10-03, real sessions: 4 of 8 false sends-back had relation 'keeps' or 'unrelated'."""
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    asyncio.run(mr.extract(squire(), store, [episode(RULE, session="old")]))
    (repo / "app" / "config.py").write_text(
        "def load():\n    return {\n    'timeout': env('APP_PAYMENT_TIMEOUT'),\n    }\n", "utf-8"
    )
    decider = RuleDecider(relation="keeps")
    broken, found = asyncio.run(mr.audit(Squire(decider), store, "new", 1, str(repo), head, MINE))
    assert broken == [] and list(found.values())[0]["breaks_first"] is False
    assert any(point == "memory_rule_relation" for point, _, _ in decider.calls)


def test_sentences_join_a_wrapped_line_and_leave_layout_out() -> None:
    text = (
        "## Rules that are not negotiated\n"
        "Every migration has to be reversible, with a working down step, and\n"
        "never edited once it is merged.\n"
        "SIX RULES I KEEP REPEATING\n"
        "| column | value |\n"
        "Rules:\n"
        "- Never commit straight to main.\n"
        "Store the keys in the .env file"
    )
    assert sentences(text) == [
        "Every migration has to be reversible, with a working down step, and never edited "
        "once it is merged.",
        "Never commit straight to main.",
        "Store the keys in the .env file",
    ]


def test_sentences_keep_a_persons_short_lines_apart() -> None:
    """A new thought starts with a capital: short lines without a stop are not joined."""
    text = "Push everything to dev\nThe policy does not go into git\nAre the duplicates gone?"
    assert sentences(text) == [
        "Push everything to dev",
        "The policy does not go into git",
        "Are the duplicates gone?",
    ]


class RelationDecider(PickDecider):
    """PickDecider whose `kept` for the picked rule and whose relation answer are set: `bare`
    names the option with no probabilities, `down` fails the relation decision."""

    def __init__(self, pick: str, kept: float = 0.1, relation: str = "breaks") -> None:
        super().__init__(pick)
        self.kept, self.mode = kept, relation

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        if "relation" in questions:
            self.calls.append((point, state, dict(questions)))
            if self.mode == "down":
                return Decision(point=point, answers={}, provider=self.name, model="scripted-1",
                                error="down")  # fmt: skip
            return Decision(point=point, answers={"relation": choice("breaks", 0.6)},
                            provider=self.name, model="scripted-1")  # fmt: skip
        if "kept" in questions and state["rule"].startswith(f"Rule {self.pick} "):
            self.calls.append((point, state, dict(questions)))
            return Decision(point=point, answers={"kept": yes(self.kept)}, provider=self.name,
                            model="scripted-1")  # fmt: skip
        return await super().decide(point, state, questions)


def _audit_eight(tmp_path: Path, decider: RuleDecider) -> tuple[Path, Any]:
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo)
    (repo / "app" / "config.py").write_text("x = 1\n", "utf-8")
    _eight_rules(store)
    return store, asyncio.run(mr.audit(Squire(decider), store, "new", 1, str(repo), head, MINE))


@needs_git
def test_review_v81_a_relation_named_without_probabilities_still_sends_back(
        tmp_path: Path) -> None:  # fmt: skip
    """A provider may give the choice and no probabilities: max() over nothing must not turn
    every audit into a failure (review of v8.1, HIGH)."""
    _, (broken, _) = _audit_eight(tmp_path, RelationDecider("C", relation="bare"))
    assert [r["text"] for r in broken] == ["Rule C can never change in this project."]


@needs_git
def test_review_v81_a_failed_relation_marks_nothing_and_is_asked_again(tmp_path: Path) -> None:
    store, out = _audit_eight(tmp_path, RelationDecider("C", relation="down"))
    assert out == ([], {"_failed": "memory_rule_relation"}) and mr.load(store)[mr.AUDITED] == []


@needs_git
def test_review_v81_kept_between_045_and_05_is_no_longer_doubtful(tmp_path: Path) -> None:
    """BROKEN_BELOW 0.45 (2026-10-03): a `kept` of 0.47 is not sent back nor asked the relation."""
    decider = RelationDecider("C", kept=0.47)
    _, (broken, found) = _audit_eight(tmp_path, decider)
    assert broken == [] and not any(p == "memory_rule_relation" for p, _, _ in decider.calls)
    assert any(v["kept"] == 0.47 for v in found.values())


def test_sentences_start_a_spanish_question_on_its_own_line() -> None:
    text = (
        "Revisa que las migraciones se puedan deshacer siempre con su paso de bajada\n"
        "¿Por que falla el test de esquema?"
    )
    assert sentences(text) == [
        "Revisa que las migraciones se puedan deshacer siempre con su paso de bajada",
        "¿Por que falla el test de esquema?",
    ]
