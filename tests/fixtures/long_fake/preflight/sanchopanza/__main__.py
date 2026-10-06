"""`python -m sanchopanza jev-preflight` for dry runs: no network, no key used. It exits with
FAKE_PREFLIGHT_EXIT (default 0) as the real one does (0 ok, 10 no_funds, 11 auth, 12 no_key,
13 unreachable, 14 other)."""

import os
import sys

REASONS = {0: "ok", 10: "no_funds", 11: "auth", 12: "no_key", 13: "unreachable", 14: "other"}
code = int(os.environ.get("FAKE_PREFLIGHT_EXIT") or 0)
if sys.argv[1:] != ["jev-preflight"]:
    raise SystemExit(f"fake sanchopanza: only jev-preflight, not {sys.argv[1:]}")
key = "set" if os.environ.get("TYPESAFE_API_KEY") else "absent"
print(f"jev preflight (fake): {REASONS.get(code, code)}; key {key}")
raise SystemExit(code)
