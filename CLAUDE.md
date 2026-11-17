# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Riddler is a mechanism-aware EEG-signal-classification platform — the second proof point (alongside GeoBind,
structural biology) of a shared, transferable methodology: **use controlled, hypothesis-tagged computer
perturbations to both generate training data and produce mechanistic interpretability for ML models**, rather
than treating an ML model as a black box scored on accuracy alone. Riddler is architecturally ported from
GeoBind — same platform-core/modality-module split, same perturbation-panel discipline, same contrast-based
interpretation engine, same reproducibility policy — retargeted from protein structures to EEG recordings.

First modality: **seizure detection on the CHB-MIT Scalp EEG Database**, chosen because it maps directly onto
Ceribell's actual product (rapid seizure/status-epilepticus detection from EEG) — see `business/bp_v0.md` and
`business/market_research_v1.md` for the business framing.

## Architecture shorthand

**Layer 1 — platform core (`src/core/`).** Interface-agnostic. Must never encode assumptions specific to one
recording montage, task type, or dataset. Responsible for: recording-type classification, hotspot (channel×band
unit) detection, the mechanism-aware perturbation panel, perturbation execution, baseline-vs-perturbed
comparison, and the centralized interpretation engine. Interpretation logic stays out of modality modules — it
is core platform IP, exactly as in GeoBind.

**Layer 2 — modality modules (`src/modules/<modality>/`).** Pluggable, task-specific metric extractors. Must
not modify core logic — only extend feature extraction via `metrics.py` + `validation.py`. First (and
currently only) modality: `seizure_detection/`.

Recording type is inferred by a `detect_recording_type()` router in `src/core/`, analogous to GeoBind's
`detect_interface_type()`, unless explicitly overridden.

## Non-negotiable constraints (inherited from GeoBind, adapted)

- **Interpretation logic stays centralized in the platform core.** Never let a modality module contain
  mechanism-classification logic.
- **Never silently guess undocumented thresholds/weights/formulas.** If a value can't be recovered from a doc
  or from cited literature, stop and report it rather than inventing a plausible number. This applies
  especially to `mechanism_aware_interpretation_rubric.md`'s `tau_*` thresholds, which start as provisional
  placeholders (see that file's status note) until grounded in Track A literature.
- **Determinism over cleverness.** Persisted signal/feature artifacts must be quantized/rounded to a fixed
  precision at write time (GeoBind's analog: coordinates rounded to 0.1 Å) to kill floating-point jitter across
  runs. If a step is genuinely nondeterministic, say so explicitly rather than hiding it.
- **Config values are function parameters or config objects, never hardcoded magic numbers** — mirrors
  GeoBind's `Thresholds` dataclass / `DEFAULT_BINDING_WEIGHTS` pattern.
- **Preserve existing output schemas** — new fields are additive columns, not replacements, once a schema
  ships.
- **Prefer augmentation over rewrite** — new scripts/functions alongside existing ones, not silent
  redefinition, once a runner/schema is in use elsewhere.
- **Baseline-normalize comparability from day one.** GeoBind learned the hard way that a raw disruption score
  is not comparable across hotspots without normalizing by each hotspot's own baseline — build the normalized
  variant first, don't retrofit it later.
- **Flag uncertainty, don't round up.** Applies to every doc in this repo (business docs, lit review,
  validation results) — same explicit discipline Talus's business docs use. This includes the institutional
  IP-ownership caveat: it is risk-informed, not resolved, and must never be reported as settled in any
  pitch-facing material until actually confirmed.
- **Validation is not peer-review-only.** The working pattern (see `business/validation_protocol_v1.md` once
  drafted) is: external-practitioner critique → concrete benchmark response against an established public
  method/dataset, plus a reproducibility audit with an explicit FAIL/WARN split (FAIL = a feature, rank, or
  mechanism-classification call changed run-to-run; WARN = a raw artifact hash drifted but downstream
  conclusions didn't).

## Turn protocol (every turn, no exceptions)

Set by the user 2026-11-17. Every turn that changes the repo must be standalone and end with all of:

1. **Update `HANDOFF.md`**: refresh the date, "Where things actually stand", and "Immediate next steps" so a
   cold-start session (or Ricardo) can resume from it alone. Fix stale statements; don't just append.
2. **Update `CHANGELOG.md`**: a new dated entry at the top (most recent first) recording what changed, what was
   verified (actual commands/results), and anything flagged as provisional or undecided.
3. **Commit and push to `origin/master`.** The remote is meant to be standalone while the proof of concept is
   developed, so work lands on `master`, not on side branches. Never commit gitignored material (`business/`,
   `data/raw/`, `outputs/contacts/`).
4. **Close with a suggested next prompt**: a ready-to-paste prompt for the next step, normally the next
   unchecked item in `ROADMAP.md`'s current phase.

This sits on top of the "Definition of done" below and doesn't replace it. If a step can't be completed (e.g. the push
fails), say so explicitly in the reply and in `HANDOFF.md` rather than skipping it silently.

## Definition of done for any task

1. Name the governing source-of-truth doc (`ARCHITECTURE.md` for the core/module boundary,
   `mechanism_aware_interpretation_rubric.md` for interpretation logic).
2. Implement in that doc's specified order.
3. Flag any assumed undocumented value explicitly rather than silently picking one.
4. Add or update a smoke test on demo-scale (synthetic, no dataset file needed) data.
5. Show the diff.
6. Run the smallest relevant test, not the full suite, and report the actual result.
7. State explicitly whether any existing runner/schema/output path was touched, and why.

## GenAI tooling as a design axis

Part of Riddler's explicit purpose is hands-on work with current industry genAI tooling — this should shape
tool choices, not just be a footnote. Concretely: Claude Code drives the literature review and per-company
research directly; an EEG foundation-model embedding may be evaluated as one ML *baseline*, but never replaces
the interpretation engine (interpretation stays rule-driven and centralized, per the non-negotiable above); any
LLM-assisted drafting is scoped to rationale *prose* wrapped around deterministic, code-computed numbers, never
to inventing thresholds or numbers itself.

## Environment (placeholder — finalize once the smoke test is scaffolded)

```bash
mamba create -n riddler python=3.11 -y
mamba activate riddler
pip install mne numpy scipy pandas scikit-learn matplotlib
# GNN/graph layer, added when that stage is reached:
# pip install torch torch-geometric
```

No installed package yet; run as `python -m src.<module>` from `Riddler/`, same convention as GeoBind.
