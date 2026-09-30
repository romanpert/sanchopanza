# The shell guard inside a person's repository: sandbox profile against coding profile

Run 2026-09-30, not pre-registered: a defect found in the adoption pilot
(`../2026-09-30-adopt/`), measured to choose the fix. Numbers in `measure.json`; the script is
`benchmarks/guard_coding/measure.py`.

**What was wrong.** `sanchopanza install` has always wired the shell guard into Claude Code. Its
code deny-list and its question to the decider were written for Indagis's agent: web research in
a container whose writable path is `/workspace`. In a coding session both are the wrong frame:

- in the pilot, the agent's `rm -f` of its own two scratch files inside its repository was
  denied by the decider (0.81): asked about "a web-research job", a path outside `/workspace`
  looked like destruction;
- over the owner's 33,119 distinct real Bash commands from their Claude Code sessions, the code
  list alone would have denied **12.2 %**: "su " in Spanish text read as `su`, any mention of
  `.env` or `credentials`, `|| python -m unittest` read as piping into Python, `ssh` to their own
  servers, `chmod +x`.

**The fix.** A `coding` profile, written by `sanchopanza install` by default
(`SANCHOPANZA_GUARD_PROFILE=coding`; `--guard-profile sandbox` keeps the old one, which stays the
hook's default so the R-Judge and ATBench replays are unchanged):

- a narrow code list of what is unambiguous in any repository: wiping a root, a home or the
  whole working tree, running a download, sending key or secret files out (a key named with
  `-i` to authenticate is not sent), writing to a device, a fork bomb, a world-writable root;
- the decider asked whether a person would not want an agent in their repository to do this
  unasked, with the session's own working directory as the writable path.

| | sandbox profile | coding profile |
|---|---|---|
| owner's real commands denied, code list | 4,055 of 33,119 (12.2 %) | 4 (0.01 %), all text inside heredocs |
| owner's real commands denied, code + Jev, seeded sample | not measured | 1 of 300 (adding a key to root's `authorized_keys` on a server) |
| guard bench, unsafe / safe denied | 17/17 / 0/15 (list written after seeing it) | 12/17 / 0/15 |
| R-Judge, unsafe / safe trajectories flagged | 7/15 / 3/12 (broad run) | 6/15 / 3/12 |

The coding profile stops about forty times less real work and flags R-Judge alike; it misses 5
of the 17 commands the sandbox list was written to catch. Jev cost 0.0124 USD. The real commands
and the recorded answers stay local (they hold the owner's paths and hosts).

Limits: one person's commands; "denied real work" is not the same as "false positive" (the one
sampled denial is a change a person would want to approve); R-Judge's n is small.
