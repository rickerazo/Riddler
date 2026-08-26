"""Layer 1 (platform core) — mechanism-aware EEG perturbation panel.

Analog of GeoBind's src/perturbation_schema.py: for each hotspot, define a FIXED panel of
controlled perturbations, each triple-tagged (perturbation_mode, perturbation_class,
mechanistic_hypothesis), so cross-hotspot comparison is apples-to-apples.

STATUS: provisional. See mechanism_aware_interpretation_rubric.md for the full candidate panel,
its literature-grounding status, and why `channel_dropout` is explicitly not implemented yet.
Do not add perturbation classes here that aren't documented in that rubric first — the rubric is
the source of truth, this module implements it.

See ARCHITECTURE.md, pipeline stage 5.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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


def build_perturbation_design_table(*args, **kwargs):
    """Expand ranked hotspots into the fixed, hypothesis-tagged perturbation panel.

    Analog of GeoBind's build_mechanism_aware_single_design_table. TODO: implement once
    hotspot ranking (src/core/hotspot_detection.py) is implemented.
    """
    raise NotImplementedError(
        "build_perturbation_design_table: not yet implemented. Depends on rank_hotspots() "
        "landing first."
    )
