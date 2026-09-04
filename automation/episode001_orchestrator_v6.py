#!/usr/bin/env python3
"""Episode 001 controller v6: retry-storm protection and repair gating.

Safety upgrades over v5:
- a rejected still batch is handled once per exact hash-bound batch;
- only one live Kaggle submission is allowed per production family;
- transient API/indexing failures wait and require repeated confirmation;
- repeated identical Kaggle failures enter ``repair_required`` instead of
  spending more GPU quota on unchanged code.

This module intentionally wraps the existing v3-v5 continuity, archive,
quota-backoff and Kaggle-indexing protections rather than replacing them.
"""
from __future__ import annotations

import hashlib
import json
import re
import time

import episode001_orchestrator as base
import episode001_orchestrator_v2 as v2
import episode001_orchestrator_v3 as v3
import episode001_orchestrator_v4 as v4
import episode001_orchestrator_v5 as v5  # noqa: F401 - imports v5 safety patches

TRANSIENT_STATUS_BACKOFF_SECONDS = 15 * 60
MISSING_CONFIRMATIONS_REQUIRED = 3
MISSING_SUBMISSION_GRACE_SECONDS = 60 * 60
IDENTICAL_FAILURE_LIMIT = 2
REPAIR_RECORD = base.ROOT / "automation" / "episode001-repair-required.json"

_V5_HANDLE_STILLS = v2.handle_stills
_V5_HANDLE_MOTION = v2.handle_motion
_ORIGINAL_RETRY_STILLS = v2.retry_stills
_ORIGINAL_RETRY_MOTION = v2.retry_motion


def _now() -> int:
    return int(time.time())


def _family_phase(family: str) -> str:
    return "awaiting_stills" if family == "stills" else "awaiting_motion"


def _kernel_for(state: dict, family: str) -> str:
    if family == "stills":
        return v2.current_kernel(state, "stills_kernel", base.STILLS_KERNEL)
    return v2.current_kernel(state, "motion_kernel", base.MOTION_KERNEL)


def _submitted_key(family: str) -> str:
    return f"{family}_submitted_at_epoch"


def _active_key(family: str) -> str:
    return f"{family}_active_kernel"


def _transient_until_key(family: str) -> str:
    return f"{family}_transient_retry_after"


def _missing_checks_key(family: str) -> str:
    return f"{family}_missing_checks"


def _quota_wait_active(state: dict, family: str) -> bool:
    if str(state.get("last_status") or "") != f"{family.upper()}_GPU_QUOTA_WAIT":
        return False
    try:
        return int(state.get("gpu_quota_retry_after") or 0) > _now()
    except (TypeError, ValueError):
        return False


def _transient_wait_active(state: dict, family: str) -> bool:
    try:
        return int(state.get(_transient_until_key(family)) or 0) > _now()
    except (TypeError, ValueError):
        return False


def _mark_transient_wait(state: dict, family: str, reason: str) -> None:
    state["phase"] = _family_phase(family)
    state["last_status"] = f"{family.upper()}_STATUS_TRANSIENT_WAIT"
    state["last_error"] = reason
    state[_transient_until_key(family)] = _now() + TRANSIENT_STATUS_BACKOFF_SECONDS


def _recent_submission(state: dict, family: str) -> bool:
    try:
        submitted = int(state.get(_submitted_key(family)) or 0)
    except (TypeError, ValueError):
        return False
    return submitted > 0 and (_now() - submitted) < MISSING_SUBMISSION_GRACE_SECONDS


def _hold_existing_submission(state: dict, family: str) -> bool:
    """Return True when retrying would create a duplicate live/transient job."""
    kernel = _kernel_for(state, family)
    status = v2.safe_status(kernel)

    if status in {"QUEUED", "RUNNING"}:
        state["phase"] = _family_phase(family)
        state["last_status"] = f"{family.upper()}_ACTIVE_SUBMISSION_HELD"
        state["last_error"] = None
        state[_active_key(family)] = kernel
        return True

    if status == "STATUS_ERROR":
        _mark_transient_wait(
            state,
            family,
            "Kaggle status lookup failed transiently; no replacement notebook was submitted.",
        )
        return True

    if status == "MISSING" and _recent_submission(state, family):
        state["phase"] = _family_phase(family)
        state["last_status"] = f"{family.upper()}_SUBMITTED_AWAITING_KAGGLE_INDEX"
        state["last_error"] = None
        state[_active_key(family)] = kernel
        return True

    return False


def _record_successful_submit(state: dict, family: str) -> None:
    status = str(state.get("last_status") or "")
    if not status.endswith("_SUBMITTED"):
        return
    state[_submitted_key(family)] = _now()
    state[_active_key(family)] = _kernel_for(state, family)
    state[_missing_checks_key(family)] = 0
    state.pop(_transient_until_key(family), None)


def safe_retry_stills(state: dict, reason: str) -> None:
    if _quota_wait_active(state, "stills") or _transient_wait_active(state, "stills"):
        return
    if _hold_existing_submission(state, "stills"):
        return
    _ORIGINAL_RETRY_STILLS(state, reason)
    _record_successful_submit(state, "stills")


def safe_retry_motion(state: dict, reason: str, *, first_submit: bool = False) -> None:
    if _quota_wait_active(state, "motion") or _transient_wait_active(state, "motion"):
        return
    if _hold_existing_submission(state, "motion"):
        return
    _ORIGINAL_RETRY_MOTION(state, reason, first_submit=first_submit)
    _record_successful_submit(state, "motion")


v2.retry_stills = safe_retry_stills
v2.retry_motion = safe_retry_motion


def _rejection_batch_key() -> str | None:
    qa = v4._qa_payload()
    if str(qa.get("status") or "").lower() != "rejected":
        return None
    hashes = [str(row.get("sha256") or "") for row in (qa.get("shots") or [])]
    material = "|".join(value for value in hashes if value)
    if not material:
        material = json.dumps(qa, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()[:20]


def normalize_explicit_rejection_once(state: dict) -> bool:
    """Move one exact rejected batch into rebuild once, never once per poll."""
    gate_rejected = str(state.get("continuity_gate") or "").lower() == "rejected"
    batch_key = _rejection_batch_key()
    if not gate_rejected and batch_key is None:
        return False

    key = batch_key or "gate-only-rejection"
    if state.get("handled_rejected_batch_key") == key:
        return False

    state["handled_rejected_batch_key"] = key
    state["phase"] = "blocked_continuity"
    state["last_status"] = "CONTINUITY_BATCH_REJECTED_REBUILD_REQUIRED"
    state["last_error"] = None
    state["stills_attempts"] = 0
    state["motion_attempts"] = 0
    base.save_state(state)
    return True


v4.normalize_explicit_rejection = normalize_explicit_rejection_once


def _diagnostic_signature(state: dict, family: str, kernel: str) -> tuple[str, str]:
    attempt = int(state.get(f"{family}_attempts", 0))
    label = f"{family}-error-{attempt}"
    v2.persist_kernel_diagnostics(kernel, label)

    chunks: list[str] = []
    for path in sorted(base.LOG_DIR.glob(f"{label}-*")):
        if not path.is_file():
            continue
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace")[-80_000:])
        except Exception:
            continue

    raw = "\n".join(chunks)
    interesting = []
    markers = (
        "error",
        "exception",
        "traceback",
        "failed",
        "cannot import",
        "no module named",
        "file not found",
        "filenotfound",
        "runtimeerror",
        "modulenotfound",
    )
    for line in raw.splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in markers):
            interesting.append(lowered.strip())

    normalized = "\n".join(interesting[-120:]) or f"{family}:kaggle-error:no-text-diagnostics"
    normalized = re.sub(r"\b\d+(?:\.\d+)?\b", "#", normalized)
    normalized = re.sub(r"r#-#+(?:-#)?", "r#", normalized)
    normalized = re.sub(r"/tmp/[^/\s]+", "/tmp/<run>", normalized)
    signature = hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()[:20]

    summary = interesting[-1] if interesting else "Kaggle reported ERROR with no readable text diagnostic."
    return signature, summary[:1000]


def _enter_repair_required(
    state: dict,
    family: str,
    kernel: str,
    signature: str,
    repeats: int,
    summary: str,
) -> None:
    state["phase"] = "repair_required"
    state["repair_family"] = family
    state["repair_kernel"] = kernel
    state["repair_fingerprint"] = signature
    state["repair_repeats"] = repeats
    state["last_status"] = f"{family.upper()}_REPAIR_REQUIRED"
    state["last_error"] = (
        f"Repeated identical Kaggle failure ({signature}) detected {repeats} times. "
        "Automatic GPU resubmission is stopped until the runner/dependencies are changed. "
        f"Latest diagnostic: {summary}"
    )
    state.pop(_active_key(family), None)

    payload = {
        "episode": "001",
        "family": family,
        "kernel": kernel,
        "fingerprint": signature,
        "repeat_count": repeats,
        "diagnostic_summary": summary,
        "required_action": "Repair code/dependencies, validate without a GPU render where possible, then explicitly clear repair_required before resuming.",
        "created_at_epoch": _now(),
    }
    REPAIR_RECORD.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _handle_error_with_repair_gate(state: dict, family: str, kernel: str) -> bool:
    signature, summary = _diagnostic_signature(state, family, kernel)
    previous = str(state.get(f"{family}_failure_fingerprint") or "")
    repeats = int(state.get(f"{family}_failure_repeats", 0)) + 1 if previous == signature else 1
    state[f"{family}_failure_fingerprint"] = signature
    state[f"{family}_failure_repeats"] = repeats
    state[f"{family}_failure_summary"] = summary

    if repeats >= IDENTICAL_FAILURE_LIMIT:
        _enter_repair_required(state, family, kernel, signature, repeats, summary)
        return True
    return False


def _hardened_handle(state: dict, family: str) -> None:
    if _quota_wait_active(state, family) or _transient_wait_active(state, family):
        state["phase"] = _family_phase(family)
        return

    kernel = _kernel_for(state, family)
    status = v2.safe_status(kernel)

    if status == "STATUS_ERROR":
        _mark_transient_wait(
            state,
            family,
            "Kaggle status API returned an error; waiting before checking again instead of creating a replacement notebook.",
        )
        return

    if status == "MISSING":
        checks_key = _missing_checks_key(family)
        checks = int(state.get(checks_key, 0)) + 1
        state[checks_key] = checks
        if _recent_submission(state, family) or checks < MISSING_CONFIRMATIONS_REQUIRED:
            state["phase"] = _family_phase(family)
            state["last_status"] = f"{family.upper()}_MISSING_CONFIRMATION_{checks}_OF_{MISSING_CONFIRMATIONS_REQUIRED}"
            state["last_error"] = "Kaggle has not indexed/found the notebook yet; replacement submission withheld."
            return
    else:
        state[_missing_checks_key(family)] = 0

    if status in {"QUEUED", "RUNNING"}:
        state[_active_key(family)] = kernel
        state["last_error"] = None
    elif status in {"COMPLETE", "ERROR"}:
        state.pop(_active_key(family), None)

    if status == "ERROR" and _handle_error_with_repair_gate(state, family, kernel):
        return

    if family == "stills":
        _V5_HANDLE_STILLS(state)
    else:
        _V5_HANDLE_MOTION(state)


def hardened_handle_stills(state: dict) -> None:
    _hardened_handle(state, "stills")


def hardened_handle_motion(state: dict) -> None:
    _hardened_handle(state, "motion")


v2.handle_stills = hardened_handle_stills
v2.handle_motion = hardened_handle_motion


def main() -> int:
    state = base.load_state()
    if state.get("phase") == "repair_required":
        state["last_status"] = state.get("last_status") or "REPAIR_REQUIRED"
        base.save_state(state)
        print(json.dumps(state, indent=2))
        return 0
    return v4.main()


if __name__ == "__main__":
    raise SystemExit(main())
