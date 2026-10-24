"""System telemetry routes over application-owned providers and GPU cache."""
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter


def get_gpu_info(GPUtil: Any) -> dict:
    """Detect CUDA devices, retaining the optional NVML and GPUtil fallbacks."""
    gpu_data = {
        "detected": False,
        "devices": [],
        "cuda": {"available": False, "device_name": None, "count": 0},
        "backend": "none",
        "error_detail": None,
    }
    try:
        import torch
        if torch.cuda.is_available():
            gpu_data["cuda"]["available"] = True
            gpu_data["cuda"]["count"] = torch.cuda.device_count()
            gpu_data["cuda"]["device_name"] = torch.cuda.get_device_name(0)
            gpu_data["detected"] = True
            gpu_data["backend"] = "torch_cuda"
            nvml_loads = {}
            try:
                import pynvml
                pynvml.nvmlInit()
                for i in range(pynvml.nvmlDeviceGetCount()):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    nvml_loads[i] = util.gpu
            except Exception:
                pass
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                mem_allocated = torch.cuda.memory_allocated(i) / (1024**3)
                mem_reserved = torch.cuda.memory_reserved(i) / (1024**3)
                mem_total = props.total_memory / (1024**3)
                real_load = nvml_loads.get(i)
                if real_load is not None:
                    load_pct = round(float(real_load), 1)
                else:
                    load_pct = round((mem_reserved / mem_total) * 100, 1) if mem_total > 0 else 0
                temp = 0
                try:
                    import pynvml
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                except Exception:
                    pass
                gpu_data["devices"].append({
                    "name": props.name,
                    "memory_total": round(mem_total, 2),
                    "memory_used": round(mem_allocated, 2),
                    "memory_reserved": round(mem_reserved, 2),
                    "load": load_pct,
                    "temperature": temp,
                })
            return gpu_data
        else:
            gpu_data["error_detail"] = None
            gpu_data["info"] = f"CPU-only mode (torch {torch.__version__})"
    except ImportError as e:
        gpu_data["error_detail"] = f"torch no instalado: {e}"
    except Exception as e:
        gpu_data["error_detail"] = f"torch CUDA error: {e}"
    try:
        gpus = GPUtil.getGPUs()
        if gpus:
            gpu_data["detected"] = True
            gpu_data["backend"] = "gputil"
            gpu_data["cuda"]["device_name"] = gpus[0].name
            gpu_data["cuda"]["count"] = len(gpus)
            for gpu in gpus:
                mem_total = gpu.memoryTotal / 1024
                mem_used = gpu.memoryUsed / 1024
                gpu_data["devices"].append({
                    "name": gpu.name,
                    "memory_total": round(mem_total, 2),
                    "memory_used": round(mem_used, 2),
                    "memory_reserved": round(mem_used, 2),
                    "load": round(gpu.load * 100, 1),
                    "temperature": gpu.temperature if gpu.temperature else 0,
                })
    except Exception as e:
        prev = gpu_data.get("error_detail") or ""
        gpu_data["error_detail"] = f"{prev} | GPUtil error: {e}"
    return gpu_data


def create_telemetry_router(
    *,
    metrics_provider: Callable[[], Any],
    gpu_provider: Callable[[], dict],
    cache_provider: Callable[[], dict],
    status_provider: Callable[[], Any],
    clock: Callable[[], float],
    process_id: Callable[[], int],
    logger: Any,
) -> APIRouter:
    """Bind live application state without owning startup or cache lifecycle."""
    router = APIRouter()

    @router.get("/api/system/telemetry")
    async def get_system_telemetry():
        try:
            psutil = metrics_provider()
            cpu_usage = psutil.cpu_percent(interval=None)
            cpu_count = psutil.cpu_count()
            vm = psutil.virtual_memory()
            memory_used_gb = vm.used / (1024**3)
            memory_total_gb = vm.total / (1024**3)
            process = psutil.Process(process_id())
            app_memory_gb = process.memory_info().rss / (1024**3)
            _gpu_cache = cache_provider()
            current_time = clock()
            if (
                current_time - _gpu_cache["timestamp"] > _gpu_cache["ttl"]
                or _gpu_cache["data"] is None
            ):
                gpu_data = gpu_provider()
                _gpu_cache["data"] = gpu_data
                _gpu_cache["timestamp"] = current_time
                if not gpu_data.get("detected"):
                    logger.debug("[TELEMETRY] No GPU detected — running in CPU-only mode")
                elif gpu_data.get("detected"):
                    logger.info(f"[TELEMETRY] GPU detectada via '{gpu_data.get('backend')}': {gpu_data['cuda'].get('device_name')}")
            else:
                gpu_data = _gpu_cache["data"]
            return {
                "cpu": {
                    "usage": round(cpu_usage, 1),
                    "count": cpu_count,
                    "label": f"CPU ({cpu_count} Threads)",
                },
                "memory": {
                    "used": round(memory_used_gb, 1),
                    "total": round(memory_total_gb, 1),
                    "app_used": round(app_memory_gb, 2),
                    "percent": vm.percent,
                    "label": f"{round(memory_used_gb, 1)}GB / {round(memory_total_gb, 1)}GB",
                },
                "gpu": gpu_data,
                "status": status_provider(),
            }
        except Exception as e:
            return {"error": str(e), "gpu": {"detected": False, "devices": []}}

    return router
