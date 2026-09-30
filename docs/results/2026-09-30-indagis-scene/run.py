"""The Indagis scene: Claude Code alone against Claude Code with sanchopanza, on a real Indagis bug.

    python run.py plan                 # free: arms, reps, caps, the estimate
    python run.py check                # free: the acceptance test fails at base, passes on the fix
    python run.py run                  # subscription sessions, capped (prereg-scene.md)
    python run.py score                # free

Each repetition is a fresh git worktree of Indagis at the base commit, one headless Claude Code
session, then the hidden acceptance test and the harness suite. Worktrees are removed at the
end; nothing is committed to Indagis.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

# `sanchopanza install` as it was when this ran: the defaults grew on 2026-09-30 (guard,
# context budget, find_in_repo, skill), so a rerun opts out of them to measure the same arms.
PRE_0930 = ["--no-guard", "--no-find", "--no-skill", "--context-budget", "0"]

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
INDAGIS = Path(r"C:\Users\roman\Desktop\proyectos\apps\indagis")
PYTHON_INDAGIS = INDAGIS / ".venv" / "Scripts" / "python.exe"
PYTHON = REPO / ".venv" / "Scripts" / "python.exe"
SANCHO = REPO / ".venv" / "Scripts" / "sanchopanza.exe"
ROOT = Path.home() / ".cache" / "sanchopanza" / "indagis-scene"
BASE = "6ca4e57"  # parent of 3a0e243, the real fix
FIX = "3a0e243"
MODEL = "claude-sonnet-5-5"
ARMS = ("solo", "sancho")
REPS = 3
SESSION_CAP_USD = 1.50  # --max-budget-usd of each session
CEILING_USD = 9.00  # list price of every session; the scene's hard cap is 10
MAX_TURNS = 60
TIMEOUT_S = 1800
TOOLS = ("Read", "Edit", "Write", "Grep", "Glob", "Bash")
ACCEPTANCE = "agent/harness/tests/test_zz_aceptacion_escena.py"
PROMPT = (
    "En agent/harness hay un fallo: la herramienta MCP `declarar_parada` "
    "(agent/harness/herramientas/servidor.py) contesta \"Anotado en el informe\" pero no guarda "
    "nada, y `avisos_parada` del resultado que escribe agent/harness/entrada.py solo recoge los "
    "diales agotados. Arreglalo para que lo que el agente declare llegue a `avisos_parada`, una "
    "sola vez aunque se declare dos veces, y sin romperse si falta algun campo. Para poder "
    "probarlo sin claude_agent_sdk (que no esta instalado aqui), expon en servidor.py "
    "`registrar_parada(args: dict) -> str` (anota y devuelve el texto del aviso) y "
    "`paradas_declaradas() -> tuple[str, ...]`. Anade tests en agent/harness/tests/. La suite "
    "del arnes se corre asi, desde la raiz del repo: `{python} -m pytest agent/harness/tests -q "
    "-p no:cacheprovider` (PYTHONPATH ya apunta a la raiz). No hagas commit."
)


def _rows() -> list[dict[str, Any]]:
    path = HERE / "runs.jsonl"
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def spent() -> float:
    """Every session paid, the voided ones of amendment 1 (`void.jsonl`) included."""
    void = HERE / "void.jsonl"
    voided = [json.loads(x) for x in void.read_text(encoding="utf-8").splitlines()
              if x.strip()] if void.exists() else []  # fmt: skip
    return sum(float(r.get("cost_usd") or 0.0) for r in [*_rows(), *voided])


def worktree(name: str) -> Path:
    target = ROOT / "work" / name
    if target.exists():
        subprocess.run(["git", "-C", str(INDAGIS), "worktree", "remove", "--force", str(target)],
                       capture_output=True)  # fmt: skip
        shutil.rmtree(target, ignore_errors=True)
    subprocess.run(["git", "-C", str(INDAGIS), "worktree", "prune"], check=True)
    subprocess.run(["git", "-C", str(INDAGIS), "worktree", "add", "-q", "--detach", str(target),
                    BASE], check=True)  # fmt: skip
    return target


def settings(evidence: Path, keyfile: Path) -> Path:
    """`sanchopanza install --candor` settings, each hook run through hook_key.py."""
    raw = ROOT / "install-settings.json"
    if not raw.exists():
        subprocess.run([str(SANCHO), "install", *PRE_0930, "--candor", "--path", str(raw),
                        "--write"],
                       check=True, capture_output=True)  # fmt: skip
    data = json.loads(raw.read_text(encoding="utf-8"))
    prefix = " ".join(p.as_posix() for p in (PYTHON, HERE / "hook_key.py", evidence, keyfile))
    text = json.dumps(data)
    text = text.replace('"sanchopanza candor-hook"', json.dumps(f"{prefix} candor-hook"))
    text = text.replace('"sanchopanza hook"', json.dumps(f"{prefix} hook"))
    out = evidence / "settings.json"
    out.write_text(text, encoding="utf-8")
    return out


def child_env(work: Path) -> dict[str, str]:
    """The subscription, not a key; no coordinating-session variables; the repo on PYTHONPATH."""
    drop = ("ANTHROPIC_", "CLAUDE_CODE_USE_", "CLAUDE_EFFORT", "CLAUDECODE", "SANCHOPANZA_",
            "TYPESAFE_")  # fmt: skip
    env = {k: v for k, v in os.environ.items() if not k.startswith(drop)}
    return {**env, "PYTHONPATH": str(work)}


def command(arm: str, evidence: Path, keyfile: Path) -> list[str]:
    cmd = ["claude", "-p", PROMPT.format(python=PYTHON_INDAGIS.as_posix()), "--model", MODEL,
           "--max-budget-usd", f"{SESSION_CAP_USD:.2f}", "--max-turns", str(MAX_TURNS),
           "--output-format", "stream-json", "--verbose", "--setting-sources", "project",
           "--strict-mcp-config", "--permission-mode", "dontAsk", "--tools", ",".join(TOOLS),
           "--allowedTools", *TOOLS]  # fmt: skip
    if arm == "sancho":
        cmd += ["--settings", str(settings(evidence, keyfile))]
    return cmd


def grade(work: Path) -> dict[str, Any]:
    """The hidden acceptance test, then the whole harness suite (it included)."""
    shutil.copy(HERE / "acceptance_test.py", work / ACCEPTANCE)
    env = {**child_env(work)}

    def pytest(target: str) -> tuple[bool, str]:
        proc = subprocess.run([str(PYTHON_INDAGIS), "-m", "pytest", target, "-q",
                               "-p", "no:cacheprovider"], cwd=work, env=env, capture_output=True,
                              text=True, encoding="utf-8", timeout=600)  # fmt: skip
        return proc.returncode == 0, (proc.stdout or "").strip().splitlines()[-1:][0:1]

    accepted, acc_tail = pytest(ACCEPTANCE)
    suite, suite_tail = pytest("agent/harness/tests")
    return {"acceptance": accepted, "suite": suite, "acceptance_tail": acc_tail,
            "suite_tail": suite_tail}  # fmt: skip


def stream_facts(stream: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    reads: Counter[str] = Counter()
    calls: Counter[str] = Counter()
    for line in stream.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            result = event
        if event.get("type") != "assistant":
            continue
        for block in (event.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls[str(block.get("name"))] += 1
                if block.get("name") == "Read":
                    reads[str((block.get("input") or {}).get("file_path", "")).lower()] += 1
    usage = result.get("usage") or {}
    return {
        "subtype": result.get("subtype"), "turns": result.get("num_turns"),
        "cost_usd": float(result.get("total_cost_usd") or 0.0),
        "input_tokens": int(usage.get("input_tokens") or 0),
        "cache_read": int(usage.get("cache_read_input_tokens") or 0),
        "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "calls": dict(calls), "tool_calls": sum(calls.values()),
        "rereads": sum(n - 1 for n in reads.values() if n > 1),
        "report": str(result.get("result") or "")[-1500:],
    }  # fmt: skip


def jev_usd(evidence: Path) -> float:
    path = evidence / "journal.jsonl"
    if not path.exists():
        return 0.0
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        total += float((event.get("data") or {}).get("cost_usd") or event.get("cost_usd") or 0.0)
    return total


def one(arm: str, rep: int, keyfile: Path) -> dict[str, Any] | None:
    name = f"{arm}-{rep}"
    if any(r["name"] == name for r in _rows()):
        return None
    if spent() + SESSION_CAP_USD > CEILING_USD:
        sys.stderr.write(f"ceiling: {name} NOT RUN\n")
        return None
    evidence = ROOT / "evidence" / name
    shutil.rmtree(evidence, ignore_errors=True)
    evidence.mkdir(parents=True)
    work = worktree(name)
    started = time.time()
    stream = evidence / "stream.jsonl"
    with stream.open("w", encoding="utf-8") as out:
        try:
            subprocess.run(command(arm, evidence, keyfile), cwd=work, env=child_env(work),
                           stdout=out, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                           timeout=TIMEOUT_S)  # fmt: skip
        except subprocess.TimeoutExpired:
            pass
    seconds = round(time.time() - started, 1)
    diff = subprocess.run(["git", "-C", str(work), "diff", "--stat"], capture_output=True,
                          text=True).stdout  # fmt: skip
    row = {"name": name, "arm": arm, "rep": rep, "seconds": seconds, **stream_facts(stream),
           "jev_usd": round(jev_usd(evidence), 5), **grade(work),
           "diff_stat": diff.strip().splitlines()[-1:] if diff.strip() else []}  # fmt: skip
    (evidence / "diff.patch").write_text(
        subprocess.run(["git", "-C", str(work), "diff"], capture_output=True, text=True,
                       encoding="utf-8").stdout, encoding="utf-8")  # fmt: skip
    with (HERE / "runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    sys.stderr.write(f"{name}: {row['cost_usd']:.3f} USD, accept={row['acceptance']}, "
                     f"suite={row['suite']}, total {spent():.2f}\n")  # fmt: skip
    return row


def check() -> dict[str, Any]:
    """The acceptance test must fail at BASE and pass on the real fix FIX."""
    out = {}
    for label, commit in (("base", BASE), ("fix", FIX)):
        work = ROOT / "work" / f"check-{label}"
        if work.exists():
            subprocess.run(["git", "-C", str(INDAGIS), "worktree", "remove", "--force", str(work)],
                           capture_output=True)  # fmt: skip
        subprocess.run(["git", "-C", str(INDAGIS), "worktree", "add", "-q", "--detach", str(work),
                        commit], check=True)  # fmt: skip
        out[label] = grade(work)
        subprocess.run(["git", "-C", str(INDAGIS), "worktree", "remove", "--force", str(work)],
                       capture_output=True)  # fmt: skip
    return out


def score() -> dict[str, Any]:
    import statistics

    rows = _rows()
    out: dict[str, Any] = {"sessions": len(rows), "spent_usd": round(spent(), 4)}
    for arm in ARMS:
        g = [r for r in rows if r["arm"] == arm]

        def med(key: str, group: list[dict[str, Any]] = g) -> float | None:
            values = [float(r.get(key) or 0) for r in group]
            return round(statistics.median(values), 4) if values else None

        out[arm] = {
            "n": len(g), "success": sum(bool(r["acceptance"] and r["suite"]) for r in g),
            "median_cost_usd": med("cost_usd"), "median_seconds": med("seconds"),
            "median_turns": med("turns"), "median_tool_calls": med("tool_calls"),
            "median_rereads": med("rereads"), "median_output_tokens": med("output_tokens"),
            "median_cache_read": med("cache_read"),
            "jev_usd": round(sum(r["jev_usd"] for r in g), 5),
        }  # fmt: skip
    (HERE / "summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def regrade() -> None:
    """Amendment 1: grade every kept session again with the amended acceptance test, keeping
    the first grade beside it. Voids the rows named in VOID (moved to `void.jsonl`)."""
    kept, voided = [], []
    for row in _rows():
        if row["name"] in VOID:
            voided.append({**row, "void": VOID[row["name"]]})
            continue
        work = ROOT / "work" / row["name"]
        first = {k: row[k] for k in ("acceptance", "suite", "acceptance_tail", "suite_tail")}
        kept.append({**row, **grade(work), "first_grade": row.get("first_grade", first)})
    (HERE / "runs.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")
    if voided:
        with (HERE / "void.jsonl").open("a", encoding="utf-8") as handle:
            handle.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in voided)


VOID = {
    "sancho-2": "held from its first turn by sancho-1's candor lock (one lock file per machine)",
    "sancho-3": "held from its first turn by sancho-1's candor lock (one lock file per machine)",
}


def cleanup() -> None:
    for work in (ROOT / "work").glob("*"):
        subprocess.run(["git", "-C", str(INDAGIS), "worktree", "remove", "--force", str(work)],
                       capture_output=True)  # fmt: skip
    subprocess.run(["git", "-C", str(INDAGIS), "worktree", "prune"], check=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run.py")
    parser.add_argument("step", choices=["plan", "check", "run", "score", "cleanup", "regrade"])
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args(argv)
    if args.step == "plan":
        print(json.dumps({"model": MODEL, "arms": ARMS, "reps": REPS, "base": BASE, "fix": FIX,
                          "session_cap_usd": SESSION_CAP_USD, "ceiling_usd": CEILING_USD,
                          "spent_usd": spent()}, indent=1))  # fmt: skip
    elif args.step == "check":
        print(json.dumps(check(), indent=1))
    elif args.step == "score":
        print(json.dumps(score(), indent=1))
    elif args.step == "cleanup":
        cleanup()
    elif args.step == "regrade":
        regrade()
    else:
        key = os.environ.get("TYPESAFE_API_KEY", "").strip()
        if not key:
            raise SystemExit("the sancho arm needs TYPESAFE_API_KEY in this process's environment")
        keyfile = ROOT / "typesafe.key"
        ROOT.mkdir(parents=True, exist_ok=True)
        keyfile.write_text(key, encoding="utf-8")
        try:
            # Interleaved, so a ceiling cuts both arms alike: solo-1, sancho-1, solo-2, ...
            jobs = [(arm, rep) for rep in range(1, REPS + 1) for arm in ARMS]
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                list(pool.map(lambda j: one(j[0], j[1], keyfile), jobs))
        finally:
            keyfile.unlink(missing_ok=True)
        print(json.dumps(score(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
