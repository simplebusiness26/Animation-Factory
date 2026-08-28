"""Validate Animation Factory skill registry and canonical production files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def validate_skill(path: Path, errors: list[str]) -> None:
    if not path.is_file():
        fail(f"Missing skill: {path.relative_to(ROOT)}", errors)
        return
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        fail(f"Skill missing YAML-style front matter: {path.relative_to(ROOT)}", errors)
        return
    end = text.find("\n---\n", 4)
    if end == -1:
        fail(f"Skill front matter is not closed: {path.relative_to(ROOT)}", errors)
        return
    header = text[4:end]
    if "name:" not in header or "description:" not in header:
        fail(f"Skill front matter needs name and description: {path.relative_to(ROOT)}", errors)


def main() -> int:
    errors: list[str] = []

    registry_path = ROOT / "pipeline" / "skills.json"
    gates_path = ROOT / "pipeline" / "quality-gates.json"
    agents_path = ROOT / "AGENTS.md"

    for path in (registry_path, gates_path, agents_path):
        if not path.is_file():
            fail(f"Missing required pipeline file: {path.relative_to(ROOT)}", errors)

    if errors:
        print("\n".join(f"ERROR: {e}" for e in errors))
        return 1

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        json.loads(gates_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid pipeline JSON: {exc}")
        return 1

    stage_ids: set[str] = set()
    gates: set[str] = set()
    for item in registry.get("stages", []):
        stage_id = item.get("id")
        gate = item.get("gate")
        if not stage_id or stage_id in stage_ids:
            fail(f"Missing or duplicate stage id: {stage_id!r}", errors)
        else:
            stage_ids.add(stage_id)
        if not gate or gate in gates:
            fail(f"Missing or duplicate gate: {gate!r}", errors)
        else:
            gates.add(gate)
        skill = item.get("skill")
        if skill:
            validate_skill(ROOT / skill, errors)

    shows_root = ROOT / "shows"
    if shows_root.is_dir():
        for show_dir in sorted(p for p in shows_root.iterdir() if p.is_dir()):
            for filename in ("show-bible.md", "character-bible.md", "style-bible.md"):
                if not (show_dir / filename).is_file():
                    fail(f"Show {show_dir.name} missing canonical file: {filename}", errors)

            episodes_dir = show_dir / "episodes"
            if episodes_dir.is_dir():
                for ep_dir in sorted(p for p in episodes_dir.iterdir() if p.is_dir()):
                    production = ep_dir / "production.json"
                    if not production.is_file():
                        fail(f"Episode {ep_dir.relative_to(ROOT)} missing production.json", errors)
                        continue
                    try:
                        data = json.loads(production.read_text(encoding="utf-8"))
                    except json.JSONDecodeError as exc:
                        fail(f"Invalid production.json in {ep_dir.relative_to(ROOT)}: {exc}", errors)
                        continue
                    shot_ids = [shot.get("id") for shot in data.get("shots", [])]
                    if len(shot_ids) != len(set(shot_ids)):
                        fail(f"Duplicate shot ids in {ep_dir.relative_to(ROOT)}", errors)

    if errors:
        print("\n".join(f"ERROR: {e}" for e in errors))
        return 1

    print(f"Animation Factory validation passed: {len(stage_ids)} stages, {len(gates)} gates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
