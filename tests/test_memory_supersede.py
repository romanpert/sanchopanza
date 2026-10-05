"""F1 supersession ("A + P"): a rule the person has since contradicted is not quoted back at them.

A, at audit time (v8.3): after a break is confirmed (`kept` and `relation`), one Truth per text
said since (the request's prompt, and each stored rule said after the rule) asks whether the
person, in it, asks for what the rule forbids or states its opposite; if the highest reaches
SUPERSEDED_AT, no send-back, and the hook log says which. Measured on
`benchmarks/memory_carry/supersede_bench.py`. P, at a session's start: every rule given with its
date and minute, newest first, under a header that says the newer of two conflicting rules
stands. A scripted decider stands in for Jev; git is real."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from sanchopanza import Decision
from sanchopanza.harness import memory_hook as mh
from sanchopanza.harness import memory_rules as mr
from sanchopanza.squire import Squire

from .helpers import bench_module, choice, yes

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="no git")
ROOT = Path(__file__).resolve().parent.parent

RULE = "Ops sets PAYMENT_TIMEOUT by that exact name in every deployment, it can't be renamed."
# The carry bench's `columns` rule as v8.1 stores it (lead-in kept, a83929f) and its second prompt.
COLUMNS = ("For context: finance's Excel macro reads this CSV by column position, so the order of "
           "the columns can never change.")  # fmt: skip
CURRENCY = ("Add the order's currency (row['currency']) to the CSV export in app/export.py and "
            "add a test for it.")  # fmt: skip
REPLACING = ("no longer", "drop the old")
T0 = 1_790_000_000.0


class SupersedeDecider:
    """The rule whose text holds `marker` is the one the diff breaks (named, `kept` 0.1, relation
    `breaks`); every other rule is kept. The supersession Truth answers 0.9 for a text holding one
    of REPLACING, else 0.1. `mode`: `down` (a failed decision), `raise`, `weak` (every text at
    `weak`), `partial` (the stored texts fail, the request answers), `slow` (answers after 3 s)."""

    name = "scripted"
    accepts_attachments = False

    def __init__(self, marker: str, mode: str = "ok", weak: float = 0.74) -> None:
        self.marker, self.mode, self.weak = marker, mode, weak
        self.calls: list[tuple[str, Any, dict[str, Any]]] = []

    def _done(self, point: str, **answers: Any) -> Decision:
        return Decision(point=point, answers=answers, provider=self.name, model="scripted-1")

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        self.calls.append((point, state, dict(questions)))
        if "broken" in questions:
            options = questions["broken"].options
            probs = {k: (0.9 if self.marker in v else 0.0) for k, v in options.items()}
            probs["none"] = 0.1
            return self._done(point, broken=choice(max(probs, key=probs.get), 0.8, **probs))
        if "kept" in questions:
            return self._done(point, kept=yes(0.1 if self.marker in state["rule"] else 0.9))
        if "relation" in questions:
            first = "breaks" if self.marker in state["rule"] else "unrelated"
            probs = {k: (0.8 if k == first else 0.1) for k in questions["relation"].options}
            return self._done(point, relation=choice(first, 0.6, **probs))
        if "against" in questions:
            return await self._against(point, state)
        return self._done(point)

    async def _against(self, point: str, state: dict[str, Any]) -> Decision:
        if self.mode == "slow":
            await asyncio.sleep(3)
        if self.mode == "raise":
            raise RuntimeError("provider down")
        failing = self.mode == "down" or (self.mode == "partial" and state["said_when"] != mr.NOW)
        if failing:
            return Decision(point=point, answers={}, provider=self.name, model="scripted-1",
                            error="down")  # fmt: skip
        if self.mode == "weak":
            return self._done(point, against=yes(self.weak))
        hit = any(w in state["said"] for w in REPLACING)
        return self._done(point, against=yes(0.9 if hit else 0.1))


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True)  # fmt: skip
    return done.stdout.strip()


def _repo(root: Path, rel: str, text: str) -> str:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, "utf-8")
    for args in (["init", "-q"], ["config", "user.email", "t@example.org"],
                 ["config", "user.name", "t"], ["add", "."], ["commit", "-qm", "base"]):
        _git(root, *args)
    return _git(root, "rev-parse", "HEAD")


def _rule(text: str, at: float, session: str = "old", files: tuple[str, ...] = ()) -> dict:
    return {"text": text, "p": 0.9, "session": session, "index": 1, "at": at,
            "files": list(files)}  # fmt: skip


def _payment(tmp_path: Path, rules: list[dict]) -> tuple[Path, Path, str]:
    """A repository whose request renamed PAYMENT_TIMEOUT, and a store holding `rules`."""
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo, "app/config.py", "TIMEOUT = env('PAYMENT_TIMEOUT')\n")
    (repo / "app" / "config.py").write_text("TIMEOUT = env('APP_PAYMENT_TIMEOUT')\n", "utf-8")
    mr._save(store, {"rules": rules, "asked": [], mr.AUDITED: []})
    return repo, store, head


def _audit(decider: SupersedeDecider, store: Path, repo: Path, head: str, request: str,
           paths: list[str]) -> tuple[list[dict], dict, list[dict]]:  # fmt: skip
    rows: list[dict] = []
    broken, found = asyncio.run(mr.audit(Squire(decider), store, "new", 1, str(repo), head,
                                         paths, request=request, note=rows.append))  # fmt: skip
    return broken, found, rows


def _asked(decider: SupersedeDecider) -> list[tuple[str, Any, dict[str, Any]]]:
    return [c for c in decider.calls if c[0] == "memory_rule_superseded"]


# ---- A: at audit time ----------------------------------------------------------------------


@needs_git
def test_a_rule_the_request_itself_contradicts_is_not_sent_back(tmp_path: Path) -> None:
    repo, store, head = _payment(tmp_path, [_rule(RULE, T0, files=("app/config.py",))])
    request = ("Rename PAYMENT_TIMEOUT to APP_PAYMENT_TIMEOUT. Ops moved to the new name last "
               "week, so the old rule about PAYMENT_TIMEOUT no longer applies.")  # fmt: skip
    decider = SupersedeDecider("can't be renamed")
    broken, found, rows = _audit(decider, store, repo, head, request, ["app/config.py"])
    assert broken == []
    [row] = [r for r in rows if r.get("part") == "superseded"]
    assert row["rule"] == RULE and row["suppressed"] is True and row["source"] == "request"
    assert row["by"] == request and row["p"] == pytest.approx(0.9) and row["asked"] == 1
    assert list(found.values())[0]["superseded"] == pytest.approx(0.9)
    [(_, state, questions)] = _asked(decider)  # one Truth: the request, nothing stored since
    assert questions == {"against": mr.SUPERSEDE}
    assert state["said"] == request and state["said_when"] == mr.NOW
    assert state["rule"] == RULE and state["rule_said"] == mr._when(T0)
    assert mr.load(store)[mr.AUDITED] == ["new-001"]  # asked once, as any audit


@needs_git
def test_a_newer_stored_rule_that_contradicts_it_stops_the_send_back(tmp_path: Path) -> None:
    newer = "From now on ops reads APP_PAYMENT_TIMEOUT; drop the old PAYMENT_TIMEOUT name."
    rules = [_rule(newer, T0 + 7_200, session="later"), _rule(RULE, T0)]
    repo, store, head = _payment(tmp_path, rules)
    decider = SupersedeDecider("can't be renamed")
    broken, _, rows = _audit(decider, store, repo, head, "Give every variable an APP_ prefix.",
                             ["app/config.py"])  # fmt: skip
    assert broken == []
    [row] = [r for r in rows if r.get("part") == "superseded"]
    assert row["by"] == newer and row["source"] == "stored" and row["suppressed"] is True
    assert row["asked"] == 2
    whens = {s["said"]: s["said_when"] for _, s, _ in _asked(decider)}
    assert whens[newer] == f"{mr._when(T0 + 7_200)}, as a rule for the project"


@needs_git
def test_an_older_stored_rule_is_never_asked(tmp_path: Path) -> None:
    older = "Never drop the old config names without asking ops first."
    rules = [_rule(RULE, T0 + 7_200), _rule(older, T0, session="before")]
    repo, store, head = _payment(tmp_path, rules)
    decider = SupersedeDecider("can't be renamed")
    broken, _, _ = _audit(decider, store, repo, head, "Give every variable an APP_ prefix.",
                          ["app/config.py"])  # fmt: skip
    assert [r["text"] for r in broken] == [RULE]
    assert [s["said"] for _, s, _ in _asked(decider)] == ["Give every variable an APP_ prefix."]


def test_at_most_newer_max_stored_rules_are_asked_newest_first() -> None:
    stored = [_rule(f"Stored rule number {n} about something else.", T0 + n * 60)
              for n in range(1, mr.NEWER_MAX + 3)]  # fmt: skip
    newer = mr._newer(_rule(RULE, T0), [*stored, _rule(RULE, T0)], "A request.")
    assert [s for _, s, _ in newer] == ["request"] + ["stored"] * mr.NEWER_MAX
    assert newer[1][0] == stored[-1]["text"] and newer[-1][0] == stored[2]["text"]


@needs_git
def test_the_columns_scene_still_sends_back_its_own_rule(tmp_path: Path) -> None:
    """The carry bench's own correct send-back: the second prompt adds a column and says nothing
    about the order, so the rule stands and the agent is sent back as before."""
    repo, store = tmp_path / "repo", tmp_path / "store"
    head = _repo(repo, "app/export.py", 'COLUMNS = ["id", "amount", "customer"]\n')
    (repo / "app" / "export.py").write_text(
        'COLUMNS = ["id", "currency", "amount", "customer"]\n', "utf-8")
    mr._save(store, {"rules": [_rule(COLUMNS, T0, files=("app/export.py",))], "asked": [],
                     mr.AUDITED: []})  # fmt: skip
    decider = SupersedeDecider("column position")
    broken, found, rows = _audit(decider, store, repo, head, CURRENCY, ["app/export.py"])
    assert [r["text"] for r in broken] == [COLUMNS]
    [row] = [r for r in rows if r.get("part") == "superseded"]
    assert row["suppressed"] is False and row["rule"] == COLUMNS
    assert [s["said"] for _, s, _ in _asked(decider)] == [CURRENCY]
    assert list(found.values())[0]["superseded"] == pytest.approx(0.1)


@needs_git
@pytest.mark.parametrize("mode", ["down", "raise"])
def test_supersession_fails_open_to_the_send_back(tmp_path: Path, mode: str) -> None:
    repo, store, head = _payment(tmp_path, [_rule(RULE, T0)])
    request = "Rename it; the old rule about PAYMENT_TIMEOUT no longer applies."
    decider = SupersedeDecider("can't be renamed", mode=mode)
    broken, _, rows = _audit(decider, store, repo, head, request, ["app/config.py"])
    assert [r["text"] for r in broken] == [RULE]
    [row] = [r for r in rows if r.get("part") == "superseded"]
    assert row["failed"] and row["suppressed"] is False
    assert mr.load(store)[mr.AUDITED] == ["new-001"]  # the audit itself was answered


@needs_git
def test_one_unanswered_text_sends_back_even_when_another_contradicts(tmp_path: Path) -> None:
    """Send back on any doubt: the request answers 0.9, a stored rule since goes unanswered."""
    rules = [_rule("Every log line starts with the request id.", T0 + 60), _rule(RULE, T0)]
    repo, store, head = _payment(tmp_path, rules)
    request = "Rename it; the old rule about PAYMENT_TIMEOUT no longer applies."
    decider = SupersedeDecider("can't be renamed", mode="partial")
    broken, _, rows = _audit(decider, store, repo, head, request, ["app/config.py"])
    assert [r["text"] for r in broken] == [RULE] and len(_asked(decider)) == 2
    [row] = [r for r in rows if r.get("part") == "superseded"]
    assert row["failed"] and row["suppressed"] is False


@needs_git
@pytest.mark.parametrize(("p", "suppressed"), [(0.74, False), (0.75, True)])
def test_the_cut_is_superseded_at(tmp_path: Path, p: float, suppressed: bool) -> None:
    """0.74 is the highest negative the bench's held-out third gave (an own carry rule): under
    the cut. Several texts just under it do not add up to one over it."""
    rules = [_rule(f"Stored rule {n} about the deployment.", T0 + n) for n in (1, 2, 3)]
    repo, store, head = _payment(tmp_path, [*rules, _rule(RULE, T0)])
    decider = SupersedeDecider("can't be renamed", mode="weak", weak=p)
    broken, _, rows = _audit(decider, store, repo, head, "Tidy up the config module.",
                             ["app/config.py"])  # fmt: skip
    assert mr.SUPERSEDED_AT == 0.75
    assert (broken == []) is suppressed
    [row] = [r for r in rows if r.get("part") == "superseded"]
    assert row["p"] == pytest.approx(p) and row["suppressed"] is suppressed and row["asked"] == 4


@needs_git
def test_a_late_supersession_answer_sends_back_within_the_audits_deadline(
        tmp_path: Path) -> None:  # fmt: skip
    """Review of F1, H2: the question gets what is left of the audit's deadline but the
    reserve; past it, the confirmed break is sent back and the audit is marked."""
    import time as clock

    repo, store, head = _payment(tmp_path, [_rule(RULE, T0)])
    request = "Rename it; the old rule about PAYMENT_TIMEOUT no longer applies."
    decider = SupersedeDecider("can't be renamed", mode="slow")
    rows: list[dict] = []
    began = clock.monotonic()
    deadline = began + mr.SUPERSEDE_RESERVE + 0.4
    broken, _ = asyncio.run(mr.audit(Squire(decider), store, "new", 1, str(repo), head,
                                     ["app/config.py"], request=request, note=rows.append,
                                     deadline=deadline))  # fmt: skip
    assert clock.monotonic() < deadline  # back before the caller's own wait_for would fire
    assert [r["text"] for r in broken] == [RULE]
    [row] = [r for r in rows if r.get("part") == "superseded"]
    assert "timed out" in row["failed"] and row["suppressed"] is False
    assert mr.load(store)[mr.AUDITED] == ["new-001"]


@needs_git
def test_no_time_left_means_no_question_and_the_send_back(tmp_path: Path) -> None:
    import time as clock

    repo, store, head = _payment(tmp_path, [_rule(RULE, T0)])
    decider = SupersedeDecider("can't be renamed")
    broken, _ = asyncio.run(mr.audit(Squire(decider), store, "new", 1, str(repo), head,
                                     ["app/config.py"], request="It no longer applies.",
                                     deadline=clock.monotonic()))  # fmt: skip
    assert [r["text"] for r in broken] == [RULE] and _asked(decider) == []


@needs_git
def test_nothing_newer_means_no_question_and_the_send_back(tmp_path: Path) -> None:
    repo, store, head = _payment(tmp_path, [_rule(RULE, T0)])
    decider = SupersedeDecider("can't be renamed")
    broken, _, _ = _audit(decider, store, repo, head, "", ["app/config.py"])
    assert [r["text"] for r in broken] == [RULE] and _asked(decider) == []


@needs_git
def test_supersession_is_asked_only_of_a_confirmed_break(tmp_path: Path) -> None:
    repo, store, head = _payment(tmp_path, [_rule(RULE, T0)])
    decider = SupersedeDecider("a marker no rule holds")
    broken, _, _ = _audit(decider, store, repo, head, "The old rule no longer applies.",
                          ["app/config.py"])  # fmt: skip
    assert broken == [] and _asked(decider) == []


@needs_git
def test_a_secret_in_the_request_never_reaches_the_supersession_question(tmp_path: Path) -> None:
    repo, store, head = _payment(tmp_path, [_rule(RULE, T0)])
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    request = f"Use the key {secret} for the payment provider from now on, please."
    decider = SupersedeDecider("can't be renamed")
    _audit(decider, store, repo, head, request, ["app/config.py"])
    sent = json.dumps([c[1] for c in _asked(decider)])
    assert _asked(decider) and secret not in sent


def test_the_shipped_question_is_the_one_the_bench_measured() -> None:
    bench = bench_module(ROOT / "benchmarks" / "memory_carry", "supersede_bench")
    assert bench.AGAINST == mr.SUPERSEDE
    state = bench.against_state(_rule(RULE, T0), "x" * 20, mr.NOW)
    assert state == mr.questions_for_superseded(_rule(RULE, T0), "x" * 20, mr.NOW)[0]


# ---- A through the hook --------------------------------------------------------------------


@pytest.fixture
def hook_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE", str(tmp_path / "memory"))
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE_LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("SANCHOPANZA_PROVIDER", "scripted")
    for name in ("SANCHOPANZA_MEMORY_SELECT", "SANCHOPANZA_MEMORY_RULES", "TYPESAFE_API_KEY",
                 "SANCHOPANZA_MEMORY_TREE", "SANCHOPANZA_MEMORY_PROMPT",
                 "SANCHOPANZA_MEMORY_STORE_KEY"):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    decider = SupersedeDecider("can't be renamed")
    monkeypatch.setattr("sanchopanza.harness.claude_code.squire_from_env",
                        lambda env=None, redact=False: Squire(decider))  # fmt: skip
    return tmp_path


def _transcript(path: Path, cwd: str, text: str) -> None:
    use = {"type": "tool_use", "id": "t1", "name": "Edit",
           "input": {"file_path": f"{cwd}/app/config.py", "old_string": "a", "new_string": "b"}}
    entries = [{"type": "user", "cwd": cwd, "timestamp": "2026-10-05T10:00:00Z",
                "message": {"role": "user", "content": text}},
               {"type": "assistant", "message": {"role": "assistant", "content": [use]}},
               {"type": "user", "message": {"role": "user", "content": [
                   {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}},
               {"type": "assistant", "message": {"role": "assistant", "content": [
                   {"type": "text", "text": "Done."}]}}]  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


@needs_git
def test_the_hook_passes_the_requests_prompt_and_logs_the_replacement(hook_env: Path) -> None:
    repo = hook_env / "repo"
    _repo(repo, "app/config.py", "TIMEOUT = env('PAYMENT_TIMEOUT')\n")
    cwd = str(repo).replace("\\", "/")
    base = {"session_id": "s2", "cwd": cwd,
            "transcript_path": str(hook_env / "projects" / "p" / "s2.jsonl")}  # fmt: skip
    store = mh.store_for(base)
    mr._save(store, {"rules": [_rule(RULE, T0, files=("app/config.py",))], "asked": [],
                     mr.AUDITED: []})  # fmt: skip
    text = "Rename PAYMENT_TIMEOUT to APP_PAYMENT_TIMEOUT; that old rule no longer applies."
    mh.handle({**base, "hook_event_name": "UserPromptSubmit", "prompt": text})
    (repo / "app" / "config.py").write_text("TIMEOUT = env('APP_PAYMENT_TIMEOUT')\n", "utf-8")
    _transcript(hook_env / "projects" / "p" / "s2.jsonl", cwd, text)
    assert mh.handle({**base, "hook_event_name": "Stop"}) == {}
    rows = [json.loads(x) for x in (hook_env / "log.jsonl").read_text("utf-8").splitlines()]
    [row] = [r for r in rows if r.get("part") == "superseded"]
    assert row["rule"] == RULE and "no longer applies" in row["by"] and row["suppressed"]


# ---- P: at a session's start ---------------------------------------------------------------


def test_a_given_rule_shows_its_date_and_minute() -> None:
    at = T0 + 3_723
    line = mr._line(_rule(RULE, at, files=("app/config.py",)))
    assert time.strftime("(%Y-%m-%d %H:%M", time.localtime(at)) in line


def test_the_header_says_the_newer_of_two_conflicting_rules_stands() -> None:
    assert "newest first" in mr.HEADER and "the newer one stands" in mr.HEADER


def test_two_rules_of_one_day_are_given_newest_first_with_their_times(tmp_path: Path) -> None:
    day = time.mktime((2026, 10, 5, 9, 0, 0, 0, 0, -1))
    morning = "Keep the export's columns in the order finance's macro expects."
    evening = "Finance retired the macro: the export's columns may be reordered now."
    # stored out of order (a merge, or an older writer): the time decides
    mr._save(tmp_path, {"rules": [_rule(morning, day), _rule(evening, day + 9 * 3_600)],
                        "asked": [], mr.AUDITED: []})  # fmt: skip
    text = mr.render(tmp_path)
    assert text.index(evening) < text.index(morning)
    assert "2026-10-05 18:00" in text and "2026-10-05 09:00" in text


def test_the_given_rules_stay_within_the_budget(tmp_path: Path) -> None:
    rules = [_rule(f"Rule {n}: " + "never change this part of the project " * 9, T0 + n,
                   files=("app/a.py", "app/b.py", "app/c.py", "app/d.py"))
             for n in range(mr.GIVE_MAX)]  # fmt: skip
    mr._save(tmp_path, {"rules": rules, "asked": [], mr.AUDITED: []})
    text = mr.render(tmp_path)
    assert text and len(text) <= mr.GIVE_CHARS
    assert text.startswith(mr.HEADER) and text.endswith(mr.CLOSING)
    assert text.count("\n- ") < mr.GIVE_MAX  # the budget, not GIVE_MAX, stopped it
