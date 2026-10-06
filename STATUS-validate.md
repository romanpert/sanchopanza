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
| conan-io__conan-long60-1 (gate) | **running again with extra spares** (98d3a6d, see below): round 6 60 bugs, 2 dropped; round 7 60 bugs, 2 dropped (23:39); 22 extra spares left, last round this run 11. First run: 5 rounds on 6ec4150 (20, 9, 4, 1, 0 dropped, all culprits of masking); round 5 clean with **56** bugs, all real, guard 1,143; 34 dropped, 30 spares used up; 15,452 s (`runs/*.rounds1-5.log`) | launcher 27052 / cmd 32728 / python 33808, 12156 | runs/validate-conan-io__conan-long60-1.log, runs/conan1-extra.log |
| conan-io__conan-long60-2 (dev) | **INVALID by size**: 5 rounds (18, 9, 4, 1, 0 dropped), round 5 clean with 58 bugs, spares used up; 15,465 s | done | runs/validate-conan-io__conan-long60-2.log |
| conan-io__conan-long60-3 (dev) | **INVALID by size**: 3 rounds (28, 9, 0 dropped), round 3 clean with 53 bugs, spares used up; 8,961 s | done | runs/validate-conan-io__conan-long60-3.log |
| iterative__dvc-long60-1 (dev) | running, started 22:46:45 by the queue | cmd 42080 / python 42648 | runs/validate-iterative__dvc-long60-1.log |
| getmoto__moto-long60-1 (dev) | **crashed** (exit 1, 23:3x) in round 1's start-state run: `docker_env.pytest` raised "gave no results" although the run reported 7,308 passed / 2,071 failed (colour codes in the output; parser issue, not the extra-spares change). Not retried | done | runs/validate-getmoto__moto-long60-1.log |

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

## conan-long60-1: extra spares (2026-10-06, 98d3a6d)

The owner chose more spares over a size of 56. `long.py extra60 conan-io__conan-long60-1` replays
the long60 draw (PLAN60 + RESERVE60, seed 20261005), checks it gives exactly the ids of
`long60-selected.json`, and continues the same random generator over the conan rows that no long60
chain or spare took, so the reserve chains conan-4/5/6 stay untouched: real rows first (61 usable
left, rows that fit no earlier chain), then synthetic ones, each fitting the 56 and the spares
before it. 30 drawn: 13 real, then 17 synthetic. Recorded in `long60-extra-spares.json` (start
ids, spare ids, the earlier rounds and drops); rows cached in `long60-extra-spares-full.json`,
drawn again and checked against the ids when missing (8 s).

`validate.py` takes such a chain through `long.resumed`: the 56 validated bugs in their order,
topped up to 60 from the extra spares in drawn order (`perbug.top_up`: pr_13526, pr_13015,
pr_12802, pr_13944 at positions 57-60), then the usual rounds over the whole chain, so the new
bugs are checked with the old ones; drops refill from the remaining extra spares. Rounds are
numbered after the first run's five; drops and seconds add up; the manifest carries
`extra_draw` and `before`.

The queue had already removed the conan base at 22:46:45 when this started; `isolate` pulled it
again. Concurrency: dvc-1, moto-1 and conan-1 (three). `runs/conan1-extra.ps1` stops conan-1 by
its cmd PID under 6 GB free, and writes the manifests when it ends. When it ends, remove the
conan images by hand if the disk is needed (`docker rmi adopt-conan-io--conan-long60-1:bugs
jyangballin/swesmith.x86_64.conan-io_1776_conan.86f29e13`).

### State at the stop (2026-10-06 23:50)

Running detached, free: launcher `runs/conan1-extra.ps1` powershell PID 27052 (log
`runs/conan1-extra.log`), cmd PID 32728, python 33808 / inner 12156; validation log
`runs/validate-conan-io__conan-long60-1.log` (`.err`), first run's logs `*.rounds1-5.*`. Stop
only by `taskkill /PID 32728 /T /F`. When it ends the launcher runs `long.py manifests` itself.
To finish by hand (if the launcher was stopped):

    PY=../sanchopanza/.venv/Scripts/python.exe
    tail runs/validate-conan-io__conan-long60-1.log runs/conan1-extra.log
    PYTHONPATH=src $PY benchmarks/adopt/long.py manifests   # long60/conan-io__conan-long60-1.json
    # if it ended INVALID with drops left to refill: run it again from where it stopped
    # (record the new start: long.py extra60 rewrites the entry from the cached result, drawing
    # the same spares only if the start is the same; check before relaunching)
    cmd /c runsalidate-chain.cmd conan-io__conan-long60-1   # detached by WMI, as above

Then commit `long60/conan-io__conan-long60-1.json`, `chains-validated-summary.json` and this file.



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
