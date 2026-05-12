# GPU Watcher

GPU Watcher is a small Python service for a shared NVIDIA GPU host. It reads metrics through NVML, records a configurable sliding window in SQLite, attributes active GPU work to SSH/Tailscale users, sends idle alerts through Resend, and serves a simple dashboard/API over your tailnet.

## Quick Start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp config.example.toml config.toml
gpu-watcher all --config config.toml
```

Set `RESEND_API_KEY` in the environment if email alerts are enabled.

For a Tailscale-only dashboard, bind `[dashboard].host` to the GPU host's Tailscale IP or place the local server behind `tailscale serve`.

## Commands

```bash
gpu-watcher collect-once --config config.toml
gpu-watcher run --config config.toml
gpu-watcher web --config config.toml
gpu-watcher all --config config.toml
gpu-watcher-mac-notifier --url http://localhost:8765
```

- `collect-once` samples NVML once and writes to SQLite.
- `run` starts only the polling/alert loop.
- `web` starts only the dashboard/API.
- `all` starts the polling loop and dashboard in one process.
- `gpu-watcher-mac-notifier` polls `/api/status` and sends a local macOS notification when the idle alert state changes.

Remote IP addresses are redacted before they are stored or returned by the API. Localhost addresses are left visible for local development.

## Configuration

See [config.example.toml](/Users/warrenlow/Documents/projects/gpu-watcher/config.example.toml).

Important defaults:

- `sampling_interval_seconds = 60`
- `idle_threshold_hours = 2`
- `retention_days = 15`

Secrets:

- `RESEND_API_KEY`: required only when `[resend].enabled = true`

## API

- `GET /api/status`: current GPU state and idle alert state
- `GET /api/usage?hours=24`: usage summary by attributed user
- `GET /api/timeseries?hours=24`: sampled GPU metrics
- `GET /healthz`: process health check

## Attribution Model

The first version assumes people start work through SSH over Tailscale.

For each active GPU process, the service:

1. Walks the process ancestry with `psutil`.
2. Looks for an SSH daemon process and extracts the remote IP.
3. Resolves that IP through `tailscale status --json`.
4. Falls back to Linux username, then manual config labels, then `unknown`.

## Tests

```bash
pytest
```
