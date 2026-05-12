from datetime import datetime, timedelta, timezone

from gpu_watcher.models import GpuMetric, Sample
from gpu_watcher.store import Store


def test_store_prunes_old_samples(tmp_path):
    store = Store(tmp_path / "watcher.sqlite3")
    store.initialize()
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new = old + timedelta(days=20)

    store.insert_sample(
        Sample(
            old,
            [
                GpuMetric(
                    index=0,
                    uuid="gpu",
                    name="GPU",
                    utilization_gpu_percent=10,
                    utilization_memory_percent=20,
                    memory_used_mb=100,
                    memory_total_mb=1000,
                    temperature_c=40,
                    power_draw_watts=50,
                    processes=[],
                )
            ],
            [],
        )
    )
    store.insert_sample(
        Sample(
            new,
            [
                GpuMetric(
                    index=0,
                    uuid="gpu",
                    name="GPU",
                    utilization_gpu_percent=30,
                    utilization_memory_percent=40,
                    memory_used_mb=200,
                    memory_total_mb=1000,
                    temperature_c=45,
                    power_draw_watts=60,
                    processes=[],
                )
            ],
            [],
        )
    )

    store.prune_older_than(15, now=new)

    status = store.latest_status()
    assert status["sampled_at"] == new.isoformat()
    assert len(store.timeseries(old - timedelta(days=1))) == 1


def test_usage_summary_reports_active_seconds_without_double_counting_processes(tmp_path):
    from gpu_watcher.models import Attribution, AttributedProcess, GpuProcess

    store = Store(tmp_path / "watcher.sqlite3")
    store.initialize()
    sampled_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    gpu = GpuMetric(
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
    attribution = Attribution(label="alice", source="test")
    store.insert_sample(
        Sample(
            sampled_at,
            [gpu],
            [
                AttributedProcess(
                    GpuProcess(pid=1, gpu_uuid="gpu", used_memory_mb=128),
                    attribution,
                ),
                AttributedProcess(
                    GpuProcess(pid=2, gpu_uuid="gpu", used_memory_mb=256),
                    attribution,
                ),
            ],
        )
    )

    summary = store.usage_summary(sampled_at - timedelta(minutes=1), 60)

    assert summary[0]["label"] == "alice"
    assert summary[0]["active_seconds"] == 60
    assert summary[0]["avg_process_vram_mb"] == 384
    assert summary[0]["avg_gpu_util_percent"] == 50
