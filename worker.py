#!/usr/bin/env python3
"""Issue-driven bridge between GitHub Actions and Kaggle.

The worker deliberately exposes a small allow-list of Kaggle operations instead of
executing arbitrary shell commands. Commands are supplied as JSON in a GitHub issue
whose title starts with [KAGGLE].
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
RESULT_FILE = ROOT / "result.md"
KERNEL_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
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


def parse_issue_body() -> dict[str, Any]:
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        raise RuntimeError("GITHUB_EVENT_PATH is not set")
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    body = (event.get("issue", {}).get("body") or "").strip()
    if not body:
        raise ValueError("Issue body is empty; expected a JSON command")

    # Accept raw JSON or a fenced ```json ... ``` block.
    if body.startswith("```"):
        lines = body.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            body = "\n".join(lines[1:-1]).strip()
            if body.lower().startswith("json\n"):
                body = body[5:].strip()

    command = json.loads(body)
    if not isinstance(command, dict):
        raise ValueError("Command must be a JSON object")
    return command


def bounded_size(value: Any, default: int = 10, maximum: int = 50) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        size = default
    return max(1, min(size, maximum))


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
    if kernels_root not in target.parents:
        raise ValueError("Invalid kernel path")
    if not target.is_dir():
        raise ValueError(f"Kernel folder not found: {rel}")
    return target


def render_metadata(folder: Path, owner: str | None) -> tuple[dict[str, Any], Path]:
    metadata_path = folder / "kernel-metadata.json"
    if not metadata_path.exists():
        raise ValueError(f"Missing {metadata_path.relative_to(ROOT)}")
    raw = metadata_path.read_text(encoding="utf-8")
    if "__OWNER__" in raw:
        if not owner:
            raise ValueError(
                "KAGGLE_OWNER is not configured. Add it as a GitHub Actions repository variable."
            )
        raw = raw.replace("__OWNER__", owner)
    metadata = json.loads(raw)
    kernel_id = metadata.get("id")
    if not isinstance(kernel_id, str) or not KERNEL_RE.fullmatch(kernel_id):
        raise ValueError("kernel-metadata.json must contain a valid id in owner/slug form")

    # Write the rendered metadata only into the ephemeral Actions checkout.
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata, metadata_path


def execute(command: dict[str, Any]) -> tuple[str, list[str]]:
    action = str(command.get("action") or "").strip()
    owner = str(command.get("owner") or os.getenv("KAGGLE_OWNER") or "").strip() or None
    files: list[str] = []

    if not os.getenv("KAGGLE_API_TOKEN"):
        raise RuntimeError("KAGGLE_API_TOKEN GitHub Actions secret is not configured")

    if action == "ping":
        version = run(["kaggle", "--version"])
        return f"Kaggle authentication reached the worker.\n\n```text\n{version}\n```", files

    if action == "search_models":
        query = str(command.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        size = bounded_size(command.get("limit"))
        out = run(["kaggle", "models", "list", "-s", query, "--page-size", str(size)])
        return f"Model search for **{query}**:\n\n```text\n{out[:12000]}\n```", files

    if action == "search_datasets":
        query = str(command.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        size = bounded_size(command.get("limit"))
        out = run(["kaggle", "datasets", "list", "-s", query, "--page-size", str(size)])
        return f"Dataset search for **{query}**:\n\n```text\n{out[:12000]}\n```", files

    if action == "search_kernels":
        query = str(command.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        size = bounded_size(command.get("limit"))
        out = run(["kaggle", "kernels", "list", "-s", query, "--page-size", str(size)])
        return f"Notebook search for **{query}**:\n\n```text\n{out[:12000]}\n```", files

    if action == "run_kernel":
        folder = safe_kernel_dir(command.get("path"))
        metadata, _ = render_metadata(folder, owner)
        args = ["kaggle", "kernels", "push", "-p", str(folder)]
        accelerator = str(command.get("accelerator") or "").strip()
        if accelerator:
            if accelerator not in ALLOWED_ACCELERATORS:
                raise ValueError(f"Unsupported accelerator: {accelerator}")
            args.extend(["--accelerator", accelerator])
        out = run(args)
        kernel = metadata["id"]
        status = run(["kaggle", "kernels", "status", kernel])
        return (
            f"Started Kaggle kernel **{kernel}**.\n\n"
            f"Push response:\n```text\n{out[:6000]}\n```\n\n"
            f"Current status:\n```text\n{status[:3000]}\n```",
            files,
        )

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
        return (
            f"Downloaded output for **{kernel}** into the GitHub Actions artifact.\n\n"
            f"```text\n{out[:6000]}\n```\n\nFiles:\n```text\n{listing[:8000]}\n```",
            files,
        )

    raise ValueError(
        "Unknown action. Supported actions: ping, search_models, search_datasets, "
        "search_kernels, run_kernel, kernel_status, kernel_files, kernel_output"
    )


def main() -> int:
    ARTIFACTS.mkdir(exist_ok=True)
    try:
        command = parse_issue_body()
        message, files = execute(command)
        body = "## ✅ Kaggle Worker\n\n" + message
        if files:
            body += "\n\nThe downloaded files are attached to this workflow run as the `kaggle-output` artifact."
        code = 0
    except Exception as exc:  # Surface concise errors to the issue rather than leaking secrets.
        body = f"## ❌ Kaggle Worker\n\n`{type(exc).__name__}`: {exc}"
        code = 1

    RESULT_FILE.write_text(body + "\n", encoding="utf-8")
    print(body)
    return code


if __name__ == "__main__":
    sys.exit(main())
