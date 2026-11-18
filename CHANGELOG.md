# Changelog

All notable changes to Riddler are recorded here, most recent first.

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
