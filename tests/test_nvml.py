import sys
from types import SimpleNamespace

from gpu_watcher.nvml import NvmlCollector


class FakeNvml:
    class NVMLError(Exception):
        pass

    NVML_TEMPERATURE_GPU = 0

    def __init__(self):
        self.shutdown = False

    def nvmlInit(self):
        return None

    def nvmlShutdown(self):
        self.shutdown = True

    def nvmlDeviceGetCount(self):
        return 1

    def nvmlDeviceGetHandleByIndex(self, index):
        return f"handle-{index}"

    def nvmlDeviceGetUUID(self, handle):
        return b"GPU-test"

    def nvmlDeviceGetName(self, handle):
        return b"Test GPU"

    def nvmlDeviceGetMemoryInfo(self, handle):
        return SimpleNamespace(used=512 * 1024 * 1024, total=1024 * 1024 * 1024)

    def nvmlDeviceGetUtilizationRates(self, handle):
        return SimpleNamespace(gpu=50, memory=25)

    def nvmlDeviceGetTemperature(self, handle, sensor):
        return 61

    def nvmlDeviceGetPowerUsage(self, handle):
        return 80000

    def nvmlDeviceGetComputeRunningProcesses_v3(self, handle):
        return [SimpleNamespace(pid=123, usedGpuMemory=128 * 1024 * 1024)]


def test_nvml_collector_reads_metrics(monkeypatch):
    fake = FakeNvml()
    monkeypatch.setitem(sys.modules, "pynvml", fake)

    collector = NvmlCollector()
    collector.enrich_process_details = lambda process: process
    metrics = collector.collect()
    collector.close()

    assert metrics[0].uuid == "GPU-test"
    assert metrics[0].name == "Test GPU"
    assert metrics[0].utilization_gpu_percent == 50
    assert metrics[0].memory_used_mb == 512
    assert metrics[0].temperature_c == 61
    assert metrics[0].power_draw_watts == 80
    assert metrics[0].processes[0].pid == 123
    assert metrics[0].processes[0].used_memory_mb == 128
    assert fake.shutdown is True
