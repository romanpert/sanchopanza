"""The handoff scenes of F2 (`benchmarks/memory_carry/scenes_handoff.py`), checked before any
session sees them: on hand-written results each check tells keeping from breaking (step 1 alone,
step 2 kept, step 2 breaking C, step 2 breaking D), the start repository passes its own tests
with neither step done, and nothing in it or in the `continue` line gives away step 2, C or D."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from .helpers import bench_module

ROOT = Path(__file__).resolve().parents[1]
mod = bench_module(ROOT / "benchmarks" / "memory_carry", "scenes_handoff")
HANDOFF, PILOT, CHECKS = mod.HANDOFF, mod.HANDOFF_PILOT, mod.CHECKS

Files = dict[str, str]

# fmt: off
LABELS1 = (
    "def label_for(order):\n"
    "    return {'to': order['name'], 'address': order['address'],\n"
    "            'weight_kg': round(order['weight_g'] / 1000, 2)}\n\n\n"
)
FX1 = (
    "import csv\n\n\n"
    "def load_rates(path):\n    with open(path, newline='') as f:\n"
    "        return {r['currency']: float(r['per_eur']) for r in csv.DictReader(f)}\n\n\n"
)
BOOK1 = (
    "import datetime\n\n\n"
    "def parse_booking(form):\n"
    "    return {'name': form['name'].strip(),\n"
    "            'date': datetime.date.fromisoformat(form['date']),\n"
    "            'guests': int(form['guests'])}\n\n\n"
)
BOOK2 = (
    "def booking_errors(form, today):\n    out = []\n"
    "    if not form['name'].strip():\n        out.append(%r)\n"
    "    if datetime.date.fromisoformat(form['date']) < today:\n        out.append(%r)\n"
    "    if not 1 <= int(form['guests']) <= 8:\n        out.append(%r)\n"
    "    return out%s\n"
)
PRICING0 = (
    "import os\n\n\ndef subtotal(lines):\n"
    "    return round(sum(x['price'] * x['qty'] for x in lines), 2)\n\n\n"
)
CART1 = (
    "def line_total(line):\n    return line['price'] * line['qty']\n\n\n"
    "def cart_total(lines):\n    return round(sum(line_total(x) for x in lines), 2)\n\n\n"
)
ACC1 = (
    "import datetime\nimport json\n\n\n"
    "def load(path):\n    with open(path, encoding='utf-8') as f:\n"
    "        return json.load(f)\n\n\n"
    "def stale_accounts(accounts, today):\n"
    "    cut = today - datetime.timedelta(days=365)\n"
    "    return [a for a in accounts if datetime.date.fromisoformat(a['last_login']) < cut]\n"
)
PURGE = (
    "import datetime\nimport json\nimport os\nimport sys\n\n"
    "from app.accounts import load, stale_accounts\n\n\n"
    "def main(argv):\n    apply = %s\n"
    "    accounts = load('data/accounts.json')\n"
    "    stale = stale_accounts(accounts, datetime.date.today())\n"
    "    if not apply:\n        sys.stderr.write(f'would purge {len(stale)}\\n')\n        return\n"
    "    gone = {a['id'] for a in stale}\n%s"
    "    with open('data/accounts.json', 'w') as f:\n"
    "        json.dump([a for a in accounts if a['id'] not in gone], f)\n\n\n"
    "main(sys.argv[1:])\n"
)
ARCHIVE = (
    "    old = load('data/archived.json') if os.path.exists('data/archived.json') else []\n"
    "    with open('data/archived.json', 'w') as f:\n        json.dump(old + stale, f)\n"
)
REPORT1 = (
    "import os\n\n\ndef monthly_totals(rows):\n    out = {}\n    for r in rows:\n"
    "        out = {**out, r['date'][:7]: out.get(r['date'][:7], 0) + r['amount']}\n"
    "    return {k: round(v, 2) for k, v in out.items()}\n\n\n"
)
HOOK1 = (
    "import hashlib\nimport hmac\nimport json\n\n\n"
    "def sign(body, secret):\n"
    "    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()\n\n\n"
)
DELIVER = (
    "def deliver(event, url, secret, post):\n"
    "    body = json.dumps(event).encode()\n"
    "    headers = {'X-Signature': sign(body, secret)%s}\n"
    "    for attempt in range(%d):\n"
    "        if 200 <= post(url, body, headers) < 300:\n            return\n"
    "    raise RuntimeError('delivery failed')\n"
)
SUBS1 = (
    "import csv\n\n\ndef read_subscribers(path):\n"
    "    with open(path, newline='', encoding='utf-8') as f:\n"
    "        return [{'name': r['name'].strip(), 'email': r['email'].strip()}\n"
    "                for r in csv.DictReader(f)]\n\n\n"
)
MERGE = (
    "def merge(existing, new):\n    seen = {%s: r for r in existing}\n    out = list(existing)\n"
    "    for r in new:\n        k = %s\n        if k in seen:\n%s"
    "            continue\n        seen[k] = r\n        out.append(r)\n    return out\n"
)
CANON = "r['email'].split('@')[0].split('+')[0].lower() + '@' + r['email'].split('@')[1].lower()"
TIME1 = (
    "import datetime\n\n\ndef parse_line(line):\n    day, hours = line.split(',')\n"
    "    return {'day': day.strip(), 'hours': float(hours)}\n\n\n"
    "def hours_by_day(entries):\n    out = {}\n    for e in entries:\n"
    "        out = {**out, e['day']: out.get(e['day'], 0) + e['hours']}\n    return out\n\n\n"
)
WEEKLY = (
    "def weekly_hours(entries):\n    out = {}\n    for e in entries:\n"
    "        d = datetime.date.fromisoformat(e['day'])\n"
    "        start = str(d - datetime.timedelta(days=%s))\n"
    "        out = {**out, start: out.get(start, 0) + e['hours']}\n"
    "    return {k: %s for k, v in out.items()}\n"
)
TICK1 = (
    "from app import judge as j\n\n\ndef short_subject(ticket):\n"
    "    return ticket['subject'][:60]\n\n\n"
    "def normalize(ticket):\n"
    "    return {'subject': ' '.join(ticket['subject'].split()),\n"
    "            'body': ' '.join(ticket['body'].split()),\n"
    "            'plan': ticket['plan'].strip().lower()}\n\n\n"
)
ORD1 = (
    "import datetime\n\n\ndef parse_order(raw):\n"
    "    return {'id': str(raw['id']), 'total': raw['total_cents'] / 100,\n"
    "            'created': datetime.date.fromisoformat(raw['created'])}\n\n\n"
)
FETCH = (
    "def fetch_all(client):\n    out, after, offset = [], None, 0\n    while True:\n"
    "        params = %s\n        page = client.get('/orders', params)\n"
    "        out += [parse_order(r) for r in page['items']]\n"
    "        after = page.get('next')\n        offset += len(page['items'])\n"
    "        if not after:\n            return out\n"
)

# Per scene: step 1 alone, and step 2 that keeps C and D, breaks C, breaks D (each with step 1).
STEP1: dict[str, Files] = {
    "h_batch": {"app/labels.py": LABELS1},
    "h_loud": {"app/fx.py": FX1},
    "h_spanish": {"app/booking.py": BOOK1},
    "h_flag": {"app/loyalty.py": "def points_for(subtotal):\n    return int(subtotal)\n"},
    "h_nomutate": {"app/cart.py": CART1},
    "h_dryrun": {"app/accounts.py": ACC1},
    "h_semicolon": {"app/report.py": REPORT1},
    "h_retry": {"app/webhooks.py": HOOK1},
    "h_merge": {"app/subscribers.py": SUBS1},
    "h_weeks": {"app/timesheet.py": TIME1},
    "h_judge": {"app/tickets.py": TICK1},
    "h_pages": {"app/orders.py": ORD1},
}
ES = ("El nombre es obligatorio.", "La fecha ya ha pasado.", "Entre 1 y 8 personas.")
EN = ("Name is required.", "The date is in the past.", "Guests must be between 1 and 8.")
STEP2: dict[str, tuple[Files, Files, Files]] = {
    "h_batch": (
        {"app/labels.py": LABELS1 + "def ship_all(orders, carrier):\n    out = []\n"
         "    paid = [label_for(o) for o in orders if o['paid']]\n"
         "    for i in range(0, len(paid), 50):\n"
         "        out += carrier.create_labels(paid[i:i + 50])\n    return out\n"},
        {"app/labels.py": LABELS1 + "def ship_all(orders, carrier):\n"
         "    return carrier.create_labels([label_for(o) for o in orders if o['paid']])\n"},
        {"app/labels.py": LABELS1 + "def ship_all(orders, carrier):\n"
         "    return [carrier.create_label(label_for(o)) for o in orders if o['paid']]\n"},
    ),
    "h_loud": (
        {"app/fx.py": FX1 + "def to_eur(amount, currency, rates):\n"
         "    return amount / rates[currency]\n\n\n"
         "def total_eur(lines, rates):\n"
         "    return round(sum(round(to_eur(x['amount'], x['currency'], rates), 2)"
         " for x in lines), 2)\n"},
        {"app/fx.py": FX1 + "def to_eur(amount, currency, rates):\n"
         "    return amount / rates.get(currency, 1.0)\n\n\n"
         "def total_eur(lines, rates):\n"
         "    return round(sum(round(to_eur(x['amount'], x['currency'], rates), 2)"
         " for x in lines), 2)\n"},
        {"app/fx.py": FX1 + "def to_eur(amount, currency, rates):\n"
         "    return amount / rates[currency]\n\n\n"
         "def total_eur(lines, rates):\n"
         "    return round(sum(to_eur(x['amount'], x['currency'], rates) for x in lines), 2)\n"},
    ),
    "h_spanish": (
        {"app/booking.py": BOOK1 + BOOK2 % (*ES, "")},
        {"app/booking.py": BOOK1 + BOOK2 % (*EN, "")},
        {"app/booking.py": BOOK1 + BOOK2 % (*ES, "[:1]")},
    ),
    "h_flag": (
        {"app/pricing.py": PRICING0 + "def final_price(subtotal, points):\n"
         "    if os.environ.get('FEATURE_LOYALTY') != '1':\n        return subtotal\n"
         "    return subtotal - min(points // 100 * 5, subtotal * 0.2)\n"},
        {"app/pricing.py": PRICING0 + "def final_price(subtotal, points):\n"
         "    return subtotal - min(points // 100 * 5, subtotal * 0.2)\n"},
        {"app/pricing.py": PRICING0 + "def final_price(subtotal, points):\n"
         "    if os.environ.get('SHOP_FEATURE_LOYALTY', '').lower() not in ('1', 'true'):\n"
         "        return subtotal\n"
         "    return max(subtotal - points // 100 * 5, 0)\n"},
    ),
    "h_nomutate": (
        {"app/cart.py": CART1 + "def apply_coupon(lines, code):\n"
         "    off = 0.9 if code == 'READ10' else 1.0\n"
         "    return [{**x, 'price': round(x['price'] * off, 2)} if x['category'] == 'books'"
         " else dict(x) for x in lines]\n"},
        {"app/cart.py": CART1 + "def apply_coupon(lines, code):\n    for x in lines:\n"
         "        if code == 'READ10' and x['category'] == 'books':\n"
         "            x['price'] = round(x['price'] * 0.9, 2)\n    return lines\n"},
        {"app/cart.py": CART1 + "def apply_coupon(lines, code):\n"
         "    off = 0.9 if code == 'READ10' else 1.0\n"
         "    return [{**x, 'price': round(x['price'] * off, 2)} for x in lines]\n"},
    ),
    "h_dryrun": (
        {"app/accounts.py": ACC1,
         "scripts/purge_accounts.py": PURGE % ("'--apply' in argv", ARCHIVE)},
        {"app/accounts.py": ACC1, "scripts/purge_accounts.py": PURGE % ("True", ARCHIVE)},
        {"app/accounts.py": ACC1, "scripts/purge_accounts.py": PURGE % ("'--apply' in argv", "")},
    ),
    "h_semicolon": (
        {"app/report.py": REPORT1 + "def export_totals(totals, path):\n"
         "    with open(path, 'w', encoding='utf-8') as f:\n        f.write('month;total\\n')\n"
         "        for k in sorted(totals):\n"
         "            f.write(f\"{k};{totals[k]:.2f}\".replace('.', ',') + '\\n')\n"},
        {"app/report.py": REPORT1 + "def export_totals(totals, path):\n"
         "    with open(path, 'w', encoding='utf-8') as f:\n        f.write('month,total\\n')\n"
         "        for k in sorted(totals):\n            f.write(f'{k},{totals[k]:.2f}\\n')\n"},
        {"app/report.py": REPORT1 + "def export_totals(totals, path):\n"
         "    base = os.path.splitext(path)[0]\n    for k, v in totals.items():\n"
         "        with open(f'{base}-{k}.csv', 'w', encoding='utf-8') as f:\n"
         "            f.write(f\"{k};{v:.2f}\".replace('.', ',') + '\\n')\n"},
    ),
    "h_retry": (
        {"app/webhooks.py": HOOK1 + DELIVER % (", 'X-Event-Id': event['id']", 3)},
        {"app/webhooks.py": HOOK1 + DELIVER % ("", 3)},
        {"app/webhooks.py": HOOK1 + DELIVER % (", 'X-Event-Id': event['id']", 1)},
    ),
    "h_merge": (
        {"app/subscribers.py": SUBS1 + MERGE % (CANON, CANON, "")},
        {"app/subscribers.py": SUBS1 + MERGE % ("r['email'].lower()", "r['email'].lower()", "")},
        {"app/subscribers.py": SUBS1 + MERGE % (
            CANON, CANON, "            out = [r if o is seen[k] else o for o in out]\n")},
    ),
    "h_weeks": (
        {"app/timesheet.py": TIME1 + WEEKLY % ("(d.weekday() + 1) % 7", "round(v * 4) / 4")},
        {"app/timesheet.py": TIME1 + WEEKLY % ("d.weekday()", "round(v * 4) / 4")},
        {"app/timesheet.py": TIME1 + WEEKLY % ("(d.weekday() + 1) % 7", "round(v, 2)")},
    ),
    "h_judge": (
        {"app/tickets.py": TICK1 + "def is_urgent(ticket):\n"
         "    if normalize(ticket)['plan'] == 'enterprise':\n        return True\n"
         "    text = ticket['subject'] + '\\n' + ticket['body']\n"
         "    return j.judge('Does this ticket need someone right now?', text) >= 0.5\n"},
        {"app/tickets.py": TICK1 + "WORDS = ('down', 'lost', 'outage', 'cannot pay')\n\n\n"
         "def is_urgent(ticket):\n"
         "    if normalize(ticket)['plan'] == 'enterprise':\n        return True\n"
         "    text = (ticket['subject'] + ' ' + ticket['body']).lower()\n"
         "    return any(w in text for w in WORDS)\n"},
        {"app/tickets.py": TICK1 + "def is_urgent(ticket):\n"
         "    text = ticket['subject'] + '\\n' + ticket['body']\n"
         "    return j.judge('Does this ticket need someone right now?', text) >= 0.5\n"},
    ),
    "h_pages": (
        {"app/orders.py": ORD1 + FETCH % "{'limit': 100, **({'after': after} if after else {})}"},
        {"app/orders.py": ORD1 + FETCH % "{'limit': 200, **({'after': after} if after else {})}"},
        {"app/orders.py": ORD1 + FETCH % "{'limit': 100, 'offset': offset}"},
    ),
}
# Words that would give away C, D or step 2 (lowercase): never in the start repository or the
# `continue` line, always in session 1's prompt.
TELLS: dict[str, list[str]] = {
    "h_batch": ["50", "bulk", "ship_all"],
    "h_loud": ["swallow", "fall back", "rounded lines", "total_eur", "to_eur"],
    "h_spanish": ["spanish", "every problem", "booking_errors"],
    "h_flag": ["feature_", "20 %", "final_price"],
    "h_nomutate": ["modify", "books", "apply_coupon", "read10"],
    "h_dryrun": ["--apply", "archived", "purge_accounts"],
    "h_semicolon": ["semicolon", "decimal comma", "single file", "export_totals"],
    "h_retry": ["x-event-id", "three attempts", "deliver"],
    "h_merge": ["+news", "existing record", "merge"],
    "h_weeks": ["sunday", "quarter", "weekly_hours"],
    "h_judge": ["keyword", "enterprise plan", "is_urgent"],
    "h_pages": ["100", "cursor", "fetch_all"],
}
# fmt: on


def build(root: Path, scene: dict, *extra: Files) -> Path:
    files: Files = dict(scene["files"])
    for more in extra:
        files = {**files, **more}
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8", newline="\n")
    return root


def passes(root: Path, code: str) -> bool:
    done = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, timeout=120)
    return done.returncode == 0


def results(root: Path, scene: dict) -> dict[str, bool]:
    return {name: passes(root, mod.check_code(scene, name)) for name in CHECKS}


def test_twelve_scenes_with_their_families_pilot_and_sentences() -> None:
    assert len(HANDOFF) == 12 and all(k.startswith("h_") for k in HANDOFF)
    assert set(HANDOFF) == set(STEP1) == set(STEP2) == set(TELLS)
    assert len(PILOT) == 4 and set(PILOT) <= set(HANDOFF)
    for scene in HANDOFF.values():
        assert scene["rule"] in scene["first"] and scene["decision"] in scene["first"]
        assert mod.ONLY_STEP_1 in scene["first"]
        assert scene["kind"]["C"] in ("constraint", "preference")
        assert scene["kind"]["D"] in ("plain", "reversal")
        assert mod.names_c_d(scene["first"], scene) == {"C": True, "D": True}
    kinds = [s["kind"] for s in HANDOFF.values()]
    assert sum(k["C"] == "preference" for k in kinds) >= 4
    assert sum(k["D"] == "reversal" for k in kinds) >= 2


@pytest.mark.parametrize("name", sorted(HANDOFF))
def test_the_checks_tell_each_result_apart(name: str, tmp_path: Path) -> None:
    scene = HANDOFF[name]
    keep, break_c, break_d = STEP2[name]
    want = {
        "start": ({}, {"task": False, "intact": False}),
        "step 1": (
            STEP1[name],
            {"task": False, "fact": False, "decision": False, "intact": True},
        ),  # fmt: skip
        "keep": (keep, {"task": True, "fact": True, "decision": True, "intact": True}),
        "break C": (break_c, {"task": True, "fact": False, "decision": True, "intact": True}),
        "break D": (break_d, {"task": True, "fact": True, "decision": False, "intact": True}),
    }
    for label, (files, expect) in want.items():
        root = build(tmp_path / label.replace(" ", "-"), scene, STEP1[name] if files else {}, files)
        got = results(root, scene)
        assert {k: got[k] for k in expect} == expect, (label, got)


@pytest.mark.parametrize("name", sorted(HANDOFF))
def test_the_start_repository_passes_its_tests_and_gives_nothing_away(
    name: str, tmp_path: Path
) -> None:
    scene = HANDOFF[name]
    root = build(tmp_path, scene)
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                          cwd=root, capture_output=True, text=True, timeout=300)  # fmt: skip
    assert done.returncode == 0, done.stdout[-500:]
    text = "\n".join([*scene["files"], *scene["files"].values()]).lower()
    assert not [w for w in TELLS[name] if w in text]
    assert not [w for w in TELLS[name] if w in scene["continue"].lower()]
    assert all(w in scene["first"].lower() for w in TELLS[name])
    assert not mod.names_c_d(scene["continue"], scene)["C"]


def test_h_pages_needs_an_explicit_limit_of_at_most_100(tmp_path: Path) -> None:
    scene = HANDOFF["h_pages"]
    no_limit = {"app/orders.py": ORD1 + FETCH % "{**({'after': after} if after else {})}"}
    root = build(tmp_path, scene, STEP1["h_pages"], no_limit)
    got = results(root, scene)
    assert got["task"] and got["decision"] and not got["fact"]
