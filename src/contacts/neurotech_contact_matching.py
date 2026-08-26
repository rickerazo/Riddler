#!/usr/bin/env python3
"""Match LinkedIn connections against Riddler's tiered neurotech company list.

Reads the user's existing LinkedIn connections export IN PLACE from job_os
(does not copy the CSV into this repo — see business/bp_v0.md decision log /
the kickoff plan's contacts section) and does a case-insensitive substring
match of each connection's `Company` field against the tiered list below.

Deliberately does NOT import or call job_os/scripts/analyze_linkedin_connections.py's
main() — that script hardcodes its output paths (data/reports/ohio_linkedin_connections.*,
data/reports/ohio_network_company_summary.*) and would OVERWRITE those files with a
company-filtered subset every time it's re-run with --company, corrupting job_os's own
Ohio job-search reports which are actively used by contact_lookup.py there. This module
is intentionally self-contained: it reads Connections.csv directly and writes its own
output under Riddler/outputs/, touching nothing in job_os.

No scraping, no LinkedIn login, no automated outreach — same guarantee job_os's analyzer
makes. This only reads a file already exported to disk by the user.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LINKEDIN_EXPORT = Path(
    "/Users/rick/job_os/linkedin_data/Basic_LinkedInDataExport.zip/Connections.csv"
)

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "outputs" / "contacts"

# Tiered neurotech company list — mirrors business/market_research_v1.md §2, sourced from
# job_os/data/reports/neurotech_biotech_expansion.md. Substrings are matched case-insensitively
# against each connection's `Company` field, so keep entries short/canonical (e.g. "Ceribell",
# not "Ceribell Inc.") to avoid missing real matches on LinkedIn's free-text company field.
TIER_A = [
    "Ceribell",
    "Zeto",
    "Beacon Biosignals",
    "Cognito Therapeutics",
    "NeuroMetrix",
    "Neurable",
]
TIER_B = [
    "Synchron",
    "Paradromics",
    "Neuralink",
    "Precision Neuroscience",
    "Neuronetics",
    "electroCore",
    "Merge Labs",
    "Inspire Medical Systems",
    "NeuroPace",
    "Cala Health",
]
ACADEMIC_HUBS = [
    "PhysioNet",
    "Temple University Hospital",
]

ALL_TARGETS = [("Tier A", c) for c in TIER_A] + [("Tier B", c) for c in TIER_B] + [
    ("Academic/public-data hub", c) for c in ACADEMIC_HUBS
]


@dataclass
class MatchedContact:
    tier: str
    target_company: str
    full_name: str
    linkedin_url: str
    matched_company_field: str
    position: str
    connected_on: str


def load_connections(csv_path: Path = DEFAULT_LINKEDIN_EXPORT) -> list[dict]:
    """Read the LinkedIn connections export. Tolerates the export's leading disclaimer
    lines by locating the real header row (starts with 'First Name') rather than assuming
    it's line 1 — the export format has changed shape before and may again.
    """
    if not csv_path.exists():
        raise FileNotFoundError(
            f"LinkedIn connections export not found at {csv_path}. "
            "This script reads job_os's export in place; if it's moved, update "
            "DEFAULT_LINKEDIN_EXPORT."
        )
    with open(csv_path, newline="", encoding="utf-8") as f:
        lines = f.readlines()
    header_idx = next(
        (i for i, line in enumerate(lines) if line.startswith("First Name")), None
    )
    if header_idx is None:
        raise ValueError(f"Could not find a 'First Name' header row in {csv_path}")
    reader = csv.DictReader(lines[header_idx:])
    return list(reader)


def match_connections(
    connections: list[dict], targets: list[tuple[str, str]] = ALL_TARGETS
) -> list[MatchedContact]:
    matches: list[MatchedContact] = []
    for row in connections:
        company = (row.get("Company") or "").strip()
        if not company:
            continue
        company_lower = company.lower()
        for tier, target in targets:
            if target.lower() in company_lower:
                matches.append(
                    MatchedContact(
                        tier=tier,
                        target_company=target,
                        full_name=f"{row.get('First Name', '').strip()} {row.get('Last Name', '').strip()}".strip(),
                        linkedin_url=(row.get("URL") or "").strip(),
                        matched_company_field=company,
                        position=(row.get("Position") or "").strip(),
                        connected_on=(row.get("Connected On") or "").strip(),
                    )
                )
    return matches


def write_report(matches: list[MatchedContact], out_dir: Path = OUTPUT_DIR) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_ts = datetime.now(timezone.utc).isoformat()

    json_path = out_dir / "neurotech_contact_matches.json"
    json_path.write_text(
        json.dumps(
            {"generated_at": run_ts, "matches": [asdict(m) for m in matches]}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )

    md_path = out_dir / "neurotech_contact_matches.md"
    lines = [
        "# Neurotech contact matches",
        "",
        f"Generated {run_ts}. Source: {DEFAULT_LINKEDIN_EXPORT} (read in place, not copied).",
        f"Matched {len(matches)} connection(s) across {len({m.target_company for m in matches})} "
        "target companies out of "
        f"{len(ALL_TARGETS)} tracked (see business/market_research_v1.md §2).",
        "",
    ]
    if not matches:
        lines.append(
            "No matches found. This is a substring match on LinkedIn's free-text `Company` "
            "field — a real connection may still exist under a different company-name spelling."
        )
    else:
        by_company: dict[str, list[MatchedContact]] = {}
        for m in matches:
            by_company.setdefault(m.target_company, []).append(m)
        for company, company_matches in by_company.items():
            tier = company_matches[0].tier
            lines.append(f"## {company} ({tier})")
            for m in company_matches:
                lines.append(f"- **{m.full_name}** — {m.position or '(no title listed)'}")
                lines.append(f"  - LinkedIn: {m.linkedin_url}")
                lines.append(f"  - Company field as exported: {m.matched_company_field}")
                lines.append(f"  - Connected on: {m.connected_on or '(unknown)'}")
            lines.append("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def main() -> None:
    connections = load_connections()
    print(f"[init] Loaded {len(connections)} connection rows from {DEFAULT_LINKEDIN_EXPORT}")
    matches = match_connections(connections)
    print(f"[match] {len(matches)} connection(s) matched against {len(ALL_TARGETS)} target companies")
    md_path, json_path = write_report(matches)
    print(f"[report] Wrote {md_path}")
    print(f"[report] Wrote {json_path}")


if __name__ == "__main__":
    main()
