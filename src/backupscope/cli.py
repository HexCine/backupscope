import argparse
import json
import sys
from pathlib import Path
from . import __version__
from .catalog import read_catalog
from .core import analyze, draft_policy
from .inventory import collect, from_inspect
from .report import html_report, text_report
from .validation import InputError, need, read_json


def emit(value, output):
    if output:
        # Exclusive creation protects existing backups/configuration from replacement.
        with Path(output).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
    else:
        sys.stdout.write(value)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Check Docker mount path presence and freshness in a restic snapshot.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inventory", help="Read-only, redacted Docker mount discovery")
    inv.add_argument("--host", required=True, help="Stable identity matching restic's snapshot hostname")
    inv.add_argument("--project", help="Only containers with this Compose project label")
    inv.add_argument("--inspect", help="Normalize a saved Docker inspect JSON array instead of contacting Docker")
    inv.add_argument("--captured-at", help="Required original capture time when --inspect is used")
    inv.add_argument("--output")
    init = sub.add_parser("init", help="Draft exact mount mappings; review before using")
    init.add_argument("--inventory", required=True)
    init.add_argument("--output")
    check = sub.add_parser("check", help="Offline check of one unfiltered restic ls --json export")
    check.add_argument("--inventory", required=True)
    check.add_argument("--snapshot", required=True)
    check.add_argument("--policy", required=True)
    check.add_argument("--at", help="Explicit evaluation time for reproducible fixtures (default: current UTC)")
    check.add_argument("--format", choices=("text", "json", "html"), default="text")
    check.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        if args.command == "inventory":
            need(not (args.inspect and args.project), "--project cannot filter saved inspect input; supply a scoped export")
            need(bool(args.inspect) == bool(args.captured_at), "--inspect and --captured-at must be supplied together")
            data = from_inspect(read_json(args.inspect), args.host, args.captured_at) if args.inspect else collect(args.host, args.project)
            emit(json.dumps(data, ensure_ascii=False, indent=2) + "\n", args.output)
            return 0
        if args.command == "init":
            emit(json.dumps(draft_policy(read_json(args.inventory)), ensure_ascii=False, indent=2) + "\n", args.output)
            return 0
        report = analyze(read_json(args.inventory), read_catalog(args.snapshot), read_json(args.policy), args.at)
        output = json.dumps(report, ensure_ascii=False, indent=2) + "\n" if args.format == "json" else html_report(report) if args.format == "html" else text_report(report)
        emit(output, args.output)
        return report["exit_code"]
    except (InputError, OSError, UnicodeError, RecursionError) as exc:
        # File paths in OSError can be local; never echo file contents or subprocess stderr.
        sys.stderr.write("BackupScope input/I/O error: " + str(exc).replace("\x1b", "\\x1b") + "\n")
        return 2
