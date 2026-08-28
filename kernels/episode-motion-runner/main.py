#!/usr/bin/env python3
"""Batch image-to-video runner for one complete Animation Factory episode.

Inputs:
- episode-job.json
- stills/*.png

Outputs:
- /kaggle/working/earth-needs-help-e001-s<shot>.mp4
- /kaggle/working/earth-needs-help-e001-motion-manifest.json
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = Path('/kaggle/working')
JOB_PATH = ROOT / 'episode-job.json'
MANIFEST_PATH = WORK / 'earth-needs-help-e001-motion-manifest.json'


def run(args: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(args, cwd=str(cwd or ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    out = proc.stdout.strip()
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(args[:4])}\n{out[-6000:]}")
    return out


def install_ltx() -> Path:
    repo = WORK / 'LTX-Video'
    if not repo.exists():
        run(['git', 'clone', '--depth', '1', 'https://github.com/Lightricks/LTX-Video.git', str(repo)])
    run([sys.executable, '-m', 'pip', 'install', '-q', '-e', f'{repo}[inference-script]'])
    return repo


def normalized_frames(duration: float, fps: int) -> int:
    raw = max(9, round(duration * fps))
    return ((raw - 1) // 8) * 8 + 1


def generate_ltx(repo: Path, job: dict, shot: dict, width: int, height: int, fps: int) -> dict:
    from ltx_video.inference import infer, InferenceConfig
    still = ROOT / shot['still']
    if not still.is_file():
        raise FileNotFoundError(f"Missing still: {shot['still']}")
    frames = normalized_frames(float(shot['duration_seconds']), fps)
    output_dir = WORK / f"ltx-{shot['id']}"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg = InferenceConfig(
        pipeline_config=str(repo / 'configs' / 'ltxv-2b-0.9.6-distilled.yaml'),
        prompt=shot['prompt'],
        negative_prompt=job.get('negative_prompt', ''),
        conditioning_media_paths=[str(still)],
        conditioning_start_frames=[0],
        conditioning_strengths=[1.0],
        height=height,
        width=width,
        num_frames=frames,
        frame_rate=fps,
        seed=int(shot.get('seed', 42)),
        output_path=str(output_dir),
        offload_to_cpu=True,
    )
    infer(config=cfg)
    candidates = sorted(output_dir.rglob('*.mp4'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError('LTX completed without producing an MP4')
    target = WORK / f"earth-needs-help-e001-s{shot['id']}.mp4"
    shutil.copy2(candidates[0], target)
    return {'success': True, 'backend': 'ltx-2b-distilled', 'file': target.name, 'frames': frames, 'fps': fps, 'width': width, 'height': height}


def generate_with_reduced_profile(repo: Path, job: dict, shot: dict, fps: int) -> dict:
    return generate_ltx(repo, job, shot, width=704, height=400, fps=max(6, min(fps, 8)))


def main() -> int:
    started = time.time()
    job = json.loads(JOB_PATH.read_text(encoding='utf-8'))
    shots = job.get('shots', [])
    if not shots:
        raise ValueError('episode-job.json has no shots')
    try:
        import torch
        gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except Exception:
        gpu = None
    repo = install_ltx()
    width = int(job.get('width', 832))
    height = int(job.get('height', 480))
    fps = int(job.get('fps', 8))
    manifest = {'show': job.get('show'), 'episode': job.get('episode'), 'title': job.get('title'), 'gpu': gpu, 'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'shots': []}
    for shot in shots:
        record = {'id': shot.get('id'), 'attempts': []}
        try:
            result = generate_ltx(repo, job, shot, width=width, height=height, fps=fps)
            record['attempts'].append({'profile': 'primary', 'status': 'success'})
            record.update(result)
        except Exception as first:
            record['attempts'].append({'profile': 'primary', 'status': 'failed', 'error': f'{type(first).__name__}: {first}'[:2500]})
            try:
                result = generate_with_reduced_profile(repo, job, shot, fps=fps)
                record['attempts'].append({'profile': 'reduced', 'status': 'success'})
                record.update(result)
            except Exception as second:
                record['attempts'].append({'profile': 'reduced', 'status': 'failed', 'error': f'{type(second).__name__}: {second}'[:2500]})
                record['success'] = False
        manifest['shots'].append(record)
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    manifest['elapsed_seconds'] = round(time.time() - started, 2)
    manifest['success'] = all(bool(s.get('success')) for s in manifest['shots'])
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2))
    return 0 if manifest['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
