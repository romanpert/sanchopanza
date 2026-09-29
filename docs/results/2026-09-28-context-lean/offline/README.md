# Offline measures for the context-lean iteration: index stubs, arrival cut, the API's clearing

**Method only; results pending.** Written before the pre-registration of this iteration.
Only a smoke test has run: the free arms on 2 trajectories, and with a stand-in for
`arrival.free_cut`. The full free run and the one paid arm run after the pre-registration is
hashed. Code: `run.py` (command line, the Jev arm) and `measures.py` (pure measures).

    python docs/results/2026-09-28-context-lean/offline/run.py smoke      # 2 units, free
    python docs/results/2026-09-28-context-lean/offline/run.py free       # 40 units, free
    python docs/results/2026-09-28-context-lean/offline/run.py estimate   # Jev arm, no call
    python docs/results/2026-09-28-context-lean/offline/run.py jev --cap USD --env-file PATH
    python docs/results/2026-09-28-context-lean/offline/run.py jev --replay   # free

## Data

The 40 units of `docs/results/2026-09-28-context/`: `nebius/SWE-rebench-openhands-trajectories`
(CC-BY-4.0, revision `35455389`), 15 dev and 25 test, rebuilt by
`benchmarks/context/build.py --fetch` into `~/.cache`, never the repository. We use the same
cut (60 % of each trajectory's characters), the same history and future, and the same lexical
NEEDED labels (`benchmarks/context/labels.py`). A history result is NEEDED when the future's
assistant text or tool inputs use a distinctive token that appeared only in that result. The
tokens it used are the result's `hits`. "Present" means found literally, as a substring, as
in the bench's `simulate.present`.

## O1. Index stubs

At the cut, the history is masked the way the autopilot's compaction masks it
(`compact._plan_mask`, M = 10 acting turns, the last 6 messages and the structural invariants
kept). For every masked result:

- **index**: `index_of(result, limit)` for limits 120, 240 (the main one) and 480. `run.py`
  takes `compact.index_of` if it exists, otherwise `sanchopanza.context.index.index_of`.
- **head**: the first `limit` characters of the result.
- **plain stub**: `compact.stub_text`. It holds no token by construction. It is computed
  anyway, as a check.

Reported per split (dev, test, all):

- the share of NEEDED masked results with at least one used token present in the variant,
  with a Wilson 95 % interval. The interval treats results as independent, but results within
  one session are not.
- the characters the variant adds: per stub (over every masked result, needed or not), in
  total, and as a percentage of the characters masking freed.

## O2. Large outputs at arrival

**Population**: every history tool result of at least 6,000 characters (`arrival.Settings`'s
threshold). There are **170** across the 40 units, above the 30 the plan required, so no
second source was added. `arrival.gate` sends 169 of them on to the decider. The other one
reads as a failure under 20,000 characters and passes whole in the `jev` arm.

**Needed lines**: the lines of the result that contain at least one of its `hits`. A line
counts as kept by an arm when its stripped text appears in the arm's output. Every arm is
scored by this one rule, whether it returns text or line indexes. Results with no needed line
count only toward characters.

**Purpose**: `arrival.purpose_of(history before the result, tool, input)`. That is the first
prompt, the latest prompt, the agent's last text and this call, within 400 characters.

**Arms**:

| arm | what the agent gets | cost |
|---|---|---|
| `head_tail` | first 20 and last 20 lines | free |
| `free_cut` | `arrival.free_cut(text, purpose, Settings())`. A `Cut` with `text=None` (or `None`) means the result passes whole | free |
| `bm25_at_free_cut` | lines ranked by BM25 against the purpose, taken best first while they fit in `free_cut`'s characters for that result, then put back in their original order | free |
| `bm25_at_head_tail` | the same, within `head_tail`'s characters | free |
| `jev` | `arrival.cut`, the current tournament, through a `Squire` | Jev, prepared only |

**Metrics** (per split): the share of results whose needed lines were **all** kept (Wilson
95 %), the share of needed lines kept (pooled), characters kept as a percentage of the
original (pooled over every result), and the number of results each arm changed. Every
arm's character count excludes the arrival header. Omission markers are included for
`free_cut` and `jev`, since they are part of the text the agent reads.

**The `jev` arm.** `run.py jev` refuses to run in four cases:

- `--prereg` (default `../prereg.md`) is missing, or does not hash to the sha256 in
  `../prereg.sha256`;
- `--cap` is missing;
- the high estimate is above `--cap`;
- recordings from an earlier run exist.

The key is read in-process from `--env-file` (`TYPESAFE_API_KEY=...`) and passed to
`JevDecider`. It is never printed or written. The arm runs `jev-1.13.0` in one event loop,
behind one `Squire` whose meter stops at `--cap`. It counts failed and empty calls, and a run
with any is marked incomplete. Every decision is recorded to
`~/.cache/sanchopanza/context/recordings-lean/arrival-jev.jsonl` for a free `--replay`.

**Jev cost estimate** (`run.py estimate`; the states are built and nothing is called):

- 169 eligible results; 331 decisions expected, 780 at worst.
- Tokens at 0.042 USD per million: 0.128 USD expected, 0.273 USD at worst.
- At the planning figure of 29e-6 USD per decision: 0.0096 USD expected, 0.023 USD at worst.
  This figure is too low for these states. Amendment 2's arrival run spent 0.081 USD on 236
  decisions, about 3.4e-4 USD each. The token-based figure is the one to cap against:
  **`--cap 0.30`**.

## O3. The API's rival: `clear_tool_uses_20250919`

Semantics from https://platform.claude.com/docs/en/build-with-claude/context-editing, as
read on 2026-09-28:

- `trigger`: 100,000 input tokens by default.
- `keep`: the 3 most recent tool uses by default.
- Clearing starts from the oldest tool results. Each cleared result is replaced with
  placeholder text.
- `clear_tool_inputs` is false by default, so tool calls stay visible.
- `exclude_tools`: none by default.
- `clear_at_least`: none by default. When the API cannot clear at least that many tokens, the
  strategy is not applied.
- The editing is applied server-side on each request.

**What is modelled.** The history at the cut is taken as one request. If
`history chars x 0.3 >= T`, every tool result except those of the last K = 3 tool uses (by
call position) is cleared. Otherwise nothing is. We use the default settings, so nothing is
excluded, inputs are kept, and `clear_at_least` is none. `measures.api_actions` implements
`clear_at_least` but the runs do not use it.

T takes the values 30k, 50k and 100k (the default). The arm `api_always` is T = 0: what
clearing does whenever it fires. We compare against mask M = 10 and M = 3 (the autopilot's
`_plan_mask`). The metrics are the bench's own `metrics.unit_metrics` and `summarize`: freed
fraction, recall of NEEDED, needed chars lost and token recall, with percentile-bootstrap
intervals over units.

**Assumptions, not in the docs:**

1. Input tokens are taken as characters x 0.3. The dataset dropped the system prompt and tool
   definitions, which a real request counts toward the trigger, so the proxy undercounts.
   At the cut, 40 of 40 units reach 30k, 15 reach 50k, and **0 reach the default 100k**.
2. "The last K tool uses" is taken as the last K `tool_use` blocks by position. Parallel
   calls in one message count separately.
3. Stateless per request: the client resends the whole history, so at the cut the result
   does not depend on earlier requests. If a client kept the edited history instead, the
   same set would already be cleared.
4. The placeholder's characters are not subtracted from what was freed. The bench's stubs
   are not subtracted either.

## Results

Pending. They are filled in from `results.json` after the pre-registration is hashed.
`results.json` currently holds only `smoke` and `jev_estimate`. The `smoke` section was run
with a stand-in `free_cut`, which has since been deleted, because `src/` did not provide it
yet. Its O2 `free_cut` and `bm25_at_free_cut` figures are plumbing checks and mean nothing.

## What this does not settle

- **The labels are lexical.** A result can shape a decision without leaving a token in the
  future. The lines-level label inherits this.
- **One agent and one model**: OpenHands with Qwen3-Coder, its tools mapped to Claude Code
  names.
- **No agent was re-run.** Whether an index stub or a cut changes what the agent does next is
  not measured here.
