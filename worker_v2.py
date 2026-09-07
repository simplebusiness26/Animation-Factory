#!/usr/bin/env python3
"""Hardened Animation Factory Kaggle bridge entrypoint.

Keeps the existing allow-listed worker operations, but treats Kaggle's private
kernel session-status 403 as non-fatal after a successful kernel push. The
kernel has already been submitted at that point and its outputs can be fetched
through the normal kernel_output command.

Episode 001 run submissions are also fail-closed while its persisted production
state is paused, so the generic bridge cannot bypass the episode controller.
Read-only status/output commands remain available.
"""
from __future__ import annotations

import json
import sys
import shutil
import tempfile
from pathlib import Path

import worker
from pipeline.production_guard import require_launch_allowed
from pipeline.kaggle_packaging import prepare_image_bootstrap

ROOT = Path(__file__).resolve().parent
EPISODE001_MARKERS = (
    "earth-needs-help-e001",
    "episode001",
    "episode-001",
    "episode_001",
    "e001",
    "reference-still-runner",
    "episode-motion-runner",
)


def targets_episode001(command: dict, metadata: dict) -> bool:
    material = " ".join(
        [
            str(command.get("request_id") or ""),
            str(command.get("path") or ""),
            str(command.get("job_path") or ""),
            str(metadata.get("id") or ""),
            str(metadata.get("title") or ""),
        ]
    ).lower()
    return any(marker in material for marker in EPISODE001_MARKERS)


def execute(command):
    action = str(command.get("action") or "").strip()
    if action == 'run_shot':
        job_path = worker.safe_repo_file(command.get('job_path'), roots=('shows',), suffixes={'.json'})
        job = json.loads(job_path.read_text(encoding='utf-8'))
        if targets_episode001(command, {}) or str(job.get('episode', '')).zfill(3) == '001':
            require_launch_allowed(ROOT)
            from pipeline.image_router import verified_image
            if job.get('qa_status') != 'approved':
                raise RuntimeError('Shot generation requires an approved input still')
            verified_image(ROOT, job['still_path'], job.get('still_sha256', ''))
        return worker.execute(command)
    if action != 'run_kernel':
        return worker.execute(command)

    request_id = str(command.get("request_id") or "unspecified").strip()
    owner = str(command.get("owner") or worker.os.getenv("KAGGLE_OWNER") or "").strip() or None
    folder = worker.safe_kernel_dir(command.get("path"))
    original_metadata = json.loads((folder / 'kernel-metadata.json').read_text(encoding='utf-8'))
    if targets_episode001(command, original_metadata):
        require_launch_allowed(ROOT)
    # Render metadata and inject immutable source refs only in a temporary copy.
    # A rejected launch must not modify the checked-out kernel metadata.
    with tempfile.TemporaryDirectory(prefix='animation-kernel-') as td:
        prepared = Path(td)
        shutil.copytree(folder, prepared, dirs_exist_ok=True)
        metadata = worker.render_metadata(prepared, owner)
        if folder.name == 'reference-still-runner':
            prepare_image_bootstrap(ROOT, prepared / metadata['code_file'])
        args = ['kaggle', 'kernels', 'push', '-p', str(prepared)]
        accelerator = str(command.get('accelerator') or '').strip()
        if accelerator:
            if accelerator not in worker.ALLOWED_ACCELERATORS:
                raise ValueError(f'Unsupported accelerator: {accelerator}')
            args.extend(['--accelerator', accelerator])
        push_response = worker.run(args)
    kernel = metadata["id"]
    try:
        status = worker.run(["kaggle", "kernels", "status", kernel])
        status_text = f"Current status:\n```text\n{status[:3000]}\n```"
    except Exception as exc:
        status_text = (
            "Kaggle accepted the kernel push. Its private session-status endpoint "
            f"is unavailable to this token, so output retrieval will be used instead. Request ID: `{request_id}`.\n\n"
            f"Status detail: `{type(exc).__name__}`"
        )

    return (
        f"Submitted Kaggle kernel **{kernel}**.\n\n"
        f"Push response:\n```text\n{push_response[:6000]}\n```\n\n{status_text}",
        [],
    )


def main() -> int:
    worker.ARTIFACTS.mkdir(exist_ok=True)
    try:
        command = worker.parse_command()
        if str(command.get("action") or "").strip() != "idle" and not worker.os.getenv("KAGGLE_API_TOKEN"):
            raise RuntimeError("KAGGLE_API_TOKEN GitHub Actions secret is not configured")
        message, files = execute(command)
        body = "## ✅ Kaggle Worker\n\n" + message
        if files:
            body += "\n\nDownloaded files are attached to the workflow run as the `kaggle-output` artifact."
        code = 0
    except Exception as exc:
        body = f"## ❌ Kaggle Worker\n\n`{type(exc).__name__}`: {exc}"
        code = 1

    worker.RESULT_FILE.write_text(body + "\n", encoding="utf-8")
    print(body)
    return code


if __name__ == "__main__":
    sys.exit(main())
