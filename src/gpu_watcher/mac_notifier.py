from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gpu-watcher-mac-notifier")
    parser.add_argument("--url", required=True, help="Base dashboard URL, e.g. http://localhost:8765")
    parser.add_argument("--interval-seconds", type=int, default=60)
    args = parser.parse_args(argv)

    last_sent_at = None
    base_url = args.url.rstrip("/")

    while True:
        try:
            status = _fetch_status(base_url)
            alert = status.get("alert", {})
            sent_at = alert.get("idle_alert_sent_at")
            if alert.get("idle_alert_sent") and sent_at and sent_at != last_sent_at:
                idle_since = alert.get("idle_since") or "unknown"
                _notify("GPU is idle", f"The shared GPU has been idle since {idle_since}.")
                last_sent_at = sent_at
        except Exception as exc:
            print(f"notification poll failed: {exc}")
        time.sleep(args.interval_seconds)


def _fetch_status(base_url: str) -> dict:
    with urllib.request.urlopen(f"{base_url}/api/status", timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _notify(title: str, message: str) -> None:
    subprocess.run(
        [
            "osascript",
            "-e",
            f'display notification "{_escape(message)}" with title "{_escape(title)}"',
        ],
        check=False,
    )


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


if __name__ == "__main__":
    raise SystemExit(main())
