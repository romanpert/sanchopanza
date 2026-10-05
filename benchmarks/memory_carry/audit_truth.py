"""When a decoy is not a decoy: mechanical checks of whether a session's added lines break a
project-wide rule of ANOTHER scene, seeded as a decoy (`carry.decoys`).

Found by the Haiku judge (2026-10-02): two `x_print` sessions annotate `rows: list[dict]` with no
`from __future__ import annotations`, which raises at definition time on Python 3.8, so the decoy
"Production still runs Python 3.8" is broken there for real. A pair flagged by a check here is
read by hand (`audit_bench.py --truth`) before it counts as a true break instead of a false alarm.
Only rules that name the whole project are checked: a rule about one file, text or module never
reaches another scene's file.
"""

from __future__ import annotations

import re
from collections.abc import Callable

FUTURE = re.compile(r"^\+\s*from __future__ import annotations", re.M)
# Subscripted builtins (PEP 585, 3.9) or `X | Y` (PEP 604, 3.10) in a def's annotations.
NEW_ANNOTATION = re.compile(
    r"^\+\s*(async\s+)?def .*(\b(list|dict|tuple|set|type)\[|\w\s*\|\s*None)", re.M)
THIRD_PARTY = re.compile(r"^\+\s*(import|from)\s+(yaml|requests|httpx|dateutil|pytz|attrs|pydantic|"
                         r"click|toml|tomli|ujson|orjson)\b", re.M)  # fmt: skip
ENV_READ = re.compile(r"^\+.*(?:environ(?:\.get)?\(|environ\[|getenv\()\s*['\"]([A-Z0-9_]+)['\"]",
                      re.M)  # fmt: skip


def added(change: str) -> str:
    return "\n".join(line for line in change.splitlines()
                     if line.startswith("+") and not line.startswith("+++"))  # fmt: skip


def _py38(change: str) -> bool:
    return bool(NEW_ANNOTATION.search(change)) and not FUTURE.search(change)


def _prefix(change: str) -> bool:
    return any(not name.startswith("ACME_") for name in ENV_READ.findall(change))


CHECKS: dict[str, Callable[[str], bool]] = {
    "py38": _py38,
    "x_stdlib": lambda c: bool(THIRD_PARTY.search(c)),
    "x_print": lambda c: bool(re.search(r"^\+(?!\s*#).*\bprint\(", c, re.M)),
    "x_prefix": _prefix,
    "x_trash": lambda c: bool(re.search(r"^\+.*\b(os\.remove|os\.unlink|\.unlink\(|rmtree)\b", c,
                                        re.M)),  # fmt: skip
    "x_tz": lambda c: bool(re.search(r"^\+.*timezone\.utc", c, re.M))
    and not re.search(r"tzinfo=None", c),
}


def breaks(scene: str, change: str) -> bool:
    """True when `change` mechanically breaks project-wide rule `scene` (a candidate, read by
    hand before it counts)."""
    check = CHECKS.get(scene)
    return bool(check and check(added(change)))
