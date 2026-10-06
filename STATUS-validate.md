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
| pydantic__pydantic-long60-1 (gate) | **validated** on 6ec4150: 2 rounds, 3 dropped in round 1 (two culprits of masking, one whose tests a PR fix flips), 0 in round 2; 60 bugs (23 real, 37 synthetic), guard 5,057 tests, 2,262 s. Try 1 on the old code: INVALID by the bug above (`runs/*.try1.log`) | done | runs/validate-pydantic__pydantic-long60-1.log |
| conan-io__conan-long60-1 (gate) | **INVALID: spares ran out**, not a code fault. 5 rounds on 6ec4150 (20, 9, 4, 1, 0 dropped, all culprits of masking, spread over drawn positions 3-53); round 5 is clean with **56** bugs, all real, guard 1,143; 34 dropped, 30 spares used up; 15,452 s. Needs 4 more bugs: an owner decision (more spares, e.g. from reserve conan-long60-4/5/6, or a size of 56) | done | runs/validate-conan-io__conan-long60-1.log |
| conan-io__conan-long60-2 (dev) | running on 6ec4150: rounds 1-3 dropped 18, 9, 4 (31 > its 30 spares: expect INVALID by size, like conan-1) | 24672 / 28724 / 13992 | runs/validate-conan-io__conan-long60-2.log |
| conan-io__conan-long60-3 (dev) | running on 6ec4150 | 33692 / 22444 / 13248 | runs/validate-conan-io__conan-long60-3.log |
| iterative__dvc-long60-1 (dev) | queued (`runs/after-conan.ps1`, PID 34504) | - | runs/validate-iterative__dvc-long60-1.log |
| getmoto__moto-long60-1 (dev) | queued (same queue) | - | runs/validate-getmoto__moto-long60-1.log |

Queue `runs/after-conan.ps1` (powershell PID 34504, log `runs/after-conan.log`), started by WMI:
waits for conan-2 and conan-3 by python PID (13992, 13248), removes the conan images, refuses to
go on under 14 GB free, starts dvc-1 and moto-1 together (their cmd PIDs go in its log), stops
them if C: drops under 6 GB, then runs `long.py manifests` and removes the dvc and moto images.
Its first launch misparsed the PID list (`-File` does not build an `[int[]]`): it did not wait,
untagged the conan base and started dvc and moto early. Those were stopped by their PIDs within a
minute (`runs/*.aborted.log`, `runs/after-conan.misfire.log`), the base was pulled again (layers
still present) and conan-2/3 kept running. The script now takes the PIDs as one string and
stops when any of them is not alive at start (tested with a dead PID).

Order: the conan dev chains go before dvc and moto, because conan's image was already pulled
(finish a repository before pulling the next), at most two chains at once.

## Disk

C: 50 GB free when the retries started, 45 GB now (Docker's disk image does not shrink on
`rmi`). Images: conan base 3.23 GB, pydantic base 3.82 GB, removed after its chain; baked tags
share their base's layers. Removed tags are rebuilt with `validate.py --bake <chain>`.

## Manifests

`benchmarks/adopt/long60/pydantic__pydantic-long60-1.json` (valid) and
`benchmarks/adopt/long60/conan-io__conan-long60-1.json` (`"valid": false`, 56 bugs). The queue
writes the rest when dvc and moto end; or run `$PY benchmarks/adopt/long.py manifests` by hand.

## Next

    PY=../sanchopanza/.venv/Scripts/python.exe
    cat runs/after-conan.log; tail runs/validate-*.log
    $PY benchmarks/adopt/run.py dry --chains pydantic__pydantic-long60-1   # after validate.py --bake

Decision for the owner: conan's real PR bugs mask each other heavily (conan-1 lost 34 of 90),
so 30 spares do not reach 60 bugs.
