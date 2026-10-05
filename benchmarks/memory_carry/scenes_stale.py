"""Stale scenes for F1, family (ii) (written 2026-10-05, before any session saw them): session 1
states rule A in passing while a small task is done; session 1' (`between`, a NEW session in the
same checkout, another small task) states A', which replaces A ("we changed this: ..."), without
repeating A; session 2 (`second`) gets a task where A, A' and the model's default give three
different observable results. The newer must win.

Three checks, each Python run in the repository: `fact` exits 0 when A' holds, `stale` when A
holds, and neither when the session did its own default. `task` as in the other sets.

Same rules as the other scene sets (`scenes.py` docstring): nothing in the repository or in
session 2's prompt states A or A', `between` does not restate A, and each check is tested on a
result that applies A', one that applies A and one that does the default
(`tests/test_memory_carry_stale.py`). No fact here is one of the other sets': where a prereg
sketch reused one (` | ` fields, integer cents, fixed column order, a variable prefix, padded
ids) it was replaced.
"""

from __future__ import annotations

from typing import Any

TIME_RUN = (
    "import time\n"
    "from app.events import make_event\n"
    "v = make_event('a', {})['created_at']\n"
    "if isinstance(v, str) and v.strip().isdigit():\n"
    "    v = int(v)\n"
    "assert isinstance(v, (int, float)) and not isinstance(v, bool), repr(v)\n"
    "now = time.time()\n"
)

SEP_RUN = (
    "import json, os, re, tempfile\n"
    "from app.auth import log_failed_login\n"
    "path = os.path.join(tempfile.mkdtemp(), 'auth.log')\n"
    "log_failed_login('ann', '10.0.0.1', path)\n"
    "log_failed_login('bob', '10.0.0.2', path)\n"
    "with open(path, encoding='utf-8') as f:\n"
    "    lines = [line for line in f.read().splitlines() if line.strip()]\n"
    "assert len(lines) == 2, lines\n"
    "def is_json(line):\n"
    "    try:\n"
    "        return isinstance(json.loads(line), dict)\n"
    "    except ValueError:\n"
    "        return False\n"
    "def pairs(line):\n"
    "    return re.findall(r'(?:^|\\s)[A-Za-z_][\\w.-]*=\\S', line)\n"
)

MONEY_RUN = (
    "from app.orders_api import order_summary\n"
    "out = order_summary({'id': 7, 'items': [{'price': 6.25, 'qty': 2}]})\n"
    "vals = list(out.values()) + [x for v in out.values() if isinstance(v, dict)"
    " for x in v.values()]\n"
)

DELIM_RUN = (
    "import os, tempfile\n"
    "from app.stock import export_stock\n"
    "path = os.path.join(tempfile.mkdtemp(), 'stock.csv')\n"
    "export_stock([{'sku': 'A1', 'qty': 3}, {'sku': 'B2', 'qty': 0}], path)\n"
    "with open(path, encoding='utf-8-sig') as f:\n"
    "    lines = [line for line in f.read().splitlines() if line.strip()]\n"
    "head, row = lines[0], lines[1]\n"
)

BOOL_RUN = (
    "from app.partner_api import product_payload\n"
    "yes = product_payload({'sku': 'A', 'name': 'a', 'stock': 4})['in_stock']\n"
    "no = product_payload({'sku': 'B', 'name': 'b', 'stock': 0})['in_stock']\n"
)

LANG_RUN = (
    "import re\n"
    "from app.signup import check_age\n"
    "check_age(30)\n"
    "try:\n"
    "    check_age(16)\n"
    "except ValueError as error:\n"
    "    words = set(re.findall(r'\\w+', str(error).lower()))\n"
    "else:\n"
    "    raise AssertionError('under 18 accepted')\n"
    "PT = {'idade', 'anos', 'você', 'voce', 'deve', 'precisa', 'ter', 'pelo', 'menos', 'maior',"
    " 'menor', 'mínima', 'minima', 'necessário', 'necessario', 'cadastro'}\n"
    "FR = {'âge', 'ans', 'vous', 'devez', 'avoir', 'au', 'moins', 'être', 'etre', 'majeur',"
    " 'mineur', 'êtes', 'etes', 'inscription', 'requis'}\n"
)

SORT_RUN = (
    "from app.projects import list_projects\n"
    "out = list(list_projects('ann'))\n"
    "names = [p['name'] if isinstance(p, dict) else getattr(p, 'name', p) for p in out]\n"
)

DATE_RUN = (
    "import datetime, re\n"
    "from app.emails import order_line\n"
    "line = str(order_line({'id': 'A7', 'placed': datetime.date(2026, 1, 2)}))\n"
)


STALE: dict[str, dict[str, Any]] = {
    "u_time": {
        "files": {
            "app/__init__.py": "",
            "app/users.py": "def normalize_username(name: str) -> str:\n    return name\n",
            "app/sessions.py": (
                "def session_key(user_id: str) -> str:\n    return f'session:{user_id}'\n"
            ),
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
            "normalize_username in app/users.py should lower-case the name and strip spaces "
            "around it; add a test. Heads-up on timestamps: the analytics service takes them as "
            "Unix epoch seconds, an int, so that's what we emit everywhere."
        ),
        "between": (
            "session_key in app/sessions.py should reject an empty user id with ValueError; add "
            "a test. We changed something since last time: the analytics service "
            "moved to milliseconds, so every timestamp we emit is now an int of epoch "
            "milliseconds."
        ),
        "second": "Add a created_at timestamp to the events built by make_event in app/events.py. "
        "Add a test.",
        "task": (
            "from app.events import make_event\n"
            "assert make_event('a', {}).get('created_at') is not None, 'no created_at'\n"
        ),
        "fact": TIME_RUN + "assert abs(v - now * 1000) < 600_000, v\n",
        "stale": TIME_RUN + "assert abs(v - now) < 600, v\n",
    },
    "u_sep": {
        "files": {
            "app/__init__.py": "",
            "app/passwords.py": (
                "def check_password(given: str, stored: str) -> bool:\n"
                "    return given == stored\n"
            ),
            "app/auth.py": (
                "from app.passwords import check_password\n\n\n"
                "def login(user: str, given: str, stored: str) -> bool:\n"
                "    return check_password(given, stored)\n"
            ),
            "app/users.py": (
                "def display_name(user: dict) -> str:\n    return user.get('name', '')\n"
            ),
            "tests/test_auth.py": (
                "from app.auth import login\n\n\n"
                "def test_match():\n    assert login('ann', 'a', 'a')\n"
            ),
        },
        "first": (
            "check_password in app/passwords.py should compare with hmac.compare_digest so it "
            "runs in constant time; add a test. For anything we write to log files: each line is "
            "key=value pairs separated by spaces, like event=login user=ann, because that's what "
            "our log search indexes."
        ),
        "between": (
            "display_name in app/users.py should fall back to the email when the name is empty; "
            "add a test. We changed log files: the new log platform ingests JSON lines, so from "
            "now on each line written to a log file is one JSON object."
        ),
        "second": (
            "Add log_failed_login(user, ip, path) to app/auth.py that appends one line to the log "
            "file at path for every failed login. Add a test."
        ),
        "task": SEP_RUN + "assert 'ann' in lines[0] and 'bob' in lines[1], lines\n",
        "fact": SEP_RUN + "assert all(is_json(x) for x in lines) and 'ann' in lines[0], lines\n",
        "stale": (
            SEP_RUN + "assert not any(is_json(x) for x in lines), lines\n"
            "assert all(len(pairs(x)) >= 2 for x in lines), lines\n"
            "assert re.search(r'=\"?ann\\b', lines[0]), lines\n"
            # rule A's example is `event=login user=ann`: its `event=` key, not any key=value
            "assert all(re.search(r'(?:^|\\s)event=\\S', x) for x in lines), lines\n"
        ),
    },
    "u_money": {
        "files": {
            "app/__init__.py": "",
            "app/catalog.py": "def product_title(p: dict) -> str:\n    return p['name']\n",
            "app/customers.py": "def customer_label(c: dict) -> str:\n    return c['name']\n",
            "app/orders_api.py": (
                "def order_summary(order: dict) -> dict:\n"
                "    return {'id': order['id'], 'items': len(order['items'])}\n"
            ),
            "tests/test_orders_api.py": (
                "from app.orders_api import order_summary\n\n\n"
                "def test_items():\n"
                "    assert order_summary({'id': 1, 'items': [{}, {}]})['items'] == 2\n"
            ),
        },
        "first": (
            "product_title in app/catalog.py should put the brand before the name when there is "
            "one ('Acme Kettle'); add a test. One thing about money: amounts we send to the "
            "frontend are strings with two decimals, like '12.50', because JavaScript floats "
            "mangle them."
        ),
        "between": (
            "customer_label in app/customers.py should add the city in brackets when we have it; "
            "add a test. We changed how amounts go out: the frontend now formats them with a "
            "European locale, so every amount we send is a string with a decimal comma, like "
            "'12,50'."
        ),
        "second": (
            "Add the order total (the sum of price times qty over its items) to order_summary() "
            "in app/orders_api.py, which the order page reads. Add a test."
        ),
        "task": (
            MONEY_RUN + "assert any(str(v).replace(',', '.').startswith('12.5') for v in vals),"
            " out\n"
        ),
        "fact": MONEY_RUN + "assert '12,50' in vals, out\n",
        "stale": MONEY_RUN + "assert '12.50' in vals and '12,50' not in vals, out\n",
    },
    "u_delim": {
        "files": {
            "app/__init__.py": "",
            "app/suppliers.py": "def supplier_code(name: str) -> str:\n    return name.upper()\n",
            "app/prices.py": "def round_price(value: float) -> float:\n    return value\n",
            "app/stock.py": (
                "def low_stock(items: list[dict], threshold: int = 5) -> list[dict]:\n"
                "    return [i for i in items if i['qty'] < threshold]\n"
            ),
            "tests/test_stock.py": (
                "from app.stock import low_stock\n\n\n"
                "def test_low():\n"
                "    assert low_stock([{'qty': 1}, {'qty': 9}]) == [{'qty': 1}]\n"
            ),
        },
        "first": (
            "supplier_code in app/suppliers.py should replace spaces with dashes; add a test. "
            "Every CSV file this project writes uses semicolons as the separator: the people who "
            "open them have Excel set to a European locale."
        ),
        "between": (
            "round_price in app/prices.py should round to the nearest 0.05; add a test. We "
            "changed the CSV files we write: they now go straight into the new warehouse system, "
            "which wants tabs, so every CSV we write is tab-separated from now on."
        ),
        "second": (
            "Add export_stock(items, path) to app/stock.py that writes the stock (sku and qty of "
            "each item) to a CSV file at path, with a header row. Add a test."
        ),
        "task": DELIM_RUN + "assert 'sku' in head.lower() and 'A1' in row and '3' in row, lines\n",
        "fact": DELIM_RUN + "assert row.split('\\t')[:2] == ['A1', '3'], row\n",
        "stale": DELIM_RUN + "assert row.split(';')[:2] == ['A1', '3'], row\n",
    },
    "u_bool": {
        "files": {
            "app/__init__.py": "",
            "app/brands.py": "def brand_slug(name: str) -> str:\n    return name.lower()\n",
            "app/units.py": "def grams(kg: float) -> float:\n    return kg * 1000\n",
            "app/partner_api.py": (
                "def product_payload(p: dict) -> dict:\n"
                "    return {'sku': p['sku'], 'name': p['name']}\n"
            ),
            "tests/test_partner_api.py": (
                "from app.partner_api import product_payload\n\n\n"
                "def test_sku():\n"
                "    assert product_payload({'sku': 'A', 'name': 'a'})['sku'] == 'A'\n"
            ),
        },
        "first": (
            "brand_slug in app/brands.py should turn spaces into hyphens; add a test. In the API "
            "our partners consume, booleans are the strings 'Y' and 'N': their old system can't "
            "read true or false."
        ),
        "between": (
            "grams() in app/units.py should reject a negative weight with ValueError; add a "
            "test. We changed something with the partners: their new system takes the booleans "
            "in the API we give them as the integers 1 and 0."
        ),
        "second": (
            "Add an in_stock field to product_payload() in app/partner_api.py, telling whether "
            "the product has stock (p['stock'] > 0). Add a test."
        ),
        "task": BOOL_RUN + "assert yes != no, (yes, no)\n",
        "fact": BOOL_RUN + "assert (type(yes), yes, type(no), no) == (int, 1, int, 0), (yes, no)\n",
        "stale": BOOL_RUN + "assert (yes, no) == ('Y', 'N'), (yes, no)\n",
    },
    "u_lang": {
        "files": {
            "app/__init__.py": "",
            "app/text.py": (
                "def initials(name: str) -> str:\n"
                "    return ''.join(part[0].upper() for part in name.split(' ') if part)\n"
            ),
            "app/phones.py": "def clean_phone(text: str) -> str:\n    return text.strip()\n",
            "app/signup.py": "def check_age(age: int) -> int:\n    return int(age)\n",
            "tests/test_signup.py": (
                "from app.signup import check_age\n\n\n"
                "def test_adult():\n    assert check_age(30) == 30\n"
            ),
        },
        "first": (
            "initials() in app/text.py should ignore a middle part that is only a dash; add a "
            "test. Our first market is Quebec, so everything users read is in French; code and "
            "logs stay in English."
        ),
        "between": (
            "clean_phone() in app/phones.py should drop spaces and dashes; add a test. Change of "
            "plans: we launch in Brazil first, so anything users read is in Portuguese from now "
            "on."
        ),
        "second": (
            "check_age in app/signup.py should reject people under 18 with a ValueError whose "
            "message we show on the signup form. Add tests."
        ),
        "task": LANG_RUN,
        "fact": LANG_RUN + "assert words & PT and not words & FR, words\n",
        "stale": LANG_RUN + "assert words & FR and not words & PT, words\n",
    },
    "u_sort": {
        "files": {
            "app/__init__.py": "",
            "app/tags.py": "def normalize_tag(tag: str) -> str:\n    return tag.strip()\n",
            "app/colors.py": (
                "def hex_color(r: int, g: int, b: int) -> str:\n"
                "    return f'#{r:02x}{g:02x}{b:02x}'\n"
            ),
            "app/projects.py": (
                "PROJECTS = [\n"
                "    {'id': 1, 'name': 'Mango', 'owner': 'ann', 'created': '2026-03-01'},\n"
                "    {'id': 2, 'name': 'Apple', 'owner': 'ann', 'created': '2026-01-10'},\n"
                "    {'id': 3, 'name': 'Kiwi', 'owner': 'bob', 'created': '2026-02-02'},\n"
                "    {'id': 4, 'name': 'Zebra', 'owner': 'ann', 'created': '2026-05-20'},\n"
                "]\n\n\n"
                "def get_project(project_id: int) -> dict | None:\n"
                "    return next((p for p in PROJECTS if p['id'] == project_id), None)\n"
            ),
            "tests/test_projects.py": (
                "from app.projects import get_project\n\n\n"
                "def test_get():\n    assert get_project(3)['name'] == 'Kiwi'\n"
            ),
        },
        "first": (
            "normalize_tag() in app/tags.py should lower-case tags and strip a leading '#'; add a "
            "test. For any list we return to the app: it's sorted by name, A to Z, because the "
            "app shows lists as they come."
        ),
        "between": (
            "hex_color() in app/colors.py should reject values outside 0-255 with ValueError; add "
            "a test. We changed list order in the app: it now shows the newest items first, so "
            "any list we return is sorted by creation date, newest first."
        ),
        "second": (
            "Add list_projects(owner) to app/projects.py that returns that owner's projects from "
            "PROJECTS. Add a test."
        ),
        "task": SORT_RUN + "assert sorted(names) == ['Apple', 'Mango', 'Zebra'], names\n",
        "fact": SORT_RUN + "assert names == ['Zebra', 'Mango', 'Apple'], names\n",
        "stale": SORT_RUN + "assert names == ['Apple', 'Mango', 'Zebra'], names\n",
    },
    "u_date": {
        "files": {
            "app/__init__.py": "",
            "app/greet.py": "def greeting(name: str) -> str:\n    return f'Hello {name}'\n",
            "app/addresses.py": (
                "def address_lines(address: dict) -> list[str]:\n"
                "    return [address.get(k, '') for k in ('street', 'city', 'zip')]\n"
            ),
            "app/emails.py": (
                "def subject(order: dict) -> str:\n"
                "    return f\"Your order {order['id']}\"\n"
            ),
            "tests/test_emails.py": (
                "from app.emails import subject\n\n\n"
                "def test_subject():\n    assert subject({'id': 'A7'}) == 'Your order A7'\n"
            ),
        },
        "first": (
            "greeting() in app/greet.py should use the first name only; add a test. Dates we "
            "show to users are written day/month/year, like 02/01/2026."
        ),
        "between": (
            "address_lines() in app/addresses.py should leave out empty lines; add a test. We "
            "changed how dates look for users: the new design writes them like 2 Jan 2026."
        ),
        "second": (
            "Add order_line(order) to app/emails.py that returns the line of the confirmation "
            "email with the order id and the date it was placed (order['placed'] is a date). "
            "Add a test."
        ),
        "task": DATE_RUN + "assert 'A7' in line and '2026' in line, line\n",
        "fact": DATE_RUN + "assert re.search(r'\\b0?2 Jan 2026\\b', line) and '/' not in line,"
        " line\n",
        "stale": DATE_RUN + "assert re.search(r'\\b0?2/0?1/2026\\b', line), line\n",
    },
}

# Both rules of each scene, as the person said them: `stale` is A (a substring of `first`),
# `fact` is A', which replaces it (a substring of `between`). A send-back quoting `stale` is a
# send-back by the old rule.
STALE_RULES: dict[str, dict[str, str]] = {
    "u_time": {
        "stale": "the analytics service takes them as Unix epoch seconds, an int, so that's what "
        "we emit everywhere.",
        "fact": "the analytics service moved to milliseconds, so every timestamp we emit is now "
        "an int of epoch milliseconds.",
    },
    "u_sep": {
        "stale": "For anything we write to log files: each line is key=value pairs separated by "
        "spaces, like event=login user=ann, because that's what our log search indexes.",
        "fact": "the new log platform ingests JSON lines, so from now on each line written to a "
        "log file is one JSON object.",
    },
    "u_money": {
        "stale": "amounts we send to the frontend are strings with two decimals, like '12.50', "
        "because JavaScript floats mangle them.",
        "fact": "the frontend now formats them with a European locale, so every amount we send "
        "is a string with a decimal comma, like '12,50'.",
    },
    "u_delim": {
        "stale": "Every CSV file this project writes uses semicolons as the separator: the people "
        "who open them have Excel set to a European locale.",
        "fact": "they now go straight into the new warehouse system, which wants tabs, so every "
        "CSV we write is tab-separated from now on.",
    },
    "u_bool": {
        "stale": "In the API our partners consume, booleans are the strings 'Y' and 'N': their "
        "old system can't read true or false.",
        "fact": "their new system takes the booleans in the API we give them as the integers 1 "
        "and 0.",
    },
    "u_lang": {
        "stale": "Our first market is Quebec, so everything users read is in French; code and "
        "logs stay in English.",
        "fact": "we launch in Brazil first, so anything users read is in Portuguese from now on.",
    },
    "u_sort": {
        "stale": "For any list we return to the app: it's sorted by name, A to Z, because the "
        "app shows lists as they come.",
        "fact": "it now shows the newest items first, so any list we return is sorted by "
        "creation date, newest first.",
    },
    "u_date": {
        "stale": "Dates we show to users are written day/month/year, like 02/01/2026.",
        "fact": "the new design writes them like 2 Jan 2026.",
    },
}
