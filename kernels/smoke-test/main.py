import json
import platform
import subprocess
from pathlib import Path

report = {
    "ok": True,
    "python": platform.python_version(),
    "gpu_available": False,
    "gpu_name": None,
}

try:
    import torch

    report["torch"] = torch.__version__
    report["gpu_available"] = bool(torch.cuda.is_available())
    if report["gpu_available"]:
        report["gpu_name"] = torch.cuda.get_device_name(0)
except Exception as exc:
    report["torch_error"] = f"{type(exc).__name__}: {exc}"

try:
    report["nvidia_smi"] = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    ).stdout.strip()
except Exception as exc:
    report["nvidia_smi_error"] = f"{type(exc).__name__}: {exc}"

output = Path("/kaggle/working/animation-factory-smoke-test.json")
output.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
print(f"Wrote {output}")
