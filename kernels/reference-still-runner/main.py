#!/usr/bin/env python3
"""Generate continuity-locked reference stills with FLUX.2 [klein] 4B on Kaggle."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import subprocess
import sys
import time
import traceback
import urllib.request
from pathlib import Path

WORK = Path('/kaggle/working')
BASE = 'https://raw.githubusercontent.com/simplebusiness26/Animation-Factory/main'
JOB = WORK / 'episode-image-job.json'
REPORT = WORK / 'animation-factory-image-report.json'


def fetch_bytes(path: str) -> bytes:
    with urllib.request.urlopen(f'{BASE}/{path.lstrip("/")}', timeout=120) as r:
        return r.read()


def fetch_json(path: str) -> dict:
    return json.loads(fetch_bytes(path).decode('utf-8'))


def install_runtime() -> None:
    subprocess.run(
        [
            sys.executable,
            '-m',
            'pip',
            'install',
            '-q',
            '--upgrade',
            'git+https://github.com/huggingface/diffusers.git',
            'transformers>=4.54.0',
            'accelerate>=1.6.0',
            'safetensors>=0.5.0',
            'sentencepiece',
            'protobuf',
            'Pillow',
        ],
        check=True,
    )


def write_report(payload: dict) -> None:
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

    raw = base64.b64decode(fetch_bytes(path).decode('utf-8').strip(), validate=True)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise RuntimeError(f'CONTINUITY_BLOCK: hash mismatch for {name}')
    image = Image.open(io.BytesIO(raw)).convert('RGB')
    image.load()
    return image, str(item.get('identity') or name)


def preflight(manifest: dict) -> None:
    policy = manifest.get('canon_policy') or {}
    pack = manifest.get('reference_pack') or {}
    if manifest.get('status') != 'locked' or pack.get('status') != 'locked':
        raise RuntimeError('CONTINUITY_BLOCK: reference pack is not locked')
    if not policy.get('approved_visual_reference_overrides_text'):
        raise RuntimeError('CONTINUITY_BLOCK: visual-reference priority is disabled')
    if policy.get('text_only_recurring_character_generation_allowed'):
        raise RuntimeError('CONTINUITY_BLOCK: text-only recurring identity must remain disabled')
    if not policy.get('load_references_for_every_shot'):
        raise RuntimeError('CONTINUITY_BLOCK: references must be loaded for every recurring-character shot')


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


def main() -> int:
    started = time.time()
    result = {
        'success': False,
        'pipeline': 'hybrid-image-v1/flux2-klein-4b',
        'provider': 'kaggle',
        'shots': [],
    }
    try:
        job = json.loads(JOB.read_text(encoding='utf-8'))
        manifest = fetch_json(job['continuity_manifest'])
        preflight(manifest)
        install_runtime()

        import torch
        from diffusers import Flux2KleinPipeline

        if not torch.cuda.is_available():
            raise RuntimeError('GPU_BLOCK: CUDA GPU is required')

        major, _minor = torch.cuda.get_device_capability(0)
        dtype = torch.bfloat16 if major >= 8 else torch.float16
        pipe = Flux2KleinPipeline.from_pretrained(job['model'], torch_dtype=dtype)
        pipe.enable_model_cpu_offload()

        result['gpu'] = torch.cuda.get_device_name(0)
        result['dtype'] = str(dtype)
        result['model'] = job['model']

        for shot in job.get('shots') or []:
            try:
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

                image = pipe(**kwargs).images[0]
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
