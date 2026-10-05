# Amendment 4: memory v6 (the tree and the shell) against v5, on fresh requests

Written 2026-10-01, before any of the requests it names was scored. Sealed with the code it
names (`amendment-4.sha256`); each pass runs once.

## Why

In phase B2 of the adoption study (pydantic, 40 bugs, Sonnet 5.5) the memory arm Sm had 40
memory prompts, 0 injections and 0 touches. Sonnet 5.5 read and edited through the shell
(`python - <<E ... s.replace(...)`, `sed -i`, `sed -n`, `grep -n`): it edited only through Bash in
71-100 % of its requests in phases B and B2 (Haiku in 0 %), and 86-89 % of its records said they
changed nothing, so the touch, on file tools only, had nothing to match and never fired.
On SWE-chat, 2.2 % of real requests edit only through Bash and 14.9 % read only through it.

## What v6 changes (designed on data already seen, declared)

- `context.worktree` + `harness.memory_tree`: a snapshot of the git working tree at each prompt
  and Stop; a request's record gains the files it **wrote** (a file tool's path, or a write target
  of a Bash or PowerShell command, `context.shell.written`, matched by whole path) whose content
  changed, with prints of the lines it added. git read-only; bounded in time; secret-named files
  never looked at; an interrupted request finished at the next prompt; retention as the records'.
- The touch on Bash and PowerShell (`context.shell.view`): files a command names, and lines it
  shows (output without grep or `cat -n` prefixes, the command's own lines and quoted strings). A
  file the command writes takes the edit rule; a file it only names, the read rule.
- An adversarial review (2 high, 9 medium) was fixed with tests before any number below.

Development, all through the product's hooks (`v6_chain_real.py`: clones of the run's work
folder moved request by request with the run's own patches; each request then as a new session
holding the earlier requests' records), truth from the patches:

| development | requests | with a related record | recall | precision | noise | chars per request |
|---|---|---|---|---|---|---|
| starlette N, Sm (1-10) | 18 | 7 | v5 0 / **v6 1.000** | v6 0.786 | v6 0.273 | v6 2,182 |
| pydantic N 1-25, S 1-14, Sm 1-14 | 50 | 13 | v5 0 / **v6 0.846** | v6 0.786 | v6 0.027 | v6 793 |

Records that changed nothing: v5 80-89 %, v6 2-9 %. On SWE-chat development (`replay_v6.py`,
953 requests) the shell touch gave 1 record more, unrelated (precision 0.770 to 0.766, recall and
noise unchanged); the tree cannot be replayed there (no working tree).

## Fresh data

1. **B2's later requests**, which ran after the last look: pydantic N 26-40, S 15-40, Sm 15-40
   (67 requests; their pools hold the earlier requests' records). `v6_chain_real.py --arms
   "pydantic__pydantic-long40-1/N:26-40,pydantic__pydantic-long40-1/S:15-40,pydantic__pydantic-long40-1/Sm:15-40" --tag confirm`.
2. **SWE-chat held out 1, 2 and 3** (7,734 requests; `build_v6.py` items, `replay_v6.py`), for
   regressions of the shell touch on how people's sessions ran.

## Success (all; v6 against v5)

On fresh B2 requests, `lineage or file`:

1. v6 recall >= 0.60, and at least 0.40 above v5's.
2. v6 precision >= 0.50.
3. v6 noise <= 0.20.
4. v6 records that changed nothing <= 0.20.

On SWE-chat held out 1, 2 and 3, each set, all requests, `lineage or file`:

5. v6 recall >= v5 recall - 0.005, v6 precision >= v5 precision - 0.01, v6 noise <= v5 noise +
   0.005.

Reported, not criteria: `lineage` precision, characters per request, latency
(`latency_v6.py`), failed patches.
