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

See ARCHITECTURE.md, pipeline stage 13, and the rubric's "EEG rule specification (v0.2)" section
for the exact rules implemented here (step numbers in comments follow GeoBind's implementation
sequence).

PROVISIONAL (flagged, not settled)
----------------------------------
* The GeoBind -> EEG slot mapping (amplitude <- charge pair, timing = mean(phase scramble, jitter)
  <- geometry foil, noise <- steric bulk) is a modelling choice, not literature-derived.
* Every ``Thresholds`` value defaults to ``None`` and the engine refuses to classify until all are
  set. No calibrated values exist yet; GeoBind's numeric defaults are NOT copied.
* ``tau_spill`` / the spillover qualifier is new in the EEG port (replaces GeoBind's clash
  qualifier; GeoBind's local/electrostatic support layers have no EEG analog and are dropped).
* With the Phase 1 readout (log band power), phase scramble and jitter are power-preserving by
  construction, so ``D_timing`` is ~0 and ``timing_dominant`` cannot fire until a phase-sensitive
  readout (detector output, Phase 3) supplies the D values. The engine itself is readout-agnostic.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields

from src.core.perturbation_design import PerturbationClass

AMP = PerturbationClass.AMPLITUDE_ATTENUATION.value
PHASE = PerturbationClass.PHASE_SCRAMBLE.value
JITTER = PerturbationClass.TEMPORAL_JITTER.value
NOISE = PerturbationClass.STRUCTURED_NOISE_INJECTION.value
CANONICAL_CLASSES: tuple[str, ...] = (AMP, PHASE, JITTER, NOISE)

# Slot order doubles as the tie-break order for mixed_weak_*_led (rubric v0.2, rule 6).
SLOTS: tuple[str, ...] = ("amplitude", "timing", "noise")

REPRODUCIBILITY_STATUSES = ("PASS", "WARN", "FAIL", "UNKNOWN")
_CONFIDENCE_ORDER = ("high", "medium", "low", "not_interpretable")

SPILL_EXCEEDS = "spillover_exceeds_target"
SPILL_MINOR = "spillover_minor"
SPILL_NA = "not_applicable"

STRONG_CALLS = ("amplitude_dominant_anchor", "amplitude_dominant", "timing_dominant", "noise_dominant")

_TEMPLATES: dict[str, tuple[str, str]] = {
    "amplitude_dominant_anchor": (
        "In-band attenuation is the strongest disruptor and the unit stays sensitive to noise injection, "
        "consistent with a high-leverage power feature.",
        "Treat as a high-leverage power hotspot; prioritise amplitude-based probes first.",
    ),
    "amplitude_dominant": (
        "In-band attenuation is clearly more disruptive than the timing probes, consistent with dependence "
        "on band power/amplitude.",
        "Prioritise amplitude-based probes.",
    ),
    "timing_dominant": (
        "The power-preserving timing probes (phase scramble/jitter) are more disruptive than attenuation, "
        "consistent with dependence on phase/temporal structure.",
        "Prioritise phase/timing probes; do not assume power-preserving changes are tolerated.",
    ),
    "noise_dominant": (
        "Band-limited noise injection is the most disruptive probe, consistent with SNR/robustness sensitivity.",
        "Prioritise robustness/artifact probes.",
    ),
    "mixed_weak_amplitude_led": (
        "Mixed profile; attenuation modestly leads.",
        "Begin with amplitude probes; keep the others in the comparison set.",
    ),
    "mixed_weak_timing_led": (
        "Mixed profile; timing probes modestly lead.",
        "Begin with timing probes; keep amplitude as a close alternative.",
    ),
    "mixed_weak_noise_led": (
        "Mixed profile; noise injection modestly leads.",
        "Begin with noise probes; keep amplitude in the same decision set.",
    ),
    "broadly_sensitive": (
        "All probes are materially disruptive with limited separation, suggesting a generally fragile unit "
        "rather than one mechanism.",
        "Multiple probe strategies are plausible; prioritise tractability.",
    ),
    "inconclusive": (
        "The panel does not support a stable dominant mechanism call.",
        "Acquire more evidence before assigning mechanism-specific priority.",
    ),
    "incomplete_panel": (
        "The hotspot lacks the complete four-perturbation panel.",
        "Complete the panel first.",
    ),
    "unstable_not_interpretable": (
        "Not interpretable because reproducibility checks failed.",
        "Resolve reproducibility instability first.",
    ),
}


@dataclass(frozen=True)
class Thresholds:
    """All tau_* values are PLACEHOLDERS (None) — see mechanism_aware_interpretation_rubric.md's
    'EEG rule specification (v0.2)'. Do not hand-pick these; calibrate against real disruption-score
    distributions (Phase 3) or simulated ground truth (Phase 4). Exposed as a dataclass, never
    hardcoded inline, per CLAUDE.md's config-as-object convention.
    """

    tau_dom: float | None = None
    tau_broad: float | None = None
    tau_weak: float | None = None
    tau_material: float | None = None
    tau_high: float | None = None
    tau_med: float | None = None
    tau_spill: float | None = None
    epsilon: float | None = None

    def require_calibrated(self) -> None:
        missing = [f.name for f in fields(self) if getattr(self, f.name) is None]
        if missing:
            raise ValueError(
                f"Thresholds not set: {missing}. Refusing to classify: no calibrated tau_* values exist "
                "yet (rubric v0.2 is PROVISIONAL). Pass explicit values; never invent defaults."
            )

    def as_dict(self) -> dict[str, float | None]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass
class MechanismCall:
    """One hotspot's interpretation. ``to_row()`` gives the rubric's canonical output row."""

    hotspot: tuple[str, str]
    D: dict[str, float]
    magnitude: dict[str, float]
    contrasts: dict[str, float]
    contrasts_norm: dict[str, float]
    spillover: dict[str, float]
    leading_class: str
    spillover_ratio: float
    spillover_qualifier: str
    dominant_mechanism: str
    confidence: str
    interpretation: str
    action: str
    rationale: str
    reproducibility_status: str

    def to_row(self) -> dict:
        nan = float("nan")
        row = {"hotspot_channel": self.hotspot[0], "hotspot_band": self.hotspot[1]}
        row.update({k: self.D.get(k, nan) for k in CANONICAL_CLASSES})
        for k in ("timing_mean", "disruption_max", "disruption_min", "disruption_mean", "disruption_range", "broad_ratio"):
            row[k] = self.magnitude.get(k, nan)
        for s in SLOTS:
            row[f"{s}_specificity"] = self.contrasts.get(s, nan)
        for s in SLOTS:
            row[f"{s}_specificity_norm"] = self.contrasts_norm.get(s, nan)
        for k in CANONICAL_CLASSES:
            row[f"spillover_{k}"] = self.spillover.get(k, nan)
        row.update({
            "leading_class": self.leading_class,
            "spillover_ratio": self.spillover_ratio,
            "spillover_qualifier": self.spillover_qualifier,
            "dominant_mechanism": self.dominant_mechanism,
            "confidence": self.confidence,
            "interpretation": self.interpretation,
            "action": self.action,
            "rationale": self.rationale,
            "reproducibility_status": self.reproducibility_status,
            "thresholds_provisional": True,
        })
        return row


def _downgrade(confidence: str) -> str:
    """One level down, floored at 'low' (GeoBind semantics)."""
    idx = _CONFIDENCE_ORDER.index(confidence)
    return _CONFIDENCE_ORDER[min(idx + 1, 2)]


def _fmt(x: float) -> str:
    return f"{x:.3f}" if math.isfinite(x) else "nan"


def _not_interpretable(hotspot, D, spill, call, reason, status) -> MechanismCall:
    interp, action = _TEMPLATES[call]
    return MechanismCall(
        hotspot=hotspot, D=dict(D), magnitude={}, contrasts={}, contrasts_norm={}, spillover=dict(spill),
        leading_class="none", spillover_ratio=float("nan"), spillover_qualifier=SPILL_NA,
        dominant_mechanism=call, confidence="not_interpretable", interpretation=interp, action=action,
        rationale=f"{reason} Reproducibility status: {status}.", reproducibility_status=status,
    )


def classify_hotspot_mechanism(
    panel: Mapping[str, float],
    thresholds: Thresholds,
    *,
    spillover_adjacent: Mapping[str, float] | None = None,
    reproducibility_status: str = "UNKNOWN",
    hotspot: tuple[str, str] = ("?", "?"),
) -> MechanismCall:
    """Classify one hotspot from its four-class panel of normalized disruption scores.

    ``panel`` maps perturbation-class value -> ``D_k`` (compare.py's
    ``target_disruption_score_normalized``). ``spillover_adjacent`` maps class -> that run's
    ``offtarget_adjacent_band_max_disruption_normalized`` (optional; absent -> qualifier
    ``not_applicable``). Raises ValueError if any threshold is None or the status is unknown.
    """
    thresholds.require_calibrated()
    t = thresholds
    eps = t.epsilon
    status = str(reproducibility_status).upper()
    if status not in REPRODUCIBILITY_STATUSES:
        raise ValueError(f"reproducibility_status {reproducibility_status!r} not in {REPRODUCIBILITY_STATUSES}")
    spill = {k: float(v) for k, v in (spillover_adjacent or {}).items()}

    # Steps 1-3: canonical classes, completeness (non-finite D counts as missing)
    unknown = sorted(set(panel) - set(CANONICAL_CLASSES))
    if unknown:
        raise ValueError(f"unknown perturbation class(es) {unknown}; panel must use {CANONICAL_CLASSES}")
    D = {k: float(v) for k, v in panel.items()}
    missing = [k for k in CANONICAL_CLASSES if k not in D or not math.isfinite(D[k])]
    if missing:
        return _not_interpretable(hotspot, D, spill, "incomplete_panel",
                                  f"Missing or non-finite D for {missing}.", status)

    # Step 4: magnitude layer
    d_amp, d_phase, d_jit, d_noise = (D[k] for k in CANONICAL_CLASSES)
    d_timing = (d_phase + d_jit) / 2.0
    vals = [d_amp, d_phase, d_jit, d_noise]
    d_max, d_min = max(vals), min(vals)
    d_mean = sum(vals) / 4.0
    r_d = d_max - d_min
    b = r_d / max(d_mean, eps)

    # Steps 5-6: raw and normalized contrasts
    s = {
        "amplitude": d_amp - d_timing,
        "timing": d_timing - d_amp,
        "noise": d_noise - max(d_amp, d_phase, d_jit),
    }
    s_norm = {k: v / max(r_d, eps) for k, v in s.items()}
    s_max_slot = max(SLOTS, key=lambda k: (s_norm[k], -SLOTS.index(k)))  # tie -> earlier slot
    s_max = s_norm[s_max_slot]

    # Steps 9-12: decision cascade (strict order)
    if b <= t.tau_broad and d_min >= t.tau_material:
        call = "broadly_sensitive"
        why = f"B={_fmt(b)} <= tau_broad={t.tau_broad} and D_min={_fmt(d_min)} >= tau_material={t.tau_material}"
    elif s_norm["amplitude"] >= t.tau_dom and d_amp > d_timing and d_noise >= t.tau_material:
        call = "amplitude_dominant_anchor"
        why = (f"S_amp_norm={_fmt(s_norm['amplitude'])} >= tau_dom={t.tau_dom}, D_amp={_fmt(d_amp)} > "
               f"D_timing={_fmt(d_timing)}, D_noise={_fmt(d_noise)} >= tau_material={t.tau_material}")
    elif s_norm["amplitude"] >= t.tau_dom:
        call = "amplitude_dominant"
        why = f"S_amp_norm={_fmt(s_norm['amplitude'])} >= tau_dom={t.tau_dom}"
    elif s_norm["timing"] >= t.tau_dom and d_timing >= d_amp:
        call = "timing_dominant"
        why = (f"S_timing_norm={_fmt(s_norm['timing'])} >= tau_dom={t.tau_dom} and "
               f"D_timing={_fmt(d_timing)} >= D_amp={_fmt(d_amp)}")
    elif s_norm["noise"] >= t.tau_dom:
        call = "noise_dominant"
        why = f"S_noise_norm={_fmt(s_norm['noise'])} >= tau_dom={t.tau_dom}"
    elif t.tau_weak <= s_max < t.tau_dom:
        call = f"mixed_weak_{s_max_slot}_led"
        why = f"S_max={_fmt(s_max)} ({s_max_slot}) in [tau_weak={t.tau_weak}, tau_dom={t.tau_dom})"
    else:
        call = "inconclusive"
        why = f"no strong rule passed and S_max={_fmt(s_max)} < tau_weak={t.tau_weak}"

    # Step 13: spillover qualifier (analog of GeoBind's clash qualifier; never changes the call)
    if call in ("broadly_sensitive", "inconclusive"):
        lead_slot = None
    elif call in STRONG_CALLS:
        lead_slot = call.split("_")[0]
    else:
        lead_slot = s_max_slot
    lead = {"amplitude": AMP, "noise": NOISE, "timing": PHASE if d_phase >= d_jit else JITTER}.get(lead_slot, "none")
    spill_ratio = float("nan")
    qualifier = SPILL_NA
    if lead != "none" and lead in spill and math.isfinite(spill[lead]):
        spill_ratio = spill[lead] / max(D[lead], eps)
        qualifier = SPILL_EXCEEDS if spill_ratio >= t.tau_spill else SPILL_MINOR

    # Step 14: confidence from contrast separation
    pos = sorted((max(v, 0.0) for v in s_norm.values()), reverse=True)
    gap = pos[0] - pos[1]
    if call == "inconclusive":
        confidence = "low"
    elif gap >= t.tau_high and call in STRONG_CALLS:
        confidence = "high"
    elif gap >= t.tau_med:
        confidence = "medium"
    else:
        confidence = "low"
    downgrades = []
    if qualifier == SPILL_EXCEEDS:
        confidence = _downgrade(confidence)
        downgrades.append(f"spillover_ratio={_fmt(spill_ratio)} >= tau_spill={t.tau_spill}")

    # Step 15: reproducibility gate
    if status == "WARN":
        confidence = _downgrade(confidence)
        downgrades.append("reproducibility WARN")
    elif status == "FAIL":
        call = "unstable_not_interpretable"
        confidence = "not_interpretable"
        why = "reproducibility_status=FAIL overrides the mechanism call"

    # Steps 16-18: templates and rationale
    interp, action = _TEMPLATES[call]
    rationale = (
        f"D values: amplitude={_fmt(d_amp)}, phase={_fmt(d_phase)}, jitter={_fmt(d_jit)}, noise={_fmt(d_noise)} "
        f"(D_timing={_fmt(d_timing)}, R_D={_fmt(r_d)}). "
        f"Raw contrasts: amplitude={_fmt(s['amplitude'])}, timing={_fmt(s['timing'])}, noise={_fmt(s['noise'])}. "
        f"Normalized contrasts: amplitude={_fmt(s_norm['amplitude'])}, timing={_fmt(s_norm['timing'])}, "
        f"noise={_fmt(s_norm['noise'])}; separation G={_fmt(gap)}. "
        f"Mechanism call assigned because {why}. "
        f"Spillover qualifier: {qualifier} (lead={lead}, ratio={_fmt(spill_ratio)}). "
        f"Confidence: {confidence}" + (f" after downgrade for {', '.join(downgrades)}" if downgrades else "") + ". "
        f"Reproducibility status: {status}"
        + (" (unknown; no automatic downgrade)" if status == "UNKNOWN" else "") + ". "
        "Thresholds are PROVISIONAL."
    )

    return MechanismCall(
        hotspot=hotspot, D=D,
        magnitude={"timing_mean": d_timing, "disruption_max": d_max, "disruption_min": d_min,
                   "disruption_mean": d_mean, "disruption_range": r_d, "broad_ratio": b},
        contrasts=s, contrasts_norm=s_norm, spillover=spill,
        leading_class=lead, spillover_ratio=spill_ratio, spillover_qualifier=qualifier,
        dominant_mechanism=call, confidence=confidence, interpretation=interp, action=action,
        rationale=rationale, reproducibility_status=status,
    )


def interpret_mechanism_profiles(
    summaries: Sequence[Mapping],
    thresholds: Thresholds,
    reproducibility_status: str = "UNKNOWN",
) -> list[MechanismCall]:
    """Group ``ComparisonResult.summary()`` rows by (target_channel, target_band) and classify each.

    Duplicate classes for one hotspot raise (no aggregation rule is documented). Output is sorted
    by (channel, band) name so it is deterministic regardless of input order.
    """
    thresholds.require_calibrated()
    panels: dict[tuple[str, str], dict[str, float]] = {}
    spills: dict[tuple[str, str], dict[str, float]] = {}
    for row in summaries:
        key = (str(row["target_channel"]), str(row["target_band"]))
        pclass = str(row["perturbation_class"])
        if pclass in panels.setdefault(key, {}):
            raise ValueError(f"duplicate perturbation class {pclass!r} for hotspot {key}; no aggregation rule")
        panels[key][pclass] = float(row["target_disruption_score_normalized"])
        sp = row.get("offtarget_adjacent_band_max_disruption_normalized")
        if sp is not None:
            spills.setdefault(key, {})[pclass] = float(sp)
    return [
        classify_hotspot_mechanism(panels[k], thresholds, spillover_adjacent=spills.get(k),
                                   reproducibility_status=reproducibility_status, hotspot=k)
        for k in sorted(panels)
    ]
