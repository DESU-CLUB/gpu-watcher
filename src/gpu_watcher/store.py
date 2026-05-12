from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import AttributedProcess, Sample, from_iso, to_iso


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS gpu_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sampled_at TEXT NOT NULL,
                    gpu_index INTEGER NOT NULL,
                    gpu_uuid TEXT NOT NULL,
                    gpu_name TEXT NOT NULL,
                    utilization_gpu_percent INTEGER,
                    utilization_memory_percent INTEGER,
                    memory_used_mb INTEGER NOT NULL,
                    memory_total_mb INTEGER NOT NULL,
                    temperature_c INTEGER,
                    power_draw_watts REAL,
                    process_count INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_gpu_samples_sampled_at
                    ON gpu_samples(sampled_at);

                CREATE TABLE IF NOT EXISTS gpu_process_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sampled_at TEXT NOT NULL,
                    pid INTEGER NOT NULL,
                    gpu_uuid TEXT NOT NULL,
                    used_memory_mb INTEGER,
                    command TEXT,
                    linux_user TEXT,
                    remote_ip TEXT,
                    tailscale_user TEXT,
                    tailscale_host TEXT,
                    attribution_label TEXT NOT NULL,
                    attribution_source TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_process_samples_sampled_at
                    ON gpu_process_samples(sampled_at);

                CREATE TABLE IF NOT EXISTS alert_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def insert_sample(self, sample: Sample) -> None:
        sampled_at = to_iso(sample.sampled_at)
        with self.connect() as conn:
            for gpu in sample.gpus:
                conn.execute(
                    """
                    INSERT INTO gpu_samples (
                        sampled_at, gpu_index, gpu_uuid, gpu_name,
                        utilization_gpu_percent, utilization_memory_percent,
                        memory_used_mb, memory_total_mb, temperature_c,
                        power_draw_watts, process_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sampled_at,
                        gpu.index,
                        gpu.uuid,
                        gpu.name,
                        gpu.utilization_gpu_percent,
                        gpu.utilization_memory_percent,
                        gpu.memory_used_mb,
                        gpu.memory_total_mb,
                        gpu.temperature_c,
                        gpu.power_draw_watts,
                        len(gpu.processes),
                    ),
                )

            for attributed in sample.attributed_processes:
                proc = attributed.process
                attr = attributed.attribution
                conn.execute(
                    """
                    INSERT INTO gpu_process_samples (
                        sampled_at, pid, gpu_uuid, used_memory_mb, command,
                        linux_user, remote_ip, tailscale_user, tailscale_host,
                        attribution_label, attribution_source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sampled_at,
                        proc.pid,
                        proc.gpu_uuid,
                        proc.used_memory_mb,
                        proc.command,
                        attr.linux_user,
                        attr.remote_ip,
                        attr.tailscale_user,
                        attr.tailscale_host,
                        attr.label,
                        attr.source,
                    ),
                )

    def prune_older_than(self, retention_days: int, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        cutoff = to_iso(now - timedelta(days=retention_days))
        with self.connect() as conn:
            conn.execute("DELETE FROM gpu_samples WHERE sampled_at < ?", (cutoff,))
            conn.execute("DELETE FROM gpu_process_samples WHERE sampled_at < ?", (cutoff,))

    def latest_status(self) -> dict[str, Any]:
        with self.connect() as conn:
            latest = conn.execute(
                "SELECT sampled_at FROM gpu_samples ORDER BY sampled_at DESC LIMIT 1"
            ).fetchone()
            if latest is None:
                return {"sampled_at": None, "gpus": [], "processes": [], "idle": True}

            sampled_at = latest["sampled_at"]
            gpus = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT * FROM gpu_samples
                    WHERE sampled_at = ?
                    ORDER BY gpu_index
                    """,
                    (sampled_at,),
                )
            ]
            processes = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT * FROM gpu_process_samples
                    WHERE sampled_at = ?
                    ORDER BY attribution_label, pid
                    """,
                    (sampled_at,),
                )
            ]
            alert_state = self.get_alert_state()

        return {
            "sampled_at": sampled_at,
            "gpus": gpus,
            "processes": processes,
            "idle": len(processes) == 0,
            "alert": alert_state,
        }

    def usage_summary(
        self, since: datetime, sample_interval_seconds: int = 60
    ) -> list[dict[str, Any]]:
        since_iso = to_iso(since)
        with self.connect() as conn:
            rows = conn.execute(
                """
                WITH per_user_sample AS (
                    SELECT
                        p.attribution_label AS label,
                        p.sampled_at AS sampled_at,
                        SUM(COALESCE(p.used_memory_mb, 0)) AS user_vram_mb,
                        AVG(g.utilization_gpu_percent) AS avg_gpu_util_percent,
                        AVG(
                            CASE
                                WHEN g.memory_total_mb > 0
                                THEN 100 * g.memory_used_mb / g.memory_total_mb
                            END
                        ) AS avg_vram_util_percent
                    FROM gpu_process_samples p
                    LEFT JOIN gpu_samples g
                        ON g.sampled_at = p.sampled_at
                        AND g.gpu_uuid = p.gpu_uuid
                    WHERE p.sampled_at >= ?
                    GROUP BY p.attribution_label, p.sampled_at
                )
                SELECT
                    label,
                    COUNT(*) AS sample_count,
                    COUNT(*) * ? AS active_seconds,
                    AVG(user_vram_mb) AS avg_process_vram_mb,
                    AVG(avg_gpu_util_percent) AS avg_gpu_util_percent,
                    AVG(avg_vram_util_percent) AS avg_vram_util_percent,
                    MAX(sampled_at) AS last_seen_at
                FROM per_user_sample
                GROUP BY label
                ORDER BY sample_count DESC, label ASC
                """,
                (since_iso, sample_interval_seconds),
            ).fetchall()

        return [dict(row) for row in rows]

    def timeseries(self, since: datetime) -> list[dict[str, Any]]:
        since_iso = to_iso(since)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    sampled_at,
                    gpu_index,
                    gpu_name,
                    utilization_gpu_percent,
                    utilization_memory_percent,
                    memory_used_mb,
                    memory_total_mb,
                    temperature_c,
                    power_draw_watts,
                    process_count
                FROM gpu_samples
                WHERE sampled_at >= ?
                ORDER BY sampled_at ASC, gpu_index ASC
                """,
                (since_iso,),
            ).fetchall()

        return [dict(row) for row in rows]

    def set_alert_state(self, **values: Any) -> None:
        with self.connect() as conn:
            for key, value in values.items():
                conn.execute(
                    """
                    INSERT INTO alert_state(key, value)
                    VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, json.dumps(value)),
                )

    def get_alert_state(self) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute("SELECT key, value FROM alert_state").fetchall()
        state = {}
        for row in rows:
            try:
                state[row["key"]] = json.loads(row["value"])
            except json.JSONDecodeError:
                state[row["key"]] = row["value"]
        return state

    def idle_since(self) -> datetime | None:
        with self.connect() as conn:
            latest_active = conn.execute(
                "SELECT MAX(sampled_at) AS sampled_at FROM gpu_process_samples"
            ).fetchone()["sampled_at"]
            latest_sample = conn.execute(
                "SELECT MAX(sampled_at) AS sampled_at FROM gpu_samples"
            ).fetchone()["sampled_at"]

        if latest_sample is None:
            return None
        if latest_active is None:
            return from_iso(latest_sample)
        return from_iso(latest_active)
