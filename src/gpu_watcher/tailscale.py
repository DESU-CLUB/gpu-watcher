from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class TailscalePeer:
    ip: str
    hostname: str | None
    user: str | None


class TailscaleResolver:
    def __init__(self, status_json: dict | None = None) -> None:
        self._status_json = status_json

    def resolve_ip(self, ip: str) -> TailscalePeer | None:
        status = self._status_json if self._status_json is not None else self._load_status()
        for peer in _iter_peers(status):
            ips = peer.get("TailscaleIPs") or []
            if ip not in ips:
                continue
            return TailscalePeer(
                ip=ip,
                hostname=peer.get("HostName") or peer.get("DNSName"),
                user=peer.get("User") or peer.get("LoginName"),
            )
        return None

    def _load_status(self) -> dict:
        try:
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                check=True,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except Exception:
            return {}
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {}


def _iter_peers(status: dict):
    self_peer = status.get("Self")
    if isinstance(self_peer, dict):
        yield self_peer

    peers = status.get("Peer", {})
    if isinstance(peers, dict):
        yield from peers.values()
