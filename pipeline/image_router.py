#!/usr/bin/env python3
"""Validate image jobs and select free generation or a hash-bound approved import.

Readiness describes validated inputs, not generated output or visual approval.
This module performs no model downloads, generation, or paid API calls.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'pipeline/image-generation.json'
CHATGPT_ROUTE = 'chatgpt-image-account'
FLUX_ROUTE = 'flux2-klein-kaggle'
SDXL_ROUTE = 'sdxl-layered-fallback'

def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'Expected a JSON object: {path.name}')
    return value

def asset_path(root: Path, value: str) -> Path:
    rel = Path(str(value))
    target = (root / rel).resolve()
    if rel.is_absolute() or '..' in rel.parts or root.resolve() not in target.parents:
        raise ValueError(f'Asset path must stay inside the repository: {value}')
    if not target.is_file():
        raise ValueError(f'Missing asset: {value}')
    return target

def verified_image(root: Path, value: str, expected: str, *, encoded: bool = False) -> bytes:
    from PIL import Image
    if not re.fullmatch(r'[0-9a-f]{64}', str(expected)):
        raise ValueError(f'Missing or invalid SHA-256 for {value}')
    raw = asset_path(root, value).read_bytes()
    if encoded:
        raw = base64.b64decode(raw.strip(), validate=True)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f'Image hash mismatch: {value}')
    with Image.open(io.BytesIO(raw)) as image:
        image.verify()
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        if min(image.size) < 64:
            raise ValueError(f'Image is too small: {value}')
    return raw

def validate_manifest(manifest: dict) -> None:
    if manifest.get('status') != 'locked' or (manifest.get('reference_pack') or {}).get('status') != 'locked':
        raise ValueError('CONTINUITY_BLOCK: reference pack is not locked')
    policy = manifest.get('canon_policy') or {}
    for field in ('approved_visual_reference_overrides_text', 'load_references_for_every_shot', 'continuity_qa_required_before_motion'):
        if policy.get(field) is not True:
            raise ValueError(f'CONTINUITY_BLOCK: {field} must be enabled')
    if policy.get('text_only_recurring_character_generation_allowed') is not False:
        raise ValueError('CONTINUITY_BLOCK: text-only recurring identity must be disabled')

def choose_route(job: dict, config: dict, *, root: Path = ROOT, manifest: dict | None = None) -> dict:
    purpose = str(job.get('purpose') or 'routine').strip().lower()
    requested = str(job.get('route') or 'auto').strip().lower()
    if requested not in {'auto', CHATGPT_ROUTE, FLUX_ROUTE, SDXL_ROUTE}:
        raise ValueError(f'Unsupported image route: {requested}')
    route = config.get('routing', {}).get(purpose, config.get('default_route', FLUX_ROUTE)) if requested == 'auto' else requested
    provider = config.get('providers', {}).get(route)
    if not provider:
        raise ValueError(f'Route {route!r} is not configured')
    decision = {'route': route, 'status': 'ready', 'automated': route != CHATGPT_ROUTE,
                'provider': provider.get('provider'), 'model': provider.get('model'),
                'accelerator': provider.get('accelerator'), 'references': []}
    imported = job.get('approved_input_path')
    if route == CHATGPT_ROUTE or imported:
        decision['automated'] = False
        if not imported:
            decision.update(status='awaiting_approved_chatgpt_image', reason='An approved imported image is required.')
            return decision
        if job.get('qa_status') != 'approved':
            decision.update(status='awaiting_import_approval', reason='The imported image has not passed visual QA.')
            return decision
        try:
            verified_image(root, imported, job.get('approved_input_sha256', ''))
        except (OSError, ValueError) as exc:
            decision.update(status='blocked_invalid_import', reason=str(exc))
            return decision
        decision.update(approved_input_path=imported, approved_input_sha256=job['approved_input_sha256'], reason='Reuse the exact approved image.')
        return decision
    characters = job.get('characters', [])
    if not isinstance(characters, list) or any(not isinstance(x, str) or not x for x in characters) or len(set(characters)) != len(characters):
        raise ValueError('characters must be a list of unique names')
    try:
        if characters and manifest is None:
            raise ValueError('Recurring characters require a locked continuity manifest')
        if manifest is not None:
            validate_manifest(manifest)
        for name in characters:
            spec = (manifest.get('canonical_cast') or {}).get(name) or {}
            path = spec.get('reference', '')
            verified_image(root, path, spec.get('decoded_sha256', ''), encoded=True)
            decision['references'].append({'name': name, 'path': path, 'sha256': spec['decoded_sha256'], 'identity': spec.get('identity', name)})
    except (OSError, ValueError) as exc:
        decision.update(status='blocked_missing_references', reason=str(exc))
        return decision
    if route == SDXL_ROUTE:
        decision.update(status='blocked_unsupported_route', reason='The legacy SDXL fallback requires a separately validated job.')
        return decision
    decision.update(reference_count=len(decision['references']), reason='Image inputs validated; generation still requires visual QA.')
    return decision

def plan_job(job: dict, config: dict, *, root: Path = ROOT) -> dict:
    if 'shots' not in job:
        manifest = load_json(asset_path(root, job['continuity_manifest'])) if job.get('continuity_manifest') else None
        return choose_route(job, config, root=root, manifest=manifest)
    shots = job['shots']
    if job.get('schema_version') != 1 or not isinstance(shots, list) or not shots:
        raise ValueError('Image batch requires schema_version 1 and at least one shot')
    if job.get('provider') != FLUX_ROUTE or job.get('model') != config['providers'][FLUX_ROUTE]['model']:
        raise ValueError('Image batch model/provider must match the configured free route')
    revision = config['providers'][FLUX_ROUTE].get('revision', '')
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('The model must be pinned to an immutable revision')
    for field, maximum in (('width', 1536), ('height', 1024)):
        value = job.get(field)
        if type(value) is not int or not 256 <= value <= maximum or value % 16:
            raise ValueError(f'{field} must be a multiple of 16 between 256 and {maximum}')
    if type(job.get('steps')) is not int or not 1 <= job['steps'] <= 50:
        raise ValueError('steps must be an integer between 1 and 50')
    guidance = job.get('guidance_scale')
    if not isinstance(guidance, (int, float)) or not math.isfinite(guidance) or not 0 <= guidance <= 10:
        raise ValueError('guidance_scale must be finite and between 0 and 10')
    for field in ('style_lock', 'reference_rule'):
        if not isinstance(job.get(field), str) or not job[field].strip():
            raise ValueError(f'Image batch is missing {field}')
    manifest = load_json(asset_path(root, job.get('continuity_manifest', '')))
    validate_manifest(manifest)
    rows, seen = [], set()
    for shot in shots:
        sid = shot.get('id') if isinstance(shot, dict) else None
        if not isinstance(sid, str) or not re.fullmatch(r'[0-9]{3}[a-z]?', sid) or sid in seen:
            raise ValueError(f'Invalid or duplicate shot id: {sid!r}')
        seen.add(sid)
        if 'characters' not in shot:
            raise ValueError(f'Shot {sid} must declare characters explicitly (use [] for a background)')
        if not isinstance(shot.get('prompt'), str) or not shot['prompt'].strip():
            raise ValueError(f'Shot {sid} is missing its prompt')
        if type(shot.get('seed')) is not int or not 0 <= shot['seed'] < 2**63:
            raise ValueError(f'Shot {sid} has an invalid seed')
        rows.append({'id': sid, **choose_route(shot, config, root=root, manifest=manifest)})
    return {'status': 'ready' if all(row['status'] == 'ready' for row in rows) else 'blocked',
            'model_revision': revision, 'shots': rows}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('job', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        decision = plan_job(load_json(args.job), load_json(CONFIG))
    except (ValueError, OSError) as exc:
        decision = {'status': 'blocked', 'reason': str(exc)}
    payload = json.dumps(decision, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding='utf-8')
    print(payload, end='')
    return 0 if decision['status'] == 'ready' else 2

if __name__ == '__main__':
    raise SystemExit(main())
