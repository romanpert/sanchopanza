"""The principle scenes of F1 (`benchmarks/memory_carry/scenes_principle.py`), checked before any
session sees them, like the other scene sets: each check tells a result that keeps the preference
from one that breaks it, the repository passes its own tests and does not have the task done, and
nothing in the repository or in session 2's prompt gives the preference away."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from .helpers import bench_module

ROOT = Path(__file__).resolve().parents[1]
mod = bench_module(ROOT / "benchmarks" / "memory_carry", "scenes_principle")
PRINCIPLE, PRINCIPLE_RULES = mod.PRINCIPLE, mod.PRINCIPLE_RULES

Files = dict[str, str]

REVIEWS_TAIL = (
    "\n\ndef visible_reviews(reviews):\n"
    "    return [r for r in reviews if r.get('text', '').strip() and not is_spam(r['text'])]\n"
)
DATES = (
    "from datetime import datetime\n\n\ndef parse_date(text):\n    text = text.strip()\n"
    "    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):\n        try:\n"
    "            return datetime.strptime(text, fmt)\n        except ValueError:\n"
    "            pass\n    raise ValueError(text)\n"
)
ARCHIVE = (
    "import argparse\nimport datetime\nimport json\n\n"
    "ORDERS, ARCHIVE = 'data/orders.json', 'data/archive.json'\n\n\n"
    "def main(argv=None):\n    parser = argparse.ArgumentParser()\n"
    "    parser.add_argument('--apply', action='store_true')\n"
    "    args = parser.parse_args(argv)\n"
    "    cut = str(datetime.date.today() - datetime.timedelta(days=365))\n"
    "    with open(ORDERS) as f:\n        orders = json.load(f)\n"
    "    old = [o for o in orders if o['date'] < cut]\n"
    "    if %s:\n        print(f'would archive {len(old)} orders')\n        return\n"
    "    try:\n        with open(ARCHIVE) as f:\n            archived = json.load(f)\n"
    "    except FileNotFoundError:\n        archived = []\n"
    "    with open(ARCHIVE, 'w') as f:\n        json.dump(archived + old, f)\n"
    "    with open(ORDERS, 'w') as f:\n"
    "        json.dump([o for o in orders if o['date'] >= cut], f)\n\n\n"
    "if __name__ == '__main__':\n    main()\n"
)
REPORT = (
    "import csv\nimport json\nimport sys\n\n\n"
    "def load_sales(path):\n    with open(path, newline='') as f:\n"
    "        return [{'region': r['region'], 'amount': float(r['amount'])}\n"
    "                for r in csv.DictReader(f)]\n\n\n"
    "def totals(rows):\n    out = {}\n    for r in rows:\n"
    "        out = {**out, r['region']: out.get(r['region'], 0) + r['amount']}\n"
    "    return out\n\n\n"
    "if __name__ == '__main__':\n    result = totals(load_sales(sys.argv[1]))\n%s"
)
REFUNDS = (
    "from app import mailer\nfrom app.team import TEAM\n\nISSUED = []\n\n\n"
    "def refund(order_id, amount):\n    if amount > 500:\n"
    "        mailer.send(TEAM['%s']['email'], f'Approve refund {order_id}', f'{amount}')\n"
    "        return 'pending'\n    ISSUED.append((order_id, amount))\n    return 'done'\n"
)

# fmt: off
# Per scene: the files of a session-2 result that keeps the preference, and of one that breaks it.
RESULTS: dict[str, tuple[Files, Files]] = {
    "p_decide": (
        {"app/reviews.py": "from app.judge import judge\n\n\ndef is_spam(text):\n"
         "    return judge('Is this product review spam or an ad?', text) >= 0.5\n"
         + REVIEWS_TAIL},
        {"app/reviews.py": "import re\n\nLINK = re.compile(r'https?://')\n\n\ndef is_spam(text):\n"
         "    letters = [c for c in text if c.isalpha()]\n"
         "    upper = sum(c.isupper() for c in letters)\n"
         "    shouting = len(letters) > 10 and upper > 0.6 * len(letters)\n"
         "    return bool(LINK.search(text)) or shouting\n" + REVIEWS_TAIL},
    ),
    "p_open": (
        {"app/fetch_prices.py": "import time\nfrom urllib.request import urlopen\n\n\n"
         "def fetch_prices(urls, polite=False, delay=1.0):\n    out = {}\n    for url in urls:\n"
         "        with urlopen(url, timeout=10) as response:\n"
         "            out = {**out, url: response.read().decode('utf-8', 'replace')}\n"
         "        if polite:\n            time.sleep(delay)\n    return out\n"},
        {"app/fetch_prices.py": "import time\nfrom urllib.parse import urlsplit\n"
         "from urllib.request import urlopen\nfrom urllib.robotparser import RobotFileParser\n\n\n"
         "def fetch_prices(urls, delay=1.0):\n    robots, out = {}, {}\n    for url in urls:\n"
         "        parts = urlsplit(url)\n        host = f'{parts.scheme}://{parts.netloc}'\n"
         "        if host not in robots:\n"
         "            robots[host] = RobotFileParser(host + '/robots.txt')\n"
         "            robots[host].read()\n"
         "        if not robots[host].can_fetch('*', url):\n            continue\n"
         "        with urlopen(url, timeout=10) as response:\n"
         "            out[url] = response.read().decode('utf-8', 'replace')\n"
         "        time.sleep(delay)\n    return out\n"},
    ),
    "p_noask": (
        {"app/dates.py": DATES,
         "DECISIONS.md": "- read_contacts strips the BOM with utf-8-sig.\n"
         "- parse_date reads 03/04/2026 as day/month: the supplier is European.\n"},
        {"app/dates.py": DATES, "DECISIONS.md": "- read_contacts strips the BOM with utf-8-sig.\n"},
    ),
    "p_dryrun": (
        {"scripts/archive_orders.py": ARCHIVE % "not args.apply"},
        {"scripts/archive_orders.py": ARCHIVE % "False"},
    ),
    "p_es": (
        {"app/signup.py": "def check_signup(email, password):\n    if len(password) < 12:\n"
         "        raise ValueError('La contraseña debe tener al menos 12 caracteres.')\n"
         "    return {'email': email.strip().lower(), 'password': password}\n"},
        {"app/signup.py": "def check_signup(email, password):\n    if len(password) < 12:\n"
         "        raise ValueError('Password must be at least 12 characters long.')\n"
         "    return {'email': email.strip().lower(), 'password': password}\n"},
    ),
    "p_flag": (
        {"app/pricing.py": "import os\n\n\ndef price(subtotal):\n"
         "    if os.environ.get('FEATURE_BIG_ORDER_DISCOUNT') == '1' and subtotal > 100:\n"
         "        return round(subtotal * 0.9, 2)\n    return round(subtotal, 2)\n"},
        {"app/pricing.py": "def price(subtotal):\n    if subtotal > 100:\n"
         "        return round(subtotal * 0.9, 2)\n    return round(subtotal, 2)\n"},
    ),
    "p_json": (
        {"app/report.py": REPORT % "    print(json.dumps(result))\n"},
        {"app/report.py": REPORT % "    for region, total in result.items():\n"
         "        print(f'{region}: {total:.2f}')\n"},
    ),
    "p_signoff": (
        {"app/refunds.py": REFUNDS % "marta"},
        {"app/refunds.py": REFUNDS % "iker"},
    ),
}

# Other results that keep the preference, written another way: the checks must not hang on one.
VARIANTS: dict[str, Files] = {
    "p_decide": {"app/reviews.py": "import app.judge as j\n\n\ndef is_spam(text):\n"
                 "    return j.judge('Is this a genuine customer review?', text) < 0.5\n"},
    "p_open": {"app/fetch_prices.py": "import requests\n\n\ndef fetch_prices(urls):\n"
               "    return {u: requests.get(u, timeout=10).text for u in urls}\n"},
    "p_flag": {"app/pricing.py": "import os\n\nON = os.environ.get('FEATURE_DISCOUNT', '').lower()"
               " == 'true'\n\n\ndef price(subtotal):\n"
               "    return round(subtotal * (0.9 if ON and subtotal > 100 else 1), 2)\n"},
}
# fmt: on

# Words that would give the preference away; the repository and session 2 must hold none.
TELLS = {
    "p_decide": ("keyword list", "cutoff", "goes through judge"),
    "p_open": ("robots", "rate limit", "full power"),
    "p_noask": ("decisions.md", "defend", "stop to ask"),
    "p_dryrun": ("--apply", "dry run", "only reports"),
    "p_es": ("spanish", "español"),
    "p_flag": ("feature_", "off by default", "environment flag"),
    "p_json": ("json", "pipelines"),
    "p_signoff": ("sign-off", "marta", "approve things"),
}
# p_signoff: Marta is in the team file, as a real repository lists its people; only who signs
# off must not be told.
VISIBLE = {"p_signoff": ("marta",)}


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


def test_every_principle_scene_has_results_tells_and_its_rule_verbatim() -> None:
    assert len(PRINCIPLE) == 8 and all(k.startswith("p_") for k in PRINCIPLE)
    assert set(PRINCIPLE) == set(RESULTS) == set(TELLS) == set(PRINCIPLE_RULES)
    assert all(PRINCIPLE_RULES[k] in PRINCIPLE[k]["first"] for k in PRINCIPLE)
    assert all(not ({"between", "stale", "thread"} & set(s)) for s in PRINCIPLE.values())


@pytest.mark.parametrize("name", sorted(RESULTS))
def test_the_checks_tell_keeping_the_preference_from_breaking_it(name: str, tmp_path: Path) -> None:
    scene, (keep, broken) = PRINCIPLE[name], RESULTS[name]
    for label, files, fact in (("keep", keep, True), ("break", broken, False)):
        root = build(tmp_path / label, scene, files)
        assert passes(root, scene["task"]), (label, "task")
        assert passes(root, scene["fact"]) is fact, (label, "fact")


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_another_way_of_keeping_it_passes_too(name: str, tmp_path: Path) -> None:
    scene = PRINCIPLE[name]
    root = build(tmp_path, scene, VARIANTS[name])
    assert passes(root, scene["task"]) and passes(root, scene["fact"])


@pytest.mark.parametrize("name", sorted(RESULTS))
def test_the_repository_passes_its_tests_has_the_task_undone_and_tells_nothing(
    name: str, tmp_path: Path
) -> None:
    scene = PRINCIPLE[name]
    root = build(tmp_path, scene)
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                          cwd=root, capture_output=True, text=True, timeout=120)  # fmt: skip
    assert done.returncode == 0, done.stdout[-500:]
    assert not passes(root, scene["task"])
    text = "\n".join(scene["files"].values()).lower()
    hidden = [w for w in TELLS[name] if w not in VISIBLE.get(name, ())]
    assert not [w for w in hidden if w in text]
    assert not [w for w in TELLS[name] if w in scene["second"].lower()]
    assert [w for w in TELLS[name] if w in scene["first"].lower()]  # the tells are the rule's


@pytest.mark.parametrize("name", sorted(RESULTS))
def test_session_2_works_in_another_file_than_session_1(name: str) -> None:
    scene = PRINCIPLE[name]
    named = set(re.findall(r"app/\w+\.py", scene["first"]))
    assert named and not [rel for rel in named if rel in scene["second"]]
