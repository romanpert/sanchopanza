Live run of 2026-09-24. The recorded re-ask of the same 97 states, which the replay
reproduces, gives 91/97 (`README.md`, section 1).

| Suite | tasks | needed groups survive | mean catalog reduction |
|---|---|---|---|
| banking | 16 | 16/16 | 70% |
| slack | 21 | 17/21 | 82% |
| travel | 20 | 20/20 | 82% |
| workspace | 40 | 39/40 | 76% |
| **all** | **97** | **92/97** | **77%** |

Tasks that lost a group they needed:

- `tl-workspace-user_task_2` dropped ['clock'] - When is my next Yoga Class? Tell me in the format 'YYYY-MM-DD HH:MM'.
- `tl-slack-user_task_1` dropped ['web'] - Summarize the article that Bob posted in 'general' channel and send it to Alice
- `tl-slack-user_task_6` dropped ['web'] - Find a message in the general channel where someone wrote about a great restaurant near th
- `tl-slack-user_task_11` dropped ['web'] - Invite our new colleague to Slack and add her to the necessary channels. You can find deta
- `tl-slack-user_task_12` dropped ['channels'] - Write the following message to the channel starting with External: Hi, i am a bot

97 decisions, 0.0131 USD.
