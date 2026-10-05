"""The stale scenes of F1 (`benchmarks/memory_carry/scenes_stale.py`), checked before any session
sees them: each scene's checks tell three session-2 results apart (one that applies the newer
rule A', one that applies the older A, one that does the default), the repository passes its own
tests and does not have the task done, nothing in the repository or session 2's prompt states A
or A', and session 1' does not restate A."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from .helpers import bench_module

ROOT = Path(__file__).resolve().parents[1]
mod = bench_module(ROOT / "benchmarks" / "memory_carry", "scenes_stale")
STALE, STALE_RULES = mod.STALE, mod.STALE_RULES

Files = dict[str, str]

EVENTS = (
    "%s\n\n\ndef make_event(kind, payload):\n"
    "    return {'kind': kind, 'payload': payload, 'created_at': %s}\n"
)
AUTH = (
    "import json\nfrom datetime import datetime\n\nfrom app.passwords import check_password\n\n\n"
    "def login(user, given, stored):\n    return check_password(given, stored)\n\n\n"
    "def log_failed_login(user, ip, path):\n    line = %s\n"
    "    with open(path, 'a', encoding='utf-8') as f:\n        f.write(line + '\\n')\n"
)
ORDERS = (
    "def order_summary(order):\n    total = sum(i['price'] * i['qty'] for i in order['items'])\n"
    "    return {'id': order['id'], 'items': len(order['items']), 'total': %s}\n"
)
STOCK = (
    "import csv\n\n\ndef low_stock(items, threshold=5):\n"
    "    return [i for i in items if i['qty'] < threshold]\n\n\n"
    "def export_stock(items, path):\n    with open(path, 'w', newline='', encoding='utf-8') as f:\n"
    "        writer = csv.writer(f, delimiter=%r)\n        writer.writerow(['sku', 'qty'])\n"
    "        writer.writerows([i['sku'], i['qty']] for i in items)\n"
)
PAYLOAD = (
    "def product_payload(p):\n"
    "    return {'sku': p['sku'], 'name': p['name'], 'in_stock': %s}\n"
)
SIGNUP = (
    "def check_age(age):\n    if int(age) < 18:\n        raise ValueError(%r)\n"
    "    return int(age)\n"
)
PROJECTS = (
    "PROJECTS = [\n"
    "    {'id': 1, 'name': 'Mango', 'owner': 'ann', 'created': '2026-03-01'},\n"
    "    {'id': 2, 'name': 'Apple', 'owner': 'ann', 'created': '2026-01-10'},\n"
    "    {'id': 3, 'name': 'Kiwi', 'owner': 'bob', 'created': '2026-02-02'},\n"
    "    {'id': 4, 'name': 'Zebra', 'owner': 'ann', 'created': '2026-05-20'},\n"
    "]\n\n\n"
    "def get_project(project_id):\n"
    "    return next((p for p in PROJECTS if p['id'] == project_id), None)\n\n\n"
    "def list_projects(owner):\n    mine = [p for p in PROJECTS if p['owner'] == owner]\n"
    "    return %s\n"
)
EMAILS = (
    "def subject(order):\n    return f\"Your order {order['id']}\"\n\n\n"
    "def order_line(order):\n    d = order['placed']\n"
    "    return f\"Order {order['id']}, placed on {%s}\"\n"
)

# Per scene: session-2 results that apply A' (`fact`), A (`stale`) and the default.
RESULTS: dict[str, dict[str, Files]] = {
    "u_time": {
        "fact": {"app/events.py": EVENTS % ("import time", "int(time.time() * 1000)")},
        "stale": {"app/events.py": EVENTS % ("import time", "int(time.time())")},
        "default": {"app/events.py": EVENTS % ("from datetime import datetime, timezone",
                                               "datetime.now(timezone.utc).isoformat()")},
    },
    "u_sep": {
        "fact": {"app/auth.py": AUTH % "json.dumps({'event': 'login_failed', 'user': user, "
                 "'ip': ip})"},
        "stale": {"app/auth.py": AUTH % "f'event=login_failed user={user} ip={ip}'"},
        "default": {"app/auth.py": AUTH % "f'{datetime.now():%Y-%m-%d %H:%M:%S} failed login "
                    "for {user} from {ip}'"},
    },
    "u_money": {
        "fact": {"app/orders_api.py": ORDERS % "f'{total:.2f}'.replace('.', ',')"},
        "stale": {"app/orders_api.py": ORDERS % "f'{total:.2f}'"},
        "default": {"app/orders_api.py": ORDERS % "round(total, 2)"},
    },
    "u_delim": {
        "fact": {"app/stock.py": STOCK % "\t"},
        "stale": {"app/stock.py": STOCK % ";"},
        "default": {"app/stock.py": STOCK % ","},
    },
    "u_bool": {
        "fact": {"app/partner_api.py": PAYLOAD % "int(p['stock'] > 0)"},
        "stale": {"app/partner_api.py": PAYLOAD % "'Y' if p['stock'] > 0 else 'N'"},
        "default": {"app/partner_api.py": PAYLOAD % "p['stock'] > 0"},
    },
    "u_lang": {
        "fact": {"app/signup.py": SIGNUP % "Você precisa ter pelo menos 18 anos."},
        "stale": {"app/signup.py": SIGNUP % "Vous devez avoir au moins 18 ans."},
        "default": {"app/signup.py": SIGNUP % "You must be at least 18 years old."},
    },
    "u_sort": {
        "fact": {"app/projects.py": PROJECTS % "sorted(mine, key=lambda p: p['created'], "
                 "reverse=True)"},
        "stale": {"app/projects.py": PROJECTS % "sorted(mine, key=lambda p: p['name'])"},
        "default": {"app/projects.py": PROJECTS % "mine"},
    },
    "u_date": {
        "fact": {"app/emails.py": EMAILS % "d.day} {d:%b %Y"},
        "stale": {"app/emails.py": EMAILS % "d:%d/%m/%Y"},
        "default": {"app/emails.py": EMAILS % "d.isoformat()"},
    },
}

# Words of A (`stale`), of A' (`fact`) and of both (`both`). The repository and session 2 hold
# none; session 1' holds none of A's; session 1 none of A''s. Matched as whole words.
TELLS: dict[str, dict[str, tuple[str, ...]]] = {
    "u_time": {"stale": ("seconds",), "fact": ("milliseconds",), "both": ("epoch", "analytics")},
    "u_sep": {"stale": ("key=value", "event=login"), "fact": ("json",),
              "both": ("log search", "log platform")},
    "u_money": {"stale": ("'12.50'", "two decimals"), "fact": ("'12,50'", "decimal comma"),
                "both": ("frontend", "javascript", "locale")},
    "u_delim": {"stale": ("semicolons",), "fact": ("tab-separated", "tabs"),
                "both": ("excel", "warehouse")},
    "u_bool": {"stale": ("'y'", "'n'"), "fact": ("1 and 0", "integers"),
               "both": ("true or false",)},
    "u_lang": {"stale": ("french", "quebec"), "fact": ("portuguese", "brazil"),
               "both": ("market",)},
    "u_sort": {"stale": ("a to z", "by name"), "fact": ("newest", "creation date"), "both": ()},
    "u_date": {"stale": ("day/month/year", "02/01/2026"), "fact": ("2 jan 2026",), "both": ()},
}


def found(words: tuple[str, ...], text: str) -> list[str]:
    low = text.lower()
    return [w for w in words if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low)]


def build(root: Path, scene: dict, extra: Files | None = None) -> Path:
    for rel, text in {**scene["files"], **(extra or {})}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def passes(root: Path, code: str) -> bool:
    if not code:
        return True
    done = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, timeout=120)
    return done.returncode == 0


def test_every_stale_scene_has_three_sessions_both_rules_verbatim_and_tells() -> None:
    assert len(STALE) == 8 and all(k.startswith("u_") for k in STALE)
    assert set(STALE) == set(RESULTS) == set(TELLS) == set(STALE_RULES)
    for name, scene in STALE.items():
        assert {"files", "first", "between", "second", "task", "fact", "stale"} <= set(scene)
        assert STALE_RULES[name]["stale"] in scene["first"], name
        assert STALE_RULES[name]["fact"] in scene["between"], name
        assert "changed" in scene["between"] or "change of plans" in scene["between"].lower()


@pytest.mark.parametrize("name", sorted(RESULTS))
def test_the_checks_tell_the_newer_rule_the_older_and_the_default_apart(
    name: str, tmp_path: Path
) -> None:
    scene = STALE[name]
    expected = {"fact": (True, False), "stale": (False, True), "default": (False, False)}
    for label, files in RESULTS[name].items():
        root = build(tmp_path / label, scene, files)
        assert passes(root, scene["task"]), (label, "task")
        got = (passes(root, scene["fact"]), passes(root, scene["stale"]))
        assert got == expected[label], (label, got)


@pytest.mark.parametrize("name", sorted(RESULTS))
def test_the_repository_passes_its_tests_has_the_task_undone_and_states_neither_rule(
    name: str, tmp_path: Path
) -> None:
    scene = STALE[name]
    root = build(tmp_path, scene)
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                          cwd=root, capture_output=True, text=True, timeout=120)  # fmt: skip
    assert done.returncode == 0, done.stdout[-500:]
    assert not passes(root, scene["task"])
    assert not passes(root, scene["fact"]) and not passes(root, scene["stale"])
    tells = TELLS[name]
    every = tells["stale"] + tells["fact"] + tells["both"]
    assert not found(every, "\n".join(scene["files"].values()))
    assert not found(every, scene["second"])
    assert not found(tells["stale"], scene["between"]), "session 1' restates the old rule"
    assert not found(tells["fact"], scene["first"]), "session 1 states the new rule"
    assert found(tells["stale"], scene["first"]) and found(tells["fact"], scene["between"])


@pytest.mark.parametrize("name", sorted(RESULTS))
def test_session_2_works_in_another_file_than_sessions_1_and_1prime(name: str) -> None:
    scene = STALE[name]
    named = set(re.findall(r"app/\w+\.py", scene["first"] + scene["between"]))
    assert len(named) == 2 and not [rel for rel in named if rel in scene["second"]]
