# E offline: a more demanding check-done on GAIA (2026-10-07)

Free: no session, no Jev. Read from the GAIA confirmation of 2026-10-06 (Sonnet 5.5, 135 tasks
per arm), scored in memory with GAIA's scorer and the blind hand verdicts. Counts only; no
question, answer or tool result is printed or written. Script kept outside the repository
(it only reads the private rows and transcripts).

## Question

check-done sent S back 18 times in GAIA: 2 answers went from wrong to right, 10 right answers were
sent back for nothing, 6 wrong ones stayed wrong, none was harmed. Can a stricter check keep the 2
and drop the 10?

## 1. Jev's own probability: no

The 2 useful send-backs had p 0.12 and 0.20; the 10 useless ones 0.04 to 0.49 (0.04 0.07 0.08 0.12
0.14 0.21 0.24 0.38 0.43 0.49); the 6 that stayed wrong 0.04 to 0.25. Any stricter cut loses both.

## 2. A verifiable signal in code: no

Features of the answer before any send-back, over all 270 sessions (65 wrong, 24 %):

| Feature | Sessions flagged | Wrong among flagged | Wrong among the rest |
|---|---|---|---|
| The final message hedges ("approximately", "likely", "could not", ...) | 97 | 36 % | 17 % |
| The answer appears verbatim in a tool result | 115 | 21 % | 26 % |
| A computation (Bash) ran after the last page read | 75 | 29 % | 22 % |
| The answer is a number | 121 | 24 % | 24 % |
| No tool used | 71 | 27 % | 23 % |
| A number, not in any tool result, nothing computed | 55 | 15 % | 27 % |

Only hedging concentrates wrong answers, and weakly: a check-done that sent back hedged answers
would flag 36 % of sessions at 36 % wrong. Jev's check-done as shipped already does better: 13 % of
S's sessions sent back, 44 % of them wrong before the send-back (8 of 18).

## What it says

In GAIA a second look fixes few answers (2 in 135), and neither Jev's probability nor a cheap
verifiable feature tells those few from the rest. E is not a lever: keep check-done as it is (2
fixes, no harm, about 0.78 USD of extra turns over 135 tasks) or leave it out where its cost
matters more than two answers.
