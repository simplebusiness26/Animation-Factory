#!/usr/bin/env python3
"""Generate Earth Needs Help Episode 001 stills from locked visual canon.

Continuity rules:
- recurring character identity is never generated from text alone;
- every canon crop is fetched, base64-decoded, hash-checked and opened by Pillow
  before any model is loaded;
- the five approved crops are composed into one clean runtime reference sheet;
- that sheet is injected through SDXL IP-Adapter Plus on every shot;
- the matching h94 ViT-H CLIP image encoder is loaded explicitly (never auto-guessed);
- prompts stay compact so scene instructions are not silently truncated;
- any unreadable/mismatched reference fails closed before GPU generation.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

WORK = Path('/kaggle/working')
RAW_BASE = 'https://raw.githubusercontent.com/simplebusiness26/Animation-Factory/main/'
MANIFEST_PATH = 'shows/earth-needs-help/continuity-manifest.json'

REFERENCE_FILES = [
    ('captain-pip', 'shows/earth-needs-help/assets/characters/captain-pip.jpg.b64', 'fce0949798c906abe4282d3bfee778e98530d4750805ef704c6a26ab18bd09c6'),
    ('bloop', 'shows/earth-needs-help/assets/characters/bloop.jpg.b64', 'a324cd57f151b55e870453dbbf6a56f7bb529d938a5acc43d8b96bbb22b33e96'),
    ('zig', 'shows/earth-needs-help/assets/characters/zig.jpg.b64', 'd7b519f171e91f776f7e25d44b5a393fdb5b19bef63c885cc01c3c0ef2086c17'),
    ('momo', 'shows/earth-needs-help/assets/characters/momo.jpg.b64', '126d3cbc5da02fae3b1c2b734f0fe54d1ae44dd16bf7d3c69b2ae95cf945e356'),
    ('human-child', 'shows/earth-needs-help/assets/characters/human-child.jpg.b64', '7aa15b2a11ae15f095eaabca38252672e5828add647806971f0d438ef4417ddb'),
]

CANONICAL_LOCK = (
    'Exact reference characters: green Captain Pip, blue Bloop, purple Zig, pink Momo, '
    'brown-haired child in blue hoodie. Same faces, silhouettes, clothes and colours. '
)

NEGATIVE = (
    'text, watermark, redesign, colour swap, wrong face, wrong costume, duplicate character, '
    'extra limbs, missing limbs, deformed face, horror, photorealistic skin, blurry, low quality'
)

SHOTS = [
    {'id':'002','prompt':'Colourful alien spaceship bridge, Earth huge through front window. Pip points at Earth; Bloop leans to glass; Zig checks gadget; Momo waves. Friendly cinematic 3D animation.'},
    {'id':'003','prompt':'Sunny park. Small rounded rescue spaceship has harmlessly landed through hedge into flowers. Leaves float; Bloop peeks from hatch. Playful bright 3D comedy.'},
    {'id':'004','prompt':'Sunny park beside landed spaceship. Child meets Pip, Bloop, Zig and Momo. Pip steps forward; Zig holds scanner; child surprised but unafraid. Friendly 3D animation.'},
    {'id':'005','prompt':'Sunny park tree with colourful kite stuck high. Pip, Bloop, Zig and Momo stare up dramatically; child gives confused shrug. Friendly 3D comedy.'},
    {'id':'006a','prompt':'Base of kite tree. Zig proudly kneels beside compact colourful rescue gadget with folded arms. Pip watches; Bloop leans in; child cautious; Momo calm. Bright 3D animation.'},
    {'id':'006b','prompt':'Same tree. Rescue gadget spins harmlessly, arms pointing wrong ways, leaves flying. Bloop chases it; Zig shocked; Pip directs; child amused; Momo calm. 3D comedy.'},
    {'id':'007','prompt':'Quiet beat under tree. Momo simply reaches up with gentle tool and frees kite. Child smiles; Pip, Bloop and Zig stand stunned behind. Warm 3D animation.'},
    {'id':'008','prompt':'Sunny park celebration. Child holds rescued kite. Pip heroic pose; Bloop jumps; Zig poses proudly; Momo claps. Cheerful colourful 3D animation.'},
    {'id':'009','prompt':'Sunny park comedy. Bloop holds alien snack as ordinary grey pigeon steals it. Bloop freezes; Pip, Zig and Momo turn; child holds kite nearby. Bright 3D animation.'},
]


def fetch_raw(path: str) -> bytes:
    with urllib.request.urlopen(RAW_BASE + path, timeout=90) as response:
        return response.read()


def load_manifest() -> dict:
    return json.loads(fetch_raw(MANIFEST_PATH).decode('utf-8'))


def decode_canon_image(name: str, path: str, expected_sha256: str):
    from PIL import Image
    try:
        encoded = fetch_raw(path).decode('utf-8').strip()
        data = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise RuntimeError(f'CONTINUITY_BLOCK: {name} reference base64 is invalid: {type(exc).__name__}: {exc}') from exc
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        raise RuntimeError(f'CONTINUITY_BLOCK: {name} reference hash mismatch: {digest}')
    try:
        image = Image.open(io.BytesIO(data)).convert('RGB')
        image.load()
    except Exception as exc:
        raise RuntimeError(f'CONTINUITY_BLOCK: {name} reference is unreadable: {type(exc).__name__}: {exc}') from exc
    return image


def preflight_reference_sheet():
    from PIL import Image, ImageOps
    manifest = load_manifest()
    pack = manifest.get('reference_pack') or {}
    policy = manifest.get('canon_policy') or {}
    if manifest.get('status') != 'locked' or pack.get('status') != 'locked':
        raise RuntimeError('CONTINUITY_BLOCK: canonical reference pack is not locked')
    if not policy.get('load_references_for_every_shot'):
        raise RuntimeError('CONTINUITY_BLOCK: per-shot visual reference loading disabled')
    if policy.get('text_only_recurring_character_generation_allowed'):
        raise RuntimeError('CONTINUITY_BLOCK: text-only character generation is forbidden')
    if policy.get('silent_character_redesign_allowed'):
        raise RuntimeError('CONTINUITY_BLOCK: silent character redesign is forbidden')

    required = set(pack.get('required_files') or [])
    for _, path, _ in REFERENCE_FILES:
        if Path(path).name not in required:
            raise RuntimeError(f'CONTINUITY_BLOCK: manifest does not require {Path(path).name}')

    images = [decode_canon_image(name, path, digest) for name, path, digest in REFERENCE_FILES]
    cell_w, cell_h = 224, 280
    sheet = Image.new('RGB', (cell_w * len(images), cell_h), (238, 238, 238))
    for idx, image in enumerate(images):
        fitted = ImageOps.contain(image, (190, 240), method=Image.Resampling.LANCZOS)
        x = idx * cell_w + (cell_w - fitted.width) // 2
        y = (cell_h - fitted.height) // 2
        sheet.paste(fitted, (x, y))

    target = WORK / 'canonical-five-character-reference.jpg'
    sheet.save(target, 'JPEG', quality=96)
    return sheet, target


def install() -> None:
    subprocess.run([
        sys.executable, '-m', 'pip', 'install', '-q', '-U',
        'diffusers', 'transformers', 'accelerate', 'safetensors', 'Pillow<12'
    ], check=True)


def write_report(payload: dict) -> None:
    (WORK / 'earth-needs-help-e001-stills-manifest.json').write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(payload, indent=2), flush=True)


def main() -> int:
    started = time.time()
    try:
        master_ref, master_path = preflight_reference_sheet()
    except Exception as exc:
        write_report({'show':'Earth Needs Help','episode':'001','success':False,'status':'blocked_continuity','error':f'{type(exc).__name__}: {exc}','generated_shots':[]})
        return 2

    install()
    import torch
    from diffusers import AutoPipelineForText2Image
    from transformers import CLIPVisionModelWithProjection

    image_encoder = CLIPVisionModelWithProjection.from_pretrained(
        'h94/IP-Adapter',
        subfolder='models/image_encoder',
        torch_dtype=torch.float16,
    )

    pipe = AutoPipelineForText2Image.from_pretrained(
        'stabilityai/stable-diffusion-xl-base-1.0',
        image_encoder=image_encoder,
        torch_dtype=torch.float16,
        variant='fp16',
        use_safetensors=True,
    )
    pipe.load_ip_adapter(
        'h94/IP-Adapter',
        subfolder='sdxl_models',
        weight_name='ip-adapter-plus_sdxl_vit-h.safetensors',
    )
    pipe.set_ip_adapter_scale(0.90)

    # Do NOT use enable_model_cpu_offload() with this IP-Adapter path. Diffusers has
    # a known failure mode where offload + IP-Adapter sends tuple encoder states into
    # attention and crashes with: AttributeError: tuple object has no attribute shape.
    # A Kaggle T4 has enough VRAM for this fp16 SDXL setup at 768x432, so keep the
    # pipeline resident on CUDA and use attention slicing / VAE tiling instead.
    if not torch.cuda.is_available():
        raise RuntimeError('GPU_BLOCK: CUDA is required for the stills kernel')
    pipe.to('cuda')
    pipe.enable_attention_slicing()
    if hasattr(pipe, 'enable_vae_tiling'):
        pipe.enable_vae_tiling()

    hidden_size = int(getattr(image_encoder.config, 'hidden_size', 0))
    if hidden_size != 1280:
        raise RuntimeError(f'IP_ADAPTER_BLOCK: expected ViT-H hidden_size 1280, got {hidden_size}')

    result = {
        'show':'Earth Needs Help','episode':'001','success':False,
        'reference_mode':'five hash-validated canon crops -> runtime sheet -> explicit h94 ViT-H encoder -> SDXL IP-Adapter Plus',
        'continuity_manifest':MANIFEST_PATH,
        'reference_files':[path for _, path, _ in REFERENCE_FILES],
        'master_reference_staged_as':str(master_path),
        'image_encoder_hidden_size':hidden_size,
        'ip_adapter_scale':0.90,
        'gpu':torch.cuda.get_device_name(0),'shots':[]
    }

    for index, shot in enumerate(SHOTS):
        name = f"earth-needs-help-e001-s{shot['id']}.png"
        try:
            prompt = CANONICAL_LOCK + shot['prompt']
            image = pipe(
                prompt=prompt,
                negative_prompt=NEGATIVE,
                ip_adapter_image=master_ref,
                guidance_scale=6.0,
                num_inference_steps=32,
                generator=torch.Generator(device='cuda').manual_seed(9300 + index),
                width=768,
                height=432,
            ).images[0]
            image.save(WORK / name)
            result['shots'].append({'id':shot['id'],'success':True,'file':name,'reference_loaded':'five validated canon crops via explicit ViT-H'})
            print(f"SHOT {shot['id']} COMPLETE -> {name}", flush=True)
        except Exception as exc:
            result['shots'].append({'id':shot['id'],'success':False,'error':f'{type(exc).__name__}: {exc}'[:3000]})
            print(f"SHOT {shot['id']} FAILED -> {type(exc).__name__}: {exc}", flush=True)
            structural = (
                'mat1 and mat2 shapes cannot be multiplied',
                "tuple' object has no attribute 'shape'",
                'CUDA out of memory',
            )
            if any(marker in str(exc) for marker in structural):
                write_report(result)
                return 3
        write_report(result)

    result['elapsed_seconds'] = round(time.time() - started, 2)
    result['success'] = len(result['shots']) == len(SHOTS) and all(s.get('success') for s in result['shots'])
    write_report(result)
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
