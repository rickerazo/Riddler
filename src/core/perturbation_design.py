"""Layer 1 (platform core) — mechanism-aware EEG perturbation panel.

Analog of GeoBind's src/perturbation_schema.py: for each hotspot, define a FIXED panel of
controlled perturbations, each triple-tagged (perturbation_mode, perturbation_class,
mechanistic_hypothesis), so cross-hotspot comparison is apples-to-apples.

STATUS: provisional. See mechanism_aware_interpretation_rubric.md for the full candidate panel,
its literature-grounding status, and why `channel_dropout` is explicitly not implemented yet.
Do not add perturbation classes here that aren't documented in that rubric first — the rubric is
the source of truth, this module implements it.

See ARCHITECTURE.md, pipeline stage 5.

``build_perturbation_design_table`` (implemented 2026-11-19) expands the top ``n_hotspots`` selected
hotspots from stage 4 into one execution-ready row per (hotspot, panel member). How many hotspots
feed the panel is deliberately NOT defaulted here; see that function's docstring.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

import numpy as np


class PerturbationMode(str, Enum):
    WEAK = "weak"
    STRONG = "strong"
    MECHANISM_AWARE = "mechanism_aware"


class PerturbationClass(str, Enum):
    """Provisional panel — see mechanism_aware_interpretation_rubric.md before adding/removing
    a member. `CHANNEL_DROPOUT` is intentionally absent: it's an open item pending Track A
    literature grounding, not yet safe to implement.
    """

    AMPLITUDE_ATTENUATION = "amplitude_attenuation"
    PHASE_SCRAMBLE = "phase_scramble"
    TEMPORAL_JITTER = "temporal_jitter"
    STRUCTURED_NOISE_INJECTION = "structured_noise_injection"


@dataclass
class PerturbationSpec:
    perturbation_mode: PerturbationMode
    perturbation_class: PerturbationClass
    mechanistic_hypothesis: str


# Fixed panel applied to every hotspot — see mechanism_aware_interpretation_rubric.md for the
# rationale behind each row and its literature-grounding status.
CANDIDATE_PANEL: list[PerturbationSpec] = [
    PerturbationSpec(
        PerturbationMode.MECHANISM_AWARE,
        PerturbationClass.AMPLITUDE_ATTENUATION,
        "amplitude/power dependence",
    ),
    PerturbationSpec(
        PerturbationMode.MECHANISM_AWARE,
        PerturbationClass.PHASE_SCRAMBLE,
        "phase/temporal-structure dependence, power preserved",
    ),
    PerturbationSpec(
        PerturbationMode.MECHANISM_AWARE,
        PerturbationClass.TEMPORAL_JITTER,
        "temporal-precision dependence, power+phase preserved",
    ),
    PerturbationSpec(
        PerturbationMode.MECHANISM_AWARE,
        PerturbationClass.STRUCTURED_NOISE_INJECTION,
        "robustness/SNR dependence, fixed-SNR band-limited noise",
    ),
]


# Schema version of the design-table rows. New fields are additive (CLAUDE.md: preserve schemas).
DESIGN_TABLE_SCHEMA_VERSION = 1


def perturbation_tag(channel: str, band: str, pclass: PerturbationClass | str) -> str:
    """Stable, human-readable id for one design row, e.g. ``C2__delta__amplitude_attenuation``."""
    pc = pclass.value if isinstance(pclass, PerturbationClass) else str(pclass)
    return f"{channel}__{band}__{pc}"


def build_perturbation_design_table(
    ranking,
    bands,
    *,
    n_hotspots: int,
    seed: int,
    panel: Sequence[PerturbationSpec] | None = None,
) -> list[dict]:
    """Expand the top ``n_hotspots`` *selected* hotspots into the fixed, hypothesis-tagged panel.

    Analog of GeoBind's ``build_mechanism_aware_single_design_table``: one execution-ready row per
    (hotspot, panel member), carrying everything ``apply_perturbation`` needs (channel index, band
    edges in Hz, spec tags, seed) plus the ranking provenance (rank, score, signed effect size).

    Inputs: ``ranking`` is a :class:`~src.core.hotspot_detection.HotspotRanking` (stage 4) and
    ``bands`` the :class:`~src.core.metrics_shared.BandConfig` the ranking was computed with
    (checked: every ranked band must be in it). Only ``ranking.selected`` units are eligible, in
    rank order; suppressed and degenerate units never enter the panel.

    Flagged choices (NOT settled; no source documents them):

    * ``n_hotspots`` (**how many selected hotspots feed the panel**) has no default on purpose.
      hotspot_detection applies no cutoff, and neither the rubric nor ARCHITECTURE.md gives a
      top-k, so the caller must state it. Asking for more than ``len(ranking.selected)`` raises
      rather than silently shrinking the table.
    * ``seed`` is required, and the SAME base seed is used for every row (as in the stage-7/9 smoke
      checks). Rows are therefore not independent draws across hotspots; a per-row seed
      derivation is undocumented and left open.
    * ``panel`` defaults to :data:`CANDIDATE_PANEL` (rubric v0.2, provisional). The panel is fixed
      across hotspots so cross-hotspot comparison stays apples-to-apples; duplicate classes in a
      custom panel are refused (interpretation has no aggregation rule for them).

    Rows are sorted by (hotspot_rank, panel order), so the table is deterministic.
    """
    if isinstance(n_hotspots, bool) or not isinstance(n_hotspots, (int, np.integer)) or n_hotspots < 1:
        raise ValueError(f"n_hotspots must be an int >= 1, got {n_hotspots!r}")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise ValueError(f"seed must be an int, got {seed!r}")
    panel = list(CANDIDATE_PANEL if panel is None else panel)
    if not panel:
        raise ValueError("panel is empty")
    classes = [spec.perturbation_class for spec in panel]
    if len(set(classes)) != len(classes):
        raise ValueError(f"panel repeats a perturbation class: {[c.value for c in classes]}")
    selected = list(ranking.selected)
    if n_hotspots > len(selected):
        raise ValueError(
            f"n_hotspots={n_hotspots} but the ranking has only {len(selected)} selected units; "
            "refusing to shrink the table silently")

    rows: list[dict] = []
    for unit in selected[:n_hotspots]:
        if unit.band not in bands.bands:
            raise ValueError(f"band {unit.band!r} of ranked unit not in BandConfig {bands.names}")
        lo, hi = bands.bands[unit.band]
        for spec in panel:
            rows.append({
                "design_table_schema_version": DESIGN_TABLE_SCHEMA_VERSION,
                "perturbation_tag": perturbation_tag(unit.channel, unit.band, spec.perturbation_class),
                "hotspot_rank": int(unit.rank),
                "target_channel": unit.channel,
                "target_channel_index": int(unit.channel_index),
                "target_band": unit.band,
                "band_lo_hz": float(lo),
                "band_hi_hz": float(hi),
                "rank_score": float(unit.rank_score),
                "effect_size_signed": float(unit.effect_size_signed),
                "perturbation_mode": spec.perturbation_mode.value,
                "perturbation_class": spec.perturbation_class.value,
                "mechanistic_hypothesis": spec.mechanistic_hypothesis,
                "seed": int(seed),
                "n_hotspots_requested": int(n_hotspots),
                "n_hotspots_provisional": True,
                "panel_provisional": True,
            })
    return rows


def spec_from_design_row(row: dict) -> PerturbationSpec:
    """Rebuild the triple-tagged :class:`PerturbationSpec` of one design row (for execution)."""
    return PerturbationSpec(
        PerturbationMode(row["perturbation_mode"]),
        PerturbationClass(row["perturbation_class"]),
        str(row["mechanistic_hypothesis"]),
    )
