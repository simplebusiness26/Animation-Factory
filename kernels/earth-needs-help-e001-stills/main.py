#!/usr/bin/env python3
"""Generate Earth Needs Help Episode 001 stills from the locked master consistency reference.

The prior retry path decoded the small per-character crops into files that Pillow could
not identify on Kaggle. This runner uses the original locked master consistency sheet
(`character-lock.b64`) as the visual IP-Adapter reference for every shot, while still
checking the continuity manifest and preserving the fail-closed continuity gate.
All retries that reference canonical-character-refs/*.jpg are stale and must not be reused.
"""
from __future__ import annotations

import base64
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
MASTER_LOCK_PATH = 'kernels/earth-needs-help-e001-stills/character-lock.b64'

CANONICAL_LOCK = (
    'The attached MAIN CHARACTERS consistency reference is the absolute visual source of truth. '
    'Reproduce the SAME recurring character designs; do not reinterpret, remix or redesign them. '
    'Captain Pip is the GREEN rounded alien captain with large expressive eyes, white captain hat and dark captain uniform exactly as shown. '
    'Bloop is the BLUE round alien with antennae and huge expressive eyes exactly as shown. '
    'Zig is the PURPLE tall slim alien inventor exactly as shown. '
    'Momo is the PINK small calm alien with the large ear/head-side silhouette exactly as shown. '
    'When the Earth child is visible, use the exact brown-haired child in the blue hoodie shown in the reference. '
    'Never swap colours, faces, silhouettes, clothing, accessories, roles, or relative scale. '
    'Identity is locked; only pose, expression, action, camera and location may change. '
    'Polished bright friendly 3D childrens comedy animation, rounded forms, warm cinematic lighting, 16:9 landscape. '
)

NEGATIVE = (
    'text, captions, labels, logo, watermark, infographic, storyboard, UI, poster, '
    'new character design, replacement character, identity drift, colour swap, role swap, wrong species, wrong face, wrong silhouette, '
    'coral-red Captain Pip, red Captain Pip, lime-green Zig, green Zig, lavender Momo, purple Momo, turquoise Bloop, '
    'changed costume, missing captain hat, missing captain uniform, duplicate character, extra limbs, missing limbs, deformed face, '
    'scary, horror, violence, photorealistic human skin, dark grim lighting, background melting, blurry, low quality'
)

SHOTS = [
    {'id':'002','prompt':'Inside the established colourful alien spaceship bridge. Earth fills the large front window. Captain Pip points dramatically toward Earth. Bloop leans excitedly toward the glass. Zig checks an inventor gadget. Momo gives Earth a gentle friendly wave.'},
    {'id':'003','prompt':'Sunny colourful neighbourhood park on Earth. The crews small rounded rescue spaceship has made a funny harmless landing through a soft hedge and stopped crooked in a flowerbed. Leaves float in the air and Bloop peeks from the hatch. No injuries or damage; playful physical comedy.'},
    {'id':'004','prompt':'Sunny park beside the landed alien spaceship. The recurring Earth child faces the four alien rescuers for the first time. Captain Pip steps forward, Bloop peeks curiously, Zig holds a small scanner, and Momo stands calmly behind them. The child is surprised, curious and unafraid.'},
    {'id':'005','prompt':'A colourful childs kite is harmlessly stuck high in a leafy park tree. Captain Pip, Bloop, Zig and Momo stare upward as if witnessing a planetary catastrophe while the child gives a small confused shrug because it is only a kite.'},
    {'id':'006a','prompt':'At the base of the kite tree, Zig proudly kneels beside a compact colourful alien rescue gadget with several folded mechanical arms. Zig looks extremely confident. Captain Pip watches seriously, Bloop leans in excitedly, the child watches cautiously, and Momo remains calm.'},
    {'id':'006b','prompt':'Same park tree and rescue gadget, now spinning too enthusiastically in a harmless circle with mechanical arms pointing the wrong ways and colourful leaves blowing everywhere. Bloop chases it, Zig looks shocked, Captain Pip gives urgent instructions, the child is amused, and Momo remains calm.'},
    {'id':'007','prompt':'Quiet comedic beat beneath the tree after gadget chaos. Momo stands nearest the branch and simply uses a gentle long reach or simple tool to take the kite free. The child smiles. Captain Pip, Bloop and Zig are frozen in stunned silence in the background.'},
    {'id':'008','prompt':'Sunny park celebration. The child happily holds the rescued kite while the four aliens celebrate as if they saved an entire planet. Captain Pip strikes a tiny heroic pose, Bloop jumps with joy, Zig proudly poses as the inventor, and Momo claps gently.'},
    {'id':'009','prompt':'Comedy setup in the park after the celebration. Bloop holds a small colourful alien snack while a cheeky ordinary grey pigeon steals it. Bloop freezes in disbelief. Captain Pip, Zig and Momo turn toward the pigeon. The child stands nearby holding the kite.'},
]


def fetch_raw(path: str) -> bytes:
    with urllib.request.urlopen(RAW_BASE + path, timeout=90) as response:
        return response.read()


def load_manifest() -> dict:
    return json.loads(fetch_raw(MANIFEST_PATH).decode('utf-8'))


def preflight_master_reference():
    from PIL import Image
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

    encoded = fetch_raw(MASTER_LOCK_PATH).decode('utf-8').strip()
    data = base64.b64decode(encoded)
    try:
        image = Image.open(io.BytesIO(data)).convert('RGB')
        image.load()
    except Exception as exc:
        raise RuntimeError(f'CONTINUITY_BLOCK: locked master reference is unreadable: {type(exc).__name__}: {exc}') from exc
    target = WORK / 'canonical-master-reference.jpg'
    image.save(target, 'JPEG', quality=96)
    return image, target


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
        master_ref, master_path = preflight_master_reference()
    except Exception as exc:
        write_report({'show':'Earth Needs Help','episode':'001','success':False,'status':'blocked_continuity','error':f'{type(exc).__name__}: {exc}','generated_shots':[]})
        return 2

    install()
    import torch
    from diffusers import AutoPipelineForText2Image

    pipe = AutoPipelineForText2Image.from_pretrained(
        'stabilityai/stable-diffusion-xl-base-1.0', torch_dtype=torch.float16,
        variant='fp16', use_safetensors=True,
    )
    pipe.load_ip_adapter('h94/IP-Adapter', subfolder='sdxl_models', weight_name='ip-adapter-plus_sdxl_vit-h.safetensors')
    pipe.set_ip_adapter_scale(0.95)
    pipe.enable_model_cpu_offload()
    pipe.enable_attention_slicing()
    if hasattr(pipe, 'enable_vae_tiling'):
        pipe.enable_vae_tiling()

    result = {
        'show':'Earth Needs Help','episode':'001','success':False,
        'reference_mode':'locked user-approved MAIN CHARACTERS master consistency sheet -> IP-Adapter Plus on every shot',
        'continuity_manifest':MANIFEST_PATH,'master_reference':MASTER_LOCK_PATH,
        'master_reference_staged_as':str(master_path),'ip_adapter_scale':0.95,
        'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,'shots':[]
    }

    for index, shot in enumerate(SHOTS):
        name = f"earth-needs-help-e001-s{shot['id']}.png"
        try:
            prompt = CANONICAL_LOCK + ' Compose a NEW production scene using those exact recurring designs. ' + shot['prompt'] + ' Single clean production frame only. No text.'
            image = pipe(
                prompt=prompt, negative_prompt=NEGATIVE, ip_adapter_image=master_ref,
                guidance_scale=6.5, num_inference_steps=34,
                generator=torch.Generator(device='cpu').manual_seed(9300 + index),
                width=768, height=432,
            ).images[0]
            image.save(WORK / name)
            result['shots'].append({'id':shot['id'],'success':True,'file':name,'reference_loaded':'locked master consistency sheet'})
            print(f"SHOT {shot['id']} COMPLETE -> {name}", flush=True)
        except Exception as exc:
            result['shots'].append({'id':shot['id'],'success':False,'error':f'{type(exc).__name__}: {exc}'[:3000]})
            print(f"SHOT {shot['id']} FAILED -> {type(exc).__name__}: {exc}", flush=True)
        write_report(result)

    result['elapsed_seconds'] = round(time.time() - started, 2)
    result['success'] = len(result['shots']) == len(SHOTS) and all(s.get('success') for s in result['shots'])
    write_report(result)
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
