# Benchmarks

Different questions live here, and confusing them is the main way people lie with numbers
about decision layers.

| Question | Where | What it answers |
|---|---|---|
| Does the squire decide correctly? | `../benches/` plus `sanchopanza bench` | Decision-level accuracy, calibration, coverage. Replays for free from a recorded fixture. |
| Does the agent get cheaper or worse? | `ab/run.py` | End-to-end cost, latency and answer quality in an agent loop, with and without the squire. Spends real money. |
| What does a lever remove, with the agent's discretion taken out? | `ab/fixed.py` | Both arms driven through the same fixed document sequence, so the lever is the only difference. Spends real money. |
| Where may a decision be *applied*? | `cache/` | What narrowing a tool catalog costs when it is done once, on alternate turns, or afresh every turn. Spends real money. |
| Does it hold on third-party material and a real agent? | `agentdojo/` | Injection on a harvested bench, tool selection and the tool window on AgentDojo's catalog, and both end to end. |
| Does the tool window hold on a real, wide catalog? | `mcp_wide/` | 1,497 tool definitions harvested from 55 public MCP servers, served by a stub that fails every call. |

Decision-level accuracy does not answer the end-to-end questions and must not be quoted as if
it did. A decision can be right and change nothing about what the job costs.

The scripts at this level state their command, and whether they spend anything, in their
docstrings. Most are free replays of recordings already on disk (`substitution.py`,
`agreement.py`, `collision.py`, `memory_common.py --offline`, `thresholds.py`);
`docs/paper.md` Appendix A lists them with the results they reproduce.

## The standing rule

**A counter that proves a lever ran is not a check that it did what it was for.** Every lever
in this directory answers two questions, and the second is the one that catches things: *did
it fire*, and *is the world different in the way it was supposed to be*.

| Lever | It fired | It did what it was for |
|---|---|---|
| A drop counter | the count is non-zero | the counter reads the list of the lever under test, and the dropped documents are missing from the context |
| A second annotator | the script exits 0 | every point has a rubric, and the label file holds one label per case |
| A marking defense | the detector fires | it read the content key the tool returns, and the text is still there, marked |

Ask the second question of the logs, not of the code.

## The cache arms

```
python benchmarks/cache/run.py --dry          # the token arithmetic, free
python benchmarks/cache/run.py --turns 8      # four arms, about 0.70 USD
```

Narrowing a 58-tool catalog **once** is 43 % cheaper than not narrowing it; narrowing it on
alternate turns is 14 % *dearer* than not narrowing it; narrowing it afresh every turn reads
**zero** tokens from cache across eight turns and costs 4.15x the arm that decided once.
Results, caveats and why each arm is tagged with its own name: `cache/results/summary.md`.

## The A/B, in an agent loop

```
python benchmarks/ab/run.py --verify                       # ground truth check, free
python benchmarks/ab/run.py --repeats 1 --tasks dag        # a pilot, a few cents
python benchmarks/ab/run.py --retrieval noisy --doc-size large --repeats 3

# many sources per task, with the redundancy lever
python benchmarks/ab/run.py --retrieval scattered --lever redundancy     --tasks spread-adapters,spread-costs --repeats 3
```

Needs `ANTHROPIC_API_KEY` and `TYPESAFE_API_KEY`, and `pip install anthropic`.

**Design.** Eight questions over a corpus of 23 to 56 documents built from files already in
this repository: the paper split by section, the other documents, and the Spanish page texts
of the triage bench. The agent gets two tools, `search` and `fetch(doc_id, purpose)`, and a
deliberately mediocre keyword retriever. Both arms are byte-identical in prompt, tools,
model, thinking and effort. The only difference is that in the `squire` arm `fetch` passes
the page through `Squire.triage_page` first, and a page judged irrelevant to the stated
purpose comes back as a one-line note instead of its text.

**Why a local corpus.** So the run is deterministic, free of network variance and repeatable
by anyone who clones the repository. Nothing in the corpus was written for the benchmark.

**Ground truth.** Each task carries a `pin`: a string that appears in exactly one document of
the corpus. `--verify` checks that on every run, which is what makes "the agent answered
correctly" mean "the agent retrieved the right document", not "the model already knew".

**Conditions.** Two knobs, because the answer depends on both and hiding that would be the
lie:

- `--retrieval precise|noisy`. Precise indexes and shows curated section headings, so the
  right document usually ranks first and announces itself. Noisy ranks by body frequency and
  shows snippets, which is what a real retriever over real pages gives you.
- `--doc-size small|large`. Small leaves page-sized documents; large folds sections until
  documents are the size of an official PDF.

A third condition asks for many sources: `--retrieval scattered` widens the result list to 16
and tells the agent the answer is spread across documents; `--lever redundancy` passes each
fetched page through `Squire.triage_redundant` against a digest of what the agent already
kept; and the two `spread-*` tasks carry `pins` instead of `pin`, several strings each
appearing in exactly one document and all in different documents, so they cannot be answered
without retrieving every one of them. The corpus supplies redundancy of its own, since several
of its documents state the same results.

**Statistics.** Each squire run is paired with the run of the same task and repetition
without it, and the reported change is a paired bootstrap over those pairs, 2,000 resamples,
fixed seed. Means alone would mix the effect with the run-to-run variance of the agent's
search path, which is large.

**Reporting.** The summary reports the triage and redundancy drop counters separately, its
prose follows `--lever`, and when both counters are zero it says that the comparison is
uninformative about the lever, because the two arms then handed the model the same bytes.

**Cost control.** A turn cap and an input-token cap per run, a running total printed as it
goes, and `--max-usd` aborts the sweep.

**What it found.** Results are in `ab/results/`, with every run recorded in `runs.json`. Across
64 paired runs the cost effect is not distinguishable from zero in either document size,
while the latency cost is real and its interval excludes zero. Quality did not move. The
reason is in the runs: the agent fetched one to two documents per task and triage dropped a
fraction of one. Larger documents do not change that, because in this corpus size and
retrieval difficulty are coupled: the larger the documents, the easier it is to find the
right one and the less there is to keep out.

The scattered pilot (`ab/results/2026-09-24-scattered-piloto/`, one repetition, 0.24 USD) is
uninformative about the lever: redundancy dropped nothing, so both arms read identical bytes,
and the cost difference between them is the agent's search path.

## The fetch-heavy A/B, with the sequence held fixed

```
python -m benchmarks.ab.fixed --dry-run              # the plan and the bill, no API calls
python -m benchmarks.ab.fixed --repeats 3 --docs 20 --out benchmarks/ab/results/<date>   # ~3 USD
```

In an agent loop an avoidance lever can only act on the documents the agent fetches, and the
run that fetches many redundant documents is the run that was already going badly: the
lever's opportunity is correlated with the arm having a bad draw, so pairing on (task,
repetition) does not isolate it. `ab/fixed.py` takes the agent's discretion out. For each
task the retriever returns a deterministic ranked list, the harness walks it in order, every
document goes through the lever or not, and one model call answers from what survives. It is
a pipeline, not an agent loop, so it says nothing about how a lever changes the agent's
behaviour; `run.py` measures the loop and `fixed.py` measures the lever.

On 10 tasks and 20 documents each (`docs/results/2026-09-24-fixed-sequence/`, 2.92 USD), page
triage cut input tokens by 75.2 % [-86.8 %, -63.9 %] and correct answers from 10/10 to 6/10,
and in every failure the answer document was among those dropped. Source redundancy dropped
4 of 193 documents and changed nothing measurable. The two halves of the triage result are
one result and neither is quoted without the other.

## AgentDojo

Every script states its command and cost in its docstring. Run them with an interpreter that
has `agentdojo` installed, kept out of the package's own environment.

| Script | Measures | Results |
|---|---|---|
| `extract.py`, `score.py` | Injection on 273 cases harvested from AgentDojo v1.2.2, free to rebuild and score | `docs/results/2026-09-24-agentdojo/` |
| `run.py`, `defense.py` | The squire as an AgentDojo defense: utility and attack success, end to end | `docs/results/2026-09-24-agentdojo-e2e/` |
| `tools_bench.py`, `tools_wide.py`, `tools_baselines.py`, `parts_bench.py` | Tool selection on the 16-group and 248-group catalogs, against the platform's free baselines | `docs/results/2026-09-24-tools/`, `docs/results/2026-09-25-window/` |
| `window_data.py`, `tools_window.py`, `window_escalation.py` | The tool window replayed on real trajectories, and whether an injected payload can widen it | `docs/results/2026-09-25-window/` |
| `e2e_window.py`, `e2e_report.py`, `reprice_shared_prefix.py` | The tool window with a real agent, and its cost with the `tools` + `system` prefix shared | `docs/results/2026-09-25-e2e/`, `docs/results/2026-09-25-cache/` |
| `probe_push.py` | Whether a harness can put deferred tools in front of the model unasked; a mechanism probe | `docs/results/2026-09-25-push/` |

## mcp_wide

`mcp_wide/catalog.json` and `mcp_wide/stub_server.py` are the wide catalog and its stub
server; `mcp_wide/README.md` says where every definition came from. The end-to-end run on 398
of those tools uses `agentdojo/e2e_window.py --wide`, and its results are in
`docs/results/2026-09-25-wide/`.

## What an end-to-end run finds that a bench does not

Triage reads the head of a long document plus the window that best matches the purpose
(`sanchopanza.text.excerpt`), because judged on its first 1,500 characters a 10,000-character
document whose preamble does not address the purpose is dropped even when it holds the
answer; in the agent loop the agent then re-fetches it, hits its turn cap and produces
nothing, at twice the cost. Documents that already fit are unchanged, so no bench number
depends on it, which the replay test enforces. That is the argument for running an
end-to-end benchmark even when the decision-level numbers look good: a defect can live in
the way decisions are wired to the material, not in the decisions.
