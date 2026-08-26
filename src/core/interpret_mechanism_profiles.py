"""Layer 1 (platform core) — the centralized, contrast-based interpretation engine.

Analog of GeoBind's src/interpret_mechanism_profiles.py, implementing
mechanism_aware_interpretation_rubric.md 1:1 — THAT rubric file is the source of truth, this
module must match it, not the other way around (per GeoBind's own convention: when code and
docs disagree, the doc gets corrected in place with a note, and code follows).

Non-negotiable properties (see CLAUDE.md, mechanism_aware_interpretation_rubric.md):
1. Classify off within-hotspot CONTRAST, not raw magnitude.
2. Refuse to classify an incomplete panel rather than guessing.
3. Confidence is reproducibility-gated: a FAIL audit status overrides any call to
   'unstable_not_interpretable'; a WARN status caps confidence.
4. Every classified hotspot emits an auditable rationale string with the real numbers.

Interpretation logic must NEVER live in src/modules/<modality>/ — it is centralized platform
IP, exactly as in GeoBind.

See ARCHITECTURE.md, pipeline stage 13.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Thresholds:
    """All tau_* values are PLACEHOLDERS (TBD) — see mechanism_aware_interpretation_rubric.md's
    'Decision order' section. Do not hand-pick these; calibrate against real CHB-MIT feature
    distributions once the smoke test produces them. Exposed as a dataclass, never hardcoded
    inline, per CLAUDE.md's config-as-object convention.
    """

    tau_dom: float | None = None
    tau_broad: float | None = None
    tau_weak: float | None = None
    tau_material: float | None = None
    tau_high: float | None = None
    tau_med: float | None = None
    epsilon: float | None = None


def classify_hotspot_mechanism(*args, **kwargs):
    """Classify one hotspot's dominant failure mode from its normalized contrast layer.

    TODO: implement once (a) the perturbation panel is grounded (not provisional) and
    (b) Thresholds has real, calibrated values instead of None placeholders. Raising here
    rather than returning a fabricated classification is intentional — see CLAUDE.md's
    'never silently guess undocumented thresholds'.
    """
    raise NotImplementedError(
        "classify_hotspot_mechanism: not yet implemented — Thresholds are still "
        "uncalibrated placeholders and the perturbation panel is still provisional."
    )
