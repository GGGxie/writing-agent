from __future__ import annotations

import argparse
import json
from pathlib import Path

from writing_agent.collectors.config import load_collector_config
from writing_agent.collectors.rsshub import collect_rss_once, watch_rss
from writing_agent.collectors.store import CollectorStore
from writing_agent.collectors.x import stream_x, sync_x_rules
from writing_agent.config import get_settings
from writing_agent.editorial.checker import check_markdown_file


def _store(max_seen_items: int) -> CollectorStore:
    return CollectorStore(max_seen_items=max_seen_items)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="writing-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor")
    rss = subparsers.add_parser("collect-rss")
    rss.add_argument("--watch", action="store_true")
    x = subparsers.add_parser("collect-x")
    x.add_argument("--sync-only", action="store_true")
    check = subparsers.add_parser("check")
    check.add_argument("paths", nargs="+", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()
    if args.command == "doctor":
        print(f"workspace={settings.workspace_dir}")
        print(f"editorial_resources={settings.editorial_resources_dir}")
        print(f"sources_config={settings.sources_config_path}")
        print(f"text_model={'configured' if settings.has_text_model else 'missing'}")
        print(f"langsmith={'configured' if settings.has_langsmith else 'disabled'}")
        print(f"auth={'configured' if settings.auth_configured else 'missing'}")
        print(f"auth_allowlist_entries={len(settings.auth_allowed_emails)}")
        print(f"x_token={'configured' if settings.x_bearer_token else 'missing'}")
        return
    if args.command == "check":
        failed = False
        for path in args.paths:
            errors, warnings = check_markdown_file(path)
            print(path)
            for item in errors:
                print(f"  ERROR: {item}")
            for item in warnings:
                print(f"  WARN: {item}")
            failed = failed or bool(errors)
        raise SystemExit(1 if failed else 0)

    config = load_collector_config()
    store = _store(config.max_seen_items)
    try:
        if args.command == "collect-rss":
            if not config.rsshub.enabled:
                raise SystemExit("RSSHub 采集在配置中处于关闭状态")
            if args.watch:
                watch_rss(config.rsshub, store)
            else:
                print(json.dumps(collect_rss_once(config.rsshub, store), ensure_ascii=False))
        elif args.command == "collect-x":
            if not config.x.enabled:
                raise SystemExit("X 采集在配置中处于关闭状态")
            if args.sync_only:
                print(json.dumps(sync_x_rules(config.x), ensure_ascii=False))
            else:
                stream_x(config.x, store)
    finally:
        store.close()


if __name__ == "__main__":
    main()
