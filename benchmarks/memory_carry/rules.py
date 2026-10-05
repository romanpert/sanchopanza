"""The fact each scene's session 1 states, as the person wrote it (a substring of `first`). Kept
apart from `scenes.py` and `scenes_held.py`, which stay as sealed: this is for development of v7
(standing rules and the rule check), measured offline on the runs already made."""

from __future__ import annotations

RULES: dict[str, str] = {
    "columns": "finance's Excel macro reads this CSV by column position, so the order of the "
    "columns can never change.",
    "legacy": "legacy_total looks redundant but the mobile app 2.3 still reads it, so it stays.",
    "wording": "Our support team's scripts grep the importer's error messages, so the wording of "
    "the existing errors must stay exactly as it is.",
    "fields": "Our log shipper splits each line on ' | ' and expects exactly three fields.",
    "strings": "the partner integration sends offset and limit as strings ('50'), and that has to "
    "keep working.",
    "naive": "the warehouse loader chokes on UTC offsets, every timestamp we emit has to be naive "
    "UTC like 2026-01-01T10:00:00.",
    "stdlib": "This module runs on air-gapped machines with only the standard library, nothing "
    "from PyPI.",
    "py38": "Production still runs Python 3.8, so the code has to stay 3.8-compatible.",
    "rounding": "The tax office requires rounding half up (0.125 -> 0.13), never banker's "
    "rounding, for every amount we print on an invoice.",
    "latin1": "The mainframe that reads this file only understands ISO-8859-1 (Latin-1).",
    "envvar": "Ops sets PAYMENT_TIMEOUT and DEPLOY_REGION by those exact names in every "
    "deployment, they can't be renamed.",
    "rename": "Three of our other repositories import make_client from this module by name.",
    "stdout": "It runs from a cron that emails anything written to stdout to the whole team, so "
    "it must never print.",
    "sms": "This text goes out by SMS and the gateway cuts anything over 160 characters.",
    "ids": "the ERP gives order ids with leading zeros (00042), and they have to come through "
    "exactly as sent.",
    "nulls": "The analytics pipeline treats a missing key differently from null, so every key has "
    "to be present, with None when there is no value.",
}
