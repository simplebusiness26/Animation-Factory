#!/usr/bin/env python3
"""Generate Earth Needs Help Episode 001 still frames 002-009 on a Kaggle T4.

This version hard-anchors generation to BOTH canonical sources:
1) the approved red-alert spaceship frame, and
2) the approved five-character turnaround sheet.
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
BRIDGE_STILL_URL = 'https://raw.githubusercontent.com/simplebusiness26/Animation-Factory/main/kernels/earth-needs-help-e001-s001/input-still.b64'
CHARACTER_LOCK_URL = 'https://raw.githubusercontent.com/simplebusiness26/Animation-Factory/main/kernels/earth-needs-help-e001-stills/character-lock.b64'

CHARACTER_LOCK = (
    'Use ONLY the canonical Earth Needs Help cast shown in the supplied character reference. '
    'Bloop: small round turquoise-blue alien, two ball antennae, huge oval eyes, tiny limbs. '
    'Zig: slim lime-green inventor, three green head tufts, oversized brown utility goggles and brown gadget belt. '
    'Momo: huge fluffy lavender alien, enormous arms, tiny friendly eyes, warm smile. '
    'Captain Pip: smallest coral-red alien, two short antennae, oversized dark navy rescue-captain jacket with gold trim and epaulettes, serious face. '
    'Earth child: brown tousled hair, orange hoodie over blue shirt, shorts, colourful trainers, small blue backpack. '
    'Preserve their exact colours, silhouettes, accessories and relative body proportions. '
    'Original polished 3D children\'s comedy animation, tactile rounded materials, warm cinematic lighting, 16:9 landscape. '
)

NEGATIVE = (
    'text, captions, labels, logo, watermark, infographic, storyboard, reference sheet, turnaround sheet, multiple poses, UI, poster, '
    'replacement character, wrong species, wrong colours, changed costume, duplicate character, extra limbs, missing limbs, deformed face, '
    'scary, horror, violence, photorealistic human skin, dark grim lighting, background melting, blurry, low quality'
)

SHOTS = [
    {'id':'002','strength':0.42,'prompt':'Inside the exact same tiny colourful alien spaceship bridge. Beautiful blue-and-green Earth fills the large front window. Captain Pip points dramatically toward Earth. Bloop leans excitedly toward the glass. Zig checks tools on his brown gadget belt. Momo gives Earth a gentle friendly wave. Same spaceship architecture as the approved red-alert frame.'},
    {'id':'003','strength':0.78,'prompt':'Sunny colourful neighbourhood park on Earth. The crew\'s same small rounded alien rescue spaceship has made a funny harmless landing, gently bounced through a soft hedge and stopped crooked in a flowerbed. Leaves float in the air, hatch opening, Bloop peeks out upside down. No injuries or damage, playful physical comedy, blue sky, green trees.'},
    {'id':'004','strength':0.74,'prompt':'Sunny park beside the landed alien spaceship. The canonical human child faces the four canonical alien rescuers for the first time. Captain Pip takes two tiny determined steps forward. Bloop peeks curiously beside Momo. Zig holds a small scanner. Momo stands warmly behind them. Child is surprised, curious and unafraid. Clean medium-wide group composition.'},
    {'id':'005','strength':0.76,'prompt':'A colourful red yellow and blue child\'s kite is harmlessly stuck high in a leafy park tree. In the foreground Captain Pip, Bloop, Zig and Momo stare upward in exaggerated horror as if witnessing a planetary catastrophe. The canonical child stands beside them giving a small confused shrug because it is only a kite. Sunny safe park.'},
    {'id':'006a','strength':0.78,'prompt':'At the base of the kite tree, canonical Zig proudly kneels beside a compact colourful alien rescue gadget with several folded mechanical arms. Zig looks extremely confident. Captain Pip watches with grave seriousness, Bloop leans in excitedly, the child watches cautiously, and Momo calmly stands behind them. Clean readable setup for a ridiculous invention.'},
    {'id':'006b','strength':0.80,'prompt':'Same park tree and same rescue gadget, now spinning too enthusiastically in a small harmless circle with mechanical arms pointing the wrong ways and colourful leaves blowing everywhere. Canonical Bloop chases it, Zig looks shocked his invention went off-plan, Captain Pip points and gives urgent instructions, the child watches amused and confused, Momo remains completely calm. Energetic but safe comedy.'},
    {'id':'007','strength':0.76,'prompt':'Quiet comedic beat beneath the tree after gadget chaos. Canonical huge fluffy lavender Momo stands closest to the branch and simply stretches one enormous gentle arm upward to take the colourful kite free. The child waits beside him smiling. Captain Pip, Bloop and Zig are frozen in stunned silence in the background. Warm wholesome composition.'},
    {'id':'008','strength':0.75,'prompt':'Sunny park celebration. The canonical child happily holds the rescued kite while the four canonical aliens celebrate as if they saved an entire planet. Captain Pip strikes a tiny heroic pose, Bloop jumps with joy, Zig proudly adjusts his brown goggles, Momo claps his huge fluffy hands gently. Bright uplifting wide composition.'},
    {'id':'009','strength':0.80,'prompt':'Comedy setup in the park after the celebration. Canonical Bloop holds a small colourful alien snack while one cheeky ordinary grey pigeon steals it. Bloop freezes in disbelief. Captain Pip, Zig and Momo turn toward the pigeon. The canonical child is nearby holding the kite. Clear readable visual gag, no aggressive chase.'}
]


def install() -> None:
    subprocess.run([
        sys.executable, '-m', 'pip', 'install', '-q', '-U',
        'diffusers', 'transformers', 'accelerate', 'safetensors', 'Pillow<12'
    ], check=True)


def fetch_b64(url: str, filename: str) -> Path:
    with urllib.request.urlopen(url, timeout=60) as response:
        encoded = response.read().decode('utf-8').strip()
    path = WORK / filename
    path.write_bytes(base64.b64decode(encoded))
    return path


def character_strip(sheet, include_child: bool):
    """Crop the useful front/three-quarter part of each canonical row.

    The compact reference is 480x320 with five character rows. We avoid the
    expression-head side of the sheet so the adapter sees one identity per row.
    """
    from PIL import Image
    rows = 5 if include_child else 4
    row_h = sheet.height // 5
    crops = []
    for row in range(rows):
        y0 = row * row_h
        y1 = (row + 1) * row_h
        crops.append(sheet.crop((0, y0, int(sheet.width * 0.55), y1)))
    width = max(c.width for c in crops)
    out = Image.new('RGB', (width, row_h * rows), 'white')
    for idx, crop in enumerate(crops):
        out.paste(crop, (0, idx * row_h))
    return out


def main() -> int:
    started = time.time()
    install()

    import torch
    from PIL import Image, ImageOps
    from diffusers import StableDiffusionXLImg2ImgPipeline

    reference_path = fetch_b64(BRIDGE_STILL_URL, 'reference.jpg')
    character_path = fetch_b64(CHARACTER_LOCK_URL, 'character-lock.jpg')

    ref = Image.open(reference_path).convert('RGB')
    size = (768, 432)
    ref = ImageOps.fit(ref, size, method=Image.Resampling.LANCZOS)
    sheet = Image.open(character_path).convert('RGB')

    pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
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
    pipe.set_ip_adapter_scale(0.88)
    pipe.enable_model_cpu_offload()
    pipe.enable_attention_slicing()
    pipe.enable_vae_tiling()

    manifest = {
        'show':'Earth Needs Help',
        'episode':'001',
        'reference_mode':'scene1 + canonical character sheet + IP-Adapter',
        'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        'shots':[],
    }

    for index, shot in enumerate(SHOTS):
        prompt = CHARACTER_LOCK + shot['prompt'] + ' Single production frame only. No text.'
        output_name = f"earth-needs-help-e001-s{shot['id']}.png"
        output_path = WORK / output_name
        generator = torch.Generator(device='cpu').manual_seed(5200 + index)
        include_child = shot['id'] not in {'002','003'}
        adapter_ref = character_strip(sheet, include_child=include_child)
        try:
            result = pipe(
                prompt=prompt,
                negative_prompt=NEGATIVE,
                image=ref,
                ip_adapter_image=adapter_ref,
                strength=float(shot['strength']),
                guidance_scale=7.5,
                num_inference_steps=30,
                generator=generator,
                width=size[0],
                height=size[1],
            ).images[0]
            result.save(output_path)
            manifest['shots'].append({'id':shot['id'],'success':True,'file':output_name})
        except Exception as exc:
            manifest['shots'].append({'id':shot['id'],'success':False,'error':f'{type(exc).__name__}: {exc}'})

    manifest['elapsed_seconds'] = round(time.time() - started, 2)
    manifest_path = WORK / 'earth-needs-help-e001-stills-manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2))
    return 0 if any(s.get('success') for s in manifest['shots']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
