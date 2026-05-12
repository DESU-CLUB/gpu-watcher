from __future__ import annotations

from dataclasses import replace

from .models import GpuMetric, GpuProcess


class NvmlUnavailableError(RuntimeError):
    pass


class NvmlCollector:
    def __init__(self) -> None:
        try:
            import pynvml
        except ImportError as exc:
            raise NvmlUnavailableError(
                "pynvml is not installed. Install with `pip install nvidia-ml-py`."
            ) from exc

        self._nvml = pynvml
        try:
            self._nvml.nvmlInit()
        except self._nvml.NVMLError as exc:
            raise NvmlUnavailableError(f"NVML initialization failed: {exc}") from exc

    def close(self) -> None:
        try:
            self._nvml.nvmlShutdown()
        except Exception:
            pass

    def collect(self) -> list[GpuMetric]:
        device_count = self._nvml.nvmlDeviceGetCount()
        metrics: list[GpuMetric] = []

        for index in range(device_count):
            handle = self._nvml.nvmlDeviceGetHandleByIndex(index)
            uuid = _decode(self._nvml.nvmlDeviceGetUUID(handle))
            name = _decode(self._nvml.nvmlDeviceGetName(handle))
            mem = self._nvml.nvmlDeviceGetMemoryInfo(handle)
            util = self._try(lambda: self._nvml.nvmlDeviceGetUtilizationRates(handle))

            temperature = self._try(
                lambda: self._nvml.nvmlDeviceGetTemperature(
                    handle, self._nvml.NVML_TEMPERATURE_GPU
                )
            )
            power_mw = self._try(lambda: self._nvml.nvmlDeviceGetPowerUsage(handle))
            power_watts = round(power_mw / 1000, 2) if power_mw is not None else None

            processes = self._collect_processes(handle, uuid)

            metrics.append(
                GpuMetric(
                    index=index,
                    uuid=uuid,
                    name=name,
                    utilization_gpu_percent=getattr(util, "gpu", None),
                    utilization_memory_percent=getattr(util, "memory", None),
                    memory_used_mb=int(mem.used / 1024 / 1024),
                    memory_total_mb=int(mem.total / 1024 / 1024),
                    temperature_c=temperature,
                    power_draw_watts=power_watts,
                    processes=processes,
                )
            )

        return metrics

    def enrich_process_details(self, process: GpuProcess) -> GpuProcess:
        try:
            import psutil

            proc = psutil.Process(process.pid)
            username = proc.username()
            command = " ".join(proc.cmdline()) or proc.name()
            return replace(process, user=username, command=command)
        except Exception:
            return process

    def _collect_processes(self, handle: object, gpu_uuid: str) -> list[GpuProcess]:
        processes: list[GpuProcess] = []
        raw_processes = []

        for getter_name in (
            "nvmlDeviceGetComputeRunningProcesses_v3",
            "nvmlDeviceGetComputeRunningProcesses",
        ):
            getter = getattr(self._nvml, getter_name, None)
            if getter is None:
                continue
            try:
                raw_processes = getter(handle)
                break
            except self._nvml.NVMLError:
                continue

        for proc in raw_processes:
            used_memory = getattr(proc, "usedGpuMemory", None)
            used_memory_mb = (
                int(used_memory / 1024 / 1024)
                if used_memory is not None and used_memory > 0
                else None
            )
            enriched = self.enrich_process_details(
                GpuProcess(
                    pid=int(proc.pid),
                    gpu_uuid=gpu_uuid,
                    used_memory_mb=used_memory_mb,
                )
            )
            processes.append(enriched)

        return processes

    def _try(self, fn):
        try:
            return fn()
        except self._nvml.NVMLError:
            return None


def _decode(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
