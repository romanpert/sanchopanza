# long60 validation: status (2026-10-06)

Free: Docker only, no model, no API, no Jev, no keys set (the launcher blanks
`ANTHROPIC_API_KEY` and `TYPESAFE_API_KEY`). Nothing installed into `../sanchopanza/.venv`.

## Launcher

`runs/validate-chain.cmd <chain>` (not committed; `runs/` holds logs) sets `PYTHONPATH=src`,
runs `../sanchopanza/.venv/Scripts/python.exe -u benchmarks/adopt/validate.py <chain>` and
writes `runs/validate-<chain>.log` / `.err`. It is started detached by WMI so it survives the
session:

    Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
      CommandLine = "cmd.exe /c <worktree>\runs\validate-chain.cmd <chain>"; CurrentDirectory = "<worktree>" }

Stop a chain only by its own PIDs (`taskkill /PID <cmd PID> /T /F`), never by name.

## Bug found and fixed (6ec4150)

pytest stops before running anything on `ERROR: not found: <node>`, with or without
`--continue-on-collection-errors`. Each validation round's "alone" runs list the whole chain's
FAIL_TO_PASS. When one listed id does not exist with the other bugs in, the whole run came out
empty. That happens with pydantic's doc tests, named by line range
(`test_docstrings_examples[pydantic/types.py:2042-2063]`), and with conan's `test_makedeps.py`
(10 ids missing with conan-1's bugs in). An empty run read as "nothing passes", so every bug
looked masked. Bisection runs each bug's own nodes, which do exist, so it always converged on
the chain's first two bugs. pydantic-long60-1 dropped two good bugs per round for six rounds and
came out INVALID (first try, 12,474 s). Fix: for development chains, `docker_env.pytest` leaves
out the missing nodes and runs the rest again; they read as not passing. Held-out chains keep
the sealed command. Tests: `tests/test_adopt_collection.py` (3 new). Checked on the real image:
an alone run now reports 401 of 431 nodes, the bug's own F2P pass, and nothing flips.

## Chains

| chain | state | PIDs (cmd / launcher / python) | log |
|---|---|---|---|
| pydantic__pydantic-long60-1 (gate) | running, retry on 6ec4150 (try 1 INVALID by the bug above: `runs/*.try1.log`) | 37404 / 24336 / 37060 | runs/validate-pydantic__pydantic-long60-1.log |
| conan-io__conan-long60-1 (gate) | running, restarted on 6ec4150 (try 1 on old code stopped by PID in round 2; its round 1 dropped 20, unreliable) | 41420 / 39668 / 32460 | runs/validate-conan-io__conan-long60-1.log |
| conan-io__conan-long60-2 (dev) | not started | - | - |
| conan-io__conan-long60-3 (dev) | not started | - | - |
| iterative__dvc-long60-1 (dev) | not started | - | - |
| getmoto__moto-long60-1 (dev) | not started | - | - |

Order: the conan dev chains go before dvc and moto, because conan's image is already pulled
(finish a repository before pulling the next). Then dvc-1 and moto-1, at most two at once.

## Disk

C: 50 GB free at start of the retries. Images: conan base 3.23 GB, pydantic base 3.82 GB,
baked tags share their base's layers.

## Manifests

None yet (`benchmarks/adopt/long.py manifests` after a chain validates).
