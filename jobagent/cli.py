"""Command line interface: python -m jobagent <command>."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import __version__
from .config import Config
from .notifier import DiscordNotifier, NotificationError
from .pipeline import run
from .sources import SOURCE_CLASSES
from .storage import Storage

console = Console()
logger = logging.getLogger("jobagent")


def setup_logging(config: Config, verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else getattr(logging, config.log_level, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    config.log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        config.log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


# ----------------------------------------------------------------------
def cmd_run(args: argparse.Namespace) -> int:
    config = Config.load(args.config)
    setup_logging(config, args.verbose)

    if args.dry_run:
        console.print("[bold cyan]Dry run[/] — nothing will be sent to Discord.\n")

    try:
        summary = run(
            config,
            dry_run=args.dry_run,
            limit=args.limit,
            notify=not args.no_notify,
        )
    except NotificationError as exc:
        console.print(f"[bold red]Notification error:[/] {exc}")
        return 2

    _print_summary(summary)

    if args.dry_run:
        _print_jobs_table(config)
    if summary["selected"] and not args.dry_run:
        console.print(f"[green]Sent {summary['sent']} alert(s) to Discord.[/]")
    elif not summary["selected"]:
        console.print("[yellow]No new matching jobs this run.[/]")
    return 0


def _print_summary(summary: dict) -> None:
    console.print(
        f"Fetched [bold]{summary['fetched']}[/] jobs, "
        f"[bold green]{summary['new']}[/] new matching, "
        f"[bold]{summary['selected']}[/] selected."
    )
    table = Table(title="Sources", show_edge=False, pad_edge=False)
    table.add_column("Source")
    table.add_column("Fetched", justify="right")
    table.add_column("New", justify="right")
    for name, info in summary["sources"].items():
        if info.get("error"):
            table.add_row(name, "-", "[red]error[/]")
        else:
            table.add_row(name, str(info["fetched"]), str(info["new"]))
    console.print(table)


def _print_jobs_table(config: Config) -> None:
    storage = Storage(config.db_path)
    try:
        jobs = storage.pending(30)
    finally:
        storage.close()
    if not jobs:
        return
    table = Table(title="Pending jobs (would be sent next)", show_lines=False)
    table.add_column("Score", justify="right")
    table.add_column("Category")
    table.add_column("Title", overflow="fold", max_width=45)
    table.add_column("Company", max_width=22)
    table.add_column("Source")
    table.add_column("Location", max_width=18)
    for job in jobs:
        table.add_row(
            str(job.score),
            job.category,
            job.title,
            job.company,
            job.source,
            job.location or ("Remote" if job.remote else ""),
        )
    console.print(table)


def cmd_test_notify(args: argparse.Namespace) -> int:
    config = Config.load(args.config)
    setup_logging(config, args.verbose)
    try:
        DiscordNotifier(config).send_test()
    except NotificationError as exc:
        console.print(f"[bold red]Failed:[/] {exc}")
        return 2
    console.print("[green]Test alert sent. Check your Discord channel.[/]")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    config = Config.load(args.config)
    storage = Storage(config.db_path)
    try:
        stats = storage.stats()
    finally:
        storage.close()
    console.print(f"Database: [bold]{config.db_path}[/]")
    for key, value in stats.items():
        console.print(f"  {key:>10}: {value}")
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    config = Config.load(args.config)
    table = Table(title="Job sources")
    table.add_column("Name")
    table.add_column("Enabled")
    table.add_column("Status / notes")
    for name in SOURCE_CLASSES:
        enabled = config.source_enabled(name)
        note = ""
        if name == "adzuna" and not (config.adzuna_app_id and config.adzuna_app_key):
            note = "needs ADZUNA_APP_ID / ADZUNA_APP_KEY"
        if name == "indeed":
            note = "best effort — often blocked by captcha"
        table.add_row(
            name,
            "[green]yes[/]" if enabled else "[dim]no[/]",
            note,
        )
    console.print(table)
    console.print(f"\nEnabled: {sum(config.source_enabled(n) for n in SOURCE_CLASSES)}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    config = Config.load(args.config)
    checks: list[tuple[str, bool, str]] = []

    checks.append(("config.yaml", (config.base_dir / "config.yaml").exists(), str(config.base_dir / "config.yaml")))
    checks.append(("Discord webhook", bool(config.discord_webhook), "set in .env" if config.discord_webhook else "missing DISCORD_WEBHOOK_URL"))
    checks.append(("Discord mention", bool(config.discord_mention), config.discord_mention or "not set (no ping)"))
    checks.append(("Database folder", True, str(config.db_path.parent)))

    enabled = [name for name in SOURCE_CLASSES if config.source_enabled(name)]
    checks.append(("Enabled sources", bool(enabled), ", ".join(enabled) or "none"))

    for label, ok, detail in checks:
        mark = "[green]OK  [/]" if ok else "[red]FAIL[/]"
        console.print(f"{mark} {label:<18} {detail}")

    if not config.discord_webhook:
        console.print("\n[yellow]Tip:[/] copy .env.example to .env and paste your Discord webhook URL.")
        return 1
    return 0


def cmd_clear_pending(args: argparse.Namespace) -> int:
    config = Config.load(args.config)
    storage = Storage(config.db_path)
    try:
        pending = storage.stats()["pending"]
        if not pending:
            console.print("[green]Nothing pending.[/]")
            return 0
        if not args.yes:
            console.print(
                f"[yellow]{pending} pending jobs will be marked as seen.[/] "
                "Re-run with --yes to confirm."
            )
            return 1
        cleared = storage.clear_pending()
    finally:
        storage.close()
    console.print(f"[green]Cleared {cleared} pending job(s).[/] Future runs will alert only on new postings.")
    return 0


# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobagent",
        description="Scrape web-development jobs and push new matches to Discord.",
    )
    parser.add_argument("--version", action="version", version=f"jobagent {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--config", default=None, help="path to config.yaml")
        p.add_argument("-v", "--verbose", action="store_true")

    p_run = sub.add_parser("run", help="fetch jobs and notify about new matches")
    common(p_run)
    p_run.add_argument("--dry-run", action="store_true", help="do not send to Discord")
    p_run.add_argument("--limit", type=int, default=None, help="max alerts this run")
    p_run.add_argument("--no-notify", action="store_true", help="store results only")
    p_run.set_defaults(func=cmd_run)

    p_test = sub.add_parser("test-notify", help="send a test message to Discord")
    common(p_test)
    p_test.set_defaults(func=cmd_test_notify)

    p_stats = sub.add_parser("stats", help="show database statistics")
    common(p_stats)
    p_stats.set_defaults(func=cmd_stats)

    p_clear = sub.add_parser("clear-pending", help="mark the queued backlog as seen")
    common(p_clear)
    p_clear.add_argument("--yes", action="store_true", help="confirm the clear")
    p_clear.set_defaults(func=cmd_clear_pending)

    p_src = sub.add_parser("sources", help="list sources and their status")
    common(p_src)
    p_src.set_defaults(func=cmd_sources)

    p_doc = sub.add_parser("doctor", help="check configuration")
    common(p_doc)
    p_doc.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/]")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
