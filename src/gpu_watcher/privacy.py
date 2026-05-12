from __future__ import annotations

import ipaddress

REDACTED_IP = "[redacted-ip]"


def redact_ip(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return value
    if address.is_loopback:
        return value
    return REDACTED_IP
