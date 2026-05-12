from __future__ import annotations

import re
from dataclasses import dataclass

from .config import IdentityConfig
from .models import Attribution, GpuProcess
from .privacy import redact_ip
from .tailscale import TailscaleResolver

SSH_REMOTE_RE = re.compile(r"sshd: .+?@(?P<ip>[0-9a-fA-F:.]+)(?:\s|$)")


@dataclass(frozen=True)
class ProcessContext:
    linux_user: str | None
    remote_ip: str | None


class ProcessInspector:
    def inspect(self, pid: int) -> ProcessContext:
        try:
            import psutil

            proc = psutil.Process(pid)
            linux_user = _safe_username(proc)
            remote_ip = _find_remote_ip(proc)
            return ProcessContext(linux_user=linux_user, remote_ip=remote_ip)
        except Exception:
            return ProcessContext(linux_user=None, remote_ip=None)


class Attributor:
    def __init__(
        self,
        identity: IdentityConfig,
        tailscale: TailscaleResolver | None = None,
        inspector: ProcessInspector | None = None,
    ) -> None:
        self._identity = identity
        self._tailscale = tailscale or TailscaleResolver()
        self._inspector = inspector or ProcessInspector()

    def attribute(self, process: GpuProcess) -> Attribution:
        ctx = self._inspector.inspect(process.pid)

        if ctx.remote_ip:
            peer = self._tailscale.resolve_ip(ctx.remote_ip)
            redacted_remote_ip = redact_ip(ctx.remote_ip)
            if peer:
                label = (
                    self._identity.manual_labels.get(peer.user or "")
                    or self._identity.manual_labels.get(peer.hostname or "")
                    or self._identity.ip_labels.get(ctx.remote_ip)
                    or peer.user
                    or peer.hostname
                    or redacted_remote_ip
                    or "unknown"
                )
                return Attribution(
                    label=label,
                    source="tailscale",
                    linux_user=ctx.linux_user,
                    remote_ip=redacted_remote_ip,
                    tailscale_user=peer.user,
                    tailscale_host=peer.hostname,
                )

            ip_label = self._identity.ip_labels.get(ctx.remote_ip)
            if ip_label:
                return Attribution(
                    label=ip_label,
                    source="ip_label",
                    linux_user=ctx.linux_user,
                    remote_ip=redacted_remote_ip,
                )

        linux_user = ctx.linux_user or process.user
        if linux_user:
            label = (
                self._identity.user_labels.get(linux_user)
                or self._identity.manual_labels.get(linux_user)
                or linux_user
            )
            return Attribution(
                label=label,
                source="linux_user",
                linux_user=linux_user,
                remote_ip=redact_ip(ctx.remote_ip),
            )

        return Attribution(label="unknown", source="unknown", remote_ip=redact_ip(ctx.remote_ip))


def _safe_username(proc) -> str | None:
    try:
        return proc.username()
    except Exception:
        return None


def _find_remote_ip(proc) -> str | None:
    for ancestor in [proc, *proc.parents()]:
        cmd = _cmd_text(ancestor)
        match = SSH_REMOTE_RE.search(cmd)
        if match:
            return match.group("ip")

        ip = _ip_from_connections(ancestor)
        if ip:
            return ip

    return None


def _cmd_text(proc) -> str:
    try:
        return " ".join(proc.cmdline())
    except Exception:
        try:
            return proc.name()
        except Exception:
            return ""


def _ip_from_connections(proc) -> str | None:
    try:
        name = proc.name()
        if "sshd" not in name:
            return None
        connections = proc.net_connections(kind="tcp")
    except Exception:
        return None

    for conn in connections:
        remote = getattr(conn, "raddr", None)
        if remote:
            return remote.ip
    return None
