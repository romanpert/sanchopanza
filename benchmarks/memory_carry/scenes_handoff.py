"""Handoff scenes for F2 (written 2026-10-15, before any session saw them): one feature in two
steps over two sessions. Session 1 (`first`) gives the plan (step 1 today, step 2 next session,
with step 2's function named), asks for step 1 only, and says in passing a constraint C (`rule`)
and a decision D about step 2 (`decision`). Session 2 does step 2: in arms N0 and S its prompt is
the scene's `continue` line, which names neither step 2, C nor D; in arm H it is the handoff text
session 1 wrote when asked for one.

Checks (Python run in the repository, exit 0 when true; each tested on hand-written results in
`tests/test_memory_carry_handoff.py`):
- `task`: step 2 is done (its function works on a plain case);
- `fact`: C holds in step 2's code (each fact check calls step 2, so it fails when step 2 is
  missing);
- `decision`: D was followed;
- `intact`: step 1's work is there and still works.

`kind` says which family a scene's C and D are: C a working preference of the project (as F1
family i) or a constraint of the outside world; D plain, or a reversal of what was planned
earlier in the same prompt (as F1 family ii). `keys` are the fixed phrases searched for in H's
`handoff.txt` (reported, never deciding). `near` names the decoy rules (`carry.DECOY_POOL`) that
touch the scene's C, D or task; arm S's store never gets them.

Nothing in the start repository (no TODO, no plan file) or in the `continue` line gives away step
2, C or D (tested).
"""

from __future__ import annotations

from typing import Any

ONLY_STEP_1 = "Only do step 1 now, with tests; don't start step 2."

# ---- h_batch -----------------------------------------------------------------------------------
BATCH_RUN = (
    "from app.labels import label_for\n"
    "def order(i, paid=True):\n"
    "    return {'id': i, 'name': f'N{i}', 'address': f'A{i}', 'weight_g': 1250, 'paid': paid}\n"
    "class Fake:\n"
    "    def __init__(self):\n"
    "        self.single, self.bulk = [], []\n"
    "    def create_label(self, label):\n"
    "        self.single.append(label)\n"
    "        return f'T{len(self.single)}'\n"
    "    def create_labels(self, labels):\n"
    "        self.bulk.append(list(labels))\n"
    "        return [f'B{len(self.bulk)}-{i}' for i in range(len(self.bulk[-1]))]\n"
    "ORDERS = [order(i) for i in range(120)] + [order(900 + i, False) for i in range(3)]\n"
    "from app.labels import ship_all\n"
    "c = Fake()\n"
    "out = ship_all(ORDERS, c)\n"
)

# ---- h_loud ------------------------------------------------------------------------------------
LOUD_RUN = (
    "from app.fx import total_eur\n"
    "import app.fx as fx\n"
    "RATES = {'USD': 1.08, 'GBP': 0.85, 'JPY': 160.0}\n"
)

# ---- h_spanish ---------------------------------------------------------------------------------
SPANISH_RUN = (
    "import datetime, re\n"
    "from app.booking import booking_errors\n"
    "TODAY = datetime.date(2026, 3, 10)\n"
    "OK = {'name': 'Ana', 'date': '2026-03-12', 'guests': '4'}\n"
    "BAD = {'name': ' ', 'date': '2026-03-01', 'guests': '12'}\n"
    "def msgs(form):\n"
    "    out = booking_errors(form, TODAY)\n"
    "    if isinstance(out, str):\n"
    "        return [out] if out else []\n"
    "    if isinstance(out, dict):\n"
    "        out = list(out.values())\n"
    "    return [str(m) for m in (out or [])]\n"
)

# ---- h_flag ------------------------------------------------------------------------------------
FLAG_RUN = (
    "import os, pathlib, re, subprocess, sys\n"
    "names = sorted({m for p in pathlib.Path('app').rglob('*.py')"
    " for m in re.findall(r'[A-Z0-9_]*FEATURE_[A-Z0-9_]+', p.read_text(encoding='utf-8'))})\n"
    "def prices(value):\n"
    "    env = {k: v for k, v in os.environ.items() if 'FEATURE_' not in k}\n"
    "    if value is not None:\n"
    "        env.update({n: value for n in names})\n"
    "    code = ('from app.pricing import final_price; '\n"
    "            'print(float(final_price(100, 100)), float(final_price(50, 1000)))')\n"
    "    done = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True,"
    " text=True, timeout=60)\n"
    "    assert done.returncode == 0, done.stderr[-300:]\n"
    "    return tuple(round(float(x), 2) for x in done.stdout.split()[-2:])\n"
    "def on():\n"
    "    for value in ('1', 'true', 'on', 'yes', 'enabled'):\n"
    "        got = prices(value)\n"
    "        if got[0] == 95.0:\n"
    "            return got\n"
    "    return None\n"
)

# ---- h_nomutate --------------------------------------------------------------------------------
CART_RUN = (
    "import copy\n"
    "from app.cart import apply_coupon, cart_total\n"
    "LINES = [{'sku': 'b1', 'price': 20.0, 'qty': 1, 'category': 'books'},\n"
    "         {'sku': 't1', 'price': 30.0, 'qty': 1, 'category': 'toys'}]\n"
    "before = copy.deepcopy(LINES)\n"
    "out = apply_coupon(LINES, 'READ10')\n"
)

# ---- h_dryrun ----------------------------------------------------------------------------------
PURGE_RUN = (
    "import datetime, json, os, shutil, subprocess, sys, tempfile\n"
    "copy = os.path.join(tempfile.mkdtemp(), 'repo')\n"
    "shutil.copytree(os.getcwd(), copy, ignore=shutil.ignore_patterns('.git'))\n"
    "today = datetime.date.today()\n"
    "accounts = [{'id': 'a1', 'email': 'old@example.org',"
    " 'last_login': str(today - datetime.timedelta(days=800))},\n"
    "            {'id': 'a2', 'email': 'new@example.org',"
    " 'last_login': str(today - datetime.timedelta(days=10))}]\n"
    "data = os.path.join(copy, 'data')\n"
    "for name in os.listdir(data):\n"
    "    if os.path.isfile(os.path.join(data, name)):\n"
    "        os.remove(os.path.join(data, name))\n"
    "with open(os.path.join(data, 'accounts.json'), 'w') as f:\n"
    "    json.dump(accounts, f)\n"
    "def run(*args):\n"
    "    return subprocess.run([sys.executable, '-m', 'scripts.purge_accounts', *args], cwd=copy,"
    " capture_output=True, text=True, timeout=60)\n"
    "def ids(name):\n"
    "    path = os.path.join(data, name)\n"
    "    if not os.path.exists(path):\n"
    "        return set()\n"
    "    with open(path) as f:\n"
    "        text = f.read().strip()\n"
    "    loaded = json.loads(text) if text else []\n"
    "    rows = loaded if isinstance(loaded, list) else [x for v in loaded.values()"
    " if isinstance(v, list) for x in v]\n"
    "    return {r.get('id') for r in rows if isinstance(r, dict)}\n"
)

# ---- h_semicolon -------------------------------------------------------------------------------
EXPORT_RUN = (
    "import os, tempfile\n"
    "from app.report import export_totals\n"
    "TOTALS = {'2026-03': 99.5, '2026-01': 1234.5, '2026-02': 7.25}\n"
    "folder = tempfile.mkdtemp()\n"
    "path = os.path.join(folder, 'totals.csv')\n"
    "export_totals(TOTALS, path)\n"
    "files = [os.path.join(r, n) for r, _, ns in os.walk(folder) for n in sorted(ns)]\n"
    "def read(p):\n"
    "    with open(p, encoding='utf-8', errors='replace') as f:\n"
    "        return f.read()\n"
    "text = ''.join(read(p) for p in files)\n"
    "lines = [x for x in read(path).splitlines() if x.strip()] if os.path.isfile(path) else []\n"
)

# ---- h_retry -----------------------------------------------------------------------------------
RETRY_RUN = (
    "import json, time\n"
    "time.sleep = lambda *a, **k: None\n"
    "from app.webhooks import deliver, sign\n"
    "EVENT = {'id': 'evt_42', 'kind': 'order.paid', 'data': {'order': 7}}\n"
    "calls = []\n"
    "def post_with(statuses):\n"
    "    def post(*args, **kwargs):\n"
    "        names = ('url', 'body', 'headers')\n"
    "        got = {**dict(zip(names, args)), **kwargs}\n"
    "        body = got.get('body', got.get('data', got.get('content')))\n"
    "        calls.append((got.get('url'), body, dict(got.get('headers') or {})))\n"
    "        return statuses[min(len(calls) - 1, len(statuses) - 1)]\n"
    "    return post\n"
    "def attempt(statuses):\n"
    "    calls.clear()\n"
    "    try:\n"
    "        deliver(EVENT, 'https://hooks.example/x', 's3cret', post_with(statuses))\n"
    "        return 'ok'\n"
    "    except Exception:\n"
    "        return 'raised'\n"
    "def low(headers):\n"
    "    return {str(k).lower(): v for k, v in headers.items()}\n"
)

# ---- h_merge -----------------------------------------------------------------------------------
MERGE_RUN = (
    "from app.subscribers import merge\n"
    "OLD = [{'name': 'Ana Ruiz', 'email': 'ana@example.org'},"
    " {'name': 'Bo', 'email': 'bo@example.org'}]\n"
)

# ---- h_weeks -----------------------------------------------------------------------------------
WEEKS_RUN = (
    "from app.timesheet import weekly_hours\n"
    "E = [{'day': '2026-03-01', 'hours': 2.0}, {'day': '2026-03-02', 'hours': 3.1},\n"
    "     {'day': '2026-03-07', 'hours': 1.0}, {'day': '2026-03-08', 'hours': 4.0}]\n"
    "w = {str(k)[:10]: float(v) for k, v in weekly_hours([dict(e) for e in E]).items()}\n"
)

# ---- h_judge -----------------------------------------------------------------------------------
JUDGE_RUN = (
    "import importlib, sys\n"
    "import app.judge\n"
    "calls = []\n"
    "def use(fn):\n"
    "    app.judge.judge = fn\n"
    "    sys.modules.pop('app.tickets', None)\n"
    "    return importlib.import_module('app.tickets').is_urgent\n"
    "def const(p):\n"
    "    def fake(*a, **k):\n"
    "        calls.append(a or k)\n"
    "        return p\n"
    "    return fake\n"
    "CALM = {'subject': 'Invoice address', 'body': 'Could you change the address on next month"
    " invoice?', 'plan': 'basic'}\n"
    "DOWN = {'subject': 'Site down', 'body': 'Our checkout is down, nobody can pay. Data may be"
    " lost!', 'plan': 'basic'}\n"
    "ENT = {**CALM, 'plan': 'enterprise'}\n"
)

# ---- h_pages -----------------------------------------------------------------------------------
PAGES_RUN = (
    "from app.orders import fetch_all\n"
    "ALL = [{'id': i, 'total_cents': 100 + i, 'created': '2026-03-01'} for i in range(250)]\n"
    "class Fake:\n"
    "    def __init__(self):\n"
    "        self.calls = []\n"
    "    def get(self, path, params=None, **kw):\n"
    "        p = {**(params or {}), **kw}\n"
    "        self.calls.append(p)\n"
    "        limit = int(p.get('limit') or 50)\n"
    "        after = p.get('after')\n"
    "        start = int(after) if after not in (None, '') else int(p.get('offset') or 0)\n"
    "        page = ALL[start:start + min(limit, 500)]\n"
    "        end = start + len(page)\n"
    "        return {'items': page, 'next': str(end) if end < len(ALL) else None}\n"
    "c = Fake()\n"
    "out = fetch_all(c)\n"
)


HANDOFF: dict[str, dict[str, Any]] = {
    "h_batch": {
        "files": {
            "app/__init__.py": "",
            "app/carrier.py": (
                "class Carrier:\n"
                '    """The parcel carrier\'s API client (configured in production)."""\n\n'
                "    def create_label(self, label: dict) -> str:\n"
                '        """One label; returns its tracking number."""\n'
                "        raise NotImplementedError\n\n"
                "    def create_labels(self, labels: list[dict]) -> list[str]:\n"
                '        """Several labels in one request; their tracking numbers, in order."""\n'
                "        raise NotImplementedError\n"
            ),
            "app/orders.py": (
                "def paid_orders(orders: list[dict]) -> list[dict]:\n"
                "    return [o for o in orders if o.get('paid')]\n"
            ),
            "tests/test_orders.py": (
                "from app.orders import paid_orders\n\n\n"
                "def test_paid_only():\n"
                "    assert paid_orders([{'paid': True}, {'paid': False}]) == [{'paid': True}]\n"
            ),
        },
        "first": (
            "We're adding shipping labels for our orders, in two steps. Step 1, today: in a new "
            "module app/labels.py, write label_for(order) that turns an order dict ({'id', "
            "'name', 'address', 'weight_g', 'paid'}) into the label the carrier expects: "
            "{'to': name, 'address': address, 'weight_kg': the weight in kilograms rounded to "
            "2 decimals}. Step 2, in the next session: ship_all(orders, carrier) in the same "
            "module, which creates the labels of every paid order through the carrier client in "
            "app/carrier.py and returns their tracking numbers. " + ONLY_STEP_1 + " By the way, "
            "the carrier's API rejects any request that carries more than 50 labels. For step 2 "
            "we'll use the bulk call, create_labels, not create_label once per order."
        ),
        "rule": "the carrier's API rejects any request that carries more than 50 labels.",
        "decision": "For step 2 we'll use the bulk call, create_labels, not create_label once per "
        "order.",
        "continue": "Let's continue with the shipping labels.",
        "kind": {"C": "constraint", "D": "plain"},
        "keys": {"C": ["50"], "D": ["create_labels", "bulk"]},
        "near": ["ids", "x_zeros"],
        "task": BATCH_RUN
        + (
            "assert len(list(out)) == 120\n"
            "assert len(c.single) + sum(len(b) for b in c.bulk) == 120\n"
        ),
        "fact": BATCH_RUN
        + ("assert c.single or c.bulk\nassert all(len(b) <= 50 for b in c.bulk)\n"),
        "decision_check": BATCH_RUN + "assert c.bulk and not c.single\n",
        "intact": (
            "from app.labels import label_for\n"
            "got = label_for({'id': 1, 'name': 'N1', 'address': 'A1', 'weight_g': 1250,"
            " 'paid': True})\n"
            "assert got['to'] == 'N1' and got['address'] == 'A1'\n"
            "assert abs(float(got['weight_kg']) - 1.25) < 1e-9\n"
        ),
    },
    "h_loud": {
        "files": {
            "app/__init__.py": "",
            "app/money.py": (
                "def parse_amount(text: str) -> float:\n"
                "    return float(text.strip().replace(',', '.'))\n"
            ),
            "data/rates.csv": "currency,per_eur\nUSD,1.08\nGBP,0.85\nJPY,160.0\n",
            "tests/test_money.py": (
                "from app.money import parse_amount\n\n\n"
                "def test_comma():\n"
                "    assert parse_amount(' 1,5 ') == 1.5\n"
            ),
        },
        "first": (
            "Invoices can come in other currencies and we want their totals in euros, in two "
            "steps. Step 1, today: load_rates(path) in a new app/fx.py, reading data/rates.csv "
            "into a dict like {'USD': 1.08} (units of that currency per euro). Step 2, in the "
            "next session: to_eur(amount, currency, rates) and total_eur(lines, rates) in "
            "app/fx.py, for invoice lines like {'amount': 10.0, 'currency': 'USD'}. "
            + ONLY_STEP_1
            + " A general rule of this codebase, while you're at it: we never "
            "swallow errors or fall back to a default value; if something is missing or wrong, "
            "it raises. For step 2, convert each line, round it to cents, and add up the rounded "
            "lines; don't round only the total."
        ),
        "rule": "we never swallow errors or fall back to a default value; if something is "
        "missing or wrong, it raises.",
        "decision": "For step 2, convert each line, round it to cents, and add up the rounded "
        "lines; don't round only the total.",
        "continue": "Let's continue with the currency work.",
        "kind": {"C": "preference", "D": "plain"},
        "keys": {
            "C": ["raise", "fall back", "fallback", "swallow"],
            "D": ["each line", "per line", "rounded lines", "per-line"],
        },  # fmt: skip
        "near": ["x_cents", "rounding", "strings"],
        "task": LOUD_RUN
        + (
            "t = total_eur([{'amount': 10.8, 'currency': 'USD'},"
            " {'amount': 1600, 'currency': 'JPY'}], RATES)\n"
            "assert abs(float(t) - 20.0) < 0.011\n"
        ),
        "fact": LOUD_RUN
        + (
            "calls = [lambda: total_eur([{'amount': 5.0, 'currency': 'XYZ'}], RATES)]\n"
            "if hasattr(fx, 'to_eur'):\n"
            "    calls.append(lambda: fx.to_eur(5.0, 'XYZ', RATES))\n"
            "raised = 0\n"
            "for call in calls:\n"
            "    try:\n"
            "        call()\n"
            "    except Exception:\n"
            "        raised += 1\n"
            "assert raised == len(calls)\n"
        ),
        "decision_check": LOUD_RUN
        + (
            "t = total_eur([{'amount': 0.01404, 'currency': 'USD'} for _ in range(3)], RATES)\n"
            "assert abs(float(t) - 0.03) < 1e-9\n"
        ),
        "intact": (
            "from app.fx import load_rates\n"
            "got = load_rates('data/rates.csv')\n"
            "assert {k: round(float(v), 4) for k, v in got.items()} =="
            " {'USD': 1.08, 'GBP': 0.85, 'JPY': 160.0}\n"
        ),
    },
    "h_spanish": {
        "files": {
            "app/__init__.py": "",
            "app/booking.py": (
                "OPENING = {'tue-sun': '13:00-16:00, 20:00-23:30'}\n\n\n"
                "def opening_hours() -> dict:\n"
                "    return dict(OPENING)\n"
            ),
            "tests/test_booking.py": (
                "from app.booking import opening_hours\n\n\n"
                "def test_hours():\n"
                "    assert 'tue-sun' in opening_hours()\n"
            ),
        },
        "first": (
            "We're building the table booking form of the restaurant's site, in two steps. Step "
            "1, today: parse_booking(form) in app/booking.py, which takes the raw form dict of "
            "strings {'name', 'date' (YYYY-MM-DD), 'guests'} and returns {'name': stripped, "
            "'date': a datetime.date, 'guests': an int}. Step 2, in the next session: "
            "booking_errors(form, today) in the same file, returning the messages we show the "
            "customer when the form is wrong (an empty name, a date before today, guests outside "
            "1 to 8). " + ONLY_STEP_1 + " For context, everything our customers see is written "
            "in Spanish; code, comments and logs stay in English. And for step 2: return every "
            "problem at once as a list of messages, not just the first one."
        ),
        "rule": "everything our customers see is written in Spanish; code, comments and logs "
        "stay in English.",
        "decision": "for step 2: return every problem at once as a list of messages, not just "
        "the first one.",
        "continue": "Let's continue with the booking form.",
        "kind": {"C": "preference", "D": "plain"},
        "keys": {
            "C": ["spanish", "español"],
            "D": [
                "every problem",
                "all problems",
                "all the problems",
                "every error",
                "all errors",
                "all at once",
            ],
        },  # fmt: skip
        "near": ["wording", "sms"],
        "task": SPANISH_RUN
        + ("assert msgs(OK) == []\nassert msgs(BAD)\nassert msgs({**OK, 'guests': '12'})\n"),
        "fact": SPANISH_RUN
        + (
            "text = ' '.join(msgs(BAD) + msgs({**OK, 'guests': '0'})).lower()\n"
            "assert re.search(r'nombre|fecha|persona|comensal|invitad|obligatori|pasad|anterior"
            "|hu[eé]sped|v[aá]lid|vac[ií]o|entre', text), text\n"
            "assert not re.search(r'\\b(the|name|date|guests?|required|must|past|empty|between"
            ")\\b', text), text\n"
        ),
        "decision_check": SPANISH_RUN + "assert len(msgs(BAD)) >= 3\n",
        "intact": (
            "import datetime\n"
            "from app.booking import parse_booking\n"
            "got = parse_booking({'name': ' Ana ', 'date': '2026-03-12', 'guests': '4'})\n"
            "assert got['name'] == 'Ana' and got['guests'] == 4\n"
            "assert got['date'] == datetime.date(2026, 3, 12)\n"
        ),
    },
    "h_flag": {
        "files": {
            "app/__init__.py": "",
            "app/pricing.py": (
                "def subtotal(lines: list[dict]) -> float:\n"
                "    return round(sum(x['price'] * x['qty'] for x in lines), 2)\n"
            ),
            "tests/test_pricing.py": (
                "from app.pricing import subtotal\n\n\n"
                "def test_subtotal():\n"
                "    assert subtotal([{'price': 2.5, 'qty': 2}]) == 5.0\n"
            ),
        },
        "first": (
            "We're adding loyalty points to the shop, in two steps. Step 1, today: "
            "points_for(subtotal) in a new app/loyalty.py: one point per whole euro spent (49.99 "
            "gives 49). Step 2, in the next session: final_price(subtotal, points) in "
            "app/pricing.py, where every 100 points take 5 euros off. " + ONLY_STEP_1 + " How "
            "we work here: anything that changes what a customer pays ships behind a FEATURE_* "
            "environment variable, off by default, so we can turn it on shop by shop. For step "
            "2, cap the discount at 20 % of the subtotal."
        ),
        "rule": "anything that changes what a customer pays ships behind a FEATURE_* "
        "environment variable, off by default, so we can turn it on shop by shop.",
        "decision": "For step 2, cap the discount at 20 % of the subtotal.",
        "continue": "Let's continue with the loyalty points.",
        "kind": {"C": "preference", "D": "plain"},
        "keys": {"C": ["feature_", "flag"], "D": ["20", "cap"]},
        "near": ["x_prefix", "envvar", "x_cents", "rounding"],
        "task": FLAG_RUN + "assert on() is not None\n",
        "fact": FLAG_RUN + "assert names and prices(None) == (100.0, 50.0) and on() is not None\n",
        "decision_check": FLAG_RUN + "got = on()\nassert got is not None and got[1] == 40.0\n",
        "intact": (
            "from app.loyalty import points_for\n"
            "assert int(points_for(49.99)) == 49 and int(points_for(100)) == 100\n"
        ),
    },
    "h_nomutate": {
        "files": {
            "app/__init__.py": "",
            "app/cart.py": (
                "def line_total(line: dict) -> float:\n    return line['price'] * line['qty']\n"
            ),
            "tests/test_cart.py": (
                "from app.cart import line_total\n\n\n"
                "def test_line():\n"
                "    assert line_total({'price': 2.0, 'qty': 3}) == 6.0\n"
            ),
        },
        "first": (
            "Discount coupons for the cart, in two steps. Step 1, today: cart_total(lines) in "
            "app/cart.py, the sum of price x qty over the cart's lines (each line is {'sku', "
            "'price', 'qty', 'category'}), rounded to 2 decimals. Step 2, in the next session: "
            "apply_coupon(lines, code) in app/cart.py, returning the lines with the coupon "
            "applied to their prices, for the code 'READ10'. " + ONLY_STEP_1 + " One habit of "
            "this codebase to keep in mind: functions never modify the lists or dicts they are "
            "given; they build and return new ones. About the coupon: we first said READ10 "
            "would take 10 % off the whole cart; marketing changed that this morning, it's 10 % "
            "off the 'books' lines only."
        ),
        "rule": "functions never modify the lists or dicts they are given; they build and "
        "return new ones.",
        "decision": "we first said READ10 would take 10 % off the whole cart; marketing changed "
        "that this morning, it's 10 % off the 'books' lines only.",
        "continue": "Let's continue with the cart coupons.",
        "kind": {"C": "preference", "D": "reversal"},
        "keys": {
            "C": ["modify", "mutate", "new ones", "new list", "copies", "in place"],
            "D": ["books"],
        },  # fmt: skip
        "near": ["x_cents", "rounding"],
        "task": CART_RUN + "assert 0 < cart_total(out) < 50.0\n",
        "fact": CART_RUN + "assert LINES == before\n",
        "decision_check": CART_RUN + "assert abs(cart_total(out) - 48.0) < 0.011\n",
        "intact": (
            "from app.cart import cart_total\n"
            "assert cart_total([{'sku': 'a', 'price': 1.25, 'qty': 2, 'category': 'x'},"
            " {'sku': 'b', 'price': 3.0, 'qty': 1, 'category': 'y'}]) == 5.5\n"
        ),
    },
    "h_dryrun": {
        "files": {
            "app/__init__.py": "",
            "app/accounts.py": (
                "import json\n\n\n"
                "def load(path: str) -> list[dict]:\n"
                "    with open(path, encoding='utf-8') as f:\n"
                "        return json.load(f)\n"
            ),
            "scripts/__init__.py": "",
            "data/accounts.json": (
                '[{"id": "a1", "email": "ana@example.org", "last_login": "2023-05-01"},\n'
                ' {"id": "a2", "email": "bo@example.org", "last_login": "2026-09-30"}]\n'
            ),
            "tests/test_accounts.py": (
                "from app.accounts import load\n\n\n"
                "def test_load():\n"
                "    assert [a['id'] for a in load('data/accounts.json')] == ['a1', 'a2']\n"
            ),
        },
        "first": (
            "We need to clean up stale accounts, in two steps. Step 1, today: "
            "stale_accounts(accounts, today) in app/accounts.py: the accounts whose last_login "
            "(YYYY-MM-DD) is more than 365 days before today (a datetime.date). Step 2, in the "
            "next session: a script, scripts/purge_accounts.py, run as python -m "
            "scripts.purge_accounts, that takes the stale accounts out of data/accounts.json. "
            + ONLY_STEP_1
            + " A standing rule here: any script that changes data does nothing by "
            "default and only writes when it's given --apply; without it, it just reports what "
            "it would do. For step 2, move the stale accounts into data/archived.json (append to "
            "it) instead of deleting them outright."
        ),
        "rule": "any script that changes data does nothing by default and only writes when it's "
        "given --apply; without it, it just reports what it would do.",
        "decision": "For step 2, move the stale accounts into data/archived.json (append to it) "
        "instead of deleting them outright.",
        "continue": "Let's continue with the stale accounts.",
        "kind": {"C": "preference", "D": "plain"},
        "keys": {"C": ["--apply", "dry run", "dry-run"], "D": ["archived.json", "archive"]},
        "near": ["x_trash", "x_print", "stdout"],
        "task": PURGE_RUN
        + (
            "run()\n"
            "if 'a1' in ids('accounts.json'):\n"
            "    run('--apply')\n"
            "left = ids('accounts.json')\n"
            "assert 'a1' not in left and 'a2' in left\n"
        ),
        "fact": PURGE_RUN
        + (
            "done = run()\n"
            "assert done.returncode == 0, done.stderr[-300:]\n"
            "assert ids('accounts.json') == {'a1', 'a2'} and not ids('archived.json')\n"
            "run('--apply')\n"
            "assert 'a1' not in ids('accounts.json')\n"
        ),
        "decision_check": PURGE_RUN
        + (
            "run()\n"
            "run('--apply')\n"
            "kept = ids('archived.json')\n"
            "assert 'a1' in kept and 'a2' not in kept\n"
        ),
        "intact": (
            "import datetime\n"
            "from app.accounts import stale_accounts\n"
            "rows = [{'id': 'o', 'last_login': '2024-01-01'},"
            " {'id': 'n', 'last_login': '2026-01-01'}]\n"
            "got = stale_accounts(rows, datetime.date(2026, 3, 1))\n"
            "assert [r['id'] for r in got] == ['o']\n"
        ),
    },
    "h_semicolon": {
        "files": {
            "app/__init__.py": "",
            "app/sales.py": (
                "import csv\n\n\n"
                "def read_sales(path: str) -> list[dict]:\n"
                "    with open(path, newline='', encoding='utf-8') as f:\n"
                "        return [{'date': r['date'], 'amount': float(r['amount'])}\n"
                "                for r in csv.DictReader(f)]\n"
            ),
            "data/sales.csv": "date,amount\n2026-01-15,10.50\n2026-01-20,0.25\n2026-02-01,3\n",
            "tests/test_sales.py": (
                "from app.sales import read_sales\n\n\n"
                "def test_read():\n"
                "    assert read_sales('data/sales.csv')[0] == "
                "{'date': '2026-01-15', 'amount': 10.5}\n"
            ),
        },
        "first": (
            "Our accounting partner wants monthly sales totals, in two steps. Step 1, today: "
            "monthly_totals(rows) in a new app/report.py, taking the rows read_sales gives "
            "(app/sales.py) and returning {'YYYY-MM': total rounded to 2 decimals}. Step 2, in "
            "the next session: export_totals(totals, path) in app/report.py, which writes the "
            "CSV we send them. " + ONLY_STEP_1 + " Something to know about the partner: their "
            "importer only reads files separated by semicolons, with a decimal comma, like "
            "2026-01;1234,50. And a change to what we planned: we said step 2 would write one "
            "file per month; now they want a single file at path with every month, oldest first."
        ),
        "rule": "their importer only reads files separated by semicolons, with a decimal comma, "
        "like 2026-01;1234,50.",
        "decision": "we said step 2 would write one file per month; now they want a single file "
        "at path with every month, oldest first.",
        "continue": "Let's continue with the partner's sales report.",
        "kind": {"C": "constraint", "D": "reversal"},
        "keys": {
            "C": ["semicolon", "decimal comma"],
            "D": ["single file", "one file", "oldest first"],
        },  # fmt: skip
        "near": ["columns", "fields", "latin1", "rounding", "x_cents"],
        "task": EXPORT_RUN + "assert files and all(m in text for m in TOTALS)\n",
        "fact": EXPORT_RUN
        + (
            "data = [x for x in text.splitlines() if x[:4].isdigit()]\n"
            "assert data and all(';' in x for x in data)\n"
            "assert '1234,5' in text and '1234.5' not in text\n"
        ),
        "decision_check": EXPORT_RUN
        + (
            "assert os.path.isfile(path) and len(files) == 1\n"
            "months = [x[:7] for x in lines if x[:4].isdigit()]\n"
            "assert months == sorted(TOTALS)\n"
        ),
        "intact": (
            "from app.report import monthly_totals\n"
            "got = monthly_totals([{'date': '2026-01-15', 'amount': 10.5},"
            " {'date': '2026-01-20', 'amount': 0.25}, {'date': '2026-02-01', 'amount': 3.0}])\n"
            "assert {k: round(float(v), 2) for k, v in got.items()} =="
            " {'2026-01': 10.75, '2026-02': 3.0}\n"
        ),
    },
    "h_retry": {
        "files": {
            "app/__init__.py": "",
            "app/events.py": (
                "import uuid\n\n\n"
                "def make_event(kind: str, data: dict) -> dict:\n"
                "    return {'id': f'evt_{uuid.uuid4().hex[:12]}', 'kind': kind, 'data': data}\n"
            ),
            "tests/test_events.py": (
                "from app.events import make_event\n\n\n"
                "def test_event():\n"
                "    e = make_event('order.paid', {'order': 1})\n"
                "    assert e['id'].startswith('evt_') and e['kind'] == 'order.paid'\n"
            ),
        },
        "first": (
            "We're adding outgoing webhooks, in two steps. Step 1, today: sign(body, secret) in "
            "a new app/webhooks.py, returning the hex HMAC-SHA256 of the body bytes keyed with "
            "the secret (a str). Step 2, in the next session: deliver(event, url, secret, post) "
            "in the same file: it sends the event (see app/events.py) as JSON, with its "
            "signature in an X-Signature header, through post(url, body_bytes, headers), which "
            "returns the HTTP status. " + ONLY_STEP_1 + " One thing about the receivers: they "
            "drop duplicates by the X-Event-Id header, so every request we send must carry the "
            "event's id in X-Event-Id. For step 2, when a delivery fails (a status other than "
            "2xx), try again: three attempts in total, then raise."
        ),
        "rule": "they drop duplicates by the X-Event-Id header, so every request we send must "
        "carry the event's id in X-Event-Id.",
        "decision": "For step 2, when a delivery fails (a status other than 2xx), try again: "
        "three attempts in total, then raise.",
        "continue": "Let's continue with the webhooks.",
        "kind": {"C": "constraint", "D": "plain"},
        "keys": {
            "C": ["x-event-id"],
            "D": ["three attempts", "3 attempts", "three times", "3 times"],
        },  # fmt: skip
        "near": ["x_camel"],
        "task": RETRY_RUN
        + (
            "assert attempt([200]) == 'ok' and len(calls) == 1\n"
            "body = calls[0][1]\n"
            "raw = body if isinstance(body, bytes) else str(body).encode()\n"
            "assert json.loads(raw)['id'] == 'evt_42'\n"
            "assert str(low(calls[0][2]).get('x-signature', '')).endswith(sign(raw, 's3cret'))\n"
        ),
        "fact": RETRY_RUN
        + (
            "for statuses in ([200], [500]):\n"
            "    attempt(statuses)\n"
            "    assert calls and all(low(c[2]).get('x-event-id') == 'evt_42' for c in calls)\n"
        ),
        "decision_check": RETRY_RUN
        + (
            "assert attempt([500]) == 'raised' and len(calls) == 3\n"
            "assert attempt([500, 503, 200]) == 'ok' and len(calls) == 3\n"
        ),
        "intact": (
            "import hashlib, hmac\n"
            "from app.webhooks import sign\n"
            "assert sign(b'abc', 'k') == hmac.new(b'k', b'abc', hashlib.sha256).hexdigest()\n"
        ),
    },
    "h_merge": {
        "files": {
            "app/__init__.py": "",
            "app/newsletter.py": (
                "def greeting(name: str) -> str:\n"
                "    return f'Hi {name.split()[0]},' if name.strip() else 'Hi,'\n"
            ),
            "data/old_site.csv": "name,email\n Ana Ruiz ,ana@example.org\nBo, bo@example.org\n",
            "tests/test_newsletter.py": (
                "from app.newsletter import greeting\n\n\n"
                "def test_greeting():\n"
                "    assert greeting('Ana Ruiz') == 'Hi Ana,'\n"
            ),
        },
        "first": (
            "We're importing the newsletter subscribers of the old site, in two steps. Step 1, "
            "today: read_subscribers(path) in a new app/subscribers.py, reading a CSV with name "
            "and email columns (like data/old_site.csv) into a list of {'name', 'email'} dicts "
            "with the spaces stripped. Step 2, in the next session: merge(existing, new) in the "
            "same file, returning the combined list of subscribers without duplicates. "
            + ONLY_STEP_1
            + " Something about our CRM: it treats ana+news@example.org and "
            "ANA@example.org as the same person, so neither case nor anything after a + before "
            "the @ makes a different subscriber. For step 2, when someone is in both lists keep "
            "the existing record as it is, name included; don't take the new one."
        ),
        "rule": "it treats ana+news@example.org and ANA@example.org as the same person, so "
        "neither case nor anything after a + before the @ makes a different subscriber.",
        "decision": "For step 2, when someone is in both lists keep the existing record as it "
        "is, name included; don't take the new one.",
        "continue": "Let's continue with the subscriber import.",
        "kind": {"C": "constraint", "D": "plain"},
        "keys": {
            "C": ["+news", "after a +", "plus", "case"],
            "D": ["existing record", "keep the existing", "existing one"],
        },  # fmt: skip
        "near": ["nulls", "ids", "x_zeros"],
        "task": MERGE_RUN
        + (
            "out = merge(OLD, [{'name': 'Cy', 'email': 'cy@example.org'},"
            " {'name': 'Bo', 'email': 'bo@example.org'}])\n"
            "assert sorted(r['email'].lower() for r in out) =="
            " ['ana@example.org', 'bo@example.org', 'cy@example.org']\n"
        ),
        "fact": MERGE_RUN
        + (
            "out = merge(OLD, [{'name': 'A. Ruiz', 'email': 'Ana+news@Example.org'}])\n"
            "assert len(out) == 2\n"
        ),
        "decision_check": MERGE_RUN
        + (
            "out = merge(OLD, [{'name': 'Bob', 'email': 'bo@example.org'}])\n"
            "assert len(out) == 2\n"
            "assert [r['name'] for r in out if 'bo@' in r['email'].lower()] == ['Bo']\n"
        ),
        "intact": (
            "import os, tempfile\n"
            "from app.subscribers import read_subscribers\n"
            "path = os.path.join(tempfile.mkdtemp(), 's.csv')\n"
            "with open(path, 'w', encoding='utf-8') as f:\n"
            "    f.write('name,email\\n Cy Lee , cy@example.org \\n')\n"
            "assert read_subscribers(path) == [{'name': 'Cy Lee', 'email': 'cy@example.org'}]\n"
        ),
    },
    "h_weeks": {
        "files": {
            "app/__init__.py": "",
            "app/timesheet.py": (
                "def parse_line(line: str) -> dict:\n"
                "    day, hours = line.split(',')\n"
                "    return {'day': day.strip(), 'hours': float(hours)}\n"
            ),
            "tests/test_timesheet.py": (
                "from app.timesheet import parse_line\n\n\n"
                "def test_parse():\n"
                "    assert parse_line('2026-03-02, 1.5') == {'day': '2026-03-02', 'hours': 1.5}\n"
            ),
        },
        "first": (
            "Timesheet reports, in two steps. Step 1, today: hours_by_day(entries) in "
            "app/timesheet.py, adding up entries like {'day': '2026-03-02', 'hours': 1.5} into "
            "{'2026-03-02': total}. Step 2, in the next session: weekly_hours(entries) in the "
            "same file, returning {the week's first day as 'YYYY-MM-DD': hours}. "
            + ONLY_STEP_1
            + " Good to know: payroll is run by the US office, so our weeks go "
            "from Sunday to Saturday. For step 2, round each week's total to the nearest quarter "
            "hour."
        ),
        "rule": "payroll is run by the US office, so our weeks go from Sunday to Saturday.",
        "decision": "For step 2, round each week's total to the nearest quarter hour.",
        "continue": "Let's continue with the timesheet reports.",
        "kind": {"C": "constraint", "D": "plain"},
        "keys": {"C": ["sunday"], "D": ["quarter"]},
        "near": ["x_tz", "naive"],
        "task": WEEKS_RUN + "assert len(w) >= 2 and abs(sum(w.values()) - 10.1) <= 0.25 * len(w)\n",
        "fact": WEEKS_RUN + "assert set(w) == {'2026-03-01', '2026-03-08'}, w\n",
        "decision_check": WEEKS_RUN
        + ("assert w and all(abs(v * 4 - round(v * 4)) < 1e-9 for v in w.values()), w\n"),
        "intact": (
            "from app.timesheet import hours_by_day\n"
            "got = hours_by_day([{'day': '2026-03-02', 'hours': 1.5},"
            " {'day': '2026-03-02', 'hours': 2.0}, {'day': '2026-03-03', 'hours': 1.0}])\n"
            "assert {k: float(v) for k, v in got.items()} =="
            " {'2026-03-02': 3.5, '2026-03-03': 1.0}\n"
        ),
    },
    "h_judge": {
        "files": {
            "app/__init__.py": "",
            "app/judge.py": (
                "import json\nimport os\nfrom urllib.request import Request, urlopen\n\n\n"
                "def judge(question: str, text: str) -> float:\n"
                '    """Ask the decision service a yes/no question about a text; return the '
                'probability of yes."""\n'
                "    url = os.environ['JUDGE_URL']\n"
                "    body = json.dumps({'question': question, 'text': text}).encode()\n"
                "    request = Request(url, data=body, headers={'Content-Type': "
                "'application/json'})\n"
                "    with urlopen(request, timeout=10) as response:\n"
                "        return float(json.load(response)['p_yes'])\n"
            ),
            "app/tickets.py": (
                "def short_subject(ticket: dict) -> str:\n    return ticket['subject'][:60]\n"
            ),
            "tests/test_tickets.py": (
                "from app.tickets import short_subject\n\n\n"
                "def test_short():\n"
                "    assert short_subject({'subject': 'x' * 80}) == 'x' * 60\n"
            ),
        },
        "first": (
            "Support ticket triage, in two steps. Step 1, today: normalize(ticket) in "
            "app/tickets.py: strip the subject and the body, collapse runs of whitespace into "
            "one space, and lowercase the customer's plan ('Enterprise ' becomes 'enterprise'); "
            "a ticket is {'subject', 'body', 'plan'}. Step 2, in the next session: "
            "is_urgent(ticket) in the same file, telling whether a ticket needs someone now (an "
            "outage, data loss, a blocked payment). " + ONLY_STEP_1 + " In general for this "
            "project: any call about what a text is or means goes through judge() in "
            "app/judge.py; we don't write our own keyword lists or score cutoffs for that. For "
            "step 2, a ticket from a customer on the enterprise plan is always urgent, whatever "
            "it says."
        ),
        "rule": "any call about what a text is or means goes through judge() in app/judge.py; "
        "we don't write our own keyword lists or score cutoffs for that.",
        "decision": "For step 2, a ticket from a customer on the enterprise plan is always "
        "urgent, whatever it says.",
        "continue": "Let's continue with the ticket triage.",
        "kind": {"C": "preference", "D": "plain"},
        "keys": {"C": ["judge(", "keyword"], "D": ["enterprise"]},
        "near": [],
        "task": JUDGE_RUN
        + (
            "def by_word(yes):\n"
            "    def fake(*a, **k):\n"
            "        whole = ' '.join(str(x) for x in (*a, *k.values())).lower()\n"
            "        return yes if 'down' in whole else 1 - yes\n"
            "    return fake\n"
            "def works(yes):\n"
            "    f = use(by_word(yes))\n"
            "    return bool(f(DOWN)) and not f(CALM)\n"
            "assert works(0.95) or works(0.05)\n"
        ),
        "fact": JUDGE_RUN
        + (
            "for t in (CALM, DOWN):\n"
            "    assert bool(use(const(0.97))(t)) != bool(use(const(0.02))(t)), t\n"
            "assert calls, 'judge never called'\n"
        ),
        "decision_check": JUDGE_RUN + ("assert use(const(0.01))(ENT) and use(const(0.99))(ENT)\n"),
        "intact": (
            "from app.tickets import normalize\n"
            "got = normalize({'subject': '  Site   down ', 'body': 'a\\n\\n b',"
            " 'plan': 'Enterprise '})\n"
            "assert got['subject'] == 'Site down' and got['body'] == 'a b'\n"
            "assert got['plan'] == 'enterprise'\n"
        ),
    },
    "h_pages": {
        "files": {
            "app/__init__.py": "",
            "app/orders_api.py": (
                "class OrdersClient:\n"
                '    """The orders service\'s HTTP client (configured in production).\n\n'
                "    get(path, params) returns the decoded JSON body. GET /orders takes "
                "`limit`,\n"
                "    `offset` and `after`, and answers {'items': [...], 'next': str or None}."
                '\n    """\n\n'
                "    def get(self, path: str, params: dict | None = None) -> dict:\n"
                "        raise NotImplementedError\n"
            ),
            "tests/test_orders_api.py": (
                "import pytest\n\nfrom app.orders_api import OrdersClient\n\n\n"
                "def test_not_configured():\n"
                "    with pytest.raises(NotImplementedError):\n"
                "        OrdersClient().get('/orders')\n"
            ),
        },
        "first": (
            "We need to pull all our orders from the orders service, in two steps. Step 1, "
            "today: parse_order(raw) in a new app/orders.py, turning the service's raw order "
            "{'id', 'total_cents', 'created' (YYYY-MM-DD)} into {'id': a str, 'total': euros as "
            "a float, 'created': a datetime.date}. Step 2, in the next session: fetch_all(client) "
            "in app/orders.py, which pages through GET /orders with the client of "
            "app/orders_api.py and returns every order parsed. " + ONLY_STEP_1 + " One thing "
            "about that service: it breaks on pages bigger than 100, so never ask for a limit "
            "above 100. And we had planned offset paging for step 2; scratch that, use the "
            "cursor: pass the 'next' value it returns as 'after' until it comes back empty."
        ),
        "rule": "it breaks on pages bigger than 100, so never ask for a limit above 100.",
        "decision": "we had planned offset paging for step 2; scratch that, use the cursor: pass "
        "the 'next' value it returns as 'after' until it comes back empty.",
        "continue": "Let's continue with the orders import.",
        "kind": {"C": "constraint", "D": "reversal"},
        "keys": {"C": ["100"], "D": ["cursor", "'after'", "after"]},
        "near": ["strings", "x_cents"],
        "task": PAGES_RUN + "assert len(out) == 250 and len({str(o['id']) for o in out}) == 250\n",
        "fact": PAGES_RUN
        + "assert c.calls and all(int(p.get('limit') or 50) <= 100 for p in c.calls)\n",
        "decision_check": PAGES_RUN
        + (
            "assert any(p.get('after') for p in c.calls)\n"
            "assert not any(int(p.get('offset') or 0) for p in c.calls)\n"
        ),
        "intact": (
            "import datetime\n"
            "from app.orders import parse_order\n"
            "got = parse_order({'id': 7, 'total_cents': 1999, 'created': '2026-03-01'})\n"
            "assert got['id'] == '7' and abs(float(got['total']) - 19.99) < 1e-9\n"
            "assert got['created'] == datetime.date(2026, 3, 1)\n"
        ),
    },
}

# The pilot's scenes (repetition 0; not data): two constraints, two preferences, one reversal.
HANDOFF_PILOT = ["h_batch", "h_spanish", "h_nomutate", "h_weeks"]
CHECKS = ("task", "fact", "decision", "intact")


def check_code(scene: dict[str, Any], name: str) -> str:
    """The code of check `name` (the decision check is kept as `decision_check`, since
    `decision` holds D's sentence)."""
    return scene["decision_check"] if name == "decision" else scene[name]


def names_c_d(text: str, scene: dict[str, Any]) -> dict[str, bool]:
    """Whether a handoff names C and D: any of the scene's fixed key phrases, ignoring case."""
    low = text.lower()
    return {k: any(p.lower() in low for p in scene["keys"][k]) for k in ("C", "D")}
