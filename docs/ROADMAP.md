# Roadmap: what is pending, by priority (2026-10-15)

What is still open in sanchopanza after the final scoreboard
([`docs/results/2026-10-13-final/`](results/2026-10-13-final/README.md)), and what the one known
consumer, an agent with its own harness, asked of it. Each item says what it would cost and
whether it is done. Measured results stay in `docs/results/`; this page only orders the work.

Cost: **free** is code, tests or replays with no model; **Jev** is TypeSafe calls (cents unless
said); **Claude** is Claude Code sessions on the subscription, quoted at list price.
Priority: **high** breaks something or blocks the consumer; **medium** is a cheap, measurable
gain; **low** is an idea, or an expensive cell with no margin shown.

## Jev 1.14

Supported in the client since 2026-10-15 (merge `5694973`), with the default unchanged:

- `SANCHOPANZA_JEV_MODEL` picks the model; `DEFAULT_MODEL` stays `jev-1.13.0`
  (`src/sanchopanza/providers/jev.py`). The benches that pinned 1.13 by hand follow the variable.
- Long context and images send the Danger Zone headers, by argument or by
  `SANCHOPANZA_JEV_LONG_CONTEXT` / `SANCHOPANZA_JEV_IMAGES`; images go as refs plus a top-level
  assets map (`providers/jev_assets.py`, extra `sanchopanza[images]` for resizing).
- `Box` is a fourth question type, refused before any request on a version below 1.14.
- Recordings key the model from 1.14 on, and a 1.14 fixture has its own file
  (`fixtures/jev114/<name>`); every existing key is unchanged.
- `SpendLedger` and `CappedDecider`: a hard dollar cap shared by every process of a batch, each
  call reserved before it is made (`8c82dff`).
- The truncation limits are parameters (`limits.Limits` on `Squire(limits=)`), defaults
  unchanged (`dad1fb5`).

Experiments with 1.14 are running. Their figures will go in their own `docs/results/` folders, and
`DEFAULT_MODEL` moves only if they justify it.

## Priority table

| # | Item | Priority | Cost | State |
|---|---|---|---|---|
| B1 | Publish a release (`v*` tag and PyPI) so the consumer stops pinning a tarball by commit | **high** | free (owner's decision, irreversible) | open |
| A3 | MCP tool calls pass the installed hook with no decision | medium | Jev (replay ~0.03 USD), then Claude (a bounded live probe) | open |
| B6 | Page triage and passages unmeasured in Spanish or outside QASPER | medium | Jev (< 0.10 USD) + Claude (~1-3 USD, Haiku answering) | open |
| B4 | Order the approved paragraphs that do not fit by a four-level score | low-medium | free + Jev cents | open |
| B7 | A stable API of questions, thresholds and recording keys to import rather than copy | low | free | open |
| A4 | Cells not run by decision (code on Sonnet and Opus, memory F2, Fable, S2, Ne against Ne+A) | low (owner's decision) | Claude: see below | open |
| A5 | `relate_facts`: the `unrelated` gate | low | Jev cents | open |
| A6 | Getting an agent to use `find_in_repo` | low | Claude | open |
| A7 | The derivation rule against Sonnet on unseen data | low | Claude + Jev | open |
| A8 | Deciding before Claude Code's auto-mode classifier | low | Jev + Claude | idea, unmeasured |
| A9 | The tool window by tournament over the sub-groups of a large server | low | Jev | idea, unmeasured |
| A10 | A local classifier (LoRA) for decisions Jev pays for today | low | free (Colab or Kaggle) | idea |
| A1 | Benchmarks read the TypeSafe key from a fixed path on the owner's disk | high | free | **done** (`de7c38a`) |
| A2 | Documents with an old state: README "What is open", the guard-struct README, the root `STATUS*.md` | medium | free | **done** (2026-10-15) |
| B2 | Spanish sentence splitting | medium | free | **done** (`872e068`) |
| B3 | `select_passages`: an unanswered paragraph, and a call budget per document | medium | free | **done** (`a1a04db`) |

## Open

**B1. A published release.** The consumer installs
`sanchopanza[jev] @ https://github.com/romanpert/sanchopanza/archive/<sha>.tar.gz`, pinned to one
commit in three files that must move together. There is no tag in the repository;
`pyproject.toml` says 0.3.0 and `.github/workflows/release.yml` publishes to PyPI by Trusted
Publishing on a `v*.*.*` tag ([governance](governance.md)). If the history is ever rewritten, the
old SHAs stop resolving and the consumer's image would not build, or would run without a decider:
its factory falls back to a null decider in silence when the package does not import. Proposal:
tag `v0.3.0` (or `v0.3.1`), publish, and have the consumer move to `sanchopanza[jev]>=0.3`. Until
then, every change here means moving the SHA there by hand.

**A3. MCP calls in Claude Code.** The installed hook judges shell commands, delegations and
searches, and lets MCP tool calls through: on ATBench-Codex, whose risks live in MCP calls, it
flagged 0 of 250 unsafe trajectories. The `actions` point judged the same set at 78.2 % offline
and is not wired into the hook ([cascade-frontier](results/2026-09-27-cascade-frontier/),
[broad](results/2026-09-28-claude-code-broad/)). Next: a replay of the wiring over what is
recorded, then a bounded live probe.

**B6. Spanish, and documents other than scientific papers.** What is confirmed is English:
`triage_pages` keeps every supporting page in 98.3 % of HotpotQA questions at 34 % of the text,
`select_passages` every answer sentence in 87.2 % of QASPER questions at 21.0 % (README, "What it
decides"). The consumer asks in Spanish, cuts each page to 900 characters and preselects by BM25
past 90 paragraphs, none of it measured. Next: a small Spanish bench with labels by construction.

**B4. Approved paragraphs that do not fit.** When the paragraphs that pass exceed the delivery
size, the consumer orders them by a four-level score; a second Truth pass did not discriminate.
In three of its own probes on a long public report the conclusions came through the passages in
54 calls. A candidate option for `select_passages`, after a replay here confirms it.

**B7. A stable API to import.** The consumer keeps its own copy of questions, policies, the DAG
and the recorder, because migrating changes its recording keys (they sign the question text) and
the point names in its trace. A versioned id per question and a recording key that does not
depend on the text's language would let it import instead. Meanwhile: what is measured there is
ported here, not the other way round.

**A4. Cells not run by decision** ([final scoreboard](results/2026-10-13-final/README.md), "What
was not run"): code on Sonnet 5.5 and Opus 5.5 (about 357 USD at list price, cap 465), memory F2
handoffs (about 180.5 USD), Fable 5.1 (no suite), the S2 confirmation (owner's decision after its
dev), Ne against Ne+A (about 43 chains to see a −7 %, [`PLAN-GANAR-H2H.md`](PLAN-GANAR-H2H.md)).
None has a margin shown.

**A5-A7.** Open in the README, "What is open": `relate_facts` (the `unrelated` gate at 0.5 and
examples on `unrelated` did not beat the shipped question on the fifth batch); `find_in_repo`
offered and called in 6 of 27 sessions; the "within half a point" derivation rule, untested
against Sonnet on unseen data.

**A8. Before the auto-mode classifier.** The classifier costs no money in Claude Code and a
PreToolUse `allow` does not skip it, so only latency could be won, and that is unmeasured
([`MAPA-HUECOS-ARNES.md`](MAPA-HUECOS-ARNES.md) section 2).

**A9. The unit of the tool window**, through the tournament over the sub-groups of a large
server. An idea, unmeasured.

**A10. A local classifier.** A small LoRA model could take decisions Jev pays for today
(safety, injection, done, relevance). Train only on our own labels or a public bench's, never
on Jev's outputs (check the provider's terms first), and measure it outside its training set.

## Done

- **A1** (`de7c38a`, 2026-10-15): the benches take `TYPESAFE_API_KEY` from the environment, or
  from the `.env` file `SANCHOPANZA_KEYS_ENV` names, with no default file; the identifiers no
  longer carry another project's name ([`benchmarks/README.md`](../benchmarks/README.md)).
- **A2** (2026-10-15): the README's "What is open" says the candor lock is per session (`4fa334f`)
  and `unchanged_output` locks only on a contradiction with the record (v7, `1c7d2be`); the
  guard-struct README and the README's guard section give the live probe's result (`cb0062e`);
  the root `STATUS*.md` moved to [`docs/history/`](history/).
- **B2** (`872e068`, merge `ef41b6d`): a sentence break also comes before an accented capital,
  `¿`, `¡` or `«`, and not after a Spanish abbreviation; English splits as before (2 of 458,860
  strings change) and the published `select_passages` masks are unchanged.
- **B3** (`a1a04db`, merge `ef41b6d`): a paragraph the tournament did not answer is kept whole
  with no sentence call, and `max_calls` caps one document's calls, reserved before any await;
  the sentence stage gets what the tournament left, surest paragraphs first. Opt-in: default
  `None`.

## Already in sanchopanza, asked by the consumer

- `points/chunks.py` and `Thresholds.pages_in_context` (0.40) are committed (`policy.py`).
- A warning if Jev ever sends its own confidence on a Truth answer
  (`truth_wire_confidence_differs`, `providers/jev.py`).
- A pinned model, not an alias (`DEFAULT_MODEL = "jev-1.13.0"`).
- `allowed_kinds` / `denied_kinds` on the source kind (`points/triage.py`).
- A Jev balance of zero no longer fails open in silence (`funds.py`, `jev-preflight`).
- Content fetched through the shell is scanned with `--scan-content`; `Read` and `WebFetch` too.
- The candor lock per session, and `unchanged_output` v7.
- 50 cases per point and a blind second annotator on the six binary points; thresholds move to a
  precision target ([where it pays](where-it-pays.md) section 6, item 3).
- Attachments in the state: a text-only decider refuses them out loud (`providers/jev.py`).
- The guard split, probed live (`cb0062e`).
