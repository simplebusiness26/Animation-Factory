#!/usr/bin/env python3
"""Generate Earth Needs Help Episode 001 still frames 002-009 on a Kaggle T4."""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

WORK = Path("/kaggle/working")
BRIDGE_STILL_URL = "https://raw.githubusercontent.com/simplebusiness26/Animation-Factory/main/kernels/earth-needs-help-e001-s001/input-still.b64"

CHARACTER_LOCK = (
    "Use the same original Earth Needs Help cast in every frame: "
    "Bloop is a small round turquoise-blue alien with two antennae, huge oval eyes and tiny limbs; "
    "Zig is a slim lime-green alien inventor with three green head tufts, oversized brown utility goggles and a brown gadget belt; "
    "Momo is a huge fluffy lavender alien with enormous arms, tiny friendly eyes and a warm gentle smile; "
    "Captain Pip is the smallest alien, coral-red, wearing an oversized dark navy rescue-captain jacket with gold trim and epaulettes, serious expressive face and an original space-rescue badge; "
    "the Earth child has brown tousled hair, an orange hoodie over a blue shirt, shorts, colourful trainers and a small blue backpack. "
    "Original polished 3D children's comedy animation, tactile rounded forms, bright warm cinematic lighting, expressive readable faces, family-friendly, 16:9 landscape. "
)

NEGATIVE = (
    "text, captions, labels, logo, watermark, infographic, storyboard grid, UI, poster, duplicate character, extra limbs, "
    "missing limbs, deformed face, wrong character colours, changed costume, scary, horror, violence, photorealistic human skin, "
    "dark grim lighting, background melting, blurry, low quality"
)

SHOTS = [
    {
        "id": "002",
        "strength": 0.48,
        "prompt": "Inside the exact same tiny colourful alien spaceship bridge, beautiful blue Earth fills the large front window. Captain Pip stands at the controls pointing dramatically toward Earth. Bloop leans excitedly toward the glass. Zig checks tools on his gadget belt. Momo gives Earth a gentle friendly wave. Heroic but funny composition, same spaceship architecture as the reference frame."
    },
    {
        "id": "003",
        "strength": 0.88,
        "prompt": "Sunny colourful neighbourhood park on Earth. The crew's small rounded alien rescue spaceship has just made a funny harmless landing, gently bounced through a soft hedge and stopped crooked in a flowerbed. Leaves float in the air, hatch opening, Bloop peeks out upside down. No injuries or damage, playful physical comedy, blue sky, green trees."
    },
    {
        "id": "004",
        "strength": 0.84,
        "prompt": "Sunny park beside the landed alien spaceship. The human child faces the four alien rescuers for the first time. Captain Pip takes two tiny determined steps forward with total seriousness. Bloop peeks curiously beside Momo. Zig holds a small scanner. Momo stands warmly behind them. The child looks surprised, curious and completely unafraid. Clean medium-wide group composition."
    },
    {
        "id": "005",
        "strength": 0.86,
        "prompt": "A colourful red yellow and blue child's kite is harmlessly stuck high in a leafy park tree. In the foreground Captain Pip, Bloop, Zig and Momo stare upward in exaggerated horror as if witnessing a planetary catastrophe. The child stands beside them giving a small confused shrug because it is only a kite. Clear comedic contrast, sunny safe park."
    },
    {
        "id": "006a",
        "strength": 0.90,
        "prompt": "At the base of the kite tree, Zig proudly kneels beside a compact colourful alien rescue gadget with several folded mechanical arms. Zig looks extremely confident. Captain Pip watches with grave seriousness, Bloop leans in excitedly, the child watches cautiously, and Momo calmly stands behind them. Clean readable setup for a ridiculous invention."
    },
    {
        "id": "006b",
        "strength": 0.91,
        "prompt": "Same park tree and same rescue gadget, now spinning too enthusiastically in a small harmless circle with mechanical arms pointing the wrong ways and colourful leaves blowing everywhere. Bloop chases it, Zig looks shocked his invention went off-plan, Captain Pip points and gives urgent instructions, the child watches amused and confused, Momo remains completely calm. Energetic but safe comedy."
    },
    {
        "id": "007",
        "strength": 0.86,
        "prompt": "Quiet comedic beat beneath the tree after the gadget chaos. Huge fluffy lavender Momo stands closest to the branch and simply stretches one enormous gentle arm upward to take the colourful kite free. The child waits beside him smiling. Captain Pip, Bloop and Zig are frozen in stunned silence in the background. Warm wholesome composition."
    },
    {
        "id": "008",
        "strength": 0.85,
        "prompt": "Sunny park celebration. The child happily holds the rescued kite while the four aliens celebrate as if they saved an entire planet. Captain Pip strikes a tiny heroic pose, Bloop jumps with joy, Zig proudly adjusts his brown goggles, and Momo claps his huge fluffy hands gently. Bright uplifting wide composition."
    },
    {
        "id": "009",
        "strength": 0.91,
        "prompt": "Comedy setup in the park after the celebration. Bloop holds a small colourful alien snack beside him while one cheeky ordinary grey pigeon reaches in and steals it. Bloop freezes in disbelief. Captain Pip, Zig and Momo turn toward the pigeon. The human child is nearby holding the kite. Clear readable visual gag, no aggressive chase."
    }
]


def install() -> None:
    subprocess.run([
        sys.executable, "-m", "pip", "install", "-q", "-U",
        "diffusers", "transformers", "accelerate", "safetensors", "Pillow<12"
    ], check=True)


def fetch_reference() -> Path:
    with urllib.request.urlopen(BRIDGE_STILL_URL, timeout=60) as response:
        encoded = response.read().decode("utf-8").strip()
    path = WORK / "reference.jpg"
    path.write_bytes(base64.b64decode(encoded))
    return path


def main() -> int:
    started = time.time()
    install()

    import torch
    from PIL import Image, ImageOps
    from diffusers import StableDiffusionXLImg2ImgPipeline

    reference_path = fetch_reference()
    ref = Image.open(reference_path).convert("RGB")
    size = (768, 432)
    ref = ImageOps.fit(ref, size, method=Image.Resampling.LANCZOS)

    pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16,
        variant="fp16",
        use_safetensors=True,
    )
    pipe.enable_model_cpu_offload()
    pipe.enable_attention_slicing()
    pipe.enable_vae_tiling()

    manifest = {
        "show": "Earth Needs Help",
        "episode": "001",
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "shots": [],
    }

    for index, shot in enumerate(SHOTS):
        prompt = CHARACTER_LOCK + shot["prompt"] + " Single production frame only. No text."
        output_name = f"earth-needs-help-e001-s{shot['id']}.png"
        output_path = WORK / output_name
        generator = torch.Generator(device="cpu").manual_seed(4200 + index)
        try:
            result = pipe(
                prompt=prompt,
                negative_prompt=NEGATIVE,
                image=ref,
                strength=float(shot["strength"]),
                guidance_scale=7.0,
                num_inference_steps=24,
                generator=generator,
                width=size[0],
                height=size[1],
            ).images[0]
            result.save(output_path)
            manifest["shots"].append({"id": shot["id"], "success": True, "file": output_name})
        except Exception as exc:
            manifest["shots"].append({"id": shot["id"], "success": False, "error": f"{type(exc).__name__}: {exc}"})

    manifest["elapsed_seconds"] = round(time.time() - started, 2)
    manifest_path = WORK / "earth-needs-help-e001-stills-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0 if any(s.get("success") for s in manifest["shots"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
