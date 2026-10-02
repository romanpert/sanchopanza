"""Walk each candidate multi-step task by hand, with no model, and print the facts to grade on.

python benchmarks/browse/check_tasks.py saucedemo
python benchmarks/browse/check_tasks.py todomvc

A task nobody has walked is a task whose answer nobody knows. This spends nothing: the only
thing it uses is the browser. What it prints is what goes into the task's required substrings,
and how many actions the task actually takes, which is the whole reason for this phase.
"""

from __future__ import annotations

import importlib.util
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


def refs_for(snapshot: str, pattern: str) -> list[tuple[str, str]]:
    """(ref, line) for every snapshot line matching `pattern`, in page order."""
    out = []
    for line in snapshot.splitlines():
        ref = re.search(r"\[ref=([\w-]+)\]", line)
        if ref and re.search(pattern, line, re.I):
            out.append((ref.group(1), line.strip()[:110]))
    return out


def saucedemo() -> None:
    """Login, three named items into the cart, checkout, the totals. No URL shortcut exists."""
    with pwcli.PlaywrightCLI("chk-sauce", WORK / "sauce", quiet=False) as b:
        b.open("https://www.saucedemo.com/")
        snap = b._run("snapshot")
        print(" login fields:", refs_for(snap, r"textbox|button"))
        user = refs_for(snap, r'textbox "Username"') or refs_for(snap, r"textbox")
        password = refs_for(snap, r'textbox "Password"') or refs_for(snap, r"textbox")[1:]
        b._run("fill", user[0][0], "standard_user")
        b._run("fill", password[0][0], "secret_sauce")
        login = refs_for(b._run("snapshot"), r'button "Login"')
        b._run("click", login[0][0])
        snap = b._run("snapshot")
        print(" after login at", b._last)
        wanted = ("Sauce Labs Backpack", "Sauce Labs Bike Light", "Sauce Labs Bolt T-Shirt")
        for name in wanted:
            snap = b._run("snapshot")
            lines = snap.splitlines()
            at = next((i for i, x in enumerate(lines) if name in x), None)
            if at is None:
                print(" NOT FOUND on the inventory page:", name)
                continue
            add = None
            for line in lines[at : at + 14]:
                ref = re.search(r"\[ref=([\w-]+)\]", line)
                if ref and re.search(r"Add to cart", line, re.I):
                    add = ref.group(1)
                    break
            print(f" {name}: add-to-cart ref {add}")
            price = next((x.strip() for x in lines[at : at + 14] if "$" in x), "?")
            print("   price line:", price[:90])
            if add:
                b._run("click", add)
        snap = b._run("snapshot")
        cart = refs_for(snap, r'button "Cart')
        print(" cart candidates:", cart[:4])
        if cart:
            b._run("click", cart[0][0])
        snap = b._run("snapshot")
        checkout = refs_for(snap, r"Checkout")
        print(" at", b._last, "checkout:", checkout[:2])
        if checkout:
            b._run("click", checkout[0][0])
        snap = b._run("snapshot")
        boxes = refs_for(snap, r"textbox")
        print(" checkout fields:", boxes)
        for ref, value in zip([r for r, _ in boxes], ["Ada", "Lovelace", "28001"], strict=False):
            b._run("fill", ref, value)
        cont = refs_for(b._run("snapshot"), r'button "Continue"|Continue')
        if cont:
            b._run("click", cont[0][0])
        snap = b._run("snapshot")
        print(" TOTALS PAGE", b._last)
        for line in snap.splitlines():
            if re.search(r"Item total|Tax|Total:", line, re.I):
                print("   ", line.strip()[:100])
        finish = refs_for(snap, r"Finish")
        if finish:
            b._run("click", finish[0][0])
        snap = b._run("snapshot")
        print(" DONE PAGE", b._last)
        for line in snap.splitlines():
            if re.search(r"heading|Thank you|dispatched", line, re.I):
                print("   ", line.strip()[:100])
        print(" playwright-cli calls used:", b.calls)


def todomvc() -> None:
    """Five items typed in, two completed, the Active filter, the counter. No URL shortcut."""
    with pwcli.PlaywrightCLI("chk-todo", WORK / "todo", quiet=False) as b:
        b.open("https://demo.playwright.dev/todomvc/")
        snap = b._run("snapshot")
        box = refs_for(snap, r"textbox")
        print(" input:", box[:2])
        for item in ("buy milk", "write the prereg", "walk the dog", "pay the VPS", "read QASPER"):
            b._run("fill", box[0][0], item)
            b._run("press", "Enter")
            snap = b._run("snapshot")
            box = refs_for(snap, r"textbox") or box
        snap = b._run("snapshot")
        print(" items now:", len(refs_for(snap, r"listitem|checkbox")))
        boxes = refs_for(snap, r"checkbox")
        print(" checkboxes:", boxes[:7])
        for ref, _ in boxes[1:3]:
            b._run("click", ref)
        snap = b._run("snapshot")
        for line in snap.splitlines():
            if re.search(r"items? left|Active|Completed", line, re.I):
                print("   ", line.strip()[:100])
        active = refs_for(snap, r'link "Active"')
        if active:
            b._run("click", active[0][0])
        snap = b._run("snapshot")
        print(" ACTIVE FILTER", b._last)
        for line in snap.splitlines():
            if re.search(r"listitem|items? left", line, re.I):
                print("   ", line.strip()[:100])
        print(" playwright-cli calls used:", b.calls)


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    if which == "saucedemo":
        saucedemo()
    elif which == "todomvc":
        todomvc()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
