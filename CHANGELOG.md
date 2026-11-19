# Changelog

All notable changes to Riddler are recorded here, most recent first.

## 2026-11-18: ROADMAP Phase 1 item 6, `interpret_mechanism_profiles.py` implemented

Governing doc: `mechanism_aware_interpretation_rubric.md` (ARCHITECTURE stage 13). It previously named the
cascade but not the rule conditions. The exact rules were recovered from GeoBind's
`~/Projects/GeoBind/docs/design/mechanism_aware_interpretation_rubric.md` and `src/interpret_mechanism_profiles.py`.
They were written into the rubric **first** as a new section, "EEG rule specification (v0.2)", and the code follows it.

### Rubric v0.2

- **Slot mapping (PROVISIONAL, a modelling choice):**
  - amplitude ← GeoBind charge: `D_amp`;
  - timing ← geometry: `D_timing = mean(D_phase, D_jitter)`;
  - noise ← steric: `D_noise`.
- `D_k` = compare.py's `target_disruption_score_normalized`.
- Magnitude layer, contrasts (`S_amp`, `S_timing`, `S_noise`, normalized by `R_D`), the 7-rule cascade, the
  confidence gap `G` and the reproducibility gate (WARN −1 level, FAIL → `unstable_not_interpretable`, UNKNOWN
  noted) are ported 1:1.
- **Spillover question resolved (it was open in HANDOFF 2026-11-17):** spillover is an analog of GeoBind's
  clash qualifier.
  - `spillover_ratio = adjacent-band spillover of the leading class / its D`.
  - `≥ tau_spill` → `spillover_exceeds_target` and confidence −1 level. The call itself never changes.
- **Dropped:** GeoBind's local and electrostatic support layers, plus `tau_local`, `tau_electro` and
  `tau_clash`. None of these has an EEG analog.
- **Added:** `tau_spill`.
- **Thresholds:** every one is `None` by default, and the engine raises `ValueError` until all are set.
  GeoBind's numeric defaults are not copied into the core; `tau_material = 50` is in GeoBind score units.

### Code

- `src/core/interpret_mechanism_profiles.py`: replaced the stub. It provides:
  - `Thresholds` (frozen, `require_calibrated()`);
  - `MechanismCall` with `to_row()`, the rubric's output fields plus `thresholds_provisional`;
  - `classify_hotspot_mechanism(panel, thresholds, spillover_adjacent, reproducibility_status, hotspot)`;
  - `interpret_mechanism_profiles(summaries, ...)`, which groups `ComparisonResult.summary()` rows per hotspot.
    Duplicate classes raise, unknown classes raise, and a missing or non-finite D gives `incomplete_panel`.
    Output is sorted by hotspot.
- `src/run_pipeline_smoke_test.py`: added `check_interpret_mechanism_profiles()` with explicitly labelled
  `SMOKE_TEST_ONLY_THRESHOLDS`:
  - GeoBind's dimensionless `tau_dom 0.35, tau_weak 0.15, tau_broad 0.25, tau_high 0.25, tau_med 0.10`;
  - `tau_material 1.0` and `tau_spill 1.0`, picked for the synthetic scale.

### Verified

Ran `.venv/bin/python -m src.run_pipeline_smoke_test` and got exit 0. A second run's output is byte-identical
(`cmp`).
- **Planted (C2, delta)**, real panel through compare.py: D = amplitude 1.290, phase 0.084, jitter 0.001,
  noise 0.596. Normalized contrasts are amplitude 0.968, timing −0.968, noise −0.538. The result is
  **`amplitude_dominant` / high**, with `spillover_minor` (ratio 0.015).
- Hand-built panels reach all 7 cascade branches, plus `incomplete_panel` and `unstable_not_interpretable`.
- WARN takes high → medium.
- The real noise-run spillover (1.773) on a noise-led panel with target 0.6 gives `spillover_exceeds_target`
  and takes confidence high → medium, with the call unchanged.
- `Thresholds()` refuses to classify. Duplicate or unknown classes are refused. Input order doesn't change the output.
- No existing runner, schema or output path was touched. compare, hotspot and perturbation modules are
  unchanged; the smoke test only gained a check.

### Flags

- **Known limitation:** with the Phase 1 readout (log band power), phase scramble and jitter preserve power by
  construction. `D_timing ≈ 0` there, so `timing_dominant` cannot fire on feature deltas. A planted
  rhythm/phase mechanism (ROADMAP item 7's wording) is therefore **not recoverable** until D comes from a
  phase-sensitive readout. The engine is readout-agnostic. Item 7 must either plant an amplitude-type
  mechanism or add a phase-sensitive readout.
- The `mixed_weak_timing_led` and `mixed_weak_noise_led` branches are implemented but not exercised by the smoke test.

## 2026-11-17: ROADMAP Phase 1 item 5, `hotspot_detection.py` implemented

Governing doc: `ARCHITECTURE.md` stage 4 (channel×band ranking by class-discriminative signal + spatial/spectral
neighborhood exclusion; core must not encode a montage).

- `src/core/hotspot_detection.py`: replaced the stub.
  - `rank_hotspots(features, labels, positive_label, weights, neighborhood)` → `HotspotRanking`.
    Exactly two classes; `positive_label` is explicit (no silent default).
  - Effect size: Cohen's d (pooled SD, ddof=1 per class) per unit for log band power and per channel for line
    length. The signed d is kept; the score uses |d|.
  - Score = Σ weight·|d| over nonzero-weight components (`RankingWeights`, the `DEFAULT_BINDING_WEIGHTS` analog).
  - Neighborhood exclusion: greedy in descending score; a selected unit suppresses its "cross" neighbors:
    same channel within `spectral_radius_bands` hops of band adjacency (from BandConfig edges via
    `compare.adjacent_bands`), and same band within `spatial_radius_hops` of a **caller-supplied**
    `channel_adjacency`. Diagonals are not neighbors.
  - Ties broken by (channel index, band index). `to_rows()` gives canonical rows with status/rank/suppressed_by.
  - `HotspotUnit` keeps its original fields (`channel`, `band`, `rank_score`); new fields are additive.
- **Provisional, flagged in code (`PROVISIONAL_*`, `provisional=True` on both configs) and here:**
  - Weights `log_band_power 1.0, line_length 0.0`. With line length off, the ranking is pure |d|; the 1.0 only
    sets the sign. A nonzero line-length weight would be undocumented, so it is wired in but off.
  - Radii = 1 hop (smallest non-trivial; not from literature). Cross vs box shape and d vs Hedges' g are open.
  - No spatial exclusion by default: channel geometry belongs to the modality module (Phase 2, CHB-MIT bipolar chains).
  - **No threshold, cutoff or top-k was introduced.** Every unit is selected, suppressed, or degenerate
    (zero pooled SD → NaN, listed, no epsilon). How many selected units feed the perturbation panel is still open.
- `src/run_pipeline_smoke_test.py`: new `check_hotspot_detection()`; `check_compare()` docstring fixed
  ("far bands are exactly 0" → other channels exactly 0, same-channel far bands round-off only); module docstring
  and stop message updated.
- `ROADMAP.md`: item 5 ticked; ranking weights/radii added to the provisional-values row.
- No shipped runner or schema touched: the stub was `(*args, **kwargs)` raising `NotImplementedError` and nothing called it.

Verified (`.venv/bin/python -m src.run_pipeline_smoke_test`, exit 0, all assertions pass), planted C2-delta:

- (C2, delta) is rank 1, d = +18.19; d matches stage 3's Cohen's d (rtol 1e-12).
- Default config: 9 selected + 11 suppressed = 20 units; (C2, theta) suppressed by (C2, delta).
- Rerun: bit-identical `rank_score`, identical `to_rows()` and order.
- Radius 0 → no suppression; order equals a plain descending-|d| sort.
- With a C0–C1–C2–C3 chain adjacency, (C2, delta) suppresses exactly (C1, delta), (C3, delta), (C2, theta).
- Exclusion bites: with (C2, theta) shifted +6 SD and (C0, beta) +3 SD, raw rank 2 is (C2, theta); with exclusion,
  rank 2 becomes (C0, beta).
- Flat channel → 5 degenerate units, not ranked; bad labels / unknown adjacency channel / zero weights / negative radius refused.
- **Flag:** ranks 2–9 on the planted data are noise (|d| ≤ 0.57). Without a cutoff they still get ranks; deciding
  how many to perturb (or a grounded significance criterion) is a Phase 3 / Track A decision, not made here.

## 2026-11-17: ROADMAP Phase 1 item 4, `compare.py` implemented

Governing docs: `ARCHITECTURE.md` stage 9 (baseline-normalized signed deltas, normalize from day 1) and
`mechanism_aware_interpretation_rubric.md` ("Baseline-normalize before comparing across hotspots"; **provisional**).

- `src/core/compare.py`: replaced the stubs.
  - `compute_signed_deltas(baseline, perturbed)` → `SignedDeltas`: per-epoch `perturbed − baseline` for
    `log_band_power` (epochs×channels×bands) and `line_length` (epochs×channels).
    - It raises if the two `EpochFeatures` differ in channels, bands, band edges, spectral config, sampling rate,
      window or `start_samples`.
    - Sign = the feature's own direction. It is not re-oriented to "positive = disruptive", since both up and down moves in band power are disruptive.
  - `compute_disruption_score_normalized(...)` → `ComparisonResult` with per-unit `delta_mean`, `delta_sd`,
    `baseline_spread`, `normalized_delta` (signed) and `disruption_score_normalized = |mean Δ| / spread`.
    This is the only score exposed; there is no un-normalized score.
  - Off-target reporting: each unit carries a `relation` (`target` / `adjacent_band_same_channel` /
    `other_band_same_channel` / `other_channel`). Band adjacency comes from shared BandConfig edges
    (`adjacent_bands()`), not names or order, so it stays montage- and band-set-agnostic.
    `summary()` reports `target_disruption_score_normalized` and, as separate keys,
    `offtarget_adjacent_band_max_disruption_normalized` and `offtarget_other_max_disruption_normalized`.
    Nothing sums them.
  - `to_rows()`: canonical per-unit rows sorted by (channel index, band index), for later persistence and auditing.
- **Provisional, flagged in code (`PROVISIONAL_NORMALIZER_*`) and here:**
  - Normalizer = sample SD (ddof=1) of the unit's baseline log10 power over all epochs passed in.
    Open sub-choices:
    - SD vs MAD (`NormalizerConfig(method="mad")` is offered, uncalibrated);
    - all-epochs vs a class subset (`spread_epoch_mask`);
    - spread vs class-discriminative effect size as the "baseline engagement" normalizer.
  - Zero spread → NaN plus `degenerate_units`. No epsilon floor was invented.
  - No composite weights: log band power is the only per-unit feature. Line-length deltas are returned but not scored.
  - No quantization here (nothing persisted). Feature-array precision is still open.
- `src/run_pipeline_smoke_test.py`: new `check_compare()`.
  - New constants: `SMOKE_TEST_ONLY_POWER_PRESERVED_MAX_NORM = 0.25` and `SMOKE_TEST_ONLY_ROUNDOFF_MAX_NORM = 1e-6`.
  - The docstring and stop message now say the test stops after stage 9.
- `ROADMAP.md`: item 4 ticked. The compare normalizer is added to the provisional-values row.
- No shipped runner or schema touched. The stubs were `(*args, **kwargs)` and nothing called them.

Verified (`.venv/bin/python -m src.run_pipeline_smoke_test`, exit 0, all assertions pass), planted C2-delta, seed 7:

| Perturbation | Target score (signed) | Adjacent C2-theta spillover |
|---|---|---|
| attenuation | 1.290 (−1.290) | 0.019 |
| phase scramble | 0.084 | 0.306 |
| temporal jitter | 0.001 | 0.261 |
| structured noise | 0.596 | 1.773 |

- Attenuation's largest normalized disruption over all 20 units is at (C2, delta).
- Other channels score exactly 0. Same-channel far bands max 3.6e-16 (round-off).
- A rerun gives bit-identical arrays and identical `to_rows()` / `summary()`.
- Mismatched epochs are refused.
- Normalizer sensitivity (reported, not hidden):
  - C2-delta spread is 0.466 over all epochs vs 0.065 over control epochs only.
  - With the control-only spread, attenuation → 9.24 and phase scramble → 0.61. Phase scramble is then no longer
    "near zero", so the "near zero" claim holds only under the default normalizer.
  - With MAD, attenuation → 0.86.
- **Flagged for stage 13:** under noise injection the adjacent-band spillover (1.77) exceeds the target score (0.60).
  Whether spillover discounts a mechanism call is undecided interpretation logic.

## 2026-11-17: ROADMAP Phase 1 item 3, `perturbation_execution.py` implemented

Governing docs: `ARCHITECTURE.md` stage 7 (deterministic, seeded, quantized on persist) and
`mechanism_aware_interpretation_rubric.md` (panel; **provisional**). Implemented per `ROADMAP.md` Phase 1 item 3.

- `src/core/perturbation_execution.py`: replaced the stub.
  - `apply_perturbation(data, sampling_rate_hz, spec, channel_indices, band_hz, seed, config)` → `PerturbedSignal`
    (`data` plus a JSON-serializable provenance `record` with the triple tags, target, seed, params and `provisional: True`).
    - Time is on the last axis and channels on the second-to-last.
    - Each (epoch, channel) row is `rfft`'d; only bins with `lo <= f < hi` change (the same rule as `metrics_shared`), then `irfft`.
    - `seed` has no default. Input is never mutated.
  - Classes:
    - `amplitude_attenuation`: in-band × gain;
    - `phase_scramble`: in-band phases redrawn uniformly, magnitudes kept, DC/Nyquist untouched;
    - `temporal_jitter`: in-band phase ramp, i.e. a circular delay τ ~ U[−max, max] per row;
    - `structured_noise_injection`: Gaussian noise band-limited to the hotspot band (or `noise_band_hz`), scaled per row to a fixed in-band SNR.
    - `channel_dropout` is not built; passing it raises `ValueError`.
  - Quantize-on-persist: `persist_perturbed_signal()` writes `<stem>.npy` (int64 counts of `step`) plus a sorted-key `<stem>.json`
    with the step, a sha256 of the counts, and the record. `load_perturbed_signal()` verifies the hash.
    `.npz` was avoided because zip member headers carry the write time.
- **Provisional, flagged in code (`PROVISIONAL_*`) and here:**
  - `attenuation_gain = 0.5` (same as the exploration demo);
  - `jitter_max_s = 0.1`: the rubric requires a literature-justified window, and this isn't one;
  - `noise_snr_db = 0.0`;
  - noise band = hotspot band;
  - quantization step `1e-9` signal units (1 nV). The basis for the step: the `chb01_03.edf` header shows 12-bit over ±800 µV
    (digital −2048..2047), an ADC step of ≈0.39 µV, so 1 nV is ≈390× finer. That is a first-pass choice, not a standard.
    `ARCHITECTURE.md`'s open-decision note is updated. Feature-array precision is still open.
- `src/run_pipeline_smoke_test.py`: new `check_perturbation_execution()` on the planted-delta generator
  (perturbing C2-delta). New `SMOKE_TEST_ONLY_*` tolerances: 0.02 / 0.1 / 0.5.
- No shipped runner or schema touched. The stub was `(*args, **kwargs)` and nothing called it. The smoke test only gained a check.

Verified (`.venv/bin/python -m src.run_pipeline_smoke_test`, all assertions pass):
- Amplitude ×0.5: C2-delta Δlog10P mean −0.6006 against an expected 2·log10(0.5) = −0.6021. The per-epoch range is −0.6036..−0.5897.
  Rectangular-window in-band power is exactly ×0.25.
- Phase scramble: in-band magnitudes are exact. The Hann-feature Δ mean is −0.039, but the per-epoch SD is 0.18.
  Power is preserved on average, not per epoch, because a Hann periodogram mixes neighbouring bins, so it depends on phase.
  The in-band waveform corr with the original averages −0.011.
- Jitter: Δ mean +0.0005. Noise at 0 dB: injected in-band power equals signal power exactly, and Δ mean is +0.278
  (≈log10 2 = 0.301 expected).
- For every class, the other channels are bit-identical, out-of-band rfft bins are unchanged (atol 1e-9), and C2 alpha/beta/gamma move by < 1e-9.
- Same seed gives bit-identical arrays for all 4 classes and byte-identical persisted `.npy` + `.json` (two writes). A different
  seed changes the 3 stochastic classes; attenuation is seed-independent. The round trip stays within step/2.
- **Finding to carry into `compare.py`:** the adjacent unit (C2, theta) moves through Hann leakage across the 4 Hz edge.
  Mean Δ: noise +0.335, scramble +0.058, jitter +0.049, attenuation −0.004. The perturbation is band-exact; the feature's window is not.
- Cross-machine / cross-NumPy bit-identity is not claimed. That is for the reproducibility audit (Phase 1 item 8).

## 2026-11-17: ROADMAP Phase 1 item 2, `metrics_shared.py` implemented

Governing doc: `ARCHITECTURE.md` stages 3 and 8 (shared feature extraction, same code on baseline and
perturbed signals). Implemented per `ROADMAP.md` Phase 1 item 2.

- `src/core/metrics_shared.py`: replaced the stub.
  - `compute_epoch_features(epoched, BandConfig, SpectralConfig)` → `EpochFeatures`. It holds `log_band_power`
    (n_epochs, n_channels, n_bands) and `line_length` (n_epochs, n_channels), plus `start_samples`, channel and
    band names, and the configs used.
  - Log band power: a one-sided density PSD (Hann window, `scipy.signal.welch`) integrated over the band's
    bins, then `log10`. Bands are half-open `[lo, hi)`. Extraction raises on any band with no frequency bin or
    above Nyquist instead of returning an empty or truncated band.
  - Line length is `sum(|diff|)` over the epoch (Esteller et al. 2001). It is not length-normalized, so it is
    only comparable within one window length.
  - `extract_baseline_phenotypes(features, labels)` → `ClassPhenotypes`: per-class mean and SD (ddof=1) per
    unit. It only averages. Effect-size ranking stays in stage 4 (`hotspot_detection.py`).
    The stub signature was `(*args, **kwargs)` and nothing called it, so no shipped schema changed.
- **Provisional, not cited or calibrated:**
  - `PROVISIONAL_BANDS_HZ` = delta 0.5–4, theta 4–8, alpha 8–13, beta 13–30, gamma 30–45 Hz. This is the
    conventional split, but edges vary in the literature. Track A must ground them.
  - `SpectralConfig.welch_segment_s = None`: a single whole-epoch periodogram, which gives 0.5 Hz resolution at 2 s.
  - `PROVISIONAL_LOG_FLOOR = 1e-30`: a numerical guard against `log10(0)` on flat channels, not a physiological value.
- No quantization, because nothing is persisted here. The quantize-on-persist precision is still undecided.
- `src/run_pipeline_smoke_test.py`: new `check_metrics_shared()` and generator `make_planted_delta_recording()`.
  The generator makes 4 channels × 80 epochs of 2 s: white noise plus a 1.5–2.5 Hz tone everywhere, with the
  tone ×3 on C2 in the "seizure" half only. The check asserts:
  - analytic scaling: a 10 Hz sine with a=3 gives alpha power 4.5 = a²/2, with ~0 in the other bands;
  - a ramp's line length is exact;
  - a flat channel stays finite;
  - empty and supra-Nyquist bands are refused;
  - the planted unit (C2, delta) has Cohen's d > 5 and every other unit |d| < 1;
  - bit-identical features on rerun.
  The 5 / 1 cut-offs are named `SMOKE_TEST_ONLY_*` and are not thresholds for real data.
- **Finding, by design rather than a bug:** line length does *not* pick up the planted slow-delta change
  (d = −0.37 on C2). Differencing weights high frequencies, so a 2 Hz change sits under the white-noise floor.
  My first draft asserted that it would, and that assertion failed. The test now asserts that line length is
  blind to the delta plant. A second plant, broadband ×2 on C2, is detected by line length on C2 only
  (d = 16.6, others ≤ 0.18). This matters later: line length can't serve as the channel×band unit feature for
  slow-wave mechanisms.

Verified (`.venv`, Python 3.14, SciPy 1.18.1):
- `.venv/bin/python -m src.run_pipeline_smoke_test`: all stage-1 and stage-3 assertions pass. The planted
  (C2, delta) unit has d = 18.19 and the max |d| elsewhere is 0.57. The run then stops as designed.
- On real data, `chb01_03.edf` gives features of shape (1800, 22, 5) and (1800, 22), all finite. Seizure
  epochs [2996, 3036) s (20) vs the rest (1780): the largest class-mean log-power increase is T8-P8 gamma
  (+2.15 log10). This is a plumbing check only and not a finding. It may be muscle artifact; nothing is
  interpreted from it.

## 2026-11-17: ROADMAP Phase 1 item 1, `signal_ingest.py` implemented

Governing doc: `ARCHITECTURE.md` stages 1–2 (core/module boundary). Implemented per `ROADMAP.md` Phase 1 item 1.

- `src/core/signal_ingest.py`: replaced the stub with a working implementation.
  - `load_eeg_recording(path, config)` reads via `mne.io.read_raw`, keeps EEG-typed channels, no filtering or
    resampling, and returns an `EEGRecording` (`data` (n_channels, n_samples) float64 in volts, plus `meta`).
    The stub's declared return type was `RecordingMeta`. Nothing called it, so this changes no shipped schema;
    `RecordingMeta` keeps its original fields and gains `n_samples`, `duration_s` and `dropped_duplicate_channels`.
  - `recording_from_array(...)` is the in-memory path. It shares the duplicate handling with the EDF path, so
    the synthetic test runs the same code.
  - Duplicate channel labels are handled generically, with no CHB-MIT names in core. A group is either a
    verbatim-repeated label or MNE's `<base>-0..<base>-{n-1}` rename pattern when `<base>` is absent.
    `IngestConfig.duplicate_policy`: `drop_identical` (default) keeps the first copy only if all copies are
    bit-identical (exact equality, no tolerance) and raises otherwise. The other options are `error` and
    `keep`. Dropped copies are recorded in `meta.dropped_duplicate_channels`.
  - `epoch_recording(rec, EpochConfig, start_s, stop_s)` makes fixed windows with an optional hop and segment.
    The trailing partial window is dropped, never padded. Window, hop and segment edges must be whole samples,
    otherwise it raises. `start_samples` is the stable identity key for canonical serialization.
  - `python -m src.core.signal_ingest <file>` prints a summary.
- **Provisional:** `EpochConfig.window_s` defaults to `PROVISIONAL_WINDOW_S = 2.0` s. This is not grounded in a
  cited source yet; override per call.
- No quantization at ingest because nothing is persisted here. Quantize-on-persist still applies at stage 7.
- `src/run_pipeline_smoke_test.py`: new `check_signal_ingest()` on synthetic data. It plants a duplicate pair
  and checks: collapse; refusal of a non-identical duplicate; the `keep`/`error` policies; a lone `C3-1`-style
  name left alone; epoch shapes, hops and segments; each epoch equal to its exact source slice; and refusal
  of a non-integer-sample window. The downstream "STOPPING HERE" behavior is unchanged.

Verified (`.venv`, Python 3.14, MNE 1.13.2):
- `.venv/bin/python -m src.run_pipeline_smoke_test`: all stage-1 assertions pass, then the run stops as designed.
- `.venv/bin/python -m src.core.signal_ingest data/raw/chbmit/chb01/chb01_03.edf`: 256 Hz, 22 channels
  (23 in file; `T8-P8-1` dropped as an identical copy of `T8-P8`), 921600 samples = 3600.0 s, 1800 × 22 × 512 epochs.
- Cross-check: the loaded array is bit-identical to MNE's raw minus the dropped copy. Epoching the annotated
  seizure [2996, 3036) s gives 20 epochs, and epoch 0 equals the raw slice exactly.

Not handled yet (Phase 2, modality module): CHB-MIT montage changes across files, and the placeholder `-`
channels in some files. Groups of those would currently collapse to a single `-` channel if they are identical.

## 2026-11-17: Turn protocol added; HANDOFF refreshed

- `CLAUDE.md`: new "Turn protocol" section (user-set). Every turn ends with HANDOFF + CHANGELOG updated, a
  commit, a push to `origin/master`, and a suggested next prompt.
- `HANDOFF.md`: rewritten header and status for 2026-11-17. Fixed stale claims ("no GitHub remote yet",
  "CHB-MIT not fetched"); next steps now point at ROADMAP Phase 1; added open decisions (Python version,
  deleting the merged `roadmap-and-first-data` branch).
- Earlier the same day: merged `roadmap-and-first-data` into `master` (fast-forward, `3dac7d9`) and pushed.
  `outputs/exploration/` is now tracked so the remote is standalone.

## 2026-11-17: First real data explored; implementation roadmap added

- Downloaded one CHB-MIT recording (`chb01_03.edf` + `chb01-summary.txt`, PhysioNet, public) to
  `data/raw/chbmit/chb01/` (gitignored). Seizure annotated at 2996–3036 s.
- Exploration-only figures/scripts in `outputs/exploration/` (no pipeline code touched): control-vs-seizure
  traces, a channel×band power-change heatmap (right temporal F8-T8 / T8-P8 / FT10-T8 / FT9-FT10 lead), and a
  perturbation demo on F8-T8 delta. Amplitude ×0.5 → delta power ratio 0.249; phase scramble → 1.035
  (power preserved, waveform destroyed). Band edges and the 0.5 factor are illustrative, not calibrated.
- Noted the data quirk: CHB-MIT lists `T8-P8` twice (MNE renames the copies `-0`/`-1`).
- Environment: `mamba create` failed on a corrupted package cache (not cleaned; it affects other envs).
  A project-local `.venv/` with Python 3.14 + MNE 1.13 is used instead. This deviates from CLAUDE.md's 3.11 and is flagged.
- Added `ROADMAP.md`: Phases 1–5 with exit gates. A computer-simulation layer (Epileptor) is scheduled for Phase 4
  as the ground-truth benchmark, with a pre-registered go/no-go against SHAP/occlusion.

## 2026-08-26 — Contacts matched; Merge Labs application materials drafted (job_os)

- `src/contacts/neurotech_contact_matching.py` run for real: 18 LinkedIn connections matched across 5 of the
  16 tracked companies (Precision Neuroscience 7, Beacon Biosignals 5, Cognito Therapeutics 4, Synchron 1,
  Neuralink 1). Ceribell — the top market-research target — had zero LinkedIn matches, flagged as the best
  candidate for cold/warm-adjacent outreach rather than a direct connection. Output gitignored
  (`outputs/contacts/`, third-party PII, same convention as job_os's own contact reports).
- Given Merge Labs' upgraded strategic significance (see prior entry), pulled its job_os scoring detail: of 23
  tracked postings, only 3 have gone through job_os's full LLM scoring pass — Data Scientist, Bioengineering
  (free 70, LLM overall 68 — highest of the three), ML Research Scientist – Computational Biophysics (free 70,
  LLM overall 62), ML Research Scientist – De Novo Design (free 65, LLM overall 62). All three
  `BRIDGEABLE_MEDIUM` / `BRIDGE_THEN_APPLY`.
- Generated tailored resume + cover letter for the two highest-scored roles (Data Scientist, Bioengineering;
  ML Research Scientist, Computational Biophysics) via job_os's `generate_tailored_resumes.py` — real
  Claude-backed generation against `MASTER_RESUME.md` + `candidate_profile.yaml` + the actual job descriptions,
  not fabricated. Both drafts name real capability gaps directly (OMICS/BoTorch for the Bioengineering role;
  hands-on MD simulation — GROMACS/AMBER/OpenMM — for the Computational Biophysics role) rather than glossing
  over them. Files live in job_os's own `applications/ashby_Merge Labs_7c1be553.../` and
  `applications/ashby_Merge Labs_be78d50e.../` — not duplicated into this repo, same "reference job_os in
  place" principle used for the LinkedIn export. **Not submitted** — drafts pending the user's review.

## 2026-08-26 — Verified two pass-1 flags: Synchron data collision, Merge Labs product scope

- **Synchron**: confirmed the company-name-collision flag. 16 of the original 23 "Synchron" TRACKER.csv rows
  were actually Synchrony (the financial-services company) via a `builtincincinnati` "recent" search. Corrected
  to the real 7-row picture: San Diego device-engineering/quality/regulatory roles, no dedicated ML/AI roles.
- **Merge Labs**: web-search-verified and substantially upgraded from job_os's stale "~30 employees, newest
  entrant" note. Came out of stealth 2026-01-15 with a $250M seed round at an $850M valuation, OpenAI writing
  the largest single check. Pursuing non-invasive ultrasound + molecular-engineering BCI (not electrode-based) —
  explains job_os's biophysics/de-novo-design/immunotolerization role titles, which looked anomalous before
  verification. Now flagged as the single most strategically relevant company in the tiered list, given its
  direct genAI-industry backing.
- `business/market_research_v1.md` §2/§3 and `business/lit_review_business_v1.md` updated with both
  corrections and full source citations.

## 2026-08-26 — Track B lit review, pass 1 (job_os data mining)

- `business/lit_review_business_v1.md` drafted: mined job_os's already-scraped `TRACKER.csv` (46,202 rows,
  filtered to the 16 tracked neurotech companies), the one available full job-posting text (Paradromics), and
  job_os's own scored `fit_report.md` for Ceribell — zero new scraping, per the plan's pass-1 sequencing.
- Strongest finding: Ceribell has an open "Senior Manager, Applied AI Engineering" role and its highest-scored
  posting explicitly values EEG-CNN/RNN production experience — the most concrete genAI/ML signal of any
  tracked company.
- Honest negative finding: 11 of 16 companies show no usable genAI signal in job_os's scraped data at all
  (non-technical current postings, or zero rows for Zeto/Precision Neuroscience) — flagged as needing pass 2
  (external research), not rounded up to a conclusion about those companies' actual genAI usage.
- Data-quality flag raised, not resolved: several "Synchron" TRACKER.csv rows read like Synchrony (the
  financial company) — needs manual verification before use in market_research_v1.md.
- job_os's own `ai_enablement` role-family tag confirmed unreliable on its own (2 of 3 hits in this company set
  look like taxonomy false positives per job_os's own documented caveat) — only acted on when corroborated by
  the actual job title.

## 2026-08-25 — Workspace scaffolded

- Riddler created as a standalone repo at `/Users/rick/Projectz/Riddler/`, ported from GeoBind's
  mechanism-aware structural-perturbation architecture (see `ARCHITECTURE.md` for the full stage mapping).
- Platform-core / modality-module directory split established (`src/core/`, `src/modules/seizure_detection/`).
- First modality target confirmed: seizure detection on the CHB-MIT Scalp EEG Database, chosen for direct
  product overlap with Ceribell (job_os's highest-scored neurotech target) and with the author's GSU
  electrophysiology background.
- `business/bp_v0.md` and `business/market_research_v1.md` drafted, cloning the exact structure of Talus's
  `bp_v0.md` / `market_research_v1.md` templates, retargeted at the EEG-classification market.
- `mechanism_aware_interpretation_rubric.md` drafted as a v0.1 **provisional** EEG-native rubric — the
  candidate perturbation panel and thresholds are placeholders pending Track A literature grounding (see
  `business/lit_review_science_v1.md` once drafted).
- Known open item, carried over from GeoBind/Talus and applicable here: institutional IP-ownership status is
  risk-informed, not resolved. Do not overclaim sole ownership in any pitch-facing material until confirmed.
