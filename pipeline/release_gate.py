#!/usr/bin/env python3
"""A filename or ffprobe pass is insufficient approval to publish an episode."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

def verify_release(video: Path) -> None:
    qa = video.with_name(video.stem + '-qa.json')
    if not video.is_file() or not qa.is_file():
        raise ValueError('Final video and its QA record are both required')
    report = json.loads(qa.read_text(encoding='utf-8'))
    if not isinstance(report, dict) or report.get('technical_pass') is not True:
        raise ValueError('Final video has not passed technical checks')
    if report.get('visual_review') != 'approved' or report.get('audio_review') != 'approved':
        raise ValueError('Final visual and audio review are required before publication')
    digest = hashlib.sha256()
    with video.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    if report.get('sha256') != digest.hexdigest():
        raise ValueError('Final review does not match the current video')

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('video', type=Path)
    args = parser.parse_args()
    try:
        verify_release(args.video)
    except (OSError, ValueError) as exc:
        print(f'Release withheld: {exc}')
        return 2
    print('Final video matches its approved QA record')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
