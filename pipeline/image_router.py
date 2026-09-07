#!/usr/bin/env python3
"""Deterministic image-route selector for Animation Factory.

This file deliberately does not call any paid API. It decides whether a still can
run automatically on Kaggle/FLUX, should fall back to the legacy SDXL route, or
must wait for an image created through the user's existing ChatGPT account.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "pipeline" / "image-generation.json"

CHATGPT_ROUTE = "chatgpt-image-account"
FLUX_ROUTE = "flux2-klein-kaggle"
SDXL_ROUTE = "sdxl-layered-fallback"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def choose_route(job: dict, config: dict) -> dict:
    purpose = str(job.get("purpose") or "routine").strip().lower()
    requested = str(job.get("route") or "auto").strip().lower()
    refs = [str(x) for x in (job.get("reference_paths") or []) if str(x).strip()]
    recurring = [str(x) for x in (job.get("characters") or []) if str(x).strip()]

    if requested not in {"auto", CHATGPT_ROUTE, FLUX_ROUTE, SDXL_ROUTE}:
        raise ValueError(f"Unsupported image route: {requested}")

    if requested == "auto":
        route = config.get("routing", {}).get(purpose, config.get("default_route", FLUX_ROUTE))
    else:
        route = requested

    if route == CHATGPT_ROUTE:
        imported = str(job.get("approved_input_path") or "").strip()
        return {
            "route": CHATGPT_ROUTE,
            "status": "ready" if imported else "awaiting_approved_chatgpt_image",
            "automated": False,
            "approved_input_path": imported or None,
            "reason": "Quality-route image must be created in ChatGPT and committed as an approved asset before automation continues.",
        }

    if recurring and not refs:
        return {
            "route": route,
            "status": "blocked_missing_references",
            "automated": route != CHATGPT_ROUTE,
            "reason": "Recurring characters are present but no locked reference images were supplied.",
        }

    provider = config.get("providers", {}).get(route)
    if not provider:
        raise ValueError(f"Route {route!r} is not configured")

    return {
        "route": route,
        "status": "ready",
        "automated": True,
        "provider": provider.get("provider"),
        "model": provider.get("model"),
        "accelerator": provider.get("accelerator"),
        "reference_count": len(refs),
        "reason": "Automatic zero-cost image route selected.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job", type=Path, help="Path to an image-job JSON file")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    config = load_json(CONFIG)
    job = load_json(args.job)
    decision = choose_route(job, config)
    payload = json.dumps(decision, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if decision["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
