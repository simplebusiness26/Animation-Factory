#!/usr/bin/env python3
"""Hardened Animation Factory Kaggle bridge entrypoint.

Keeps the existing allow-listed worker operations, but treats Kaggle's private
kernel session-status 403 as non-fatal after a successful kernel push. The
kernel has already been submitted at that point and its outputs can be fetched
through the normal kernel_output command.
"""
from __future__ import annotations

import sys

import worker


def execute(command):
    action = str(command.get("action") or "").strip()
    if action != "run_kernel":
        return worker.execute(command)

    request_id = str(command.get("request_id") or "unspecified").strip()
    owner = str(command.get("owner") or worker.os.getenv("KAGGLE_OWNER") or "").strip() or None
    folder = worker.safe_kernel_dir(command.get("path"))
    metadata = worker.render_metadata(folder, owner)
    args = ["kaggle", "kernels", "push", "-p", str(folder)]
    accelerator = str(command.get("accelerator") or "").strip()
    if accelerator:
        if accelerator not in worker.ALLOWED_ACCELERATORS:
            raise ValueError(f"Unsupported accelerator: {accelerator}")
        args.extend(["--accelerator", accelerator])

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
