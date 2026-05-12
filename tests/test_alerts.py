from datetime import datetime, timedelta, timezone

from gpu_watcher.alerts import IdleAlertManager
from gpu_watcher.config import AppConfig, ResendConfig
from gpu_watcher.models import Attribution, AttributedProcess, GpuProcess, Sample
from gpu_watcher.store import Store


class FakeResend:
    def __init__(self):
        self.sent = []

    def send_email(self, **kwargs):
        self.sent.append(kwargs)


def test_idle_alert_sends_once_per_idle_period(tmp_path, monkeypatch):
    store = Store(tmp_path / "watcher.sqlite3")
    store.initialize()
    config = AppConfig(
        database_path=tmp_path / "watcher.sqlite3",
        idle_threshold_hours=1,
        resend=ResendConfig(
            enabled=True,
            from_email="gpu@example.com",
            to_emails=("you@example.com",),
        ),
    )
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    resend = FakeResend()
    manager = IdleAlertManager(config, store, resend_client=resend)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    first = Sample(now, [], [])
    second = Sample(now + timedelta(minutes=30), [], [])
    third = Sample(now + timedelta(hours=1, minutes=1), [], [])
    fourth = Sample(now + timedelta(hours=2), [], [])

    assert manager.evaluate(first).should_send is False
    assert manager.evaluate(second).should_send is False
    assert manager.evaluate(third).should_send is True
    assert manager.evaluate(fourth).should_send is False
    assert len(resend.sent) == 1


def test_idle_alert_resets_after_activity(tmp_path, monkeypatch):
    store = Store(tmp_path / "watcher.sqlite3")
    store.initialize()
    config = AppConfig(
        database_path=tmp_path / "watcher.sqlite3",
        idle_threshold_hours=1,
        resend=ResendConfig(
            enabled=True,
            from_email="gpu@example.com",
            to_emails=("you@example.com",),
        ),
    )
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    resend = FakeResend()
    manager = IdleAlertManager(config, store, resend_client=resend)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert manager.evaluate(Sample(now, [], [])).should_send is False
    assert manager.evaluate(Sample(now + timedelta(hours=2), [], [])).should_send is True

    active = Sample(
        now + timedelta(hours=3),
        [],
        [
            AttributedProcess(
                GpuProcess(pid=1, gpu_uuid="gpu"),
                Attribution(label="alice", source="test"),
            )
        ],
    )
    assert manager.evaluate(active).should_send is False
    assert manager.evaluate(Sample(now + timedelta(hours=4), [], [])).should_send is False
    assert manager.evaluate(Sample(now + timedelta(hours=5, minutes=1), [], [])).should_send is True
    assert len(resend.sent) == 2


def test_resend_missing_key_records_error_without_throwing(tmp_path, monkeypatch):
    store = Store(tmp_path / "watcher.sqlite3")
    store.initialize()
    config = AppConfig(
        database_path=tmp_path / "watcher.sqlite3",
        idle_threshold_hours=1,
        resend=ResendConfig(
            enabled=True,
            from_email="gpu@example.com",
            to_emails=("you@example.com",),
        ),
    )
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    manager = IdleAlertManager(config, store)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert manager.evaluate(Sample(now, [], [])).should_send is False
    decision = manager.evaluate(Sample(now + timedelta(hours=2), [], []))

    assert decision.should_send is False
    assert decision.reason == "notification_failed"
    assert store.get_alert_state()["idle_alert_error"] is True
