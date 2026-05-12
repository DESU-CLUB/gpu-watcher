from __future__ import annotations

import argparse
import logging
import threading

from .config import load_config
from .service import WatcherService, install_signal_handlers, run_service
from .store import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gpu-watcher")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--log-level", default="INFO")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("collect-once")
    subparsers.add_parser("run")
    subparsers.add_parser("web")
    subparsers.add_parser("all")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = load_config(args.config)

    if args.command == "collect-once":
        service = WatcherService.create(config)
        try:
            service.collect_once()
        finally:
            service.stop()
        return 0

    if args.command == "run":
        run_service(config)
        return 0

    if args.command == "web":
        import uvicorn

        from .web import create_app

        app = create_app(config)
        uvicorn.run(app, host=config.dashboard.host, port=config.dashboard.port)
        return 0

    if args.command == "all":
        import uvicorn

        from .web import create_app

        service = WatcherService.create(config)
        install_signal_handlers(service)
        thread = threading.Thread(target=service.run_forever, daemon=True)
        thread.start()
        try:
            store = Store(config.database_path)
            app = create_app(config, store)
            uvicorn.run(app, host=config.dashboard.host, port=config.dashboard.port)
        finally:
            service.stop()
            thread.join(timeout=5)
        return 0

    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
