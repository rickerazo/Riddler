# Riddler roadmap

Status as of 2026-11-19: Phase 1 items 1–7 are done. Items 1–6 are `signal_ingest.py`, `metrics_shared.py`,
`perturbation_execution.py`, `compare.py`, `hotspot_detection.py` and `interpret_mechanism_profiles.py`. Item 7 adds
`perturbation_design.build_perturbation_design_table` plus the end-to-end smoke run. The remaining `src/core/*.py` stages are still
documented stubs, and **there is no seizure detector yet**, so there's no model for a perturbation to move. One real CHB-MIT recording
(`chb01_03.edf`) has been explored by hand; see `outputs/exploration/`.

Governing docs: `ARCHITECTURE.md` (stage order 1–17, core/module boundary) and
`mechanism_aware_interpretation_rubric.md` (perturbation panel + interpretation logic; still **provisional**).

**Rule:** each phase ends in an exit gate. Don't start the next phase until the gate passes, and record each pass or
fail in `CHANGELOG.md`.

---

## Phase 1: Plumbing on synthetic data with planted answers ("simulation level 0")

Cheap synthetic signals where we plant the mechanism ourselves. For example, the seizure class differs from
control *only* in delta amplitude on channel 2, or *only* in rhythm/phase structure on channel 3. This is not
neuroscience, but it gives **known ground truth from day one**, so every later stage can be checked against
an answer key.

Implement in ARCHITECTURE.md stage order:

1. ✅ (2026-11-17) `src/core/signal_ingest.py`: `load_eeg_recording()` (MNE) plus an epoching helper. Window length is a config param.
2. ✅ (2026-11-17) `src/core/metrics_shared.py`: log band power per channel×band (plus line length). Band edges are a config
   object, flagged provisional.
3. ✅ (2026-11-17) `src/core/perturbation_execution.py`: the 4 provisional classes (amplitude attenuation, phase scramble,
   temporal jitter, structured noise). Seeded; quantized on persist at an explicit, flagged precision.
   `channel_dropout` stays unbuilt (rubric open item). Done: in-band FFT-bin edits per (epoch, channel) row;
   persisted as int64 counts at a PROVISIONAL 1e-9 step (≈390× finer than CHB-MIT's 0.39 µV ADC step).
4. ✅ (2026-11-17) `src/core/compare.py`: signed deltas plus the **baseline-normalized** disruption score only.
   Done: `|mean Δlog10P| / unit's own baseline SD` (ddof=1, all epochs passed in; **normalizer PROVISIONAL**).
   Adjacent-band Hann-leakage spillover is a separate off-target column, never folded into the target score.
5. ✅ (2026-11-17) `src/core/hotspot_detection.py`: rank units by class-discriminative effect size; weights as a named config.
   Done: score = Σ weight·|Cohen's d| (`RankingWeights`, PROVISIONAL `log_band_power 1.0, line_length 0.0`), greedy
   cross-shaped neighborhood exclusion (adjacent band via band edges; spatial only from a caller-supplied channel
   adjacency, since the core knows no montage). **No cutoff / top-k**: every unit is selected, suppressed or degenerate.
6. ✅ (2026-11-18) `src/core/interpret_mechanism_profiles.py`: rule cascade per the rubric. `Thresholds` default to `None` and the
   engine refuses to classify while any is `None`. The smoke test passes explicitly labeled
   `SMOKE_TEST_ONLY` thresholds that are never used on real data. Done: the GeoBind cascade was ported into
   rubric v0.2 (slot mapping amplitude/timing/noise is **PROVISIONAL**). Spillover is a qualifier
   (`tau_spill`) that downgrades confidence but never changes the call. Planted C2-delta → `amplitude_dominant` / high.
7. ✅ (2026-11-19) `src/run_pipeline_smoke_test.py`: end-to-end on the planted-mechanism generator. **Note (2026-11-18):** with the
   log-band-power readout, phase scramble and jitter score ≈ 0 by construction, so a planted *phase* mechanism can't
   be recovered yet. Plant an amplitude-type mechanism here, or add a phase-sensitive readout first.
   Done: `check_end_to_end()` runs ingest → features → `rank_hotspots` → `build_perturbation_design_table` → panel →
   `compare` → `interpret_mechanism_profiles` on the planted C2-delta generator. It recovers (C2, delta) as the top hotspot
   (d = +18.19) and calls it **`amplitude_dominant` / high**, and a second run is identical. **Flagged:** `n_hotspots`
   has no core default; the smoke test passes `SMOKE_TEST_ONLY_N_HOTSPOTS = 1`. The same base seed is used for every
   design row. The run passes `reproducibility_status="UNKNOWN"` until item 8 exists.
8. `src/audit_reproducibility.py`: two runs → PASS/WARN/FAIL.
9. `requirements.txt`.

**Exit gate:** the smoke test recovers the planted hotspot **and** the planted mechanism, and the audit is PASS across two runs.

## Phase 2: Real CHB-MIT plus a baseline detector

1. Fetch script for a subset of CHB-MIT (start with chb01–chb05) → `data/raw/chbmit/` (gitignored).
2. `src/modules/seizure_detection/validation.py`: parse `chbXX-summary.txt` seizure times; handle the duplicate
   `T8-P8` channel and montage changes across files. Read the real files and don't assume their shape.
3. `src/modules/seizure_detection/metrics.py`: seizure-specific features layered on the core features.
4. Baseline detector (ARCHITECTURE stage 12): features → logistic regression / random forest.
   - **Patient-specific, leave-one-seizure-out** evaluation, following the Shoeb & Guttag (2010) CHB-MIT protocol.
     Verify their published numbers from the paper itself before quoting them.
   - Report event sensitivity, false alarms per hour and detection latency.
   - **Never use random-epoch splits.** Neighboring windows leak across folds and inflate CHB-MIT results.

**Exit gate:** detector performance is in the same ballpark as the published patient-specific baseline, with the
comparison written down honestly, including where it falls short.

## Phase 3: Perturbation panel on real data → first mechanism calls

1. Run the panel on top-ranked real hotspots per patient. Measure the change in the **detector's output** (drop in
   seizure probability), not only the change in features. That is what makes this *model* interpretability.
2. Collect disruption-score distributions and *propose* `tau_*` values from them (still provisional).
3. Compare Riddler hotspots with standard attribution baselines on the same detector: occlusion, permutation
   importance, SHAP.
4. In parallel, the Track A literature review grounds `phase_scramble` / `structured_noise_injection` and resolves
   `channel_dropout`.

**Exit gate:** mechanism calls are stable across seeds (audit PASS) and across seizures within a patient.

## Phase 4: Computer-simulation layer, the benchmark

**When:** immediately after Phase 3 passes.
- **Not earlier:** before Phase 3 there's no detector or interpretation engine to benchmark.
- **Not later:** Phase 3 exposes the fundamental limit of real data. Nobody knows the true mechanism of a real
  seizure, so real data alone can never prove the interpretation engine is *right*, only that it is *consistent*.
  A simulator provides the answer key.

What to build:
- **Model:** Epileptor (Jirsa et al. 2014), the standard phenomenological seizure model, available in The Virtual
  Brain (TVB), or as a hand-coded ODE for full control. A small network of regions, projected to a scalp-like
  bipolar montage.
- **Benchmark:** plant mechanisms at the source (raise one region's excitability, change inter-region coupling,
  add realistic artifact noise) → generate data → train the same detector → run Riddler and SHAP/occlusion →
  score the **recovery rate of the planted hotspot and mechanism**.
- **Threshold calibration:** calibrate `tau_*` against simulated ground truth. This requires amending the rubric,
  which currently says to calibrate against CHB-MIT distributions. Decide and record the change in CHANGELOG at
  that point.
- **Sim-to-real check:** does the CHB-MIT-trained detector fire on simulated seizures, and does a sim-trained
  detector fire on real ones?

**Exit gate (go/no-go: "powerful, or not worth doing"):**
- Riddler recovers planted mechanisms **measurably better than SHAP/occlusion**. The margin is pre-registered in
  this file *before* the benchmark runs, never chosen after.
- Mechanism calls are stable (audit PASS) and transfer across patients.
- **If Riddler doesn't beat the standard methods:** stop and rethink the panel rather than polishing it. A clean
  negative is still a useful result.

## Phase 5: Scale-up (only after a "go")

- CNN/RNN detector (matches Ceribell's stated EEG-CNN/RNN stack).
- EEG foundation-model embedding as an additional *baseline*. It never replaces the interpretation engine.
- Graph export and GNN (ARCHITECTURE stages 15–17).
- Full CHB-MIT, then a second dataset (e.g. TUH EEG Seizure Corpus) to test generalization.

---

## Open decisions (flagged, not silently picked)

| Decision | Status |
|---|---|
| Epoch window length, band edges, Welch segment length, log floor, quantization precision, perturbation strengths, compare normalizer (SD vs MAD; all-epochs vs control-only spread), hotspot ranking weights + neighborhood radii/shape + how many selected hotspots feed the panel (`n_hotspots`: required arg, no default; smoke uses 1) + per-design-row seed derivation (currently one shared base seed) | Config params, provisional until Track A / real distributions |
| Python version | `.venv` runs 3.14; CLAUDE.md specifies 3.11. The mamba package cache is corrupted, and fixing it (`mamba clean -a`) affects other envs, so it's the user's call |
| `outputs/exploration/` in git | Currently untracked; decide whether to gitignore |
| Rubric amendment: calibrate `tau_*` on simulation ground truth | Decide at Phase 4 |
| Rubric v0.2 slot mapping (amplitude ← attenuation, timing ← mean(phase scramble, jitter), noise ← noise injection) and new `tau_spill` | PROVISIONAL modelling choice; revisit with Track A |
| Phase 4 pre-registered success margin vs SHAP/occlusion | Set before Phase 4 runs |
