# Mechanism-aware interpretation rubric — EEG (v0.1, PROVISIONAL)

**Status: provisional.** This rubric ports GeoBind's mechanism-aware interpretation pattern
(`GeoBind/mechanism_aware_interpretation_rubric.md`) into EEG signal classification. The *structure* below
(canonical classes, magnitude layer, normalized contrast layer, ordered decision rules, reproducibility-gated
confidence, mandatory rationale) is a direct, deliberate port and is not provisional. The *specific
perturbation classes, thresholds, and physical justifications* are provisional placeholders pending the Track A
literature review (`business/lit_review_science_v1.md`) — do not treat `tau_*` values or class definitions
below as final, and do not let a downstream script silently assume they are validated. Flag this status
explicitly wherever this rubric is cited.

## Core principle (unchanged from GeoBind)

A perturbation with the largest raw disruption score does not necessarily define the mechanism. Mechanism is
read off the **contrast structure** across a fixed panel of perturbations applied at one hotspot (a
channel×band unit), not off raw magnitude alone.

## Candidate perturbation panel (provisional — needs Track A grounding)

For each detected hotspot, apply the same fixed panel of controlled perturbations, each triple-tagged exactly
as in GeoBind: `perturbation_mode` (weak / strong / mechanism_aware), `perturbation_class` (which physical
lever), `mechanistic_hypothesis` (what it tests for).

| `perturbation_class` | `mechanistic_hypothesis` | Literature grounding needed |
|---|---|---|
| `amplitude_attenuation` | amplitude/power dependence | — (most straightforward; scale the signal in-band) |
| `phase_scramble` | phase/temporal-structure dependence, power preserved | Surrogate-data methods — Theiler-style surrogates, AAFT/phase-randomization (Track A item 2) |
| `temporal_jitter` | temporal-precision dependence, power+phase preserved, onset timing perturbed | Needs a defensible jitter-window justification from the seizure-detection literature |
| `structured_noise_injection` | robustness/SNR dependence, fixed-SNR band-limited noise (EMG/eye-blink-like) | EEG artifact/noise literature — ICA-based rejection, EMG/eye-blink contamination models (Track A item 3) |
| `channel_dropout` / spatial occlusion | spatial-network dependence | **Open** — no direct GeoBind analog; resolve via Track A before finalizing, do not implement until grounded |

Do not implement `channel_dropout` until Track A resolves it. The other four may be implemented as a first
pass once the smoke test is being built, explicitly labeled provisional in any output they produce.

## Magnitude layer and normalized contrast layer

Ported unchanged in structure from GeoBind: compute max/min/mean/range of the panel's raw disruption scores at
one hotspot (magnitude layer), then compute normalized contrasts between class pairs, e.g.
`S_amplitude_norm = (amplitude_mean - timing_score) / disruption_range`, so thresholds are dimensionless and
portable across hotspots with different baseline engagement. **Baseline-normalize before comparing across
hotspots** — this is the `binding_disruption_score_normalized_local` lesson from GeoBind: raw magnitudes are
not comparable across channel×band units without it.

## Decision order (structure ported; thresholds are placeholders)

Same ordered-rule-cascade structure as GeoBind: broadly-sensitive → dominant-anchor → dominant → mixed-weak-led
→ inconclusive, checked in strict priority order, using a `Thresholds` dataclass (`tau_dom`, `tau_broad`,
`tau_weak`, `tau_material`, `tau_high`, `tau_med`, `epsilon`) exposed as config, never hardcoded. **All `tau_*`
values are placeholders (`TBD`) until grounded against real CHB-MIT feature distributions** — do not invent
numbers here; leave them as an explicit open parameter in code until Track A + the smoke test produce real
distributions to calibrate against.

Require a complete panel per hotspot; refuse to classify (`incomplete_panel` / `not_interpretable`) rather than
guessing, exactly as GeoBind does.

## Confidence logic (ported unchanged)

Confidence is driven by contrast separation (gap between the top two normalized contrasts), not raw magnitude,
and is downgraded/overridden by the reproducibility audit's PASS/WARN/FAIL status: `FAIL` → the call is
`unstable_not_interpretable` regardless of contrast separation; `WARN` → confidence is capped, never reported
as high; `PASS` → confidence follows contrast separation normally.

## Mandatory auditable rationale (ported unchanged)

Every classified hotspot must emit a human-readable rationale string showing the actual numbers that drove the
call. Do not hide the contrast values.

## Next steps to move this out of "provisional"

1. Complete Track A literature review items 2-3 (surrogate-data methods, EEG artifact/noise literature) to
   ground `phase_scramble` and `structured_noise_injection`.
2. Resolve the `channel_dropout` open item or drop it from the panel.
3. Run the smoke test on synthetic data, then on CHB-MIT, to get real disruption-score distributions to
   calibrate `tau_*` against — do not hand-pick thresholds without real distributions to check them against.
4. Update this file's status line to "grounded" once 1-3 are done, and record what changed in `CHANGELOG.md`.
