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
`tau_weak`, `tau_material`, `tau_high`, `tau_med`, `tau_spill`, `epsilon`) exposed as config, never hardcoded.
Exact conditions: see "EEG rule specification (v0.2)" below. **All `tau_*`
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

## EEG rule specification (v0.2, 2026-11-18, ported from GeoBind; PROVISIONAL)

This section spells out the exact rule conditions that the sections above only name. They are ported 1:1 from
GeoBind's `docs/design/mechanism_aware_interpretation_rubric.md` and `src/interpret_mechanism_profiles.py`
(`~/Projects/GeoBind`). `src/core/interpret_mechanism_profiles.py` implements this section. If code and doc
disagree, fix the doc in place with a note, and the code follows the doc.

### Slot mapping (PROVISIONAL)

GeoBind has three contrast slots: a charge *pair*, a geometry *foil*, and a steric *bulk* class. The EEG port
fills them as follows. It follows this file's own example contrast, `(amplitude_mean - timing_score) / disruption_range`.

| GeoBind slot | EEG slot | Panel classes | Slot value |
|---|---|---|---|
| charge (pair mean) | **amplitude** | `amplitude_attenuation` | `D_amp` (one class, so its "mean" is `D_amp` itself) |
| geometry (foil) | **timing** | `phase_scramble`, `temporal_jitter` | `D_timing = (D_phase + D_jitter) / 2` |
| steric (bulk) | **noise** | `structured_noise_injection` | `D_noise` |

The mapping is a modelling choice, not literature-derived. It treats phase scramble and jitter as two probes of
one "timing" hypothesis, in the same way GeoBind treats remove/invert charge as two probes of one "charge"
hypothesis. Revisit it with Track A.

### Input

There is one row per (hotspot, perturbation class). `D_k` is the hotspot's
`target_disruption_score_normalized` from `src/core/compare.py`. It is already baseline-normalized, so do not
delta or re-normalize it. The panel must contain exactly the four classes above.
- A missing class gives `incomplete_panel` / `not_interpretable`.
- A duplicate class is an error: fail loudly, because there is no aggregation rule.
- A non-finite `D_k` (e.g. a degenerate-spread unit) is treated like a missing class.

The engine is **readout-agnostic**: `D_k` can come from feature deltas (Phase 1) or from detector-output change
(Phase 3). **Known limitation:** under the Phase 1 readout (log band power), phase scramble and jitter preserve
power by construction. `D_timing ≈ 0` there, so `timing_dominant` cannot fire until a phase-sensitive readout
exists.

### Magnitude layer
```text
D_max = max(D_amp, D_phase, D_jitter, D_noise)    D_min = min(...)    D_mean = mean(...)
R_D   = D_max - D_min
B     = R_D / max(D_mean, epsilon)
```

### Contrast layer
```text
S_amp    = D_amp    - D_timing
S_timing = D_timing - D_amp
S_noise  = D_noise  - max(D_amp, D_phase, D_jitter)
S_x_norm = S_x / max(R_D, epsilon)
```
Thresholds and confidence use the normalized contrasts. The rationale text reports the raw contrasts too.

### Decision order (strict priority)
1. `broadly_sensitive`: `B <= tau_broad` and `D_min >= tau_material`.
2. `amplitude_dominant_anchor`: `S_amp_norm >= tau_dom` and `D_amp > D_timing` and `D_noise >= tau_material`.
3. `amplitude_dominant`: `S_amp_norm >= tau_dom`.
4. `timing_dominant`: `S_timing_norm >= tau_dom` and `D_timing >= D_amp`.
5. `noise_dominant`: `S_noise_norm >= tau_dom`.
6. `mixed_weak_{amplitude|timing|noise}_led`: `tau_weak <= S_max < tau_dom`, where `S_max` is the largest
   normalized contrast. On a tie, the earlier slot in the order amplitude, timing, noise wins.
7. `inconclusive`: none of the above.

Rules 2–5 are "strong" rules.

### Spillover qualifier (EEG analog of GeoBind's clash qualifier)

This resolves the open HANDOFF 2026-11-17 question of how adjacent-band spillover enters a call. The qualifier
never changes the mechanism call. It only qualifies it and can downgrade confidence.

The **leading class** is:
- the strong rule's class when a strong rule fired;
- otherwise the slot with the largest normalized contrast;
- `none` for `broadly_sensitive` and `inconclusive`.

For timing, the leading class is whichever of phase/jitter has the larger `D`.

```text
spillover_ratio = offtarget_adjacent_band_max_disruption_normalized[lead] / max(D_lead, epsilon)
```
- If `spillover_ratio >= tau_spill`, set `spillover_exceeds_target`.
- Otherwise set `spillover_minor`.
- If there's no leading class, or no adjacent band, set `not_applicable`. This also applies when the spillover
  column isn't supplied.

`tau_spill` is new in the EEG port and has no GeoBind counterpart.

### Confidence
- Take the positive normalized contrasts, `max(S_x_norm, 0)`, sort them in descending order and set
  `G = S1 - S2`.
- The base level is:
  - `high` if `G >= tau_high` and a strong rule fired;
  - `medium` if `G >= tau_med`;
  - `low` otherwise. `inconclusive` is always `low`.
- Downgrade one level, with a floor at `low`, for each of:
  - `spillover_exceeds_target`;
  - `reproducibility_status == WARN`.

  These two replace GeoBind's support-based downgrades.
- `FAIL` overrides the call to `unstable_not_interpretable` / `not_interpretable`.
- `UNKNOWN` gives no downgrade, but the rationale says so.

### Thresholds

The `Thresholds` dataclass holds `tau_dom`, `tau_broad`, `tau_weak`, `tau_material`, `tau_high`, `tau_med`,
`tau_spill` and `epsilon`. **All of them default to `None`, and the engine refuses to classify while any is
`None`.** GeoBind's numeric defaults are deliberately not copied: `tau_material = 50` is in GeoBind
binding-score units and means nothing for a baseline-normalized EEG score. The smoke test uses explicitly
labelled `SMOKE_TEST_ONLY` values that are never used on real data.

### Dropped from GeoBind (no EEG analog)

These were removed:
- the local structural support layer (`L_k` from phosphate/DNA contacts);
- the electrostatic support layer (`Q_electro_k`);
- their thresholds, `tau_local` and `tau_electro`;
- `tau_clash`, which is replaced by `tau_spill`.

### Templates

| Call | Interpretation | Action |
|---|---|---|
| `amplitude_dominant_anchor` | In-band attenuation is the strongest disruptor and the unit stays sensitive to noise injection, consistent with a high-leverage power feature. | Treat as a high-leverage power hotspot; prioritise amplitude-based probes first. |
| `amplitude_dominant` | In-band attenuation is clearly more disruptive than the timing probes, consistent with dependence on band power/amplitude. | Prioritise amplitude-based probes. |
| `timing_dominant` | The power-preserving timing probes (phase scramble/jitter) are more disruptive than attenuation, consistent with dependence on phase/temporal structure. | Prioritise phase/timing probes; do not assume power-preserving changes are tolerated. |
| `noise_dominant` | Band-limited noise injection is the most disruptive probe, consistent with SNR/robustness sensitivity. | Prioritise robustness/artifact probes. |
| `mixed_weak_amplitude_led` | Mixed profile; attenuation modestly leads. | Begin with amplitude probes; keep the others in the comparison set. |
| `mixed_weak_timing_led` | Mixed profile; timing probes modestly lead. | Begin with timing probes; keep amplitude as a close alternative. |
| `mixed_weak_noise_led` | Mixed profile; noise injection modestly leads. | Begin with noise probes; keep amplitude in the same decision set. |
| `broadly_sensitive` | All probes are materially disruptive with limited separation, suggesting a generally fragile unit rather than one mechanism. | Multiple probe strategies are plausible; prioritise tractability. |
| `inconclusive` | The panel does not support a stable dominant mechanism call. | Acquire more evidence before assigning mechanism-specific priority. |
| `incomplete_panel` | The hotspot lacks the complete four-perturbation panel. | Complete the panel first. |
| `unstable_not_interpretable` | Not interpretable because reproducibility checks failed. | Resolve reproducibility instability first. |

### Output fields (one row per hotspot)

Each row has these fields:
- hotspot: `hotspot_channel`, `hotspot_band`;
- the four D values: `amplitude_attenuation`, `phase_scramble`, `temporal_jitter`, `structured_noise_injection`;
- magnitude: `timing_mean`, `disruption_max`, `disruption_min`, `disruption_mean`, `disruption_range`,
  `broad_ratio`;
- raw contrasts: `amplitude_specificity`, `timing_specificity`, `noise_specificity`;
- normalized contrasts: `amplitude_specificity_norm`, `timing_specificity_norm`, `noise_specificity_norm`;
- spillover: `spillover_<class>` ×4, `leading_class`, `spillover_ratio`, `spillover_qualifier`;
- the call: `dominant_mechanism`, `confidence`, `interpretation`, `action`, `rationale`, `reproducibility_status`;
- `thresholds_provisional`, which is always `true` until this rubric is grounded.

## Next steps to move this out of "provisional"

1. Complete Track A literature review items 2-3 (surrogate-data methods, EEG artifact/noise literature) to
   ground `phase_scramble` and `structured_noise_injection`.
2. Resolve the `channel_dropout` open item or drop it from the panel.
3. Run the smoke test on synthetic data, then on CHB-MIT, to get real disruption-score distributions to
   calibrate `tau_*` against — do not hand-pick thresholds without real distributions to check them against.
4. Update this file's status line to "grounded" once 1-3 are done, and record what changed in `CHANGELOG.md`.
