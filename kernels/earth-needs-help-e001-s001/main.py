#!/usr/bin/env python3
"""Generate Earth Needs Help Episode 001 Shot 001 on Kaggle GPU."""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ASSET_BASE = "https://raw.githubusercontent.com/simplebusiness26/Animation-Factory/main/kernels/earth-needs-help-e001-s001"
WORK = Path("/kaggle/working")
OUTPUT = WORK / "earth-needs-help-e001-s001.mp4"
REPORT = WORK / "earth-needs-help-e001-s001-report.json"


def fetch_text(name: str) -> str:
    with urllib.request.urlopen(f"{ASSET_BASE}/{name}", timeout=60) as response:
        return response.read().decode("utf-8")


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
            "Pillow<12",
        ],
        check=True,
    )


pip_install()

import torch
from PIL import Image, ImageOps
from diffusers import I2VGenXLPipeline
from diffusers.utils import export_to_video


def fetch_still() -> Path:
    encoded = fetch_text("input-still.b64").strip()
    path = WORK / "input-still.jpg"
    path.write_bytes(base64.b64decode(encoded))
    return path


def fit_image(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGB")
    size = (704, 480)
    canvas = Image.new("RGB", size, (10, 10, 18))
    fitted = ImageOps.contain(image, size)
    canvas.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    return canvas


def main() -> int:
    started = time.time()
    report = {
        "show": "Earth Needs Help",
        "episode": "001",
        "shot": "001",
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "success": False,
    }

    try:
        config = json.loads(fetch_text("config.json"))
        prompt = fetch_text("prompt.txt").strip()
        still = fetch_still()
        report["input"] = still.name

        pipeline = I2VGenXLPipeline.from_pretrained(
            "ali-vilab/i2vgen-xl",
            torch_dtype=torch.float16,
            variant="fp16",
        )
        pipeline.enable_model_cpu_offload()
        pipeline.enable_attention_slicing()

        generator = torch.Generator(device="cpu").manual_seed(int(config.get("seed", 1234)))
        frames = pipeline(
            prompt=prompt,
            image=fit_image(still),
            num_inference_steps=35,
            negative_prompt=config.get("negative_prompt", ""),
            guidance_scale=8.0,
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
