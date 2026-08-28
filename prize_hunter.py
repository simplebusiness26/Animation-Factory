#!/usr/bin/env python3
"""Kaggle Prize Hunter.

Scans currently available Kaggle competitions and ranks cash-prize opportunities by
preliminary expected-value signals. It does not enter competitions or submit entries.
Those remain explicit approval-gated actions.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "prize-hunter"
HISTORY_DIR = OUT_DIR / "history"
MONEY_RE = re.compile(r"([\$£€])\s*([0-9][0-9,]*(?:\.[0-9]+)?)")


@dataclass
class Opportunity:
    ref: str
    deadline: str
    category: str
    reward: str
    prize_value: float
    currency: str
    team_count: int
    days_left: float
    score: float
    verdict: str
    user_has_entered: bool
    user_rank: int
    reasons: list[str]


def run_kaggle_rows() -> list[dict[str, Any]]:
    """Read competition rows from Kaggle CLI 1.8.x CSV output."""
    proc = subprocess.run(
        [
            "kaggle",
            "competitions",
            "list",
            "-v",
            "--page-size",
            "100",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())

    raw = proc.stdout.strip()
    # Kaggle may emit an upgrade warning before the CSV header. Locate the header.
    lines = raw.splitlines()
    header_index = next((i for i, line in enumerate(lines) if line.startswith("ref,")), None)
    if header_index is None:
        raise RuntimeError(f"Could not find Kaggle CSV header in output: {raw[:1200]}")

    csv_text = "\n".join(lines[header_index:])
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    return [dict(row) for row in rows]


def parse_reward(text: Any) -> tuple[float, str]:
    value = str(text or "").strip()
    match = MONEY_RE.search(value)
    if not match:
        return 0.0, ""
    symbol, amount = match.groups()
    return float(amount.replace(",", "")), symbol


def parse_deadline(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def to_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def to_int(value: Any) -> int:
    try:
        return int(float(str(value or "0").strip()))
    except ValueError:
        return 0


def preliminary_score(prize: float, teams: int, days_left: float) -> tuple[float, list[str]]:
    reasons: list[str] = []
    teams = max(teams, 1)

    # 0-35: size of the prize, with diminishing returns.
    prize_score = min(35.0, max(0.0, 7.0 * math.log10(max(prize, 1.0))))

    # 0-25: fewer existing teams means a less crowded field.
    crowd_score = max(0.0, 25.0 - 8.0 * math.log10(teams + 1.0))

    # 0-25: prize-per-team is a crude but useful expected-value signal.
    prize_per_team = prize / teams
    efficiency_score = min(25.0, 8.0 * math.log10(prize_per_team + 1.0))

    # 0-15: enough time to work, without over-rewarding far-future contests.
    if 21 <= days_left <= 90:
        time_score = 15.0
    elif 8 <= days_left < 21:
        time_score = 12.0
    elif 90 < days_left <= 180:
        time_score = 10.0
    elif 3 <= days_left < 8:
        time_score = 6.0
    elif days_left > 180:
        time_score = 7.0
    else:
        time_score = 0.0

    if teams <= 50:
        reasons.append(f"low crowd ({teams} teams)")
    elif teams >= 1000:
        reasons.append(f"very crowded ({teams} teams)")
    else:
        reasons.append(f"{teams} teams")

    if prize_per_team >= 1000:
        reasons.append(f"strong prize/team ({prize_per_team:,.0f})")
    elif prize_per_team >= 100:
        reasons.append(f"reasonable prize/team ({prize_per_team:,.0f})")
    else:
        reasons.append(f"weak prize/team ({prize_per_team:,.0f})")

    if days_left < 3:
        reasons.append("almost no time left")
    elif days_left < 8:
        reasons.append("tight deadline")
    elif days_left <= 90:
        reasons.append(f"{days_left:.0f} days left")
    else:
        reasons.append(f"long runway ({days_left:.0f} days)")

    score = round(prize_score + crowd_score + efficiency_score + time_score, 1)
    return score, reasons


def build_opportunities(rows: list[dict[str, Any]]) -> list[Opportunity]:
    now = datetime.now(timezone.utc)
    results: list[Opportunity] = []

    for row in rows:
        prize, currency = parse_reward(row.get("reward"))
        if prize <= 0:
            continue

        deadline = parse_deadline(row.get("deadline"))
        if deadline is None:
            continue
        days_left = (deadline - now).total_seconds() / 86400.0
        if days_left <= 0:
            continue

        teams = to_int(row.get("teamCount"))
        score, reasons = preliminary_score(prize, teams, days_left)
        verdict = "HUNT" if score >= 70 else "INVESTIGATE" if score >= 58 else "WATCH" if score >= 45 else "PASS"

        results.append(
            Opportunity(
                ref=str(row.get("ref") or ""),
                deadline=deadline.isoformat(),
                category=str(row.get("category") or "unknown"),
                reward=str(row.get("reward") or ""),
                prize_value=prize,
                currency=currency,
                team_count=teams,
                days_left=round(days_left, 1),
                score=score,
                verdict=verdict,
                user_has_entered=to_bool(row.get("userHasEntered")),
                user_rank=to_int(row.get("userRank")),
                reasons=reasons,
            )
        )

    results.sort(key=lambda x: (x.score, x.prize_value), reverse=True)
    return results


def markdown_report(opportunities: list[Opportunity], limit: int = 15) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Kaggle Prize Hunter",
        "",
        f"Generated: **{generated}**",
        "",
        "Preliminary ranking only. Top candidates still need a rules/data/compute/eligibility dossier before we decide whether they are suitable to pursue.",
        "",
    ]

    if not opportunities:
        lines += ["No active cash-prize competitions were found.", ""]
        return "\n".join(lines)

    lines += [
        "| # | Verdict | Score | Competition | Prize | Teams | Days left | Why it surfaced |",
        "|---:|---|---:|---|---:|---:|---:|---|",
    ]
    for i, item in enumerate(opportunities[:limit], 1):
        why = "; ".join(item.reasons)
        lines.append(
            f"| {i} | **{item.verdict}** | **{item.score:.1f}** | `{item.ref}` | {item.reward} | {item.team_count} | {item.days_left:.0f} | {why} |"
        )

    top = opportunities[0]
    lines += [
        "",
        "## Current lead",
        "",
        f"**{top.ref}** — {top.reward}, {top.team_count} teams, {top.days_left:.0f} days left, preliminary score **{top.score:.1f}/100**.",
        "",
        "Next gate: inspect its description, rules, evaluation metric, data size, likely hardware requirement, submission limits and eligibility before spending compute.",
        "",
        "## Safety rails",
        "",
        "Prize Hunter may discover and analyse competitions automatically. Entering, accepting rules, spending paid resources, or submitting an entry remains approval-gated and must satisfy the competition's eligibility requirements.",
        "",
    ]
    return "\n".join(lines)


def write_reports(opportunities: list[Opportunity], report: str) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    HISTORY_DIR.mkdir(exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(opportunities),
        "opportunities": [asdict(o) for o in opportunities],
    }
    (OUT_DIR / "latest.md").write_text(report + "\n", encoding="utf-8")
    (OUT_DIR / "latest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (HISTORY_DIR / f"{stamp}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    rows = run_kaggle_rows()
    opportunities = build_opportunities(rows)
    report = markdown_report(opportunities, max(1, min(args.limit, 30)))
    write_reports(opportunities, report)
    if args.stdout:
        print(report)
    else:
        print(f"Prize Hunter ranked {len(opportunities)} active cash-prize competitions.")
        if opportunities:
            print(f"Leader: {opportunities[0].ref} ({opportunities[0].score:.1f}/100)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
