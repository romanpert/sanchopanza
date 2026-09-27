# mcp_wide: a wide catalog of real MCP tools

`catalog.json` holds **1,497 tool definitions from 55 public MCP servers**, harvested on
2026-09-25. It exists to stress-test a *tool window*: a per-session subset of a large
catalog, chosen by a cheap classifier. Real catalogs contain near-duplicates and overlapping
domains, and invented catalogs don't, so this one is built only from real servers.
Examples: three `create_branch` tools, two invoice APIs, four ways to send an email and five
ways to fetch a web page.

`stub_server.py` serves the catalog (or part of it) over MCP stdio. Every call fails, so an
agent can see and choose tools without anything happening.

## Where the tools came from

No definition was written by hand. Each server was **started and asked with
`initialize` + `tools/list`**, and its answer was copied as-is: name, description and
`inputSchema`. This gives the definitions exactly as the published code emits them. That is
more reliable than converting zod, pydantic or Go structs by reading the source, where a
translation error would go unnoticed.

| How | Servers |
|---|---|
| stdio, published npm package (`npx`, or the local install for `gitnexus`) | 38 |
| stdio, published PyPI package (`uvx`, or the local install for `code_review_graph`) | 10 |
| stdio, official Docker image | 2 (`github`, `grafana`) |
| Streamable HTTP, public remote endpoint with no auth | 5 (`kiwi`, `cloudflare_docs`, `deepwiki`, `huggingface`, `open_targets`) |

Servers that refuse to start without credentials got **dummy** values: `ghp_dummy`, a fake
OAuth client file, an unreachable database URL, a sandboxed home directory. `tools/list`
does not need a real account for any server included here. No real credential was used. No
tool was ever called.

Each server entry carries its provenance:

- `source`: the repository or official page, or `local tools/list` for the four servers
  harvested from MCP configurations on the harvesting machine.
- `harvest`: package, exact version and how it was started, including any pin needed to make
  an archived package run.
- `server_info`: what the server reported in `initialize`.
- `about`: the opening line of the server's README. For the remote servers that have no
  README (`kiwi`, `deepwiki`, `huggingface`), it is the opening line of the `instructions`
  they return in `initialize`. It is trimmed of markdown links and badges.

Descriptions are verbatim, cut at 1,000 characters (63 tools were cut). Every schema has
`"type": "object"` and passes `check_schema` with `jsonschema` (Draft 2020-12, or draft-07
where the schema declares it). `$schema` keys are kept as emitted: 483 schemas declare
draft-07, 244 declare 2020-12 and 770 declare nothing.

## Counts per server

Chars = description + serialized `input_schema`, summed over the server's tools.

| Server | Tools | Chars | Source |
|---|---:|---:|---|
| `filesystem` | 14 | 7,382 | [modelcontextprotocol/servers/src/filesystem](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) |
| `memory` | 9 | 3,837 | [modelcontextprotocol/servers/src/memory](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) |
| `everything` | 13 | 4,315 | [modelcontextprotocol/servers/src/everything](https://github.com/modelcontextprotocol/servers/tree/main/src/everything) |
| `sequentialthinking` | 1 | 2,210 | [modelcontextprotocol/servers/src/sequentialthinking](https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking) |
| `git` | 12 | 4,262 | [modelcontextprotocol/servers/src/git](https://github.com/modelcontextprotocol/servers/tree/main/src/git) |
| `fetch` | 1 | 1,104 | [modelcontextprotocol/servers/src/fetch](https://github.com/modelcontextprotocol/servers/tree/main/src/fetch) |
| `time` | 2 | 919 | [modelcontextprotocol/servers/src/time](https://github.com/modelcontextprotocol/servers/tree/main/src/time) |
| `github_archived` | 26 | 15,232 | [servers-archived/src/github](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/github) |
| `gitlab` | 9 | 5,217 | [servers-archived/src/gitlab](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/gitlab) |
| `slack` | 8 | 2,726 | [servers-archived/src/slack](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/slack) |
| `google_maps` | 7 | 2,351 | [servers-archived/src/google-maps](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/google-maps) |
| `postgres` | 1 | 86 | [servers-archived/src/postgres](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/postgres) |
| `puppeteer` | 7 | 2,128 | [servers-archived/src/puppeteer](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/puppeteer) |
| `brave_search` | 2 | 1,362 | [servers-archived/src/brave-search](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/brave-search) |
| `aws_kb` | 1 | 428 | [servers-archived/src/aws-kb-retrieval-server](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/aws-kb-retrieval-server) |
| `everart` | 1 | 850 | [servers-archived/src/everart](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/everart) |
| `sqlite` | 6 | 993 | [servers-archived/src/sqlite](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/sqlite) |
| `sentry_archived` | 1 | 535 | [servers-archived/src/sentry](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/sentry) |
| `redis` | 4 | 850 | [servers-archived/src/redis](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/redis) |
| `github` | 90 | 101,890 | [github/github-mcp-server](https://github.com/github/github-mcp-server) |
| `notion` | 24 | 78,535 | [makenotion/notion-mcp-server](https://github.com/makenotion/notion-mcp-server) |
| `stripe` | 22 | 16,881 | [stripe/agent-toolkit](https://github.com/stripe/agent-toolkit) |
| `playwright` | 25 | 16,538 | [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) |
| `supabase` | 29 | 15,819 | [supabase-community/supabase-mcp](https://github.com/supabase-community/supabase-mcp) |
| `sentry` | 9 | 19,449 | [getsentry/sentry-mcp](https://github.com/getsentry/sentry-mcp) |
| `atlassian` | 98 | 81,618 | [sooperset/mcp-atlassian](https://github.com/sooperset/mcp-atlassian) |
| `kubernetes` | 23 | 22,789 | [Flux159/mcp-server-kubernetes](https://github.com/Flux159/mcp-server-kubernetes) |
| `google_calendar` | 13 | 33,785 | [nspady/google-calendar-mcp](https://github.com/nspady/google-calendar-mcp) |
| `todoist` | 47 | 56,494 | [Doist/todoist-ai](https://github.com/Doist/todoist-ai) |
| `airtable` | 16 | 10,508 | [domdomegg/airtable-mcp-server](https://github.com/domdomegg/airtable-mcp-server) |
| `hubspot` | 21 | 36,083 | [developers.hubspot.com/mcp](https://developers.hubspot.com/mcp) |
| `shopify` | 6 | 18,718 | [Shopify/dev-mcp](https://github.com/Shopify/dev-mcp) |
| `paypal` | 28 | 41,587 | [paypal/agent-toolkit](https://github.com/paypal/agent-toolkit) |
| `airbnb` | 2 | 2,146 | [openbnb-org/mcp-server-airbnb](https://github.com/openbnb-org/mcp-server-airbnb) |
| `chrome_devtools` | 30 | 23,865 | [ChromeDevTools/chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) |
| `mongodb` | 31 | 62,096 | [mongodb-js/mongodb-mcp-server](https://github.com/mongodb-js/mongodb-mcp-server) |
| `tavily` | 5 | 7,768 | [tavily-ai/tavily-mcp](https://github.com/tavily-ai/tavily-mcp) |
| `exa` | 2 | 1,763 | [exa-labs/exa-mcp-server](https://github.com/exa-labs/exa-mcp-server) |
| `firecrawl` | 29 | 48,994 | [firecrawl/firecrawl-mcp-server](https://github.com/firecrawl/firecrawl-mcp-server) |
| `grafana` | 65 | 64,875 | [grafana/mcp-grafana](https://github.com/grafana/mcp-grafana) |
| `google_workspace` | 121 | 193,071 | [taylorwilsdon/google_workspace_mcp](https://github.com/taylorwilsdon/google_workspace_mcp) |
| `gmail` | 19 | 11,896 | [GongRzhe/Gmail-MCP-Server](https://github.com/GongRzhe/Gmail-MCP-Server) |
| `microsoft365` | 188 | 1,019,739 | [Softeria/ms-365-mcp-server](https://github.com/Softeria/ms-365-mcp-server) |
| `resend` | 105 | 107,116 | [resend/resend-mcp](https://github.com/resend/resend-mcp) |
| `linear` | 198 | 89,008 | [tacticlaunch/mcp-linear](https://github.com/tacticlaunch/mcp-linear) |
| `mapbox` | 29 | 56,822 | [mapbox/mcp-server](https://github.com/mapbox/mcp-server) |
| `docker` | 19 | 12,992 | [ckreiling/mcp-server-docker](https://github.com/ckreiling/mcp-server-docker) |
| `kiwi` | 2 | 12,172 | [mcp.kiwi.com](https://mcp.kiwi.com) (remote) |
| `cloudflare_docs` | 2 | 841 | [cloudflare/mcp-server-cloudflare/apps/docs-ai-search](https://github.com/cloudflare/mcp-server-cloudflare/tree/main/apps/docs-ai-search) (remote) |
| `deepwiki` | 3 | 912 | [mcp.deepwiki.com](https://docs.devin.ai/work-with-devin/deepwiki-mcp) (remote) |
| `huggingface` | 4 | 5,404 | [huggingface.co/mcp](https://huggingface.co/mcp) (remote, anonymous) |
| `gitnexus` | 17 | 30,366 | local tools/list (npm `gitnexus` 1.6.9) |
| `code_review_graph` | 24 | 23,015 | local tools/list (PyPI `code-review-graph` 1.27.0) |
| `aemps` | 21 | 16,900 | local tools/list (PyPI `mcp-aemps` 0.5.0) |
| `open_targets` | 5 | 5,765 | local tools/list (remote Open Targets endpoint) |
| **Total** | **1,497** | **2,405,007** | |

**Size is very uneven.** `microsoft365` alone accounts for 42 % of the characters: its
tools are generated from Microsoft Graph and carry large OData parameter lists. At a rough
4 characters per token, the whole catalog is on the order of 600k tokens. That figure is an
estimate, not a count: no tokenizer or API was called. The catalog is far too big to send
whole, which is the point of a window, but budget accordingly when picking subsets.

## Name disambiguation

Tool names must be unique across the file and match `^[a-zA-Z0-9_-]{1,64}$`. Every harvested
name already matched the pattern. **35 names appeared in more than one server.** Each copy of
such a name, in every server where it appears, became `<server>__<name>`, with the upstream
name kept in `original_name`. No server keeps the bare name, so no server is favored by
alphabetical order or by position in the file. This renamed 80 tools. Examples:

- `create_branch`: `github_archived`, `gitlab`, `github`, `supabase`
- `get_file_contents`, `push_files`, `fork_repository`, `create_repository`,
  `search_repositories`, `create_or_update_file`: `github_archived`, `gitlab`, `github`
- `search_issues`: `github_archived`, `github`, `sentry`
- `list_tables`: `sqlite`, `supabase`, `airtable`
- `create_invoice`, `list_invoices`, `create_refund`, `create_product`, `list_products`,
  `cancel_subscription`, `list_disputes`: `stripe`, `paypal`
- `fetch`: `fetch`, `todoist`
- `query`: `postgres`, `gitnexus`
- `explain`: `mongodb`, `gitnexus`
- `list-calendars`: `google_calendar`, `microsoft365`
- `search_docs`: `supabase`, `google_workspace`

Most near-duplicates don't share a name, so the renaming doesn't reveal them. Examples:
`slack_post_message` against `send_gmail_message`, `send-mail` and `send-email`;
`maps_search_places` against Mapbox's search tools; five scrapers (`fetch`, `firecrawl`,
`tavily`, `exa`, `puppeteer`/`playwright`/`chrome_devtools`); three calendar APIs; three Git
hosts. That is the load a classifier has to separate.

## Overlap with AgentDojo's four apps

This catalog was built to collide with AgentDojo on purpose. It does not reproduce
AgentDojo's tools. The overlap is by domain, and it is uneven:

| AgentDojo app | Servers here that cover the same domain | How close |
|---|---|---|
| **workspace**: email | `gmail`, `google_workspace` (Gmail tools), `microsoft365` (Outlook mail), `resend` | Close. Search, read, send, draft, label, and attachments are all here, several times over. |
| **workspace**: calendar | `google_calendar`, `google_workspace` (Calendar), `microsoft365` (calendar) | Close. List, create, update and delete events, and free/busy. |
| **workspace**: cloud drive | `google_workspace` (Drive, Docs, Sheets), `microsoft365` (OneDrive, Excel), `filesystem`, `notion` | Close for files. Sharing and permissions are richer here than in AgentDojo. |
| **slack** | `slack` (reference server: channels, post, reply, history, users) | Partial. There is only one Slack server. It has no invite-user or direct-message tool. AgentDojo's `get_webpage` overlaps `fetch` and the scrapers. |
| **travel** | `kiwi` (flight search), `airbnb` (lodging search), `google_maps` and `mapbox` (places, directions) | Partial and search-only. **Nothing here books a hotel, a restaurant or a car**, and nothing covers car rental. The only "reservation" tools are calendar events. |
| **banking** | `stripe`, `paypal` | **Weak.** These are merchant payment APIs (invoices, refunds, subscriptions, balances). AgentDojo's banking is a personal account: send money, scheduled transactions, IBANs. No public consumer-banking MCP server could be harvested without credentials. |

Honest summary: workspace is covered densely, slack thinly, travel by search only, and
banking only by adjacent payment APIs. Everything else (developer tooling, databases,
observability, CRM, project management, science) is realistic noise.

## Known gaps and choices

- **Skipped, credentials needed to list tools:** `korotovsky/slack-mcp-server` (validates the
  Slack token before serving, so it would have been a second Slack server) and the archived
  `gdrive` server (requires an OAuth token at startup). The remote PubMed and ClinicalTrials
  connectors configured on the harvesting machine returned 403 without auth.
- **Skipped on purpose:** Twilio (`@twilio-alpha/mcp` generates hundreds of tools from
  OpenAPI and would dwarf every other server); the Docker MCP Toolkit gateway (a meta-server
  whose tool set depends on each user's configuration).
- **Stripe is version 0.2.5 of `@stripe/mcp`.** Later releases proxy every call to the
  remote `mcp.stripe.com` and list nothing without a valid key. 0.2.5 is the last release
  that defines its tools locally, from `stripe/agent-toolkit`.
- **Archived reference servers needed pins to start:** `sqlite` and `sentry_archived` with
  `mcp==1.2.0` (plus `httpx` for sentry), `aemps` with `mcp==1.25.0`. The tool definitions
  are theirs. Only the SDK version changed.
- **Tool sets depend on how a server is started.** `github` uses `GITHUB_TOOLSETS=all`.
  `microsoft365` uses its default personal-account set; `--org-mode` exposes 344 tools.
  `playwright` uses default capabilities. `huggingface` was queried anonymously; logged in, it
  exposes more. `google_workspace` has no OAuth client configured, which is why it lists
  `start_google_auth`. `atlassian` had dummy Jira and Confluence URLs, which enable both
  products.
- **Community servers** stand in where there is no official one that runs locally: Gmail,
  Google Calendar, Google Workspace, Microsoft 365, Linear, Kubernetes, Docker, Airtable,
  Airbnb, Atlassian.
- **Versions move.** Every definition is pinned to the version recorded in `harvest`. A
  harvest on a different day will differ.

## Stub server

```bash
# whole catalog
python benchmarks/mcp_wide/stub_server.py
# only some servers (unknown ids abort with an error)
MCP_WIDE_SERVERS=slack,gmail,google_calendar,stripe python benchmarks/mcp_wide/stub_server.py
```

It uses only the standard library and speaks JSON-RPC 2.0 over newline-delimited
stdin/stdout with protocol version `2025-06-18`. It handles `initialize`,
`notifications/initialized`, `ping`, `tools/list` (single page) and `tools/call`. Every
call returns `isError: true` with the text
`Error: this tool is not available in this environment.`. Other requests get `-32601`.
`MCP_WIDE_CATALOG` points it at a different catalog file.

Smoke test:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"slack_post_message","arguments":{}}}' \
| python benchmarks/mcp_wide/stub_server.py \
| python -c "import sys,json; [print(m['id'], len(m['result']['tools']) if 'tools' in m.get('result',{}) else m['result']) for m in map(json.loads, sys.stdin)]"
# expected: 1 {...initialize...} / 2 1497 / 3 {... isError: True}
```
