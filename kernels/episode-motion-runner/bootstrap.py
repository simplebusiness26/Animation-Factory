#!/usr/bin/env python3
"""Kaggle bootstrap for Episode 001 motion rendering.

Kaggle may omit auxiliary source files when pushing script kernels. This
bootstrap downloads the authoritative motion runner, job spec, and all stills
from the public Animation-Factory repository into /kaggle/working, then runs
the real motion runner from there so relative paths resolve reliably.
"""
from __future__ import annotations

import json
import hashlib
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

WORK = Path('/kaggle/working')
SOURCE_REF = '__SOURCE_COMMIT__'
PUBLIC_ROOT = 'https://raw.githubusercontent.com/simplebusiness26/Animation-Factory'
BASE = f'{PUBLIC_ROOT}/{SOURCE_REF}'
QA_URL = f'{BASE}/shows/earth-needs-help/episodes/001-great-earth-emergency/continuity-qa.json'
RUNNER_URL = f'{BASE}/kernels/episode-motion-runner/main.py'
JOB_URL = f'{BASE}/shows/earth-needs-help/episodes/001-great-earth-emergency/episode001-motion-job.json'
STILLS_BASE = f'{BASE}/shows/earth-needs-help/episodes/001-great-earth-emergency/assets/stills'


def fetch(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        target.write_bytes(response.read())


def main() -> int:
    if not re.fullmatch(r'[0-9a-f]{40}', SOURCE_REF):
        raise RuntimeError('Motion bootstrap must be prepared by the guarded controller')
    with urllib.request.urlopen(f'{PUBLIC_ROOT}/main/automation/episode001-state.json', timeout=30) as response:
        state = json.load(response)
    if not isinstance(state, dict) or not state.get('phase') or state.get('paused_by_user') or state['phase'] in {'paused_by_user', 'repair_required', 'failed'}:
        raise RuntimeError('Episode 001 is paused or requires repair; motion blocked')
    with urllib.request.urlopen(QA_URL, timeout=30) as response:
        qa = json.load(response)
    if qa.get('status') != 'approved':
        raise RuntimeError('Motion requires continuity approval at the pinned source commit')
    approved = {row['id']: row for row in qa.get('shots', [])}
    runner = WORK / 'episode-motion-runner.py'
    job_path = WORK / 'episode-job.json'
    stills = WORK / 'stills'
    fetch(RUNNER_URL, runner)
    fetch(JOB_URL, job_path)

    job = json.loads(job_path.read_text(encoding='utf-8'))
    shots = job.get('shots', [])
    if not shots:
        raise RuntimeError('Remote Episode 001 motion job contains no shots')

    for shot in shots:
        name = Path(str(shot['still'])).name
        expected_path = f'shows/earth-needs-help/episodes/001-great-earth-emergency/assets/stills/{name}'
        review = approved.get(shot['id'], {})
        if review.get('file') != expected_path or not review.get('sha256'):
            raise RuntimeError(f"Missing hash-bound approval for shot {shot['id']}")
        fetch(f'{STILLS_BASE}/{name}', stills / name)
        if hashlib.sha256((stills / name).read_bytes()).hexdigest() != review['sha256']:
            raise RuntimeError(f'Approved still hash mismatch: {name}')

    proc = subprocess.run([sys.executable, str(runner)], cwd=str(WORK))
    return int(proc.returncode)


if __name__ == '__main__':
    raise SystemExit(main())
