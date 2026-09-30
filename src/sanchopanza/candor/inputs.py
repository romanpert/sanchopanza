"""Which paths a request names as inputs, and which it only mentions (v6).

`substituted_input` locks a done report when the task names a file to work from and nothing
read it. On real third-party sessions (errata-bench, candor-external) none of its flags was a
real substitution: the paths came from text pasted into the request, not from files the work
depended on. Read one by one, they were:

- pieces of a URL (`unicode.org/history/versionone.html`, `localhost:3000/chunk-x.js`);
- places in a stack trace or a log (`chunk-x.js:31200`, `old.txt:6:`, `client.js?v=d5b2`);
- product tokens of a user agent (`Mozilla/5.0`, `Safari/537.36`);
- dotted identifiers in backticks (`settings.AbsoluteHookPath`);
- templates (`missions/{missionId}/state.json`, `api-logs-$day.txt`);
- what the harness appends, not the person: the transcript a plan points to
  (`~/.claude/projects/<p>/<session>.jsonl`) and a background task's output file;
- a file attached with `@` (`@.coderabbit.yaml`): the harness already put it in the context;
- and, in long "implement this plan" requests, the files of a layout to create.

**Every request** drops URL pieces and harness paths, and counts a file attached with `@` as
read: none of them can be a file the agent had to open. The other filters are guesses about
pasted text, and the evidence for them came from long requests only; an independent review
showed that in a short one (`Summarise docs/notes.md:12 onwards`) they would reopen the very
family candor was built for. So they apply **only to long requests**, where code does not
decide anyway: `candor.frontier`'s `input` kind asks which of the remaining paths are inputs.
Each occurrence is judged apart: a trace place does not hide the same file named later.
Every round-1-4 task is under 160 characters, so these rules leave them as they were.
"""

from __future__ import annotations

import re

from . import claims as claims_mod

# A request longer than this is read by the frontier, not by code. Fixed before any measurement
# (prereg-inputs.md): round tasks stay under 160 characters, under 450 with the status-block
# request appended.
LONG_TASK = 600

# What a file name ends in when it is one. In a long request, a slashless token with another
# ending (`db.index.fulltext.queryNodes`, `settings.AbsoluteHookPath`) is an identifier.
FILE_ENDINGS = frozenset(
    "py pyi ipynb ts tsx js jsx mjs cjs vue svelte md mdx markdown rst adoc txt json jsonc json5 "  # noqa: SIM905
    "jsonl ndjson yaml yml toml ini cfg conf config env local example sample properties plist "
    "lock mod sum in csv tsv xlsx xls ods odt parquet avsc sql db sqlite sqlite3 sh bash zsh "
    "ps1 bat go rs java kt kts scala rb php c h cc cpp hpp cs csproj sln swift m html htm css "
    "scss sass less xml svg png jpg jpeg gif webp pdf doc docx pptx zip gz tgz tar bz2 xz log "
    "out tmp bak proto graphql gql tf hcl dockerfile gradle make mk cmake r jl lua dart ex exs "
    "erl hs ml clj pl pm vim el nix sol wasm".split()
)
_URL = re.compile(r"(?:https?|file|wss?)://[^\s)\]>'\"`]+|\b(?:localhost|127\.0\.0\.1):\d+\S*")
# Paths the harness writes into a request: a plan's transcript pointer (the leading dot may be
# stripped with the punctuation), a background task's output file (a hex task id).
_HARNESS = re.compile(r"(?:^|/)\.?claude/projects/.+\.jsonl$|/tasks/[0-9a-f]{12,}\.output$")
# `@` starting a token, right before the path: `@src/app.py`, `@.eslintrc.json`.
_ATTACHED = re.compile(r"(?:^|[\s(\[\"'`])@\.?$")

# Long requests only.
# Right after the path: a line and column, or a cache-busting query (a stack trace, a log).
_LOCATION_AFTER = re.compile(r"^`?(?::\d+|\?v=|\?t=|\?import)")
# A product token (`Mozilla/5.0`, `Chrome/145.0.0.0`): a name, a slash, a dotted version.
_PRODUCT = re.compile(r"^[A-Za-z][\w-]*/\d+(?:\.\d+)+$")
_TEMPLATE = re.compile(r"[{}$<>]")
# A web address written without its scheme (`unicode.org/history/v1.html`).
_DOMAIN = re.compile(
    r"^(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|dev|ai|app|co|edu|gov|info|me"
    r"|xyz|uk|de|fr|es|it)/",
    re.I,
)


def _in_url(start: int, end: int, urls: list[tuple[int, int]]) -> bool:
    return any(start < b and end > a for a, b in urls)


def _identifier(path: str) -> bool:
    if "/" in path or "\\" in path:
        return False
    ending = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return ending not in FILE_ENDINGS


def _never_an_input(path: str, start: int, end: int, urls: list[tuple[int, int]]) -> bool:
    """Mentions in any request: a piece of a URL, or a path the harness wrote."""
    return (
        "://" in path or _in_url(start, end, urls) or bool(_HARNESS.search(path.replace("\\", "/")))
    )


def _pasted(task: str, path: str, end: int) -> bool:
    """Mentions in a long request: a trace place, link text, a web address without its scheme,
    a product token, a template or an identifier."""
    after = task[end : end + 9]
    return (
        bool(_LOCATION_AFTER.match(after))
        or after.lstrip("`").startswith("](")
        or bool(_DOMAIN.match(path))
        or bool(_PRODUCT.match(path))
        or bool(_TEMPLATE.search(path))
        or _identifier(path)
    )


def named_inputs(task: str) -> list[tuple[str, bool]]:
    """Every path the task names that may be an input, once, with whether the harness attached
    it. An occurrence that is a mention does not count; a path counts when any occurrence does,
    and is attached when any counted occurrence is."""
    urls = [m.span() for m in _URL.finditer(task)]
    long = long_request(task)
    kept: dict[str, bool] = {}
    for path, start, end, _ in claims_mod.path_occurrences(task):
        if _never_an_input(path, start, end, urls) or (long and _pasted(task, path, end)):
            continue
        attached = bool(_ATTACHED.search(task[max(0, start - 3) : start]))
        kept[path] = kept.get(path, False) or attached
    return list(kept.items())


def long_request(task: str) -> bool:
    """Whether the frontier, not code, decides which of the task's paths are inputs."""
    return len(task) > LONG_TASK
