from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class GpuProcess:
    pid: int
    gpu_uuid: str
    used_memory_mb: int | None = None
    user: str | None = None
    command: str | None = None


@dataclass(frozen=True)
class GpuMetric:
    index: int
    uuid: str
    name: str
    utilization_gpu_percent: int | None
    utilization_memory_percent: int | None
    memory_used_mb: int
    memory_total_mb: int
    temperature_c: int | None
    power_draw_watts: float | None
    processes: list[GpuProcess] = field(default_factory=list)


@dataclass(frozen=True)
class Attribution:
    label: str
    source: str
    linux_user: str | None = None
    remote_ip: str | None = None
    tailscale_user: str | None = None
    tailscale_host: str | None = None


@dataclass(frozen=True)
class AttributedProcess:
    process: GpuProcess
    attribution: Attribution


@dataclass(frozen=True)
class Sample:
    sampled_at: datetime
    gpus: list[GpuMetric]
    attributed_processes: list[AttributedProcess]

    @property
    def is_idle(self) -> bool:
        return len(self.attributed_processes) == 0
