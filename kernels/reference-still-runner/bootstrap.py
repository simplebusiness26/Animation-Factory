#!/usr/bin/env python3
"""Kaggle bootstrap for the FLUX.2 reference-still batch runner."""
from __future__ import annotations

import subprocess
import sys
import urllib.request
from pathlib import Path

WORK = Path('/kaggle/working')
BASE = 'https://raw.githubusercontent.com/simplebusiness26/Animation-Factory/main'
RUNNER_URL = f'{BASE}/kernels/reference-still-runner/main.py'
JOB_URL = f'{BASE}/shows/earth-needs-help/episodes/001-great-earth-emergency/episode001-image-job.json'


def fetch(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        target.write_bytes(response.read())


def main() -> int:
    runner = WORK / 'reference-still-runner.py'
    job = WORK / 'episode-image-job.json'
    fetch(RUNNER_URL, runner)
    fetch(JOB_URL, job)
    proc = subprocess.run([sys.executable, str(runner)], cwd=str(WORK))
    return int(proc.returncode)


if __name__ == '__main__':
    raise SystemExit(main())
