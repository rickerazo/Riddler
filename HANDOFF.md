# Handoff — 2026-11-17

Session-continuity note for picking this back up (by a future Claude session or by Ricardo directly). See
`CHANGELOG.md` for the detailed chronological log this summarizes, and `ROADMAP.md` for the phased
implementation plan with exit gates (this supersedes the kickoff plan at
`/Users/rick/.claude/plans/recursive-soaring-bengio.md` for engineering sequencing).

**Working rule:** every turn ends with HANDOFF + CHANGELOG updated, a commit, a push to `origin/master`, and a
suggested next prompt. See `CLAUDE.md` § "Turn protocol".

## Where things actually stand

**Latest (2026-11-17):**
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
- **Still true:** every `src/core/*.py` stage other than `signal_ingest.py`, `metrics_shared.py` and `perturbation_execution.py` is a stub, and there is no seizure detector yet.

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

1. **ROADMAP Phase 1, item 4 (recommended):** implement `src/core/compare.py`. It needs signed baseline-vs-perturbed
   feature deltas plus the **baseline-normalized** disruption score only. Decide explicitly how adjacent-band
   Hann leakage (the C2-theta spillover above) is reported: as a separate off-target column, not folded into the target score.
2. **Track A**: state-of-science literature review. It unblocks moving
   `mechanism_aware_interpretation_rubric.md` out of provisional status, and runs in parallel with Phases 1–3.
3. **Track B pass 2**: external research on the 14 companies job_os's data didn't inform (Ceribell, Merge Labs first).
4. **Informational interviews**: 18 real contacts and 2 drafted Merge Labs applications. This one is on Ricardo.

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
| Kickoff plan (full phased plan) | `/Users/rick/.claude/plans/recursive-soaring-bengio.md` |
| Architecture / non-negotiables | `Riddler/CLAUDE.md`, `Riddler/ARCHITECTURE.md` |
| Chronological log | `Riddler/CHANGELOG.md` |
| Business docs (gitignored) | `Riddler/business/*.md` |
| Contact matches (gitignored, PII) | `Riddler/outputs/contacts/` |
| Merge Labs application drafts | `/Users/rick/job_os/applications/ashby_Merge Labs_7c1be553.../` and `.../be78d50e.../` |
