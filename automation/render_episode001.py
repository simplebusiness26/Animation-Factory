#!/usr/bin/env python3
from __future__ import annotations
import asyncio, json, subprocess, sys, tempfile, wave
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; DIST=ROOT/'dist'; FINAL=DIST/'earth-needs-help-e001-final.mp4'; RUNTIME=80.0
SHOTS=[('001',7.0),('002',7.0),('003',8.0),('004',9.0),('005',8.0),('006a',6.0),('006b',7.0),('007',10.0),('008',10.0),('009',8.0)]
LINES=[(0.25,'narrator','Far, far away, the bravest rescue crew in the galaxy received a terrible warning.'),(5.25,'pip','Emergency!'),(7.45,'pip','Earth needs us!'),(10.6,'bloop','Helloooo, Earth!'),(19.15,'bloop','Nailed it.'),(22.55,'pip','Earthling! Take us to the emergency!'),(27.1,'child',"Um... it's over there."),(31.55,'pip',"It's worse than I feared."),(34.45,'child',"It's just my kite."),(37.0,'pip','Exactly.'),(39.5,'zig','Stand back. Science is happening!'),(47.1,'narrator','The rescue became very... advanced.'),(56.1,'child','Thanks, Momo.'),(59.0,'momo','Momo help.'),(63.1,'pip','Earth is safe!'),(74.2,'bloop','...my snack.'),(77.1,'pip','NEW EMERGENCY!')]
VOICE={'narrator':('en-GB-SoniaNeural','-5%','+0Hz'),'pip':('en-GB-RyanNeural','+12%','+22Hz'),'bloop':('en-GB-SoniaNeural','+16%','+28Hz'),'zig':('en-GB-RyanNeural','+20%','+10Hz'),'momo':('en-GB-RyanNeural','-20%','-28Hz'),'child':('en-GB-SoniaNeural','+8%','+12Hz')}
def run(args):
 p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT); out=p.stdout.strip()
 if p.returncode: raise RuntimeError(out[-6000:])
 return out
async def edge_voice(text,voice,rate,pitch,target):
 import edge_tts
 await edge_tts.Communicate(text,voice=voice,rate=rate,pitch=pitch).save(str(target))
def espeak_voice(text,speaker,target):
 wav=target.with_suffix('.wav'); speed={'narrator':150,'pip':190,'bloop':200,'zig':205,'momo':120,'child':180}[speaker]; pitch={'narrator':50,'pip':65,'bloop':72,'zig':58,'momo':32,'child':67}[speaker]
 run(['espeak-ng','-s',str(speed),'-p',str(pitch),'-w',str(wav),text]); run(['ffmpeg','-y','-i',str(wav),'-c:a','libmp3lame','-q:a','3',str(target)]); wav.unlink(missing_ok=True)
def voices(folder):
 out=[]
 for i,(_,sp,text) in enumerate(LINES):
  t=folder/f'voice-{i:02d}-{sp}.mp3'; v,r,p=VOICE[sp]
  try: asyncio.run(edge_voice(text,v,r,p,t))
  except Exception: espeak_voice(text,sp,t)
  out.append(t)
 return out
def wav_write(path,a,sr=22050):
 a=np.clip(a,-1,1); d=(a*32767).astype(np.int16)
 with wave.open(str(path),'wb') as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(d.tobytes())
def music(path,sr=22050):
 n=int(RUNTIME*sr); a=np.zeros(n,dtype=np.float32); chords=[(261.63,329.63,392),(196,246.94,392),(220,261.63,329.63),(174.61,220,349.23)]
 for k,start in enumerate(np.arange(0,RUNTIME,.5)):
  f=chords[(k//8)%4][k%3]; m=int(min(.38,RUNTIME-start)*sr); t=np.arange(m)/sr; i=int(start*sr); a[i:i+m]+=0.08*np.exp(-5.5*t)*np.sin(2*np.pi*f*t)
 wav_write(path,a,sr)
def sfx(path,sr=22050):
 n=int(RUNTIME*sr); a=np.zeros(n,dtype=np.float32)
 def tone(st,d,f,amp):
  i=int(st*sr); m=min(int(d*sr),n-i); t=np.arange(m)/sr; a[i:i+m][:]+=amp*np.exp(-2*t)*np.sin(2*np.pi*f*t)
 for st in (1.4,2.0,2.6): tone(st,.3,880,.2)
 tone(17,.8,220,.22); tone(40.6,8.5,130,.05); tone(77.1,.9,660,.12)
 wav_write(path,a,sr)
def normalize(motion,work):
 seg=[]
 for sid,dur in SHOTS:
  c=list(motion.rglob(f'*s{sid}.mp4'))
  if not c: raise FileNotFoundError(sid)
  dst=work/f'segment-{sid}.mp4'; vf='scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=24,format=yuv420p'
  run(['ffmpeg','-y','-stream_loop','-1','-i',str(c[0]),'-t',str(dur),'-an','-vf',vf,'-c:v','libx264','-preset','veryfast','-crf','20',str(dst)]); seg.append(dst)
 return seg
def main():
 motion=Path(sys.argv[1]).resolve(); DIST.mkdir(exist_ok=True)
 with tempfile.TemporaryDirectory() as td:
  w=Path(td); vd=w/'voices'; vd.mkdir(); vs=voices(vd); mu=w/'music.wav'; sf=w/'sfx.wav'; music(mu); sfx(sf); seg=normalize(motion,w)
  lst=w/'concat.txt'; lst.write_text(''.join(f"file '{p.as_posix()}'\n" for p in seg)); pic=w/'picture.mp4'; run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(lst),'-c','copy',str(pic)])
  args=['ffmpeg','-y','-i',str(pic),'-i',str(mu),'-i',str(sf)]; [args.extend(['-i',str(v)]) for v in vs]; filt=['[1:a]volume=0.14[bg]','[2:a]volume=0.7[sfx]']; labels=['[bg]','[sfx]']
  for i,(st,_,_) in enumerate(LINES): ms=int(st*1000); filt.append(f'[{i+3}:a]adelay={ms}|{ms},volume=1.25[v{i}]'); labels.append(f'[v{i}]')
  filt.append(''.join(labels)+f'amix=inputs={len(labels)}:duration=longest,alimiter=limit=0.95[aout]'); args+=['-filter_complex',';'.join(filt),'-map','0:v:0','-map','[aout]','-c:v','copy','-c:a','aac','-b:a','192k','-t',str(RUNTIME),str(FINAL)]; run(args)
 out=json.loads(run(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_type','-of','json',str(FINAL)])); dur=float(out['format']['duration']); streams=out['streams']; report={'pass':78<=dur<=82 and any(s['codec_type']=='video' for s in streams) and any(s['codec_type']=='audio' for s in streams),'duration_seconds':dur,'size_bytes':int(out['format']['size'])}; (DIST/'earth-needs-help-e001-final-qa.json').write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report,indent=2)); return 0 if report['pass'] else 1
if __name__=='__main__': raise SystemExit(main())
