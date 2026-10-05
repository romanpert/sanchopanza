"""Walk the third confirmation's two interactive tasks by hand, with no model.

python benchmarks/browse/check_tasks3.py

I1 logs in and out of the-internet's form authentication page; I2 sorts saucedemo's inventory
by price, buys the first two and reads the totals. What this prints is what goes into the tasks'
required substrings. It spends nothing: the only thing it uses is the browser.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
WORK = pathlib.Path.home() / ".cache" / "sanchopanza" / "browse-nav"


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pwcli = _load("browse_pwcli", HERE / "pwcli.py")
refs_for = _load("browse_check_tasks", HERE / "check_tasks.py").refs_for


def _show(snap: str, pattern: str) -> None:
    for line in snap.splitlines():
        if re.search(pattern, line, re.I):
            print("   ", line.strip()[:110])


def _snapshot_with(b: Any, pattern: str, tries: int = 5) -> str:
    """A snapshot that shows `pattern`: the first one can arrive before the form has loaded."""
    snap = ""
    for _ in range(tries):
        snap = b._run("snapshot")
        if refs_for(snap, pattern):
            return snap
    return snap


def internet_login() -> None:
    with pwcli.PlaywrightCLI(
        f"chk-internet-{os.getpid()}", WORK / f"internet-{os.getpid()}", quiet=False
    ) as b:
        b.open("https://the-internet.herokuapp.com/login")
        snap = _snapshot_with(b, "textbox")
        boxes = refs_for(snap, r"textbox")
        b._run("fill", boxes[0][0], "tomsmith")
        b._run("fill", boxes[1][0], "SuperSecretPassword!")
        print(" buttons:", refs_for(snap, r"button"))
        b._run("click", refs_for(snap, r"button.*Login")[0][0])
        snap = _snapshot_with(b, "Logout")
        print(" AFTER LOGIN", b._last)
        _show(snap, r"logged|secure area|heading")
        b._run("click", refs_for(snap, r"link .*Logout")[0][0])
        snap = b._run("snapshot")
        print(" AFTER LOGOUT", b._last)
        _show(snap, r"logged|secure area")
        print(" playwright-cli calls used:", b.calls)


def saucedemo_sorted() -> None:
    with pwcli.PlaywrightCLI(
        f"chk-sauce3-{os.getpid()}", WORK / f"sauce3-{os.getpid()}", quiet=False
    ) as b:
        b.open("https://www.saucedemo.com/")
        snap = _snapshot_with(b, "textbox")
        boxes = refs_for(snap, r"textbox")
        b._run("fill", boxes[0][0], "standard_user")
        b._run("fill", boxes[1][0], "secret_sauce")
        b._run("click", refs_for(snap, r'button "Login"')[0][0])
        snap = _snapshot_with(b, "combobox")
        sort = refs_for(snap, r"combobox")
        print(" sort control:", sort[:1])
        b._run("select", sort[0][0], "Price (high to low)")
        snap = b._run("snapshot")
        adds = refs_for(snap, r'button "Add to cart')
        names = [
            line for _, line in refs_for(snap, r'link ".+"') if "Sauce" in line or "T-Shirt" in line
        ]
        print(" first products after sorting:", names[:4])
        _show(snap, r"\$\d")
        for ref, _ in adds[:2]:
            b._run("click", ref)
        snap = b._run("snapshot")
        b._run("click", refs_for(snap, r"Cart|shopping_cart")[0][0])
        snap = b._run("snapshot")
        _show(snap, r"Sauce|\$")
        b._run("click", refs_for(snap, r"Checkout")[0][0])
        snap = b._run("snapshot")
        for ref, value in zip([r for r, _ in refs_for(snap, r"textbox")],
                              ["Ada", "Lovelace", "28001"], strict=False):  # fmt: skip
            b._run("fill", ref, value)
        b._run("click", refs_for(b._run("snapshot"), r"Continue")[0][0])
        snap = b._run("snapshot")
        print(" TOTALS PAGE", b._last)
        _show(snap, r"Item total|Tax|Total:|Sauce")
        print(" playwright-cli calls used:", b.calls)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # the sites use icon-font characters
    internet_login()
    saucedemo_sorted()
