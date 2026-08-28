#!/usr/bin/env python3
"""Episode 001 autonomous controller with compact Kaggle motion packaging.

Extends the self-healing v2 controller. Motion input stills are re-encoded as
compact JPEGs before upload so the Kaggle kernel source stays comfortably
below API source-size limits while retaining enough detail for image-to-video.

A persisted force_stills_retry flag can deliberately supersede an in-flight
kernel that is known to contain obsolete/broken code. A completed episode whose
GitHub Release was not confirmed is automatically rebuilt from the completed
motion kernel on the next cycle so release publication can retry.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

import episode001_orchestrator as base
import episode001_orchestrator_v2 as v2

base.MAX_STILLS_ATTEMPTS = 6
base.MAX_MOTION_ATTEMPTS = 5
base.MOTION_RUNNER = base.ROOT / "kernels" / "episode-motion-runner" / "bootstrap.py"

TARGET_SIZE = (704, 400)
TARGET_SOURCE_BYTES = 750_000
FINAL_MP4 = base.DIST_DIR / "earth-needs-help-e001-final.mp4"


def robust_stage_generated_stills(downloaded: Path) -> list[Path]:
    """Stage the completed still batch, using Kaggle's repaired bridge as Shot 001."""
    base.STILLS_DIR.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []

    shot1_target = base.STILLS_DIR / "earth-needs-help-e001-s001.png"
    repaired_refs = list(downloaded.rglob("reference.jpg")) + list(downloaded.rglob("reference.png"))
    if repaired_refs:
        base.normalize_image(repaired_refs[0], shot1_target)
        if not base.valid_image(shot1_target):
            raise RuntimeError("Repaired canonical Shot 001 bridge failed validation")
        staged.append(shot1_target)
    else:
        staged.append(base.make_shot1_still())

    for shot in base.SHOTS[1:]:
        sid = shot["id"]
        candidates = list(downloaded.rglob(f"*s{sid}.png")) + list(downloaded.rglob(f"*s{sid}.jpg"))
        if not candidates:
            raise RuntimeError(f"Stills kernel completed but Shot {sid} output was missing")
        target = base.STILLS_DIR / f"earth-needs-help-e001-s{sid}.png"
        base.normalize_image(candidates[0], target)
        if not base.valid_image(target):
            raise RuntimeError(f"Shot {sid} still failed validation")
        staged.append(target)

    return staged


base.stage_generated_stills = robust_stage_generated_stills


def encode_stills(root: Path, quality: int) -> tuple[dict[str, str], int]:
    still_dir = root / "stills"
    if still_dir.exists():
        shutil.rmtree(still_dir)
    still_dir.mkdir(parents=True)
    mapping: dict[str, str] = {}
    total = 0
    for shot in base.SHOTS:
        sid = shot["id"]
        source = base.STILLS_DIR / f"earth-needs-help-e001-s{sid}.png"
        if not source.is_file():
            raise RuntimeError(f"Cannot package motion kernel; missing still {sid}")
        target = still_dir / f"earth-needs-help-e001-s{sid}.jpg"
        with Image.open(source) as im:
            im = ImageOps.fit(im.convert("RGB"), TARGET_SIZE, method=Image.Resampling.LANCZOS)
            im.save(target, "JPEG", quality=quality, optimize=True, progressive=True)
        mapping[sid] = f"stills/{target.name}"
        total += target.stat().st_size
    return mapping, total


def compact_motion_folder(kernel_ref: str, attempt: int) -> Path:
    if not base.MOTION_RUNNER.is_file():
        raise RuntimeError("Episode motion bootstrap is missing")
    root = Path(tempfile.mkdtemp(prefix="e001-motion-compact-"))
    shutil.copy2(base.MOTION_RUNNER, root / "main.py")

    mapping, total = encode_stills(root, 82)
    if total > TARGET_SOURCE_BYTES:
        mapping, total = encode_stills(root, 70)
    if total > TARGET_SOURCE_BYTES:
        mapping, total = encode_stills(root, 58)
    if total > 950_000:
        raise RuntimeError(f"Motion still package remains too large: {total} bytes")

    job = base.motion_job()
    job["width"], job["height"] = TARGET_SIZE
    for shot in job["shots"]:
        shot["still"] = mapping[shot["id"]]
    job["packaged_stills_bytes"] = total
    (root / "episode-job.json").write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")

    slug = kernel_ref.split("/", 1)[1]
    metadata = {
        "id": kernel_ref,
        "title": slug,
        "code_file": "main.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": True,
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": []
    }
    (root / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return root


v2.build_motion_retry_folder = compact_motion_folder


def run_controller() -> int:
    state = base.load_state()

    if bool(state.pop("force_stills_retry", False)):
        reason = str(state.pop("force_stills_retry_reason", "Known-bad stills attempt was superseded after a root-cause fix."))
        state["last_status"] = "STILLS_SUPERSEDED_RETRY_REQUESTED"
        state["last_error"] = None
        v2.retry_stills(state, reason)
        base.save_state(state)
        print(json.dumps(state, indent=2))
        return 0 if state.get("phase") != "failed" else 1

    if state.get("phase") == "complete" and not bool(state.get("release_published")) and not FINAL_MP4.is_file():
        state["phase"] = "awaiting_motion"
        state["last_status"] = "FINAL_RELEASE_REBUILD_REQUIRED"
        state["last_error"] = None
        base.save_state(state)

    return v2.main()


if __name__ == "__main__":
    raise SystemExit(run_controller())
