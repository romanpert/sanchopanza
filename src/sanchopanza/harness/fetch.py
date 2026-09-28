"""Whether a shell command fetches from the network, decided in code.

Used to scan the output of such a command without the operator naming the shell as a content
tool: an agent refused by WebFetch reaches for `curl`, and that page is exactly the content the
scan exists for (docs/results/2026-09-28-claude-code-harness/). The matcher is deliberately
plain. A miss leaves the command where it was before (unscanned unless the shell is named); a
false match costs one decision on output that did not need it. Neither changes what runs.
"""

from __future__ import annotations

import re

# Names specific enough to count anywhere as a word: nobody writes `wget` meaning something else.
_ANYWHERE = re.compile(
    r"(?<![\w.-])(?:curl|wget|aria2c|lynx|w3m|invoke-webrequest|invoke-restmethod)"
    r"(?:\.exe)?(?![\w-])",
    re.IGNORECASE,
)

# Short names that only count as the command itself: at the start or after a separator.
_COMMAND_START = r"(?:^|[;&|(`\n]|\$\()\s*(?:sudo\s+|time\s+)?"
_AS_COMMAND = re.compile(
    _COMMAND_START + r"(?:iwr|irm|http|https|xh|xhs)(?:\.exe)?\s+\S",
    re.IGNORECASE,
)
_GH_API = re.compile(r"(?<![\w.-])gh(?:\.exe)?\s+api\b")

# An interpreter given inline code that names an HTTP client.
_INLINE_CODE = re.compile(r"(?<![\w.-])(?:python[\d.]*|py|node|deno|bun)(?:\.exe)?\s+-[ce]\b")
_HTTP_CLIENTS = re.compile(
    r"\b(?:requests|urllib|httpx|aiohttp|http\.client|urlopen|axios)\b|\bfetch\s*\(",
    re.IGNORECASE,
)


def fetches_from_network(command: str) -> bool:
    """True when the command visibly downloads something. Conservative on purpose."""
    if not command.strip():
        return False
    if _ANYWHERE.search(command) or _AS_COMMAND.search(command) or _GH_API.search(command):
        return True
    return bool(_INLINE_CODE.search(command) and _HTTP_CLIENTS.search(command))
