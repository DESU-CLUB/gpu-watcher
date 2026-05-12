from __future__ import annotations

import logging
import signal
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from .alerts import IdleAlertManager
from .attribution import Attributor
from .config import AppConfig
from .models import AttributedProcess, Sample
from .nvml import NvmlCollector
from .store import Store

LOGGER = logging.getLogger(__name__)


@dataclass
class WatcherService:
    config: AppConfig
    store: Store
    collector: NvmlCollector
    attributor: Attributor
    alerts: IdleAlertManager
    stop_event: threading.Event

    @classmethod
    def create(cls, config: AppConfig) -> "WatcherService":
        store = Store(config.database_path)
        store.initialize()
        return cls(
            config=config,
            store=store,
            collector=NvmlCollector(),
            attributor=Attributor(config.identity),
            alerts=IdleAlertManager(config, store),
            stop_event=threading.Event(),
        )

    def collect_once(self) -> Sample:
        sampled_at = datetime.now(timezone.utc)
        gpus = self.collector.collect()
        attributed = []

        for gpu in gpus:
            for process in gpu.processes:
                attributed.append(
                    AttributedProcess(
                        process=process,
                        attribution=self.attributor.attribute(process),
                    )
                )

        sample = Sample(
            sampled_at=sampled_at,
            gpus=gpus,
            attributed_processes=attributed,
        )
        self.store.insert_sample(sample)
        self.store.prune_older_than(self.config.retention_days, now=sampled_at)
        decision = self.alerts.evaluate(sample)
        LOGGER.info(
            "sampled %s gpu(s), %s process(es), idle_alert=%s:%s",
            len(gpus),
            len(attributed),
            decision.should_send,
            decision.reason,
        )
        return sample

    def run_forever(self) -> None:
        LOGGER.info(
            "starting GPU watcher loop interval=%ss db=%s",
            self.config.sampling_interval_seconds,
            self.config.database_path,
        )
        while not self.stop_event.is_set():
            started = time.monotonic()
            try:
                self.collect_once()
            except Exception:
                LOGGER.exception("collection failed")

            elapsed = time.monotonic() - started
            wait_for = max(1, self.config.sampling_interval_seconds - elapsed)
            self.stop_event.wait(wait_for)

    def stop(self) -> None:
        self.stop_event.set()
        self.collector.close()


def install_signal_handlers(service: WatcherService) -> None:
    def _handle(_signum, _frame) -> None:
        service.stop()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)


def run_service(config: AppConfig) -> None:
    service = WatcherService.create(config)
    install_signal_handlers(service)
    try:
        service.run_forever()
    finally:
        service.stop()
