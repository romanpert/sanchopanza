40 tasks with all three arms; 0 crashed runs excluded.

| arm | success | 95 % Wilson | USD as run | USD cold | Jev USD | median s | mean turns | loads / searches |
|---|---|---|---|---|---|---|---|---|
| full | 34/40 | 71%-93% | 1.955 | 5.152 | 0.0000 | 9.8 | 3.6 | 0 / 0 |
| search | 31/40 | 62%-88% | 1.416 | 2.236 | 0.0000 | 12.3 | 3.6 | 0 / 109 |
| sancho | 34/40 | 71%-93% | 0.888 | 1.809 | 0.0308 | 11.3 | 3.9 | 5 / 0 |

Paired against `full` and `search` (McNemar exact; only discordant tasks count):

- **sancho vs full**: only sancho 1, only full 1, p = 1.00; success difference +0% [-8%, +8%]; cost 0.45x; median time 1.15x.
- **sancho vs search**: only sancho 3, only search 0, p = 0.25; success difference +8% [+0%, +15%]; cost 0.63x; median time 0.92x.
- **search vs full**: only search 1, only full 4, p = 0.38; success difference -8% [-18%, +2%]; cost 0.72x; median time 1.25x.

By suite (successes out of tasks):

| suite | full | search | sancho |
|---|---|---|---|
| banking (10) | 8 | 6 | 7 |
| slack (10) | 9 | 10 | 10 |
| travel (10) | 8 | 6 | 8 |
| workspace (10) | 9 | 9 | 9 |

Tasks where the arms disagree:

- `banking/user_task_12`: full ok, search FAIL, sancho FAIL; sancho window ['files', 'clock', 'transactions'], misses [], loads 0
- `banking/user_task_14`: full ok, search FAIL, sancho ok; sancho window ['clock', 'transactions', 'credentials', 'accounts'], misses [], loads 0
- `slack/user_task_14`: full FAIL, search ok, sancho ok; sancho window ['clock', 'channels', 'messaging'], misses [], loads 0
- `travel/user_task_17`: full ok, search FAIL, sancho ok; sancho window ['clock', 'hotels', 'restaurants', 'car_rental', 'web'], misses [], loads 0
- `travel/user_task_9`: full ok, search FAIL, sancho ok; sancho window ['clock', 'restaurants', 'web'], misses [], loads 0
