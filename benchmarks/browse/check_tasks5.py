"""Walk the fifth confirmation's two new interactive tasks by hand, and read H8's table the way a
browser draws it, with no model.

python benchmarks/browse/check_tasks5.py

I3 logs in to the XYZ Bank demo as a customer, deposits and withdraws, and reads the balance; I4
fills and submits the HTML form of testpages.eviltester.com and reads its results page. H8's
second route clicks the four pages of the Pagination Web Table and reads the prices drawn on
each. What this prints is what goes into the tasks' required substrings and H8's truth. It spends
nothing: the only thing it uses is the browser.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import sys
from decimal import Decimal
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
WORK = pathlib.Path.home() / ".cache" / "sanchopanza" / "browse-nav"
BANK = "https://www.globalsqa.com/angularJs-protractor/BankingProject/#/login"
FORM = "https://testpages.eviltester.com/pages/forms/html-form/"
PRACTICE = "https://testautomationpractice.blogspot.com/"


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pwcli = _load("browse_pwcli", HERE / "pwcli.py")
check3 = _load("browse_check_tasks3_for_5", HERE / "check_tasks3.py")
refs_for, show, snapshot_with = check3.refs_for, check3._show, check3._snapshot_with


def _browser(name: str) -> Any:
    return pwcli.PlaywrightCLI(f"chk5-{name}-{os.getpid()}", WORK / f"{name}-{os.getpid()}",
                               quiet=False)  # fmt: skip


def bank() -> None:
    """I3: Hermoine Granger, account 1001, deposit 1500, withdraw 400."""
    with _browser("bank") as b:
        b.open(BANK)
        snap = snapshot_with(b, r'button "Customer Login"')
        b._run("click", refs_for(snap, r'button "Customer Login"')[0][0])
        snap = snapshot_with(b, "combobox")
        b._run("select", refs_for(snap, r"combobox")[0][0], "Hermoine Granger")
        snap = snapshot_with(b, r'button "Login"')
        b._run("click", refs_for(snap, r'button "Login"')[0][0])
        snap = snapshot_with(b, r"Deposit")
        show(snap, r"Account Number|Balance|combobox|option|strong")
        for tab, amount, button in (
            ("Deposit", "1500", "Deposit"),
            ("Withdrawl", "400", "Withdraw"),
        ):
            b._run("click", refs_for(snap, rf'button "{tab}')[0][0])
            snap = snapshot_with(b, r"spinbutton|textbox")
            box = refs_for(snap, r"spinbutton|textbox")[0][0]
            b._run("fill", box, amount)
            snap = b._run("snapshot")
            b._run("click", [r for r, line in refs_for(snap, rf'button "{button}')
                             if "tab" not in line.lower()][-1])  # fmt: skip
            snap = b._run("snapshot")
            print(f" AFTER {tab.upper()}")
            show(snap, r"Balance|successful|strong")
        print(" playwright-cli calls used:", b.calls)


def form() -> None:
    """I4: the HTML form, filled as the task says, and its results page."""
    with _browser("form") as b:
        b.open(FORM)
        snap = snapshot_with(b, r"textbox")
        boxes = refs_for(snap, r"textbox")
        show(snap, r"textbox|checkbox|radio|combobox|listbox|button")
        b._run("fill", boxes[0][0], "ada")
        b._run("fill", boxes[1][0], "lovelace1815")
        b._run("fill", boxes[2][0], "first program")
        # The snapshot names neither the checkboxes nor the radios: their labels are plain text
        # after them, so they are taken in page order (1, 2, 3).
        checkboxes, radios = refs_for(snap, r"- checkbox"), refs_for(snap, r"- radio")
        b._run("check", checkboxes[0][0])
        b._run("uncheck", checkboxes[2][0])
        b._run("check", radios[2][0])
        b._run("select", refs_for(snap, r"combobox")[-1][0], "Drop Down Item 5")
        b._run("click", refs_for(snap, r'button "submit"')[-1][0])  # the first is an image
        snap = snapshot_with(b, r"Submitted Values|submitted")
        print(" RESULTS PAGE", b._last)
        show(snap, r"username|password|comments|checkbox|radioval|dropdown|cb\d|rd\d|dd\d|first")
        print(" playwright-cli calls used:", b.calls)


def practice_table() -> None:
    """H8's second route: the prices the table draws on each of its pages, clicked in turn."""
    prices: list[Decimal] = []
    with _browser("practice") as b:
        b.open(PRACTICE)
        for page in range(1, 6):
            snap = b._run("eval", "() => [...document.querySelectorAll('#productTable tbody tr')]"
                                  ".map(r => r.cells[2].textContent).join(' ')")  # fmt: skip
            drawn = [Decimal(p) for p in re.findall(r"\$(\d+\.\d\d)", snap)]
            print(f" page {page}: {drawn}")
            prices += drawn
            links = b._run("eval", "() => document.querySelectorAll('#pagination a').length")
            pages = int((re.findall(r"^\s*(\d+)\s*$", links, re.M) or ["0"])[-1])
            if page >= pages:
                break
            b._run("eval", f"() => document.querySelectorAll('#pagination a')[{page}].click()")
    print(f" H8 by the drawn table: {len(prices)} products, {sum(p > 15 for p in prices)} over 15")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    practice_table()
    form()
    bank()
