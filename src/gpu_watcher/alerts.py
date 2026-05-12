from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .config import AppConfig
from .models import Sample, to_iso
from .store import Store

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertDecision:
    should_send: bool
    reason: str
    idle_since: datetime | None


class ResendClient:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def send_email(
        self,
        *,
        from_email: str,
        to_emails: tuple[str, ...],
        subject: str,
        html: str,
    ) -> None:
        request = urllib.request.Request(
            "https://api.resend.com/emails",
            data=json.dumps(
                {
                    "from": from_email,
                    "to": list(to_emails),
                    "subject": subject,
                    "html": html,
                }
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status >= 300:
                    raise RuntimeError(f"Resend returned HTTP {response.status}")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Resend request failed: {exc}") from exc


class IdleAlertManager:
    def __init__(
        self,
        config: AppConfig,
        store: Store,
        resend_client: ResendClient | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._resend_client = resend_client
        self._warned_alert_errors: set[str] = set()

    def evaluate(self, sample: Sample) -> AlertDecision:
        if not sample.is_idle:
            self._store.set_alert_state(
                idle=False,
                idle_since=None,
                idle_alert_sent=False,
                last_active_at=to_iso(sample.sampled_at),
            )
            return AlertDecision(False, "gpu_active", None)

        state = self._store.get_alert_state()
        idle_since_value = state.get("idle_since")
        idle_since = (
            datetime.fromisoformat(idle_since_value)
            if isinstance(idle_since_value, str) and idle_since_value
            else sample.sampled_at
        )

        threshold = timedelta(hours=self._config.idle_threshold_hours)
        already_sent = bool(state.get("idle_alert_sent", False))
        threshold_reached = sample.sampled_at - idle_since >= threshold

        self._store.set_alert_state(idle=True, idle_since=to_iso(idle_since))

        if already_sent:
            return AlertDecision(False, "already_sent", idle_since)
        if not threshold_reached:
            return AlertDecision(False, "below_threshold", idle_since)

        notification_sent = self._send_idle_alert(idle_since, sample.sampled_at)
        if not notification_sent:
            self._store.set_alert_state(idle_alert_error=True)
            return AlertDecision(False, "notification_failed", idle_since)

        self._store.set_alert_state(
            idle_alert_sent=True,
            idle_alert_sent_at=to_iso(sample.sampled_at),
            idle_alert_error=False,
        )
        reason = "sent" if self._config.resend.enabled else "notifications_disabled"
        return AlertDecision(True, reason, idle_since)

    def _send_idle_alert(self, idle_since: datetime, now: datetime) -> bool:
        if not self._config.resend.enabled:
            return True
        if not self._config.resend_api_key:
            self._warn_once("RESEND_API_KEY is required when Resend alerts are enabled")
            return False
        if not self._config.resend.from_email or not self._config.resend.to_emails:
            self._warn_once("Resend from_email and to_emails must be configured")
            return False

        client = self._resend_client or ResendClient(self._config.resend_api_key)
        idle_hours = (now - idle_since).total_seconds() / 3600
        try:
            client.send_email(
                from_email=self._config.resend.from_email,
                to_emails=self._config.resend.to_emails,
                subject=f"GPU idle for {idle_hours:.1f} hours",
                html=(
                    "<p>The shared GPU appears idle.</p>"
                    f"<p><strong>Idle since:</strong> {to_iso(idle_since)}</p>"
                    f"<p><strong>Idle duration:</strong> {idle_hours:.1f} hours</p>"
                ),
            )
        except RuntimeError as exc:
            self._warn_once(str(exc))
            return False
        return True

    def _warn_once(self, message: str) -> None:
        if message in self._warned_alert_errors:
            return
        self._warned_alert_errors.add(message)
        LOGGER.warning("idle alert notification skipped: %s", message)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
