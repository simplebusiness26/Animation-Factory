#!/usr/bin/env python3
"""Episode 001 controller v4.

Adds explicit rejected-batch recovery on top of v3 and guarantees that the
currently active still batch is copied into an archive folder before a newly
completed Kaggle still batch replaces it.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import episode001_orchestrator as base
import episode001_orchestrator_v3 as v3

CONTINUITY_QA = base.EPISODE_DIR / "continuity-qa.json"
ARCHIVE_ROOT = base.STILLS_DIR / "archive"
_ORIGINAL_STAGE = base.stage_generated_stills


def _qa_payload() -> dict:
    if not CONTINUITY_QA.is_file():
        return {}
    try:
        return json.loads(CONTINUITY_QA.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _batch_id() -> str:
    qa = _qa_payload()
    rows = qa.get("shots") or []
    hashes = [str(row.get("sha256") or "")[:8] for row in rows if row.get("sha256")]
    if hashes:
        return "rejected-" + "-".join(hashes[:2])
    return "superseded-" + time.strftime("%Y%m%d-%H%M%S", time.gmtime())


def archive_current_stills() -> Path | None:
    existing = []
    for shot in base.SHOTS:
        p = base.STILLS_DIR / f"earth-needs-help-e001-s{shot['id']}.png"
        if p.is_file():
            existing.append(p)
    if not existing:
        return None

    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    target = ARCHIVE_ROOT / _batch_id()
    suffix = 2
    while target.exists():
        target = ARCHIVE_ROOT / f"{_batch_id()}-{suffix}"
        suffix += 1
    target.mkdir(parents=True)
    for p in existing:
        shutil.copy2(p, target / p.name)
    if CONTINUITY_QA.is_file():
        shutil.copy2(CONTINUITY_QA, target / "continuity-qa.json")
    return target


def stage_with_archive(downloaded: Path):
    archive_current_stills()
    return _ORIGINAL_STAGE(downloaded)


base.stage_generated_stills = stage_with_archive


def normalize_explicit_rejection(state: dict) -> bool:
    qa = _qa_payload()
    gate_rejected = str(state.get("continuity_gate") or "").lower() == "rejected"
    qa_rejected = str(qa.get("status") or "").lower() == "rejected"
    if not gate_rejected and not qa_rejected:
        return False

    # Persist the human rejection in the exact hash-bound review file, then move
    # the controller back into its still-regeneration path. v3 will immediately
    # submit the upgraded layered still kernel on this same controller cycle.
    if qa and not qa_rejected:
        qa["status"] = "rejected"
        qa["reviewed_by"] = qa.get("reviewed_by") or "user"
        qa["review_notes"] = qa.get("review_notes") or "Batch rejected for visual quality/continuity; rebuild with layered 2.5D still pipeline."
        CONTINUITY_QA.write_text(json.dumps(qa, indent=2) + "\n", encoding="utf-8")

    state["phase"] = "blocked_continuity"
    state["last_status"] = "CONTINUITY_BATCH_REJECTED_REBUILD_REQUIRED"
    state["last_error"] = None
    state["stills_attempts"] = 0
    state["motion_attempts"] = 0
    base.save_state(state)
    return True


def main() -> int:
    state = base.load_state()
    normalize_explicit_rejection(state)
    return v3.run_controller()


if __name__ == "__main__":
    raise SystemExit(main())
