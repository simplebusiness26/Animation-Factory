#!/usr/bin/env python3
"""Self-healing controller for Earth Needs Help Episode 001.

Failure-aware behaviour:
- failed/incomplete kernels are diagnosed and text logs are persisted;
- retries use fresh unique Kaggle kernel slugs;
- Kaggle title/id slug rules are enforced;
- submission failures do not consume actual render attempts;
- COMPLETE still kernels are never automatically rerendered just because local staging fails;
- motion and assembly resume from the latest successful stage;
- only repeated terminal failures halt production.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
from pathlib import Path

import episode001_orchestrator as base

MAX_ASSEMBLY_ATTEMPTS = 2
MAX_SUBMIT_FAILURES = 5
GPU_QUOTA_BACKOFF_SECONDS = 60 * 60
TEXT_SUFFIXES = {".log", ".txt", ".json", ".md", ".csv"}


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")[:50]


def current_kernel(state: dict, key: str, fallback: str) -> str:
    value = str(state.get(key) or "").strip()
    return value or fallback


def safe_status(kernel: str) -> str:
    try:
        return base.status_of(kernel)
    except Exception as exc:
        text = str(exc)
        base.log("latest-status-error.txt", text)
        if "404" in text or "not found" in text.lower():
            return "MISSING"
        return "STATUS_ERROR"


def persist_kernel_diagnostics(kernel: str, label: str) -> None:
    try:
        with tempfile.TemporaryDirectory(prefix=f"{label}-") as td:
            root = Path(td)
            base.download_output(kernel, root)
            found = False
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                found = True
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except Exception as exc:
                    text = f"Could not read {path.name}: {exc}"
                safe_name = slugify(path.name.rsplit(".", 1)[0]) or "diagnostic"
                base.log(f"{label}-{safe_name}{path.suffix.lower()}", text[-200_000:])
            if not found:
                base.log(f"{label}-diagnostic.txt", f"No text diagnostics were returned for {kernel}.")
    except Exception as exc:
        base.log(f"{label}-download-error.txt", f"{type(exc).__name__}: {exc}")


def prepare_retry_folder(source: Path, kernel_ref: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="animation-factory-retry-"))
    shutil.copytree(source, root, dirs_exist_ok=True)
    meta_path = root / "kernel-metadata.json"
    raw = meta_path.read_text(encoding="utf-8").replace("__OWNER__", base.OWNER)
    metadata = json.loads(raw)
    slug = kernel_ref.split("/", 1)[1]
    metadata["id"] = kernel_ref
    metadata["title"] = slug
    metadata["is_private"] = True
    metadata["enable_gpu"] = True
    metadata["enable_internet"] = True
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return root


def _validate_kaggle_push_output(out: str) -> None:
    """Kaggle CLI can print a push error while still exiting with code 0."""
    lowered = out.lower()
    if "kernel push error:" in lowered or "maximum weekly gpu quota" in lowered:
        raise RuntimeError(out[-6000:] or "Kaggle kernel push failed")


def push_fresh(source: Path, prefix: str, attempt: int) -> tuple[str, str]:
    for collision in range(2):
        stamp = str(int(time.time()))[-7:]
        suffix = f"r{attempt}-{stamp}" if collision == 0 else f"r{attempt}-{stamp}-{collision+1}"
        slug = slugify(f"{prefix}-{suffix}")
        kernel = f"{base.OWNER}/{slug}"
        folder = prepare_retry_folder(source, kernel)
        try:
            out = base.run(["kaggle", "kernels", "push", "-p", str(folder), "--accelerator", "NvidiaTeslaT4"])
            _validate_kaggle_push_output(out)
            return kernel, out
        except Exception as exc:
            if "409" not in str(exc) or collision == 1:
                raise
            time.sleep(2)
        finally:
            shutil.rmtree(folder, ignore_errors=True)
    raise RuntimeError("Could not allocate a fresh Kaggle retry kernel")


def _is_gpu_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "maximum weekly gpu quota" in text or ("gpu quota" in text and "reached" in text)


def record_gpu_quota_wait(state: dict, family: str, exc: Exception) -> None:
    state["phase"] = "awaiting_stills" if family == "stills" else "awaiting_motion"
    state["last_status"] = f"{family.upper()}_GPU_QUOTA_WAIT"
    state["last_error"] = "Kaggle weekly GPU quota is exhausted; production will retry automatically after backoff without consuming a render attempt."
    state["gpu_quota_retry_after"] = int(time.time()) + GPU_QUOTA_BACKOFF_SECONDS
    base.log(f"{family}-gpu-quota-wait.txt", str(exc))


def record_submit_failure(state: dict, family: str, exc: Exception) -> None:
    key = f"{family}_submit_failures"
    count = int(state.get(key, 0)) + 1
    state[key] = count
    state["last_status"] = f"{family.upper()}_SUBMIT_ERROR_{count}"
    state["last_error"] = f"{type(exc).__name__}: {exc}"
    if count >= MAX_SUBMIT_FAILURES:
        state["phase"] = "failed"
        state["last_status"] = f"{family.upper()}_SUBMIT_TERMINAL_FAILURE"


def retry_stills(state: dict, reason: str) -> None:
    attempts = int(state.get("stills_attempts", 0))
    if attempts >= base.MAX_STILLS_ATTEMPTS:
        state["phase"] = "failed"
        state["last_status"] = "STILLS_TERMINAL_FAILURE"
        state["last_error"] = f"Stills generation exhausted {attempts} automatic retries. Last reason: {reason}"
        return
    attempt = attempts + 1
    try:
        kernel, out = push_fresh(base.STILLS_KERNEL_DIR, "enh-e001-stills", attempt)
        base.log("stills-resubmit.txt", out)
        state["stills_attempts"] = attempt
        state["stills_submit_failures"] = 0
        state["stills_staging_failures"] = 0
        state["stills_kernel"] = kernel
        state["phase"] = "awaiting_stills"
        state["last_status"] = f"STILLS_RETRY_{attempt}_SUBMITTED"
        state["last_error"] = None
        state.pop("gpu_quota_retry_after", None)
    except Exception as exc:
        if _is_gpu_quota_error(exc):
            record_gpu_quota_wait(state, "stills", exc)
        else:
            record_submit_failure(state, "stills", exc)


def build_motion_retry_folder(kernel_ref: str, attempt: int) -> Path:
    root = base.build_motion_kernel()
    meta_path = root / "kernel-metadata.json"
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    metadata["id"] = kernel_ref
    metadata["title"] = kernel_ref.split("/", 1)[1]
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return root


def retry_motion(state: dict, reason: str, *, first_submit: bool = False) -> None:
    attempts = int(state.get("motion_attempts", 0))
    if attempts >= base.MAX_MOTION_ATTEMPTS:
        state["phase"] = "failed"
        state["last_status"] = "MOTION_TERMINAL_FAILURE"
        state["last_error"] = f"Motion generation exhausted {attempts} automatic attempts. Last reason: {reason}"
        return
    attempt = attempts + 1
    for collision in range(2):
        stamp = str(int(time.time()))[-7:]
        slug = slugify(f"enh-e001-motion-r{attempt}-{stamp}-{collision}")
        kernel = f"{base.OWNER}/{slug}"
        folder = build_motion_retry_folder(kernel, attempt)
        try:
            out = base.run(["kaggle", "kernels", "push", "-p", str(folder), "--accelerator", "NvidiaTeslaT4"])
            _validate_kaggle_push_output(out)
            base.log("motion-submit.txt", out)
            state["motion_attempts"] = attempt
            state["motion_submit_failures"] = 0
            state["motion_kernel"] = kernel
            state["phase"] = "awaiting_motion"
            state["last_status"] = f"MOTION_ATTEMPT_{attempt}_SUBMITTED"
            state["last_error"] = None
            state.pop("gpu_quota_retry_after", None)
            return
        except Exception as exc:
            if "409" in str(exc) and collision == 0:
                time.sleep(2)
                continue
            if _is_gpu_quota_error(exc):
                record_gpu_quota_wait(state, "motion", exc)
            else:
                record_submit_failure(state, "motion", exc)
            return
        finally:
            shutil.rmtree(folder, ignore_errors=True)


def handle_stills(state: dict) -> None:
    kernel = current_kernel(state, "stills_kernel", base.STILLS_KERNEL)
    status = safe_status(kernel)
    state["last_status"] = f"STILLS_{status}"
    if status in {"QUEUED", "RUNNING"}:
        state["last_error"] = None
        return
    if status == "COMPLETE":
        try:
            with tempfile.TemporaryDirectory(prefix="e001-stills-output-") as td:
                out_dir = Path(td)
                base.download_output(kernel, out_dir)
                staged = base.stage_generated_stills(out_dir)
                if len(staged) != len(base.SHOTS):
                    raise RuntimeError(f"Expected {len(base.SHOTS)} validated stills, got {len(staged)}")
            state["stills_staging_failures"] = 0
            state["last_status"] = "STILLS_VALIDATED"
            state["last_error"] = None
            retry_motion(state, "initial motion submission", first_submit=True)
        except Exception as exc:
            failures = int(state.get("stills_staging_failures", 0)) + 1
            state["stills_staging_failures"] = failures
            persist_kernel_diagnostics(kernel, f"stills-staging-error-{failures}")
            state["phase"] = "awaiting_stills"
            state["last_status"] = f"STILLS_STAGING_ERROR_{failures}"
            state["last_error"] = f"Completed Kaggle batch retained; staging failed: {type(exc).__name__}: {exc}"
        return
    if status == "ERROR":
        persist_kernel_diagnostics(kernel, f"stills-error-{int(state.get('stills_attempts', 0))}")
        retry_stills(state, "Kaggle reported ERROR")
        return
    if status in {"MISSING", "STATUS_ERROR"}:
        retry_stills(state, f"kernel status unavailable: {status}")
        return
    retry_stills(state, f"unrecognised Kaggle status: {status}")


def handle_motion(state: dict) -> None:
    kernel = current_kernel(state, "motion_kernel", base.MOTION_KERNEL)
    status = safe_status(kernel)
    state["last_status"] = f"MOTION_{status}"
    if status in {"QUEUED", "RUNNING"}:
        state["last_error"] = None
        return
    if status == "COMPLETE":
        try:
            with tempfile.TemporaryDirectory(prefix="e001-motion-output-") as td:
                output = Path(td)
                base.download_output(kernel, output)
                base.verify_motion_outputs(output)
                assembly_attempts = int(state.get("assembly_attempts", 0)) + 1
                state["assembly_attempts"] = assembly_attempts
                final = base.render_final(output)
                state["final_file"] = str(final.relative_to(base.ROOT))
            state["phase"] = "complete"
            state["last_status"] = "FINAL_MP4_VALIDATED"
            state["last_error"] = None
        except Exception as exc:
            state["last_error"] = f"Final assembly/QA failed: {type(exc).__name__}: {exc}"
            if int(state.get("assembly_attempts", 0)) >= MAX_ASSEMBLY_ATTEMPTS:
                state["phase"] = "failed"
                state["last_status"] = "ASSEMBLY_TERMINAL_FAILURE"
            else:
                state["phase"] = "awaiting_motion"
                state["last_status"] = "ASSEMBLY_RETRY_PENDING"
        return
    if status == "ERROR":
        persist_kernel_diagnostics(kernel, f"motion-error-{int(state.get('motion_attempts', 0))}")
        retry_motion(state, "Kaggle reported ERROR")
        return
    if status in {"MISSING", "STATUS_ERROR"}:
        retry_motion(state, f"kernel status unavailable: {status}")
        return
    retry_motion(state, f"unrecognised Kaggle status: {status}")
