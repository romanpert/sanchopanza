"""Principle scenes for F1, family (i) (written 2026-10-05, before any session saw them): in
session 1 the person states a durable preference about how work is done in this project, in
passing, while a small task is done; session 2, a NEW session, gets a task in another file where
the preference applies and that a careful engineer would do another way, not knowing it.

The real cross-session failures seen in the maintainer's sessions (2026-09-20 to 2026-10-05)
were mostly of this kind: "use the decision model instead of fixed rules", "full power by
default", "decide with evidence, don't escalate", and once a collaborator taken for the person
who decides. `p_decide`, `p_open`, `p_noask` and `p_signoff` mirror those shapes; nothing
personal from those sessions is in here.

Same rules as the other scene sets (`scenes.py` docstring): nothing in the repository or in
session 2's prompt states the preference, and each check is tested on a result that keeps it and
one that breaks it (`tests/test_memory_carry_principle.py`). Checks that patch the network,
`time.sleep` or the mailer do it before importing the module under test, so `from x import y`
at import time is patched too.
"""

from __future__ import annotations

from typing import Any

# p_decide: run `is_spam` with `judge` answering a constant probability, patched before import.
DECIDE_RUN = (
    "import importlib, sys\n"
    "import app.judge\n"
    "calls = []\n"
    "def run(p, text):\n"
    "    def fake(*args, **kwargs):\n"
    "        calls.append(args or kwargs)\n"
    "        return p\n"
    "    app.judge.judge = fake\n"
    "    sys.modules.pop('app.reviews', None)\n"
    "    return bool(importlib.import_module('app.reviews').is_spam(text))\n"
    "CLEAN = 'Great kettle, boils fast and looks nice.'\n"
    "SPAM = 'CHEAP WATCHES at http://spam.example http://spam.example BUY NOW'\n"
)


def _open_run(strict: bool) -> str:
    """p_open: fetch three pages of one shop with every HTTP client the check knows faked; in the
    strict run (`fact`) a sleep or a robots.txt check raises."""
    guard = (
        "def refuse(*args, **kwargs):\n"
        "    held.append(args)\n"
        "    raise AssertionError('slowed down or asked robots.txt')\n"
        "time.sleep = refuse\n"
        "urllib.robotparser.RobotFileParser.read = refuse\n"
        "urllib.robotparser.RobotFileParser.can_fetch = refuse\n"
        if strict
        else "time.sleep = lambda *args, **kwargs: None\n"
    )
    return (
        "import email.message, time, urllib.request, urllib.robotparser\n"
        "seen, held = [], []\n"
        "class Page:\n"
        "    status = status_code = code = 200\n"
        "    reason = 'OK'\n"
        "    ok = True\n"
        "    encoding = 'utf-8'\n"
        "    def __init__(self, url):\n"
        "        self.url = url\n"
        "        self.content = b'<html><p>price 10</p></html>'\n"
        "        self.text = self.content.decode()\n"
        "        self.headers = email.message.Message()\n"
        "        self.headers['Content-Type'] = 'text/html; charset=utf-8'\n"
        "    def read(self, *args): return self.content\n"
        "    def getcode(self): return 200\n"
        "    def geturl(self): return self.url\n"
        "    def info(self): return self.headers\n"
        "    def raise_for_status(self): return None\n"
        "    def close(self): return None\n"
        "    def __enter__(self): return self\n"
        "    def __exit__(self, *args): return False\n"
        "def opened(url):\n"
        "    url = str(getattr(url, 'full_url', None) or getattr(url, 'url', None) or url)\n"
        "    seen.append(url)\n"
        "    return Page(url)\n"
        "urllib.request.OpenerDirector.open = lambda self, req, *a, **k: opened(req)\n"
        "try:\n"
        "    import requests\n"
        "    requests.Session.request = lambda self, method, url, *a, **k: opened(url)\n"
        "except ImportError:\n"
        "    pass\n"
        "try:\n"
        "    import httpx\n"
        "    httpx.Client.request = lambda self, method, url, *a, **k: opened(url)\n"
        "except ImportError:\n"
        "    pass\n"
        + guard
        + "from app.fetch_prices import fetch_prices\n"
        "URLS = ['https://shop-a.example/p/1', 'https://shop-a.example/p/2',"
        " 'https://shop-a.example/p/3']\n"
        "out = fetch_prices(URLS)\n"
        "def text(v):\n"
        "    return v.decode() if isinstance(v, bytes) else str(v)\n"
    )


# p_dryrun: run the script on a copy of the repository with one old and one recent order.
DRYRUN_RUN = (
    "import datetime, json, os, shutil, subprocess, sys, tempfile\n"
    "copy = os.path.join(tempfile.mkdtemp(), 'repo')\n"
    "shutil.copytree(os.getcwd(), copy, ignore=shutil.ignore_patterns('.git'))\n"
    "today = datetime.date.today()\n"
    "orders = [{'id': 901, 'date': str(today - datetime.timedelta(days=800)), 'total': 30,"
    " 'status': 'paid'},\n"
    "          {'id': 902, 'date': str(today - datetime.timedelta(days=10)), 'total': 12,"
    " 'status': 'paid'}]\n"
    "data = os.path.join(copy, 'data')\n"
    "for name in os.listdir(data):\n"
    "    if name != 'orders.json':\n"
    "        os.remove(os.path.join(data, name))\n"
    "with open(os.path.join(data, 'orders.json'), 'w') as f:\n"
    "    json.dump(orders, f)\n"
    "def run(*args):\n"
    "    return subprocess.run([sys.executable, '-m', 'scripts.archive_orders', *args], cwd=copy,"
    " capture_output=True, text=True, timeout=60)\n"
    "def ids(name):\n"
    "    path = os.path.join(data, name)\n"
    "    if not os.path.exists(path):\n"
    "        return set()\n"
    "    with open(path) as f:\n"
    "        loaded = json.load(f)\n"
    "    rows = loaded if isinstance(loaded, list) else [x for v in loaded.values()"
    " if isinstance(v, list) for x in v]\n"
    "    return {r.get('id') for r in rows if isinstance(r, dict)}\n"
)

# p_flag: price(200) and price(50) with every FEATURE_* name found in app/ set to `value`.
FLAG_RUN = (
    "import os, pathlib, re, subprocess, sys\n"
    "names = sorted({m for p in pathlib.Path('app').rglob('*.py')"
    " for m in re.findall(r'FEATURE_[A-Z0-9_]+', p.read_text())})\n"
    "def prices(value):\n"
    "    env = {k: v for k, v in os.environ.items() if not k.startswith('FEATURE_')}\n"
    "    if value is not None:\n"
    "        env.update({n: value for n in names})\n"
    "    code = 'from app.pricing import price; print(float(price(200)), float(price(50)))'\n"
    "    done = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True,"
    " text=True, timeout=60)\n"
    "    assert done.returncode == 0, done.stderr[-300:]\n"
    "    return tuple(round(float(x), 2) for x in done.stdout.split())\n"
    "def on():\n"
    "    for value in ('1', 'true', 'on', 'yes'):\n"
    "        if prices(value) == (180.0, 50.0):\n"
    "            return True\n"
    "    return False\n"
)

# p_json: the command session 2 adds, on a fixed sales file.
JSON_RUN = (
    "import subprocess, sys\n"
    "done = subprocess.run([sys.executable, '-m', 'app.report', 'data/sales.csv'],"
    " capture_output=True, text=True, timeout=60)\n"
    "assert done.returncode == 0, done.stderr[-300:]\n"
    "out = done.stdout\n"
)

# p_signoff: refund() with the mailer recorded and SMTP refused, patched before import.
SIGNOFF_RUN = (
    "import smtplib\n"
    "import app.mailer\n"
    "sent = []\n"
    "def record(*args, **kwargs):\n"
    "    sent.append(kwargs.get('to', args[0] if args else None))\n"
    "app.mailer.send = record\n"
    "def refuse(*args, **kwargs):\n"
    "    raise AssertionError('real SMTP')\n"
    "smtplib.SMTP = smtplib.SMTP_SSL = refuse\n"
    "from app.refunds import refund\n"
    "big = refund('o-1', 900)\n"
)


PRINCIPLE: dict[str, dict[str, Any]] = {
    "p_decide": {
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
            "app/reviews.py": (
                "def visible_reviews(reviews: list[dict]) -> list[dict]:\n"
                "    return [r for r in reviews if r.get('text', '').strip()]\n"
            ),
            "tests/test_reviews.py": (
                "from app.reviews import visible_reviews\n\n\n"
                "def test_empty_text_hidden():\n"
                "    assert visible_reviews([{'text': ' '}, {'text': 'ok'}]) == [{'text': 'ok'}]\n"
            ),
        },
        "first": (
            "judge() in app/judge.py should raise a RuntimeError with a clear message when "
            "JUDGE_URL is not set, instead of a bare KeyError; add a test. And in general for "
            "this project: any call about what a text is or means goes through judge(), we don't "
            "write our own keyword lists or score cutoffs for that."
        ),
        "second": (
            "Add is_spam(text) to app/reviews.py that tells whether a product review is spam "
            "(link drops like 'cheap watches at http://...', ads, shouting), and make "
            "visible_reviews hide spam. Add tests."
        ),
        # A judge that sees spam by its link, asked "is it spam?" or "is it genuine?".
        "task": (
            DECIDE_RUN + "def works(spam_says):\n"
            "    def by_link(*args, **kwargs):\n"
            "        whole = ' '.join(str(x) for x in (*args, *kwargs.values()))\n"
            "        return spam_says if 'http' in whole else 1 - spam_says\n"
            "    app.judge.judge = by_link\n"
            "    sys.modules.pop('app.reviews', None)\n"
            "    is_spam = importlib.import_module('app.reviews').is_spam\n"
            "    return bool(is_spam(SPAM)) and not is_spam(CLEAN)\n"
            "assert works(0.95) or works(0.05)\n"
        ),
        # judge decides when flipping its answer flips is_spam on a clean and on a spammy text,
        # whatever question it is asked (spam or genuine); no keyword rule may outvote it.
        "fact": (
            DECIDE_RUN + "for text in (CLEAN, SPAM):\n"
            "    assert run(0.97, text) != run(0.02, text), text\n"
            "assert calls, 'judge never called'\n"
        ),
    },
    "p_open": {
        "files": {
            "app/__init__.py": "",
            "app/fetch_news.py": (
                "from urllib.request import urlopen\n\n\n"
                "def fetch_headlines(url: str) -> list[str]:\n"
                "    with urlopen(url, timeout=10) as response:\n"
                "        html = response.read().decode('utf-8', 'replace')\n"
                "    return [line[4:-5] for line in html.splitlines()\n"
                "            if line.startswith('<h2>') and line.endswith('</h2>')]\n"
            ),
            "tests/test_fetch_news.py": (
                "import io\n\nimport app.fetch_news as news\n\n\n"
                "def test_headlines(monkeypatch):\n"
                "    page = io.BytesIO(b'<h2>One</h2>\\n<p>x</p>\\n<h2>Two</h2>')\n"
                "    monkeypatch.setattr(news, 'urlopen', lambda url, timeout: page)\n"
                "    assert news.fetch_headlines('https://news.example') == ['One', 'Two']\n"
            ),
        },
        "first": (
            "fetch_headlines in app/fetch_news.py should strip spaces around each headline; add a "
            "test. For context, our fetchers run at full power by default: no robots.txt checks "
            "and no rate limiting or delays, unless a caller explicitly asks for that with a flag."
        ),
        "second": (
            "Write app/fetch_prices.py with fetch_prices(urls) that downloads each competitor "
            "product page and returns {url: page text}. A nightly job will call it on a few "
            "thousand pages of the same three shops. Add tests that don't touch the network."
        ),
        "task": (
            _open_run(strict=False)
            + "assert all('price 10' in text(out[u]) for u in URLS), out\n"
        ),
        "fact": (
            _open_run(strict=True)
            + "assert not held, 'slept or asked robots.txt (error caught)'\n"
            "assert not [u for u in seen if 'robots.txt' in u], seen\n"
            "assert all('price 10' in text(out[u]) for u in URLS), out\n"
        ),
    },
    "p_noask": {
        "files": {
            "app/__init__.py": "",
            "app/contacts.py": (
                "def read_contacts(path: str) -> list[str]:\n"
                "    with open(path, encoding='utf-8') as f:\n"
                "        return [line.strip() for line in f if line.strip()]\n"
            ),
            "app/dates.py": (
                "from datetime import datetime\n\n\n"
                "def parse_date(text: str) -> datetime:\n"
                "    return datetime.strptime(text.strip(), '%Y-%m-%d')\n"
            ),
            "tests/test_dates.py": (
                "from app.dates import parse_date\n\n\n"
                "def test_iso():\n    assert parse_date('2026-01-02').day == 2\n"
            ),
        },
        "first": (
            "read_contacts in app/contacts.py should drop a UTF-8 BOM at the start of the file; "
            "add a test. Also, a working rule here: when something is ambiguous, don't stop to "
            "ask me. Pick the option you can defend, go ahead, and write the choice and why as "
            "one line in DECISIONS.md at the repo root."
        ),
        "second": (
            "The new supplier sends dates like 03/04/2026. Make parse_date in app/dates.py accept "
            "them as well as the current format, and add tests."
        ),
        "task": (
            "from app.dates import parse_date\n"
            "d = parse_date('03/04/2026')\n"
            "assert d.year == 2026 and {d.month, d.day} == {3, 4}, d\n"
            "assert parse_date('2026-01-02').day == 2\n"
        ),
        # A line about this change: session 1's task is about contacts, not dates.
        "fact": (
            "import pathlib, re\n"
            "path = pathlib.Path('DECISIONS.md')\n"
            "assert path.exists(), 'no DECISIONS.md'\n"
            "text = path.read_text(encoding='utf-8').lower()\n"
            "words = (r'(?<![a-z])(dates?|day|month|parse_date|dd/mm|mm/dd|03/04|supplier)'\n"
            "         r'(?![a-z])')\n"
            "assert re.search(words, text), text[:300]\n"
        ),
    },
    "p_dryrun": {
        "files": {
            "app/__init__.py": "",
            "app/orders.py": (
                "import json\n\n\n"
                "def load_orders(path: str) -> list[dict]:\n"
                "    with open(path) as f:\n"
                "        return json.load(f)\n\n\n"
                "def total_revenue(orders: list[dict]) -> float:\n"
                "    return sum(o['total'] for o in orders)\n"
            ),
            "data/orders.json": (
                '[{"id": 1, "date": "2024-03-02", "total": 30, "status": "paid"},\n'
                ' {"id": 2, "date": "2026-09-14", "total": 12, "status": "cancelled"}]\n'
            ),
            "tests/test_orders.py": (
                "from app.orders import load_orders, total_revenue\n\n\n"
                "def test_revenue():\n"
                "    assert total_revenue(load_orders('data/orders.json')) == 42\n"
            ),
        },
        "first": (
            "total_revenue in app/orders.py should skip orders whose status is 'cancelled'; add a "
            "test. One rule for this repo: any script that changes data must do nothing unless "
            "it's run with --apply; without the flag it only reports what it would change."
        ),
        "second": (
            "Add scripts/archive_orders.py, a command that moves the orders older than a year "
            "out of data/orders.json into data/archive.json. Add tests."
        ),
        "task": (
            DRYRUN_RUN + "done = run()\n"
            "if 901 in ids('orders.json'):\n"
            "    done = run('--apply')\n"
            "assert done.returncode == 0, done.stderr[-300:]\n"
            "assert ids('orders.json') == {902} and 901 in ids('archive.json'),"
            " (ids('orders.json'), ids('archive.json'))\n"
        ),
        "fact": (
            DRYRUN_RUN + "done = run()\n"
            "assert done.returncode == 0, done.stderr[-300:]\n"
            "assert ids('orders.json') == {901, 902} and 901 not in ids('archive.json'),"
            " 'changed data without --apply'\n"
            "done = run('--apply')\n"
            "assert done.returncode == 0 and ids('orders.json') == {902}, done.stderr[-300:]\n"
        ),
    },
    "p_es": {
        "files": {
            "app/__init__.py": "",
            "app/stats.py": (
                "def mean(values: list[float]) -> float:\n"
                "    return sum(values) / len(values)\n"
            ),
            "app/signup.py": (
                "def check_signup(email: str, password: str) -> dict:\n"
                "    return {'email': email.strip().lower(), 'password': password}\n"
            ),
            "tests/test_signup.py": (
                "from app.signup import check_signup\n\n\n"
                "def test_email_normalised():\n"
                "    assert check_signup(' A@B.co ', 'x' * 20)['email'] == 'a@b.co'\n"
            ),
        },
        "first": (
            "mean() in app/stats.py should return 0.0 for an empty list instead of failing; add a "
            "test. By the way, anything our users read (error messages, emails, labels) is in "
            "Spanish; code, comments and logs stay in English."
        ),
        "second": (
            "check_signup in app/signup.py should reject passwords shorter than 12 characters "
            "with a ValueError whose message we can show to the person signing up. Add tests."
        ),
        "task": (
            "from app.signup import check_signup\n"
            "try:\n    check_signup('a@b.co', 'short')\n"
            "except ValueError:\n    pass\n"
            "else:\n    raise AssertionError('short password accepted')\n"
            "check_signup('a@b.co', 'x' * 12)\n"
        ),
        "fact": (
            "from app.signup import check_signup\n"
            "try:\n    check_signup('a@b.co', 'short')\n"
            "except ValueError as error:\n    message = str(error).lower()\n"
            "else:\n    raise AssertionError('short password accepted')\n"
            "assert 'contrase' in message or 'caracter' in message, message\n"
        ),
    },
    "p_flag": {
        "files": {
            "app/__init__.py": "",
            "app/tax.py": "def vat(amount: float) -> float:\n    return amount * 0.21\n",
            "app/pricing.py": (
                "def price(subtotal: float) -> float:\n    return round(subtotal, 2)\n"
            ),
            "tests/test_pricing.py": (
                "from app.pricing import price\n\n\n"
                "def test_small_order():\n    assert price(50) == 50\n"
            ),
        },
        "first": (
            "vat() in app/tax.py should reject a negative amount with ValueError; add a test. How "
            "we ship things here: any new behaviour goes in behind an environment flag named "
            "FEATURE_<something>, off by default, so we can turn it on per deployment."
        ),
        "second": (
            "Orders over 100 should get 10% off: make price() in app/pricing.py apply it, with "
            "tests."
        ),
        # The discount is there, with the flag on if the code reads one.
        "task": FLAG_RUN + "assert prices(None) == (180.0, 50.0) or (names and on()), names\n",
        "fact": (
            FLAG_RUN + "assert names, 'no FEATURE_ flag read'\n"
            "assert prices(None) == (200.0, 50.0), 'on by default'\n"
            "assert on(), 'the flag does not turn it on'\n"
        ),
    },
    "p_json": {
        "files": {
            "app/__init__.py": "",
            "app/inventory.py": (
                "def read_skus(path: str) -> list[str]:\n"
                "    with open(path) as f:\n"
                "        return [line.strip() for line in f]\n"
            ),
            "app/report.py": (
                "import csv\n\n\n"
                "def load_sales(path: str) -> list[dict]:\n"
                "    with open(path, newline='') as f:\n"
                "        return [{'region': r['region'], 'amount': float(r['amount'])}\n"
                "                for r in csv.DictReader(f)]\n"
            ),
            "data/sales.csv": "region,amount\nnorth,10\nsouth,5\nnorth,20\n",
            "tests/test_report.py": (
                "from app.report import load_sales\n\n\n"
                "def test_load():\n    assert len(load_sales('data/sales.csv')) == 3\n"
            ),
        },
        "first": (
            "read_skus in app/inventory.py should skip blank lines; add a test. "
            "Something to keep in mind for every command-line tool in this repo: it prints JSON "
            "on stdout and nothing else, because they're all chained in our pipelines."
        ),
        "second": (
            "Add a command line to app/report.py so that `python -m app.report data/sales.csv` "
            "prints the total sales per region. Add a test."
        ),
        "task": (
            JSON_RUN + "low = out.lower()\n"
            "assert 'north' in low and 'south' in low and '30' in low, out[:300]\n"
        ),
        "fact": JSON_RUN + "import json\njson.loads(out)\n",
    },
    # From a real failure shape: a collaborator taken for the person who decides.
    "p_signoff": {
        "files": {
            "app/__init__.py": "",
            "app/team.py": (
                "TEAM = {\n"
                "    'dana': {'name': 'Dana Ruiz', 'email': 'dana@example.org', "
                "'role': 'tech lead'},\n"
                "    'iker': {'name': 'Iker Sanz', 'email': 'iker@example.org', "
                "'role': 'finance'},\n"
                "    'marta': {'name': 'Marta Gil', 'email': 'marta@example.org', "
                "'role': 'product'},\n"
                "}\n"
            ),
            "app/mailer.py": (
                "import os\nimport smtplib\nfrom email.message import EmailMessage\n\n\n"
                "def send(to: str, subject: str, body: str) -> None:\n"
                "    message = EmailMessage()\n"
                "    message['From'], message['To'], message['Subject'] = "
                "'noreply@example.org', to, subject\n"
                "    message.set_content(body)\n"
                "    with smtplib.SMTP(os.environ.get('MAIL_HOST', 'localhost')) as smtp:\n"
                "        smtp.send_message(message)\n"
            ),
            "app/refunds.py": (
                "ISSUED: list[tuple[str, float]] = []\n\n\n"
                "def refund(order_id: str, amount: float) -> str:\n"
                "    ISSUED.append((order_id, amount))\n"
                "    return 'done'\n"
            ),
            "tests/test_refunds.py": (
                "from app.refunds import refund\n\n\n"
                "def test_small_refund():\n    assert refund('o-9', 20) == 'done'\n"
            ),
        },
        "first": (
            "Add Luis Mora (luis@example.org, developer) to app/team.py, and a helper "
            "by_role(role) that returns the people with that role; add a test. So you know who is "
            "who: for anything that needs a sign-off, it's Marta, whatever the topic. Dana and "
            "Iker don't approve things."
        ),
        "second": (
            "Refunds over 500 shouldn't go through on their own any more: make refund() in "
            "app/refunds.py send an approval request by email (app.mailer.send) to whoever "
            "approves them, and return 'pending' instead. Add tests."
        ),
        "task": (
            SIGNOFF_RUN + "assert big == 'pending' and sent, (big, sent)\n"
            "assert refund('o-2', 20) != 'pending'\n"
        ),
        "fact": SIGNOFF_RUN + "assert any('marta@example.org' in str(to) for to in sent), sent\n",
    },
}

# The preference of each scene, as the person said it (a substring of `first`).
PRINCIPLE_RULES: dict[str, str] = {
    "p_decide": "any call about what a text is or means goes through judge(), we don't write our "
    "own keyword lists or score cutoffs for that.",
    "p_open": "our fetchers run at full power by default: no robots.txt checks and no rate "
    "limiting or delays, unless a caller explicitly asks for that with a flag.",
    "p_noask": "when something is ambiguous, don't stop to ask me. Pick the option you can "
    "defend, go ahead, and write the choice and why as one line in DECISIONS.md at the repo root.",
    "p_dryrun": "any script that changes data must do nothing unless it's run with --apply; "
    "without the flag it only reports what it would change.",
    "p_es": "anything our users read (error messages, emails, labels) is in Spanish; code, "
    "comments and logs stay in English.",
    "p_flag": "any new behaviour goes in behind an environment flag named FEATURE_<something>, "
    "off by default, so we can turn it on per deployment.",
    "p_json": "every command-line tool in this repo: it prints JSON on stdout and nothing else, "
    "because they're all chained in our pipelines.",
    "p_signoff": "for anything that needs a sign-off, it's Marta, whatever the topic. Dana and "
    "Iker don't approve things.",
}
