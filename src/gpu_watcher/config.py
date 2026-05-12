from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DashboardConfig:
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass(frozen=True)
class ResendConfig:
    enabled: bool = False
    from_email: str = ""
    to_emails: tuple[str, ...] = ()


@dataclass(frozen=True)
class IdentityConfig:
    manual_labels: dict[str, str] = field(default_factory=dict)
    ip_labels: dict[str, str] = field(default_factory=dict)
    user_labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AppConfig:
    sampling_interval_seconds: int = 60
    idle_threshold_hours: float = 2.0
    retention_days: int = 15
    database_path: Path = Path("gpu-watcher.sqlite3")
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    resend: ResendConfig = field(default_factory=ResendConfig)
    identity: IdentityConfig = field(default_factory=IdentityConfig)

    @property
    def resend_api_key(self) -> str | None:
        return os.environ.get("RESEND_API_KEY")


def load_config(path: str | Path | None) -> AppConfig:
    if path is None:
        return AppConfig()

    path = Path(path)
    with path.open("rb") as f:
        raw = tomllib.load(f)

    dashboard_raw = raw.get("dashboard", {})
    resend_raw = raw.get("resend", {})
    identity_raw = raw.get("identity", {})

    return AppConfig(
        sampling_interval_seconds=int(raw.get("sampling_interval_seconds", 60)),
        idle_threshold_hours=float(raw.get("idle_threshold_hours", 2)),
        retention_days=int(raw.get("retention_days", 15)),
        database_path=Path(raw.get("database_path", "gpu-watcher.sqlite3")),
        dashboard=DashboardConfig(
            host=str(dashboard_raw.get("host", "127.0.0.1")),
            port=int(dashboard_raw.get("port", 8765)),
        ),
        resend=ResendConfig(
            enabled=bool(resend_raw.get("enabled", False)),
            from_email=str(resend_raw.get("from_email", "")),
            to_emails=tuple(resend_raw.get("to_emails", ())),
        ),
        identity=IdentityConfig(
            manual_labels=dict(identity_raw.get("manual_labels", {})),
            ip_labels=dict(identity_raw.get("ip_labels", {})),
            user_labels=dict(identity_raw.get("user_labels", {})),
        ),
    )
