#!/usr/bin/env python3
"""Allow-listed GitHub Actions -> Kaggle control bridge for Animation Factory."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
RESULT_FILE = ROOT / "result.md"
COMMAND_FILE = ROOT / "control" / "command.json"
SHOT_TEMPLATE = ROOT / "kernels" / "shot-runner" / "main.py"
KERNEL_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
ALLOWED_ACCELERATORS = {
    "NvidiaTeslaT4",
    "NvidiaTeslaT4Highmem",
    "NvidiaTeslaA100",
    "NvidiaL4",
    "NvidiaL4X1",
    "NvidiaH100",
    "NvidiaRtxPro6000",
    "TpuV38",
    "Tpu1VmV38",
    "TpuV5E8",
    "TpuV6E8",
}
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_MODELS = {"ltx-2b-distilled", "i2vgen-xl", "svd-xt"}


def run(args: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(
        args,
        cwd=str(cwd or ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = proc.stdout.strip()
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(args[:3])}\n{output}")
    return output


def parse_command() -> dict[str, Any]:
    if not COMMAND_FILE.exists():
        raise RuntimeError("control/command.json does not exist")
    value = json.loads(COMMAND_FILE.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Command must be a JSON object")
    return value


def bounded_size(value: Any, default: int = 10, maximum: int = 50) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        size = default
    return max(1, min(size, maximum))


def safe_repo_file(value: Any, *, roots: tuple[str, ...], suffixes: set[str] | None = None) -> Path:
    rel = Path(str(value or "")).as_posix().strip("/")
    if not rel or not any(rel.startswith(root.rstrip("/") + "/") for root in roots):
        raise ValueError(f"Path must be inside one of: {', '.join(roots)}")
    target = (ROOT / rel).resolve()
    if ROOT not in target.parents:
        raise ValueError("Path escapes repository")
    if not target.is_file():
        raise ValueError(f"File not found: {rel}")
    if suffixes and target.suffix.lower() not in suffixes:
        raise ValueError(f"Unsupported file type: {target.suffix}")
    return target


def safe_kernel_ref(value: Any) -> str:
    ref = str(value or "").strip()
    if not KERNEL_RE.fullmatch(ref):
        raise ValueError("kernel must be in owner/slug form")
    return ref


def safe_kernel_dir(value: Any) -> Path:
    rel = Path(str(value or "")).as_posix().strip("/")
    if not rel.startswith("kernels/"):
        raise ValueError("path must be inside kernels/")
    target = (ROOT / rel).resolve()
    kernels_root = (ROOT / "kernels").resolve()
    if kernels_root not in target.parents or not target.is_dir():
        raise ValueError(f"Invalid kernel path: {rel}")
    return target


def render_metadata(folder: Path, owner: str | None) -> dict[str, Any]:
    path = folder / "kernel-metadata.json"
    raw = path.read_text(encoding="utf-8")
    if "__OWNER__" in raw:
        if not owner:
            raise ValueError("KAGGLE_OWNER is not configured")
        raw = raw.replace("__OWNER__", owner)
    metadata = json.loads(raw)
    if not KERNEL_RE.fullmatch(str(metadata.get("id") or "")):
        raise ValueError("Invalid kernel id")
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def validate_shot_job(job: dict[str, Any]) -> dict[str, Any]:
    required = ["show", "episode", "shot", "still_path", "prompt"]
    for key in required:
        if not str(job.get(key) or "").strip():
            raise ValueError(f"Shot job is missing {key}")

    prompt = str(job["prompt"]).strip()
    if len(prompt) > 5000:
        raise ValueError("Shot prompt is too long")
    duration = float(job.get("duration_seconds", 5))
    fps = int(job.get("fps", 8))
    width = int(job.get("width", 832))
    height = int(job.get("height", 480))
    if not (1 <= duration <= 10):
        raise ValueError("duration_seconds must be 1-10")
    if not (4 <= fps <= 24):
        raise ValueError("fps must be 4-24")
    if not (256 <= width <= 1280 and 256 <= height <= 720):
        raise ValueError("Shot dimensions are outside the allowed range")

    model = str(job.get("model") or "ltx-2b-distilled")
    if model not in ALLOWED_MODELS:
        raise ValueError(f"Unsupported model: {model}")
    fallbacks = job.get("fallback_models", ["i2vgen-xl", "svd-xt"])
    if not isinstance(fallbacks, list) or any(str(x) not in ALLOWED_MODELS for x in fallbacks):
        raise ValueError("Invalid fallback_models")
    return job


def build_shot_kernel(job_path: Path, owner: str) -> tuple[Path, str]:
    job = validate_shot_job(json.loads(job_path.read_text(encoding="utf-8")))
    still = safe_repo_file(job["still_path"], roots=("shows",), suffixes=ALLOWED_IMAGE_SUFFIXES)
    job_id = str(job.get("job_id") or f"{job['show']}-{job['episode']}-{job['shot']}").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", job_id).strip("-")[:80]
    if len(slug) < 3 or not SLUG_RE.fullmatch(slug):
        raise ValueError("Could not create a safe Kaggle kernel slug")

    temp_root = Path(tempfile.mkdtemp(prefix="animation-factory-shot-"))
    shutil.copy2(SHOT_TEMPLATE, temp_root / "main.py")
    shutil.copy2(still, temp_root / f"input-still{still.suffix.lower()}")
    (temp_root / "job.json").write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
    metadata = {
        "id": f"{owner}/{slug}",
        "title": f"Animation Factory {job['show']} E{job['episode']} Shot {job['shot']}",
        "code_file": "main.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": True,
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    (temp_root / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return temp_root, metadata["id"]


def execute(command: dict[str, Any]) -> tuple[str, list[str]]:
    action = str(command.get("action") or "").strip()
    request_id = str(command.get("request_id") or "unspecified").strip()
    owner = str(command.get("owner") or os.getenv("KAGGLE_OWNER") or "").strip() or None
    files: list[str] = []

    if action == "idle":
        return f"Bridge is installed. Request ID: `{request_id}`.", files
    if not os.getenv("KAGGLE_API_TOKEN"):
        raise RuntimeError("KAGGLE_API_TOKEN GitHub Actions secret is not configured")

    if action == "ping":
        version = run(["kaggle", "--version"])
        account_check = run(["kaggle", "kernels", "list", "-m", "--page-size", "1"])
        return f"Kaggle authentication is working. Request ID: `{request_id}`.\n\n```text\n{version}\n{account_check[:4000]}\n```", files

    if action in {"search_models", "search_datasets", "search_kernels"}:
        query = str(command.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        size = bounded_size(command.get("limit"))
        noun = {"search_models": "models", "search_datasets": "datasets", "search_kernels": "kernels"}[action]
        out = run(["kaggle", noun, "list", "-s", query, "--page-size", str(size)])
        return f"Kaggle {noun} search for **{query}**:\n\n```text\n{out[:12000]}\n```", files

    if action == "run_shot":
        if not owner:
            raise ValueError("KAGGLE_OWNER is not configured")
        job_path = safe_repo_file(command.get("job_path"), roots=("shows",), suffixes={".json"})
        folder, kernel = build_shot_kernel(job_path, owner)
        try:
            out = run(["kaggle", "kernels", "push", "-p", str(folder), "--accelerator", "NvidiaTeslaT4"])
            status = run(["kaggle", "kernels", "status", kernel])
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        return (
            f"Started Animation Factory shot **{kernel}** from `{job_path.relative_to(ROOT)}`.\n\n"
            f"Push response:\n```text\n{out[:6000]}\n```\n\nCurrent status:\n```text\n{status[:3000]}\n```\n\n"
            f"Use `kernel_status` and then `kernel_output` to return the MP4/report to chat.",
            files,
        )

    if action == "run_kernel":
        folder = safe_kernel_dir(command.get("path"))
        metadata = render_metadata(folder, owner)
        args = ["kaggle", "kernels", "push", "-p", str(folder)]
        accelerator = str(command.get("accelerator") or "").strip()
        if accelerator:
            if accelerator not in ALLOWED_ACCELERATORS:
                raise ValueError(f"Unsupported accelerator: {accelerator}")
            args.extend(["--accelerator", accelerator])
        out = run(args)
        kernel = metadata["id"]
        status = run(["kaggle", "kernels", "status", kernel])
        return f"Started Kaggle kernel **{kernel}**.\n\n```text\n{out[:6000]}\n{status[:3000]}\n```", files

    if action == "kernel_status":
        kernel = safe_kernel_ref(command.get("kernel"))
        out = run(["kaggle", "kernels", "status", kernel])
        return f"Status for **{kernel}**:\n\n```text\n{out[:6000]}\n```", files

    if action == "kernel_files":
        kernel = safe_kernel_ref(command.get("kernel"))
        out = run(["kaggle", "kernels", "files", kernel, "--page-size", "100"])
        return f"Output files for **{kernel}**:\n\n```text\n{out[:12000]}\n```", files

    if action == "kernel_output":
        kernel = safe_kernel_ref(command.get("kernel"))
        slug = kernel.split("/", 1)[1]
        target = ARTIFACTS / slug
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        args = ["kaggle", "kernels", "output", kernel, "-p", str(target), "-o"]
        pattern = str(command.get("file_pattern") or "").strip()
        if pattern:
            if len(pattern) > 200:
                raise ValueError("file_pattern is too long")
            args.extend(["--file-pattern", pattern])
        out = run(args)
        downloaded = [str(p.relative_to(ROOT)) for p in target.rglob("*") if p.is_file()]
        files.extend(downloaded)
        listing = "\n".join(downloaded) if downloaded else "(no files downloaded)"
        return f"Downloaded output for **{kernel}**.\n\n```text\n{out[:6000]}\n```\n\nFiles:\n```text\n{listing[:8000]}\n```", files

    raise ValueError(
        "Unknown action. Supported: idle, ping, search_models, search_datasets, search_kernels, "
        "run_shot, run_kernel, kernel_status, kernel_files, kernel_output"
    )


def main() -> int:
    ARTIFACTS.mkdir(exist_ok=True)
    try:
        command = parse_command()
        message, files = execute(command)
        body = "## ✅ Kaggle Worker\n\n" + message
        if files:
            body += "\n\nDownloaded files are attached to the workflow run as the `kaggle-output` artifact."
        code = 0
    except Exception as exc:
        body = f"## ❌ Kaggle Worker\n\n`{type(exc).__name__}`: {exc}"
        code = 1
    RESULT_FILE.write_text(body + "\n", encoding="utf-8")
    print(body)
    return code


if __name__ == "__main__":
    sys.exit(main())
