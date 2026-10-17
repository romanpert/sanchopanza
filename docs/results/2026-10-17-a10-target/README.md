# A10 with labels from the target environment: in-domain labels close much of the gap, not all of it

**The result:** by the planned rule, **"no concluyente"**. A local check_done classifier trained on
AgentDojo's own labels in the suites it is scored on (banking, travel, workspace), never on the
user task it scores, ranked 2,522 stops at **AUC 0.812** against **0.861** for Jev 1.14 on the
same stops: **−0.049, cluster bootstrap 95 % [−0.104, +0.004]**, against a −0.05 margin. Not
shown to be as good as Jev, and not shown to be worse.

Against A10's cross-suite classifier (slack labels only), in-domain labels gained **+0.048 AUC
[−0.007, +0.104]** on the same stops: about half of A10's gap closes, but the interval reaches 0.
Training each agent only on its own stops did best: **−0.023 [−0.075, +0.029]** against Jev.

Free: no model was called. Planned in [`plan.md`](plan.md), committed with the code before any
held-out stop was scored; the run refused unless the plan and the code were committed, and it
records the commit (`99bbb1a`) and the plan's sha256 (`befa14b0…`).

## What ran

- **Stops:** 2,522 AgentDojo trajectories, its authors' published runs (MIT) of
  `claude-3-7-sonnet-20250219` (950), `claude-3-5-sonnet-20241022` (622) and
  `gemini-2.0-flash-001` (950) in banking (507), travel (501) and workspace (1,514); 1,623 finished,
  899 not; 106 user-task clusters. Every file checked by git blob sha against the manifests of
  lots checkdone114 and checkdone-w17.
- **Labels:** AgentDojo's `utility`, its own check of the environment's final state. No Jev in
  the agents' loop: neither the text nor the label is an effect of a Jev decision (TypeSafe's
  MCA 2.3(b) forbids training on Jev's outputs).
- **Model:** A10's, unchanged (TF-IDF over word 1-2-grams, character 3-5-grams, the last agent
  message and structure tokens; logistic regression, C = 1). Nothing was tuned on these stops.
- **Primary split:** five folds of whole user-task clusters within each suite; all three agents'
  runs of a task in the same fold. Each stop is scored by the model fitted on the other four.
- **Jev:** `jev-1.14.0`'s recorded p(done) on the same record (lots checkdone114 and
  checkdone-w17), joined after every fit, for the comparison only.

## Primary result

| | AUC on the 2,522 | Local minus Jev 1.14 | Cluster bootstrap 95 % | Reading at −0.05 |
|---|---|---|---|---|
| Jev 1.14 | 0.861 | | | |
| **Local, in-domain labels** | **0.812** | **−0.049** | **[−0.104, +0.004]** | **no concluyente** |

## Secondary (none changes the primary)

| Arm, against Jev 1.14 on the same stops | Stops | Local | Jev | Difference | 95 % (clusters) | Reading |
|---|---|---|---|---|---|---|
| Strict: disjoint in user task **and** injection task | 753 | 0.823 | 0.868 | −0.045 | [−0.098, +0.004] | no concluyente |
| Each agent's own labels only | 2,522 | 0.838 | 0.861 | −0.023 | [−0.075, +0.029] | no concluyente |
| No target labels (A10's slack model) | 2,522 | 0.764 | 0.861 | −0.097 | [−0.151, −0.047] | no concluyente |

- **The strict split** removes the leak the primary leaves (an injected payload seen under other
  user tasks in training). It reads the same as the primary, so that leak did not flatter it.
- **In-domain against cross-suite:** +0.048 [−0.007, +0.104] (local in-domain minus A10's
  model). A10's model scored 0.655 on the 950 alone; on all 2,522 it scores 0.764.

**By suite** (in-domain local / Jev, difference and interval):

| Suite | Stops | Local | Jev | Difference | 95 % |
|---|---|---|---|---|---|
| banking | 507 | 0.751 | 0.872 | −0.121 | [−0.236, −0.011] |
| travel | 501 | 0.852 | 0.893 | −0.041 | [−0.152, +0.043] |
| workspace | 1,514 | 0.808 | 0.855 | −0.047 | [−0.114, +0.015] |

**By agent** (pooled labels / the agent's own labels, each against Jev):

| Agent | Stops | Jev | Pooled | Difference, 95 % | Own | Difference, 95 % |
|---|---|---|---|---|---|---|
| claude-3-5-sonnet | 622 | 0.770 | 0.756 | −0.014 [−0.131, +0.096] | 0.736 | −0.034 [−0.155, +0.085] |
| claude-3-7-sonnet | 950 | 0.814 | 0.726 | −0.088 [−0.217, +0.045] | 0.781 | −0.033 [−0.126, +0.064] |
| gemini-2.0-flash | 950 | 0.882 | 0.759 | −0.123 [−0.191, −0.063] | 0.782 | −0.099 [−0.163, −0.042] |

On gemini-2.0-flash's stops the pooled arm reads "peor" by the rule (the whole interval below
−0.05); its own-labels arm narrowly misses that zone. The subgroups are small and not the
verdict.

**Per fold** (descriptive; the pooled AUC mixes five fitted models): mean AUC Jev 0.863, local
in-domain 0.825, own-agent 0.843, A10's model 0.761. The local arm was ahead of Jev in one fold
of five (0.901 against 0.833).

## What this licenses, and what it does not

- **Labels from the setting help.** With the same model, in-domain labels lift the ranking from
  0.764 to 0.812 on the same stops, and to 0.838 when each agent is trained on its own runs. A
  local provider still needs labels from the setting it serves; A10's conclusion holds.
- **Not shown to match Jev.** Every interval against Jev reaches below −0.05. The primary's point
  estimate sits at the margin.
- **The interval is set by 106 user tasks, not 2,522 stops.** A confirmation that could separate
  "no peor" from "peor" needs more distinct tasks, not more runs of the same ones.
- **Not tested:** a stronger model (an encoder or a fine-tuned one, trained on own labels only),
  a cut and its false blocks and catches, coding sessions instead of AgentDojo, a split by time.

## Caveats

- AgentDojo stops, not coding sessions; one model family (n-grams and logistic regression).
- "In-domain" means the same suites, tools and task distribution with a new user task. A user
  whose sessions repeat the same tasks would see less shift; one whose tasks change, more.
- Jev may have seen these public files in training; the local model saw only its fitting folds.
- Known before the run: Jev's AUC on these stops (0.814 on the 950, 0.865 on the 1,572), the
  label mix, and A10's model's 0.655 on the 950. No in-domain fit had been run.

## Files

- `plan.md`: the plan, committed before the run.
- `analysis.json`: every comparison, with the commit, the plan's sha256, the folds and the fits.
- `scored.jsonl`: each stop's id, cluster, agent, label, fold and the four local probabilities
  (`p_target`, `p_strict` (null where the strict split does not score), `p_agent`, `p_a10`); no
  text, no Jev probability (those stay in their own lots).
- Code: `benchmarks/a10_local/a10_target.py` (splits, fits, analysis), `target.py` (the run);
  tests in `tests/test_a10_target.py`.

```bash
python benchmarks/a10_local/target.py run      # needs the AgentDojo files of both lots, fetched
python -m pytest tests/test_a10_target.py
```
