#!/usr/bin/env python3
"""Episode 001 controller v5.

Adds a Kaggle submission-indexing grace period on top of v4.

Private Kaggle kernels can briefly report as missing immediately after a
successful `kaggle kernels push`. The previous controller interpreted that
transient MISSING result as a failed render and submitted another fresh kernel
on the next self-check. That caused kernel churn without advancing production.

This wrapper preserves all v4 behaviour, including the locked character canon,
hash-bound continuity gate, and archive/current-stills separation. It only
suppresses automatic still/motion resubmission while a newly submitted kernel
is inside a conservative indexing grace window.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import episode001_orchestrator as base
import episode001_orchestrator_v2 as v2
import episode001_orchestrator_v4 as v4

INDEXING_GRACE_SECONDS = 30 * 60

_ORIGINAL_HANDLE_STILLS = v2.handle_stills
_ORIGINAL_HANDLE_MOTION = v2.handle_motion


def _age_seconds(state: dict) -> float | None:
    raw = str(state.get("updated_at") or "").strip()
    if not raw:
        return None
    try:
        submitted = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return max(0.0, time.time() - submitted.timestamp())


def _fresh_submission(state: dict, family: str) -> bool:
    status = str(state.get("last_status") or "")
    if family == "stills":
        submitted = status.startswith("STILLS_RETRY_") and status.endswith("_SUBMITTED")
    else:
        submitted = status.startswith("MOTION_ATTEMPT_") and status.endswith("_SUBMITTED")
    age = _age_seconds(state)
    return submitted and age is not None and age < INDEXING_GRACE_SECONDS


def guarded_handle_stills(state: dict) -> None:
    kernel = v2.current_kernel(state, "stills_kernel", base.STILLS_KERNEL)
    status = v2.safe_status(kernel)
    if status == "MISSING" and _fresh_submission(state, "stills"):
        state["phase"] = "awaiting_stills"
        state["last_status"] = "STILLS_SUBMITTED_AWAITING_KAGGLE_INDEX"
        state["last_error"] = None
        return
    _ORIGINAL_HANDLE_STILLS(state)


def guarded_handle_motion(state: dict) -> None:
    kernel = v2.current_kernel(state, "motion_kernel", base.MOTION_KERNEL)
    status = v2.safe_status(kernel)
    if status == "MISSING" and _fresh_submission(state, "motion"):
        state["phase"] = "awaiting_motion"
        state["last_status"] = "MOTION_SUBMITTED_AWAITING_KAGGLE_INDEX"
        state["last_error"] = None
        return
    _ORIGINAL_HANDLE_MOTION(state)


v2.handle_stills = guarded_handle_stills
v2.handle_motion = guarded_handle_motion


def main() -> int:
    return v4.main()


if __name__ == "__main__":
    raise SystemExit(main())
