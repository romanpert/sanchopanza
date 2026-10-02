# Memory carry: a fact said in an earlier session, that the repository does not show (2026-10-02)

Development pilot, n = 1 per scene. Not a confirmation.

## Question

The person says something in passing in one session ("finance's macro reads this CSV by column
position"). A later, new session gets a task that tempts breaking it. Does Claude Code keep the
fact? Does sanchopanza's memory change that?

## Design (`benchmarks/memory_carry/`, 119b075)

- Eight scenes (`scenes.py`): column order, a legacy field, error wording, three log fields,
  string paging parameters, naive UTC, stdlib only, Python 3.8. Session 1 does a small task on a
  file and the fact is said in passing. Session 2, a new session (no `--resume`), gets a task on
  the same file that tempts breaking it.
- Arms:
  - `N` is Claude Code 2.1.285 as it ships, with its own auto memory on (it is by default).
  - `M` is the same plus sanchopanza's memory hooks as `install --memory` writes them, with
    the decider. The TypeSafe key reaches only the hook.
  - Both arms get the same prompts, tools (Bash, Read, Edit, Write, Glob, Grep), model
    (Sonnet 5.5) and caps.
- Checks fixed before any session (`tests/test_memory_carry.py`):
  - `task` exits 0 when session 2's task is done; two scenes have no task check.
  - `fact` exits 0 when the fact still holds.
  - The repository's tests are run too.
  - Per scene, a result that keeps the fact and one that breaks it, written by hand, are told
    apart.
  - No repository file, and no session-2 prompt, gives the fact away.

## Result (Sonnet 5.5, 32 sessions, 5.97 USD at list price, the subscription paid)

| | fact kept | tests | task | cost |
|---|---|---|---|---|
| N, Claude Code as it ships | 5 / 8 | 8 / 8 | 6 / 6 | 3.04 USD |
| M, with sanchopanza's memory | **7 / 8** | 8 / 8 | 6 / 6 | 2.93 USD |

- **The two discordant scenes both favour M.**
  - `naive`: N wrote `datetime.now(timezone.utc).isoformat()`, with an offset. M wrote the fact
    as a comment ("The warehouse loader rejects UTC offsets") and emitted naive UTC.
  - `fields`: N added a fourth ` | `-separated field. M put the request id inside the message.
- **`wording` fails in both arms.** M recalled the fact: its comment reads "Keep the 'Row N:
  missing email' prefix: support scripts grep for it". It kept the prefix and appended detail,
  but the check, fixed before the run, wants the exact message.
- **Claude Code's own auto memory** was on in every session: it created the project's memory
  folder and announced it at start. It saved nothing in any of the eight first sessions, so in
  `N` nothing carried.
- **M's memory gave the earlier request in all eight second sessions**:
  - seven at the first prompt (the decider; the prompt names the file);
  - one when the file was opened (`fields`).
- **Five scenes did not tempt Sonnet**: N kept the fact anyway in `columns`, `legacy`,
  `strings`, `stdlib` and `py38`. The pilot's power comes from three scenes.

What this does not show: with two discordant pairs, McNemar's exact p = 0.5. Direction only.
Rows are in `~/.cache/sanchopanza/memory-carry/2026-10-02-sonnet/carry.json`.
