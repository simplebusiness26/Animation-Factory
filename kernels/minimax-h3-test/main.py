#!/usr/bin/env python3
"""MiniMax H3 isolated image-to-video experiment for Animation Factory.

The Kaggle CLI turns the configured code file into /kaggle/src/script.py and
may not preserve arbitrary sibling files beside it. To make the experiment
reliable, minimax_worker.py embeds the approved shot job and still directly in
this script before upload. File-based lookup remains as a development fallback.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

# These three values are rendered by minimax_worker.py in the temporary kernel
# copy. Keep the exact assignment text because the worker replaces it safely.
EMBEDDED_JOB_JSON = None
EMBEDDED_STILL_B64 = None
EMBEDDED_STILL_SUFFIX = ".png"

ROOT = Path(__file__).resolve().parent
WORK = Path("/kaggle/working")
REPORT = WORK / "minimax-h3-report.json"
OUTPUT = WORK / "minimax-h3-test.mp4"


def load_job() -> dict:
    if EMBEDDED_JOB_JSON:
        value = json.loads(EMBEDDED_JOB_JSON)
        if not isinstance(value, dict):
            raise RuntimeError("Embedded MiniMax job is not a JSON object")
        return value

    candidates = [
        ROOT / "job.json",
        Path.cwd() / "job.json",
        WORK / "job.json",
        Path("/kaggle/src/job.json"),
    ]
    for path in candidates:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError("MiniMax job.json was not embedded and was not found in Kaggle runtime paths")


JOB = load_job()


def sh(args: list[str]) -> str:
    proc = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(args[:3])}\n{proc.stdout[-5000:]}")
    return proc.stdout


def write_report(**extra):
    data = {
        "success": False,
        "experiment": JOB.get("experiment"),
        "provider": "kaggle",
        "backend": "minimax-h3",
        "model_repo": JOB.get("model_repo"),
        "workflow": JOB.get("workflow"),
        "show": JOB.get("show"),
        "episode": JOB.get("episode"),
        "shot": JOB.get("shot"),
        "seed": JOB.get("seed"),
        "fps": 24,
        "num_frames": JOB.get("num_frames"),
        **extra,
    }
    REPORT.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


def install_runtime():
    sh([
        sys.executable, "-m", "pip", "install", "-q", "--upgrade",
        "git+https://github.com/huggingface/diffusers.git",
        "transformers", "accelerate", "safetensors", "sentencepiece",
        "huggingface_hub", "imageio", "imageio-ffmpeg", "pillow",
    ])


def find_still() -> Path:
    if EMBEDDED_STILL_B64:
        suffix = str(EMBEDDED_STILL_SUFFIX or ".png")
        if suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise RuntimeError(f"Unsupported embedded still suffix: {suffix}")
        target = WORK / f"minimax-input-still{suffix.lower()}"
        target.write_bytes(base64.b64decode(EMBEDDED_STILL_B64, validate=True))
        return target

    roots = [ROOT, Path.cwd(), WORK, Path("/kaggle/src")]
    for root in roots:
        for name in ("input-still.png", "input-still.jpg", "input-still.jpeg", "input-still.webp"):
            path = root / name
            if path.is_file():
                return path
    raise FileNotFoundError("No embedded or file-based input still was supplied to the MiniMax Kaggle kernel")


def main():
    started = time.time()
    gpu_count = 0
    gpu_name = "none"
    try:
        install_runtime()
        import torch
        from diffusers import ModularPipeline
        from diffusers.utils import load_image
        from diffusers.utils.export_utils import encode_video

        gpu_count = torch.cuda.device_count()
        if gpu_count < 1:
            raise RuntimeError("CUDA GPU is required for the MiniMax H3 experiment")
        gpu_name = ", ".join(torch.cuda.get_device_name(i) for i in range(gpu_count))

        still = find_still()
        image = load_image(str(still))
        image.thumbnail((960, 544))
        width = max(256, (image.width // 32) * 32)
        height = max(256, (image.height // 32) * 32)
        image = image.resize((width, height))

        model_repo = str(JOB.get("model_repo") or "ewin-reg/MiniMax-H3-Turbo-FP8-ComfyUI")
        prompt = str(JOB["prompt"])
        seed = int(JOB.get("seed", 6100))
        frames = int(JOB.get("num_frames", 124))

        load_errors = []
        pipe = None
        try:
            pipe = ModularPipeline.from_pretrained(
                model_repo,
                subfolder="FL2VA",
                torch_dtype=torch.bfloat16,
                device_map="balanced" if gpu_count > 1 else None,
            )
        except Exception as exc:
            load_errors.append(f"packaged loader: {type(exc).__name__}: {exc}")

        if pipe is None:
            try:
                pipe = ModularPipeline.from_pretrained(model_repo, workflow="fl2va")
                try:
                    pipe.load_components(dtype=torch.bfloat16, device_map="balanced" if gpu_count > 1 else None)
                except TypeError:
                    pipe.load_components(dtype=torch.bfloat16)
            except Exception as exc:
                load_errors.append(f"modular loader: {type(exc).__name__}: {exc}")
                raise RuntimeError("MiniMax H3 model could not be loaded: " + " | ".join(load_errors))

        if gpu_count == 1:
            offload = getattr(pipe, "enable_sequential_cpu_offload", None)
            if callable(offload):
                offload()
            else:
                to = getattr(pipe, "to", None)
                if callable(to):
                    to("cuda")

        generator = torch.Generator(device="cpu").manual_seed(seed)
        kwargs = {
            "prompt": prompt,
            "image": image,
            "num_frames": frames,
            "generator": generator,
            "output": ["videos", "audio", "sampling_rate"],
        }
        results = pipe(**kwargs)

        videos = results["videos"] if isinstance(results, dict) else results.videos
        audio = results.get("audio") if isinstance(results, dict) else getattr(results, "audio", None)
        sampling_rate = results.get("sampling_rate") if isinstance(results, dict) else getattr(results, "sampling_rate", None)

        encode_kwargs = {"fps": 24, "output_path": str(OUTPUT)}
        if audio is not None and sampling_rate is not None:
            encode_kwargs.update(audio=audio[0], audio_sample_rate=int(sampling_rate))
        encode_video(videos[0], **encode_kwargs)

        write_report(
            success=True,
            gpu_count=gpu_count,
            gpu_name=gpu_name,
            width=width,
            height=height,
            runtime_seconds=round(time.time() - started, 2),
            output=str(OUTPUT),
            native_audio=audio is not None,
            loader_warnings=load_errors,
        )
        print(REPORT.read_text(encoding="utf-8"))
    except Exception as exc:
        write_report(
            success=False,
            gpu_count=gpu_count,
            gpu_name=gpu_name,
            runtime_seconds=round(time.time() - started, 2),
            error_type=type(exc).__name__,
            error=str(exc),
            traceback=traceback.format_exc()[-12000:],
        )
        print(REPORT.read_text(encoding="utf-8"))
        raise


if __name__ == "__main__":
    main()
