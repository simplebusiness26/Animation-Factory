#!/usr/bin/env python3
"""Kaggle bootstrap for Episode 001 motion rendering.

Kaggle may omit auxiliary source files when pushing script kernels. This
bootstrap downloads the authoritative motion runner, job spec, and all stills
from the public Animation-Factory repository into /kaggle/working, then runs
the real motion runner from there so relative paths resolve reliably.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

WORK = Path('/kaggle/working')
BASE = 'https://raw.githubusercontent.com/simplebusiness26/Animation-Factory/main'
RUNNER_URL = f'{BASE}/kernels/episode-motion-runner/main.py'
JOB_URL = f'{BASE}/shows/earth-needs-help/episodes/001-great-earth-emergency/episode001-motion-job.json'
STILLS_BASE = f'{BASE}/shows/earth-needs-help/episodes/001-great-earth-emergency/assets/stills'


def fetch(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        target.write_bytes(response.read())


def main() -> int:
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
        fetch(f'{STILLS_BASE}/{name}', stills / name)

    proc = subprocess.run([sys.executable, str(runner)], cwd=str(WORK))
    return int(proc.returncode)


if __name__ == '__main__':
    raise SystemExit(main())
