#!/usr/bin/env python3
"""Batch image-to-video runner for one complete Animation Factory episode.

Inputs:
- episode-job.json
- stills/*.jpg or *.png

Outputs:
- /kaggle/working/earth-needs-help-e001-s<shot>.mp4
- /kaggle/working/earth-needs-help-e001-motion-manifest.json

Recovery order per shot:
1. LTX-Video primary profile
2. LTX-Video reduced profile
3. I2VGen-XL
4. Stable Video Diffusion XT
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
_I2V_PIPE = None
_SVD_PIPE = None


def run(args: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(args, cwd=str(cwd or ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    out = proc.stdout.strip()
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(args[:4])}\n{out[-6000:]}")
    return out


def pip_install(*packages: str) -> None:
    run([sys.executable, '-m', 'pip', 'install', '-q', '--upgrade', *packages])


def install_ltx() -> Path:
    repo = WORK / 'LTX-Video'
    if not repo.exists():
        run(['git', 'clone', '--depth', '1', 'https://github.com/Lightricks/LTX-Video.git', str(repo)])
    run([sys.executable, '-m', 'pip', 'install', '-q', '-e', f'{repo}[inference-script]'])
    return repo


def normalized_frames(duration: float, fps: int) -> int:
    raw = max(9, round(duration * fps))
    return ((raw - 1) // 8) * 8 + 1


def shot_still(shot: dict) -> Path:
    still = ROOT / shot['still']
    if not still.is_file():
        raise FileNotFoundError(f"Missing still: {shot['still']}")
    return still


def output_path(shot: dict) -> Path:
    return WORK / f"earth-needs-help-e001-s{shot['id']}.mp4"


def generate_ltx(repo: Path, job: dict, shot: dict, width: int, height: int, fps: int) -> dict:
    from ltx_video.inference import infer, InferenceConfig
    still = shot_still(shot)
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
    target = output_path(shot)
    shutil.copy2(candidates[0], target)
    return {'success': True, 'backend': 'ltx-2b-distilled', 'file': target.name, 'frames': frames, 'fps': fps, 'width': width, 'height': height}


def generate_with_reduced_profile(repo: Path, job: dict, shot: dict, fps: int) -> dict:
    return generate_ltx(repo, job, shot, width=704, height=400, fps=max(6, min(fps, 8)))


def get_i2v_pipe():
    global _I2V_PIPE
    if _I2V_PIPE is not None:
        return _I2V_PIPE
    pip_install('diffusers', 'transformers', 'accelerate', 'imageio[ffmpeg]', 'safetensors', 'Pillow')
    import torch
    from diffusers import I2VGenXLPipeline
    pipe = I2VGenXLPipeline.from_pretrained('ali-vilab/i2vgen-xl', torch_dtype=torch.float16, variant='fp16')
    pipe.enable_model_cpu_offload()
    pipe.enable_attention_slicing()
    _I2V_PIPE = pipe
    return pipe


def generate_i2vgen(job: dict, shot: dict, fps: int) -> dict:
    import torch
    from PIL import Image, ImageOps
    from diffusers.utils import export_to_video
    pipe = get_i2v_pipe()
    width, height = 704, 400
    image = ImageOps.fit(Image.open(shot_still(shot)).convert('RGB'), (width, height))
    generator = torch.Generator(device='cpu').manual_seed(int(shot.get('seed', 42)))
    frames = pipe(
        prompt=shot['prompt'],
        negative_prompt=job.get('negative_prompt', ''),
        image=image,
        num_inference_steps=28,
        guidance_scale=7.0,
        generator=generator,
        height=height,
        width=width,
        target_fps=max(6, min(fps, 8)),
    ).frames[0]
    target = output_path(shot)
    export_to_video(frames, str(target), fps=max(6, min(fps, 8)))
    return {'success': True, 'backend': 'i2vgen-xl', 'file': target.name, 'frames': len(frames), 'fps': max(6, min(fps, 8)), 'width': width, 'height': height}


def get_svd_pipe():
    global _SVD_PIPE
    if _SVD_PIPE is not None:
        return _SVD_PIPE
    pip_install('diffusers', 'transformers', 'accelerate', 'imageio[ffmpeg]', 'safetensors', 'Pillow')
    import torch
    from diffusers import StableVideoDiffusionPipeline
    pipe = StableVideoDiffusionPipeline.from_pretrained(
        'stabilityai/stable-video-diffusion-img2vid-xt', torch_dtype=torch.float16, variant='fp16'
    )
    pipe.enable_model_cpu_offload()
    pipe.enable_attention_slicing()
    pipe.unet.enable_forward_chunking()
    _SVD_PIPE = pipe
    return pipe


def generate_svd(job: dict, shot: dict, fps: int) -> dict:
    import torch
    from PIL import Image, ImageOps
    from diffusers.utils import export_to_video
    pipe = get_svd_pipe()
    image = ImageOps.fit(Image.open(shot_still(shot)).convert('RGB'), (1024, 576))
    generator = torch.manual_seed(int(shot.get('seed', 42)))
    frames = pipe(
        image,
        decode_chunk_size=6,
        generator=generator,
        motion_bucket_id=100,
        noise_aug_strength=0.035,
    ).frames[0]
    target = output_path(shot)
    export_to_video(frames, str(target), fps=max(6, min(fps, 8)))
    return {'success': True, 'backend': 'svd-xt', 'file': target.name, 'frames': len(frames), 'fps': max(6, min(fps, 8)), 'width': 1024, 'height': 576}


def try_backend(record: dict, name: str, fn):
    try:
        result = fn()
        record['attempts'].append({'profile': name, 'status': 'success'})
        record.update(result)
        return True
    except Exception as exc:
        record['attempts'].append({'profile': name, 'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'[:3500]})
        return False


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

    ltx_repo = None
    ltx_install_error = None
    try:
        ltx_repo = install_ltx()
    except Exception as exc:
        ltx_install_error = f'{type(exc).__name__}: {exc}'[:3500]

    width = int(job.get('width', 704))
    height = int(job.get('height', 400))
    fps = int(job.get('fps', 8))
    manifest = {
        'show': job.get('show'),
        'episode': job.get('episode'),
        'title': job.get('title'),
        'gpu': gpu,
        'ltx_install_error': ltx_install_error,
        'packaged_stills_bytes': job.get('packaged_stills_bytes'),
        'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'shots': []
    }

    for shot in shots:
        record = {'id': shot.get('id'), 'attempts': []}
        success = False
        if ltx_repo is not None:
            success = try_backend(record, 'ltx-primary', lambda s=shot: generate_ltx(ltx_repo, job, s, width=width, height=height, fps=fps))
            if not success:
                success = try_backend(record, 'ltx-reduced', lambda s=shot: generate_with_reduced_profile(ltx_repo, job, s, fps=fps))
        if not success:
            success = try_backend(record, 'i2vgen-xl', lambda s=shot: generate_i2vgen(job, s, fps=fps))
        if not success:
            success = try_backend(record, 'svd-xt', lambda s=shot: generate_svd(job, s, fps=fps))
        record['success'] = bool(success)
        manifest['shots'].append(record)
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

    manifest['elapsed_seconds'] = round(time.time() - started, 2)
    manifest['success'] = all(bool(s.get('success')) for s in manifest['shots'])
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2))
    return 0 if manifest['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
