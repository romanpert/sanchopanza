"""Browse, development: where a playwright-cli session's money goes (Phases 3k and 3m).

python benchmarks/browse/cli_cost.py OUT.json   # free: reads the sessions' Claude Code transcripts

Per turn usage from each transcript, priced at list rates (it rebuilds 15.10 of the 15.24 USD
recorded); tool results by kind, the playwright-cli banner, and the paired noise. Written by a
read-only analysis on 2026-10-02 and kept as it ran, so the README's numbers can be redone.
"""

import collections
import glob
import json
import os
import pathlib
import re
import statistics as st
import sys

RES = str(pathlib.Path(__file__).resolve().parents[2] / "docs/results/2026-09-30-browse") + "/"
PROJ = os.path.expanduser("~/.claude/projects/")
P = {"in": 2.0e-6, "w1h": 4.0e-6, "w5m": 2.5e-6, "read": 0.2e-6, "out": 10.0e-6}
BANNER_RE = re.compile(r"^╔.*?╝\n\n", re.S)


def folder_for(workdir):
    return re.sub(r"[:\\/_.]", "-", workdir)


def text_of(content):
    if isinstance(content, str):
        return content
    parts = []
    for c in content or []:
        if isinstance(c, dict):
            parts.append(c.get("text") or json.dumps(c))
    return "\n".join(parts)


def tool_kind(name, inp):
    if name == "Bash":
        cmd = inp.get("command", "")
        m = re.search(r"playwright-cli\s+(?:-s=\S+\s+)?(\S+)", cmd)
        sub = m.group(1) if m else cmd.split()[0] if cmd else "?"
        if "|" in cmd or ">" in cmd:
            sub += "+pipe"
        return "cli:" + sub, cmd[:120]
    if name == "Read":
        fp = inp.get("file_path", "")
        kind = (
            "Read:yml"
            if fp.endswith(".yml")
            else ("Read:persisted" if "tool-results" in fp or "persist" in fp else "Read:other")
        )
        return kind, fp[-90:]
    return name, json.dumps(inp)[:120]


def parse(path):
    turns, order, calls, results = {}, [], {}, []
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        if d.get("isSidechain"):
            continue
        t = d.get("type")
        if t == "assistant":
            m = d["message"]
            mid = m.get("id")
            if mid not in turns:
                u = m.get("usage") or {}
                cc = u.get("cache_creation") or {}
                turns[mid] = {
                    "in": u.get("input_tokens", 0),
                    "cw": u.get("cache_creation_input_tokens", 0),
                    "cw1h": cc.get("ephemeral_1h_input_tokens", 0),
                    "cw5m": cc.get("ephemeral_5m_input_tokens", 0),
                    "cr": u.get("cache_read_input_tokens", 0),
                    "out": u.get("output_tokens", 0),
                    "think": (u.get("output_tokens_details") or {}).get("thinking_tokens", 0),
                    "calls": [],
                    "model": m.get("model"),
                }
                order.append(mid)
            for c in m.get("content", []):
                if c.get("type") == "tool_use":
                    k, head = tool_kind(c["name"], c.get("input") or {})
                    calls[c["id"]] = {"turn": len(order) - 1, "kind": k, "head": head}
                    turns[mid]["calls"].append(c["id"])
        elif t == "user":
            c = d["message"]["content"]
            if isinstance(c, list):
                for x in c:
                    if x.get("type") == "tool_result":
                        s = text_of(x.get("content"))
                        b = BANNER_RE.match(s)
                        info = calls.get(x["tool_use_id"], {"kind": "?", "head": "", "turn": -1})
                        results.append(
                            {
                                **info,
                                "chars": len(s),
                                "banner": len(b.group(0)) if b else 0,
                                "persisted": "Output too large" in s
                                or "persisted" in s.lower()[:400],
                                "err": bool(x.get("is_error")),
                            }
                        )
    return [turns[k] for k in order], results


def cost(t):
    return (
        t["in"] * P["in"]
        + t["cw1h"] * P["w1h"]
        + t["cw5m"] * P["w5m"]
        + (t["cw"] - t["cw1h"] - t["cw5m"]) * P["w1h"]
        + t["cr"] * P["read"]
        + t["out"] * P["out"]
    )


def extract(out):
    sessions = []
    for phase, fn in (("3k", "e2e-cli-y-sessions.jsonl"), ("3m", "e2e-cli-z-sessions.jsonl")):
        for line in pathlib.Path(RES + fn).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            hits = glob.glob(PROJ + folder_for(row["workdir"]) + "/*.jsonl")
            if not hits:
                sessions.append(
                    {
                        "phase": phase,
                        **{k: row[k] for k in ("task", "run", "arm", "list_usd")},
                        "missing": True,
                    }
                )
                continue
            turns, results = parse(max(hits, key=os.path.getsize))
            sessions.append(
                {
                    "phase": phase,
                    "task": row["task"],
                    "run": row["run"],
                    "arm": row["arm"],
                    "success": row["success"],
                    "list_usd": row["list_usd"],
                    "turns": turns,
                    "results": results,
                    "est_usd": sum(cost(t) for t in turns),
                }
            )
    pathlib.Path(out).write_text(json.dumps(sessions, indent=0), encoding="utf-8")
    print("sessions", len(sessions), "missing", sum(1 for s in sessions if s.get("missing")))


def report(path):
    S = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    P_ = {"in": 2.0e-6, "w": 4.0e-6, "read": 0.2e-6, "out": 10.0e-6}
    S = [s for s in S if s["run"] > 0]
    print("sessions", len(S), collections.Counter((s["phase"], s["arm"]) for s in S))

    # 1. Cost composition
    tot = collections.Counter()
    for s in S:
        for i, t in enumerate(s["turns"]):
            tot["read"] += t["cr"] * P_["read"]
            tot["out"] += t["out"] * P_["out"]
            tot["think_out"] += t["think"] * P_["out"]
            tot["in"] += t["in"] * P_["in"]
            key = "write_turn1" if i == 0 else "write_later"
            tot[key] += t["cw"] * P_["w"]
            tot["read_base"] += (
                min(t["cr"], s["turns"][0]["cr"]) * P_["read"]
            )  # globally cached prefix
            tot["read_session_prefix"] += (
                min(t["cr"], s["turns"][0]["cr"] + s["turns"][0]["cw"]) * P_["read"]
            )
    est = sum(tot[k] for k in ("read", "out", "in", "write_turn1", "write_later"))
    lst = sum(s["list_usd"] for s in S)
    print(f"est {est:.3f} list {lst:.3f}  per session est {est / len(S):.4f}")
    for k, v in tot.items():
        print(f"  {k:22s} {v:.3f}  {100 * v / est:.1f}%")

    # turn1 prefix sizes
    t1cr = [s["turns"][0]["cr"] for s in S]
    t1cw = [s["turns"][0]["cw"] for s in S]
    print("turn1 cache_read median", st.median(t1cr), "min", min(t1cr), "max", max(t1cr))
    print("turn1 cache_write median", st.median(t1cw), "min", min(t1cw), "max", max(t1cw))
    nturns = [len(s["turns"]) for s in S]
    print(
        "API turns/session median",
        st.median(nturns),
        "mean",
        round(st.mean(nturns), 2),
        "max",
        max(nturns),
    )

    # 2. Page-content attribution: tokens of tool results enter as later writes + get re-read.
    # Each later turn's write ~ (results chars of the turn before) / cpt + out_prev + overhead.
    res_chars = sum(r["chars"] for s in S for r in s["results"])
    banner_chars = sum(r["banner"] for s in S for r in s["results"])
    nres = sum(len(s["results"]) for s in S)
    later_w = sum(t["cw"] for s in S for t in s["turns"][1:])
    out_tok = sum(t["out"] for s in S for t in s["turns"])
    print(
        f"tool results {nres}, chars {res_chars}, banner chars {banner_chars} "
        f"({100 * banner_chars / res_chars:.1f}%), "
        f"later-turn writes {later_w} tok, outputs {out_tok} tok"
    )

    # chars-per-token fit: for turn k>=1, cw_k ~ out_{k-1} + a*nonbanner_chars + b*nbanner + c

    def lstsq(X, y):
        n = len(X[0])
        A = [[sum(r[i] * r[j] for r in X) for j in range(n)] for i in range(n)]
        b = [sum(r[i] * v for r, v in zip(X, y, strict=False)) for i in range(n)]
        for i in range(n):
            piv = A[i][i]
            for j in range(i + 1, n):
                f = A[j][i] / piv
                A[j] = [a - f * c for a, c in zip(A[j], A[i], strict=False)]
                b[j] -= f * b[i]
        x = [0.0] * n
        for i in reversed(range(n)):
            x[i] = (b[i] - sum(A[i][j] * x[j] for j in range(i + 1, n))) / A[i][i]
        return x

    def corr(a, b):
        ma, mb = st.mean(a), st.mean(b)
        return sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=False)) / (
            (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
        )

    X, y = [], []
    for s in S:
        byturn = collections.defaultdict(lambda: [0, 0])
        for r in s["results"]:
            byturn[r["turn"]][0] += r["chars"] - r["banner"]
            byturn[r["turn"]][1] += 1 if r["banner"] else 0
        for k in range(1, len(s["turns"])):
            nb, nbn = byturn.get(k - 1, [0, 0])
            X.append([nb, nbn, 1.0])
            y.append(s["turns"][k]["cw"] - s["turns"][k - 1]["out"])
    coef = lstsq(X, y)
    print(
        f"fit tokens = {coef[0]:.3f}*chars + {coef[1]:.1f}*banners + {coef[2]:.1f}"
        f"  (chars/token {1 / coef[0]:.2f})"
    )

    # 3. Tool outputs by kind
    kinds = collections.defaultdict(list)
    for s in S:
        for r in s["results"]:
            kinds[r["kind"]].append(r["chars"])
    print("\nkind                 n   per_sess  median   p90     max    sum_chars")
    for k, v in sorted(kinds.items(), key=lambda kv: -sum(kv[1])):
        v2 = sorted(v)
        print(
            f"{k:20s} {len(v):4d} {len(v) / len(S):6.2f} {st.median(v2):8.0f} "
            f"{v2[int(0.9 * (len(v2) - 1))]:7d} {max(v2):7d} {sum(v2):9d}"
        )
    big = [
        (s["task"], s["arm"], r["kind"], r["chars"], r["persisted"])
        for s in S
        for r in s["results"]
        if r["chars"] > 10000
    ]
    print("results >10k chars:", len(big), "persisted flag:", sum(1 for b in big if b[4]))
    print(
        "results with persisted marker:", sum(1 for s in S for r in s["results"] if r["persisted"])
    )

    # Re-read multiplier: a token written at turn k is re-read in turns k+1..end
    def content_cost(s, chars_by_turn, cpt):
        n = len(s["turns"])
        c = 0.0
        for k, ch in chars_by_turn.items():
            tok = ch / cpt
            remaining = max(n - (k + 1) - 1, 0)  # written at turn k+1, read after
            c += tok * P_["w"] + tok * remaining * P_["read"]
        return c

    cpt = 1 / coef[0]
    bann_tok = coef[1]
    page_usd = bann_usd = 0.0
    for s in S:
        cb = collections.Counter()
        bb = collections.Counter()
        for r in s["results"]:
            if r["turn"] >= 0:
                cb[r["turn"]] += r["chars"] - r["banner"]
                bb[r["turn"]] += 1 if r["banner"] else 0
        page_usd += content_cost(s, cb, cpt)
        n = len(s["turns"])
        for k, nb in bb.items():
            remaining = max(n - (k + 1) - 1, 0)
            bann_usd += nb * bann_tok * (P_["w"] + remaining * P_["read"])
    print(
        f"\npage content (non-banner tool results) est {page_usd:.3f} = "
        f"{100 * page_usd / est:.1f}% ; banners {bann_usd:.3f} = {100 * bann_usd / est:.1f}%"
    )

    # 4. Variance
    for ph in ("3k", "3m"):
        for arm in ("PLAIN", "LEAN"):
            v = [s["list_usd"] for s in S if s["phase"] == ph and s["arm"] == arm]
            print(
                ph,
                arm,
                "n",
                len(v),
                f"mean {st.mean(v):.4f} sd {st.stdev(v):.4f}",
                "se %.4f" % (st.stdev(v) / len(v) ** 0.5),
            )
    # within-task paired SD
    pairs = collections.defaultdict(dict)
    for s in S:
        pairs[(s["phase"], s["task"], s["run"])][s["arm"]] = s["list_usd"]
    d = [p["LEAN"] - p["PLAIN"] for p in pairs.values() if len(p) == 2]
    print(
        "paired LEAN-PLAIN n",
        len(d),
        f"mean {st.mean(d):.4f} sd {st.stdev(d):.4f} se {st.stdev(d) / len(d) ** 0.5:.4f}",
    )
    # within task cv
    cvs = []
    bytask = collections.defaultdict(list)
    for s in S:
        bytask[(s["phase"], s["task"], s["arm"])].append(s["list_usd"])
    for v in bytask.values():
        if len(v) > 1:
            cvs.append(st.stdev(v) / st.mean(v))
    print(f"within task/arm CV median {st.median(cvs):.2f} mean {st.mean(cvs):.2f}")
    # per task mean cost and turns
    print("\ntask means (both arms)")
    tm = collections.defaultdict(list)
    for s in S:
        tm[(s["phase"], s["task"])].append(
            (s["list_usd"], len(s["turns"]), sum(r["chars"] for r in s["results"]))
        )
    for k, v in sorted(tm.items()):
        print(
            k,
            "usd {:.3f} turns {:.1f} reschars {:.0f}".format(
                *tuple(st.mean(x[i] for x in v) for i in range(3))
            ),
        )
    # cost vs turns correlation
    xs = [len(s["turns"]) for s in S]
    ys = [s["list_usd"] for s in S]
    print(f"corr(turns, usd) {corr(xs, ys):.2f}")
    rc = [sum(r["chars"] for r in s["results"]) for s in S]
    print(f"corr(result chars, usd) {corr(rc, ys):.2f}")
    think = sum(t["think"] for s in S for t in s["turns"])
    print("thinking tokens", think, "of output", out_tok)


if __name__ == "__main__":
    extract(sys.argv[1])
    report(sys.argv[1])
