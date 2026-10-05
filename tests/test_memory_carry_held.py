"""The carry confirmation's held-out scenes (`benchmarks/memory_carry/scenes_held.py`), checked
like the pilot's (`test_memory_carry.py`) before any session sees them."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from .helpers import bench_module

ROOT = Path(__file__).resolve().parents[1]
held = bench_module(ROOT / "benchmarks" / "memory_carry", "scenes_held").HELD

RESULTS: dict[str, tuple[str, str, str]] = {
    "rounding": (
        "app/invoice.py",
        "from decimal import Decimal, ROUND_HALF_UP\n\nCENT = Decimal('0.01')\n\n\n"
        "def total(lines):\n    return sum((Decimal(str(l['price'])) * l['qty'] for l in lines),"
        " Decimal(0)).quantize(CENT, ROUND_HALF_UP)\n\n\n"
        "def vat_lines(lines, rate):\n    out = []\n    for l in lines:\n"
        "        net = (Decimal(str(l['price'])) * l['qty']).quantize(CENT, ROUND_HALF_UP)\n"
        "        vat = (net * Decimal(str(rate))).quantize(CENT, ROUND_HALF_UP)\n"
        "        out.append({'net': net, 'vat': vat})\n    return out\n",
        "from decimal import Decimal\n\n\ndef total(lines):\n"
        "    return sum((Decimal(str(l['price'])) * l['qty'] for l in lines), Decimal(0))\n\n\n"
        "def vat_lines(lines, rate):\n"
        "    return [{'net': round(l['price'] * l['qty'], 2),"
        " 'vat': round(l['price'] * l['qty'] * rate, 2)} for l in lines]\n",
    ),
    "latin1": (
        "app/feed.py",
        "def write_feed(path, customers):\n"
        "    with open(path, 'w', newline='', encoding='latin-1') as out:\n"
        "        for c in customers:\n            out.write(f\"{c['id']};{c['name']}\\r\\n\")\n",
        "def write_feed(path, customers):\n"
        "    with open(path, 'w', newline='', encoding='utf-8') as out:\n"
        "        for c in customers:\n            out.write(f\"{c['id']};{c['name']}\\r\\n\")\n",
    ),
    "envvar": (
        "app/config.py",
        "import os\n\n\ndef _env(name, old=None, default=None):\n"
        "    return os.environ.get(name) or (os.environ.get(old) if old else None) or default\n\n\n"
        "def load():\n    return {'log_level': _env('APP_LOG_LEVEL', default='INFO'),\n"
        "            'retries': int(_env('APP_RETRIES', default='3')),\n"
        "            'timeout': int(_env('APP_PAYMENT_TIMEOUT', 'PAYMENT_TIMEOUT', '30')),\n"
        "            'region': _env('APP_DEPLOY_REGION', 'DEPLOY_REGION', 'eu')}\n",
        "import os\n\n\ndef load():\n"
        "    return {'log_level': os.environ.get('APP_LOG_LEVEL', 'INFO'),\n"
        "            'retries': int(os.environ.get('APP_RETRIES', '3')),\n"
        "            'timeout': int(os.environ.get('APP_PAYMENT_TIMEOUT', '30')),\n"
        "            'region': os.environ.get('APP_DEPLOY_REGION', 'eu')}\n",
    ),
    "rename": (
        "app/client.py",
        "class Client:\n    def __init__(self, base_url, token):\n"
        "        self.base_url, self.token = base_url, token\n\n\n"
        "def create_client(base_url, token):\n    return Client(base_url.rstrip('/'), token)\n\n\n"
        "make_client = create_client\n",
        "class Client:\n    def __init__(self, base_url, token):\n"
        "        self.base_url, self.token = base_url, token\n\n\n"
        "def create_client(base_url, token):\n    return Client(base_url.rstrip('/'), token)\n",
    ),
    "stdout": (
        "app/job.py",
        "import logging\n\nlog = logging.getLogger('job')\n\n\ndef run(items):\n    done = 0\n"
        "    for n, item in enumerate(items, 1):\n        done += item\n"
        "        if n % 100 == 0:\n            log.info('progress %d', n)\n    return done\n",
        "import logging\n\nlog = logging.getLogger('job')\n\n\ndef run(items):\n    done = 0\n"
        "    for n, item in enumerate(items, 1):\n        done += item\n"
        "        if n % 100 == 0:\n            print(f'progress {n}/{len(items)}')\n"
        "    return done\n",
    ),
    "sms": (
        "app/notify.py",
        "def delivery_text(o):\n"
        "    return (f\"Order {o['id']} arrives {o.get('day', 'today')} {o['window']} with \"\n"
        "            f\"{o['courier']}. Track: {o['tracking_url']}\")\n",
        "def delivery_text(o):\n"
        "    return (f\"Hi! Your order {o['id']} is out for delivery {o.get('day', 'today')} \"\n"
        "            f\"between {o['window']}. Your courier today is {o['courier']}. You can \"\n"
        "            f\"follow your package here: {o['tracking_url']}\")\n",
    ),
    "ids": (
        "app/orders.py",
        "def load_order(row):\n    oid = str(row['id']).strip()\n    if not oid.isdigit():\n"
        "        raise ValueError(oid)\n    try:\n        amount = float(row['amount'])\n"
        "    except ValueError:\n        raise ValueError(row['amount']) from None\n"
        "    return {'id': oid, 'amount': amount}\n",
        "def load_order(row):\n    try:\n        oid = int(row['id'])\n"
        "        amount = float(row['amount'])\n    except ValueError as e:\n"
        "        raise ValueError(str(e)) from None\n"
        "    return {'id': str(oid), 'amount': amount}\n",
    ),
    "nulls": (
        "app/payload.py",
        "KEYS = ('discount', 'coupon', 'note')\n\n\ndef order_payload(order):\n"
        "    return {'id': order['id'], 'total': round(order['total'], 2),"
        " **{k: order.get(k) for k in KEYS}}\n",
        "def order_payload(order):\n"
        "    out = {'id': order['id'], 'total': round(order['total'], 2), 'discount':"
        " order.get('discount'), 'coupon': order.get('coupon'), 'note': order.get('note')}\n"
        "    return {k: v for k, v in out.items() if v is not None}\n",
    ),
}

TELLS = {
    "rounding": ("tax office", "half up", "banker"),
    "latin1": ("mainframe", "8859", "latin"),
    "envvar": ("ops sets", "deployment", "can't be renamed"),
    "rename": ("other repositories", "import make_client"),
    "stdout": ("cron", "email", "never print"),
    "sms": ("sms", "gateway", "160"),
    "ids": ("erp", "leading zeros", "00042"),
    "nulls": ("analytics", "missing key", "every key"),
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


def test_every_held_scene_has_its_results_and_tells() -> None:
    assert set(held) == set(RESULTS) == set(TELLS)


@pytest.mark.parametrize("name", sorted(RESULTS))
def test_the_checks_tell_keeping_the_fact_from_breaking_it(name: str, tmp_path: Path) -> None:
    scene, (rel, good, bad) = held[name], RESULTS[name]
    for label, text, fact in (("good", good, True), ("bad", bad, False)):
        root = build(tmp_path / label, scene)
        (root / rel).write_text(text, encoding="utf-8")
        assert passes(root, scene["task"]), (label, "task")
        assert passes(root, scene["fact"]) is fact, (label, "fact")


@pytest.mark.parametrize("name", sorted(RESULTS))
def test_the_repository_passes_its_tests_and_does_not_tell_the_fact(
    name: str, tmp_path: Path
) -> None:
    scene = held[name]
    root = build(tmp_path, scene)
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                          cwd=root, capture_output=True, text=True, timeout=120)  # fmt: skip
    assert done.returncode == 0, done.stdout[-500:]
    text = "\n".join(scene["files"].values()).lower()
    assert not [w for w in TELLS[name] if w.lower() in text]
    assert TELLS[name][0].lower() in scene["first"].lower()
    assert not [w for w in TELLS[name] if w.lower() in scene["second"].lower()]
