#!/usr/bin/env python3
"""Generate Earth Needs Help Episode 001 production stills with hard continuity.

Fail-closed rules:
- recurring characters are never generated from prose alone;
- every shot loads the locked visual references extracted from the user-approved
  MAIN CHARACTERS - CONSISTENCY REFERENCE sheet;
- generated stills are not canon and must pass the separate continuity QA gate
  before motion generation can start.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

WORK = Path('/kaggle/working')
RAW_BASE = 'https://raw.githubusercontent.com/simplebusiness26/Animation-Factory/main/'
MANIFEST_PATH = 'shows/earth-needs-help/continuity-manifest.json'

CANONICAL_LOCK = (
    'The attached reference sheet is the absolute character source of truth. '
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
    {'id':'002','characters':['captain-pip','bloop','zig','momo'],'prompt':'Inside the established colourful alien spaceship bridge. Earth fills the large front window. Captain Pip points dramatically toward Earth. Bloop leans excitedly toward the glass. Zig checks an inventor gadget. Momo gives Earth a gentle friendly wave. Preserve the established spaceship visual language.'},
    {'id':'003','characters':['captain-pip','bloop','zig','momo'],'prompt':'Sunny colourful neighbourhood park on Earth. The crews small rounded rescue spaceship has made a funny harmless landing through a soft hedge and stopped crooked in a flowerbed. Leaves float in the air and Bloop peeks from the hatch. No injuries or damage; playful physical comedy.'},
    {'id':'004','characters':['captain-pip','bloop','zig','momo','human-child'],'prompt':'Sunny park beside the landed alien spaceship. The recurring Earth child faces the four alien rescuers for the first time. Captain Pip takes a determined step forward, Bloop peeks curiously, Zig holds a small scanner, and Momo stands calmly behind them. The child is surprised, curious and unafraid.'},
    {'id':'005','characters':['captain-pip','bloop','zig','momo','human-child'],'prompt':'A colourful childs kite is harmlessly stuck high in a leafy park tree. Captain Pip, Bloop, Zig and Momo stare upward as if witnessing a planetary catastrophe while the child gives a small confused shrug because it is only a kite. Sunny safe park.'},
    {'id':'006a','characters':['captain-pip','bloop','zig','momo','human-child'],'prompt':'At the base of the kite tree, Zig proudly kneels beside a compact colourful alien rescue gadget with several folded mechanical arms. Zig looks extremely confident. Captain Pip watches seriously, Bloop leans in excitedly, the child watches cautiously, and Momo remains calm.'},
    {'id':'006b','characters':['captain-pip','bloop','zig','momo','human-child'],'prompt':'Same park tree and rescue gadget, now spinning too enthusiastically in a harmless circle with mechanical arms pointing the wrong ways and colourful leaves blowing everywhere. Bloop chases it, Zig looks shocked, Captain Pip gives urgent instructions, the child is amused, and Momo remains calm.'},
    {'id':'007','characters':['captain-pip','bloop','zig','momo','human-child'],'prompt':'Quiet comedic beat beneath the tree after gadget chaos. Momo stands nearest the branch and simply uses a gentle long reach or simple tool to take the kite free. The child smiles. Captain Pip, Bloop and Zig are frozen in stunned silence in the background. Warm wholesome composition.'},
    {'id':'008','characters':['captain-pip','bloop','zig','momo','human-child'],'prompt':'Sunny park celebration. The child happily holds the rescued kite while the four aliens celebrate as if they saved an entire planet. Captain Pip strikes a tiny heroic pose, Bloop jumps with joy, Zig proudly poses as the inventor, and Momo claps gently. Bright uplifting wide composition.'},
    {'id':'009','characters':['captain-pip','bloop','zig','momo','human-child'],'prompt':'Comedy setup in the park after the celebration. Bloop holds a small colourful alien snack while a cheeky ordinary grey pigeon steals it. Bloop freezes in disbelief. Captain Pip, Zig and Momo turn toward the pigeon. The child stands nearby holding the kite. Clear readable visual gag, no aggressive chase.'}
]


def install() -> None:
    subprocess.run([
        sys.executable, '-m', 'pip', 'install', '-q', '-U',
        'diffusers', 'transformers', 'accelerate', 'safetensors', 'Pillow<12'
    ], check=True)


def fetch_raw(repo_path: str) -> bytes:
    with urllib.request.urlopen(RAW_BASE + repo_path, timeout=90) as response:
        return response.read()


def fetch_asset(repo_path: str) -> bytes:
    data = fetch_raw(repo_path)
    if repo_path.endswith('.b64'):
        return base64.b64decode(data.decode('utf-8').strip())
    return data


def load_manifest() -> dict:
    return json.loads(fetch_raw(MANIFEST_PATH).decode('utf-8'))


def preflight(manifest: dict) -> tuple[Path, dict[str, str]]:
    pack = manifest.get('reference_pack') or {}
    policy = manifest.get('canon_policy') or {}
    if pack.get('status') != 'locked' or manifest.get('status') != 'locked':
        raise RuntimeError('CONTINUITY_BLOCK: canonical character reference pack is not locked')
    if not bool(policy.get('load_references_for_every_shot')):
        raise RuntimeError('CONTINUITY_BLOCK: per-shot reference loading is disabled')
    if bool(policy.get('text_only_recurring_character_generation_allowed')):
        raise RuntimeError('CONTINUITY_BLOCK: text-only recurring character generation must remain disabled')
    if bool(policy.get('silent_character_redesign_allowed')):
        raise RuntimeError('CONTINUITY_BLOCK: silent character redesign must remain disabled')

    directory = str(pack.get('directory') or '').strip('/')
    required = [str(name) for name in (pack.get('required_files') or [])]
    if not directory or not required:
        raise RuntimeError('CONTINUITY_BLOCK: reference pack manifest is incomplete')

    local_dir = WORK / 'canonical-character-refs'
    local_dir.mkdir(parents=True, exist_ok=True)
    refs: dict[str, str] = {}
    for filename in required:
        data = fetch_asset(f'{directory}/{filename}')
        char_id = filename.split('.', 1)[0]
        target = local_dir / f'{char_id}.jpg'
        target.write_bytes(data)
        refs[char_id] = str(target)
    return local_dir, refs


def build_reference_sheet(refs: dict[str, str], visible: list[str]):
    from PIL import Image, ImageOps

    selected = []
    for char_id in visible:
        path = refs.get(char_id)
        if not path:
            raise RuntimeError(f'CONTINUITY_BLOCK: missing locked reference for {char_id}')
        with Image.open(path) as im:
            selected.append(im.convert('RGB').copy())

    cell = (256, 256)
    cols = 3
    rows = (len(selected) + cols - 1) // cols
    sheet = Image.new('RGB', (cell[0] * cols, cell[1] * rows), (238, 240, 244))
    for i, image in enumerate(selected):
        fitted = ImageOps.contain(image, (232, 232), method=Image.Resampling.LANCZOS)
        x = (i % cols) * cell[0] + (cell[0] - fitted.width) // 2
        y = (i // cols) * cell[1] + (cell[1] - fitted.height) // 2
        sheet.paste(fitted, (x, y))
    return sheet


def write_blocked_report(error: Exception) -> None:
    report = {
        'show': 'Earth Needs Help',
        'episode': '001',
        'success': False,
        'status': 'blocked_continuity',
        'error': f'{type(error).__name__}: {error}',
        'generated_shots': []
    }
    (WORK / 'earth-needs-help-e001-stills-manifest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


def main() -> int:
    started = time.time()
    try:
        manifest = load_manifest()
        _, refs = preflight(manifest)
    except Exception as exc:
        write_blocked_report(exc)
        return 2

    install()

    import torch
    from diffusers import AutoPipelineForText2Image

    pipe = AutoPipelineForText2Image.from_pretrained(
        'stabilityai/stable-diffusion-xl-base-1.0',
        torch_dtype=torch.float16,
        variant='fp16',
        use_safetensors=True,
    )
    pipe.load_ip_adapter(
        'h94/IP-Adapter',
        subfolder='sdxl_models',
        weight_name='ip-adapter-plus_sdxl_vit-h.safetensors',
    )
    pipe.set_ip_adapter_scale(0.95)
    pipe.enable_model_cpu_offload()
    pipe.enable_attention_slicing()
    if hasattr(pipe, 'enable_vae_tiling'):
        pipe.enable_vae_tiling()

    result = {
        'show': 'Earth Needs Help',
        'episode': '001',
        'success': False,
        'reference_mode': 'locked user-approved individual visual refs -> IP-Adapter Plus on every shot',
        'continuity_manifest': MANIFEST_PATH,
        'ip_adapter_scale': 0.95,
        'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        'shots': [],
    }
    manifest_path = WORK / 'earth-needs-help-e001-stills-manifest.json'

    for index, shot in enumerate(SHOTS):
        output_name = f"earth-needs-help-e001-s{shot['id']}.png"
        try:
            sheet = build_reference_sheet(refs, shot['characters'])
            prompt = CANONICAL_LOCK + ' Compose a NEW production scene using those exact recurring designs. ' + shot['prompt'] + ' Single clean production frame only. No text.'
            image = pipe(
                prompt=prompt,
                negative_prompt=NEGATIVE,
                ip_adapter_image=sheet,
                guidance_scale=6.5,
                num_inference_steps=34,
                generator=torch.Generator(device='cpu').manual_seed(9200 + index),
                width=768,
                height=432,
            ).images[0]
            image.save(WORK / output_name)
            result['shots'].append({
                'id': shot['id'],
                'success': True,
                'file': output_name,
                'references_loaded': shot['characters']
            })
            print(f"SHOT {shot['id']} COMPLETE -> {output_name}", flush=True)
        except Exception as exc:
            result['shots'].append({'id': shot['id'], 'success': False, 'error': f'{type(exc).__name__}: {exc}'[:3000]})
            print(f"SHOT {shot['id']} FAILED -> {type(exc).__name__}: {exc}", flush=True)
        manifest_path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')

    result['elapsed_seconds'] = round(time.time() - started, 2)
    result['success'] = len(result['shots']) == len(SHOTS) and all(s.get('success') for s in result['shots'])
    manifest_path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
