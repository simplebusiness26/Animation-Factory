#!/usr/bin/env python3
"""Pre-Kaggle continuity asset validation for Earth Needs Help.

This runs inside GitHub Actions before Episode 001 is allowed to submit a GPU job.
It verifies that every user-approved visual reference exists, base64-decodes,
matches its locked decoded SHA-256, and opens successfully as an image.
"""
# Recovery trigger: resubmit Episode 001 after the pinned IP-Adapter compatibility fix.
from __future__ import annotations

import base64
import hashlib
import io
import json
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "shows" / "earth-needs-help" / "continuity-manifest.json"
STATE = ROOT / "automation" / "episode001-state.json"


def fail(message: str) -> int:
    try:
        state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else {}
        state.update({
            "episode": "001",
            "title": "The Great Earth Emergency",
            "phase": "blocked_continuity",
            "stills_attempts": 0,
            "motion_attempts": 0,
            "last_status": "CONTINUITY_REFERENCE_PREFLIGHT_FAILED",
            "last_error": message,
            "continuity_gate": "blocked",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass
    print(f"CANON PREFLIGHT FAILED: {message}")
    return 2


def main() -> int:
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception as exc:
        return fail(f"continuity manifest unreadable: {type(exc).__name__}: {exc}")

    if manifest.get("status") != "locked":
        return fail(f"continuity manifest status is {manifest.get('status')!r}, not 'locked'")
    pack = manifest.get("reference_pack") or {}
    if pack.get("status") != "locked":
        return fail(f"reference pack status is {pack.get('status')!r}, not 'locked'")

    cast = manifest.get("canonical_cast") or {}
    if not cast:
        return fail("canonical_cast is empty")

    checked = []
    for name, spec in cast.items():
        rel = str(spec.get("reference") or "").strip()
        expected = str(spec.get("decoded_sha256") or "").strip().lower()
        if not rel or not expected:
            return fail(f"{name}: missing reference path or decoded_sha256")
        path = ROOT / rel
        if not path.is_file():
            return fail(f"{name}: reference file missing: {rel}")
        try:
            encoded = path.read_text(encoding="utf-8").strip()
            raw = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            return fail(f"{name}: invalid base64 in {rel}: {type(exc).__name__}: {exc}")
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            return fail(f"{name}: decoded SHA-256 mismatch: expected {expected}, got {actual}")
        try:
            image = Image.open(io.BytesIO(raw))
            image.load()
            image = image.convert("RGB")
        except Exception as exc:
            return fail(f"{name}: image unreadable: {type(exc).__name__}: {exc}")
        if image.width < 64 or image.height < 64:
            return fail(f"{name}: reference image unexpectedly small: {image.width}x{image.height}")
        checked.append({"name": name, "size": [image.width, image.height], "sha256": actual})

    print(json.dumps({"status": "ok", "checked": checked}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
