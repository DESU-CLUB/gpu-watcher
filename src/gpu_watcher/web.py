from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib.resources import files

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import AppConfig
from .store import Store


def create_app(config: AppConfig, store: Store | None = None) -> FastAPI:
    store = store or Store(config.database_path)
    store.initialize()
    app = FastAPI(title="GPU Watcher")

    static_path = files("gpu_watcher").joinpath("static")
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return static_path.joinpath("index.html").read_text(encoding="utf-8")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/status")
    def status():
        return store.latest_status()

    @app.get("/api/usage")
    def usage(hours: float = Query(default=24, gt=0, le=24 * 15)):
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        return {
            "hours": hours,
            "users": store.usage_summary(since, config.sampling_interval_seconds),
        }

    @app.get("/api/timeseries")
    def timeseries(hours: float = Query(default=24, gt=0, le=24 * 15)):
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        return {"hours": hours, "samples": store.timeseries(since)}

    return app
