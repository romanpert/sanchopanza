"""Long chains: many bugs of one repository asked in one session, long enough to reach the context
where a budget or memory can act. Free and seeded; validation runs in Docker (`validate.py`).

    python benchmarks/adopt/long.py              # writes long-selected.json (long40, as drawn)
    python benchmarks/adopt/long.py long60       # writes long60-selected.json (and reserve)
    python benchmarks/adopt/long.py manifests    # after validate.py: long60/<chain>.json
    python benchmarks/adopt/long.py extra60 <chain>  # a chain validated short: extra spares
    <swe-venv python> benchmarks/adopt/long.py --extract-synthetic   # once, needs pyarrow

Why: in phase B, Sonnet 5.5 took about 5k tokens of context per SWE-smith bug and ended ten bugs
at 80k, below the default 160k budget, so nothing acted (dev log, "Phase B"). A session of 40
bugs should pass 200k. The bugs are drawn like the related chains (`related.py`): SWE-smith
`pr_mirror` rows of one repository, patches normalised, no two with overlapping hunks or a
FAIL_TO_PASS test in common, none in any chain or spare of `chains.py` or `related.py`; files may
be shared. Up to SPARES more are drawn the same way, to replace bugs that fail validation.

long60 (2026-10-05, the long-session prereg draft): B2's 40 bugs peaked at 263k on Sonnet, short
of the real median (370k). A long60 chain has `size` bugs (60 by default) drawn the same way,
after every long40 chain and with its own seed, so nothing drawn before changes:

- real `pr_mirror` bugs first; when a repository runs short, SWE-smith's synthetic bugs of the
  same repository (`lm_rewrite`, `func_pm_*`, `func_basic`; not `combine_*`, which are several
  of those at once) fill the rest. Each bug records its `source` (`pr_mirror` or the synthetic
  kind) and `origin` (`real` or `synthetic`);
- the chain's bugs are put in a seeded random order, so synthetic bugs are not all at the end;
- each chain carries a control fact: a token given only in the first prompt, which every
  `changes/<n>.md` must carry, and two callback prompts late in the session that ask which
  files were changed for early bugs (`requests`); `perbug.py` grades both;
- validation (`validate.isolate`) drops bugs that interact, and the grade is per bug
  (`perbug.py`): a bug is resolved when its own FAIL_TO_PASS pass; regressions are a separate
  guard, not a condition of every bug (B2's strict rule turned one regression into 0/40).

Split `reserve` chains are drawn and written down, never validated until promoted.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

import chains
import related

HERE = Path(__file__).resolve().parent
SEED = 20261003
SIZE = 40
SPARES = 12
# (repo, name, split): development only for now; the owner decides on a held-out one. A later
# chain never changes an earlier one (the generator runs them in this order) and takes none of
# their bugs or spares. conan-long40-1 is the new Sonnet 5.5 chain of memory amendment 6, part
# A (pydantic-long40-1 was spent in B2, and pydantic has 26 compatible bugs left): of the five
# repositories with 40 bugs and 12 spares left, the one whose base image is already local.
PLAN = (
    ("swesmith/pydantic__pydantic.acb0f10f", "pydantic__pydantic-long40-1", "dev"),
    ("swesmith/conan-io__conan.86f29e13", "conan-io__conan-long40-1", "dev"),
)

# ---- long60 --------------------------------------------------------------------------------------

SEED60 = 20261005
SIZE60 = 60
SPARES60 = 30  # validation drops interacting bugs and refills from these, in drawn order
SYNTH_SOURCE = chains.SOURCE.parent / "swesmith_synth.jsonl"
HF_DATASET, HF_REVISION = "SWE-bench/SWE-smith", "ea6d7173829c7ec8fa16c22055699ff2e9188091"
EXCLUDED_KINDS = ("combine_file", "combine_module")
_PR = re.compile(r"pr_\d+$")
CONAN, PYDANTIC = "swesmith/conan-io__conan.86f29e13", "swesmith/pydantic__pydantic.acb0f10f"
DVC, MOTO = "swesmith/iterative__dvc.1d6ea681", "swesmith/getmoto__moto.694ce1f4"
STARLETTE, DSPY = "swesmith/encode__starlette.db5063c2", "swesmith/stanfordnlp__dspy.651a4c71"
ASTROID, DASK = "swesmith/pylint-dev__astroid.b114f6b5", "swesmith/dask__dask.5f61e423"
PYGMENTS = "swesmith/pygments__pygments.27649ebb"
# (repo, name, split). Built and validated: two for the headroom gate, four for development.
# Gate rows are the N rows of the same chains in the development run (prereg draft, section 5).
PLAN60 = (
    (CONAN, "conan-io__conan-long60-1", "gate"),
    (PYDANTIC, "pydantic__pydantic-long60-1", "gate"),
    (CONAN, "conan-io__conan-long60-2", "dev"),
    (DVC, "iterative__dvc-long60-1", "dev"),
    (MOTO, "getmoto__moto-long60-1", "dev"),
    (CONAN, "conan-io__conan-long60-3", "dev"),
)
# Drawn after PLAN60 and written down, not built: candidates for held-out confirmation chains.
RESERVE60 = (
    (CONAN, "conan-io__conan-long60-4", "reserve"),
    (CONAN, "conan-io__conan-long60-5", "reserve"),
    (CONAN, "conan-io__conan-long60-6", "reserve"),
    (MOTO, "getmoto__moto-long60-2", "reserve"),
    (MOTO, "getmoto__moto-long60-3", "reserve"),
    (MOTO, "getmoto__moto-long60-4", "reserve"),
    (DASK, "dask__dask-long60-1", "reserve"),
    (ASTROID, "pylint-dev__astroid-long60-1", "reserve"),
    (ASTROID, "pylint-dev__astroid-long60-2", "reserve"),
    (PYGMENTS, "pygments__pygments-long60-1", "reserve"),
    (PYGMENTS, "pygments__pygments-long60-2", "reserve"),
    (STARLETTE, "encode__starlette-long60-1", "reserve"),
)
SYNTH_REPOS = tuple(dict.fromkeys(repo for repo, _, _ in (*PLAN60, *RESERVE60)))
# Callbacks: after the request of bug `after`, ask for the files changed for `asked` (fractions
# of the chain size, so a chain of another size keeps the same shape: 60 -> after 45 and 60).
CALLBACKS = ((0.75, (0.05, 0.12, 0.20)), (1.0, (0.08, 0.15, 0.25)))


def fits(row: dict[str, Any], taken: list[dict[str, Any]]) -> bool:
    mine, tests = related.spans(row["patch"]), set(row["FAIL_TO_PASS"])
    return not any(tests & set(b["FAIL_TO_PASS"])
                   or related.overlaps(mine, related.spans(b["patch"])) for b in taken)  # fmt: skip


def draw(
    rows: list[dict[str, Any]], size: int, spares: int, rng: random.Random
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pool = [n for r in rows if chains.usable(r) and related.code_files(n := related.normalized(r))]
    rng.shuffle(pool)
    picked: list[dict[str, Any]] = []
    for row in pool:
        if len(picked) == size + spares:
            break
        if fits(row, picked):
            picked.append(row)
    return picked[:size], picked[size:]


def select(plan: tuple[tuple[str, str, str], ...] = PLAN) -> list[dict[str, Any]]:
    by_repo = chains.load()
    sealed = {b["instance_id"] for c in [*chains.full(), *related.full()]
              for b in [*c["bugs"], *c["spares"]]}  # fmt: skip
    rng = random.Random(SEED)
    out = []
    for repo, name, split in plan:
        rows = [r for r in by_repo[repo] if r["instance_id"] not in sealed]
        bugs, spares = draw(rows, SIZE, SPARES, rng)
        if len(bugs) < SIZE:
            raise SystemExit(f"{repo}: only {len(bugs)} compatible bugs of {SIZE}")
        sealed = sealed | {b["instance_id"] for b in [*bugs, *spares]}
        out.append({"chain": name, "repo": repo, "image": bugs[0]["image_name"], "split": split,
                    "kind": "long", "bugs": bugs, "spares": spares})  # fmt: skip
    return out


def full() -> list[dict[str, Any]]:
    path = chains.CACHE / "long-selected-full.json"
    if not path.exists():
        path.write_text(json.dumps(select(), ensure_ascii=False), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


# ---- long60: sources and draw --------------------------------------------------------------------


def source_of(instance_id: str) -> str:
    """`pr_mirror`, or SWE-smith's synthetic kind (`lm_rewrite`, `func_pm_remove_cond`, ...)."""
    tail = instance_id.rsplit(".", 1)[1]
    return "pr_mirror" if _PR.match(tail) else tail.split("__")[0]


def extract_synthetic(snapshot: Path, repos: tuple[str, ...] = SYNTH_REPOS) -> int:
    """SWE-smith's synthetic rows of `repos` from the Hugging Face parquet (revision HF_REVISION)
    into SYNTH_SOURCE, one JSON row per line, in the dataset's order. Needs pyarrow (the swe-venv
    has it; the project venv does not). Rows of the excluded kinds and pr_mirror rows stay out:
    pr_mirror bugs come from `chains.SOURCE`, as before."""
    import pyarrow.parquet as pq  # only here: the benchmark itself never needs it

    wanted, kept = set(repos), 0
    with SYNTH_SOURCE.open("w", encoding="utf-8", newline="\n") as out:
        for part in sorted((snapshot / "data").glob("train-*.parquet")):
            for batch in pq.ParquetFile(part).iter_batches(batch_size=2000):
                for row in batch.to_pylist():
                    kind = source_of(row["instance_id"])
                    if row["repo"] in wanted and kind != "pr_mirror" and kind not in EXCLUDED_KINDS:
                        out.write(json.dumps(row, ensure_ascii=False) + "\n")
                        kept += 1
    return kept


def load_synthetic() -> dict[str, list[dict[str, Any]]]:
    by_repo: dict[str, list[dict[str, Any]]] = {}
    for line in SYNTH_SOURCE.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        row["FAIL_TO_PASS"] = chains.listed(row["FAIL_TO_PASS"])
        row["PASS_TO_PASS"] = chains.listed(row["PASS_TO_PASS"])
        by_repo.setdefault(row["repo"], []).append(row)
    return by_repo


def tagged(row: dict[str, Any]) -> dict[str, Any]:
    kind = source_of(row["instance_id"])
    return {**row, "source": kind, "origin": "real" if kind == "pr_mirror" else "synthetic"}


def pool60(rows: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    """The rows a long60 draw may take, normalised and tagged, in `rng`'s shuffled order."""
    out = [tagged(n) for r in rows
           if chains.usable(r) and related.code_files(n := related.normalized(r))]  # fmt: skip
    rng.shuffle(out)
    return out


def draw_mixed(
    real: list[dict[str, Any]], synthetic: list[dict[str, Any]], size: int, spares: int,
    rng: random.Random,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:  # fmt: skip
    """`size` bugs and up to `spares` spares, real ones first and synthetic ones once the real
    ones that fit run out; the bugs then in a seeded random order (sources mixed through the
    session), the spares in drawn order."""

    picked: list[dict[str, Any]] = []
    for row in [*pool60(real, rng), *pool60(synthetic, rng)]:
        if len(picked) == size + spares:
            break
        if fits(row, picked):
            picked.append(row)
    bugs = picked[:size]
    rng.shuffle(bugs)
    return bugs, picked[size:]


def used_before() -> set[str]:
    """Every bug and spare of the chains drawn before long60, the extra spares included."""
    extra = json.loads((HERE / "extra-spares.json").read_text(encoding="utf-8"))["chains"]
    drawn = [*chains.full(), *related.full(), *full()]
    return {b["instance_id"] for c in drawn for b in [*c["bugs"], *c["spares"]]} | {
        i for ids in extra.values() for i in ids
    }


def token_for(name: str, avoid: tuple[str, ...] = (), index: int = 0) -> str:
    """The chain's control token: 8 hex characters from the seed and the chain's name, the
    `index`-th one that appears in none of `avoid` (issues, patches, test names)."""
    found = -1
    for k in range(10_000):
        token = hashlib.sha256(f"{SEED60}:{name}:{k}".encode()).hexdigest()[:8]
        if not any(token in text for text in avoid):
            found += 1
            if found == index:
                return token
    raise RuntimeError(f"{name}: no token absent from the chain's texts")


def texts_of(bugs: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(t for b in bugs for t in (b["problem_statement"], b["patch"],
                                           *b["FAIL_TO_PASS"]))  # fmt: skip


def select60(
    plan: tuple[tuple[str, str, str], ...] = PLAN60 + RESERVE60, size: int = SIZE60,
    spares: int = SPARES60,
) -> list[dict[str, Any]]:  # fmt: skip
    """long60 chains in plan order: a later chain never changes an earlier one."""
    return _select60(plan, size, spares)[0]


def _select60(
    plan: tuple[tuple[str, str, str], ...], size: int, spares: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """`select60`, and where the draw stopped: the rows by repository, what it took and its
    random generator, so a later draw (`extra60`) continues it."""
    by_repo, synthetic = chains.load(), load_synthetic()
    taken = used_before()
    rng = random.Random(SEED60)
    out = []
    for repo, name, split in plan:
        real = [r for r in by_repo.get(repo, []) if r["instance_id"] not in taken]
        synth = [r for r in synthetic.get(repo, []) if r["instance_id"] not in taken]
        bugs, extra = draw_mixed(real, synth, size, spares, rng)
        if len(bugs) < size:
            raise SystemExit(f"{repo}: only {len(bugs)} compatible bugs of {size}")
        taken = taken | {b["instance_id"] for b in [*bugs, *extra]}
        out.append({"chain": name, "repo": repo, "image": bugs[0]["image_name"], "split": split,
                    "kind": "long", "grader": "per_bug", "size": size, "seed": SEED60,
                    "token": token_for(name, texts_of([*bugs, *extra])),
                    "bugs": bugs, "spares": extra})  # fmt: skip
    return out, {"real": by_repo, "synthetic": synthetic, "taken": taken, "rng": rng}


FULL60 = chains.CACHE / "long60-selected-full.json"


def full60() -> list[dict[str, Any]]:
    """The long60 selection (built chains and reserve) with every row in full, kept in the cache."""
    if not FULL60.exists():
        FULL60.write_text(json.dumps(select60(), ensure_ascii=False), encoding="utf-8")
    return json.loads(FULL60.read_text(encoding="utf-8"))


# ---- long60: extra spares for a validated chain short of its size --------------------------------
#
# conan-long60-1 (2026-10-06): its real PR bugs masked each other, validation dropped 34 of 90 and
# settled at 56 clean bugs with every spare used. The owner chose more spares over a size of 56.
# Nothing drawn before changes: `extra60` replays the long60 draw (built and reserve chains, in
# plan order, seed SEED60), checks it gives exactly the ids of long60-selected.json, and goes on
# with the same random generator over the repository's rows no chain or spare took (reserves
# untouched): real rows first, then synthetic ones, each fitting the validated bugs and the extra
# spares before it (`fits`). Validation then starts from the validated bugs in their order, tops
# them up to `size` from these spares in drawn order (`perbug.top_up`), and checks the whole chain.

EXTRA60 = HERE / "long60-extra-spares.json"
EXTRA60_FULL = chains.CACHE / "long60-extra-spares-full.json"
EXTRA60_COUNT = 30


def _ids(rows: list[dict[str, Any]]) -> list[str]:
    return [r["instance_id"] for r in rows]


def continue60(
    name: str, start: list[str], count: int, drawn: list[dict[str, Any]], state: dict[str, Any],
    sealed: list[dict[str, Any]],
) -> list[dict[str, Any]]:  # fmt: skip
    """`count` extra spares for chain `name` that fit its validated bugs `start` (ids), continuing
    the draw `drawn`/`state` (`_select60`) after checking it against the sealed compact chains."""
    replay = [(c["chain"], _ids(c["bugs"]), _ids(c["spares"])) for c in drawn]
    if replay != [(c["chain"], c["bugs"], c["spares"]) for c in sealed]:
        raise SystemExit("the long60 replay does not give long60-selected.json")
    chain = next(c for c in drawn if c["chain"] == name)
    rows = {b["instance_id"]: b for b in [*chain["bugs"], *chain["spares"]]}
    missing = [i for i in start if i not in rows]
    if missing:
        raise SystemExit(f"{name}: validated bugs not of its draw: {missing[:3]}")
    kept = [rows[i] for i in start]
    taken, rng = state["taken"], state["rng"]
    real = [r for r in state["real"].get(chain["repo"], []) if r["instance_id"] not in taken]
    synth = [r for r in state["synthetic"].get(chain["repo"], []) if r["instance_id"] not in taken]
    picked: list[dict[str, Any]] = []
    for row in [*pool60(real, rng), *pool60(synth, rng)]:
        if len(picked) == count:
            break
        if fits(row, [*kept, *picked]):
            picked.append(row)
    return picked


def extra60(name: str, start: list[str], count: int = EXTRA60_COUNT) -> list[dict[str, Any]]:
    """The extra spares of `name` (see above), drawn again from the sources."""
    drawn, state = _select60(PLAN60 + RESERVE60, SIZE60, SPARES60)
    sealed = json.loads((HERE / "long60-selected.json").read_text(encoding="utf-8"))["chains"]
    return continue60(name, start, count, drawn, state, sealed)


def extra60_spares(name: str) -> list[dict[str, Any]]:
    """`name`'s extra spares in full, from the cache or drawn again and checked against the ids
    EXTRA60 recorded; [] for a chain it does not name."""
    record = json.loads(EXTRA60.read_text(encoding="utf-8"))["chains"] if EXTRA60.exists() else {}
    if name not in record:
        return []
    full = json.loads(EXTRA60_FULL.read_text(encoding="utf-8")) if EXTRA60_FULL.exists() else {}
    rows = full.get(name) or extra60(name, record[name]["start"], len(record[name]["spares"]))
    if _ids(rows) != record[name]["spares"]:
        raise SystemExit(f"{name}: extra spares differ from {EXTRA60.name}")
    return rows


def resumed(chain: dict[str, Any]) -> dict[str, Any]:
    """`chain` as validation takes it: unchanged, or, when EXTRA60 names it, its validated bugs
    (in their order) as the start, its extra spares, and the earlier validation as `before`."""
    record = json.loads(EXTRA60.read_text(encoding="utf-8"))["chains"] if EXTRA60.exists() else {}
    if chain["chain"] not in record:
        return chain
    entry = record[chain["chain"]]
    rows = {b["instance_id"]: b for b in [*chain["bugs"], *chain["spares"]]}
    return {**chain, "bugs": [rows[i] for i in entry["start"]],
            "spares": extra60_spares(chain["chain"]), "before": entry["before"],
            "extra_draw": {k: entry[k] for k in ("seed", "how", "spares")}}  # fmt: skip


def record_extra60(name: str, previous: dict[str, Any], count: int = EXTRA60_COUNT) -> list[str]:
    """Draws `name`'s extra spares from its validated result `previous` (validate.validated()),
    writes their ids into EXTRA60 and the rows into the cache. Returns the ids."""
    if previous.get("valid") or len(previous["bugs"]) >= previous.get("size", SIZE60):
        raise SystemExit(f"{name}: valid or at its size, no extra spares needed")
    start = _ids(previous["bugs"])
    rows = extra60(name, start, count)
    record = json.loads(EXTRA60.read_text(encoding="utf-8")) if EXTRA60.exists() else {
        "seed": SEED60, "count": count, "chains": {}}  # fmt: skip
    before = {"rounds": len(previous["history"]), "history": previous["history"],
              "dropped": previous["dropped"], "seconds": previous["seconds"],
              "bugs": len(start)}  # fmt: skip
    how = ("replay of select60 over PLAN60 + RESERVE60 (seed SEED60), checked against "
           "long60-selected.json, continued with the same random generator over the repository's "
           "rows no long60 chain or spare took: real first, then synthetic, each fitting the "
           "start bugs and the spares before it")  # fmt: skip
    record["chains"][name] = {"seed": SEED60, "how": how, "start": start, "spares": _ids(rows),
                              "before": before}  # fmt: skip
    EXTRA60.write_text(json.dumps(record, indent=1), encoding="utf-8", newline="\n")
    full = json.loads(EXTRA60_FULL.read_text(encoding="utf-8")) if EXTRA60_FULL.exists() else {}
    EXTRA60_FULL.write_text(json.dumps({**full, name: rows}, ensure_ascii=False), encoding="utf-8")
    return _ids(rows)


# ---- long60: the prompts -------------------------------------------------------------------------

RULE = (
    "Before the first bug, one rule for this whole session. For every bug I report, add a file "
    "`changes/<n>.md` at the repository root, where <n> is the bug's number as I give it. Its "
    "first line must be exactly `Ref: {token}`; after that line, one or two sentences on what was "
    "wrong. I will not repeat this rule."
)
BUG_HEAD = "Bug {n} of this session.\n\n{issue}"
CALLBACK = (
    "No new bug in this message. Write the file `changes/recall-{k}.md` with one line for each of "
    "bugs {asked} of this session, in the form `bug <n>: <path>, <path>`, listing every "
    "repository file you changed while fixing that bug (paths from the repository root; leave "
    "out files under `changes/`; write `bug <n>: none` if you changed none). Answer from what you "
    "remember of this session: do not use git and do not open files to work it out. Change "
    "nothing else."
)


def callbacks(size: int) -> list[tuple[int, list[int]]]:
    """(after bug, bugs asked) for a chain of `size` bugs.

    60 bugs: after bug 45, bugs 3, 7 and 12; after bug 60, bugs 5, 9 and 15."""
    return [(max(1, round(after * size)), sorted({max(1, round(f * size)) for f in asked}))
            for after, asked in CALLBACKS]  # fmt: skip


def requests(chain: dict[str, Any], template: str) -> list[dict[str, Any]]:
    """The session's prompts in order. `template` is the runner's bug prompt (`run.PROMPT`, with
    `{issue}`). Bug n's prompt names its number; the first one alone carries the rule and its
    token; callbacks follow bugs at the positions `callbacks` gives."""
    after = dict(callbacks(len(chain["bugs"])))
    out: list[dict[str, Any]] = []
    for n, bug in enumerate(chain["bugs"], start=1):
        text = template.format(issue=BUG_HEAD.format(n=n, issue=bug["problem_statement"].strip()))
        if n == 1:
            text = RULE.format(token=chain["token"]) + "\n\n" + text
        out.append({"kind": "bug", "bug": n, "instance_id": bug["instance_id"], "prompt": text})
        if n in after:
            k = sum(1 for r in out if r["kind"] == "callback") + 1
            asked = after[n]
            words = " and ".join([", ".join(str(a) for a in asked[:-1]), str(asked[-1])][-2:]
                                 if len(asked) > 1 else [str(asked[0])])
            out.append({"kind": "callback", "callback": k, "asked": asked,
                        "instance_id": f"callback-{k}",
                        "prompt": CALLBACK.format(k=k, asked=words)})  # fmt: skip
    return out


def manifest(chain: dict[str, Any], template: str) -> dict[str, Any]:
    """What a long60 chain is, for the record: bugs with their sources and tests, the token, the
    prompts (each hashed; the rule and callbacks in full), the seed and the guard."""
    asks = requests(chain, template)
    guard = chain.get("guard", [])
    return {"chain": chain["chain"], "repo": chain["repo"], "image": chain["image"],
            "tag": chain.get("tag"), "split": chain["split"], "seed": chain["seed"],
            "token": chain["token"], "size": len(chain["bugs"]),
            "sources": {k: sum(1 for b in chain["bugs"] if b["source"] == k)
                        for k in sorted({b["source"] for b in chain["bugs"]})},
            "real": sum(1 for b in chain["bugs"] if b["origin"] == "real"),
            "synthetic_dataset": f"{HF_DATASET}@{HF_REVISION}",
            "pr_mirror_sha256": chains.source_digest(),
            "bugs": [{"n": n, "instance_id": b["instance_id"], "source": b["source"],
                      "origin": b["origin"], "files": sorted(related.code_files(b)),
                      "FAIL_TO_PASS": b["FAIL_TO_PASS"]}
                     for n, b in enumerate(chain["bugs"], start=1)],
            "guard": {"tests": len(guard),
                      "sha256": hashlib.sha256("\n".join(guard).encode()).hexdigest()},
            **({"extra_draw": chain["extra_draw"],
                "before": {k: chain["before"][k] for k in ("rounds", "bugs", "seconds")}}
               if "extra_draw" in chain else {}),
            "callbacks": [{"after_bug": a, "asked": q} for a, q in callbacks(len(chain["bugs"]))],
            "rule": RULE.format(token=chain["token"]),
            "requests": [{"kind": r["kind"], "instance_id": r["instance_id"],
                          "chars": len(r["prompt"]),
                          "sha256": hashlib.sha256(r["prompt"].encode()).hexdigest(),
                          **({"prompt": r["prompt"]} if r["kind"] == "callback" else {})}
                         for r in asks]}  # fmt: skip


MANIFESTS = HERE / "long60"


def write_manifests() -> list[str]:
    """One manifest per validated long60 chain into MANIFESTS (`long60/<chain>.json`)."""
    import run  # both import this module
    import validate

    MANIFESTS.mkdir(exist_ok=True)
    out = []
    for name, chain in validate.validated().items():
        if chain.get("grader") != "per_bug":
            continue
        body = {**manifest(chain, run.PROMPT), "valid": chain["valid"],
                "validation_seconds": chain["seconds"], "rounds": len(chain["history"]),
                "dropped": chain["dropped"], "p2p": chain["p2p"],
                "sha256": run.chain_digest(chain)}  # fmt: skip
        (MANIFESTS / f"{name}.json").write_text(json.dumps(body, indent=1), encoding="utf-8",
                                                newline="\n")  # fmt: skip
        out.append(name)
    return out


def main(argv: list[str]) -> int:
    if argv[:1] == ["manifests"]:
        print("manifests:", write_manifests())
        return 0
    if argv[:1] == ["extra60"]:  # long.py extra60 <chain>: after a validation short of its size
        import validate

        ids = record_extra60(argv[1], validate.validated()[argv[1]])
        print(argv[1], len(ids), "extra spares:", [i.rsplit(".", 1)[1] for i in ids])
        return 0
    if argv[:1] == ["--extract-synthetic"]:
        print(extract_synthetic(Path(argv[1])), "synthetic rows into", SYNTH_SOURCE)
        return 0
    if argv[:1] == ["long60"]:
        selected = select60()
        FULL60.write_text(json.dumps(selected, ensure_ascii=False), encoding="utf-8")
        compact = {"source": "SWE-bench/SWE-smith: pr_mirror rows, then synthetic rows",
                   "source_sha256": chains.source_digest(),
                   "synthetic": f"{HF_DATASET}@{HF_REVISION}",
                   "synthetic_sha256": hashlib.sha256(SYNTH_SOURCE.read_bytes()).hexdigest(),
                   "seed": SEED60, "kind": "long", "grader": "per_bug",
                   "chains": [{"chain": c["chain"], "repo": c["repo"], "image": c["image"],
                               "split": c["split"],
                               "bugs": [b["instance_id"] for b in c["bugs"]],
                               "spares": [b["instance_id"] for b in c["spares"]]}
                              for c in selected]}  # fmt: skip
        (HERE / "long60-selected.json").write_text(json.dumps(compact, indent=1),
                                                   encoding="utf-8", newline="\n")  # fmt: skip
        for c in selected:
            real = sum(1 for b in c["bugs"] if b["origin"] == "real")
            spare_real = sum(1 for b in c["spares"] if b["origin"] == "real")
            print(c["split"], c["chain"], f"{real} real + {len(c['bugs']) - real} synthetic,",
                  f"{len(c['spares'])} spares ({spare_real} real)")  # fmt: skip
        return 0
    selected = select()
    (chains.CACHE / "long-selected-full.json").write_text(json.dumps(selected, ensure_ascii=False),
                                                           encoding="utf-8")  # fmt: skip
    compact = {"source": "SWE-bench/SWE-smith, pr_mirror rows", "source_sha256":
               chains.source_digest(), "seed": SEED, "kind": "long",
               "chains": [{"chain": c["chain"], "repo": c["repo"], "image": c["image"],
                           "split": c["split"], "bugs": [b["instance_id"] for b in c["bugs"]],
                           "spares": [b["instance_id"] for b in c["spares"]]}
                          for c in selected]}  # fmt: skip
    (HERE / "long-selected.json").write_text(json.dumps(compact, indent=1), encoding="utf-8",
                                             newline="\n")  # fmt: skip
    for c in selected:
        files = {f for b in c["bugs"] for f in related.code_files(b)}
        print(c["chain"], len(c["bugs"]), "bugs,", len(c["spares"]), "spares,", len(files), "files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
