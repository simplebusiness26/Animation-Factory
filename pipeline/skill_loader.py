"""Lightweight loader for Animation Factory skills and episode context.

No third-party dependencies are required. The module is intentionally simple so it can
run in GitHub Actions, Kaggle, or another free Python environment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "pipeline" / "skills.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_registry() -> dict[str, Any]:
    return load_json(REGISTRY_PATH)


def stage(stage_id: str) -> dict[str, Any]:
    for item in load_registry()["stages"]:
        if item["id"] == stage_id:
            return item
    raise KeyError(f"Unknown pipeline stage: {stage_id}")


def load_skill(stage_id: str) -> str:
    item = stage(stage_id)
    skill_path = item.get("skill")
    if not skill_path:
        return ""
    path = ROOT / skill_path
    if not path.is_file():
        raise FileNotFoundError(f"Skill file missing for {stage_id}: {skill_path}")
    return path.read_text(encoding="utf-8")


def episode_dir(show_slug: str, episode_slug: str) -> Path:
    return ROOT / "shows" / show_slug / "episodes" / episode_slug


def build_episode_context(show_slug: str, episode_slug: str, stage_id: str) -> dict[str, Any]:
    """Return the canonical context packet an agent should receive for one stage."""
    show_dir = ROOT / "shows" / show_slug
    ep_dir = episode_dir(show_slug, episode_slug)

    required_show_files = ["show-bible.md", "character-bible.md", "style-bible.md"]
    show_context: dict[str, str] = {}
    for filename in required_show_files:
        path = show_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Required canonical show file missing: {path.relative_to(ROOT)}")
        show_context[filename] = path.read_text(encoding="utf-8")

    production_path = ep_dir / "production.json"
    if not production_path.is_file():
        raise FileNotFoundError(f"Episode production file missing: {production_path.relative_to(ROOT)}")

    episode_files: dict[str, str] = {}
    for filename in ("script.md", "shot-list.md", "prompts.md", "voice-notes.md"):
        path = ep_dir / filename
        if path.is_file():
            episode_files[filename] = path.read_text(encoding="utf-8")

    return {
        "stage": stage(stage_id),
        "skill": load_skill(stage_id),
        "agent_constitution": (ROOT / "AGENTS.md").read_text(encoding="utf-8"),
        "show": show_context,
        "production": load_json(production_path),
        "episode_files": episode_files,
        "quality_gates": load_json(ROOT / "pipeline" / "quality-gates.json"),
    }


def next_stage(completed_gates: set[str]) -> dict[str, Any] | None:
    """Return the first stage whose gate has not yet been completed."""
    for item in load_registry()["stages"]:
        if item["gate"] not in completed_gates:
            return item
    return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build an Animation Factory agent context packet")
    parser.add_argument("--show", required=True, help="Show slug, e.g. earth-needs-help")
    parser.add_argument("--episode", required=True, help="Episode folder slug")
    parser.add_argument("--stage", required=True, help="Pipeline stage id")
    args = parser.parse_args()

    packet = build_episode_context(args.show, args.episode, args.stage)
    print(json.dumps(packet, indent=2, ensure_ascii=False))
