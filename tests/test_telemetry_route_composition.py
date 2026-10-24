"""Public telemetry contracts without importing the broker-backed application."""
import ast
import logging
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[1]
GIB = 1024**3
GPU = {"detected": False, "devices": [], "backend": "none"}


def synthetic_state():
    return SimpleNamespace(
        metrics=SimpleNamespace(
            cpu_percent=Mock(return_value=12.34), cpu_count=lambda: 8,
            virtual_memory=lambda: SimpleNamespace(used=3 * GIB, total=8 * GIB, percent=37.5),
            Process=lambda pid: SimpleNamespace(memory_info=lambda: SimpleNamespace(rss=GIB / 4)),
        ),
        cache={"data": None, "timestamp": 0, "ttl": 5},
        gpu=Mock(return_value=GPU.copy()), now=100, status=None,
    )


def composed_app(state):
    """Execute the actual include with synthetic globals, never main imports."""
    from src.platform.api.telemetry_api import create_telemetry_router

    tree = ast.parse((ROOT / "src/platform/api/main.py").read_text())
    includes = [node for node in tree.body if isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "include_router"
                and node.value.args
                and isinstance(node.value.args[0], ast.Call)
                and isinstance(node.value.args[0].func, ast.Name)
                and node.value.args[0].func.id == "create_telemetry_router"]
    assert len(includes) == 1, "Telemetry must be composed through its real router"
    app = FastAPI()
    namespace = dict(
        app=app, create_telemetry_router=create_telemetry_router,
        psutil=state.metrics, _gpu_cache=state.cache,
        _get_gpu_info_cached=state.gpu, ALGO_TYPE=state.status,
        logger=logging.getLogger("telemetry-test"),
        time=SimpleNamespace(time=lambda: state.now), os=os,
    )
    exec(compile(ast.Module(body=includes, type_ignores=[]), "telemetry-composition", "exec"), namespace)

    @app.get("/{path:path}", response_class=HTMLResponse)
    async def fallback(path: str):
        return "synthetic SPA"

    return app, namespace


def test_exact_success_and_live_provider_state():
    state = synthetic_state()
    app, namespace = composed_app(state)
    with TestClient(app) as client:
        assert state.gpu.call_count == 0
        response = client.get("/api/system/telemetry")
        assert response.status_code == 200
        assert response.json() == {
            "cpu": {"usage": 12.3, "count": 8, "label": "CPU (8 Threads)"},
            "memory": {"used": 3.0, "total": 8.0, "app_used": 0.25,
                       "percent": 37.5, "label": "3.0GB / 8.0GB"},
            "gpu": GPU, "status": None,
        }
        assert dict(response.headers) == {"content-length": str(len(response.content)),
                                          "content-type": "application/json"}
        state.metrics.cpu_percent.assert_called_once_with(interval=None)
        assert state.cache == {"data": GPU, "timestamp": 100, "ttl": 5}
        namespace["ALGO_TYPE"] = "training"
        namespace["_gpu_cache"] = {"data": {"detected": True}, "timestamp": 100, "ttl": 5}
        assert client.get("/api/system/telemetry").json()["status"] == "training"
        assert client.get("/api/system/telemetry").json()["gpu"] == {"detected": True}
        assert state.gpu.call_count == 1


def test_cache_strict_ttl_boundary_and_empty_data_refresh():
    state = synthetic_state()
    app, _ = composed_app(state)
    with TestClient(app) as client:
        client.get("/api/system/telemetry")
        state.now = 105
        assert client.get("/api/system/telemetry").json()["gpu"] == GPU
        assert state.gpu.call_count == 1
        state.now = 105.01
        client.get("/api/system/telemetry")
        assert state.gpu.call_count == 2
        assert state.cache["timestamp"] == 105.01
        state.cache["data"] = None
        client.get("/api/system/telemetry")
        assert state.gpu.call_count == 3


@pytest.mark.parametrize("failure", ["metrics", "gpu"])
def test_exact_error_body_and_unchanged_cache(failure):
    state = synthetic_state()
    if failure == "metrics":
        state.metrics.cpu_percent.side_effect = RuntimeError("metrics unavailable")
    else:
        state.gpu.side_effect = RuntimeError("gpu unavailable")
    app, _ = composed_app(state)
    with TestClient(app) as client:
        response = client.get("/api/system/telemetry")
        assert response.status_code == 200
        assert response.json() == {"error": f"{failure} unavailable",
                                   "gpu": {"detected": False, "devices": []}}
        assert state.cache == {"data": None, "timestamp": 0, "ttl": 5}
        assert state.gpu.call_count == (failure == "gpu")


@pytest.mark.parametrize("method", ["post", "put", "delete", "patch", "head", "options"])
def test_unsupported_methods_do_not_sample_or_mutate(method):
    state = synthetic_state()
    app, _ = composed_app(state)
    with TestClient(app) as client:
        response = client.request(method, "/api/system/telemetry")
        assert response.status_code == 405
        assert response.headers["allow"] == "GET"
        assert response.content == (b"" if method == "head" else b'{"detail":"Method Not Allowed"}')
        assert state.cache == {"data": None, "timestamp": 0, "ttl": 5}
        state.metrics.cpu_percent.assert_not_called()
        state.gpu.assert_not_called()


def test_inventory_defaults_query_and_spa_fallback():
    state = synthetic_state()
    app, _ = composed_app(state)
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]
        assert list(paths) == ["/api/system/telemetry", "/{path}"]
        assert set(paths["/api/system/telemetry"]) == {"get"}
        assert "parameters" not in paths["/api/system/telemetry"]["get"]
        assert client.get("/api/system/telemetry?unused=value").json()["status"] is None
        assert client.get("/unknown-page").text == "synthetic SPA"


@pytest.mark.parametrize("torch_mode", ["missing", "cpu", "broken"])
def test_gpu_optional_torch_and_gputil_fallback(monkeypatch, torch_mode):
    import sys
    from src.platform.api.telemetry_api import get_gpu_info

    torch = None if torch_mode == "missing" else SimpleNamespace(
        __version__="synthetic", cuda=SimpleNamespace(is_available=lambda: False))
    if torch_mode == "broken":
        torch.cuda.is_available = Mock(side_effect=RuntimeError("cuda unavailable"))
    monkeypatch.setitem(sys.modules, "torch", torch)
    device = SimpleNamespace(name="synthetic GPU", memoryTotal=8192, memoryUsed=2048,
                             load=0.1234, temperature=None)
    gputil = SimpleNamespace(getGPUs=Mock(return_value=[device]))
    gpu = get_gpu_info(gputil)
    assert gpu["detected"] is True
    assert gpu["backend"] == "gputil"
    assert gpu["cuda"] == {"available": False, "device_name": "synthetic GPU", "count": 1}
    assert gpu["devices"] == [{"name": "synthetic GPU", "memory_total": 8.0,
                               "memory_used": 2.0, "memory_reserved": 2.0,
                               "load": 12.3, "temperature": 0}]
    if torch_mode == "cpu":
        assert gpu["error_detail"] is None
        assert gpu["info"] == "CPU-only mode (torch synthetic)"
    elif torch_mode == "broken":
        assert gpu["error_detail"] == "torch CUDA error: cuda unavailable"
    else:
        assert gpu["error_detail"].startswith("torch no instalado: ")
    gputil.getGPUs.side_effect = RuntimeError("driver unavailable")
    failed = get_gpu_info(gputil)
    assert failed["detected"] is False
    assert failed["devices"] == []
    assert failed["error_detail"].endswith(" | GPUtil error: driver unavailable")


@pytest.mark.parametrize("nvml_available", [True, False])
def test_cuda_precedes_gputil_and_retains_nvml_or_reserved_memory_load(monkeypatch, nvml_available):
    import sys
    from src.platform.api.telemetry_api import get_gpu_info

    cuda = SimpleNamespace(
        is_available=lambda: True, device_count=lambda: 1,
        get_device_name=lambda i: "synthetic CUDA",
        get_device_properties=lambda i: SimpleNamespace(name="synthetic CUDA", total_memory=8 * GIB),
        memory_allocated=lambda i: GIB, memory_reserved=lambda i: 2 * GIB,
    )
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=cuda))
    nvml = SimpleNamespace(
        nvmlInit=lambda: None, nvmlDeviceGetCount=lambda: 1,
        nvmlDeviceGetHandleByIndex=lambda i: i,
        nvmlDeviceGetUtilizationRates=lambda handle: SimpleNamespace(gpu=62.34),
        nvmlDeviceGetTemperature=lambda handle, kind: 45, NVML_TEMPERATURE_GPU=0,
    )
    monkeypatch.setitem(sys.modules, "pynvml", nvml if nvml_available else None)
    gputil = SimpleNamespace(getGPUs=Mock())
    assert get_gpu_info(gputil) == {
        "detected": True, "backend": "torch_cuda", "error_detail": None,
        "cuda": {"available": True, "device_name": "synthetic CUDA", "count": 1},
        "devices": [{"name": "synthetic CUDA", "memory_total": 8.0,
                     "memory_used": 1.0, "memory_reserved": 2.0,
                     "load": 62.3 if nvml_available else 25.0,
                     "temperature": 45 if nvml_available else 0}],
    }
    gputil.getGPUs.assert_not_called()
