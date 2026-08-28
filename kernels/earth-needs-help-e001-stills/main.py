#!/usr/bin/env python3
"""Generate Earth Needs Help Episode 001 production stills 002-009 on Kaggle.

This recovery runner intentionally avoids the currently incompatible SDXL
IP-Adapter integration that caused retries 1-3 to produce only debug assets.
It uses the approved bridge frame as the visual anchor plus a strict canonical
character lock in every prompt. The known three-byte JPEG DQT export defect is
repaired before Pillow loads the approved bridge frame.
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

CHARACTER_LOCK = (
    'Use ONLY the canonical Earth Needs Help cast. '
    'Bloop is a small round turquoise-blue alien with two ball antennae, huge oval eyes and tiny limbs. '
    'Zig is a slim lime-green inventor with three green head tufts, oversized brown utility goggles and a brown gadget belt. '
    'Momo is a huge fluffy lavender alien with enormous arms, tiny friendly eyes and a warm smile. '
    'Captain Pip is the smallest coral-red alien with two short antennae, a dark navy rescue-captain jacket with gold trim and epaulettes, and a serious face. '
    'The Earth child has brown tousled hair, an orange hoodie over a blue shirt, shorts, colourful trainers and a small blue backpack. '
    'Preserve these exact colours, silhouettes, clothing, accessories and relative body proportions. '
    'Original polished 3D children\'s comedy animation, tactile rounded materials, bright warm cinematic lighting, 16:9 landscape. '
)

NEGATIVE = (
    'text, captions, labels, logo, watermark, infographic, storyboard, reference sheet, turnaround sheet, UI, poster, '
    'replacement character, wrong species, wrong colours, changed costume, duplicate character, extra limbs, missing limbs, deformed face, '
    'scary, horror, violence, photorealistic human skin, dark grim lighting, background melting, blurry, low quality'
)

SHOTS = [
    {'id':'002','strength':0.48,'prompt':'Inside the exact same tiny colourful alien spaceship bridge. Beautiful blue-and-green Earth fills the large front window. Captain Pip points dramatically toward Earth. Bloop leans excitedly toward the glass. Zig checks tools on his brown gadget belt. Momo gives Earth a gentle friendly wave. Same spaceship architecture as the approved red-alert frame.'},
    {'id':'003','strength':0.88,'prompt':'Sunny colourful neighbourhood park on Earth. The crew\'s same small rounded alien rescue spaceship has made a funny harmless landing, gently bounced through a soft hedge and stopped crooked in a flowerbed. Leaves float in the air, hatch opening, Bloop peeks out upside down. No injuries or damage, playful physical comedy, blue sky, green trees.'},
    {'id':'004','strength':0.86,'prompt':'Sunny park beside the landed alien spaceship. The canonical human child faces the four canonical alien rescuers for the first time. Captain Pip takes two tiny determined steps forward. Bloop peeks curiously beside Momo. Zig holds a small scanner. Momo stands warmly behind them. Child is surprised, curious and unafraid. Clean medium-wide group composition.'},
    {'id':'005','strength':0.88,'prompt':'A colourful red yellow and blue child\'s kite is harmlessly stuck high in a leafy park tree. In the foreground Captain Pip, Bloop, Zig and Momo stare upward in exaggerated horror as if witnessing a planetary catastrophe. The canonical child stands beside them giving a small confused shrug because it is only a kite. Sunny safe park.'},
    {'id':'006a','strength':0.88,'prompt':'At the base of the kite tree, canonical Zig proudly kneels beside a compact colourful alien rescue gadget with several folded mechanical arms. Zig looks extremely confident. Captain Pip watches with grave seriousness, Bloop leans in excitedly, the child watches cautiously, and Momo calmly stands behind them. Clean readable setup for a ridiculous invention.'},
    {'id':'006b','strength':0.90,'prompt':'Same park tree and same rescue gadget, now spinning too enthusiastically in a small harmless circle with mechanical arms pointing the wrong ways and colourful leaves blowing everywhere. Canonical Bloop chases it, Zig looks shocked his invention went off-plan, Captain Pip points and gives urgent instructions, the child watches amused and confused, Momo remains completely calm. Energetic but safe comedy.'},
    {'id':'007','strength':0.87,'prompt':'Quiet comedic beat beneath the tree after gadget chaos. Canonical huge fluffy lavender Momo stands closest to the branch and simply stretches one enormous gentle arm upward to take the colourful kite free. The child waits beside him smiling. Captain Pip, Bloop and Zig are frozen in stunned silence in the background. Warm wholesome composition.'},
    {'id':'008','strength':0.87,'prompt':'Sunny park celebration. The canonical child happily holds the rescued kite while the four canonical aliens celebrate as if they saved an entire planet. Captain Pip strikes a tiny heroic pose, Bloop jumps with joy, Zig proudly adjusts his brown goggles, Momo claps his huge fluffy hands gently. Bright uplifting wide composition.'},
    {'id':'009','strength':0.89,'prompt':'Comedy setup in the park after the celebration. Canonical Bloop holds a small colourful alien snack while one cheeky ordinary grey pigeon steals it. Bloop freezes in disbelief. Captain Pip, Zig and Momo turn toward the pigeon. The canonical child is nearby holding the kite. Clear readable visual gag, no aggressive chase.'}
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


def repair_known_jpeg_dqt(path: Path) -> bool:
    data = path.read_bytes()
    first_dqt = data.find(b'\xff\xdb')
    second_dqt = data.find(b'\xff\xdb', first_dqt + 2) if first_dqt >= 0 else -1
    if second_dqt < 0 or second_dqt + 4 > len(data):
        return False
    declared_length = int.from_bytes(data[second_dqt + 2:second_dqt + 4], 'big')
    declared_end = second_dqt + 2 + declared_length
    sof_positions = [p for p in (data.find(b'\xff\xc0', second_dqt), data.find(b'\xff\xc2', second_dqt)) if p >= 0]
    if not sof_positions:
        return False
    sof = min(sof_positions)
    missing = declared_end - sof
    if not 1 <= missing <= 8 or sof == 0:
        return False
    path.write_bytes(data[:sof] + bytes([data[sof - 1]]) * missing + data[sof:])
    return True


def load_reference(path: Path):
    from PIL import Image
    try:
        image = Image.open(path).convert('RGB')
        image.load()
        return image, False
    except Exception as first_error:
        if not repair_known_jpeg_dqt(path):
            raise first_error
        image = Image.open(path).convert('RGB')
        image.load()
        return image, True


def main() -> int:
    started = time.time()
    install()

    import torch
    from PIL import Image, ImageOps
    from diffusers import StableDiffusionXLImg2ImgPipeline

    reference_path = fetch_b64(BRIDGE_STILL_URL, 'reference.jpg')
    ref, repaired = load_reference(reference_path)
    size = (768, 432)
    ref = ImageOps.fit(ref, size, method=Image.Resampling.LANCZOS)

    pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
        'stabilityai/stable-diffusion-xl-base-1.0',
        torch_dtype=torch.float16,
        variant='fp16',
        use_safetensors=True,
    )
    pipe.enable_model_cpu_offload()
    pipe.enable_attention_slicing()
    if hasattr(pipe, 'enable_vae_tiling'):
        pipe.enable_vae_tiling()
    elif hasattr(pipe, 'vae') and hasattr(pipe.vae, 'enable_tiling'):
        pipe.vae.enable_tiling()

    manifest = {
        'show': 'Earth Needs Help',
        'episode': '001',
        'reference_mode': 'approved canonical bridge + strict text continuity lock; adapter-free recovery path',
        'reference_repaired': repaired,
        'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        'shots': [],
    }
    manifest_path = WORK / 'earth-needs-help-e001-stills-manifest.json'

    for index, shot in enumerate(SHOTS):
        output_name = f"earth-needs-help-e001-s{shot['id']}.png"
        try:
            image = pipe(
                prompt=CHARACTER_LOCK + shot['prompt'] + ' Single production frame only. No text.',
                negative_prompt=NEGATIVE,
                image=ref,
                strength=float(shot['strength']),
                guidance_scale=7.5,
                num_inference_steps=28,
                generator=torch.Generator(device='cpu').manual_seed(7200 + index),
                width=size[0],
                height=size[1],
            ).images[0]
            image.save(WORK / output_name)
            manifest['shots'].append({'id': shot['id'], 'success': True, 'file': output_name})
            print(f"SHOT {shot['id']} COMPLETE -> {output_name}", flush=True)
        except Exception as exc:
            manifest['shots'].append({'id': shot['id'], 'success': False, 'error': f'{type(exc).__name__}: {exc}'[:2000]})
            print(f"SHOT {shot['id']} FAILED -> {type(exc).__name__}: {exc}", flush=True)
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

    manifest['elapsed_seconds'] = round(time.time() - started, 2)
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2), flush=True)
    return 0 if len(manifest['shots']) == len(SHOTS) and all(s.get('success') for s in manifest['shots']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
