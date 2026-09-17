#!/usr/bin/env python3
"""Isolated MiniMax H3 experiment bridge.

This deliberately does not modify the production shot runner. It reuses the
existing Kaggle credentials/CLI bridge, packages one approved Episode 001 still
and its motion prompt, and submits a dedicated MiniMax H3 test kernel.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import worker

ROOT = Path(__file__).resolve().parent
COMMAND_FILE = ROOT / "control" / "minimax-command.json"
TEMPLATE = ROOT / "kernels" / "minimax-h3-test" / "main.py"
MOTION_JOB = ROOT / "shows" / "earth-needs-help" / "episodes" / "001-great-earth-emergency" / "episode001-motion-job.json"
STILLS_DIR = ROOT / "shows" / "earth-needs-help" / "episodes" / "001-great-earth-emergency" / "assets" / "stills"


def parse_command() -> dict[str, Any]:
    value = json.loads(COMMAND_FILE.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("MiniMax command must be a JSON object")
    return value


def resolve_owner(explicit: Any = None) -> str:
    """Resolve the Kaggle owner without requiring a separate repo variable.

    Modern `KAGGLE_API_TOKEN` auth does not necessarily expose a username env
    variable. If no owner is configured, infer it from the authenticated user's
    existing kernel list. Animation Factory already has Kaggle kernels, making
    this a reliable zero-touch fallback for the current bridge.
    """
    configured = str(explicit or os.getenv("KAGGLE_OWNER") or os.getenv("KAGGLE_USERNAME") or "").strip()
    if configured:
        return configured
    listing = worker.run(["kaggle", "kernels", "list", "-m", "--page-size", "20"])
    matches = re.findall(r"\b([A-Za-z0-9_.-]+)/[A-Za-z0-9_.-]+\b", listing)
    if not matches:
        raise ValueError("Could not infer Kaggle owner from the authenticated account")
    return matches[0]


def _shot_record(shot_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    motion = json.loads(MOTION_JOB.read_text(encoding="utf-8"))
    for shot in motion.get("shots", []):
        if str(shot.get("id")) == shot_id:
            return motion, shot
    raise ValueError(f"Unknown Episode 001 shot: {shot_id}")


def _build_kernel(shot_id: str, owner: str) -> tuple[Path, str]:
    motion, shot = _shot_record(shot_id)
    still_name = Path(str(shot["still"])).name
    still = (STILLS_DIR / still_name).resolve()
    if STILLS_DIR.resolve() not in still.parents or not still.is_file():
        raise ValueError(f"Approved still not found: {still_name}")

    temp_root = Path(tempfile.mkdtemp(prefix="animation-factory-minimax-h3-"))
    shutil.copy2(TEMPLATE, temp_root / "main.py")
    shutil.copy2(still, temp_root / f"input-still{still.suffix.lower()}")

    duration = max(2.0, min(float(shot.get("duration_seconds", 5)), 15.0))
    requested = max(22, round(duration * 24))
    n = max(1, round((requested - 5) / 17))
    num_frames = 17 * n + 5

    job = {
        "show": motion.get("show"),
        "episode": motion.get("episode"),
        "shot": shot_id,
        "prompt": shot.get("prompt"),
        "seed": int(shot.get("seed", 6100)),
        "duration_seconds": duration,
        "num_frames": num_frames,
        "fps": 24,
        "model_repo": "ewin-reg/MiniMax-H3-Turbo-FP8-ComfyUI",
        "workflow": "fl2va",
        "experiment": "minimax-h3-isolated-v1",
    }
    (temp_root / "job.json").write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")

    slug = re.sub(r"[^a-z0-9-]+", "-", f"minimax-h3-e001-s{shot_id}".lower()).strip("-")
    metadata = {
        "id": f"{owner}/{slug}",
        "title": f"Animation Factory MiniMax H3 E001 Shot {shot_id}",
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

    if action == "idle":
        return f"MiniMax H3 experiment bridge is installed. Request ID: `{request_id}`.", []

    if not os.getenv("KAGGLE_API_TOKEN"):
        raise RuntimeError("KAGGLE_API_TOKEN GitHub Actions secret is not configured")

    if action in {"kernel_status", "kernel_files", "kernel_output"}:
        return worker.execute(command)

    if action != "run_minimax_shot":
        raise ValueError("Supported MiniMax actions: idle, run_minimax_shot, kernel_status, kernel_files, kernel_output")

    owner = resolve_owner(command.get("owner"))
    shot_id = str(command.get("shot") or "001").strip().lower()
    if not re.fullmatch(r"(?:00[1-9]|006[ab])", shot_id):
        raise ValueError("shot must be one of 001-005, 006a, 006b, 007-009")

    folder, kernel = _build_kernel(shot_id, owner)
    try:
        push = worker.run(["kaggle", "kernels", "push", "-p", str(folder), "--accelerator", "NvidiaTeslaT4"])
        try:
            status = worker.run(["kaggle", "kernels", "status", kernel])
        except Exception as exc:
            status = f"Kernel submitted; immediate status unavailable: {type(exc).__name__}: {exc}"
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    return (
        f"Submitted isolated MiniMax H3 test **{kernel}** for Episode 001 shot **{shot_id}**.\n\n"
        f"Push response:\n```text\n{push[:6000]}\n```\n\nStatus:\n```text\n{status[:3000]}\n```\n\n"
        "This does not alter the production video backend. Use `kernel_output` after completion to retrieve "
        "`minimax-h3-test.mp4` and `minimax-h3-report.json`.",
        [],
    )


def main() -> int:
    worker.ARTIFACTS.mkdir(exist_ok=True)
    try:
        message, files = execute(parse_command())
        body = "## ✅ MiniMax H3 Experiment\n\n" + message
        if files:
            body += "\n\nDownloaded files are attached to the workflow run as `minimax-h3-output`."
        code = 0
    except Exception as exc:
        body = f"## ❌ MiniMax H3 Experiment\n\n`{type(exc).__name__}`: {exc}"
        code = 1
    worker.RESULT_FILE.write_text(body + "\n", encoding="utf-8")
    print(body)
    return code


if __name__ == "__main__":
    sys.exit(main())
