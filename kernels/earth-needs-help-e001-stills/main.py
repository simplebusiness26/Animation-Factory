#!/usr/bin/env python3
from __future__ import annotations

import base64, hashlib, io, json, math, subprocess, sys, time, traceback, urllib.request
from pathlib import Path

WORK = Path('/kaggle/working')
RAW_BASE = 'https://raw.githubusercontent.com/simplebusiness26/Animation-Factory/main/'
MANIFEST_PATH = 'shows/earth-needs-help/continuity-manifest.json'
REFERENCE_FILES = [
    ('captain-pip','shows/earth-needs-help/assets/characters/captain-pip.jpg.b64','fce0949798c906abe4282d3bfee778e98530d4750805ef704c6a26ab18bd09c6'),
    ('bloop','shows/earth-needs-help/assets/characters/bloop.jpg.b64','a324cd57f151b55e870453dbbf6a56f7bb529d938a5acc43d8b96bbb22b33e96'),
    ('zig','shows/earth-needs-help/assets/characters/zig.jpg.b64','d7b519f171e91f776f7e25d44b5a393fdb5b19bef63c885cc01c3c0ef2086c17'),
    ('momo','shows/earth-needs-help/assets/characters/momo.jpg.b64','126d3cbc5da02fae3b1c2b734f0fe54d1ae44dd16bf7d3c69b2ae95cf945e356'),
    ('human-child','shows/earth-needs-help/assets/characters/human-child.jpg.b64','7aa15b2a11ae15f095eaabca38252672e5828add647806971f0d438ef4417ddb'),
]
NEGATIVE = 'text, watermark, redesign, colour swap, wrong face, wrong costume, duplicate character, extra limbs, missing limbs, deformed face, horror, photorealistic skin, blurry, low quality, cropped body'
CHARACTER_LOCK = {
    'captain-pip': 'green Captain Pip, exact same rounded face and silhouette, white captain hat, dark navy captain uniform, friendly expressive eyes',
    'bloop': 'blue round Bloop, exact same round body, antennae and big expressive eyes, cheerful friendly face',
    'zig': 'tall slim purple Zig, exact same long silhouette, head features and inventor personality, holding a compact scanner when requested',
    'momo': 'small pink Momo, exact same compact silhouette, head features and calm kind face',
    'human-child': 'brown-haired child, exact same face and proportions, blue hoodie, dark trousers and trainers',
}

# The new pipeline deliberately separates scene generation from recurring-character generation.
# Each recurring character is rendered alone from its own locked reference, then composited by code.
SHOTS = [
 {'id':'001','bg':'Colourful friendly alien spaceship bridge during a gentle emergency alert, Earth visible through the front window, empty crew positions, premium child-friendly 3D animation, cinematic lighting, no characters',
  'chars':[('captain-pip','snaps upright at the controls, alert but friendly',(85,118,165)),('bloop','gasps beside the controls',(265,168,120)),('zig','reacts while checking a handheld gadget',(410,105,155)),('momo','stands calm and reassuring',(575,178,105))]},
 {'id':'002','bg':'Colourful alien spaceship bridge, Earth huge through front window, empty crew positions, premium child-friendly 3D animation, no characters',
  'chars':[('captain-pip','points toward Earth',(80,118,165)),('bloop','leans excitedly toward the window',(260,165,120)),('zig','checks a handheld gadget',(410,108,150)),('momo','waves gently toward Earth',(575,175,105))]},
 {'id':'003','bg':'Sunny neighbourhood park, small rounded rescue spaceship harmlessly landed through a hedge into flowers, hatch open, leaves floating, bright premium child-friendly 3D comedy, no characters',
  'chars':[('bloop','peeks excitedly out beside the spaceship hatch',(480,185,125))]},
 {'id':'004','bg':'Sunny neighbourhood park beside a small rounded landed rescue spaceship, clear meeting area in foreground, premium child-friendly 3D animation, no characters',
  'chars':[('captain-pip','steps forward and gestures kindly while speaking',(65,155,135)),('bloop','stands excitedly nearby',(210,205,105)),('human-child','looks surprised but unafraid, hands slightly open',(345,138,150)),('zig','holds a compact scanner and looks curious',(500,130,145)),('momo','smiles reassuringly with hands together',(655,205,92))]},
 {'id':'005','bg':'Sunny park with a colourful kite stuck high in a large leafy tree, clear ground beneath tree, premium child-friendly 3D comedy, no characters',
  'chars':[('captain-pip','stares dramatically up at the kite',(70,180,120)),('bloop','looks straight up in amazement',(205,220,95)),('human-child','gives a confused shrug while looking upward',(335,165,130)),('zig','stares up while holding scanner',(500,160,125)),('momo','looks calmly upward',(650,218,85))]},
 {'id':'006a','bg':'Base of a sunny park kite tree, open patch of grass with room for a small rescue gadget, premium child-friendly 3D animation, no characters',
  'chars':[('captain-pip','watches carefully',(70,185,120)),('bloop','leans in curiously',(205,225,92)),('human-child','looks cautious',(335,170,125)),('zig','kneels proudly beside an imaginary compact rescue gadget, inventor pose',(500,170,125)),('momo','stands calm',(650,220,85))]},
 {'id':'006b','bg':'Same sunny park kite tree, leaves flying around a compact colourful rescue gadget in the centre, playful harmless chaos, premium child-friendly 3D comedy, no characters',
  'chars':[('captain-pip','directs everyone with one arm extended',(70,182,120)),('bloop','runs after the spinning gadget, surprised',(205,220,95)),('human-child','looks amused',(335,168,125)),('zig','looks shocked at the gadget malfunction',(500,160,125)),('momo','remains calm while watching',(650,218,85))]},
 {'id':'007','bg':'Quiet warm beat beneath the sunny park kite tree, colourful kite just within reach, premium child-friendly 3D animation, no characters',
  'chars':[('momo','reaches upward with a simple gentle tool and frees the kite',(185,155,120)),('human-child','smiles warmly',(350,170,125)),('captain-pip','stands stunned in the background',(485,200,95)),('bloop','stands stunned beside Pip',(585,235,76)),('zig','stands stunned holding scanner',(660,190,90))]},
 {'id':'008','bg':'Sunny park celebration with open foreground, rescued colourful kite visible, premium cheerful child-friendly 3D animation, no characters',
  'chars':[('human-child','holds the rescued kite proudly and smiles',(55,155,135)),('captain-pip','strikes a playful heroic pose',(220,165,125)),('bloop','jumps happily',(365,215,95)),('zig','poses proudly with scanner',(500,160,125)),('momo','claps happily',(650,220,85))]},
 {'id':'009','bg':'Sunny neighbourhood park with path and flowers, ordinary grey pigeon near foreground, playful premium child-friendly 3D animation, no recurring characters',
  'chars':[('bloop','holds a small alien snack and freezes in surprise as a pigeon steals it',(105,205,105)),('captain-pip','turns toward Bloop in surprise',(275,180,115)),('zig','turns toward Bloop holding scanner',(420,165,120)),('momo','turns toward Bloop calmly',(555,220,85)),('human-child','stands nearby holding the kite and laughing gently',(650,170,118))]},
]

def fetch_raw(path: str) -> bytes:
    with urllib.request.urlopen(RAW_BASE + path, timeout=90) as r:
        return r.read()

def write_report(payload: dict) -> None:
    (WORK/'earth-needs-help-e001-stills-manifest.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(payload,indent=2),flush=True)

def preflight_references():
    from PIL import Image
    manifest=json.loads(fetch_raw(MANIFEST_PATH).decode())
    pack=manifest.get('reference_pack') or {}; policy=manifest.get('canon_policy') or {}
    if manifest.get('status')!='locked' or pack.get('status')!='locked':
        raise RuntimeError('CONTINUITY_BLOCK: canonical reference pack is not locked')
    if not policy.get('load_references_for_every_shot') or policy.get('text_only_recurring_character_generation_allowed') or policy.get('silent_character_redesign_allowed'):
        raise RuntimeError('CONTINUITY_BLOCK: canon policy invalid')
    required=set(pack.get('required_files') or []); refs={}
    for name,path,expected in REFERENCE_FILES:
        if Path(path).name not in required:
            raise RuntimeError(f'CONTINUITY_BLOCK: manifest missing {Path(path).name}')
        data=base64.b64decode(fetch_raw(path).decode().strip(),validate=True)
        if hashlib.sha256(data).hexdigest()!=expected:
            raise RuntimeError(f'CONTINUITY_BLOCK: {name} hash mismatch')
        im=Image.open(io.BytesIO(data)).convert('RGB'); im.load(); refs[name]=im
    return refs

def install():
    pkgs=['diffusers==0.31.0','transformers==4.46.3','accelerate==1.1.1','safetensors==0.4.5','huggingface-hub==0.26.2','tokenizers==0.20.3','Pillow<12']
    subprocess.run([sys.executable,'-m','pip','install','-q','--upgrade','--no-deps',*pkgs],check=True)

def remove_studio_background(image):
    from PIL import ImageFilter
    rgba=image.convert('RGBA')
    px=rgba.load(); w,h=rgba.size
    corners=[rgba.getpixel((2,2)),rgba.getpixel((w-3,2)),rgba.getpixel((2,h-3)),rgba.getpixel((w-3,h-3))]
    bg=tuple(sum(c[i] for c in corners)//len(corners) for i in range(3))
    for y in range(h):
        for x in range(w):
            r,g,b,a=px[x,y]
            d=math.sqrt((r-bg[0])**2+(g-bg[1])**2+(b-bg[2])**2)
            if d < 34:
                px[x,y]=(r,g,b,0)
            elif d < 70:
                px[x,y]=(r,g,b,int(255*(d-34)/36))
    alpha=rgba.getchannel('A').filter(ImageFilter.GaussianBlur(0.8))
    rgba.putalpha(alpha)
    bbox=rgba.getbbox()
    return rgba.crop(bbox) if bbox else rgba

def render_character(pipe, ref, name, action, seed):
    import torch
    pipe.set_ip_adapter_scale(0.95)
    prompt=(f"Single isolated full-body recurring TV character only: {CHARACTER_LOCK[name]}. "
            f"Action: {action}. Preserve exact identity, colours, outfit and silhouette from reference. "
            "Premium rounded 3D children's animation render. Centered full body, feet visible. Plain uniform pale grey studio background, no scenery, no props except explicitly requested, no text.")
    image=pipe(prompt=prompt,negative_prompt=NEGATIVE,ip_adapter_image=ref,guidance_scale=6.0,num_inference_steps=28,
               generator=torch.Generator(device='cuda').manual_seed(seed),width=512,height=512).images[0]
    return remove_studio_background(image)

def render_background(pipe, prompt, seed):
    import torch
    pipe.set_ip_adapter_scale(0.0)
    # A reference image is supplied only to satisfy older diffusers IP-Adapter call paths; scale 0 disables its influence.
    blank=pipe._canon_blank
    return pipe(prompt=prompt+', wide 16:9 composition, clean readable staging, no people, no aliens, no text',negative_prompt=NEGATIVE,
                ip_adapter_image=blank,guidance_scale=6.0,num_inference_steps=28,
                generator=torch.Generator(device='cuda').manual_seed(seed),width=768,height=432).images[0]

def composite_shot(background, layers):
    from PIL import Image, ImageDraw, ImageFilter
    canvas=background.convert('RGBA')
    for layer,(x,y,target_h) in layers:
        if layer.height <= 0: continue
        target_w=max(1,round(layer.width*target_h/layer.height))
        sprite=layer.resize((target_w,target_h),Image.Resampling.LANCZOS)
        shadow=Image.new('RGBA',canvas.size,(0,0,0,0)); draw=ImageDraw.Draw(shadow)
        foot_y=min(canvas.height-6,y+target_h-4)
        draw.ellipse((x+target_w*.18,foot_y-6,x+target_w*.82,foot_y+5),fill=(0,0,0,65))
        shadow=shadow.filter(ImageFilter.GaussianBlur(5)); canvas.alpha_composite(shadow)
        canvas.alpha_composite(sprite,(int(x),int(y)))
    return canvas.convert('RGB')

def main()->int:
    started=time.time()
    try:
        refs=preflight_references()
    except Exception as exc:
        write_report({'show':'Earth Needs Help','episode':'001','success':False,'status':'blocked_continuity','error':f'{type(exc).__name__}: {exc}','shots':[]})
        return 2
    install()
    import torch
    from PIL import Image
    from diffusers import StableDiffusionXLPipeline
    from transformers import CLIPVisionModelWithProjection
    image_encoder=CLIPVisionModelWithProjection.from_pretrained('h94/IP-Adapter',subfolder='models/image_encoder',torch_dtype=torch.float16)
    if int(getattr(image_encoder.config,'hidden_size',0))!=1280:
        raise RuntimeError('IP_ADAPTER_BLOCK: ViT-H hidden size mismatch')
    pipe=StableDiffusionXLPipeline.from_pretrained('stabilityai/stable-diffusion-xl-base-1.0',image_encoder=image_encoder,torch_dtype=torch.float16,variant='fp16',use_safetensors=True)
    pipe.load_ip_adapter('h94/IP-Adapter',subfolder='sdxl_models',weight_name='ip-adapter-plus_sdxl_vit-h.safetensors')
    if not torch.cuda.is_available(): raise RuntimeError('GPU_BLOCK: CUDA required')
    pipe.to('cuda'); pipe.enable_vae_tiling()
    pipe._canon_blank=Image.new('RGB',(256,256),(230,230,230))
    result={'show':'Earth Needs Help','episode':'001','success':False,'pipeline':'layered-2.5d-v1','continuity_manifest':MANIFEST_PATH,
            'character_method':'one locked reference -> one isolated character render -> deterministic code composite',
            'background_method':'separate text-only scene render with recurring characters forbidden','gpu':torch.cuda.get_device_name(0),'shots':[]}
    for index,shot in enumerate(SHOTS):
        try:
            bg=render_background(pipe,shot['bg'],12000+index)
            layers=[]; char_rows=[]
            for cidx,(name,action,placement) in enumerate(shot['chars']):
                sprite=render_character(pipe,refs[name],name,action,22000+index*10+cidx)
                layers.append((sprite,placement)); char_rows.append({'name':name,'placement':placement})
            image=composite_shot(bg,layers)
            out=WORK/f"earth-needs-help-e001-s{shot['id']}.png"; image.save(out)
            if shot['id']=='001': image.save(WORK/'reference.png')
            result['shots'].append({'id':shot['id'],'success':True,'file':out.name,'characters':char_rows})
            print(f"SHOT {shot['id']} COMPLETE -> {out.name}",flush=True)
        except Exception as exc:
            traceback.print_exc(); result['shots'].append({'id':shot['id'],'success':False,'error':f'{type(exc).__name__}: {exc}'[:3000]}); write_report(result); return 3
        write_report(result)
    result['elapsed_seconds']=round(time.time()-started,2); result['success']=len(result['shots'])==len(SHOTS) and all(x.get('success') for x in result['shots'])
    write_report(result); return 0 if result['success'] else 1

if __name__=='__main__':
    raise SystemExit(main())
