"""`sancho` command line.

sanchopanza bench benches/*.jsonl --provider recorded --fixture fixtures/public-benches.jsonl
sanchopanza bench benches/*.jsonl --provider jev --record fixtures/new.jsonl --out results/today
sanchopanza hook            # Claude Code hook: JSON in, JSON out
sanchopanza install         # print the settings block; --write to apply it
sanchopanza install --scan-content --write   # and scan arriving content for injections
sanchopanza install --check-done --write     # and check "done" before a stop
sanchopanza providers       # what is installed
sanchopanza dag plan.json   # clean DAG and waves from {"nodes": [...], "edges": {"A->B": 0.9}}
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
from pathlib import Path

from .dag import build_dag, waves
from .eval.bench import load_cases, render_markdown, rows_to_json, run_bench, summarize
from .providers import available, create
from .providers.recorded import RecordingDecider


def _bench(args: argparse.Namespace) -> int:
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
    for name, target in sorted(available().items()):
        sys.stdout.write(f"{name:10} {target}\n")
    return 0


def _install(args: argparse.Namespace) -> int:
    from .harness.generic import HarnessConfig
    from .harness.install import apply, default_path, plan

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
    try:
        settings = plan(path, config, command=args.command_line, provider=args.provider or "")
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        return 2
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
    return 0


def _dag(args: argparse.Namespace) -> int:
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
    install.add_argument("--provider", default=None, help="set SANCHO_PROVIDER in the env block")
    install.add_argument("--command-line", default="sanchopanza hook", help="the hook command")
    install.add_argument("--write", action="store_true", help="apply instead of printing")
    install.set_defaults(func=_install)

    dag = sub.add_parser("dag", help="clean DAG and waves from probabilistic pairs")
    dag.add_argument("plan")
    dag.add_argument("--threshold", type=float, default=0.5)
    dag.set_defaults(func=_dag)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
