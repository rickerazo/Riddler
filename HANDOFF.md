# Handoff — 2026-08-26

Session-continuity note for picking this back up (by a future Claude session or by Ricardo directly). See
`CHANGELOG.md` for the detailed chronological log this summarizes; see the original kickoff plan at
`/Users/rick/.claude/plans/recursive-soaring-bengio.md` for the full phased plan this is executing against.

## Where things actually stand

**Done and real** (not placeholder):
- Repo scaffolded at `/Users/rick/Projectz/Riddler/`, own local git repo, **no GitHub remote yet** — that's an
  explicit hold pending your go-ahead, not an oversight.
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
- CHB-MIT dataset — not fetched. No pipeline code has touched real data yet.
- `business/validation_protocol_v1.md`, `business/pricing_model_v1.md`, `business/milestone_review_v1.md` —
  not started (Phase 3/4 in the kickoff plan).

## Immediate next steps (pick one, or say what you want instead)

1. **Track B pass 2** — external research (engineering blogs, talks, public statements) on the 14 companies
   job_os's data didn't inform, starting with Ceribell and Merge Labs since those already have the strongest
   base to build on.
2. **Track A** — state-of-science literature review (EEG classification benchmarks, surrogate-data methods,
   artifact/noise literature, explainability literature, EEG graph/GNN literature) — this is what unblocks
   turning `mechanism_aware_interpretation_rubric.md` from provisional to grounded.
3. **CHB-MIT fetch + smoke test wiring** — start filling in the `src/core/*.py` stubs against real data.
4. **Informational interviews** — you have 18 real contacts and 2 drafted Merge Labs applications; the
   remaining bp_v0.md action item is actually reaching out, which is on you, not something I can do on your
   behalf.

## Open decisions still waiting on you (from the original kickoff plan, unresolved)

- GitHub remote name/creation for Riddler — holding until you say go.
- Whether "Riddler" stays an internal codename or becomes customer-facing (like "Talus" is for GeoBind).
- Whether to prioritize the Merge Labs applications (now that they're drafted) over the rest of the Riddler
  research plan, given the strategic overlap you flagged — your call on sequencing.

## Key file map

| What | Where |
|---|---|
| Kickoff plan (full phased plan) | `/Users/rick/.claude/plans/recursive-soaring-bengio.md` |
| Architecture / non-negotiables | `Riddler/CLAUDE.md`, `Riddler/ARCHITECTURE.md` |
| Chronological log | `Riddler/CHANGELOG.md` |
| Business docs (gitignored) | `Riddler/business/*.md` |
| Contact matches (gitignored, PII) | `Riddler/outputs/contacts/` |
| Merge Labs application drafts | `/Users/rick/job_os/applications/ashby_Merge Labs_7c1be553.../` and `.../be78d50e.../` |
