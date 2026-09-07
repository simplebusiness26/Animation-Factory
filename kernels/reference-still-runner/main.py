#!/usr/bin/env python3
"""Generate continuity-locked reference stills with FLUX.2 [klein] 4B on Kaggle."""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

WORK = Path('/kaggle/working')
SOURCE_ROOT = Path(os.environ.get('ANIMATION_SOURCE_ROOT', Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(SOURCE_ROOT))
from pipeline.image_router import load_json, plan_job, verified_image
from pipeline.production_guard import require_launch_allowed

JOB = SOURCE_ROOT / os.environ.get('ANIMATION_IMAGE_JOB', 'shows/earth-needs-help/episodes/001-great-earth-emergency/episode001-image-job.json')
REPORT = WORK / 'animation-factory-image-report.json'


def install_runtime() -> None:
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '-r',
                    str(SOURCE_ROOT / 'kernels/reference-still-runner/requirements.txt')], check=True)


def write_report(payload: dict) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(payload, indent=2), flush=True)


def load_locked_reference(manifest: dict, name: str):
    from PIL import Image

    cast = manifest.get('canonical_cast') or {}
    item = cast.get(name)
    if not item:
        raise RuntimeError(f'CONTINUITY_BLOCK: no canonical reference entry for {name}')
    path = str(item.get('reference') or '')
    expected = str(item.get('decoded_sha256') or '')
    if not path or not expected:
        raise RuntimeError(f'CONTINUITY_BLOCK: incomplete canonical entry for {name}')

    raw = verified_image(SOURCE_ROOT, path, expected, encoded=True)
    image = Image.open(io.BytesIO(raw)).convert('RGB')
    image.load()
    return image, str(item.get('identity') or name)


def build_prompt(job: dict, shot: dict, identities: list[str]) -> str:
    identity_note = '; '.join(identities)
    return (
        f"{job['style_lock']}. {job['reference_rule']} "
        f"Reference identities: {identity_note}. "
        f"Shot: {shot['prompt']} "
        "Use the supplied reference images only as identity/style anchors for the named recurring characters. "
        "Do not redesign, recolour, resize, replace or duplicate them. Keep anatomy clean, faces readable, "
        "all required characters present, and leave physical room for the intended animation."
    )


def load_pipeline(job: dict, revision: str):
    # Kaggle provides torch. Check CUDA before a lengthy dependency/model install.
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('GPU_BLOCK: CUDA GPU is required')
    install_runtime()
    from diffusers import Flux2KleinPipeline
    major, _minor = torch.cuda.get_device_capability(0)
    dtype = torch.bfloat16 if major >= 8 else torch.float16
    pipe = Flux2KleinPipeline.from_pretrained(job['model'], revision=revision, torch_dtype=dtype)
    pipe.enable_model_cpu_offload()
    pipe.vae.enable_tiling()
    return pipe, torch, dtype


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result = {
        'success': False,
        'pipeline': 'hybrid-image-v1/flux2-klein-4b',
        'provider': 'kaggle',
        'shots': [],
    }
    try:
        require_launch_allowed(SOURCE_ROOT)
        job = load_json(JOB)
        config = load_json(SOURCE_ROOT / 'pipeline/image-generation.json')
        plan = plan_job(job, config, root=SOURCE_ROOT)
        if plan['status'] != 'ready':
            raise RuntimeError('IMAGE_PREFLIGHT_BLOCK: ' + json.dumps(plan))
        manifest = load_json(SOURCE_ROOT / job['continuity_manifest'])
        result['source_commit'] = os.environ.get('ANIMATION_SOURCE_COMMIT')
        result['model_revision'] = plan['model_revision']
        decisions = {row['id']: row for row in plan['shots']}
        needs_gpu = any(row['automated'] for row in plan['shots'])
        pipe = None
        if needs_gpu:
            pipe, torch, dtype = load_pipeline(job, plan['model_revision'])
            result['gpu'] = torch.cuda.get_device_name(0)
            result['dtype'] = str(dtype)
        result['model'] = job['model']

        for shot in job.get('shots') or []:
            try:
                decision = decisions[shot['id']]
                out = WORK / f"earth-needs-help-e001-s{shot['id']}.png"
                if decision.get('approved_input_path'):
                    from PIL import Image
                    with Image.open(SOURCE_ROOT / decision['approved_input_path']) as imported:
                        imported.convert('RGB').save(out)
                    result['shots'].append({'id': shot['id'], 'success': True, 'file': out.name,
                                            'qa_status': 'pending', 'reused_approved_input': True,
                                            'source_sha256': decision['approved_input_sha256'],
                                            'sha256': hashlib.sha256(out.read_bytes()).hexdigest()})
                    write_report(result)
                    continue
                refs = []
                identities = []
                for name in shot.get('characters') or []:
                    image, identity = load_locked_reference(manifest, name)
                    refs.append(image)
                    identities.append(f'{name}: {identity}')

                prompt = build_prompt(job, shot, identities)
                kwargs = {
                    'prompt': prompt,
                    'height': int(job.get('height', 576)),
                    'width': int(job.get('width', 1024)),
                    'guidance_scale': float(job.get('guidance_scale', 1.0)),
                    'num_inference_steps': int(job.get('steps', 4)),
                    'generator': torch.Generator(device='cuda').manual_seed(int(shot.get('seed', 0))),
                }
                if refs:
                    kwargs['image'] = refs

                # Check raw pixels before PIL can hide NaNs as a black image.
                import numpy as np
                from PIL import Image
                pixels = np.asarray(pipe(**kwargs, output_type='np').images[0])
                if pixels.shape != (job['height'], job['width'], 3) or not np.isfinite(pixels).all():
                    raise RuntimeError('IMAGE_OUTPUT_BLOCK: non-finite pixels or incorrect output dimensions')
                if float(pixels.max() - pixels.min()) < 1 / 255:
                    raise RuntimeError('IMAGE_OUTPUT_BLOCK: blank output; check model precision')
                image = Image.fromarray((np.clip(pixels, 0, 1) * 255).round().astype('uint8'))
                out = WORK / f"earth-needs-help-e001-s{shot['id']}.png"
                image.save(out)
                result['shots'].append({
                    'id': shot['id'],
                    'success': True,
                    'file': out.name,
                    'characters': shot.get('characters') or [],
                    'reference_count': len(refs),
                    'seed': int(shot.get('seed', 0)),
                    'qa_status': 'pending',
                    'sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
                })
                print(f"STILL {shot['id']} COMPLETE -> {out.name}", flush=True)
                write_report(result)
            except Exception as exc:
                traceback.print_exc()
                result['shots'].append({
                    'id': shot.get('id'),
                    'success': False,
                    'error': f'{type(exc).__name__}: {exc}'[:3000],
                })
                write_report(result)
                return 3

        result['elapsed_seconds'] = round(time.time() - started, 2)
        result['success'] = bool(result['shots']) and all(x.get('success') for x in result['shots'])
        write_report(result)
        return 0 if result['success'] else 1
    except Exception as exc:
        traceback.print_exc()
        result['error'] = f'{type(exc).__name__}: {exc}'[:3000]
        result['elapsed_seconds'] = round(time.time() - started, 2)
        write_report(result)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
