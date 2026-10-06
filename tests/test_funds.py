"""Out of funds (HTTP 402): the breaker shared by every process, the notice, and the preflight.

The audit of 2026-10-06 found that with the TypeSafe balance at zero every part of S fell open in
silence. These tests pin the three answers to that: a 402 is remembered across processes and not
called again while fresh, a person is told, and a launcher can check for one cent before spending.
No network: httpx's MockTransport stands in for the service.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from sanchopanza import funds
from sanchopanza.contract import DeciderOutOfFunds, Truth
from sanchopanza.journal import MemoryJournal
from sanchopanza.providers import jev
from sanchopanza.providers.jev import JevDecider, apreflight
from sanchopanza.squire import Squire

OK_BODY = {
    "model": "jev-1.13.0",
    "answers": {"ok": {"type": "noul", "noul": 0.9}, "q": {"type": "noul", "noul": 0.9}},
    "usage": {"input_tokens": 300},
}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SANCHOPANZA_FUNDS_DIR", str(tmp_path / "funds"))
    monkeypatch.delenv("SANCHOPANZA_FUNDS_BREAKER_S", raising=False)
    monkeypatch.setattr(funds, "_stderr_said", False)
    monkeypatch.setattr(jev, "BASE_WAIT_S", 0.0)


class Service:
    """Answers with the given statuses in turn (the last one repeats) and counts the calls."""

    def __init__(self, *statuses: int) -> None:
        self.statuses = list(statuses)
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        status = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        if status == 200:
            return httpx.Response(200, json=OK_BODY)
        return httpx.Response(status, json={"error": {"type": "billing_error"}})


def client(service: Service) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=jev.BASE_URL, transport=httpx.MockTransport(service))


def decider(service: Service) -> JevDecider:
    return JevDecider("k", client=client(service))


def ask(d: Any) -> Any:
    return asyncio.run(d.decide("p", "state", {"q": Truth("is it?")}))


def test_a_402_raises_out_of_funds_and_trips_the_breaker() -> None:
    service = Service(402)
    with pytest.raises(DeciderOutOfFunds) as caught:
        ask(decider(service))
    assert caught.value.status == 402
    assert service.calls == 1  # a 402 is not retried
    assert len(funds.live()) == 1


def test_while_the_breaker_is_fresh_no_process_calls() -> None:
    ask_first = Service(402)
    with pytest.raises(DeciderOutOfFunds):
        ask(decider(ask_first))
    other_process = Service(200)  # a new decider stands for the next hook process
    with pytest.raises(DeciderOutOfFunds):
        ask(decider(other_process))
    assert other_process.calls == 0


def test_a_stale_breaker_lets_one_call_through_and_a_200_clears_it(monkeypatch) -> None:
    with pytest.raises(DeciderOutOfFunds):
        ask(decider(Service(402)))
    monkeypatch.setenv("SANCHOPANZA_FUNDS_BREAKER_S", "0")
    topped_up = Service(200)
    decision = ask(decider(topped_up))
    assert topped_up.calls == 1 and decision.cost_usd > 0
    monkeypatch.delenv("SANCHOPANZA_FUNDS_BREAKER_S")
    assert funds.live() == []


def test_the_breaker_is_per_endpoint_and_key() -> None:
    with pytest.raises(DeciderOutOfFunds):
        ask(decider(Service(402)))
    other_key = Service(200)
    asyncio.run(JevDecider("another", client=client(other_key)).decide(
        "p", "state", {"q": Truth("is it?")}))  # fmt: skip
    assert other_key.calls == 1


def test_the_squire_journals_and_says_out_of_funds_once(capsys) -> None:
    journal = MemoryJournal()
    squire = Squire(decider(Service(402)), journal=journal)
    first = asyncio.run(squire.decide("p", "state", {"q": Truth("is it?")}))
    second = asyncio.run(squire.decide("p", "state", {"q": Truth("is it?")}))
    assert first.failed and second.failed
    warnings = [e["data"] for e in journal.events if e["kind"] == "warning"]
    assert len(warnings) == 1 and warnings[0]["out_of_funds"] is True
    assert capsys.readouterr().err.count("out of funds") == 1


def test_other_failures_reach_the_journal_once_per_error() -> None:
    journal = MemoryJournal()
    squire = Squire(decider(Service(400)), journal=journal)
    for _ in range(3):
        asyncio.run(squire.decide("p", "state", {"q": Truth("is it?")}))
    warnings = [e["data"] for e in journal.events if e["kind"] == "warning"]
    assert len(warnings) == 1 and "HTTP 400" in warnings[0]["error"]


def test_a_hook_carries_the_notice_once_per_window(capsys) -> None:
    from sanchopanza.harness.hookio import stdout_json

    with pytest.raises(DeciderOutOfFunds):
        ask(decider(Service(402)))
    stdout_json({"systemMessage": "earlier"})
    stdout_json({})
    first, second = (json.loads(line) for line in capsys.readouterr().out.replace("}{", "}\n{")
                     .splitlines())  # fmt: skip
    assert first["systemMessage"].startswith("earlier")
    assert "out of funds" in first["systemMessage"]
    assert second == {}


def test_no_notice_without_a_trip(capsys) -> None:
    from sanchopanza.harness.hookio import stdout_json

    stdout_json({"x": 1})
    assert json.loads(capsys.readouterr().out) == {"x": 1}


@pytest.mark.parametrize(
    ("status", "reason"),
    [(402, "no_funds"), (401, "auth"), (403, "auth"), (500, "unreachable"), (400, "other")],
)
def test_preflight_names_the_reason(status: int, reason: str) -> None:
    result = asyncio.run(apreflight("k", client=client(Service(status))))
    assert not result.ok and result.reason == reason and result.http_status == status


def test_preflight_ok_costs_cents_and_clears_the_breaker() -> None:
    with pytest.raises(DeciderOutOfFunds):
        ask(decider(Service(402)))
    service = Service(200)
    result = asyncio.run(apreflight("k", client=client(service)))
    assert result.ok and result.reason == "ok" and service.calls == 1  # it ignores the breaker
    assert 0 < result.cost_usd < 0.0001
    assert funds.live() == []


def test_preflight_without_a_key(monkeypatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    result = asyncio.run(apreflight(None))
    assert not result.ok and result.reason == "no_key"


def test_preflight_unreachable_network() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    broken = httpx.AsyncClient(base_url=jev.BASE_URL, transport=httpx.MockTransport(down))
    result = asyncio.run(apreflight("k", client=broken))
    assert not result.ok and result.reason == "unreachable" and result.http_status is None


@pytest.mark.parametrize(
    ("reason", "code"),
    [("ok", 0), ("no_funds", 10), ("auth", 11), ("no_key", 12), ("unreachable", 13), ("other", 14)],
)
def test_cli_exit_codes(monkeypatch, capsys, reason: str, code: int) -> None:
    from sanchopanza import cli

    canned = jev.PreflightResult(reason == "ok", reason, None, 0.0, "jev-1.13.0", "")
    monkeypatch.setattr(jev, "preflight", lambda **_: canned)
    assert cli.main(["jev-preflight", "--json"]) == code
    assert json.loads(capsys.readouterr().out)["reason"] == reason


def test_memory_rule_points_journal_their_decisions() -> None:
    from sanchopanza.harness import memory_rules

    journal = MemoryJournal()
    squire = Squire(decider(Service(200)), journal=journal)
    decision = asyncio.run(memory_rules._decided(squire, "memory_rule_check", "state",
                                                 {"q": Truth("is it?")}))  # fmt: skip
    rows = journal.decisions()
    assert not decision.failed and len(rows) == 1 and rows[0]["point"] == "memory_rule_check"


def test_a_mistyped_flag_never_reads_as_a_preflight_reason() -> None:
    from sanchopanza import cli

    with pytest.raises(SystemExit) as caught:
        cli.main(["jev-preflight", "--timout", "5"])
    assert caught.value.code not in set(jev.PREFLIGHT_EXIT.values())


def test_the_journal_row_keeps_the_text_launchers_grep_for() -> None:
    import re

    journal = MemoryJournal()
    asyncio.run(Squire(decider(Service(402)), journal=journal).decide(
        "p", "state", {"q": Truth("is it?")}))  # fmt: skip
    row = next(e["data"] for e in journal.events if e["kind"] == "warning")
    assert re.search(r"did not answer: HTTP 40[123]", row["error"])


def test_an_open_breaker_keeps_the_text_launchers_grep_for() -> None:
    import re

    with pytest.raises(DeciderOutOfFunds):
        ask(decider(Service(402)))
    with pytest.raises(DeciderOutOfFunds) as caught:
        ask(decider(Service(200)))
    assert re.search(r"did not answer: HTTP 40[123]", str(caught.value))


def test_a_fallback_chain_with_every_link_out_of_funds_stays_out_of_funds() -> None:
    from sanchopanza.providers.chain import FallbackDecider
    from sanchopanza.providers.fixed import BrokenDecider

    chain = FallbackDecider([decider(Service(402)), BrokenDecider()])
    with pytest.raises(DeciderOutOfFunds):
        ask(chain)


def test_a_cascade_does_not_escalate_everything_when_the_cheap_stage_is_out_of_funds() -> None:
    from sanchopanza.providers.chain import CascadeDecider

    expensive = Service(200)
    cascade = CascadeDecider(decider(Service(402)), JevDecider("other", client=client(expensive)),
                             tau=0.5)  # fmt: skip
    with pytest.raises(DeciderOutOfFunds):
        ask(cascade)
    assert expensive.calls == 0


@pytest.mark.parametrize("at", ['"yesterday"', "null", "1e999", "[]"])
def test_a_corrupt_trip_file_reads_as_stale_and_never_raises(at: str) -> None:
    name = funds.scope(jev.BASE_URL, "k")
    path = funds.funds_dir() / f"out-of-funds-{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"at": ' + at + ', "first": "x", "status": "?"}', encoding="utf-8")
    service = Service(200)
    ask(decider(service))
    assert service.calls == 1
    assert funds.notice() is None


def test_a_trip_from_the_future_is_stale() -> None:
    import time

    name = funds.scope(jev.BASE_URL, "k")
    funds.trip(name, "jev", 402)
    assert funds.tripped(name, now=time.time() - 3600) is None


def test_stamping_the_notice_never_brings_back_a_cleared_trip() -> None:
    with pytest.raises(DeciderOutOfFunds):
        ask(decider(Service(402)))
    assert funds.notice() is not None
    ask_ok = Service(200)
    import os

    os.environ["SANCHOPANZA_FUNDS_BREAKER_S"] = "0"
    try:
        ask(decider(ask_ok))
    finally:
        del os.environ["SANCHOPANZA_FUNDS_BREAKER_S"]
    assert funds.notice() is None and funds.live() == []
    assert ask_ok.calls == 1


def test_a_new_trip_after_a_clear_is_noticed_again() -> None:
    import time

    name = funds.scope(jev.BASE_URL, "k")
    funds.trip(name, "jev", 402)
    assert funds.notice() is not None
    funds.clear(name)
    time.sleep(0.01)
    funds.trip(name, "jev", 402)
    assert funds.notice() is not None


def test_preflight_never_raises(monkeypatch) -> None:
    def broken(*_: Any, **__: Any) -> None:
        raise ValueError("corrupt")

    monkeypatch.setattr(funds, "trip", broken)
    result = asyncio.run(apreflight("k", client=client(Service(402))))
    assert not result.ok and result.reason == "other"
