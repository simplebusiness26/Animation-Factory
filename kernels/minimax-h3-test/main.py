#!/usr/bin/env python3
"""MiniMax H3 isolated Kaggle experiment using the public ComfyUI T4 route.

Animation Factory embeds the approved shot metadata and starting still directly
into this script. The runner downloads only the public quantized FL2VA assets
needed for a small image-to-video smoke test and writes a report even on failure.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request
from pathlib import Path

EMBEDDED_JOB_JSON = None
EMBEDDED_STILL_B64 = None
EMBEDDED_STILL_SUFFIX = ".png"

WORK = Path("/kaggle/working")
RUN_ROOT = Path("/kaggle/temp/minimax-h3-public")
COMFY = RUN_ROOT / "ComfyUI"
HF_CACHE = RUN_ROOT / "hf-cache"
COMFY_OUTPUT = RUN_ROOT / "output"
COMFY_TEMP = RUN_ROOT / "temp"
REPORT = WORK / "minimax-h3-report.json"
OUTPUT = WORK / "minimax-h3-test.mp4"
COMFY_LOG = WORK / "minimax-h3-comfyui.log"


def load_job() -> dict:
    if not EMBEDDED_JOB_JSON:
        raise RuntimeError("MiniMax job was not embedded by Animation Factory")
    value = json.loads(EMBEDDED_JOB_JSON)
    if not isinstance(value, dict):
        raise RuntimeError("Embedded MiniMax job is not a JSON object")
    return value


JOB = load_job()


def run(args: list[str], cwd: Path | None = None, timeout: int | None = None) -> str:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=timeout,
    )
    out = proc.stdout or ""
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(args[:4])}\n{out[-8000:]}"
        )
    return out


def report(**extra):
    data = {
        "success": False,
        "provider": "kaggle",
        "backend": "minimax-h3-comfyui-public",
        "model_repo": "Comfy-Org/MiniMax-H3",
        "turbo_repo": "lightx2v/Minimax-h3-Turbo",
        "show": JOB.get("show"),
        "episode": JOB.get("episode"),
        "shot": JOB.get("shot"),
        "seed": JOB.get("seed"),
        "requested_duration_seconds": JOB.get("duration_seconds"),
        "fps": 24,
        **extra,
    }
    REPORT.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


def find_still() -> Path:
    if not EMBEDDED_STILL_B64:
        raise RuntimeError("Approved starting still was not embedded")
    suffix = str(EMBEDDED_STILL_SUFFIX or ".png").lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise RuntimeError(f"Unsupported still type: {suffix}")
    target = WORK / f"minimax-input-still{suffix}"
    target.write_bytes(base64.b64decode(EMBEDDED_STILL_B64, validate=True))
    return target


def install_comfyui():
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    if not (COMFY / ".git").exists():
        run([
            "git", "clone", "--depth", "1", "--branch", "v0.30.1",
            "https://github.com/comfyanonymous/ComfyUI.git", str(COMFY),
        ], timeout=600)

    run([
        sys.executable, "-m", "pip", "install", "-q", "--upgrade",
        "huggingface_hub", "hf_xet",
    ], timeout=600)
    run([
        sys.executable, "-m", "pip", "install", "-q", "-r",
        str(COMFY / "requirements.txt"),
    ], timeout=1200)


def link_model(repo: str, filename: str, target: Path) -> int:
    from huggingface_hub import hf_hub_download

    target.parent.mkdir(parents=True, exist_ok=True)
    cached = Path(hf_hub_download(
        repo_id=repo,
        filename=filename,
        cache_dir=str(HF_CACHE),
    ))
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(cached)
    return cached.stat().st_size


def prepare_models() -> dict:
    os.environ["HF_HOME"] = str(HF_CACHE)
    os.environ["HF_XET_HIGH_PERFORMANCE"] = "1"

    free = shutil.disk_usage("/kaggle/temp").free
    if free < 44 * 1024**3:
        raise RuntimeError(
            f"MiniMax public T4 route needs about 44 GiB free disk; only {free / 1024**3:.1f} GiB available"
        )

    specs = [
        (
            "Comfy-Org/MiniMax-H3",
            "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
            COMFY / "models/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        ),
        (
            "Comfy-Org/MiniMax-H3",
            "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
            COMFY / "models/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        ),
        (
            "Comfy-Org/MiniMax-H3",
            "vae/minimax_h3_video_vae_fp16.safetensors",
            COMFY / "models/vae/minimax_h3_video_vae_fp16.safetensors",
        ),
        (
            "Comfy-Org/MiniMax-H3",
            "vae/minimax_h3_audio_vae_fp32.safetensors",
            COMFY / "models/vae/minimax_h3_audio_vae_fp32.safetensors",
        ),
        (
            "lightx2v/Minimax-h3-Turbo",
            "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
            COMFY / "models/loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
        ),
    ]
    sizes = {}
    for repo, filename, target in specs:
        sizes[target.name] = link_model(repo, filename, target)
    return sizes


def request_json(url: str, payload: dict | None = None, timeout: int = 60):
    if payload is None:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8"))
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def wait_for_server(proc: subprocess.Popen, timeout_seconds: int = 240):
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"ComfyUI exited early with code {proc.returncode}. Log tail:\n{log_tail()}"
            )
        try:
            return request_json("http://127.0.0.1:8188/system_stats", timeout=5)
        except Exception as exc:
            last = exc
            time.sleep(3)
    raise RuntimeError(f"ComfyUI did not start: {last}. Log tail:\n{log_tail()}")


def log_tail() -> str:
    try:
        return COMFY_LOG.read_text(encoding="utf-8", errors="replace")[-12000:]
    except Exception:
        return "(ComfyUI log unavailable)"


def build_prompt(still_name: str) -> tuple[dict, int, int, int]:
    # First test deliberately uses the public Kaggle notebook's low-resolution
    # recommendation. Once this proves the path, quality can be raised.
    width, height = 608, 352
    duration = min(5.0, max(4.0, float(JOB.get("duration_seconds", 5))))
    raw_frames = round(duration * 24)
    frames = raw_frames + (5 - (raw_frames % 17)) % 17
    seed = int(JOB.get("seed", 6100))
    prompt = str(JOB.get("prompt") or "").strip()
    if not prompt:
        raise RuntimeError("MiniMax prompt is empty")

    graph = {
        "1": {"class_type": "LoadImage", "inputs": {"image": still_name}},
        "2": {"class_type": "VAELoader", "inputs": {
            "vae_name": "minimax_h3_video_vae_fp16.safetensors"
        }},
        "3": {"class_type": "VAELoader", "inputs": {
            "vae_name": "minimax_h3_audio_vae_fp32.safetensors"
        }},
        "4": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
            "type": "minimax",
            "device": "default"
        }},
        "5": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
            "weight_dtype": "default"
        }},
        "6": {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": ["5", 0],
            "lora_name": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
            "strength_model": 1.0
        }},
        "7": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {
            "clip": ["4", 0],
            "vae": ["2", 0],
            "first_frame": ["1", 0],
            "prompt": prompt,
            "width": width,
            "height": height,
            "length": frames
        }},
        "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "9": {"class_type": "BasicGuider", "inputs": {
            "model": ["6", 0],
            "conditioning": ["7", 0]
        }},
        "10": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "11": {"class_type": "BasicScheduler", "inputs": {
            "model": ["6", 0],
            "scheduler": "simple",
            "steps": 8,
            "denoise": 1.0
        }},
        "12": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["8", 0],
            "guider": ["9", 0],
            "sampler": ["10", 0],
            "sigmas": ["11", 0],
            "latent_image": ["7", 1]
        }},
        "13": {"class_type": "VAEDecode", "inputs": {
            "samples": ["12", 0],
            "vae": ["2", 0]
        }},
        "14": {"class_type": "VAEDecodeAudio", "inputs": {
            "samples": ["12", 0],
            "vae": ["3", 0]
        }},
        "15": {"class_type": "CreateVideo", "inputs": {
            "images": ["13", 0],
            "audio": ["14", 0],
            "fps": 24
        }},
        "16": {"class_type": "SaveVideo", "inputs": {
            "video": ["15", 0],
            "filename_prefix": f"minimax-h3-e001-s{JOB.get('shot', '001')}",
            "format": "auto",
            "codec": "auto"
        }},
    }
    return graph, width, height, frames


def verify_nodes():
    info = request_json("http://127.0.0.1:8188/object_info", timeout=30)
    required = {
        "LoadImage", "VAELoader", "CLIPLoader", "UNETLoader",
        "LoraLoaderModelOnly", "MiniMaxH3ImageToVideo", "RandomNoise",
        "BasicGuider", "KSamplerSelect", "BasicScheduler",
        "SamplerCustomAdvanced", "VAEDecode", "VAEDecodeAudio",
        "CreateVideo", "SaveVideo",
    }
    missing = sorted(required.difference(info))
    if missing:
        raise RuntimeError("ComfyUI is missing required MiniMax H3 nodes: " + ", ".join(missing))


def wait_for_prompt(prompt_id: str, proc: subprocess.Popen, timeout_seconds: int = 5 * 60 * 60):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"ComfyUI exited during render with code {proc.returncode}. Log tail:\n{log_tail()}"
            )
        try:
            history = request_json(
                f"http://127.0.0.1:8188/history/{prompt_id}", timeout=15
            )
            if prompt_id in history:
                entry = history[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError(
                        "ComfyUI render failed: " + json.dumps(status, default=str)[-8000:]
                    )
                if entry.get("outputs"):
                    return entry
        except RuntimeError:
            raise
        except Exception:
            pass
        time.sleep(15)
    raise RuntimeError("Timed out waiting for MiniMax H3 render")


def collect_video() -> Path:
    videos = []
    for suffix in ("*.mp4", "*.webm", "*.mov", "*.mkv"):
        videos.extend(COMFY_OUTPUT.rglob(suffix))
    videos = [p for p in videos if p.is_file()]
    if not videos:
        raise RuntimeError("ComfyUI finished but produced no video file")
    latest = max(videos, key=lambda p: p.stat().st_mtime)
    shutil.copy2(latest, OUTPUT)
    return latest


def main():
    started = time.time()
    proc = None
    gpu_names = []
    try:
        import torch
        gpu_names = [
            torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())
        ]

        install_comfyui()
        model_sizes = prepare_models()

        still = find_still()
        input_dir = COMFY / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        still_name = f"animation-factory-e001-s{JOB.get('shot', '001')}{still.suffix.lower()}"
        shutil.copy2(still, input_dir / still_name)

        COMFY_OUTPUT.mkdir(parents=True, exist_ok=True)
        COMFY_TEMP.mkdir(parents=True, exist_ok=True)

        log_handle = COMFY_LOG.open("w", encoding="utf-8")
        cmd = [
            sys.executable, "main.py",
            "--listen", "127.0.0.1",
            "--port", "8188",
            "--lowvram",
            "--preview-method", "none",
            "--output-directory", str(COMFY_OUTPUT),
            "--temp-directory", str(COMFY_TEMP),
            "--reserve-vram", "0.5",
        ]
        proc = subprocess.Popen(
            cmd,
            cwd=str(COMFY),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
            text=True,
        )
        stats = wait_for_server(proc)
        verify_nodes()

        graph, width, height, frames = build_prompt(still_name)
        submitted = request_json(
            "http://127.0.0.1:8188/prompt",
            {"prompt": graph, "client_id": "animation-factory-minimax"},
            timeout=60,
        )
        prompt_id = str(submitted.get("prompt_id") or "")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI did not return prompt_id: {submitted}")

        wait_for_prompt(prompt_id, proc)
        source_video = collect_video()

        report(
            success=True,
            stage="completed",
            gpu_count=len(gpu_names),
            gpu_names=gpu_names,
            width=width,
            height=height,
            num_frames=frames,
            turbo_steps=8,
            native_audio=True,
            model_files={k: round(v / 1024**3, 3) for k, v in model_sizes.items()},
            prompt_id=prompt_id,
            source_video=str(source_video),
            output=str(OUTPUT),
            runtime_seconds=round(time.time() - started, 2),
            comfy_system_stats=stats,
        )
        print(REPORT.read_text(encoding="utf-8"))
    except Exception as exc:
        report(
            success=False,
            stage="failed",
            gpu_count=len(gpu_names),
            gpu_names=gpu_names,
            error_type=type(exc).__name__,
            error=str(exc),
            runtime_seconds=round(time.time() - started, 2),
            comfy_log_tail=log_tail(),
            traceback=traceback.format_exc()[-14000:],
        )
        print(REPORT.read_text(encoding="utf-8"))
        raise
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()


if __name__ == "__main__":
    main()
