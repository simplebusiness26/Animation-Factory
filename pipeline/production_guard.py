"""Shared, fail-closed Episode 001 launch guard (no network or GPU work)."""
from __future__ import annotations
import json
from pathlib import Path
STATE_PATH = 'automation/episode001-state.json'

def is_paused(state: dict) -> bool:
    return bool(state.get('paused_by_user')) or state.get('phase') == 'paused_by_user'

def load_state(root: Path) -> dict:
    try:
        state = json.loads((root / STATE_PATH).read_text(encoding='utf-8'))
        if not isinstance(state, dict) or not state.get('phase'):
            raise ValueError('state must contain a phase')
        return state
    except (OSError, ValueError) as exc:
        raise RuntimeError('Episode 001 state is missing or unreadable; submission blocked') from exc

def require_running(state: dict) -> None:
    if is_paused(state):
        raise RuntimeError('Episode 001 is paused. Submission is blocked; status/output checks remain available.')
    if state.get('phase') in {'repair_required', 'failed'}:
        raise RuntimeError('Episode 001 requires repair before another submission')

def require_launch_allowed(root: Path) -> None:
    require_running(load_state(root))
