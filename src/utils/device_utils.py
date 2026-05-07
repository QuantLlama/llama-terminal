try:
    import torch
    HAS_TORCH = True
except (ImportError, OSError):
    HAS_TORCH = False
    torch = None
import logging
import sys

logger = logging.getLogger(__name__)

def get_best_device():
    """
    Returns the best available device, testing CUDA compatibility.
    Catches errors where is_available() is True but the hardware/build is incompatible.
    """
    if not HAS_TORCH or torch is None:
        return "cpu"

    if torch.cuda.is_available():
        try:
            # Test actual computation to catch 'no kernel image' error
            a = torch.tensor([1.0]).cuda()
            b = torch.tensor([1.0]).cuda()
            c = a + b
            del a, b, c
            return torch.device("cuda")
        except Exception as e:
            print(f"\n[DEVICE_CHECK] CUDA detectado pero incompatible (error kernel/compute): {e}")
            print("[DEVICE_CHECK] Cambiando automáticamente a CPU para estabilidad.\n")
            logger.warning(f"CUDA is available but testing failed: {e}")
            
    return torch.device("cpu")
