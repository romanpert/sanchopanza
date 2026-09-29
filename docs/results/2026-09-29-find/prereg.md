# Repository search on SWE-bench Verified: pre-registration

Written 2026-09-29, before any arm ran on the sample. `prereg.sha256` holds the hash of this file
together with the code it names (`prereg.manifest.json`).

## The question

An agent in Claude Code or Codex that gets an issue first has to find where to look.
`sanchopanza.context.repo` answers that, and nothing about it is specific to Indagis:

1. it cuts the repository into fragments (top-level definitions for code, paragraphs for prose);
2. BM25 over path and text keeps a shortlist of 60;
3. with a decider, `select` → `Squire.triage_many` judges the shortlist in context, the
   tournament measured on HotpotQA pages (docs/results/2026-09-27-hierarchy/).

It is exposed as `find_in_repo` in the archive MCP server (opt-in, `SANCHOPANZA_FIND=1`) and as
`python -m sanchopanza.context.repo`.

## Data and label

- **Data:** `princeton-nlp/SWE-bench_Verified`, revision
  `c104f840cc67f8b6eec6f759ebc8b2693d585d4a`. 500 real issues from 12 Python repositories.
- **Sample:** seeded (20260929), at most 12 instances per repository. That gives 117 instances
  and 141 gold files; django has 12, not 231.
- **Label:** the files the accepted patch edits, parsed from `diff --git` headers. Nobody here
  labels anything.
- **Checkout:** each instance runs on its repository at its `base_commit`.
- **Plumbing check:** one django instance **outside the sample** (django__django-10097) was run
  with no decider, to check timing (33,636 fragments, 32 s to index). No arm has run on the
  sample.

## Arms (`benchmarks/find/swebench.py`)

- **`file_bm25`:** BM25 over whole files (path and text), the SWE-bench paper's retrieval
  baseline.
- **`frag_bm25`:** fragments ranked by BM25; files in order of their first fragment.
- **`frag_judge`:** the product path. `select` over the 60-fragment shortlist with Jev
  (`jev-1.13.0`) through `Squire.triage_many`. Kept fragments come first, by p; then the rest of
  the shortlist by BM25.

For all three arms:

- **Query:** the issue text.
- **Judge's purpose:** "Find the code or text a developer must read to work on this: <issue>",
  cut to 400 characters by the question's limit.
- **Metrics:** any@k (a gold file in the top k files) and all@k (every gold file in the top k),
  for k = 1, 3, 5, 10.
- **Ceiling:** the share of instances with a gold file among the 60 shortlisted fragments.

## Hypotheses (`summary()` in the same file)

- **F1:** `frag_judge` any@5 >= `file_bm25` any@5 + 10 points.
- **F2:** `frag_judge` any@1 >= `frag_bm25` any@1 + 5 points. This is what the judge adds over
  its own shortlist.
- **F3:** the judge's median cost per instance is <= 0.005 USD.

Reported without a verdict: every arm at every k, per repository, the ceiling, and the judge's
latency.

What published numbers mean here: agent-based localisation systems report higher any@5 than
BM25. They read the repository with a generative model over many turns, which is a different
cost class. They are context, not a comparison.

## Budget

Jev only: about 3 calls per instance of about 9,000 tokens each at 0.042 USD per million, about
0.13 USD for the 117. The cap is 0.50 USD, set in code (`swebench.JEV_CAP_USD`) and counted by
the decider. A per-instance meter of 0.05 USD sits on top. Answers are recorded and replay free.

Whatever does not hold is reported as not holding.
