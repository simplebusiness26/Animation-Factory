#!/usr/bin/env python3
"""Generate Earth Needs Help Episode 001 Shot 001 on Kaggle GPU."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


def pip_install() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-q",
            "-U",
            "diffusers",
            "transformers",
            "accelerate",
            "safetensors",
            "imageio[ffmpeg]",
            "Pillow",
        ],
        check=True,
    )


pip_install()

import torch
from PIL import Image, ImageOps
from diffusers import I2VGenXLPipeline
from diffusers.utils import export_to_video

ROOT = Path(__file__).resolve().parent
WORK = Path("/kaggle/working")
OUTPUT = WORK / "earth-needs-help-e001-s001.mp4"
REPORT = WORK / "earth-needs-help-e001-s001-report.json"


def find_still() -> Path:
    for name in ("input-still.jpg", "input-still.jpeg", "input-still.png"):
        path = ROOT / name
        if path.exists():
            return path
    raise FileNotFoundError("Shot still not found in kernel bundle")


def fit_image(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGB")
    size = (704, 480)
    canvas = Image.new("RGB", size, (10, 10, 18))
    fitted = ImageOps.contain(image, size)
    canvas.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    return canvas


def main() -> int:
    started = time.time()
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    prompt = (ROOT / "prompt.txt").read_text(encoding="utf-8").strip()
    still = find_still()

    report = {
        "show": "Earth Needs Help",
        "episode": "001",
        "shot": "001",
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "input": still.name,
        "success": False,
    }

    try:
        pipeline = I2VGenXLPipeline.from_pretrained(
            "ali-vilab/i2vgen-xl",
            torch_dtype=torch.float16,
            variant="fp16",
        )
        pipeline.enable_model_cpu_offload()
        pipeline.enable_attention_slicing()

        generator = torch.manual_seed(int(config.get("seed", 1234)))
        frames = pipeline(
            prompt=prompt,
            image=fit_image(still),
            num_inference_steps=50,
            negative_prompt=config.get("negative_prompt", ""),
            guidance_scale=9.0,
            generator=generator,
        ).frames[0]

        export_to_video(frames, str(OUTPUT), fps=8)
        report.update(
            {
                "success": True,
                "backend": "ali-vilab/i2vgen-xl",
                "frames": len(frames),
                "output": OUTPUT.name,
            }
        )
        return_code = 0
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        return_code = 1

    report["elapsed_seconds"] = round(time.time() - started, 2)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
