"""Phase D: validate the drawn SWE-bench images before sealing. Free: Docker only, no session.

    python benchmarks/adopt_d/validate_d.py run [--limit N]   # validate, resuming where it stopped
    python benchmarks/adopt_d/validate_d.py summary           # rewrite the output's summary only

As `docs/results/2026-10-03-adopt-d/prereg.md` specifies ("Validation before sealing", and "The
runner", item 7). For each drawn instance of `singles-d.json`, in table order, one at a time (the
disk is nearly full): pull its image, export a working copy as the runner does
(`docker_env.export`), and run the official harness (`run_swe.py`, as `singles_run.grade` does)
with the gold patch (must resolve) and with an empty patch (must not resolve). An instance fails
when its image does not pull, the export fails, the gold patch does not resolve or the empty
patch does. A failed instance is replaced by its stratum's next spare that passes, in spare order.

The empty patch. SWE-bench's harness does not run an empty prediction: it lists it under
`empty_patch_ids` of its run report and starts no container, so "not resolved" is true by
definition and tests nothing. Both are run: the literal empty patch (`empty_literal`: must not be
in the run report's `resolved_ids`) and `NOOP_PATCH`, a patch that only adds a text file outside
every package, which the harness does run (`empty`: must not resolve; its FAIL_TO_PASS and
PASS_TO_PASS counts are recorded, so a no-op that breaks a PASS_TO_PASS test shows).

Recorded beside, deciding nothing: whether the gold patch applies to the exported working copy
(`git apply --check`), i.e. whether a diff taken against the runner's copy is gradable.

Resumable: every finished instance is written to `singles-validated.json` at once, and a restart
skips what is there. A harness or Docker failure that is not the instance's (Docker not answering,
a pull that fails for want of network, no report twice) stops the run with nothing recorded for
that instance, so running again retries it for free. Refuses to run once the prereg is sealed
(`prereg.sha256` exists). Drops each image after its instance, and only images it pulled itself
(`pulled.json` remembers them across a crash). Scratch and harness output live under `VD`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "benchmarks" / "adopt"))

import docker_env  # noqa: E402
import singles_run  # noqa: E402

DRAWN = HERE / "singles-d.json"
OUT = HERE / "singles-validated.json"
PREREG = REPO / "docs" / "results" / "2026-10-03-adopt-d"
SEAL = PREREG / "prereg.sha256"
VD = Path.home() / ".cache" / "sanchopanza" / "adopt" / "validate-d"
LOG = VD / "validate.log"
PULLED = VD / "pulled.json"
DATASET = "SWE-bench/SWE-bench_Verified"
MIN_FREE_GB = 12.0  # below this before a pull, stop: a SWE-bench image is 2 to 8 GB
HARNESS_TIMEOUT_S = 3600
NOOP_NAME = "adopt_d_noop_patch.txt"
NOOP_PATCH = (
    f"diff --git a/{NOOP_NAME} b/{NOOP_NAME}\n"
    "new file mode 100644\n"
    "index 0000000..0b8ef2b\n"
    "--- /dev/null\n"
    f"+++ b/{NOOP_NAME}\n"
    "@@ -0,0 +1 @@\n"
    "+no-op patch: the image's code unchanged\n"
)
# A pull error with one of these is the image's (it does not exist); any other is the network's.
IMAGE_MISSING = ("not found", "manifest unknown", "pull access denied", "repository does not exist")


class Stop(Exception):
    """A failure that is not the instance's: stop, record nothing, a restart retries."""


# ---------------------------------------------------------------------------- pure logic


def seal_refusal(seal: Path | None = None) -> str | None:
    seal = SEAL if seal is None else seal  # read at call time, not bound at import
    if seal.exists():
        return f"{seal.name} exists: phase D is sealed and its validation is closed"
    return None


def walk(
    drawn: dict[str, Any], results: dict[str, dict[str, Any]]
) -> tuple[str | None, dict[str, Any]]:
    """The next instance to validate (None when done), and the selection so far.

    Held instances in table order; each failed one is replaced by its stratum's next spare that
    passes, in spare order (a spare that fails is skipped for good). A stratum that runs out of
    spares is short, and says so."""
    pointer = {s: 0 for s in drawn["spares"]}
    selected: list[dict[str, Any]] = []
    replacements: list[dict[str, Any]] = []
    shortfall: dict[str, int] = {}
    for held in drawn["held"]:
        name, stratum = held["instance_id"], held["stratum"]
        if name not in results:
            return name, {}
        if results[name]["pass"]:
            selected.append({**entry(held), "drawn_as": "held", "replaces": None})
            continue
        spares = drawn["spares"][stratum]
        tried: list[dict[str, Any]] = []
        chosen = None
        while pointer[stratum] < len(spares):
            spare = spares[pointer[stratum]]
            sid = spare["instance_id"]
            if sid not in results:
                return sid, {}
            pointer[stratum] += 1
            if results[sid]["pass"]:
                chosen = spare
                break
            tried.append({"instance_id": sid, "reason": results[sid]["reason"]})
        replacements.append({"stratum": stratum, "failed": name, "reason": results[name]["reason"],
                             "replaced_by": chosen["instance_id"] if chosen else None,
                             "spares_failed_first": tried})  # fmt: skip
        if chosen:
            selected.append({**entry(chosen), "drawn_as": "spare", "replaces": name})
        else:
            shortfall[stratum] = shortfall.get(stratum, 0) + 1
    return None, {"selected": selected, "replacements": replacements, "shortfall": shortfall}


def entry(row: dict[str, Any]) -> dict[str, Any]:
    keys = ("instance_id", "stratum", "repo", "difficulty", "image")
    return {k: row[k] for k in keys}


def role_of(drawn: dict[str, Any], name: str) -> dict[str, Any]:
    for row in drawn["held"]:
        if row["instance_id"] == name:
            return {**entry(row), "role": "held"}
    for rows in drawn["spares"].values():
        for k, row in enumerate(rows):
            if row["instance_id"] == name:
                return {**entry(row), "role": f"spare {k + 1}"}
    raise KeyError(name)


def verdict(steps: dict[str, Any]) -> str | None:
    """Why an instance fails (None: it passes), from its recorded steps, first failure first."""
    if not steps["pull"]["ok"]:
        return f"image did not pull: {steps['pull']['error']}"
    if not steps["export"]["ok"]:
        return f"export failed: {steps['export']['error']}"
    gold = steps["gold"]
    if not gold["report"]:
        return "gold patch: no report from the harness (twice)"
    if not gold["resolved"]:
        return "gold patch does not resolve"
    literal = steps["empty_literal"]
    if not literal["report"]:
        return "empty patch (literal): no run report from the harness (twice)"
    if literal["resolved"]:
        return "empty patch (literal) resolves"
    empty = steps["empty"]
    if not empty["report"]:
        return "empty (no-op) patch: no report from the harness (twice)"
    if empty["resolved"]:
        return "empty (no-op) patch resolves"
    return None


def load(path: Path = OUT) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return {r["instance_id"]: r for r in json.loads(path.read_text("utf-8"))["results"]}


# ---------------------------------------------------------------------------- side effects


def log(line: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    text = f"{stamp} {line}"
    VD.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(text + "\n")
        f.flush()
    print(text, flush=True)


def write_out(drawn: dict[str, Any], results: dict[str, dict[str, Any]]) -> None:
    pending, selection = walk(drawn, results)
    data = {
        "prereg": "docs/results/2026-10-03-adopt-d/prereg.md, 'Validation before sealing'",
        "drawn": f"benchmarks/adopt_d/{DRAWN.name} (sha256 {sha256(DRAWN)})",
        "harness": harness_record(),
        "noop_patch": NOOP_PATCH,
        "complete": pending is None,
        "next": pending,
        **({"selected": selection["selected"], "replacements": selection["replacements"],
            "shortfall": selection["shortfall"],
            "selected_per_stratum": per_stratum(selection["selected"])} if pending is None
           else {}),  # fmt: skip
        "results": sorted(results.values(), key=lambda r: r["order"]),
    }
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8",
                   newline="\n")  # fmt: skip
    os.replace(tmp, OUT)


def per_stratum(selected: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in selected:
        out[row["stratum"]] = out.get(row["stratum"], 0) + 1
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def harness_record() -> dict[str, Any]:
    dist = sorted(p.name for p in (singles_run.SWE_PYTHON.parents[1] / "Lib" / "site-packages")
                  .glob("swebench-*.dist-info"))  # fmt: skip
    return {"run_swe.py_sha256": sha256(singles_run.SWE / "run_swe.py"), "dist": dist,
            "dataset": DATASET}  # fmt: skip


def pulled() -> set[str]:
    return set(json.loads(PULLED.read_text("utf-8"))) if PULLED.exists() else set()


def set_pulled(images: set[str]) -> None:
    PULLED.write_text(json.dumps(sorted(images)), encoding="utf-8")


def docker_alive() -> bool:
    try:
        return docker_env.docker("info", "--format", "{{.ServerVersion}}", timeout=60).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def image_size_gb(image: str) -> float | None:
    done = docker_env.docker("image", "inspect", "-f", "{{.Size}}", image)
    text = done.stdout.decode().strip()
    return round(int(text) / 1e9, 2) if done.returncode == 0 and text.isdigit() else None


def pull_step(image: str) -> dict[str, Any]:
    began = time.time()
    existed = docker_env.docker("image", "inspect", image).returncode == 0
    ours = image in pulled()
    if not existed:
        set_pulled(pulled() | {image})  # before the pull: a crash mid-pull still drops it
        ours = True
        for attempt in range(2):
            try:
                docker_env.pull(image)
                break
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                error = str(exc)[-300:]
                if any(k in error.lower() for k in IMAGE_MISSING):
                    return {"ok": False, "error": error, "existed_before": False, "ours": True,
                            "s": round(time.time() - began, 1)}  # fmt: skip
                if attempt == 1:
                    raise Stop(f"pull {image} failed twice, not for a missing image: {error}")
                time.sleep(60)
    return {"ok": True, "existed_before": existed and not ours, "ours": ours,
            "size_gb": image_size_gb(image), "s": round(time.time() - began, 1)}  # fmt: skip


def export_step(image: str, name: str, gold: str) -> dict[str, Any]:
    began = time.time()
    work = VD / "work" / name
    docker_env.remove_tree(work)
    try:
        base = docker_env.export(image, work)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        docker_env.remove_tree(work)
        return {"ok": False, "error": str(exc)[-300:], "s": round(time.time() - began, 1)}
    patch = VD / "work" / f"{name}.gold.patch"
    patch.write_text(gold, encoding="utf-8", newline="\n")
    check = subprocess.run(["git", "-C", str(work), "apply", "--check", str(patch)],
                           capture_output=True, text=True, errors="replace")  # fmt: skip
    files = sum(1 for path in work.rglob("*") if ".git" not in path.parts and path.is_file())
    patch.unlink()
    docker_env.remove_tree(work)
    return {"ok": True, "base": base, "files": files,
            "gold_applies_to_export": check.returncode == 0,
            **({"gold_apply_error": check.stderr.strip()[-300:]} if check.returncode else {}),
            "s": round(time.time() - began, 1)}  # fmt: skip


def harness(name: str, kind: str, patch: str | None) -> dict[str, Any]:
    """One harness run. `patch` None: the dataset's gold patch (`-p gold`)."""
    began = time.time()
    cwd = VD / "harness"
    cwd.mkdir(parents=True, exist_ok=True)
    run_id = f"vd-{kind}-{int(time.time())}"
    model = "gold" if patch is None else f"validate-d-{kind}"
    preds = "gold"
    if patch is not None:
        path = cwd / f"{name}.{kind}.preds.jsonl"
        path.write_text(json.dumps({"instance_id": name, "model_name_or_path": model,
                                    "model_patch": patch}) + "\n",
                        encoding="utf-8", newline="\n")  # fmt: skip
        preds = str(path)
    cmd = [str(singles_run.SWE_PYTHON), str(singles_run.SWE / "run_swe.py"), "-d", DATASET,
           "-p", preds, "-i", name, "--max_workers", "1", "-id", run_id,
           "--report_dir", str(cwd / "run-reports")]  # fmt: skip
    try:
        done = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=HARNESS_TIMEOUT_S,
                              env={**os.environ, "PYTHONUTF8": "1"})  # fmt: skip
        (cwd / f"{run_id}.out").write_bytes(done.stdout + b"\n--- stderr\n" + done.stderr)
        code = done.returncode
    except subprocess.TimeoutExpired:
        code = -9
    report = cwd / "logs" / "run_evaluation" / run_id / model / name / "report.json"
    run_report = cwd / "run-reports" / f"{model}.{run_id}.json"
    out: dict[str, Any] = {"run_id": run_id, "exit": code, "s": round(time.time() - began, 1)}
    if kind == "empty_literal":
        if not run_report.exists():
            return {**out, "report": False, "resolved": False}
        summary = json.loads(run_report.read_text("utf-8"))
        return {**out, "report": True, "resolved": name in summary.get("resolved_ids", []),
                "in_empty_patch_ids": name in summary.get("empty_patch_ids", []),
                "submitted": summary.get("submitted_instances"),
                "completed": summary.get("completed_instances")}  # fmt: skip
    if not report.exists():
        return {**out, "report": False, "resolved": False}
    row = json.loads(report.read_text("utf-8")).get(name, {})
    status = row.get("tests_status", {})
    counts = {f"{k.lower()}_{s}": len(status.get(k, {}).get(s, []))
              for k in ("FAIL_TO_PASS", "PASS_TO_PASS") for s in ("success", "failure")}
    if row.get("infra_failure"):
        return {**out, "report": False, "resolved": False, "infra_failure": True, **counts}
    return {**out, "report": True, "resolved": bool(row.get("resolved")),
            "applied": row.get("patch_successfully_applied"), **counts}  # fmt: skip


def harness_twice(name: str, kind: str, patch: str | None) -> dict[str, Any]:
    first = harness(name, kind, patch)
    log(f"{name} {kind}: report {first['report']} resolved {first['resolved']} "
        f"({first['s']} s, {first['run_id']})")  # fmt: skip
    if first["report"]:
        return first
    if not docker_alive():
        raise Stop(f"{name} {kind}: no report and Docker does not answer")
    second = harness(name, kind, patch)
    log(f"{name} {kind} (again): report {second['report']} resolved {second['resolved']} "
        f"({second['s']} s, {second['run_id']})")  # fmt: skip
    if not second["report"] and not docker_alive():
        raise Stop(f"{name} {kind}: no report twice and Docker does not answer")
    return {**second, "first_attempt": first}


def validate(name: str, image: str, gold: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Steps of one instance (pull, export, gold, empty), the image dropped after if ours."""
    steps: dict[str, Any] = {}
    steps["pull"] = pull_step(image)
    log(f"{name} pull: ok {steps['pull']['ok']} size {steps['pull'].get('size_gb')} GB "
        f"existed_before {steps['pull']['existed_before']} ({steps['pull']['s']} s)")  # fmt: skip
    extra: dict[str, Any] = {"image_size_gb": steps["pull"].get("size_gb")}
    try:
        if steps["pull"]["ok"]:
            steps["export"] = export_step(image, name, gold)
            log(f"{name} export: ok {steps['export']['ok']} "
                f"gold applies {steps['export'].get('gold_applies_to_export')} "
                f"({steps['export']['s']} s)")  # fmt: skip
        if steps.get("export", {}).get("ok"):
            steps["gold"] = harness_twice(name, "gold", None)
            if steps["gold"]["resolved"]:
                steps["empty_literal"] = harness_twice(name, "empty_literal", "")
                steps["empty"] = harness_twice(name, "empty", NOOP_PATCH)
    finally:
        if steps["pull"].get("ours"):
            docker_env.drop(image)
            gone = docker_env.docker("image", "inspect", image).returncode != 0
            if gone:
                set_pulled(pulled() - {image})
            extra["dropped"] = gone
            log(f"{name} drop image: removed {gone}")
        else:
            extra["dropped"] = False
            log(f"{name} drop image: kept (it was here before this script pulled anything)")
    return steps, extra


def gold_patches(names: list[str]) -> dict[str, str]:
    import pyarrow.parquet as pq

    table = pq.read_table(Path.home() / ".cache" / "sanchopanza" / "find" / "swebench" /
                          "verified.parquet", columns=["instance_id", "patch"])  # fmt: skip
    wanted = set(names)
    return {r["instance_id"]: r["patch"] for r in table.to_pylist() if r["instance_id"] in wanted}


def every_name(drawn: dict[str, Any]) -> list[str]:
    names = [r["instance_id"] for r in drawn["held"]]
    return names + [r["instance_id"] for rows in drawn["spares"].values() for r in rows]


def run(limit: int | None) -> int:
    if why := seal_refusal():
        raise SystemExit(why)
    drawn = json.loads(DRAWN.read_text("utf-8"))
    images = singles_run.rows()
    golds = gold_patches(every_name(drawn))
    results = load()
    done_now = 0
    log(f"start: {len(results)} validated before, limit {limit}")
    while True:
        if why := seal_refusal():
            raise SystemExit(why)
        name, _ = walk(drawn, results)
        if name is None:
            write_out(drawn, results)
            log("VALIDATION DONE: every stratum settled")
            return 0
        if limit is not None and done_now >= limit:
            log(f"VALIDATION PAUSED: limit {limit} reached, next {name}")
            return 0
        if not docker_alive():
            log("VALIDATION STOP: Docker does not answer")
            return 2
        free = docker_env.disk_free_gb()
        if free < MIN_FREE_GB:
            log(f"VALIDATION STOP: {free:.1f} GB free, under {MIN_FREE_GB}")
            return 3
        info = role_of(drawn, name)
        image = images[name]["image"]
        log(f"{name} begin ({info['stratum']}, {info['role']}), {free:.1f} GB free")
        began = time.time()
        try:
            steps, extra = validate(name, image, golds[name])
        except Stop as exc:
            log(f"VALIDATION STOP: {exc}")
            return 4
        reason = verdict(steps)
        record = {**info, "order": len(results) + 1, "pass": reason is None, "reason": reason,
                  "steps": steps, **extra, "duration_s": round(time.time() - began, 1),
                  "disk_free_gb_after": round(docker_env.disk_free_gb(), 1),
                  "at": time.strftime("%Y-%m-%dT%H:%M:%S")}  # fmt: skip
        results = {**results, name: record}
        write_out(drawn, results)
        done_now += 1
        log(f"{name} {'PASS' if reason is None else 'FAIL: ' + reason} "
            f"({record['duration_s']} s, {record['disk_free_gb_after']} GB free)")  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("run", "summary"))
    parser.add_argument("--limit", type=int, default=None, help="validate at most N instances")
    args = parser.parse_args(argv)
    if args.action == "summary":
        if why := seal_refusal():
            raise SystemExit(why)
        drawn = json.loads(DRAWN.read_text("utf-8"))
        write_out(drawn, load())
        print(json.dumps(walk(drawn, load())[0]))
        return 0
    if shutil.which("docker") is None:
        raise SystemExit("docker is not on PATH")
    return run(args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
