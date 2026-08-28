#!/usr/bin/env python3
"""Generic Animation Factory image-to-video Kaggle runner.

Input files are prepared by worker.py before the kernel is pushed:
- job.json
- input-still.jpg/png/webp

Outputs:
- /kaggle/working/animation-factory-shot.mp4
- /kaggle/working/animation-factory-report.json
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
JOB = ROOT / 'job.json'
OUT_VIDEO = WORK / 'animation-factory-shot.mp4'
OUT_REPORT = WORK / 'animation-factory-report.json'


def pip_install(*packages: str) -> None:
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', *packages], check=True)


def find_still() -> Path:
    for name in ('input-still.png', 'input-still.jpg', 'input-still.jpeg', 'input-still.webp'):
        path = ROOT / name
        if path.exists():
            return path
    raise FileNotFoundError('No input-still image was supplied to the Kaggle kernel')


def normalized_frames(duration: float, fps: int) -> int:
    raw = max(9, round(duration * fps))
    return ((raw - 1) // 8) * 8 + 1


def run_ltx(job: dict, still: Path) -> dict:
    repo = WORK / 'LTX-Video'
    if not repo.exists():
        subprocess.run(['git', 'clone', '--depth', '1', 'https://github.com/Lightricks/LTX-Video.git', str(repo)], check=True)
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '-e', f'{repo}[inference-script]'], check=True)

    from ltx_video.inference import infer, InferenceConfig

    fps = int(job.get('fps', 8))
    duration = float(job.get('duration_seconds', 5))
    width = int(job.get('width', 832))
    height = int(job.get('height', 480))
    frames = normalized_frames(duration, fps)
    output_dir = WORK / 'ltx-output'
    output_dir.mkdir(exist_ok=True)

    cfg = InferenceConfig(
        pipeline_config=str(repo / 'configs' / 'ltxv-2b-0.9.6-distilled.yaml'),
        prompt=job['prompt'],
        negative_prompt=job.get('negative_prompt', ''),
        conditioning_media_paths=[str(still)],
        conditioning_start_frames=[0],
        conditioning_strengths=[1.0],
        height=height,
        width=width,
        num_frames=frames,
        frame_rate=fps,
        seed=int(job.get('seed', 42)),
        output_path=str(output_dir),
        offload_to_cpu=True,
    )
    infer(config=cfg)
    videos = sorted(output_dir.rglob('*.mp4'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not videos:
        raise RuntimeError('LTX completed without producing an MP4')
    shutil.copy2(videos[0], OUT_VIDEO)
    return {'backend': 'ltx-2b-distilled', 'frames': frames, 'fps': fps, 'width': width, 'height': height}


def run_i2vgen(job: dict, still: Path) -> dict:
    pip_install('--upgrade', 'diffusers', 'transformers', 'accelerate', 'imageio[ffmpeg]', 'safetensors', 'Pillow')
    import torch
    from PIL import Image, ImageOps
    from diffusers import I2VGenXLPipeline
    from diffusers.utils import export_to_video

    width = min(int(job.get('width', 704)), 704)
    height = min(int(job.get('height', 480)), 480)
    image = Image.open(still).convert('RGB')
    image = ImageOps.fit(image, (width, height))
    pipe = I2VGenXLPipeline.from_pretrained('ali-vilab/i2vgen-xl', torch_dtype=torch.float16, variant='fp16')
    pipe.enable_model_cpu_offload()
    pipe.enable_attention_slicing()
    generator = torch.Generator(device='cpu').manual_seed(int(job.get('seed', 42)))
    frames = pipe(
        prompt=job['prompt'],
        negative_prompt=job.get('negative_prompt', ''),
        image=image,
        num_inference_steps=30,
        guidance_scale=7.5,
        generator=generator,
        height=height,
        width=width,
        target_fps=int(job.get('fps', 8)),
    ).frames[0]
    export_to_video(frames, str(OUT_VIDEO), fps=int(job.get('fps', 8)))
    return {'backend': 'i2vgen-xl', 'frames': len(frames), 'fps': int(job.get('fps', 8)), 'width': width, 'height': height}


def run_svd(job: dict, still: Path) -> dict:
    pip_install('--upgrade', 'diffusers', 'transformers', 'accelerate', 'imageio[ffmpeg]', 'safetensors', 'Pillow')
    import torch
    from PIL import Image, ImageOps
    from diffusers import StableVideoDiffusionPipeline
    from diffusers.utils import export_to_video

    image = Image.open(still).convert('RGB')
    image = ImageOps.fit(image, (1024, 576))
    pipe = StableVideoDiffusionPipeline.from_pretrained(
        'stabilityai/stable-video-diffusion-img2vid-xt', torch_dtype=torch.float16, variant='fp16'
    )
    pipe.enable_model_cpu_offload()
    pipe.enable_attention_slicing()
    pipe.unet.enable_forward_chunking()
    generator = torch.manual_seed(int(job.get('seed', 42)))
    frames = pipe(image, decode_chunk_size=8, generator=generator, motion_bucket_id=100, noise_aug_strength=0.04).frames[0]
    export_to_video(frames, str(OUT_VIDEO), fps=int(job.get('fps', 8)))
    return {'backend': 'svd-xt', 'frames': len(frames), 'fps': int(job.get('fps', 8)), 'width': 1024, 'height': 576}


def main() -> int:
    started = time.time()
    job = json.loads(JOB.read_text(encoding='utf-8'))
    still = find_still()

    try:
        import torch
        gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except Exception:
        gpu = None

    model_order = [job.get('model', 'ltx-2b-distilled'), *job.get('fallback_models', ['i2vgen-xl', 'svd-xt'])]
    seen = set()
    attempts = []
    success = None

    for model in model_order:
        if model in seen:
            continue
        seen.add(model)
        try:
            if model == 'ltx-2b-distilled':
                success = run_ltx(job, still)
            elif model == 'i2vgen-xl':
                success = run_i2vgen(job, still)
            elif model == 'svd-xt':
                success = run_svd(job, still)
            else:
                raise ValueError(f'Unsupported model: {model}')
            attempts.append({'backend': model, 'status': 'success'})
            break
        except Exception as exc:
            attempts.append({'backend': model, 'status': 'failed', 'error': str(exc)[:2000]})

    report = {
        'show': job.get('show'),
        'episode': job.get('episode'),
        'shot': job.get('shot'),
        'job_id': job.get('job_id'),
        'gpu': gpu,
        'success': bool(success),
        'attempts': attempts,
        'elapsed_seconds': round(time.time() - started, 2),
    }
    if success:
        report.update(success)
        report['output_video'] = OUT_VIDEO.name

    OUT_REPORT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
