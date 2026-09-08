"""Prepare immutable, validated Kaggle bootstraps before spending GPU quota."""
from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path
from pipeline.image_router import asset_path, load_json, plan_job

EPISODE = 'shows/earth-needs-help/episodes/001-great-earth-emergency'

def source_revision(root: Path, paths: list[str]) -> str:
    # A remote snapshot must actually contain every local file being approved.
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise RuntimeError('Cannot resolve an immutable source commit')
    for path in paths:
        try:
            expected = subprocess.check_output(['git', 'show', f'{revision}:{path}'], cwd=root, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f'Commit {path} before submitting its Kaggle snapshot') from exc
        if expected != asset_path(root, path).read_bytes():
            raise RuntimeError(f'Commit {path} before submitting its Kaggle snapshot')
    return revision

def image_inputs(root: Path) -> list[str]:
    production = load_json(root / EPISODE / 'production.json')
    backend = production['image_backend']
    if backend['runner'] != 'kernels/reference-still-runner':
        raise ValueError('Unsupported automated image runner')
    job = load_json(asset_path(root, backend['job']))
    config = load_json(asset_path(root, backend['router_config']))
    plan = plan_job(job, config, root=root)
    if plan['status'] != 'ready':
        raise ValueError('Image routing blocked: ' + json.dumps(plan))
    paths = [backend['job'], backend['router_config'], job['continuity_manifest'],
             'pipeline/__init__.py', 'pipeline/image_router.py', 'pipeline/production_guard.py',
             'kernels/reference-still-runner/main.py',
             'kernels/reference-still-runner/bootstrap.py',
             'kernels/reference-still-runner/requirements.txt']
    for row in plan['shots']:
        paths.extend(ref['path'] for ref in row['references'])
        if row.get('approved_input_path'):
            paths.append(row['approved_input_path'])
    return list(dict.fromkeys(paths))

def prepare_image_bootstrap(root: Path, target: Path) -> None:
    paths = image_inputs(root)
    revision = source_revision(root, paths)
    source = (root / 'kernels/reference-still-runner/bootstrap.py').read_text(encoding='utf-8')
    source = source.replace('__SOURCE_COMMIT__', revision)
    source = source.replace('INPUT_PATHS = []', 'INPUT_PATHS = ' + repr(paths))
    job_path = load_json(root / EPISODE / 'production.json')['image_backend']['job']
    source = source.replace('__IMAGE_JOB_PATH__', job_path)
    target.write_text(source, encoding='utf-8')

def prepare_motion_bootstrap(root: Path, target: Path) -> None:
    job_path = f'{EPISODE}/episode001-motion-job.json'
    qa_path = f'{EPISODE}/continuity-qa.json'
    job = load_json(root / job_path)
    qa = load_json(root / qa_path)
    if qa.get('status') != 'approved':
        raise RuntimeError('Motion requires the exact still batch to pass continuity review')
    from pipeline.image_router import verified_image
    rows = {row['id']: row for row in qa.get('shots', [])}
    paths = [job_path, qa_path, 'kernels/episode-motion-runner/main.py',
             'kernels/episode-motion-runner/bootstrap.py']
    if not job.get('shots'):
        raise ValueError('Motion job contains no shots')
    for shot in job['shots']:
        path = f"{EPISODE}/assets/stills/{Path(shot['still']).name}"
        row = rows.get(shot['id'], {})
        if row.get('file') != path:
            raise RuntimeError(f"Missing approval for motion shot {shot['id']}")
        verified_image(root, path, row.get('sha256', ''))
        paths.append(path)
    revision = source_revision(root, paths)
    source = (root / 'kernels/episode-motion-runner/bootstrap.py').read_text(encoding='utf-8')
    target.write_text(source.replace('__SOURCE_COMMIT__', revision), encoding='utf-8')
