# Changelog

All notable changes to Riddler are recorded here, most recent first.

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
