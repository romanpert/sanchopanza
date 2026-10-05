# long60 chains: status (2026-10-06, stopped for the day)

Code is committed (`6ea83ea`, branch `long-bench`, not pushed): `long.py` (long60 draw, prompts,
token, callbacks, manifests), `perbug.py` (isolation validation, per-bug grader, dry run),
`run.py` (request sequence, `dry` action, per-bug grade), `validate.py` (dispatch),
`tests/test_adopt_long60.py` (22 tests). Full suite: 3034 passed, 40 skipped (run without
`tests/test_adopt_long_fixes.py`, another session's uncommitted file that breaks collection).

Another session is editing this worktree at the same time (`arm_files.py`, `long_run.py`,
`docker_env.py`, `runtests.py`, parts of `run.py`). Its changes are not in `6ea83ea`.

## Chains

Drawn (`benchmarks/adopt/long60-selected.json`, seed 20261005), none validated yet:

| chain | split | real + synthetic | spares |
|---|---|---|---|
| conan-io__conan-long60-1 | gate | 60 + 0 | 30 |
| pydantic__pydantic-long60-1 | gate | 25 + 35 | 20 |
| conan-io__conan-long60-2 | dev | 60 + 0 | 30 |
| iterative__dvc-long60-1 | dev | 60 + 0 | 30 (synthetic) |
| getmoto__moto-long60-1 | dev | 60 + 0 | 30 |
| conan-io__conan-long60-3 | dev | 60 + 0 | 30 |

Reserve, written down only (12): conan-long60-4/5/6, moto-long60-2/3/4, dask-long60-1,
astroid-long60-1/2, pygments-long60-1/2, starlette-long60-1.

Validation of the gate chains, dvc-1 and moto-1 was started and stopped before any first round
ended (about 20 minutes in; conan's start-state run is a whole-suite run). Nothing was saved,
so no interactions have been dropped yet. Baked images are kept.

## Next commands (from the worktree root, free)

```
PY=../sanchopanza/.venv/Scripts/python.exe
$PY -u benchmarks/adopt/validate.py conan-io__conan-long60-1     # one process per chain;
$PY -u benchmarks/adopt/validate.py pydantic__pydantic-long60-1  # 3-4 at once is fine
$PY -u benchmarks/adopt/validate.py iterative__dvc-long60-1
$PY -u benchmarks/adopt/validate.py getmoto__moto-long60-1
$PY -u benchmarks/adopt/validate.py conan-io__conan-long60-2
$PY -u benchmarks/adopt/validate.py conan-io__conan-long60-3
$PY benchmarks/adopt/long.py manifests          # long60/<chain>.json per validated chain
$PY benchmarks/adopt/run.py dry --chains <chain>  # scripted gold agent, gold and empty grades
```

Expect 1 h or more per chain and round. conan and moto run their whole suite twice per round.

## Disk (C: 38 GB free)

- Base images, one per repository: conan 3.23 GB, pydantic 3.82, dvc 4.01, moto 4.03 GB.
- Baked tag per chain: about 10-30 MB on top of its base.
- Cache: `swesmith_synth.jsonl` 682 MB, `long60-selected-full.json` 125 MB.
- Per arm at run time, one exported working copy of the repository (not measured yet).
