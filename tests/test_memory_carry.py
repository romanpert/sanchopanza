"""The carry pilot's instrument (`benchmarks/memory_carry/scenes.py`), before any session: each
scene's checks tell a session-2 result that keeps the fact from one that breaks it, its
repository passes its own tests, and nothing in the repository gives the fact away (the
shell_first pilot's traps were found by `grep`, 2026-10-02)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from .helpers import bench_module

ROOT = Path(__file__).resolve().parents[1]
scenes = bench_module(ROOT / "benchmarks" / "memory_carry", "scenes").SCENES

# Per scene: the file session 2 edits, a result that keeps the fact, one that breaks it.
RESULTS: dict[str, tuple[str, str, str]] = {
    "columns": (
        "app/export.py",
        'import csv\nimport io\n\nCOLUMNS = ["id", "amount", "customer", "currency"]\n\n\n'
        "def to_csv(rows):\n    out = io.StringIO()\n    w = csv.writer(out)\n"
        "    w.writerow(COLUMNS)\n    for r in rows:\n        w.writerow([r[c] for c in COLUMNS])\n"
        "    return out.getvalue()\n",
        'import csv\nimport io\n\nCOLUMNS = ["id", "amount", "currency", "customer"]\n\n\n'
        "def to_csv(rows):\n    out = io.StringIO()\n    w = csv.writer(out)\n"
        "    w.writerow(COLUMNS)\n    for r in rows:\n        w.writerow([r[c] for c in COLUMNS])\n"
        "    return out.getvalue()\n",
    ),
    "legacy": (
        "app/serialize.py",
        "def order_dict(order):\n    total = sum(i['price'] * i['qty'] for i in order['items'])\n"
        "    return {'id': order['id'], 'total': total, 'legacy_total': total,"
        " 'status': order['status']}\n",
        "def order_dict(order):\n    total = sum(i['price'] * i['qty'] for i in order['items'])\n"
        "    return {'id': order['id'], 'total': total, 'status': order['status']}\n",
    ),
    "wording": (
        "app/importer.py",
        "def parse_rows(lines):\n    rows = []\n    for n, line in enumerate(lines, start=1):\n"
        "        name, _, email = line.partition(',')\n        if not email.strip():\n"
        "            raise ValueError(f'Row {n}: missing email')\n"
        "        rows.append({'name': name.strip(), 'email': email.strip()})\n    return rows\n",
        "def parse_rows(lines):\n    rows = []\n    for n, line in enumerate(lines, start=1):\n"
        "        name, _, email = line.partition(',')\n        if not email.strip():\n"
        "            raise ValueError(f'Row {n} ({name!r}): the email column is empty')\n"
        "        rows.append({'name': name.strip(), 'email': email.strip()})\n    return rows\n",
    ),
    "fields": (
        "app/logline.py",
        "from datetime import datetime\n\n\ndef format_line(level, message, now=None,"
        " request_id=None):\n    now = now or datetime.now()\n"
        "    msg = f'[{request_id}] {message}' if request_id else message\n"
        "    return f\"{now:%Y-%m-%d %H:%M:%S} | {level.upper()} | {msg}\"\n",
        "from datetime import datetime\n\n\ndef format_line(level, message, now=None,"
        " request_id=None):\n    now = now or datetime.now()\n"
        "    return f\"{now:%Y-%m-%d %H:%M:%S} | {level.upper()} | {request_id or '-'} |"
        " {message}\"\n",
    ),
    "strings": (
        "app/users.py",
        "USERS = [{'id': i} for i in range(1, 201)]\n\n\ndef list_users(offset=0, limit=20):\n"
        "    try:\n        offset, limit = int(offset), int(limit)\n"
        "    except (TypeError, ValueError):\n        raise ValueError('bad paging') from None\n"
        "    if offset < 0 or limit < 1:\n        raise ValueError('bad paging')\n"
        "    return USERS[offset:offset + min(limit, 100)]\n",
        "USERS = [{'id': i} for i in range(1, 201)]\n\n\ndef list_users(offset: int = 0,"
        " limit: int = 20):\n    if not isinstance(offset, int) or not isinstance(limit, int):\n"
        "        raise ValueError('offset and limit must be integers')\n"
        "    if offset < 0 or limit < 1:\n        raise ValueError('bad paging')\n"
        "    return USERS[offset:offset + min(limit, 100)]\n",
    ),
    "naive": (
        "app/events.py",
        "from datetime import datetime, timezone\n\n\ndef make_event(kind, payload):\n"
        "    now = datetime.now(timezone.utc).replace(tzinfo=None)\n"
        "    return {'kind': kind, 'payload': payload,"
        " 'created_at': now.isoformat(timespec='seconds')}\n",
        "from datetime import datetime, timezone\n\n\ndef make_event(kind, payload):\n"
        "    return {'kind': kind, 'payload': payload,"
        " 'created_at': datetime.now(timezone.utc).isoformat()}\n",
    ),
    "stdlib": (
        "app/dates.py",
        "from datetime import datetime\n\nFORMATS = ('%Y-%m-%d', '%d/%m/%Y', '%d %b %Y',"
        " '%B %d, %Y', '%Y-%m-%dT%H:%M:%S')\n\n\ndef parse_date(text):\n    for f in FORMATS:\n"
        "        try:\n            return datetime.strptime(text.strip(), f)\n"
        "        except ValueError:\n            pass\n    raise ValueError(text)\n",
        "from datetime import datetime\n\nfrom dateutil import parser\n\n\n"
        "def parse_date(text):\n    return parser.parse(text, dayfirst=True)\n",
    ),
    "py38": (
        "app/commands.py",
        "from typing import Callable, Dict, List\n\n"
        "COMMANDS: Dict[str, Callable[[List[str]], str]] = {\n"
        "    'add': lambda a: str(sum(int(x) for x in a)),\n"
        "    'upper': lambda a: ' '.join(a).upper(),\n"
        "    'lower': lambda a: ' '.join(a).lower(),\n"
        "}\n\n\ndef dispatch(command, args):\n    try:\n"
        "        return COMMANDS[command.strip().lower()](args)\n"
        "    except KeyError:\n        raise ValueError(command) from None\n",
        "from collections.abc import Callable\n\n"
        "COMMANDS: dict[str, Callable[[list[str]], str]] = {\n"
        "    'add': lambda a: str(sum(int(x) for x in a)),\n"
        "    'upper': lambda a: ' '.join(a).upper(),\n"
        "    'lower': lambda a: ' '.join(a).lower(),\n"
        "}\n\n\ndef dispatch(command, args):\n    try:\n"
        "        return COMMANDS[command.strip().lower()](args)\n"
        "    except KeyError:\n        raise ValueError(command) from None\n",
    ),
}

# Words of each fact that must not appear anywhere in its repository.
TELLS = {
    "columns": ("macro", "position", "finance", "order of the columns"),
    "legacy": ("mobile", "2.3", "still reads"),
    "wording": ("support", "grep", "wording"),
    "fields": ("shipper", "three fields", "exactly three"),
    "strings": ("partner", "string"),
    "naive": ("warehouse", "naive", "offset"),
    "stdlib": ("air-gapped", "standard library", "PyPI"),
    "py38": ("3.8", "compatible"),
}


def build(root: Path, scene: dict) -> Path:
    for rel, text in scene["files"].items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def passes(root: Path, code: str) -> bool:
    if not code:
        return True
    done = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, timeout=60)
    return done.returncode == 0


def test_every_scene_has_its_two_results_and_tells() -> None:
    assert set(scenes) == set(RESULTS) == set(TELLS)


@pytest.mark.parametrize("name", sorted(RESULTS))
def test_the_checks_tell_keeping_the_fact_from_breaking_it(name: str, tmp_path: Path) -> None:
    scene, (rel, good, bad) = scenes[name], RESULTS[name]
    for label, text, fact in (("good", good, True), ("bad", bad, False)):
        root = build(tmp_path / label, scene)
        (root / rel).write_text(text, encoding="utf-8")
        if name == "stdlib" and label == "bad":
            assert not passes(root, scene["fact"])  # dateutil need not be installed here
            continue
        assert passes(root, scene["task"]), (label, "task")
        assert passes(root, scene["fact"]) is fact, (label, "fact")


@pytest.mark.parametrize("name", sorted(RESULTS))
def test_the_repository_passes_its_tests_and_does_not_tell_the_fact(
    name: str, tmp_path: Path
) -> None:
    scene = scenes[name]
    root = build(tmp_path, scene)
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                          cwd=root, capture_output=True, text=True, timeout=120)  # fmt: skip
    assert done.returncode == 0, done.stdout[-500:]
    text = "\n".join(scene["files"].values()).lower()
    assert not [w for w in TELLS[name] if w.lower() in text]
    assert all(w.lower() in scene["first"].lower() for w in TELLS[name][:1])
    assert not [w for w in TELLS[name] if w.lower() in scene["second"].lower()]


def test_the_stream_reader_takes_events_whose_message_is_text(tmp_path: Path) -> None:
    # Haiku, 2026-10-02: a permission_denied event carries `message` as a string
    carry = bench_module(ROOT / "benchmarks" / "memory_carry", "carry")
    path = tmp_path / "s.jsonl"
    rows = ['{"type":"system","subtype":"permission_denied","message":"Compound command"}',
            '{"type":"result","total_cost_usd":0.1,"num_turns":3,"result":"ok"}']
    path.write_text("\n".join(rows), encoding="utf-8")
    seen = carry.read_stream(path)
    assert seen["cost"] == 0.1 and seen["turns"] == 3 and seen["tools"] == 0
