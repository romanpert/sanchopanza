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
| owner's real commands denied, code list | 4,055 of 33,119 (12.2 %) | 9 (0.03 %): 7 are text inside heredocs, 2 format a disk with `mkfs` |
| owner's real commands denied, code + Jev, seeded sample | not measured | 2 of 300 (a key added to root's `authorized_keys` on a server; one heredoc) |
| guard bench, unsafe / safe denied | 17/17 / 0/15 (list written after seeing it) | 12/17 / 0/15 |
| R-Judge, unsafe / safe trajectories flagged | 7/15 / 3/12 (broad run) | 6/15 / 3/12 |

The coding profile stops about forty times less real work and flags R-Judge alike; it misses 5
of the 17 commands the sandbox list was written to catch. Jev cost 0.0124 USD. The real commands
and the recorded answers stay local (they hold the owner's paths and hosts).

Limits: one person's commands; "denied real work" is not the same as "false positive" (the one
sampled denial is a change a person would want to approve); R-Judge's n is small.

## After the adversarial review (same day)

A review found the first coding list too loose and too tight in places, and every finding was
fixed with a test (`tests/test_guard_coding.py`): `-i` was stripped from every command, which hid
`curl -i -d @.env` (now only inside `ssh`/`scp`/`sftp`); **the PowerShell tool, Claude Code's
shell on Windows, was not guarded at all** (it is now, in both profiles); recursive deletes with
`--`, long flags, `${HOME}`, a Git Bash drive or `find / -delete` passed; `bash <(curl ...)`,
`sh -c "$(curl ...)"`, `| python` and `iwr | iex` passed; a reinstall overwrote a profile the owner
had set; the decider was told the live `cwd` was writable (now the project directory). A bare
`rm -rf *` or `rm -rf .` is now the decider's to judge: after `cd build` it is ordinary cleanup.
The numbers above are after these fixes; the decider answers for commands whose state changed
are replayed from the recording where they exist.

## Asking only when there is something to deny (same day)

In the adoption study's second pygments session the shell guard took **1.23 s per shell call**
(median; 139 s in one session) and asked the decider on 92 of 102 calls without denying one. The
coding profile now asks only when the command carries a risk signal (`points.guard.CODING_ASK`: a
delete, permission or process command where a command stands, network tools, device writes,
`python -c` or `node -e` that touches the network, the environment or `exec`, pushes and hard
resets, secret file shapes, redirects outside the tree, pipes into a shell). It asks on **2.2 %**
of the study's 552 shell commands and **12.5 %** of the owner's real ones, and the bench and
R-Judge numbers above are unchanged with it (12/17 and 0/15; 6/15 and 3/12).
