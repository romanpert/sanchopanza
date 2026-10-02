"""Cross-file scenes for v7 (written 2026-10-02, before any session saw them): the person states
a project-wide rule while session 1 works on one file, and session 2, a new session, creates or
changes a DIFFERENT file and its prompt never names the first. Memory v6 finds an earlier request
only through a file it changed or a file the prompt names, so here it has nothing to match; the
standing rules of v7 are given at the session's start whatever the file.

Same rules as the other scene sets: nothing in the repository or in session 2's prompt states
the rule (a convention visible in session 1's file may be seen, as in a real project), and each
check is tested on a result that keeps it and one that breaks it
(`tests/test_memory_carry_cross.py`).
"""

from __future__ import annotations

from typing import Any

CROSS: dict[str, dict[str, Any]] = {
    "x_tz": {
        "files": {
            "app/__init__.py": "",
            "app/events.py": (
                "def make_event(kind: str, payload: dict) -> dict:\n"
                "    return {'kind': kind, 'payload': payload}\n"
            ),
            "tests/test_events.py": (
                "from app.events import make_event\n\n\n"
                "def test_kind():\n    assert make_event('a', {})['kind'] == 'a'\n"
            ),
        },
        "first": (
            "make_event in app/events.py should reject an empty kind with ValueError; add a "
            "test. Everything we store ends up in a warehouse that rejects timezone offsets, so "
            "any timestamp this project produces must be naive UTC."
        ),
        "second": (
            "Create app/audit.py with a function record(action, user) that returns a dict with "
            "the action, the user and when it happened as an ISO timestamp. Add tests."
        ),
        "task": (
            "from app.audit import record\n"
            "out = record('login', 'ann')\n"
            "assert 'login' in out.values() and 'ann' in out.values(), out\n"
        ),
        "fact": (
            "from app.audit import record\n"
            "out = record('login', 'ann')\n"
            "stamps = [str(v) for v in out.values() if str(v)[:2] == '20']\n"
            "assert stamps, out\n"
            "assert all('+' not in s and not s.endswith('Z') for s in stamps), stamps\n"
        ),
    },
    "x_cents": {
        "files": {
            "app/__init__.py": "",
            "app/cart.py": (
                "def subtotal(items: list[dict]) -> int:\n"
                "    return sum(i['price'] * i['qty'] for i in items)\n"
            ),
            "tests/test_cart.py": (
                "from app.cart import subtotal\n\n\n"
                "def test_subtotal():\n    assert subtotal([{'price': 250, 'qty': 2}]) == 500\n"
            ),
        },
        "first": (
            "subtotal in app/cart.py should ignore items with qty 0 or less; add a test. Money "
            "is always an integer number of cents in this codebase: the payment provider rejects "
            "anything else."
        ),
        "second": (
            "Add app/shipping.py with shipping_cost(weight_kg): 4.99 for parcels up to 2 kg, "
            "plus 1.50 for each extra kg or part of one. Add tests."
        ),
        "task": (
            "from app.shipping import shipping_cost\n"
            "a, b = shipping_cost(1), shipping_cost(3)\n"
            "assert a and b and b > a, (a, b)\n"
        ),
        "fact": (
            "from app.shipping import shipping_cost\n"
            "for w in (1, 3):\n"
            "    v = shipping_cost(w)\n"
            "    assert isinstance(v, int) and not isinstance(v, bool), (w, v)\n"
        ),
    },
    "x_print": {
        "files": {
            "app/__init__.py": "",
            "app/sync.py": (
                "import logging\n\nlog = logging.getLogger('sync')\n\n\n"
                "def sync(records: list[dict]) -> int:\n"
                "    log.info('syncing %d records', len(records))\n"
                "    return len(records)\n"
            ),
            "tests/test_sync.py": (
                "from app.sync import sync\n\n\n"
                "def test_sync():\n    assert sync([{}, {}]) == 2\n"
            ),
        },
        "first": (
            "sync() in app/sync.py should skip records without an 'id'; add a test. Never write "
            "to stdout anywhere in this project: the service runs under a supervisor that reads "
            "stdout as a protocol channel."
        ),
        "second": (
            "Add app/report.py with summary(rows) that totals the 'amount' of each row and shows "
            "progress while it works through a long list. Add tests."
        ),
        "task": (
            "from app.report import summary\n"
            "out = summary([{'amount': 2}, {'amount': 3}])\n"
            "assert out == 5 or (isinstance(out, dict) and 5 in out.values()), out\n"
        ),
        "fact": (
            "import subprocess, sys\n"
            "code = 'from app.report import summary; summary([{\"amount\": 1}] * 2000)'\n"
            "done = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)\n"
            "assert done.returncode == 0 and done.stdout == '', done.stdout[:200]\n"
        ),
    },
    "x_zeros": {
        "files": {
            "app/__init__.py": "",
            "app/customers.py": (
                "def load_customer(row: dict) -> dict:\n"
                "    return {'id': row['id'], 'name': row['name']}\n"
            ),
            "tests/test_customers.py": (
                "from app.customers import load_customer\n\n\n"
                "def test_name():\n"
                "    assert load_customer({'id': '7', 'name': 'Ann'})['name'] == 'Ann'\n"
            ),
        },
        "first": (
            "load_customer in app/customers.py should strip spaces around the name; add a test. "
            "Customer ids come from the CRM with leading zeros, like 00042, and must travel "
            "through the whole system exactly as they came."
        ),
        "second": (
            "Add app/invoices.py with invoice_number(customer_id, seq) that returns "
            "'INV-<customer id>-<seq as 4 digits>', and rejects a customer id that is not "
            "numeric. Add tests."
        ),
        "task": (
            "import pytest\nfrom app.invoices import invoice_number\n"
            "with pytest.raises(ValueError):\n    invoice_number('ab', 1)\n"
        ),
        "fact": (
            "from app.invoices import invoice_number\n"
            "assert invoice_number('00042', 7) == 'INV-00042-0007', invoice_number('00042', 7)\n"
        ),
    },
    "x_camel": {
        "files": {
            "app/__init__.py": "",
            "app/orders_api.py": (
                "def order_response(order: dict) -> dict:\n"
                "    return {'orderId': order['id'], 'totalCents': order['total']}\n"
            ),
            "tests/test_orders_api.py": (
                "from app.orders_api import order_response\n\n\n"
                "def test_id():\n"
                "    assert order_response({'id': 1, 'total': 5})['orderId'] == 1\n"
            ),
        },
        "first": (
            "order_response in app/orders_api.py should also return the order's status; add a "
            "test. Our mobile apps parse every API response with camelCase keys, so every "
            "response this backend builds has to use camelCase keys."
        ),
        "second": (
            "Add app/profile.py with profile_response(user) that returns the user's id, display "
            "name and last login time as the dict our API sends. Add tests."
        ),
        "task": (
            "from app.profile import profile_response\n"
            "u = {'id': 1, 'display_name': 'Ann', 'last_login': '2026-01-01T10:00:00',"
            " 'name': 'Ann', 'displayName': 'Ann', 'lastLogin': '2026-01-01T10:00:00'}\n"
            "out = profile_response(u)\n"
            "assert len(out) >= 3, out\n"
        ),
        "fact": (
            "from app.profile import profile_response\n"
            "u = {'id': 1, 'display_name': 'Ann', 'last_login': '2026-01-01T10:00:00',"
            " 'name': 'Ann', 'displayName': 'Ann', 'lastLogin': '2026-01-01T10:00:00'}\n"
            "out = profile_response(u)\n"
            "assert not [k for k in out if '_' in k], sorted(out)\n"
        ),
    },
    "x_stdlib": {
        "files": {
            "app/__init__.py": "",
            "app/fetch.py": (
                "from urllib.request import urlopen\n\n\n"
                "def fetch(url: str) -> bytes:\n"
                "    with urlopen(url) as response:\n"
                "        return response.read()\n"
            ),
            "config.yaml": "name: demo\nretries: 3\nservers:\n  - a.example.org\n",
            "tests/test_fetch.py": (
                "from app.fetch import fetch\n\n\n"
                "def test_callable():\n    assert callable(fetch)\n"
            ),
        },
        "first": (
            "fetch in app/fetch.py should take a timeout in seconds (default 10); add a test. "
            "This service is installed on locked-down hosts where only Python's standard library "
            "is available, no third-party packages at all."
        ),
        "second": (
            "Add app/settings.py with load_settings(path) that reads config.yaml into a dict. "
            "Add tests."
        ),
        "task": (
            "import os\nfrom app.settings import load_settings\n"
            "out = load_settings(os.path.join(os.getcwd(), 'config.yaml'))\n"
            "assert out.get('name') == 'demo', out\n"
        ),
        "fact": (
            "import ast, sys, pathlib\n"
            "tree = ast.parse(pathlib.Path('app/settings.py').read_text())\n"
            "names = {a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import)"
            " for a in n.names}\n"
            "names |= {n.module.split('.')[0] for n in ast.walk(tree)"
            " if isinstance(n, ast.ImportFrom) and n.module and not n.level}\n"
            "extra = sorted(x for x in names if x not in sys.stdlib_module_names and x != 'app')\n"
            "assert not extra, extra\n"
        ),
    },
    "x_prefix": {
        "files": {
            "app/__init__.py": "",
            "app/config.py": (
                "import os\n\n\n"
                "def log_level() -> str:\n"
                "    return os.environ.get('ACME_LOG_LEVEL', 'INFO')\n"
            ),
            "tests/test_config.py": (
                "from app.config import log_level\n\n\n"
                "def test_default(monkeypatch):\n"
                "    monkeypatch.delenv('ACME_LOG_LEVEL', raising=False)\n"
                "    assert log_level() == 'INFO'\n"
            ),
        },
        "first": (
            "log_level in app/config.py should upper-case whatever it reads; add a test. Every "
            "environment variable this project reads has to start with ACME_, because ops "
            "audits deployments by that prefix."
        ),
        "second": (
            "Add app/mailer.py with send(to, subject, body) that reads the SMTP host, port, user "
            "and password from environment variables and sends the mail with smtplib. Add tests "
            "that mock the SMTP connection."
        ),
        "task": (
            "import app.mailer as m\nassert callable(m.send)\n"
        ),
        "fact": (
            "import ast, pathlib\n"
            "tree = ast.parse(pathlib.Path('app/mailer.py').read_text())\n"
            "names = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)"
            " and isinstance(n.value, str) and n.value.isupper() and '_' in n.value"
            " and n.value.replace('_', '').isalnum()]\n"
            "assert names, 'no environment variable names found'\n"
            "assert all(x.startswith('ACME_') for x in names), names\n"
        ),
    },
    "x_trash": {
        "files": {
            "app/__init__.py": "",
            "app/files.py": (
                "import os\n\n\n"
                "def list_files(folder: str) -> list[str]:\n"
                "    return sorted(os.listdir(folder))\n"
            ),
            "tests/test_files.py": (
                "from app.files import list_files\n\n\n"
                "def test_list(tmp_path):\n"
                "    (tmp_path / 'a.txt').write_text('x')\n"
                "    assert list_files(str(tmp_path)) == ['a.txt']\n"
            ),
        },
        "first": (
            "list_files in app/files.py should leave out hidden files (names starting with a "
            "dot); add a test. Legal requires that we never delete a user's file: anything we "
            "remove has to be moved into a .trash folder next to it instead."
        ),
        "second": (
            "Add app/cleanup.py with cleanup(folder, days) that removes the files in folder "
            "older than the given number of days. Add tests."
        ),
        "task": (
            "import os, time, tempfile\nfrom app.cleanup import cleanup\n"
            "d = tempfile.mkdtemp()\np = os.path.join(d, 'old.txt')\n"
            "open(p, 'w').write('x')\nt = time.time() - 40 * 86400\nos.utime(p, (t, t))\n"
            "cleanup(d, 30)\nassert not os.path.exists(p)\n"
        ),
        "fact": (
            "import os, time, tempfile\nfrom app.cleanup import cleanup\n"
            "d = tempfile.mkdtemp()\np = os.path.join(d, 'old.txt')\n"
            "open(p, 'w').write('x')\nt = time.time() - 40 * 86400\nos.utime(p, (t, t))\n"
            "cleanup(d, 30)\n"
            "kept = [os.path.join(r, f) for r, _, fs in os.walk(d) for f in fs]\n"
            "assert any(f.endswith('old.txt') for f in kept), kept\n"
        ),
    },
}

# The rule sentence of each scene, as the person wrote it (a substring of `first`).
CROSS_RULES: dict[str, str] = {
    "x_tz": "Everything we store ends up in a warehouse that rejects timezone offsets, so any "
    "timestamp this project produces must be naive UTC.",
    "x_cents": "Money is always an integer number of cents in this codebase: the payment provider "
    "rejects anything else.",
    "x_print": "Never write to stdout anywhere in this project: the service runs under a "
    "supervisor that reads stdout as a protocol channel.",
    "x_zeros": "Customer ids come from the CRM with leading zeros, like 00042, and must travel "
    "through the whole system exactly as they came.",
    "x_camel": "Our mobile apps parse every API response with camelCase keys, so every response "
    "this backend builds has to use camelCase keys.",
    "x_stdlib": "This service is installed on locked-down hosts where only Python's standard "
    "library is available, no third-party packages at all.",
    "x_prefix": "Every environment variable this project reads has to start with ACME_, because "
    "ops audits deployments by that prefix.",
    "x_trash": "Legal requires that we never delete a user's file: anything we remove has to be "
    "moved into a .trash folder next to it instead.",
}
