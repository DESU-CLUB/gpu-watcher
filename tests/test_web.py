from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from gpu_watcher.config import AppConfig
from gpu_watcher.models import GpuMetric, Sample
from gpu_watcher.store import Store
from gpu_watcher.web import create_app


def test_status_api_returns_latest_sample(tmp_path):
    db = tmp_path / "watcher.sqlite3"
    store = Store(db)
    store.initialize()
    store.insert_sample(
        Sample(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            [
                GpuMetric(
                    index=0,
                    uuid="gpu",
                    name="GPU",
                    utilization_gpu_percent=50,
                    utilization_memory_percent=25,
                    memory_used_mb=512,
                    memory_total_mb=1024,
                    temperature_c=55,
                    power_draw_watts=80,
                    processes=[],
                )
            ],
            [],
        )
    )

    app = create_app(AppConfig(database_path=db), store)
    client = TestClient(app)

    response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["idle"] is True
    assert body["gpus"][0]["utilization_gpu_percent"] == 50
