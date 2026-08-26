# Changelog

All notable changes to Riddler are recorded here, most recent first.

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
