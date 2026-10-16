"""A paid decider out of funds: a breaker shared by every process on the machine, and a notice.

Why this exists (audit of 2026-10-06): with the TypeSafe balance at zero, Jev answers HTTP 402,
the squire fails open, and every part of S keeps running on its defaults **without saying so**.
Four GAIA sessions of h2h-s1 were invalidated that way, and the memory points journaled nothing.

Hooks are short-lived processes, so an in-process breaker would forget the 402 at the next
shell command. The trip is a small file instead, one per endpoint and key (a 402 is about an
account, not a session). While it is fresh a provider does not call: it raises at once. When it
goes stale (`SANCHOPANZA_FUNDS_BREAKER_S`, 300 s by default) one call goes through again, and a
200 clears it, so a top-up recovers on its own within minutes. `jev-preflight` clears it at once.

The notice is how a person finds out: the squire journals a warning and writes one line to
stderr, and every hook that prints JSON carries a `systemMessage`, at most once per
`NOTICE_S` across all processes, so the message is seen without flooding the session.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

from . import _env, durable

BREAKER_S = 300.0
NOTICE_S = 600.0
_FILE_PREFIX = "out-of-funds-"


def funds_dir() -> Path:
    """`SANCHOPANZA_FUNDS_DIR`, else `<home>/funds`."""
    return Path(_env.get("FUNDS_DIR", "") or _env.home_dir() / "funds")


def breaker_s() -> float:
    try:
        return max(0.0, float(_env.get("FUNDS_BREAKER_S", "") or BREAKER_S))
    except ValueError:
        return BREAKER_S


def scope(base_url: str, key: str) -> str:
    """One trip per endpoint and key, never the key itself on disk."""
    return hashlib.sha256(f"{base_url}\n{key}".encode()).hexdigest()[:16]


def _path(name: str) -> Path:
    return funds_dir() / f"{_FILE_PREFIX}{name}.json"


def _num(value: Any) -> float:
    """A finite number, or 0. A hand-edited or half-written file must read as stale, never
    raise: a breaker that raises on every decision would stick until someone deletes it."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    numbers = {k: _num(data.get(k)) for k in ("at", "first", "status", "count")}
    return {**data, **numbers, "status": int(numbers["status"]) or 402,
            "count": int(numbers["count"])}  # fmt: skip


def _retry(action: Any) -> bool:
    """Windows refuses to replace or delete a file another process has open (every hook reads
    this one), with PermissionError. Those holds last microseconds: three short retries."""
    for attempt in range(3):
        try:
            action()
        except FileNotFoundError:
            return False
        except PermissionError:
            time.sleep(0.02 * (attempt + 1))
            continue
        except OSError:
            return False
        return True
    return False


def _write(path: Path, data: dict[str, Any]) -> bool:
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(data))
            durable.sync(handle)  # the breaker is not lost when the machine goes down
    except OSError:  # a breaker that cannot be written must not take the caller down
        return False
    done = _retry(lambda: os.replace(tmp, path))
    if not done:
        with contextlib.suppress(OSError):
            tmp.unlink()
    return done


def tripped(name: str, now: float | None = None) -> dict[str, Any] | None:
    """The live trip for this scope, or None when there is none or it went stale. A trip
    from the future (the clock went back) counts as stale rather than open for hours."""
    data = _read(_path(name))
    if data is None:
        return None
    age = (time.time() if now is None else now) - data["at"]
    return data if 0 <= age < breaker_s() else None


def trip(name: str, provider: str, status: int, detail: str = "") -> dict[str, Any]:
    """Record a refusal for lack of funds. Keeps the first time seen while the trip lives."""
    path = _path(name)
    now = time.time()
    old = tripped(name, now) or {}
    data = {
        "provider": provider,
        "status": status,
        "detail": detail[:300],
        "at": now,
        "first": old.get("first") or now,
        "count": int(old.get("count") or 0) + 1,
    }
    _write(path, data)
    return data


def clear(name: str) -> bool:
    """Forget the trip (the provider answered). True if there was one."""
    return _retry(_path(name).unlink)


def message(data: dict[str, Any]) -> str:
    provider = str(data.get("provider") or "the decider")
    since = time.strftime("%H:%M", time.localtime(float(data.get("first") or data.get("at") or 0)))
    return (
        f"sanchopanza: {provider} is out of funds (HTTP {data.get('status', 402)} since {since}). "
        "Every S component is running on its defaults, without its judgments, until the balance "
        f"is topped up. {_check_hint(provider)}"
    )


def _check_hint(provider: str) -> str:
    """How to check: Jev and a CLM server have a preflight; another provider's account is
    checked where it is billed."""
    if provider in ("jev", "clm", "the decider"):
        return "Check with `python -m sanchopanza jev-preflight`."
    return f"Check the {provider} account's balance; the breaker clears on its first answer."


def live() -> list[dict[str, Any]]:
    """Every fresh trip on this machine."""
    folder = funds_dir()
    if not folder.is_dir():
        return []
    found = (tripped(p.stem[len(_FILE_PREFIX) :]) for p in folder.glob(f"{_FILE_PREFIX}*.json"))
    return [d for d in found if d is not None]


def _noticed_path(name: str) -> Path:
    return funds_dir() / f"noticed-{name}.json"


def notice(now: float | None = None) -> str | None:
    """The message to show a person now, at most once per `NOTICE_S` per trip, or None.

    The stamp lives in its own file: rewriting the trip to stamp it could bring back a trip
    that a 200 had just cleared, and every hook would then skip the decider for minutes."""
    now = time.time() if now is None else now
    folder = funds_dir()
    if not folder.is_dir():
        return None
    for path in sorted(folder.glob(f"{_FILE_PREFIX}*.json")):
        name = path.stem[len(_FILE_PREFIX) :]
        data = tripped(name, now)
        if data is None:
            continue
        stamp = _read(_noticed_path(name)) or {}
        same_trip = stamp.get("trip") == data["first"]
        if same_trip and 0 <= now - stamp["at"] < NOTICE_S:
            continue
        _write(_noticed_path(name), {"at": now, "trip": data["first"]})
        return message(data)
    return None


def with_notice(payload: Any) -> Any:
    """`payload` with the out-of-funds notice added as `systemMessage`, when one is due.

    Only a JSON object gets it, and an existing message is kept in front of ours."""
    if not isinstance(payload, dict):
        return payload
    try:
        text = notice()
    except Exception:  # noqa: BLE001 - the notice must never break a hook's own output
        return payload
    if not text:
        return payload
    earlier = str(payload.get("systemMessage") or "")
    return {**payload, "systemMessage": f"{earlier}\n{text}" if earlier else text}


_stderr_said = False


def say_once(text: str) -> None:
    """One line on stderr per process."""
    global _stderr_said
    if _stderr_said:
        return
    _stderr_said = True
    with contextlib.suppress(OSError, ValueError):
        sys.stderr.write(text + chr(10))
