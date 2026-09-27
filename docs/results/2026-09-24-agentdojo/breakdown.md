# Injection detection on third-party data

273 cases harvested from AgentDojo v1.2.2: 124 carrying a real attack payload, 149 the same tool outputs without one. Labels are by construction, not by annotation. Nothing here was written by us.

### 1. The two errors are not the same error

| Threshold | Caught | False alarms | 95 % CI on false alarms | Correct |
|---|---|---|---|---|
| plain 0.5 cut | 112/124 = 90% | 0/149 = 0.0% | [0.0%, 2.5%] | 261/273 |
| shipped, above 0.70 | 101/124 = 81% | 0/149 = 0.0% | [0.0%, 2.5%] | 250/273 |

### 2. By attack template, against a keyword baseline

| Attack | n | Caught by the question | Caught by a regex |
|---|---|---|---|
| `captcha_dos` | 9 | 6/9 | 9/9 |
| `direct` | 9 | 5/9 | 0/9 |
| `dos` | 9 | 8/9 | 9/9 |
| `felony_dos` | 9 | 5/9 | 9/9 |
| `ignore_previous` | 13 | 12/13 | 13/13 |
| `important_instructions` | 13 | 12/13 | 13/13 |
| `important_instructions_no_names` | 9 | 8/9 | 9/9 |
| `injecagent` | 12 | 11/12 | 12/12 |
| `offensive_email_dos` | 9 | 9/9 | 9/9 |
| `swearwords_dos` | 9 | 4/9 | 9/9 |
| `system_message` | 12 | 10/12 | 12/12 |
| `tool_knowledge` | 11 | 11/11 | 11/11 |

### 3. The whole bench, both ways of deciding

| Detector | Caught | False alarms | Correct |
|---|---|---|---|
| Calibrated question, above 0.70 | 101/124 | 0/149 | 250/273 |
| Keyword regex | 115/124 | 0/149 | 264/273 |

### 4. Where the payload starts

| Payload starts | n | Caught |
|---|---|---|
| within the first 2000 characters | 117 | 101/117 |
| beyond them | 7 | 0/7 |

This recording asked the question over the first 2000 characters of each output, so the seven payloads that start later were never shown to it: the second row is not a model result. The package reads long outputs in overlapping 2000-character windows (`points.injection.windows`); the README gives the live re-run of those seven cases.

### 5. By application

| Suite | n | Caught | False alarms |
|---|---|---|---|
| banking | 31 | 14/16 | 0/15 |
| slack | 42 | 20/26 | 0/16 |
| travel | 98 | 27/29 | 0/69 |
| workspace | 102 | 40/53 | 0/49 |
