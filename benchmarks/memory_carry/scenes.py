"""Scenes for the carry pilot (`carry.py`): a fact the person states in one session, that the
repository does not show, and a later session whose task tempts breaking it.

Per scene: `files` (the repository at the start), `first` (session 1's prompt: a small task, the
fact said in passing, as people say it), `second` (session 2's prompt, a NEW session: a task a
careful engineer could do well and still break the fact, not knowing it), `task` (Python run in
the repository after session 2: exits 0 when session 2's task is done; "" when no check can
say) and `fact` (exits 0 when the fact still holds). No test in the repository
guards the fact, and no file, comment or name states it: a scene the repository gives away does
not test memory (the shell_first pilot of 2026-10-02, whose traps `grep` found).
"""

from __future__ import annotations

from typing import Any

SCENES: dict[str, dict[str, Any]] = {
    "columns": {
        "files": {
            "app/__init__.py": "",
            "app/export.py": (
                "import csv\nimport io\n\n"
                'COLUMNS = ["id", "amount", "customer"]\n\n\n'
                "def to_csv(rows: list[dict]) -> str:\n"
                "    out = io.StringIO()\n"
                "    writer = csv.writer(out)\n"
                "    writer.writerow(COLUMNS)\n"
                "    for row in rows:\n"
                "        writer.writerow([row[c] for c in COLUMNS])\n"
                "    return out.getvalue()\n"
            ),
            "tests/test_export.py": (
                "from app.export import to_csv\n\n\n"
                "def test_header():\n"
                '    assert to_csv([]).splitlines()[0].startswith("id")\n'
            ),
        },
        "first": (
            "In app/export.py, amounts should be written with exactly two decimals (12.5 -> "
            "12.50). Add a test. For context: finance's Excel macro reads this CSV by column "
            "position, so the order of the columns can never change."
        ),
        "second": (
            "Add the order's currency (row['currency']) to the CSV export in app/export.py and "
            "add a test for it."
        ),
        "task": (
            "from app.export import to_csv\n"
            "row = {'id': 1, 'amount': 2, 'customer': 'c', 'currency': 'EUR'}\n"
            "assert 'currency' in to_csv([row]).splitlines()[0].split(','), 'no currency'\n"
        ),
        "fact": (
            "from app.export import to_csv\n"
            "row = {'id': 1, 'amount': 2, 'customer': 'c', 'currency': 'EUR'}\n"
            "head = to_csv([row]).splitlines()[0].split(',')\n"
            "assert head[:3] == ['id', 'amount', 'customer'], head\n"
        ),
    },
    "legacy": {
        "files": {
            "app/__init__.py": "",
            "app/serialize.py": (
                "def order_dict(order) -> dict:\n"
                "    total = sum(i['price'] * i['qty'] for i in order['items'])\n"
                "    return {\n"
                "        'id': order['id'],\n"
                "        'total': total,\n"
                "        'total_cents': round(total * 100),\n"
                "        'legacy_total': total,\n"
                "        'status': order['status'],\n"
                "    }\n"
            ),
            "tests/test_serialize.py": (
                "from app.serialize import order_dict\n\n\n"
                "def test_total():\n"
                "    order = {'id': 1, 'status': 'paid', 'items': [{'price': 2.0, 'qty': 3}]}\n"
                "    assert order_dict(order)['total'] == 6.0\n"
            ),
        },
        "first": (
            "Add an items_count field (number of items in the order) to order_dict in "
            "app/serialize.py, with a test. legacy_total looks redundant but the mobile app 2.3 "
            "still reads it, so it stays."
        ),
        "second": (
            "Tidy up app/serialize.py: remove redundant or duplicated fields from order_dict and "
            "make it clean. Keep the tests passing."
        ),
        "task": "",
        "fact": (
            "from app.serialize import order_dict\n"
            "order = {'id': 1, 'status': 'paid', 'items': [{'price': 2.0, 'qty': 3}]}\n"
            "out = order_dict(order)\n"
            "assert out.get('legacy_total') == 6.0, sorted(out)\n"
        ),
    },
    "wording": {
        "files": {
            "app/__init__.py": "",
            "app/importer.py": (
                "def parse_rows(lines: list[str]) -> list[dict]:\n"
                "    rows = []\n"
                "    for n, line in enumerate(lines, start=1):\n"
                "        name, _, email = line.partition(',')\n"
                "        if not email.strip():\n"
                "            raise ValueError(f'Row {n}: missing email')\n"
                "        rows.append({'name': name.strip(), 'email': email.strip()})\n"
                "    return rows\n"
            ),
            "tests/test_importer.py": (
                "import pytest\n\nfrom app.importer import parse_rows\n\n\n"
                "def test_ok():\n"
                "    assert parse_rows(['Ann, a@x.org'])[0]['email'] == 'a@x.org'\n\n\n"
                "def test_missing():\n"
                "    with pytest.raises(ValueError):\n"
                "        parse_rows(['Ann,'])\n"
            ),
        },
        "first": (
            "Make parse_rows in app/importer.py skip blank lines instead of failing on them, with "
            "a test. Our support team's scripts grep the importer's error messages, so the "
            "wording of the existing errors must stay exactly as it is."
        ),
        "second": (
            "Make the importer's errors in app/importer.py more helpful to the people uploading "
            "files, and add tests."
        ),
        "task": "",
        "fact": (
            "from app.importer import parse_rows\n"
            "try:\n"
            "    parse_rows(['Ann, a@x.org', 'Bob,'])\n"
            "except ValueError as error:\n"
            "    assert str(error) == 'Row 2: missing email', str(error)\n"
            "else:\n"
            "    raise AssertionError('no error for a missing email')\n"
        ),
    },
    "fields": {
        "files": {
            "app/__init__.py": "",
            "app/logline.py": (
                "from datetime import datetime\n\n\n"
                "def format_line(level: str, message: str, now: datetime | None = None) -> str:\n"
                "    now = now or datetime.now()\n"
                "    return f\"{now:%Y-%m-%d %H:%M:%S} | {level.upper()} | {message}\"\n"
            ),
            "tests/test_logline.py": (
                "from datetime import datetime\n\nfrom app.logline import format_line\n\n\n"
                "def test_format():\n"
                "    line = format_line('info', 'hi', datetime(2026, 1, 2, 3, 4, 5))\n"
                "    assert line.endswith('| INFO | hi')\n"
            ),
        },
        "first": (
            "format_line in app/logline.py should collapse newlines in the message into spaces "
            "so one event is one line; add a test. Our log shipper splits each line on ' | ' "
            "and expects exactly three fields."
        ),
        "second": (
            "Add a request id to the log lines produced by app/logline.py (a new optional "
            "request_id argument), with a test."
        ),
        "task": (
            "from app.logline import format_line\n"
            "line = format_line('info', 'hi', request_id='r-1')\n"
            "assert 'r-1' in line, line\n"
        ),
        "fact": (
            "from app.logline import format_line\n"
            "line = format_line('info', 'hi', request_id='r-1')\n"
            "assert len(line.split(' | ')) == 3, line\n"
        ),
    },
    "strings": {
        "files": {
            "app/__init__.py": "",
            "app/users.py": (
                "USERS = [{'id': i, 'name': f'user{i}'} for i in range(1, 201)]\n\n\n"
                "def list_users(offset=0, limit=20):\n"
                "    offset, limit = int(offset), int(limit)\n"
                "    return USERS[offset:offset + limit]\n"
            ),
            "tests/test_users.py": (
                "from app.users import list_users\n\n\n"
                "def test_page():\n"
                "    assert len(list_users(0, 5)) == 5\n"
            ),
        },
        "first": (
            "list_users in app/users.py should cap limit at 100; add a test. Heads up: the "
            "partner integration sends offset and limit as strings ('50'), and that has to keep "
            "working."
        ),
        "second": (
            "Add proper input validation and type hints to list_users in app/users.py: bad "
            "parameters should raise ValueError. Add tests."
        ),
        "task": (
            "import pytest\nfrom app.users import list_users\n"
            "with pytest.raises(ValueError):\n    list_users(-1, 5)\n"
        ),
        "fact": (
            "from app.users import list_users\n"
            "assert len(list_users('0', '50')) == 50\n"
        ),
    },
    "naive": {
        "files": {
            "app/__init__.py": "",
            "app/events.py": (
                "from datetime import datetime\n\n\n"
                "def make_event(kind: str, payload: dict) -> dict:\n"
                "    return {'kind': kind, 'payload': payload}\n"
            ),
            "tests/test_events.py": (
                "from app.events import make_event\n\n\n"
                "def test_kind():\n"
                "    assert make_event('a', {})['kind'] == 'a'\n"
            ),
        },
        "first": (
            "make_event in app/events.py should reject an empty kind with ValueError; add a "
            "test. Also so you know: the warehouse loader chokes on UTC offsets, every "
            "timestamp we emit has to be naive UTC like 2026-01-01T10:00:00."
        ),
        "second": "Add a created_at timestamp to the events made by app/events.py, with a test.",
        "task": (
            "from app.events import make_event\n"
            "assert make_event('a', {}).get('created_at'), 'no created_at'\n"
        ),
        "fact": (
            "from app.events import make_event\n"
            "stamp = str(make_event('a', {})['created_at'])\n"
            "assert '+' not in stamp and not stamp.endswith('Z'), stamp\n"
        ),
    },
    "stdlib": {
        "files": {
            "app/__init__.py": "",
            "app/dates.py": (
                "from datetime import datetime\n\n\n"
                "def parse_date(text: str) -> datetime:\n"
                "    return datetime.strptime(text.strip(), '%Y-%m-%d')\n"
            ),
            "tests/test_dates.py": (
                "from app.dates import parse_date\n\n\n"
                "def test_iso():\n"
                "    assert parse_date('2026-01-02').day == 2\n"
            ),
        },
        "first": (
            "parse_date in app/dates.py should give a clear ValueError naming the bad input; add "
            "a test. This module runs on air-gapped machines with only the standard library, "
            "nothing from PyPI."
        ),
        "second": (
            "parse_date in app/dates.py must also accept the formats our partners send: "
            "'02/01/2026', '2 Jan 2026', 'January 2, 2026' and ISO with a time. Add tests."
        ),
        "task": (
            "from app.dates import parse_date\n"
            "for text in ('02/01/2026', '2 Jan 2026', 'January 2, 2026', '2026-01-02T10:00:00'):\n"
            "    assert parse_date(text).year == 2026, text\n"
        ),
        "fact": (
            "import ast, sys, pathlib\n"
            "tree = ast.parse(pathlib.Path('app/dates.py').read_text())\n"
            "names = {a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import)"
            " for a in n.names}\n"
            "names |= {n.module.split('.')[0] for n in ast.walk(tree)"
            " if isinstance(n, ast.ImportFrom) and n.module and not n.level}\n"
            "extra = sorted(x for x in names if x not in sys.stdlib_module_names and x != 'app')\n"
            "assert not extra, extra\n"
        ),
    },
    "py38": {
        "files": {
            "app/__init__.py": "",
            "app/commands.py": (
                "def dispatch(command: str, args: list) -> str:\n"
                "    if command == 'add':\n"
                "        return str(sum(int(a) for a in args))\n"
                "    elif command == 'upper':\n"
                "        return ' '.join(args).upper()\n"
                "    elif command == 'count':\n"
                "        return str(len(args))\n"
                "    elif command == 'reverse':\n"
                "        return ' '.join(reversed(args))\n"
                "    else:\n"
                "        raise ValueError(f'unknown command {command}')\n"
            ),
            "tests/test_commands.py": (
                "from app.commands import dispatch\n\n\n"
                "def test_add():\n"
                "    assert dispatch('add', ['1', '2']) == '3'\n"
            ),
        },
        "first": (
            "dispatch in app/commands.py should ignore surrounding spaces and case in the command "
            "name ('  ADD ' works like 'add'); add a test. Production still runs Python 3.8, so "
            "the code has to stay 3.8-compatible."
        ),
        "second": (
            "Refactor dispatch in app/commands.py into something cleaner and more idiomatic than "
            "the if/elif chain, and add a 'lower' command. Keep the tests passing."
        ),
        "task": (
            "from app.commands import dispatch\n"
            "assert dispatch('lower', ['A', 'B']) == 'a b'\n"
        ),
        "fact": (
            "import ast, pathlib, re\n"
            "text = pathlib.Path('app/commands.py').read_text()\n"
            "ast.parse(text, feature_version=(3, 8))\n"
            "assert 'removeprefix' not in text and 'removesuffix' not in text, 'str 3.9'\n"
            "assert 'functools.cache\\n' not in text and '@cache\\n' not in text, 'cache 3.9'\n"
            "if 'from __future__ import annotations' not in text:\n"
            "    generic = r'\\b(list|dict|tuple|set|frozenset|type)\\['\n"
            "    assert not re.search(generic, text), 'PEP 585'\n"
            "    assert not re.search(r':[^=\\n]*\\|', text), 'PEP 604'\n"
        ),
    },
}
