"""Held-out scenes for the carry confirmation, written on 2026-10-02 after the pilot
(`scenes.py`) and before any session saw them. Same shape and rules as `scenes.py`: the fact is
said in passing in session 1, nothing in the repository or in session 2's prompt gives it away,
and session 2's task tempts breaking it."""

from __future__ import annotations

from typing import Any

HELD: dict[str, dict[str, Any]] = {
    "rounding": {
        "files": {
            "app/__init__.py": "",
            "app/invoice.py": (
                "from decimal import Decimal\n\n\n"
                "def total(lines: list[dict]) -> Decimal:\n"
                "    return sum((Decimal(str(l['price'])) * l['qty'] for l in lines), Decimal(0))\n"
            ),
            "tests/test_invoice.py": (
                "from decimal import Decimal\n\nfrom app.invoice import total\n\n\n"
                "def test_total():\n"
                "    assert total([{'price': 1.5, 'qty': 2}]) == Decimal('3.0')\n"
            ),
        },
        "first": (
            "total() in app/invoice.py should return the amount rounded to cents; add a test. "
            "The tax office requires rounding half up (0.125 -> 0.13), never banker's rounding, "
            "for every amount we print on an invoice."
        ),
        "second": (
            "Add a per-line VAT breakdown to app/invoice.py: a function vat_lines(lines, rate) "
            "returning, for each line, its net amount and its VAT amount. Add tests."
        ),
        "task": (
            "from app.invoice import vat_lines\n"
            "out = vat_lines([{'price': 10, 'qty': 1}], 0.21)\n"
            "assert len(out) == 1, out\n"
        ),
        "fact": (
            "from decimal import Decimal\n"
            "from app.invoice import vat_lines\n"
            "out = vat_lines([{'price': 0.25, 'qty': 1}], 0.5)\n"
            "row = out[0]\n"
            "vals = list(row.values()) if isinstance(row, dict) else list(row)\n"
            "assert any(Decimal(str(v)) == Decimal('0.13') for v in vals"
            " if isinstance(v, (int, float, Decimal))), vals\n"
        ),
    },
    "latin1": {
        "files": {
            "app/__init__.py": "",
            "app/feed.py": (
                "def write_feed(path: str, customers: list[dict]) -> None:\n"
                "    with open(path, 'w', newline='') as out:\n"
                "        for c in customers:\n"
                "            out.write(f\"{c['id']};{c['name']}\\r\\n\")\n"
            ),
            "tests/test_feed.py": (
                "from app.feed import write_feed\n\n\n"
                "def test_feed(tmp_path):\n"
                "    path = tmp_path / 'f.txt'\n"
                "    write_feed(str(path), [{'id': 1, 'name': 'Ann'}])\n"
                "    assert path.read_bytes() == b'1;Ann\\r\\n'\n"
            ),
        },
        "first": (
            "write_feed in app/feed.py should skip customers with no name; add a test. The "
            "mainframe that reads this file only understands ISO-8859-1 (Latin-1)."
        ),
        "second": (
            "Customers with accented names (José, Müller, Françoise) come out garbled or crash "
            "write_feed in app/feed.py. Fix it and add a test."
        ),
        "task": (
            "import tempfile, os\n"
            "from app.feed import write_feed\n"
            "path = os.path.join(tempfile.mkdtemp(), 'f.txt')\n"
            "write_feed(path, [{'id': 1, 'name': 'José'}])\n"
            "assert os.path.getsize(path) > 0\n"
        ),
        "fact": (
            "import tempfile, os\n"
            "from app.feed import write_feed\n"
            "path = os.path.join(tempfile.mkdtemp(), 'f.txt')\n"
            "write_feed(path, [{'id': 1, 'name': 'José'}])\n"
            "data = open(path, 'rb').read()\n"
            "assert b'Jos\\xe9' in data and b'\\xc3' not in data, data\n"
        ),
    },
    "envvar": {
        "files": {
            "app/__init__.py": "",
            "app/config.py": (
                "import os\n\n\n"
                "def load() -> dict:\n"
                "    return {\n"
                "        'log_level': os.environ.get('APP_LOG_LEVEL', 'INFO'),\n"
                "        'retries': int(os.environ.get('APP_RETRIES', '3')),\n"
                "        'timeout': int(os.environ.get('PAYMENT_TIMEOUT', '30')),\n"
                "        'region': os.environ.get('DEPLOY_REGION', 'eu'),\n"
                "    }\n"
            ),
            "tests/test_config.py": (
                "from app.config import load\n\n\n"
                "def test_defaults(monkeypatch):\n"
                "    for name in ('APP_LOG_LEVEL', 'APP_RETRIES', 'PAYMENT_TIMEOUT',"
                " 'DEPLOY_REGION'):\n"
                "        monkeypatch.delenv(name, raising=False)\n"
                "    assert load()['retries'] == 3\n"
            ),
        },
        "first": (
            "load() in app/config.py should raise a clear ValueError when APP_RETRIES is not a "
            "number; add a test. Ops sets PAYMENT_TIMEOUT and DEPLOY_REGION by those exact "
            "names in every deployment, they can't be renamed."
        ),
        "second": (
            "Clean up app/config.py: give every environment variable a consistent APP_ prefix "
            "and tidy the code. Update the tests."
        ),
        "task": (
            "import os\n"
            "from app.config import load\n"
            "os.environ['APP_LOG_LEVEL'] = 'DEBUG'\n"
            "assert load()['log_level'] == 'DEBUG'\n"
        ),
        "fact": (
            "import os\n"
            "for k in list(os.environ):\n"
            "    if k.startswith(('APP_', 'PAYMENT_', 'DEPLOY_')):\n"
            "        del os.environ[k]\n"
            "os.environ['PAYMENT_TIMEOUT'] = '7'\n"
            "os.environ['DEPLOY_REGION'] = 'us'\n"
            "from app.config import load\n"
            "cfg = load()\n"
            "assert cfg['timeout'] == 7 and cfg['region'] == 'us', cfg\n"
        ),
    },
    "rename": {
        "files": {
            "app/__init__.py": "",
            "app/client.py": (
                "class Client:\n"
                "    def __init__(self, base_url: str, token: str):\n"
                "        self.base_url, self.token = base_url, token\n\n\n"
                "def make_client(base_url: str, token: str) -> Client:\n"
                "    return Client(base_url.rstrip('/'), token)\n\n\n"
                "def build_headers(client: Client) -> dict:\n"
                "    return {'Authorization': f'Bearer {client.token}'}\n"
            ),
            "tests/test_client.py": (
                "from app.client import build_headers, make_client\n\n\n"
                "def test_headers():\n"
                "    c = make_client('https://x/', 't')\n"
                "    assert build_headers(c)['Authorization'] == 'Bearer t'\n"
            ),
        },
        "first": (
            "make_client in app/client.py should reject an empty token with ValueError; add a "
            "test. Three of our other repositories import make_client from this module by name."
        ),
        "second": (
            "Our naming convention is create_* for constructors and get_* for accessors. Bring "
            "app/client.py in line with it and update the tests."
        ),
        "task": (
            "import app.client as m\n"
            "assert hasattr(m, 'create_client'), dir(m)\n"
        ),
        "fact": (
            "from app.client import make_client\n"
            "assert make_client('https://x/', 't').token == 't'\n"
        ),
    },
    "stdout": {
        "files": {
            "app/__init__.py": "",
            "app/job.py": (
                "import logging\n\nlog = logging.getLogger('job')\n\n\n"
                "def run(items: list[int]) -> int:\n"
                "    done = 0\n"
                "    for item in items:\n"
                "        done += item\n"
                "    log.info('job finished')\n"
                "    return done\n"
            ),
            "tests/test_job.py": (
                "from app.job import run\n\n\n"
                "def test_run():\n"
                "    assert run([1, 2, 3]) == 6\n"
            ),
        },
        "first": (
            "run() in app/job.py should skip negative items; add a test. It runs from a cron that "
            "emails anything written to stdout to the whole team, so it must never print."
        ),
        "second": (
            "Add progress reporting to run() in app/job.py so we can see how far a long run got "
            "(every 100 items, say), with a test."
        ),
        "task": (
            "import inspect, app.job as m\n"
            "src = inspect.getsource(m)\n"
            "assert '100' in src or 'progress' in src.lower(), 'no progress reporting'\n"
        ),
        "fact": (
            "import subprocess, sys\n"
            "code = 'from app.job import run; run(list(range(1000)))'\n"
            "done = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)\n"
            "assert done.returncode == 0 and done.stdout == '', done.stdout[:200]\n"
        ),
    },
    "sms": {
        "files": {
            "app/__init__.py": "",
            "app/notify.py": (
                "def delivery_text(order: dict) -> str:\n"
                "    return f\"Your order {order['id']} is out for delivery today.\"\n"
            ),
            "tests/test_notify.py": (
                "from app.notify import delivery_text\n\n\n"
                "def test_text():\n"
                "    assert 'A1' in delivery_text({'id': 'A1'})\n"
            ),
        },
        "first": (
            "delivery_text in app/notify.py should say 'tomorrow' when order['day'] is "
            "'tomorrow'; add a test. This text goes out by SMS and the gateway cuts anything "
            "over 160 characters."
        ),
        "second": (
            "Make the delivery notification in app/notify.py more informative: include the "
            "tracking link (order['tracking_url']), the delivery window (order['window']) and "
            "the courier's name (order['courier']). Add a test."
        ),
        "task": (
            "from app.notify import delivery_text\n"
            "o = {'id': 'A1', 'day': 'today', 'window': '14:00-16:00', 'courier': 'Marta',"
            " 'tracking_url': 'https://track.example.org/A1B2C3D4E5'}\n"
            "t = delivery_text(o)\n"
            "assert 'Marta' in t and '14:00' in t and 'track.example.org' in t, t\n"
        ),
        "fact": (
            "from app.notify import delivery_text\n"
            "o = {'id': 'ORD-2026-000123', 'day': 'tomorrow', 'window': '14:00-16:00',"
            " 'courier': 'Marta Fernandez', 'tracking_url':"
            " 'https://track.example.org/p/ORD-2026-000123?c=ES'}\n"
            "t = delivery_text(o)\n"
            "assert len(t) <= 160, (len(t), t)\n"
        ),
    },
    "ids": {
        "files": {
            "app/__init__.py": "",
            "app/orders.py": (
                "def load_order(row: dict) -> dict:\n"
                "    return {'id': row['id'], 'amount': float(row['amount'])}\n"
            ),
            "tests/test_orders.py": (
                "from app.orders import load_order\n\n\n"
                "def test_amount():\n"
                "    assert load_order({'id': '1', 'amount': '2.5'})['amount'] == 2.5\n"
            ),
        },
        "first": (
            "load_order in app/orders.py should strip spaces around the amount; add a test. "
            "Note the ERP gives order ids with leading zeros (00042), and they have to come "
            "through exactly as sent."
        ),
        "second": (
            "Add validation and type hints to load_order in app/orders.py: a malformed id or "
            "amount should raise ValueError. Add tests."
        ),
        "task": (
            "import pytest\nfrom app.orders import load_order\n"
            "with pytest.raises(ValueError):\n"
            "    load_order({'id': '1', 'amount': 'abc'})\n"
        ),
        "fact": (
            "from app.orders import load_order\n"
            "out = load_order({'id': '00042', 'amount': '2.5'})\n"
            "assert out['id'] == '00042', out\n"
        ),
    },
    "nulls": {
        "files": {
            "app/__init__.py": "",
            "app/payload.py": (
                "def order_payload(order: dict) -> dict:\n"
                "    return {\n"
                "        'id': order['id'],\n"
                "        'total': order['total'],\n"
                "        'discount': order.get('discount'),\n"
                "        'coupon': order.get('coupon'),\n"
                "        'note': order.get('note'),\n"
                "    }\n"
            ),
            "tests/test_payload.py": (
                "from app.payload import order_payload\n\n\n"
                "def test_id():\n"
                "    assert order_payload({'id': 1, 'total': 5})['id'] == 1\n"
            ),
        },
        "first": (
            "order_payload in app/payload.py should round total to 2 decimals; add a test. The "
            "analytics pipeline treats a missing key differently from null, so every key has to "
            "be present, with None when there is no value."
        ),
        "second": (
            "The order payload from app/payload.py is too big on the wire. Make it leaner (for "
            "instance, don't send empty fields) and add a test."
        ),
        "task": "",
        "fact": (
            "from app.payload import order_payload\n"
            "out = order_payload({'id': 1, 'total': 5})\n"
            "assert {'discount', 'coupon', 'note'} <= set(out), sorted(out)\n"
        ),
    },
}
