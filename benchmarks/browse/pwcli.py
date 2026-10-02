"""A `Browser` for `sanchopanza.navigate` over the `playwright-cli` command.

Measurement plumbing, which is why it lives here and not in the package: the package takes the
browser as an argument and does not depend on one.

`playwright-cli -s=NAME` keeps one browser between invocations, prints a snapshot inline on
`snapshot`, and takes the snapshot's own refs for `click`, `fill` and `select`. Each call is a
new node process (about a second), which is slow and does not matter: the thing being measured
is what the models cost, not what the driver costs.

    browser = PlaywrightCLI("nav1", workdir)
    browser.open("https://example.org/")
    snapshot, url, title = await browser.snapshot()
    ...
    browser.close()
"""

from __future__ import annotations

import contextlib
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from sanchopanza.navigate import Action  # noqa: E402

TIMEOUT_S = 90
_URL = re.compile(r"^- Page URL:\s*(.*)$", re.M)
_TITLE = re.compile(r"^- Page Title:\s*(.*)$", re.M)
_ERROR = re.compile(r"^###? Error|^Error:", re.M)


class BrowserGone(RuntimeError):
    pass


class PlaywrightCLI:
    def __init__(self, session: str, workdir: pathlib.Path, *, quiet: bool = True) -> None:
        self.session = session
        self.workdir = workdir
        self.quiet = quiet
        self.calls = 0
        self._last: tuple[str, str] = ("", "")  # url, title
        workdir.mkdir(parents=True, exist_ok=True)

    def _run(self, *args: str) -> str:
        self.calls += 1
        exe = shutil.which("playwright-cli") or "playwright-cli"
        argv = [exe, f"-s={self.session}", *args]
        try:
            done = subprocess.run(
                argv, cwd=self.workdir, capture_output=True, timeout=TIMEOUT_S, shell=False
            )
        except subprocess.TimeoutExpired:
            raise BrowserGone(f"playwright-cli {args[0]} timed out after {TIMEOUT_S}s") from None
        text = done.stdout.decode("utf-8", errors="replace")
        if done.returncode != 0 and not text.strip():
            raise BrowserGone(done.stderr.decode("utf-8", errors="replace")[:300])
        url = _URL.search(text)
        title = _TITLE.search(text)
        self._last = (
            url.group(1).strip() if url else self._last[0],
            title.group(1).strip() if title else self._last[1],
        )
        if not self.quiet:
            print(f"  $ playwright-cli {' '.join(args)[:90]} -> {self._last[0][:70]}")
        return text

    # --- the loop's interface ----------------------------------------------------------------

    async def snapshot(self) -> tuple[str, str, str]:
        text = self._run("snapshot")
        return text, self._last[0], self._last[1]

    async def act(self, action: Action) -> str:
        try:
            if action.kind == "click":
                text = self._run("click", action.ref)
            elif action.kind == "fill":
                text = self._run("fill", action.ref, action.text)
            elif action.kind == "select":
                text = self._run("select", action.ref, action.text)
            elif action.kind == "press":
                text = self._run("press", action.text)
            elif action.kind == "back":
                text = self._run("go-back")
            else:
                return f"error: nothing to do for {action.kind!r}"
        except BrowserGone:
            raise  # a dead browser is not a step the loop can score
        if _ERROR.search(text):
            line = next((x for x in text.splitlines() if x.strip().startswith("Error")), "")
            return f"error: {line.strip()[:200] or 'the command failed'}"
        return f"ok, now at {self._last[0]}"

    # --- driving it by hand -------------------------------------------------------------------

    def open(self, url: str) -> str:
        return self._run("open", url)

    def goto(self, url: str) -> str:
        return self._run("goto", url)

    def find(self, text: str) -> str:
        return self._run("find", text)

    def close(self) -> None:
        with contextlib.suppress(BrowserGone):
            self._run("close")

    def __enter__(self) -> PlaywrightCLI:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
