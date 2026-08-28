#!/usr/bin/env python3
"""Autonomous Episode 001 production controller.

Designed for GitHub Actions schedule runs. It:
1. waits for the Episode 001 still-generation Kaggle kernel;
2. downloads and validates stills;
3. submits one batch image-to-video Kaggle kernel for the whole episode;
4. waits for the motion kernel;
5. downloads shot MP4s, renders voices/music/SFX, QA-checks the final episode;
6. leaves a final MP4 for the workflow to publish as a GitHub Release.

State is persisted in automation/episode001-state.json.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EPISODE_DIR = ROOT / "shows" / "earth-needs-help" / "episodes" / "001-great-earth-emergency"
ASSETS = EPISODE_DIR / "assets"
STILLS_DIR = ASSETS / "stills"
STATE_PATH = ROOT / "automation" / "episode001-state.json"
LOG_DIR = ROOT / "automation" / "logs"
DIST_DIR = ROOT / "dist"
STILLS_KERNEL_DIR = ROOT / "kernels" / "earth-needs-help-e001-stills"
MOTION_RUNNER = ROOT / "kernels" / "episode-motion-runner" / "main.py"
SHOT1_B64 = ROOT / "kernels" / "earth-needs-help-e001-s001" / "input-still.b64"

OWNER = os.getenv("KAGGLE_OWNER", "").strip() or "simplebusiness"
STILLS_KERNEL = f"{OWNER}/earth-needs-help-episode-001-production-stills"
MOTION_KERNEL = f"{OWNER}/earth-needs-help-episode-001-motion"
MAX_STILLS_ATTEMPTS = 3
MAX_MOTION_ATTEMPTS = 3

SHOTS = [
    {"id": "001", "duration_seconds": 7, "prompt": "A sudden emergency alarm activates. Red warning lights begin flashing softly. Captain Pip snaps upright and urgently leans toward the control panel. Bloop gasps and bounces slightly in surprise. Zig accidentally drops his small gadget and reacts. Momo stays calm, blinking and continuing to chew. Gentle cinematic camera push forward. Natural expressive movement, no redesigns, no extra characters, preserve faces and proportions exactly."},
    {"id": "002", "duration_seconds": 7, "prompt": "Earth slowly grows larger through the window. Captain Pip points dramatically and gives a serious command. Bloop presses against the glass and wiggles with excitement. Zig quickly checks his tools. Momo waves gently at Earth. Subtle ship vibration and restrained camera movement. Preserve the exact spaceship and character designs."},
    {"id": "003", "duration_seconds": 8, "prompt": "The tiny spaceship swoops down, gently bounces through the hedge with a soft comedic boing, slides a short distance and stops crooked in the flowerbed. A harmless puff of dust and leaves rises. The hatch pops open and Bloop appears upside down for a beat. Funny physical comedy, smooth motion, no damage or danger."},
    {"id": "004", "duration_seconds": 9, "prompt": "Captain Pip takes two determined little steps toward the child and urgently gestures for directions. The child blinks, then slowly points toward a nearby tree. Bloop leans out to see where the child points. Zig raises a scanner. Momo smiles reassuringly. Natural character acting, stable camera, preserve all designs."},
    {"id": "005", "duration_seconds": 8, "prompt": "Camera tilts from the aliens up to the harmless kite, then settles back on their reaction. Captain Pip slowly raises an emergency scanner. Bloop's mouth drops open. Zig reaches for several gadgets. Momo looks puzzled. The child gives a small confused shrug. Keep motion controlled and faces consistent."},
    {"id": "006a", "duration_seconds": 6, "prompt": "Zig proudly presses a button. The rescue gadget unfolds several small mechanical arms and begins humming. Zig strikes a confident inventor pose. Bloop bounces with excitement. Captain Pip nods seriously. The child takes one small step back. Smooth harmless comedy, no violent motion."},
    {"id": "006b", "duration_seconds": 7, "prompt": "The gadget spins in a small circle, extends its arms in the wrong directions and blows leaves everywhere without hurting anyone. Bloop runs after it. Zig tries to catch it. Captain Pip points urgently. The child watches with an amused, confused expression. Momo barely moves. Fast but readable physical comedy, preserve anatomy and character identity."},
    {"id": "007", "duration_seconds": 10, "prompt": "Hold a brief quiet beat. Momo looks at the kite, looks at everyone else, then gently reaches up, lifts the kite free from the branch and hands it to the child. The child smiles gratefully. The rest of the crew stays frozen in stunned silence. Captain Pip slowly lowers his scanner. Very gentle camera move, warm wholesome timing."},
    {"id": "008", "duration_seconds": 10, "prompt": "The child starts flying the kite. Bloop hops excitedly. Zig proudly adjusts his goggles. Momo claps slowly. Captain Pip plants his hands on his hips in a tiny heroic pose. Warm celebratory movement, gentle camera pull back, preserve all character designs."},
    {"id": "009", "duration_seconds": 8, "prompt": "The pigeon quickly snatches Bloop's snack and takes two small hops away. Bloop freezes, slowly looks down at his empty hand, then turns toward the pigeon in disbelief. The whole alien crew turns. Captain Pip immediately raises the emergency scanner as if a major crisis has begun. Quick comedic push-in at the end. No aggressive chase, no frightening movement."},
]

GLOBAL_NEGATIVE = "blurry, distorted, deformed, extra arms, extra legs, duplicate character, missing character, wrong colours, changed costume, changed species, text, watermark, logo, scary, horror, violent, photorealistic human skin, inconsistent face, melted anatomy, extreme camera motion, background morphing"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run(args: list[str], cwd: Path | None = None, check: bool = True) -> str:
    proc = subprocess.run(args, cwd=str(cwd or ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    out = proc.stdout.strip()
    if check and proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(args[:4])}\n{out[-6000:]}")
    return out


def default_state() -> dict:
    return {"episode": "001", "title": "The Great Earth Emergency", "phase": "awaiting_stills", "stills_kernel": STILLS_KERNEL, "stills_attempts": 0, "motion_kernel": MOTION_KERNEL, "motion_attempts": 0, "last_status": None, "last_error": None, "updated_at": now(), "release_tag": "earth-needs-help-e001"}


def load_state() -> dict:
    if not STATE_PATH.exists():
        return default_state()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = default_state()
    base = default_state()
    base.update(data)
    return base


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now()
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def log(name: str, text: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / name).write_text(text + "\n", encoding="utf-8")


def status_of(kernel: str) -> str:
    out = run(["kaggle", "kernels", "status", kernel])
    log("latest-kaggle-status.txt", out)
    m = re.search(r'KernelWorkerStatus\.([A-Z_]+)', out)
    return m.group(1) if m else out[-200:].strip()


def download_output(kernel: str, target: Path) -> str:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    out = run(["kaggle", "kernels", "output", kernel, "-p", str(target), "-o"])
    log("latest-kaggle-output.txt", out)
    return out


def valid_image(path: Path) -> bool:
    try:
        from PIL import Image, ImageFile
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        with Image.open(path) as im:
            im.load()
            return im.width >= 256 and im.height >= 144
    except Exception:
        return False


def normalize_image(source: Path, target: Path) -> None:
    from PIL import Image, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as im:
        im = im.convert("RGB")
        im.save(target, format="PNG", optimize=True)


def make_shot1_still() -> Path:
    STILLS_DIR.mkdir(parents=True, exist_ok=True)
    target = STILLS_DIR / "earth-needs-help-e001-s001.png"
    raw = base64.b64decode(SHOT1_B64.read_text(encoding="utf-8").strip())
    with tempfile.TemporaryDirectory(prefix="e001-s001-") as td:
        source = Path(td) / "shot1.jpg"
        source.write_bytes(raw)
        normalize_image(source, target)
    if not valid_image(target):
        raise RuntimeError("Could not recover the approved Shot 001 bridge image")
    return target


def stage_generated_stills(downloaded: Path) -> list[Path]:
    STILLS_DIR.mkdir(parents=True, exist_ok=True)
    staged = [make_shot1_still()]
    for shot in SHOTS[1:]:
        sid = shot["id"]
        candidates = list(downloaded.rglob(f"*s{sid}.png")) + list(downloaded.rglob(f"*s{sid}.jpg"))
        if not candidates:
            raise RuntimeError(f"Stills kernel completed but Shot {sid} output was missing")
        target = STILLS_DIR / f"earth-needs-help-e001-s{sid}.png"
        normalize_image(candidates[0], target)
        if not valid_image(target):
            raise RuntimeError(f"Shot {sid} still failed validation")
        staged.append(target)
    return staged


def motion_job() -> dict:
    return {"show": "Earth Needs Help", "episode": "001", "title": "The Great Earth Emergency", "fps": 8, "width": 832, "height": 480, "negative_prompt": GLOBAL_NEGATIVE, "shots": [{**shot, "still": f"stills/earth-needs-help-e001-s{shot['id']}.png", "seed": 6100 + i} for i, shot in enumerate(SHOTS)]}


def build_motion_kernel() -> Path:
    if not MOTION_RUNNER.is_file():
        raise RuntimeError("Episode motion runner is missing")
    missing = [shot["id"] for shot in SHOTS if not (STILLS_DIR / f"earth-needs-help-e001-s{shot['id']}.png").is_file()]
    if missing:
        raise RuntimeError(f"Cannot build motion kernel; missing stills: {', '.join(missing)}")
    root = Path(tempfile.mkdtemp(prefix="e001-motion-kernel-"))
    shutil.copy2(MOTION_RUNNER, root / "main.py")
    stills = root / "stills"
    stills.mkdir()
    for shot in SHOTS:
        src = STILLS_DIR / f"earth-needs-help-e001-s{shot['id']}.png"
        shutil.copy2(src, stills / src.name)
    (root / "episode-job.json").write_text(json.dumps(motion_job(), indent=2) + "\n", encoding="utf-8")
    metadata = {"id": MOTION_KERNEL, "title": "Earth Needs Help Episode 001 Motion", "code_file": "main.py", "language": "python", "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True, "dataset_sources": [], "competition_sources": [], "kernel_sources": [], "model_sources": []}
    (root / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return root


def submit_motion(state: dict) -> None:
    folder = build_motion_kernel()
    try:
        out = run(["kaggle", "kernels", "push", "-p", str(folder), "--accelerator", "NvidiaTeslaT4"])
        log("motion-submit.txt", out)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    state["motion_attempts"] = int(state.get("motion_attempts", 0)) + 1
    state["phase"] = "awaiting_motion"
    state["last_status"] = "MOTION_SUBMITTED"
    state["last_error"] = None


def resubmit_stills(state: dict) -> None:
    out = run(["kaggle", "kernels", "push", "-p", str(STILLS_KERNEL_DIR), "--accelerator", "NvidiaTeslaT4"])
    log("stills-resubmit.txt", out)
    state["stills_attempts"] = int(state.get("stills_attempts", 0)) + 1
    state["last_status"] = "STILLS_RESUBMITTED"
    state["last_error"] = None


def verify_motion_outputs(folder: Path) -> list[Path]:
    videos = []
    for shot in SHOTS:
        sid = shot["id"]
        candidates = list(folder.rglob(f"*s{sid}.mp4"))
        if not candidates:
            raise RuntimeError(f"Motion kernel completed but Shot {sid} MP4 was missing")
        path = candidates[0]
        if path.stat().st_size < 50_000:
            raise RuntimeError(f"Shot {sid} MP4 is unexpectedly small")
        videos.append(path)
    return videos


def render_final(motion_output: Path) -> Path:
    verify_motion_outputs(motion_output)
    script = ROOT / "automation" / "render_episode001.py"
    if not script.is_file():
        raise RuntimeError("Final episode renderer is missing")
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    out = run([sys.executable, str(script), str(motion_output)], cwd=ROOT)
    log("render-final.txt", out)
    final = DIST_DIR / "earth-needs-help-e001-final.mp4"
    if not final.is_file() or final.stat().st_size < 200_000:
        raise RuntimeError("Final renderer did not produce a valid-sized MP4")
    return final


def handle_awaiting_stills(state: dict) -> None:
    status = status_of(STILLS_KERNEL)
    state["last_status"] = f"STILLS_{status}"
    if status in {"QUEUED", "RUNNING"}:
        return
    if status == "COMPLETE":
        with tempfile.TemporaryDirectory(prefix="e001-stills-output-") as td:
            out_dir = Path(td)
            download_output(STILLS_KERNEL, out_dir)
            stage_generated_stills(out_dir)
        submit_motion(state)
        return
    if status == "ERROR":
        try:
            with tempfile.TemporaryDirectory(prefix="e001-stills-error-") as td:
                download_output(STILLS_KERNEL, Path(td))
        except Exception as exc:
            log("stills-error-output.txt", str(exc))
        attempts = int(state.get("stills_attempts", 0))
        if attempts < MAX_STILLS_ATTEMPTS:
            resubmit_stills(state)
        else:
            state["phase"] = "failed"
            state["last_error"] = f"Stills generation failed after {attempts} automatic retries."
        return
    state["last_error"] = f"Unrecognised stills status: {status}"


def handle_awaiting_motion(state: dict) -> None:
    status = status_of(MOTION_KERNEL)
    state["last_status"] = f"MOTION_{status}"
    if status in {"QUEUED", "RUNNING"}:
        return
    if status == "COMPLETE":
        with tempfile.TemporaryDirectory(prefix="e001-motion-output-") as td:
            output = Path(td)
            download_output(MOTION_KERNEL, output)
            final = render_final(output)
            state["final_file"] = str(final.relative_to(ROOT))
        state["phase"] = "complete"
        state["last_status"] = "FINAL_QA_PASS"
        state["last_error"] = None
        return
    if status == "ERROR":
        try:
            with tempfile.TemporaryDirectory(prefix="e001-motion-error-") as td:
                download_output(MOTION_KERNEL, Path(td))
        except Exception as exc:
            log("motion-error-output.txt", str(exc))
        attempts = int(state.get("motion_attempts", 0))
        if attempts < MAX_MOTION_ATTEMPTS:
            submit_motion(state)
        else:
            state["phase"] = "failed"
            state["last_error"] = f"Motion generation failed after {attempts} automatic retries."
        return
    state["last_error"] = f"Unrecognised motion status: {status}"


def main() -> int:
    STILLS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    try:
        phase = state.get("phase")
        if phase == "awaiting_stills":
            handle_awaiting_stills(state)
        elif phase == "awaiting_motion":
            handle_awaiting_motion(state)
        elif phase == "complete":
            print("Episode 001 is complete; nothing to do.")
        elif phase == "failed":
            print(f"Episode 001 automation is halted: {state.get('last_error')}")
        else:
            state["phase"] = "failed"
            state["last_error"] = f"Unknown phase: {phase}"
    except Exception as exc:
        state["last_error"] = f"{type(exc).__name__}: {exc}"
        print(state["last_error"])
    finally:
        save_state(state)
    print(json.dumps(state, indent=2))
    return 0 if state.get("phase") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
