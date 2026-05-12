# GPU Watcher

GPU Watcher is a small Python service for a shared NVIDIA GPU host. It reads metrics through NVML, records a configurable sliding window in SQLite, attributes active GPU work to SSH/Tailscale users, sends idle alerts through Resend, and serves a simple dashboard/API over your tailnet.

## Quick Start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp config.example.toml config.toml
gpu-watcher --config config.toml all
```

Set `RESEND_API_KEY` in the environment if email alerts are enabled.

For a Tailscale-only dashboard, keep the default localhost bind and place the local server behind `tailscale serve`. The API/dashboard has no app-level auth; anyone who can reach the port can see usage data and process command lines.

## Commands

```bash
gpu-watcher --config config.toml collect-once
gpu-watcher --config config.toml run
gpu-watcher --config config.toml web
gpu-watcher --config config.toml all
gpu-watcher-mac-notifier --url http://localhost:8765
```

Global flags can also be placed after the subcommand, so `gpu-watcher all --config config.toml` works too.

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

`config.toml` is git-ignored because it may contain real IP-to-name mappings and alert recipients. Commit only `config.example.toml`.

If `[resend].enabled = true` but the key/from/to values are missing, the service records an alert error and logs a warning once instead of failing the polling loop every interval.

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

For useful SSH remote-IP attribution, run the service as root. Inspecting `sshd` socket ownership through `psutil` often requires elevated privileges; a normal/shared account will usually fall back to the local Linux username.

## Production

Install the repo somewhere stable, for example `/opt/gpu-watcher`, and keep private config in `/etc/gpu-watcher`:

```bash
sudo mkdir -p /opt /etc/gpu-watcher
sudo git clone https://github.com/DESU-CLUB/gpu-watcher.git /opt/gpu-watcher
cd /opt/gpu-watcher
sudo python3 -m venv .venv
sudo .venv/bin/pip install -e .
sudo cp config.example.toml /etc/gpu-watcher/config.toml
sudo cp deploy/gpu-watcher.service /etc/systemd/system/gpu-watcher.service
```

Optional Resend env file:

```bash
sudo install -m 600 /dev/null /etc/gpu-watcher/gpu-watcher.env
sudo editor /etc/gpu-watcher/gpu-watcher.env
```

```bash
RESEND_API_KEY=...
```

Enable the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now gpu-watcher
```

Expose the localhost dashboard to your tailnet:

```bash
tailscale serve --bg localhost:8765
```

The bundled macOS notifier is optional and macOS-only; it uses `osascript` and runs a simple polling loop intended for a login item or terminal session.

## Tests

```bash
pytest
```
