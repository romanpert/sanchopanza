"""L2-regularised logistic regression in pure Python (lot A10): no numpy in this environment.

Objective, as scikit-learn's `LogisticRegression(C=...)`: C * sum of log-losses + ||w||^2 / 2,
intercept not penalised. Solved by L-BFGS (memory 10) with a backtracking Armijo line search.
Every loop runs in a fixed order, so the same rows give the same weights bit for bit.

Rows are sparse: (column indices, values), as `a10_features.Vectorizer.transform` returns.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

Row = tuple[tuple[int, ...], tuple[float, ...]]

MEMORY = 10
MAX_ITER = 500
TOL = 1e-6  # stop when the largest gradient component is below TOL * max(1, C * n)
ARMIJO = 1e-4


def _log1pexp(z: float) -> float:
    return z + math.log1p(math.exp(-z)) if z > 0 else math.log1p(math.exp(z))


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def margin(row: Row, w: Sequence[float], b: float) -> float:
    idx, val = row
    return b + sum(w[j] * v for j, v in zip(idx, val, strict=True))


def loss_grad(
    rows: Sequence[Row], y: Sequence[int], theta: Sequence[float], c: float
) -> tuple[float, list[float]]:
    """Objective and gradient at theta = weights + [intercept]; y in {-1, +1}."""
    d = len(theta) - 1
    w, b = theta[:d], theta[d]
    grad = list(w) + [0.0]
    loss = 0.0
    for row, yi in zip(rows, y, strict=True):
        m = yi * margin(row, w, b)
        loss += _log1pexp(-m)
        coef = -c * yi * sigmoid(-m)
        idx, val = row
        for j, v in zip(idx, val, strict=True):
            grad[j] += coef * v
        grad[d] += coef
    return c * loss + 0.5 * sum(x * x for x in w), grad


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def fit(
    rows: Sequence[Row], labels: Sequence[bool], dim: int, c: float, max_iter: int = MAX_ITER
) -> tuple[list[float], float, dict[str, float]]:
    """Weights, intercept and how the solver ended ({"iterations", "grad_max", "objective"})."""
    y = [1 if t else -1 for t in labels]
    theta = [0.0] * (dim + 1)
    f, g = loss_grad(rows, y, theta, c)
    s_hist: list[list[float]] = []
    y_hist: list[list[float]] = []
    tol = TOL * max(1.0, c * len(rows))
    it = 0
    for it in range(1, max_iter + 1):  # noqa: B007 - `it` is reported after the loop
        if max(abs(x) for x in g) < tol:
            break
        q = list(g)
        alphas = []
        for s, yy in zip(reversed(s_hist), reversed(y_hist), strict=True):
            rho = 1.0 / _dot(yy, s)
            a = rho * _dot(s, q)
            alphas.append((rho, a))
            q = [qi - a * yi for qi, yi in zip(q, yy, strict=True)]
        if s_hist:
            gamma = _dot(s_hist[-1], y_hist[-1]) / _dot(y_hist[-1], y_hist[-1])
        else:
            gamma = 1.0 / math.sqrt(_dot(g, g))
        r = [gamma * qi for qi in q]
        for (s, yy), (rho, a) in zip(zip(s_hist, y_hist, strict=True), reversed(alphas),
                                     strict=True):  # fmt: skip
            beta = rho * _dot(yy, r)
            r = [ri + (a - beta) * si for ri, si in zip(r, s, strict=True)]
        direction = [-ri for ri in r]
        slope = _dot(g, direction)
        if slope >= 0:  # not a descent direction: restart from the gradient
            s_hist, y_hist = [], []
            direction = [-gi / math.sqrt(_dot(g, g)) for gi in g]
            slope = _dot(g, direction)
        step = 1.0
        while True:
            trial = [t + step * di for t, di in zip(theta, direction, strict=True)]
            f_new, g_new = loss_grad(rows, y, trial, c)
            if f_new <= f + ARMIJO * step * slope or step < 1e-12:
                break
            step *= 0.5
        s_new = [a - b for a, b in zip(trial, theta, strict=True)]
        y_new = [a - b for a, b in zip(g_new, g, strict=True)]
        if _dot(s_new, y_new) > 1e-12:
            s_hist.append(s_new)
            y_hist.append(y_new)
            if len(s_hist) > MEMORY:
                s_hist.pop(0)
                y_hist.pop(0)
        converged = abs(f - f_new) <= 1e-12 * max(1.0, abs(f))
        theta, f, g = trial, f_new, g_new
        if converged:
            break
    info = {"iterations": it, "grad_max": max(abs(x) for x in g), "objective": f}
    return theta[:dim], theta[dim], info


def predict(rows: Sequence[Row], w: Sequence[float], b: float) -> list[float]:
    """p(done) for each row."""
    return [sigmoid(margin(r, w, b)) for r in rows]
