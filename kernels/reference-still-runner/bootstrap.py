#!/usr/bin/env python3
"""Kaggle bootstrap. The bridge pins this template to the reviewed source commit."""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

WORK = Path('/kaggle/working')
SOURCE_REF = '__SOURCE_COMMIT__'
INPUT_PATHS = []
JOB_PATH = '__IMAGE_JOB_PATH__'
PUBLIC_ROOT = 'https://raw.githubusercontent.com/simplebusiness26/Animation-Factory'

def fetch(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        target.write_bytes(response.read())

def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    try:
        if not re.fullmatch(r'[0-9a-f]{40}', SOURCE_REF) or not INPUT_PATHS:
            raise RuntimeError('Use the bridge to prepare a pinned image job before submission')
        # The live pause is deliberately read separately from immutable model inputs.
        with urllib.request.urlopen(f'{PUBLIC_ROOT}/main/automation/episode001-state.json', timeout=30) as response:
            state = json.load(response)
        if not isinstance(state, dict) or not state.get('phase') or state.get('paused_by_user') or state['phase'] in {'paused_by_user', 'repair_required', 'failed'}:
            raise RuntimeError('Episode 001 is paused or requires repair; generation blocked')
        root = WORK / 'image-source'
        live_state = root / 'automation/episode001-state.json'
        live_state.parent.mkdir(parents=True, exist_ok=True)
        live_state.write_text(json.dumps(state), encoding='utf-8')
        for value in INPUT_PATHS:
            rel = Path(value)
            if rel.is_absolute() or '..' in rel.parts:
                raise ValueError('Invalid snapshot input path')
            fetch(f'{PUBLIC_ROOT}/{SOURCE_REF}/{rel.as_posix()}', root / rel)
        env = dict(os.environ, ANIMATION_SOURCE_ROOT=str(root), ANIMATION_IMAGE_JOB=JOB_PATH,
                   ANIMATION_SOURCE_COMMIT=SOURCE_REF)
        proc = subprocess.run([sys.executable, str(root / 'kernels/reference-still-runner/main.py')], cwd=str(WORK), env=env)
        return int(proc.returncode)
    except Exception as exc:
        payload = {'success': False, 'stage': 'bootstrap', 'error': f'{type(exc).__name__}: {exc}', 'source_commit': SOURCE_REF}
        (WORK / 'animation-factory-image-report.json').write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(payload), flush=True)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
