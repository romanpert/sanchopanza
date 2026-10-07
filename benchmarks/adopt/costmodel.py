"""Free cost model for the long-session bench. No API calls.

    python benchmarks/adopt/costmodel.py            # the table, power and the launch estimates

Request-level replay of a synthetic session: context grows linearly per request, every request
reads the cached prefix at 0.1x input, writes its new tokens at 2x input (1-hour TTL) and emits
output. A compaction (arms N-early, S) costs one request that reads the context and writes a
summary, then the context restarts at base + summary (+ guard block for S), and the agent pays
extra re-read requests and tokens afterwards.

Calibration: B2 (pydantic-long40-1, Sonnet 5.5, arm N): 8.74 USD at Claude Code's recorded
Sonnet 5.5 rate (2/10, 1h write 4, read 0.2), peak 263k, 186 tool calls + 40 prompts.

**Check-done (S only; STATUS-runner item 9, pre-mortem 17).** S's Stop hook asks Jev whether the
request was done and, when it says no, sends Claude back for one more turn. Since gate A (main
f2a0fe2, `harness.change_gate`) it asks only when the request changed something or asks for an
action; every request of a coding chain does both (a bug: "Please fix this"; a callback: "Write
the file"), so it is asked on every one. Each send-back costs the requests Claude makes after it,
at the context it has then; the term is those requests, spread over the session. From the
gate-A data on main (`docs/results/2026-10-05-change-gate/`):

- requests per send-back: 41 turns followed 17 send-backs on h2h (BrowseComp-Plus 23 after 10,
  LongBench v2 18 after 7), 2.41;
- the chance of a send-back on an open request, by what is true of the request:
  unfinished work, 286/313 (check-done's recall on AgentDojo's unfinished runs); finished work,
  13/342 (its false blocks on the finished ones; gate A lets 12 of them through only because
  those requests read; a coding request does not). The share of unfinished bugs is taken as
  1 - per-bug F2P (B2's N: 27 of 40 resolved).
- A ceiling: 17/20 h2h sessions sent back when the question did not fit the task (Q&A).

Not measured on coding (no recorded coding session ran check-done): `CHECK_DONE` names the three
scenarios, and the launch estimate uses "mid".
"""

from __future__ import annotations

import json
import math
import random
import statistics as st
from dataclasses import dataclass

PRICES = {  # USD per MTok (input, output), as given by the owner for this design
    "sonnet-5.5": (3.0, 15.0),
    "opus-5.5": (5.0, 25.0),
    "haiku-4.5": (1.0, 5.0),
    "sonnet-5.5@2/10": (2.0, 10.0),  # what Claude Code's costUSD reproduced in B2
}

# ---- check-done (gate-A data, main docs/results/2026-10-05-change-gate) --------------------------

REQUESTS_PER_SEND_BACK = 41 / 17  # h2h: turns after the 17 send-backs (23 + 18)
RECALL_UNFINISHED = 286 / 313  # AgentDojo: blocks on unfinished runs
FALSE_FINISHED = 13 / 342  # AgentDojo: blocks on finished runs (655 - 313)
B2_N_UNFINISHED = 1 - 27 / 40  # B2 N, per-bug F2P 27/40
QA_MISFIT = 17 / 20  # h2h: sessions sent back when the question did not fit


def send_back_rate(unfinished: float) -> float:
    """The chance check-done sends Claude back on one open request."""
    return unfinished * RECALL_UNFINISHED + (1 - unfinished) * FALSE_FINISHED


CHECK_DONE = {
    "low": send_back_rate(0.0),  # every bug finished: only false blocks
    "mid": send_back_rate(B2_N_UNFINISHED),
    "high": QA_MISFIT,
}


@dataclass(frozen=True)
class CheckDone:
    rate: float  # send-backs per open request
    open_requests: int  # requests gate A opens on (every bug and callback of a coding chain)
    requests_per: float = REQUESTS_PER_SEND_BACK

    @property
    def send_backs(self) -> float:
        return self.rate * self.open_requests

    @property
    def extra_requests(self) -> float:
        return self.send_backs * self.requests_per


def session_cost(model, requests, base=22_000, growth=1_070, out=400, threshold=None,
                 summary=12_000, post_extra=15_000, guard_block=0, reread_tok=0, reread_req=0,
                 fixed_overhead=0, jev_usd=0.0, check_done: CheckDone | None = None):  # fmt: skip
    pin, pout = PRICES[model]
    read, write = 0.1 * pin / 1e6, 2.0 * pin / 1e6
    o = pout / 1e6
    ctx = base + fixed_overhead
    if threshold:  # a re-read after a compaction fits under the next one (else it thrashes)
        room = threshold - (base + fixed_overhead + post_extra + guard_block)
        if room <= growth * (reread_req + 1):
            raise ValueError(f"threshold {threshold} leaves no room after a compaction")
        reread_tok = min(reread_tok, (room - growth * (reread_req + 1)) // 2)
    cost = ctx * write  # first request writes the prefix
    over200, compactions, peak, n_req = 0.0, 0, ctx, 0
    pending_reread = 0
    # check-done's extra requests, due in proportion to the session's own requests
    extra = round(check_done.extra_requests) if check_done else 0
    own, extra_done, owed = 0, 0, 0
    while own < requests or pending_reread or owed:
        add = growth
        if pending_reread > 0:  # re-read requests add their own tokens
            add += reread_tok / max(reread_req, 1)
            pending_reread -= 1
        elif owed:  # a send-back's request: one more turn at this context
            owed -= 1
            extra_done += 1
        else:
            own += 1
            owed += extra * own // requests - extra * (own - 1) // requests
        c = ctx * read + add * write + out * o
        cost += c
        if ctx > 200_000:
            over200 += c
        ctx += add
        peak = max(peak, ctx)
        n_req += 1
        if threshold and ctx >= threshold:
            cost += ctx * read + summary * o  # the compaction call
            compactions += 1
            ctx = base + fixed_overhead + post_extra + guard_block
            cost += (post_extra + guard_block) * write
            pending_reread = reread_req  # extra requests after each compaction
    return {"usd": round(cost + jev_usd, 2), "peak_k": round(peak / 1000), "requests": n_req,
            "compactions": compactions, "share_over_200k": round(over200 / cost, 2),
            "send_back_requests": extra_done}  # fmt: skip


def with_check_done(model, requests, check_done: CheckDone, **kw) -> dict:
    """S's session with and without the check-done term, and the term itself in USD."""
    plain = session_cost(model, requests, **kw)
    full = session_cost(model, requests, check_done=check_done, **kw)
    return {**full, "check_done_usd": round(full["usd"] - plain["usd"], 2),
            "send_backs": round(check_done.send_backs, 1)}  # fmt: skip


def arms(model, requests, growth=1_070, out=400, open_requests=62, scenario="mid",
         n_threshold=None, threshold=160_000):  # fmt: skip
    """N, N-early and S on one chain. `open_requests`: the requests check-done is asked on (a
    long60 chain: 60 bugs and 2 callbacks). `n_threshold`: where N compacts when its window is
    known (None: it does not within the chain). `threshold`: N-early's and S's compaction point."""
    common = dict(growth=growth, out=out)
    done = CheckDone(CHECK_DONE[scenario], open_requests)
    return {
        "N": session_cost(model, requests, threshold=n_threshold, reread_tok=25_000,
                          reread_req=10, **common),
        "N-early": session_cost(model, requests, threshold=threshold, reread_tok=25_000,
                                reread_req=10, **common),
        "S": with_check_done(model, requests, done, threshold=threshold, guard_block=3_000,
                             reread_tok=15_000, reread_req=6, fixed_overhead=700, jev_usd=0.10,
                             **common),
    }  # fmt: skip


def calib():
    return session_cost("sonnet-5.5@2/10", 226)


# ---- what each launch is expected to cost (printed by long_launch before it starts) -------------

REQ_PER_BUG = {"sonnet": (5.65, 5.65), "opus": (4.2, 5.65), "haiku": (5.65, 48.0)}
# Sonnet: B2 (226 requests / 40 bugs); Opus: 0.75x-1x Sonnet's; Haiku: from Sonnet's to the ~48
# turns of an adopt_d single (SWE-bench Verified). Output per request: Sonnet 400, Opus 500,
# Haiku 400.
OUT = {"sonnet": 400, "opus": 500, "haiku": 400}
PRICE_OF = {"sonnet": "sonnet-5.5", "opus": "opus-5.5", "haiku": "haiku-4.5"}
HAIKU_WINDOW = 200_000  # Haiku 4.5's model default; compacts at window - 33k


def expected(model: str, bugs: int, callbacks: int, arm_names: tuple[str, ...],
             threshold: int) -> dict[str, tuple[float, float]]:  # fmt: skip
    """(low, high) USD per arm of one chain, over the model's range of requests per bug."""
    n_threshold = HAIKU_WINDOW - 33_000 if model == "haiku" else None
    names = {"N": "N", "Ne": "N-early", "S": "S"}
    out: dict[str, list[float]] = {a: [] for a in arm_names}
    for per_bug in REQ_PER_BUG[model]:
        table = arms(PRICE_OF[model], round(bugs * per_bug), out=OUT[model],
                     open_requests=bugs + callbacks, n_threshold=n_threshold,
                     threshold=threshold)  # fmt: skip
        for a in arm_names:
            out[a].append(table[names[a]]["usd"])
    return {a: (min(v), max(v)) for a, v in out.items()}


# ---- power ---------------------------------------------------------------------------------------


def power_cost(sd, effect, n, sims=4000, seed=20261005):
    """Paired log-ratio test: share of studies whose 95 % t-CI on mean ln(S/N) excludes 0."""
    rng = random.Random(seed)
    tcrit = {4: 2.776, 5: 2.571, 6: 2.447, 8: 2.306, 10: 2.228, 12: 2.179, 16: 2.120,
             20: 2.086, 24: 2.064, 30: 2.042, 40: 2.021, 60: 2.000}  # fmt: skip
    t = tcrit.get(n, 1.96)
    hits = 0
    for _ in range(sims):
        d = [rng.gauss(math.log(effect), sd) for _ in range(n)]
        m, s = st.mean(d), st.stdev(d)
        if m + t * s / math.sqrt(n) < 0:
            hits += 1
    return round(hits / sims, 3)


def halfwidth(sd, n):
    return round(math.exp(1.96 * sd / math.sqrt(n)), 3)


def ni_power(n_chains, bugs, disc, deff, margin, sims=4000, seed=7):
    """Non-inferiority on per-bug resolution, paired by bug, true difference 0: share of
    studies whose one-sided 95 % lower bound on S - N is above -margin. Discordant share
    `disc`, design effect `deff` for clustering by chain."""
    n = n_chains * bugs
    se = math.sqrt(disc / n) * math.sqrt(deff)
    rng = random.Random(seed)
    hits = sum(1 for _ in range(sims) if rng.gauss(0, se) - 1.645 * se > -margin)
    return round(hits / sims, 3), round(se * 100, 2)


if __name__ == "__main__":
    out = {"calibration_B2_N_at_2_10": calib(), "B2_measured": 8.74,
           "check_done_rates": {k: round(v, 3) for k, v in CHECK_DONE.items()}}  # fmt: skip
    tasks = {"L40": 40, "L60": 60, "L80": 80}
    for model, req_per_bug, o in (("sonnet-5.5", 5.65, 400), ("opus-5.5", 4.2, 500),
                                  ("opus-5.5-high", 5.65, 500)):  # fmt: skip
        price = "opus-5.5" if model.startswith("opus") else model
        for t, bugs in tasks.items():
            out[f"{model} {t}"] = arms(price, round(bugs * req_per_bug), out=o,
                                       open_requests=bugs + 2)  # fmt: skip
    out["check_done_L60_sonnet"] = {s: arms("sonnet-5.5", 339, open_requests=62, scenario=s)["S"]
                                    for s in CHECK_DONE}  # fmt: skip
    out["launch_smoke_haiku"] = expected("haiku", 3, 2, ("N", "Ne", "S"), 67_000)
    out["launch_gate"] = {m: expected(m, 60, 2, ("N",), 160_000) for m in ("sonnet", "opus")}
    out["power_cost"] = {
        f"sd{sd} eff{eff}": {n: power_cost(sd, eff, n) for n in (6, 8, 12, 16, 20, 24)}
        for sd in (0.30, 0.38, 0.48) for eff in (0.55, 0.70, 0.80, 0.90)
    }
    out["ci_halfwidth_x"] = {f"sd{sd}": {n: halfwidth(sd, n) for n in (6, 12, 16, 20, 24)}
                             for sd in (0.30, 0.38, 0.48)}  # fmt: skip
    out["ni_power"] = {
        f"chains{c} margin{m} deff{d}": ni_power(c, 50, 0.18, d, m / 100)
        for c in (6, 12, 16, 20, 24) for m in (2, 5) for d in (1.0, 2.0)
    }
    print(json.dumps(out, indent=1))
