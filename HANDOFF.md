# Handoff — 2026-11-19

Session-continuity note for picking this back up (by a future Claude session or by Ricardo directly). See
`CHANGELOG.md` for the detailed chronological log this summarizes, and `ROADMAP.md` for the phased
implementation plan with exit gates (this supersedes the kickoff plan at
`/Users/rick/.claude/plans/recursive-soaring-bengio.md` for engineering sequencing).

**Working rule:** every turn ends with HANDOFF + CHANGELOG updated, a commit, a push to `origin/master`, and a
suggested next prompt. See `CLAUDE.md` § "Turn protocol".

## Where things actually stand

**Latest (2026-11-19):**
- **ROADMAP Phase 1 item 7 done.** That means the end-to-end smoke run works, and part of the Phase 1 exit gate is met.
  - `src/core/perturbation_design.build_perturbation_design_table(ranking, bands, *, n_hotspots, seed, panel=None)` is
    implemented. It is the analog of GeoBind's `build_mechanism_aware_single_design_table`. It writes one
    execution-ready row per (selected hotspot × panel member), sorted by (rank, panel order). Each row carries the
    channel index, band edges in Hz, the triple tags, the seed, rank provenance and `perturbation_tag`
    (e.g. `C2__delta__amplitude_attenuation`), plus `design_table_schema_version` 1.
    `spec_from_design_row()` rebuilds the spec for execution.
  - **Flagged, not decided: how many selected hotspots feed the panel.** `n_hotspots` is a required
    keyword argument with no default. Omitting it gives a `TypeError`; asking for more than the selected count raises
    instead of shrinking the table. The smoke test passes `SMOKE_TEST_ONLY_N_HOTSPOTS = 1` (the top hotspot).
    On real data this is a Phase 3 decision.
  - **Also flagged:** every row shares the same base seed (7 in the smoke test). A per-row seed derivation is undocumented.
  - `src/run_pipeline_smoke_test.py`: added `run_end_to_end()` and `check_end_to_end()`. On the planted C2-delta
    generator, (C2, delta) is the top hotspot (d = +18.19). The 4-row panel gives D: amplitude 1.290, phase 0.084,
    jitter 0.001, noise 0.596, so the call is **`amplitude_dominant` / high** (`spillover_minor`). These numbers
    match item 6's standalone check exactly. A second full run gives identical tables, summaries and calls.
  - The end-to-end run passes `reproducibility_status="UNKNOWN"` (no downgrade), because the audit (item 8)
    doesn't exist yet; it doesn't claim PASS.
  - **Exit gate status:** hotspot and mechanism recovery pass. The audit-PASS half waits on item 8.

**Earlier (2026-11-18):**
- **ROADMAP Phase 1 item 6 done:** `src/core/interpret_mechanism_profiles.py` is implemented.
  - The rule conditions were missing from Riddler's rubric. They were recovered from GeoBind
    (`~/Projects/GeoBind/docs/design/mechanism_aware_interpretation_rubric.md` + `src/interpret_mechanism_profiles.py`)
    and written into `mechanism_aware_interpretation_rubric.md` § "EEG rule specification (v0.2)" first.
  - **Slot mapping (PROVISIONAL):**
    - amplitude ← attenuation;
    - timing ← mean(phase scramble, jitter);
    - noise ← noise injection.
    These stand in for GeoBind's charge/geometry/steric. The cascade, contrasts, confidence gap and
    reproducibility gate are ported 1:1.
  - **Spillover resolved:** it is a qualifier, like GeoBind's clash. `spillover_ratio ≥ tau_spill` →
    `spillover_exceeds_target`, which lowers confidence one level and never changes the call.
    GeoBind's local/electrostatic support layers were dropped because they have no EEG analog.
  - `Thresholds` (incl. new `tau_spill`) are all `None` → `ValueError`. The smoke test uses labelled
    `SMOKE_TEST_ONLY_THRESHOLDS` (GeoBind's dimensionless taus; `tau_material = tau_spill = 1.0` for synthetic scale).
  - Smoke: the planted (C2, delta) real panel (amp 1.290 / phase 0.084 / jitter 0.001 / noise 0.596) gives
    **`amplitude_dominant` / high**. All 7 branches, plus `incomplete_panel` and FAIL→`unstable_not_interpretable`,
    are reachable. WARN takes high→medium, and noise spillover 1.773 qualifies and downgrades. Two runs give
    byte-identical output.
  - **Flag for item 7:** under the log-band-power readout, phase scramble and jitter score ≈ 0 by construction, so
    `timing_dominant` can't fire and a planted *phase* mechanism isn't recoverable yet. Item 7 should plant an
    amplitude-type mechanism (or add a phase-sensitive readout first).

**Earlier (2026-11-17):**
- **ROADMAP Phase 1 item 5 done:** `src/core/hotspot_detection.py` is implemented.
  - `rank_hotspots(features, labels, positive_label, weights, neighborhood)` → `HotspotRanking`. Score per unit =
    Σ weight·|Cohen's d| (pooled SD, ddof=1); signed d kept as a column.
  - `RankingWeights` is **PROVISIONAL**: `log_band_power 1.0, line_length 0.0`, so the ranking is currently pure
    |d| of log band power. Line length is wired in but off (no documented weighting).
  - Greedy neighborhood exclusion, "cross" shape, radius 1 hop (**PROVISIONAL**): adjacent band on the same channel
    (from band edges), and the same band on neighbor channels **only if the caller passes `channel_adjacency`**.
    The core knows no montage, so the CHB-MIT module must supply bipolar-chain adjacency in Phase 2.
  - **No cutoff/top-k**: every unit is selected, suppressed (with `suppressed_by`) or degenerate (NaN).
  - Smoke: (C2, delta) rank 1 at d = +18.19; rerun bit-identical; with chain adjacency it suppresses exactly
    (C1, delta), (C3, delta), (C2, theta); a planted +6 SD (C2, theta) is raw rank 2 but excluded.
  - **Flag:** ranks 2–9 on the planted data are noise (|d| ≤ 0.57). How many selected hotspots feed the
    perturbation panel is undecided; it's a caller/Phase 3 decision, not a threshold in the core.
  - Also fixed `check_compare`'s docstring: far bands see round-off only, not exactly 0.
- **ROADMAP Phase 1 item 4 done:** `src/core/compare.py` is implemented.
  - `compute_signed_deltas(baseline, perturbed)` returns per-epoch `perturbed − baseline` for log band power and line length.
    It refuses mismatched epochs, channels, bands or spectral configs. The sign is the feature's own direction; it is
    not re-oriented, because a power increase (noise) and a decrease (attenuation) are both disruptive.
  - `compute_disruption_score_normalized(baseline, perturbed, target, normalizer, spread_epoch_mask, record)` →
    `ComparisonResult`. Per unit: `normalized_delta = mean Δlog10P / that unit's baseline spread`, and
    `disruption_score_normalized = |normalized_delta|`. This is the only score; there is no raw variant.
  - Each unit gets a relation to the target: `target`, `adjacent_band_same_channel` (from band edges),
    `other_band_same_channel` or `other_channel`. `summary()` keeps
    `offtarget_adjacent_band_max_disruption_normalized` as its own column, never added to the target score.
  - **Normalizer is PROVISIONAL**: SD (ddof=1) over all baseline epochs passed in; MAD is offered as an alternative.
    The choice matters. On the planted data the C2-delta spread is 0.466 over all epochs, but 0.065 over control
    epochs only, because the all-epochs SD contains the planted class difference.
  - A zero-spread unit gives NaN and is listed in `degenerate_units`; no floor is invented.
  - Composite weights are not introduced: there is one feature per unit, and line length stays out of the score.
  Smoke test on planted C2-delta (default normalizer):

  | Perturbation | Target score | Adjacent C2-theta spillover |
  |---|---|---|
  | attenuation | 1.290 (largest unit) | 0.019 |
  | phase scramble | 0.084 | 0.306 |
  | jitter | 0.001 | 0.261 |
  | noise | 0.596 | **1.773** |

  Other channels score exactly 0, same-channel far bands ≤ 4e-16, and reruns are bit-identical.
  **Flag for stage 13:** under noise, spillover is about 3× the target score. That's why it has its own
  column. How (or whether) spillover discounts a mechanism call is an interpretation-engine decision, still open.
- **ROADMAP Phase 1 item 3 done:** `src/core/perturbation_execution.py` is implemented.
  `apply_perturbation(data, sfreq, spec, channel_indices, band_hz, seed, config)` edits only the target band's
  rfft bins on the target channel(s), per (epoch, channel) row. The 4 classes:
  - amplitude attenuation: gain 0.5;
  - phase scramble: random in-band phases, magnitudes kept;
  - temporal jitter: in-band circular delay of ±0.1 s;
  - structured noise injection: band-limited Gaussian noise at 0 dB in-band SNR.
  `persist_perturbed_signal()` writes int64 counts at a 1e-9 step (`.npy`) plus a sorted-key `.json` provenance file.
  It deliberately avoids `.npz`, because `.npz` embeds timestamps.
  **All strengths and the step are PROVISIONAL.** `channel_dropout` is refused.
  Smoke test on planted C2-delta:
  - attenuation gives Δlog10P = −0.6006 against an expected −0.6021;
  - phase scramble preserves rectangular-window power exactly, shifts the Hann feature by a mean of −0.039 (per-epoch SD 0.18), and drops in-band waveform corr to −0.01;
  - same seed gives bit-identical arrays and files.
  **Flag for `compare.py`:** Hann-window leakage moves the adjacent C2-theta unit (noise +0.34, scramble/jitter
  ≈ +0.05). Off-target *channels* and far bands are untouched.
- **ROADMAP Phase 1 item 2 done:** `src/core/metrics_shared.py` is implemented. `compute_epoch_features()` gives
  log10 band power per channel×band (Hann PSD integrated per band) and line length per channel.
  `extract_baseline_phenotypes()` gives per-class means and SDs. Band edges (delta 0.5–4 … gamma 30–45 Hz),
  the Welch segment and the log floor are all **provisional** config. The smoke test plants delta ×3 on one
  channel and recovers exactly that channel×band unit (d = 18.2; every other unit |d| < 0.6). Line length is
  blind to that slow-delta plant, which is a documented property of the feature rather than a bug; it does
  catch a broadband plant. The features also run on `chb01_03.edf`, giving (1800, 22, 5).
- **ROADMAP Phase 1 item 1 done:** `src/core/signal_ingest.py` is implemented. It has `load_eeg_recording()` via MNE,
  `recording_from_array()`, generic duplicate-channel handling (the default drops bit-identical copies and
  raises on non-identical ones), and `epoch_recording()`. Window length is a config param with a
  **provisional** 2.0 s default. The synthetic check lives in `src/run_pipeline_smoke_test.py` and passes.
  `chb01_03.edf` loads to 22 ch × 3600 s at 256 Hz (the duplicate `T8-P8` collapsed), bit-identical to MNE.
- GitHub remote live: `origin` = `github.com:rickerazo/Riddler.git`; `master` is pushed and current.
  (An old side branch, `roadmap-and-first-data`, is fully merged and can be deleted.)
- First real data: `data/raw/chbmit/chb01/chb01_03.edf` + `chb01-summary.txt` (gitignored; fetch steps in
  `outputs/exploration/README.md`). Seizure annotated 2996–3036 s.
- Exploration figures + scripts tracked in `outputs/exploration/`: control-vs-seizure traces, a channel×band
  hotspot heatmap (right temporal leads), and a perturbation demo (amplitude ×0.5 → delta power 0.25;
  phase scramble → 1.03). Exploration only, not pipeline code.
- `ROADMAP.md` written: Phases 1–5 with exit gates; Epileptor simulation layer at Phase 4 as the ground-truth
  benchmark with a pre-registered go/no-go against SHAP/occlusion.
- Environment: project-local `.venv/` (Python 3.14, MNE 1.13) because the mamba package cache is corrupted.
  This deviates from CLAUDE.md's 3.11; still an open decision for Ricardo.
- **Still true (updated 2026-11-19):** `src/audit_reproducibility.py` is a stub. Every stage in `src/core/` that Phase 1 uses is implemented. There is no seizure detector yet.

**Earlier work (2026-08-26), still accurate unless noted:**
**Done and real** (not placeholder):
- Repo scaffolded at `/Users/rick/Projectz/Riddler/` (GitHub remote now live, see above).
- Platform-core/modality-module architecture ported from GeoBind (`CLAUDE.md`, `ARCHITECTURE.md`) — most
  `src/core/*.py` are intentionally documented stubs (`raise NotImplementedError`), not fake implementations.
  The synthetic smoke test (`src/run_pipeline_smoke_test.py`) runs and stops cleanly at the first unimplemented
  stage — verified by actually running it.
- `business/bp_v0.md`, `business/market_research_v1.md` drafted (gitignored — see `CLAUDE.md`/`.gitignore` for
  why business docs stay out of this repo's git history).
- `business/lit_review_business_v1.md` — Track B pass 1 complete (job_os data mining, zero new scraping) +
  a verification pass on two flagged items. **Real, cited findings**, not fabricated:
  - Ceribell: open "Senior Manager, Applied AI Engineering" role + explicit EEG-CNN/RNN requirement — strongest
    lead of the 16 companies.
  - Merge Labs: OpenAI-backed ($250M seed, $850M valuation, disclosed 2026-01-15), non-invasive
    ultrasound+molecular-engineering BCI — verified via web search, now the single most strategically relevant
    company on the list given its direct genAI-industry backing.
  - Synchron: corrected a real data-quality bug (16 of 23 tracked rows were actually Synchrony, the financial
    company) — real Synchron picture is thin (7 rows, hardware/regulatory, no dedicated ML roles).
  - 11 of 16 companies still have no usable genAI signal from job_os data alone — honestly reported as a gap,
    not papered over.
- Contacts matched: `src/contacts/neurotech_contact_matching.py` run against the real LinkedIn export (read in
  place from job_os, never copied). 18 matches across 5 companies — see `outputs/contacts/` (gitignored, PII).
  Ceribell had zero matches — best candidate for cold outreach, not a warm intro.
- Two Merge Labs application drafts generated via job_os's own `generate_tailored_resumes.py` (real
  Claude-backed generation, not fabricated) — sitting unsubmitted in job_os's `applications/` folders, pending
  your review.

**Still provisional / not started:**
- `mechanism_aware_interpretation_rubric.md`'s EEG perturbation panel and all `tau_*` thresholds — explicitly
  flagged placeholder, waiting on Track A literature grounding.
- Track A (state-of-science literature review) — not started at all.
- `business/market_research_v1.md` §1 (spend/funding figures) and §4 (neurotech startup track records) —
  not started; §3 (competitive landscape) only has Ceribell and Merge Labs rows filled in.
- Track B pass 2 (external research) for the 14 companies not yet well-informed by job_os data alone.
- CHB-MIT: one recording fetched. Only the stage-1 ingest has touched it. Montage changes across files and the
  `-` placeholder channels in some files are Phase 2 (modality-module) work, not handled yet.
- `business/validation_protocol_v1.md`, `business/pricing_model_v1.md`, `business/milestone_review_v1.md` —
  not started (Phase 3/4 in the kickoff plan).

## Immediate next steps (pick one, or say what you want instead)

1. **ROADMAP Phase 1, item 8 (recommended):** `src/audit_reproducibility.py`, two runs → PASS/WARN/FAIL.
   - Run `run_end_to_end()` twice, and persist the design table, compare summaries and calls as canonical JSON.
     Persist the perturbed signals via `persist_perturbed_signal`.
   - FAIL = a hotspot rank, design row or mechanism call changed. WARN = only a raw artifact hash drifted.
   - Feed the audit's status back into `interpret_mechanism_profiles` in place of `UNKNOWN`.
   - This closes the Phase 1 exit gate.
2. **ROADMAP Phase 1, item 9:** `requirements.txt`, a small task to pair with item 8.
3. **Track A**: state-of-science literature review. It grounds the panel, the v0.2 slot mapping and the `tau_*` values.
4. **Track B pass 2** / informational interviews (these are on Ricardo).

## Open decisions still waiting on you

- Python version: `.venv` is 3.14 vs CLAUDE.md's 3.11 (fixing mamba needs `mamba clean -a`, which affects other envs).
- Delete the merged `roadmap-and-first-data` branch (local + remote)?

- Whether "Riddler" stays an internal codename or becomes customer-facing (like "Talus" is for GeoBind).
- Whether to prioritize the Merge Labs applications (now that they're drafted) over the rest of the Riddler
  research plan, given the strategic overlap you flagged — your call on sequencing.

## Key file map

| What | Where |
|---|---|
| Implementation roadmap (phases + exit gates) | `Riddler/ROADMAP.md` |
| GeoBind source for ported rules | `~/Projects/GeoBind/docs/design/mechanism_aware_interpretation_rubric.md` |
| Kickoff plan (full phased plan) | `/Users/rick/.claude/plans/recursive-soaring-bengio.md` |
| Architecture / non-negotiables | `Riddler/CLAUDE.md`, `Riddler/ARCHITECTURE.md` |
| Chronological log | `Riddler/CHANGELOG.md` |
| Business docs (gitignored) | `Riddler/business/*.md` |
| Contact matches (gitignored, PII) | `Riddler/outputs/contacts/` |
| Merge Labs application drafts | `/Users/rick/job_os/applications/ashby_Merge Labs_7c1be553.../` and `.../be78d50e.../` |
