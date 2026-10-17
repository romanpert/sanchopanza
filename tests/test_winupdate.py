"""`benchmarks/memory_carry/winupdate.py`: the quiet hours of a long lot lift only while Windows
Update is paused well past the check. Free: the registry is replaced by a reader."""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "winupdate_under_test", ROOT / "benchmarks" / "memory_carry" / "winupdate.py"
)
assert _SPEC and _SPEC.loader
wu = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(wu)

NOW = dt.datetime(2026, 10, 17, 3, 0, tzinfo=dt.UTC)


def _reader(**values: str):
    """The registry as Settings leaves it while paused: the agent's flag on, plus `values`."""
    return lambda: {"PausedQualityStatus": "1", **values}


def test_no_pause_keeps_the_quiet_hours() -> None:
    assert wu.quiet_lifted(NOW, _reader()) == ""
    assert wu.quiet_lifted(NOW, lambda: {}) == ""


def test_stale_end_times_without_the_agents_flag_keep_them() -> None:
    read = _reader(PauseUpdatesExpiryTime="2026-10-24T01:10:00Z", PausedQualityStatus="0")
    assert wu.quiet_lifted(NOW, read) == ""
    assert wu.quiet_lifted(NOW, lambda: {"PauseUpdatesExpiryTime": "2026-10-24T01:10:00Z"}) == ""


def test_a_week_long_pause_lifts_them() -> None:
    read = _reader(PauseUpdatesExpiryTime="2026-10-24T01:10:00Z",
                   PauseQualityUpdatesEndTime="2026-10-24T01:10:00Z")  # fmt: skip
    assert "2026-10-24 01:10" in wu.quiet_lifted(NOW, read)


def test_a_pause_ending_within_the_margin_keeps_them() -> None:
    soon = (NOW + wu.MARGIN - dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert wu.quiet_lifted(NOW, _reader(PauseUpdatesExpiryTime=soon)) == ""
    later = (NOW + wu.MARGIN).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert wu.quiet_lifted(NOW, _reader(PauseUpdatesExpiryTime=later))


def test_the_earliest_end_counts() -> None:
    read = _reader(PauseUpdatesExpiryTime="2026-10-24T00:00:00Z",
                   PauseQualityUpdatesEndTime="2026-10-17T12:00:00Z")  # fmt: skip
    assert wu.quiet_lifted(NOW, read) == ""


def test_an_unreadable_value_is_no_pause() -> None:
    read = _reader(PauseUpdatesExpiryTime="2026-10-24T00:00:00Z",
                   PauseQualityUpdatesEndTime="soon")  # fmt: skip
    assert wu.quiet_lifted(NOW, read) == ""


def test_a_naive_time_is_read_as_utc_and_now_may_be_local() -> None:
    read = _reader(PauseUpdatesExpiryTime="2026-10-24T00:00:00")
    assert wu.quiet_lifted(dt.datetime(2026, 10, 17, 5, 0), read)


def test_the_real_reader_returns_a_mapping() -> None:
    found = wu._read_ux()
    assert isinstance(found, dict) and set(found) <= {*wu.ENDS, wu.PAUSED}
