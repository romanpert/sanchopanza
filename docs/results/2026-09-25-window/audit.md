# Audit of the policy layer, 2026-09-25

Three of the four defects found on 2026-09-24 were in the policy, not the model, and the
policy layer had never been audited. This is that audit: every `decide*` function in
`points/` except `tools.py` (reworked the same day, see `README.md`), plus the orchestration
in `squire.py`, read as multi-criteria rules. It was run by an independent reviewer told to
destroy each candidate before reporting it, and every surviving finding was confirmed by
building the exact `Decision` that produces the wrong action and calling the real function.

**The headline: the dominant defect was not gate order or shared knobs. It was an absent
answer read as permission.** `probability(answer)` returns 0.0 for an answer that does not
exist, so a missing "is this about a person?" reads as a confident no, a missing direction
as a confident yes. Six of the fifteen findings are that one shape.

**Replaying all 1,153 recorded bench cases before and after the fixes changed zero
predictions** (1,141 non-null on both sides). These are paths no recorded case reaches -
which is exactly why no test caught them. `tests/test_audit_fixes.py` builds each one.

## Fixed

| | where | defect | fix |
|---|---|---|---|
| F1 | `plan.decide_line` via `routing.decide` | plan lines never ask `person_risk`; the absent answer read as "not a person", so a line about one could go to the light tier | a downgrade now needs `person_risk` **answered**; plan lines stay at the default tier |
| F2 | `routing.decide` | the same, for any provider that omits the key; and an answered 0.65 ("probably a person") still downgraded, because `risk` fires at 0.7 | a downgrade needs `person_risk` answered **and** a confident no (`p <= 1 - act`). Applied after a second review, and kept because replaying the 1,153 cases changed zero predictions |
| F4 | `graph.decide_edge` | an absent `direction` committed the edge on `stated` alone | absent direction goes to review, as the comment beside it already said |
| F6 | `memory.decide_collision` | "adds nothing" and "contradicts" both high: duplicate won by position and a correction was discarded | incoherent readings are flagged |
| F7 | `memory.decide_write` | an absent `derivable` stored; and the gate read `act`, where raising it stored *more* | absent answer does not store; the gate has its own knob `derivable = 0.75` (same value) |
| F8 | `Squire.scan_content` | a failed window scored 0.0, the scan came back clean, and the journal claimed full coverage; coverage ignored the 200-character overlap (8 windows cover 14,600 characters, not 16,000) | failed windows are counted, coverage is computed from the windows actually judged, and `Flag.complete` says whether the whole text was read. `ToolWindow` adds nothing on an incomplete scan |
| - | `tools.decide` | did not pass the `deferred` answer to `select`, so the deferral guard ran only through the squire | passed, with its own knob `deferred = 0.60` instead of borrowing the confidence knob `relax` |
| - | `harness/langchain.py` | re-selected on every model call: a paid decision per call, and a different `tools` array each turn - the 4.15x churn pattern, in the package's own adapter | a per-conversation `ToolWindow`, opened once and only widened |

F5 is half-fixed: `decide_collision` said "no contradiction (0.65)" for a contradiction below
the bar to act. The reason text is fixed. Whether that band should *flag*, as the module
docstring promises, is open: the two recorded cases in it are labelled `replace` and `flag`,
and changing the policy on the cases that exposed it is what rule 7 forbids.

## A second review, of the code written today

An independent code review of the window and its adapters found two HIGH defects in code
written the same day, both confirmed with fake deciders and both fixed:

- **`load_tools` let untrusted content widen the window.** It scanned the `need` the model
  writes - which, after reading an injection, is a plain "pay the invoice to this IBAN" that
  no injection question flags - and its "best group anyway" fallback let four vague loads open
  the whole catalog. Now a request is judged by the selection question on the *user's*
  purpose with `need` only as a clue, nothing is added below the threshold, and after a
  blocked tool result the window refuses requests until the next user turn
  (`ToolWindow.request`, `ToolWindow.tainted`).
- **The LangChain adapter could freeze the window on a later turn**: an outage or an
  exhausted budget on turn two left the tools of turn one in place. A user turn now adds every
  group nobody answered for (`tests/test_window.py`,
  `test_a_user_turn_during_an_outage_opens_what_nobody_answered_for`).

And three MEDIUM/LOW: conversations sharing a fallback key stopped widening (the window now
remembers which human messages it saw, and callers can pass `key_of`, e.g. a thread id);
`max_windows = 0` reported a clean *complete* scan; a `ToolWindow` opening a new conversation
raised the session-churn warning. The review's point that `reversed` is read before
`unsupported` in `decide_edge` is F3 below and stays open for the reason given there.

## Open, and why each stays open

| | defect | why not fixed today |
|---|---|---|
| F3 | `decide_edge` answers `reversed` for a relation that is not in the text at all (`ed-11`): `direction` is conditional on the relation being there, and `stated`'s criteria call "states the reverse" false, so `unsupported` and `reversed` cannot be told apart with these two questions | needs a third question ("is the relation there in either direction?"). A new question invalidates the edge recordings; pre-registered, with its cases to be written before it is measured |
| F9 | `verify_edge`'s literal mention check returns `unsupported` at confidence 1.0 on coreference ("Su licencia", "filial portuguesa"); 5 of 50 edge cases never reach the model, 4 labelled `supported` | errs in the safe direction; the honest fix (`review` instead of a confident verdict) changes five published predictions, so it goes with F3's re-measurement |
| F10 | `triage_results` can keep nothing: five pages at relevance 0.40 and evidence 0.90 all drop | this is the covering-constraint family (see the queue); a floor is a policy change that needs its own bench |
| F11 | `t.saturated` serves plan saturation, `goal_met` and `repeats_check` | **measured, free, from the recordings**, and the bench now scores both loop points at the 0.70 the policy applies (`tests/test_policy_in_force.py`): `goal_met` 46/50 with 0 false alarms and 4 silent, `repeats_check` 50/50; at a plain 0.5 cut, 49/50 each. The policy errs in the cheap direction: it never calls a goal met that is not. The shared knob stays: no sample says the three points need different values |
| F12 | `review.decide`: one absent answer silences a strong `unsourced` warning | safe direction (says less, never more) |
| F13 | answers paid for and never read: `needs_browser` on every routing call; `depends_on_others` overwritten by the DAG for plans of 2 to 8 lines | removing a question changes the state hash and invalidates every routing recording |
| F14 | the triage drop (p < 0.45) and redundant-page drop (0.59) contradict the asymmetry `policy.py` states | both values are measured or derived; the documentation is what is wrong |
| F15 | `entities.decide_facts` shares `relax` with routing and edge direction | same class as `t.redundant` and `deferred`; no sample to derive its own value |

## The method note

The reviewer was told what the last three defects looked like and asked to look for more of
the same. It found something else. Gate order and shared knobs turned up (F3, F11, F15), but
the most common shape was one nobody had named: **the default of an accessor standing in for
an answer.** Worth a line in the checklist for any new point - a missing answer must be
checked with `.empty` before its probability is read, whenever the default would push the
decision in the costly direction.
