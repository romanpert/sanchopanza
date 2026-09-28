"""`sanchopanza` command line.

sanchopanza bench benches/*.jsonl --provider recorded --fixture fixtures/public-benches.jsonl
sanchopanza bench benches/*.jsonl --provider jev --record fixtures/new.jsonl --out results/today
sanchopanza hook            # Claude Code hook: JSON in, JSON out
sanchopanza install         # print the settings block; --write to apply it
sanchopanza install --scan-content --write   # and scan arriving content for injections
sanchopanza install --check-done --write     # and check "done" before a stop
sanchopanza install --compact --write        # and prune tool results at /compact
sanchopanza install --autopilot --write      # cut on arrival, recall, mask at a percentage
sanchopanza compact --transcript session.jsonl --provider null   # plan and apply a pruning
sanchopanza providers       # what is installed
sanchopanza dag plan.json   # clean DAG and waves from {"nodes": [...], "edges": {"A->B": 0.9}}
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

# Each subcommand imports what it needs: `sanchopanza hook` runs once per tool call, and the
# bench machinery, asyncio and the provider scan are no part of an event that needs no decision.


def _bench(args: argparse.Namespace) -> int:
    import asyncio

    from .eval.bench import load_cases, render_markdown, rows_to_json, run_bench, summarize
    from .providers import create
    from .providers.recorded import RecordingDecider

    cases = load_cases(args.cases)
    if args.provider == "recorded":
        decider = create("recorded", path=args.fixture)
    elif args.provider == "jev":
        decider = create("jev", api_key=os.environ.get("TYPESAFE_API_KEY"))
    else:
        decider = create(args.provider)
    if args.record:
        decider = RecordingDecider(decider, args.record)
    results = asyncio.run(run_bench(cases, decider, concurrency=args.concurrency))
    summary = summarize(results)
    text = render_markdown(summary, title=args.title)
    sys.stdout.write(text)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "results.json").write_text(
            json.dumps(rows_to_json(results), ensure_ascii=False, indent=1), encoding="utf-8"
        )
        (out / "summary.md").write_text(text, encoding="utf-8")
        (out / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
        )
    return 0


def _hook(_args: argparse.Namespace) -> int:
    from .harness.claude_code import main as hook_main

    return hook_main()


def _providers(_args: argparse.Namespace) -> int:
    from .providers import available

    for name, target in sorted(available().items()):
        sys.stdout.write(f"{name:10} {target}\n")
    return 0


def _install_plugin(args: argparse.Namespace, root: Path | None) -> list[str]:
    """The compaction plugin's files to (re)write, written under `--write`."""
    from .harness.install import plugin_changes, write_plugin

    if root is None:
        return []
    return write_plugin(root) if args.write else plugin_changes(root)


def _install(args: argparse.Namespace) -> int:
    from .harness.generic import HarnessConfig
    from .harness.install import apply, default_path, default_plugin_root, plan

    defaults = HarnessConfig()
    config = HarnessConfig(
        scan_content=args.scan_content,
        check_done=args.check_done,
        scan_shell_fetches=not args.no_shell_fetches,
        content_tools=(
            frozenset(t.strip() for t in args.content_tools.split(",") if t.strip())
            if args.content_tools
            else defaults.content_tools
        ),
    )
    path = Path(args.path) if args.path else default_path(args.scope)
    root = None
    if args.compact or args.autopilot:
        root = Path(args.plugin_dir) if args.plugin_dir else default_plugin_root()
    try:
        settings = plan(
            path,
            config,
            command=args.command_line,
            provider=args.provider or "",
            compact_root=root.resolve() if root else None,
            autopilot=args.autopilot,
        )
        files = _install_plugin(args, root)
    except (ValueError, OSError) as error:
        sys.stderr.write(f"{error}\n")
        return 2
    for name in files:
        verb = "written" if args.write else "to write"
        sys.stdout.write(f"plugin file {verb}: {root / name}\n")
    if not settings.changed:
        sys.stdout.write(f"{path}: already wired, nothing to do\n")
        return 0
    for line in settings.removed:
        sys.stdout.write(f"- {line}\n")
    for line in settings.added:
        sys.stdout.write(f"+ {line}\n")
    if not args.write:
        sys.stdout.write(
            "\n" + json.dumps(settings.merged, ensure_ascii=False, indent=2) + "\n\n"
            f"Nothing written. Re-run with --write to apply to {path}.\n"
        )
        return 0
    try:
        backup = apply(settings)
    except OSError as error:
        sys.stderr.write(f"could not write {path} ({error}); the file was left as it was\n")
        return 2
    kept = f" (previous contents in {backup.name})" if backup else ""
    sys.stdout.write(f"\nwritten to {path}{kept}\n")
    if config.scan_content:
        sys.stdout.write(
            "Content scanning is on. It is detection, not prevention: by PostToolUse the "
            "text is already in the model's context and no hook can take it back.\n"
        )
    if args.autopilot:
        sys.stdout.write(
            "Autopilot is on: long tool results are cut on arrival to what the task needs "
            "(full text in .sanchopanza/archive), archived output and memories are recalled "
            "when relevant, and the context is masked into the archive at "
            "SANCHOPANZA_COMPACT_AT_PERCENT. Hooks fail open; the per-session ceiling is "
            "SANCHOPANZA_SESSION_MAX_USD (default 0.50).\n"
        )
    if root is not None:
        sys.stdout.write(
            "Compaction by pruning is wired. Function hooks are early access and may change "
            "between Claude Code releases; if the plugin does not load, run "
            f"`claude --plugin-dir {root}` once to check it.\n"
        )
    return 0


COMPACT_BELOW_MINIMUM = 3


def _compact_decider(args: argparse.Namespace) -> Any:
    from .harness.claude_code import decider_from_env
    from .providers import create

    if not args.provider:
        return decider_from_env()
    if args.provider == "recorded":
        return create("recorded", path=args.fixture)
    if args.provider == "jev":
        return create("jev", api_key=os.environ.get("TYPESAFE_API_KEY"))
    return create(args.provider)


def _compact_input(args: argparse.Namespace) -> tuple[list[dict[str, Any]], str]:
    """The messages and a session name for the archive directory."""
    import hashlib

    from .context.transcript import messages_from_claude_code

    if args.transcript:
        path = Path(args.transcript)
        return messages_from_claude_code(path), args.session or path.stem
    raw = sys.stdin.buffer.read().decode("utf-8")
    data = json.loads(raw)
    messages = data.get("messages") if isinstance(data, dict) else data
    if not isinstance(messages, list) or not all(isinstance(m, dict) for m in messages):
        raise ValueError('stdin must hold a JSON list of messages, or {"messages": [...]}')
    session = args.session or (data.get("session") if isinstance(data, dict) else None)
    if not session:
        session = hashlib.blake2b(raw.encode("utf-8"), digest_size=6).hexdigest()
    # As given: a caller maps the output back by position and by any key it added.
    return [dict(m) for m in messages], str(session)


def _compact(args: argparse.Namespace) -> int:
    import asyncio

    from . import _env
    from .context import compact
    from .journal import JsonlJournal
    from .policy import Thresholds
    from .redact import redact_secrets
    from .squire import Squire

    try:
        messages, session = _compact_input(args)
        journal_path = Path(_env.get("JOURNAL") or _env.home_dir() / "journal.jsonl")
        thresholds = Thresholds.from_mapping(
            {k.lower(): v for k, v in _env.with_prefix("T_").items()}
        )
        squire = Squire(
            _compact_decider(args),
            thresholds=thresholds,
            journal=JsonlJournal(journal_path),
            redact=redact_secrets,
        )
        from .context.archive import root_for

        archive = root_for(Path.cwd(), override=args.archive or _env.get("ARCHIVE"))
        archive = archive / compact.safe_name(session)
        # Pruned results go to a staging folder first: nothing is kept on disk unless the
        # compaction is actually used.
        staging = archive.with_name(archive.name + ".staging")
        _keep_out_of_git(staging)
        plan = asyncio.run(
            compact.plan(
                squire,
                messages,
                arm=args.arm,
                keep_recent=args.keep_recent,
                small=args.small,
                mask_turns=args.mask_turns,
            )
        )
        pruned = compact.apply(messages, plan, staging)
    except Exception as error:  # the caller falls back to its own summary; say why
        _discard(locals().get("staging"))
        sys.stderr.write(f"sanchopanza compact failed: {error.__class__.__name__}: {error}\n")
        return 2
    summary = {**compact.report(messages, pruned, plan), "archive": str(archive)}
    if summary["reduction"] < args.min_reduction:
        _discard(staging)
        # Same shape as a used compaction: the bare report with --out, wrapped without it.
        sys.stdout.write(json.dumps(summary if args.out else {"report": summary}) + "\n")
        sys.stderr.write(
            f"sanchopanza compact: freed {summary['reduction']:.0%} of the conversation, below "
            f"the {args.min_reduction:.0%} minimum ({summary['failed_decisions']} of "
            f"{summary['decisions']} decisions failed); use the normal summary instead.\n"
        )
        return COMPACT_BELOW_MINIMUM
    try:
        _promote(staging, archive)
        pruned = _repoint(pruned, staging, archive)
    except OSError as error:
        _discard(staging)
        sys.stderr.write(f"sanchopanza compact: could not keep the archive ({error})\n")
        return 2
    _after_compaction(args, squire, messages, plan, archive, session)
    output = json.dumps({"messages": pruned, "report": summary})
    if args.out:
        try:
            out = Path(args.out)
            _keep_out_of_git(out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(output, encoding="utf-8")
        except OSError as error:
            sys.stderr.write(f"sanchopanza compact: could not write {args.out} ({error})\n")
            return 2
        sys.stdout.write(json.dumps(summary) + "\n")
    else:
        sys.stdout.write(output + "\n")
    return 0


def _after_compaction(
    args: argparse.Namespace, squire: Any, messages: Any, plan: Any, archive: Path, session: str
) -> None:
    """What follows a used compaction; never fails it. The autopilot's list of injected
    entries is cleared (the context no longer holds them), and memory formation runs when the
    owner turned it on."""
    from . import _env
    from .context import compact
    from .harness.autopilot import clear_injected

    try:
        clear_injected(archive.parent, session)
    except OSError as error:
        sys.stderr.write(f"sanchopanza compact: ledger not cleared ({error})\n")
    wanted = args.form_memories or _env.get("MEMORY_FORMATION") in ("1", "true", "yes")
    if not wanted:
        return
    import asyncio

    from .context.formation import form
    from .harness.memory_gate import memory_dir_for

    stubbed = {
        s.id: archive / f"{compact.safe_name(s.id)}.txt" for s in plan.steps if s.action == "stub"
    }
    directory = _env.get("MEMORY_DIR") or memory_dir_for({"cwd": str(Path.cwd())})
    try:
        records = asyncio.run(form(squire, messages, stubbed, Path(directory)))
    except Exception as error:  # formation is lateral: the compaction stands
        sys.stderr.write(f"sanchopanza compact: memory formation failed ({error})\n")
        return
    stored = sum(r["stored"] for r in records)
    sys.stderr.write(
        f"sanchopanza compact: memory formation asked {len(records)}, stored {stored} "
        f"in {directory}\n"
    )


def _keep_out_of_git(path: Path) -> None:
    """A `.sanchopanza` folder on the way to `path` ignores itself (`context.archive`)."""
    from .context.archive import keep_out_of_git

    keep_out_of_git(path)


def _discard(folder: Path | None) -> None:
    import shutil

    if folder is not None:
        shutil.rmtree(folder, ignore_errors=True)


def _promote(staging: Path, archive: Path) -> None:
    """Move the staged results into the archive, keeping any from an earlier compaction."""
    if not staging.exists():
        return
    archive.mkdir(parents=True, exist_ok=True)
    for item in staging.iterdir():
        item.replace(archive / item.name)
    staging.rmdir()


def _repoint(messages: list[dict[str, Any]], staging: Path, archive: Path) -> list[dict[str, Any]]:
    """The stubs name the staging folder; point them at the archive the files now live in."""
    old, new = str(staging), str(archive)
    return json.loads(json.dumps(messages).replace(json.dumps(old)[1:-1], json.dumps(new)[1:-1]))


def _dag(args: argparse.Namespace) -> int:
    from .dag import build_dag, waves

    data = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    nodes = list(data["nodes"])
    edges = {tuple(k.split("->")): float(v) for k, v in data["edges"].items()}
    clean = build_dag(nodes, edges, threshold=args.threshold)  # type: ignore[arg-type]
    sys.stdout.write(
        json.dumps({"edges": sorted(clean), "waves": waves(nodes, clean)}, indent=1) + "\n"
    )
    return 0


def _tolerate_the_console_encoding() -> None:
    """Never die on a console that cannot encode what we print.

    `install` echoes the user's own settings file, and a console's encoding is not ours to
    choose (Windows defaults to cp1252): an unencodable character degrades to `?`, it does
    not abort the command. Only the error handler changes; the encoding stays the console's.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):  # a closed or exotic stream
                reconfigure(errors="replace")


def main(argv: list[str] | None = None) -> int:
    _tolerate_the_console_encoding()
    parser = argparse.ArgumentParser(
        prog="sanchopanza",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    bench = sub.add_parser("bench", help="run labelled cases through the squire")
    bench.add_argument("cases", nargs="+", help="JSONL bench files")
    bench.add_argument(
        "--provider", default="recorded", help="recorded | jev | null | <entry point>"
    )
    bench.add_argument("--fixture", default="fixtures/public-benches.jsonl")
    bench.add_argument("--record", default=None, help="append real decisions to this fixture file")
    bench.add_argument("--out", default=None, help="directory for results.json and summary.md")
    bench.add_argument("--title", default="Bench results")
    bench.add_argument("--concurrency", type=int, default=4)
    bench.set_defaults(func=_bench)

    hook = sub.add_parser("hook", help="Claude Code hook (stdin JSON -> stdout JSON)")
    hook.set_defaults(func=_hook)

    providers = sub.add_parser("providers", help="list installed providers")
    providers.set_defaults(func=_providers)

    install = sub.add_parser("install", help="write the harness hooks into settings.json")
    install.add_argument(
        "--scope", default="user", choices=("user", "project", "local"), help="which settings file"
    )
    install.add_argument("--path", default=None, help="an explicit settings file instead")
    install.add_argument(
        "--scan-content",
        action="store_true",
        help="also scan arriving tool results for instructions aimed at the model "
        "(detection only: the text is already in context by then)",
    )
    install.add_argument(
        "--check-done",
        action="store_true",
        help="at Stop, check that the transcript shows the request done and send Claude back "
        "once if it confidently does not (measured on AgentDojo, not on coding sessions)",
    )
    install.add_argument(
        "--content-tools",
        default=None,
        help="comma-separated tools to scan (default WebFetch,WebSearch)",
    )
    install.add_argument(
        "--no-shell-fetches",
        action="store_true",
        help="with --scan-content, do not scan the output of shell commands that fetch from "
        "the network (curl, wget, ...), which is scanned by default",
    )
    install.add_argument(
        "--compact",
        action="store_true",
        help="also install the Claude Code function-hook plugin that prunes tool results at "
        "/compact instead of summarising (early-access function hooks)",
    )
    install.add_argument(
        "--autopilot",
        action="store_true",
        help="cut long tool results on arrival, recall archived output and memories, and "
        "mask old results into the archive at a context percentage (implies --compact)",
    )
    install.add_argument(
        "--plugin-dir",
        default=None,
        help="with --compact, where the plugin is written (default ~/.sanchopanza/claude-plugin)",
    )
    install.add_argument(
        "--provider", default=None, help="set SANCHOPANZA_PROVIDER in the env block"
    )
    install.add_argument("--command-line", default="sanchopanza hook", help="the hook command")
    install.add_argument("--write", action="store_true", help="apply instead of printing")
    install.set_defaults(func=_install)

    compact = sub.add_parser(
        "compact",
        help="prune old tool results from a conversation (JSON out; exit 3 below the minimum)",
    )
    source = compact.add_mutually_exclusive_group(required=True)
    source.add_argument("--transcript", default=None, help="a Claude Code JSONL transcript")
    source.add_argument(
        "--stdin", action="store_true", help="a JSON list of Messages-API messages on stdin"
    )
    compact.add_argument(
        "--archive",
        default=None,
        help="where pruned results are saved (default ./.sanchopanza/archive), one folder per "
        "session",
    )
    compact.add_argument("--session", default=None, help="the archive folder's name")
    compact.add_argument(
        "--out", default=None, help="write the JSON here and only the report to stdout"
    )
    compact.add_argument(
        "--arm",
        default="sanchopanza",
        choices=("sanchopanza", "fastjev", "rules", "mask", "tournament"),
        help="mask: free observation masking (the autopilot's); tournament: experimental",
    )
    compact.add_argument(
        "--mask-turns", type=int, default=10, help="mask arm: acting turns whose results stay"
    )
    compact.add_argument(
        "--form-memories",
        action="store_true",
        help="ask `remember` about stubbed results and write the durable ones as memory files "
        "(also SANCHOPANZA_MEMORY_FORMATION=1; off by default)",
    )
    compact.add_argument(
        "--provider",
        default=None,
        help="recorded | jev | null | <entry point> (default: as the hook, from the environment)",
    )
    compact.add_argument("--fixture", default="fixtures/public-benches.jsonl")
    compact.add_argument("--keep-recent", type=int, default=6, help="last messages never pruned")
    compact.add_argument("--small", type=int, default=400, help="results shorter than this stay")
    compact.add_argument(
        "--min-reduction",
        type=float,
        default=0.25,
        help="below this fraction of characters freed, exit 3 so the caller summarises instead",
    )
    compact.set_defaults(func=_compact)

    dag = sub.add_parser("dag", help="clean DAG and waves from probabilistic pairs")
    dag.add_argument("plan")
    dag.add_argument("--threshold", type=float, default=0.5)
    dag.set_defaults(func=_dag)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
