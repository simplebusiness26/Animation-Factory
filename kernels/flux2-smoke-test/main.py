#!/usr/bin/env python3
"""Isolated FLUX.2 smoke test for Animation Factory.

This kernel is intentionally NOT the Episode 001 production runner. It generates
one disposable multi-character test still from the immutable locked references
and writes only to /kaggle/working. It never stages episode assets or changes the
persisted Episode 001 pause state.
"""
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
REPORT = WORK / 'flux2-smoke-report.json'
OUTPUT = WORK / 'flux2-smoke-shot-002.png'
SOURCE_COMMIT = 'b568cf2f1d68e61c46b59e8b672774d6d222ee42'
RAW_BASE = f'https://raw.githubusercontent.com/simplebusiness26/Animation-Factory/{SOURCE_COMMIT}'
MANIFEST_PATH = 'shows/earth-needs-help/continuity-manifest.json'
MODEL = 'black-forest-labs/FLUX.2-klein-4B'
MODEL_REVISION = 'e7b7dc27f91deacad38e78976d1f2b499d76a294'
CHARACTERS = ['captain-pip', 'bloop', 'zig', 'momo']
WIDTH = 768
HEIGHT = 432
SEED = 42002

PROMPT = (
    "Polished bright 3D children's comedy animation, warm tactile materials, soft rounded forms, "
    "expressive readable faces, gentle cinematic lighting, strong silhouettes, safe playful environment. "
    "Inside the same colourful alien spaceship bridge, beautiful blue Earth fills the large front window. "
    "Captain Pip points dramatically toward Earth, Bloop leans excitedly toward the glass, Zig checks his "
    "inventor equipment, and Momo gives Earth a friendly wave. Warm interior light, heroic but funny framing. "
    "The four supplied reference images are the exact identity authority for Captain Pip, Bloop, Zig and Momo. "
    "Preserve each supplied character's face, colour, silhouette, proportions, clothing and accessories. "
    "Do not duplicate, merge, recolour, resize or redesign the characters. No text or logos. 16:9 landscape."
)

PINNED_PACKAGES = [
    'diffusers==0.40.0',
    'transformers==5.0.0',
    'accelerate==1.12.0',
    'safetensors==0.8.0',
    'sentencepiece==0.2.1',
    'protobuf==6.33.5',
    'Pillow==12.1.0',
    'numpy==2.2.6',
]


def fetch(path: str) -> bytes:
    with urllib.request.urlopen(f'{RAW_BASE}/{path}', timeout=120) as response:
        return response.read()


def write_report(payload: dict) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(payload, indent=2), flush=True)


def install_runtime() -> None:
    proc = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '--upgrade', *PINNED_PACKAGES],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f'pip install failed ({proc.returncode}):\n{proc.stdout[-4000:]}')


def load_refs(manifest: dict):
    from PIL import Image

    if manifest.get('status') != 'locked' or (manifest.get('reference_pack') or {}).get('status') != 'locked':
        raise RuntimeError('CONTINUITY_BLOCK: locked reference pack required')
    policy = manifest.get('canon_policy') or {}
    if not policy.get('approved_visual_reference_overrides_text') or not policy.get('load_references_for_every_shot'):
        raise RuntimeError('CONTINUITY_BLOCK: reference priority policy invalid')
    if policy.get('text_only_recurring_character_generation_allowed'):
        raise RuntimeError('CONTINUITY_BLOCK: text-only identity is forbidden')

    refs = []
    rows = []
    cast = manifest.get('canonical_cast') or {}
    for name in CHARACTERS:
        item = cast.get(name) or {}
        path = str(item.get('reference') or '')
        expected = str(item.get('decoded_sha256') or '')
        if not path or len(expected) != 64:
            raise RuntimeError(f'CONTINUITY_BLOCK: incomplete canonical entry for {name}')
        raw = base64.b64decode(fetch(path).decode('utf-8').strip(), validate=True)
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected:
            raise RuntimeError(f'CONTINUITY_BLOCK: hash mismatch for {name}')
        image = Image.open(io.BytesIO(raw)).convert('RGB')
        image.load()
        refs.append(image)
        rows.append({'name': name, 'reference': path, 'sha256': digest, 'size': list(image.size)})
    return refs, rows


def main() -> int:
    started = time.time()
    result = {
        'success': False,
        'kind': 'isolated_flux2_single_shot_smoke',
        'production_state_changed': False,
        'source_commit': SOURCE_COMMIT,
        'model': MODEL,
        'model_revision': MODEL_REVISION,
        'width': WIDTH,
        'height': HEIGHT,
        'seed': SEED,
        'characters': CHARACTERS,
    }
    try:
        manifest = json.loads(fetch(MANIFEST_PATH).decode('utf-8'))
        install_runtime()

        import numpy as np
        import torch
        from PIL import Image
        from diffusers import Flux2KleinPipeline

        if not torch.cuda.is_available():
            raise RuntimeError('GPU_BLOCK: CUDA GPU required')

        refs, ref_rows = load_refs(manifest)
        major, minor = torch.cuda.get_device_capability(0)
        dtype = torch.bfloat16 if major >= 8 else torch.float16
        result.update(
            gpu=torch.cuda.get_device_name(0),
            capability=f'{major}.{minor}',
            dtype=str(dtype),
            references=ref_rows,
        )
        write_report(result)

        pipe = Flux2KleinPipeline.from_pretrained(MODEL, revision=MODEL_REVISION, torch_dtype=dtype)
        pipe.enable_model_cpu_offload()
        if hasattr(pipe, 'vae') and hasattr(pipe.vae, 'enable_tiling'):
            pipe.vae.enable_tiling()

        generated = pipe(
            image=refs,
            prompt=PROMPT,
            height=HEIGHT,
            width=WIDTH,
            guidance_scale=1.0,
            num_inference_steps=4,
            generator=torch.Generator(device='cuda').manual_seed(SEED),
            output_type='np',
        ).images[0]
        pixels = np.asarray(generated)
        if pixels.shape != (HEIGHT, WIDTH, 3):
            raise RuntimeError(f'IMAGE_OUTPUT_BLOCK: wrong dimensions {pixels.shape}')
        if not np.isfinite(pixels).all():
            raise RuntimeError('IMAGE_OUTPUT_BLOCK: non-finite pixels')
        dynamic_range = float(pixels.max() - pixels.min())
        if dynamic_range < 1 / 255:
            raise RuntimeError('IMAGE_OUTPUT_BLOCK: blank image')

        image = Image.fromarray((np.clip(pixels, 0, 1) * 255).round().astype('uint8'))
        image.save(OUTPUT)
        digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
        result.update(
            success=True,
            output=OUTPUT.name,
            output_sha256=digest,
            output_bytes=OUTPUT.stat().st_size,
            dynamic_range=dynamic_range,
            elapsed_seconds=round(time.time() - started, 2),
            next_gate='human_visual_continuity_review',
        )
        write_report(result)
        return 0
    except Exception as exc:
        traceback.print_exc()
        result.update(
            success=False,
            error=f'{type(exc).__name__}: {exc}'[:4000],
            elapsed_seconds=round(time.time() - started, 2),
        )
        write_report(result)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
