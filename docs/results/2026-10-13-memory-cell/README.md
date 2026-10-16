# Memory cell: N against S on Sonnet 5.5, F1 family (iii) parallel (2026-10-13)

**Verdict: gana.** On 24 pairs (8 scenes x 3 repetitions), Claude Code with sanchopanza (S)
broke the fact in **0** pairs; clean Claude Code (N) broke it in **11**. One-sided exact McNemar
p = 0.00049. S passed every criterion fixed before the data, cost **1.12 x** N per pair (median;
the limit was 1.15) and took **1.12 x** N's wall time.

Sealed pre-registration: `prereg.md`, commit d42d261, file sha256
`86b5cbe0e6a105e14f0a0bee187bb75bfc4f1e80750b55495eb0f74f1bf8ba81`; launcher `mem-cell-run.cmd`
sha256 `67837f636f1e0ad37853d4e49db625baf160728d8affe26bb868f5a6b49682a7`. Before sealing, two
independent checks of the text against the code (no paid call) found every number and flag in
agreement; their findings were fixed in 02fe9c9 before the seal. Run from a detached worktree at
d42d261 (`sanchopanza-mem-cell`), started by WMI with CreateFlags 512 at 20:44:32. The run ended
at 21:52:53 with exit 0 and was not resumed. `run.status` is the launcher's status file and
`table.json` is the sealed `cell.py` output, both copied as found. Nothing was amended after the
data.

## Result

| | S | N |
|---|---|---|
| pairs run | 24/24 | 24/24 |
| facts broken (the gate's break: fact not kept, task not failed) | **0** | **11** |
| facts not kept, any task outcome | 0 | 11 |
| task done | 23 | 24 |
| repository tests pass | 24 | 24 |
| list cost, USD (Claude Code; S with Jev) | 4.441 (Jev 0.008) | 4.027 |
| wall time, s (sum of sessions) | 2,124 | 1,881 |

| sealed criterion | value | rule | holds |
|---|---|---|---|
| 1. primary: McNemar on breaks, S better | 11 to 0, p = 0.00049 | p < 0.05 | yes |
| 2. fact alone (a failed task counts as not kept) | 11 to 0, p = 0.00049 | p < 0.05 | yes |
| 3a. tests, S no more than 3 fewer than N | 24 vs 24 | >= 21 | yes |
| 3b. task, S no more than 3 fewer than N | 23 vs 24 | >= 21 | yes |
| 4. false send-backs in S's last session | 0 | <= 1 | yes |
| 5. cost, median S/N per pair | 1.117 | <= 1.15 | yes |

Reported beside the rule:
- The other one-sided p (S breaks more) is 1.0.
- Cost S/N: geometric mean 95 % bootstrap interval over scenes 1.05-1.15. The total-cost ratio
  is 1.10.
- Wall time, median S/N per pair: 1.12.
- Effect: S kept 24/24, N 13/24. The difference is +45.8 points; exact 95 % interval of N's break
  rate 11/24: 25.6-67.2 %. Bootstrap over scenes, 10,000 draws, seed 20261013: 12.5-79.2 points.
- Variants: same checkout, N broke 5 of 12, S 0. Sibling worktree, N 6 of 12, S 0.

**Where N broke: 4 of the 8 scenes, and almost always.**

| scene | N broke | what N's session 2 wrote |
|---|---|---|
| `q_cents` | 3/3 | float prices, `round(4.99 + 1.50 * extra_kg, 2)` |
| `q_stdlib` | 3/3 | `import yaml` / `yaml.safe_load` |
| `q_trash` | 3/3 | `os.remove(...)` on the old files |
| `q_tz` | 2/3 | `datetime.now(timezone.utc).isoformat()`, with the offset |

N kept `q_print`, `q_camel`, `q_zeros` and `q_prefix` 3 of 3, as in the gate. The gate's two
reasons apply: the start repository shows the habit (`sync.py`'s logging, `orders_api.py`'s
camelCase, `config.py`'s `ACME_` prefix), or the default keeps the fact (ids as strings). So S
gains where the fact is not visible in the code, and ties where it is. **Read by scene, S beat N
in 4 scenes and lost in none.** A sign test over scenes gives one-sided p = 1/16 = 0.0625. The
sealed test counts pairs, and repetitions of one scene are not independent, so the pair-level p
overstates the evidence. The direction is not in doubt (11 to 0); the size across scenes is less
sure (bootstrap interval 12.5-79 points).

## Read by hand

- **Every check was rerun by hand** in all 48 repositories (task and fact, bytecode writing off):
  48 of 48 match `carry.json`.
- **Every N break** was read from `git diff HEAD` (table above). Each one is the fact plainly
  broken, with the task done and the tests passing.
- **How S kept the fact: the same mechanism in all 24 pairs.**
  - Session 1b said the fact in passing. At its Stop, memory's rule extraction (one Jev decision per prompt sentence)
    stored it as a standing rule: each store ended with 8 rules, the 7 decoys plus the scene's
    own.
  - That includes the 12 worktree pairs: the store is keyed by the repository and shared by its
    worktrees.
  - At session 2's start the standing rules were injected with the new rule first. The injected
    text grew in every pair between session 1b's start and session 2's.
  - Session 2 then followed the rule. In `q_stdlib`, for example, it wrote its own small YAML
    parser instead of `import yaml`.
  - The Stop audit sent nothing back: no send-back of any kind, own rule or decoy.
- **The one S task failure** (`q_stdlib` r3) is a cost of keeping the fact. The hand-written
  parser raises on `config.yaml`'s list (`servers:` / `- a.example.org`), so the task check
  fails. It kept the fact (no `yaml` import) and its own tests passed. S's other two `q_stdlib`
  parsers handled the list. It is within the task margin (23 vs 24). It is not a break under
  either reading: criterion 1 forgives a failed task, and criterion 2 counts only the fact, which
  held.
- **Claude Code's own auto memory** held the fact before session 2 in **1 of 24 N pairs**
  (`q_tz` r1, which N kept). In the other 23 nothing was saved before session 2. This is the same
  pattern as the gate: on Sonnet, sessions 1a and 1b rarely save. In S, Claude Code's own memory
  saved nothing before session 2 in any pair; sanchopanza's store carried the fact.

## Exclusions and items reported whatever the result

- **NOT RUN: none.** 24 of 24 pairs, 144 of 144 sessions ended `success`. There was no usage
  limit, no timeout, no harness cut and no cap stop.
- **init, all 144 sessions:** `claude-sonnet-5-5`, Claude Code 2.1.287, `apiKeySource` `none`
  (the OAuth token). Permission mode is `auto` in session 1 and `default` after it in both arms,
  as in the gate.
- **S's find server** `sanchopanza` was `connected` in 72 of 72 S sessions.
- **Jev:** preflight HTTP 200 (`jev-1.13.0`, 0.000012 USD). Over the S pairs, 243 decisions with
  0 failed, 0.0080 USD. Every S pair passed the "S ran as S" checks; S's hooks logged no call
  that exited non-zero or wrote to stderr.
- **Subagents:** none. No `Task` or `Agent` call and no event with a `parent_tool_use_id`.
- **Denied tool calls:** `PowerShell` (not in `--allowedTools`), 7 in S and 1 in N, as in the
  gate. Every such session still ended `success`.
- **Token:** no pair has `token_scrubbed` or `token_in_git`. `typesafe.key` was removed by the
  runner at the end.
- **Order:** with `--rotate`, 12 pairs ran S first and 12 ran N first, and every scene ran both
  orders.

## Spend

**8.47 USD at list price, through the subscription** (Claude Code 8.468 + Jev 0.008 + preflight
0.00001), against the hard cap of 36.5 and the sealed expectation of about 9.5. Per session: N
0.056, S 0.062 USD; the costliest session was 0.115 against the 0.60 cap.

## What this does not show

- **One model and one family.** Sonnet 5.5, the parallel-session case, the only cell the gate
  opened. On Opus 5.5 and in families (i) and (ii), the gate found no room: N did not break
  enough for S to show a gain there.
- **S is the default install plus `--memory`** (project scope, Jev with a key, 7 decoy rules in
  the store). The bare default install wires no memory and was not run; its result would be known
  beforehand.
- **Eight scenes.** The gain is concentrated in the four scenes where the fact is invisible in the
  code. Across scenes the evidence is 4 wins and 0 losses, not 24 independent trials.
- Headless `claude -p`, a clean user, Claude Code 2.1.287, three short sessions per pair.
  Interactive sessions and later Claude Code releases may save their own memory differently.
- The cost criterion passed close to its line: 1.117 against 1.15, interval upper bound 1.149.

2026-10-15: text redacted to remove the name of another project; the sealed originals (`prereg.md`, hash 8ce5dfd4b71b251fe41f7aaf5a4c319c6abf5d5aea22813c0b95e31b533bcc26; `mem-cell-run.cmd`, hash 7ed50064986b6646146f74281c0568967b3b7defe992a3d72a94e806ce464106) are kept in the git history.
