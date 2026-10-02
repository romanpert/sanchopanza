"""The cross-file scenes (`benchmarks/memory_carry/scenes_cross.py`), checked before any session
sees them, like the other scene sets."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from .helpers import bench_module

ROOT = Path(__file__).resolve().parents[1]
mod = bench_module(ROOT / "benchmarks" / "memory_carry", "scenes_cross")
CROSS, CROSS_RULES = mod.CROSS, mod.CROSS_RULES

RESULTS: dict[str, tuple[str, str, str]] = {
    "x_tz": (
        "app/audit.py",
        "from datetime import datetime, timezone\n\n\ndef record(action, user):\n"
        "    now = datetime.now(timezone.utc).replace(tzinfo=None)\n"
        "    return {'action': action, 'user': user, 'at': now.isoformat(timespec='seconds')}\n",
        "from datetime import datetime, timezone\n\n\ndef record(action, user):\n"
        "    return {'action': action, 'user': user,"
        " 'at': datetime.now(timezone.utc).isoformat()}\n",
    ),
    "x_cents": (
        "app/shipping.py",
        "import math\n\n\ndef shipping_cost(weight_kg):\n"
        "    extra = max(0, math.ceil(weight_kg - 2))\n    return 499 + 150 * extra\n",
        "import math\n\n\ndef shipping_cost(weight_kg):\n"
        "    extra = max(0, math.ceil(weight_kg - 2))\n"
        "    return round(4.99 + 1.50 * extra, 2)\n",
    ),
    "x_print": (
        "app/report.py",
        "import logging\n\nlog = logging.getLogger('report')\n\n\ndef summary(rows):\n"
        "    total = 0\n    for n, r in enumerate(rows, 1):\n        total += r['amount']\n"
        "        if n % 500 == 0:\n            log.info('%d rows', n)\n    return total\n",
        "def summary(rows):\n    total = 0\n    for n, r in enumerate(rows, 1):\n"
        "        total += r['amount']\n        if n % 500 == 0:\n"
        "            print(f'{n}/{len(rows)} rows')\n    return total\n",
    ),
    "x_zeros": (
        "app/invoices.py",
        "def invoice_number(customer_id, seq):\n    if not str(customer_id).isdigit():\n"
        "        raise ValueError(customer_id)\n    return f'INV-{customer_id}-{seq:04d}'\n",
        "def invoice_number(customer_id, seq):\n    try:\n        cid = int(customer_id)\n"
        "    except ValueError:\n        raise ValueError(customer_id) from None\n"
        "    return f'INV-{cid}-{seq:04d}'\n",
    ),
    "x_camel": (
        "app/profile.py",
        "def profile_response(user):\n    return {'id': user['id'], 'displayName':"
        " user['display_name'], 'lastLogin': user['last_login']}\n",
        "def profile_response(user):\n    return {'id': user['id'], 'display_name':"
        " user['display_name'], 'last_login': user['last_login']}\n",
    ),
    "x_stdlib": (
        "app/settings.py",
        "def load_settings(path):\n    out = {}\n    for line in open(path):\n"
        "        if ':' in line and not line.startswith(' '):\n"
        "            k, _, v = line.partition(':')\n            out[k.strip()] = v.strip()\n"
        "    return out\n",
        "import yaml\n\n\ndef load_settings(path):\n    with open(path) as f:\n"
        "        return yaml.safe_load(f)\n",
    ),
    "x_prefix": (
        "app/mailer.py",
        "import os\nimport smtplib\n\n\ndef send(to, subject, body):\n"
        "    host = os.environ['ACME_SMTP_HOST']\n"
        "    port = int(os.environ.get('ACME_SMTP_PORT', '25'))\n"
        "    with smtplib.SMTP(host, port) as s:\n        s.sendmail('a@example.org', to, body)\n",
        "import os\nimport smtplib\n\n\ndef send(to, subject, body):\n"
        "    host = os.environ['SMTP_HOST']\n    port = int(os.environ.get('SMTP_PORT', '25'))\n"
        "    with smtplib.SMTP(host, port) as s:\n        s.sendmail('a@example.org', to, body)\n",
    ),
    "x_trash": (
        "app/cleanup.py",
        "import os, shutil, time\n\n\ndef cleanup(folder, days):\n"
        "    trash = os.path.join(folder, '.trash')\n    cut = time.time() - days * 86400\n"
        "    for name in os.listdir(folder):\n        p = os.path.join(folder, name)\n"
        "        if os.path.isfile(p) and os.path.getmtime(p) < cut:\n"
        "            os.makedirs(trash, exist_ok=True)\n"
        "            shutil.move(p, os.path.join(trash, name))\n",
        "import os, time\n\n\ndef cleanup(folder, days):\n    cut = time.time() - days * 86400\n"
        "    for name in os.listdir(folder):\n        p = os.path.join(folder, name)\n"
        "        if os.path.isfile(p) and os.path.getmtime(p) < cut:\n            os.remove(p)\n",
    ),
}

TELLS = {
    "x_tz": ("warehouse", "offset", "naive"),
    "x_cents": ("integer number of cents", "payment provider"),
    "x_print": ("supervisor", "stdout", "protocol"),
    "x_zeros": ("crm", "leading zeros", "00042"),
    "x_camel": ("mobile apps", "camelcase"),
    "x_stdlib": ("locked-down", "standard library", "third-party"),
    "x_prefix": ("acme_", "audits"),
    "x_trash": (".trash", "legal", "never delete"),
}
# x_prefix: `ACME_` is visible in session 1's file (a convention a real repository shows);
# only the stated rule and its reason must not be.
VISIBLE = {"x_prefix": ("acme_",)}


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


def test_every_cross_scene_has_results_tells_and_its_rule_verbatim() -> None:
    assert set(CROSS) == set(RESULTS) == set(TELLS) == set(CROSS_RULES)
    assert all(CROSS_RULES[k] in CROSS[k]["first"] for k in CROSS)


@pytest.mark.parametrize("name", sorted(RESULTS))
def test_the_checks_tell_keeping_the_rule_from_breaking_it(name: str, tmp_path: Path) -> None:
    scene, (rel, good, bad) = CROSS[name], RESULTS[name]
    for label, text, fact in (("good", good, True), ("bad", bad, False)):
        root = build(tmp_path / label, scene)
        (root / rel).write_text(text, encoding="utf-8")
        if name == "x_stdlib" and label == "bad":
            assert not passes(root, scene["fact"])  # PyYAML need not be installed here
            continue
        assert passes(root, scene["task"]), (label, "task")
        assert passes(root, scene["fact"]) is fact, (label, "fact")


@pytest.mark.parametrize("name", sorted(RESULTS))
def test_the_repository_passes_and_tells_nothing_and_session_2_names_no_earlier_file(
    name: str, tmp_path: Path
) -> None:
    scene = CROSS[name]
    root = build(tmp_path, scene)
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                          cwd=root, capture_output=True, text=True, timeout=120)  # fmt: skip
    assert done.returncode == 0, done.stdout[-500:]
    text = "\n".join(scene["files"].values()).lower()
    hidden = [w for w in TELLS[name] if w not in VISIBLE.get(name, ())]
    assert not [w for w in hidden if w.lower() in text]
    assert not [w for w in TELLS[name] if w.lower() in scene["second"].lower()]
    earlier = [rel for rel in scene["files"] if rel.startswith("app/") and rel != "app/__init__.py"]
    assert not [rel for rel in earlier if rel in scene["second"]]
