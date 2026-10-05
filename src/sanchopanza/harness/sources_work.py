"""The arithmetic a reply shows, for the sources hook's number sign (version 2.1).

Version 2's number sign blocks on any number in the ANSWER line that no tool result shows. On the
second FRAMES pilot 4 of Sonnet's 6 blocks went to right sessions that had computed a right
number from operands a page showed (a span of years, a sum). With
`SANCHOPANZA_SOURCES_SHOWN_WORK=1` such a number counts as read when the reply writes the step
out (`a - b = c`, `a + b + c = d`, `a / b ≈ c%`), the step is right, and every operand is a
number some tool result or the question shows, or the result of another such step.

Deterministic, no model: a regular expression for the steps and a small evaluator for + - x /.
"""

from __future__ import annotations

import ast
import operator
import re
from collections.abc import Iterable
from dataclasses import dataclass

_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_OP = r"[-+−–×x*/÷]"
_EQUATION = re.compile(
    rf"(?<![\w.,])((?:{_NUM})(?:\s*{_OP}\s*(?:{_NUM}))+)\s*(?:=|≈|~|→)\s*\**\s*({_NUM})\s*(%?)"
)
_TERM = re.compile(rf"({_NUM})|({_OP})")
_SYMBOL = {"-": "-", "−": "-", "–": "-", "+": "+", "×": "*", "x": "*", "*": "*", "/": "/",
           "÷": "/"}  # fmt: skip
_APPLY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
          ast.Div: operator.truediv}  # fmt: skip


@dataclass(frozen=True)
class Equation:
    operands: tuple[float, ...]
    result: float
    right: bool


def _value(text: str) -> float:
    return float(text.replace(",", ""))


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _APPLY:
        return _APPLY[type(node.op)](_evaluate(node.left), _evaluate(node.right))
    raise ValueError("not plain arithmetic")


def _close(computed: float, written: str) -> bool:
    """Right to the precision the reply wrote: half a unit for a whole number, one unit of the
    last decimal place otherwise (a value rounded up at the last place is still right)."""
    decimals = len(written.split(".")[1]) if "." in written else 0
    tolerance = 10.0**-decimals if decimals else 0.5
    return abs(computed - _value(written)) <= tolerance + 1e-9


def _equation(left: str, result: str, percent: str) -> Equation | None:
    terms = [(num, op) for num, op in _TERM.findall(left)]
    operands = tuple(_value(num) for num, _ in terms if num)
    source = " ".join(repr(_value(num)) if num else _SYMBOL[op] for num, op in terms)
    try:
        computed = _evaluate(ast.parse(source, mode="eval").body)
    except (SyntaxError, ValueError, ZeroDivisionError):
        return None
    right = _close(computed, result) or bool(percent and _close(computed * 100, result))
    return Equation(operands, _value(result), right)


def equations(text: str) -> list[Equation]:
    """Every arithmetic step written out in a text, in order, with whether it is right."""
    found = (_equation(*m.groups()) for m in _EQUATION.finditer(text or ""))
    return [e for e in found if e is not None]


def grounded(text: str, seen: Iterable[float]) -> set[float]:
    """The results of the right steps whose operands are all in `seen` or results of such
    steps themselves (to a fixed point)."""
    steps = [e for e in equations(text) if e.right]
    known, out = set(seen), set()
    changed = True
    while changed:
        fresh = {e.result for e in steps if e.result not in out and set(e.operands) <= known | out}
        changed = bool(fresh)
        out |= fresh
    return out
