"""`sanchopanza hook` with the proposed `text_of` patch applied in memory. Exploratory arm only.

The registered run found that Claude Code's built-in tools answer PostToolUse with shapes
`text_of` does not read: `Read` returns `{"type": "text", "file": {"content": ...}}`,
`WebFetch` `{"result": ...}`, `WebSearch` `{"results": [...]}`. The scan then sees an empty
string and never runs. This wrapper applies the patch proposed in README.md without editing
`src/`, so the post-hoc arm can show what the patched hook does. It is not part of the
registered result.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import Any

from sanchopanza.harness import generic
from sanchopanza.harness.claude_code import main

_original = generic.text_of


def text_of(response: Any) -> str:
    if isinstance(response, Mapping):
        file = response.get("file")
        if isinstance(file, Mapping) and isinstance(file.get("content"), str):
            return file["content"]  # Read
        if isinstance(response.get("result"), str):
            return response["result"]  # WebFetch
        results = response.get("results")
        if isinstance(results, list) and results:  # WebSearch
            return "\n".join(r if isinstance(r, str) else json.dumps(r) for r in results)
    return _original(response)


generic.text_of = text_of

if __name__ == "__main__":
    sys.exit(main())
