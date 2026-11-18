# Riddler architecture

Status: **scaffold** — this document defines the target shape; most `src/` modules are stubs until the
CHB-MIT smoke test (Phase 2 of the kickoff plan) is built.

## Why this shape

Riddler transplants GeoBind's proven pattern — computer-simulation/structured-perturbation panels used to both
generate training signal and produce mechanistic interpretability — from structural biology into EEG signal
classification. The two-layer split (interface-agnostic core vs. pluggable modality modules) and the
mechanism-aware perturbation-panel discipline are the parts of GeoBind explicitly identified as portable IP,
not the DNA/protein-specific code itself. See GeoBind's `ARCHITECTURE_AUGMENTATION_PLAN.md` and
`mechanism_aware_interpretation_rubric.md` for the source pattern this document ports.

## Layer 1 vs Layer 2

**Layer 1 — platform core (`src/core/`)**: recording-type classification, hotspot detection, perturbation
design, perturbation execution, baseline-vs-perturbed comparison, and the interpretation engine. Never depends
on a specific task type, montage, or dataset.

**Layer 2 — modality modules (`src/modules/<modality>/`)**: pluggable feature extraction only
(`metrics.py` + `validation.py`). Must reuse Layer 1's hotspot detection, perturbation panel, comparison, and
interpretation engine — never own interpretation logic. First modality: `seizure_detection/`.

## Pipeline stage mapping (GeoBind → Riddler)

| Stage | GeoBind | Riddler |
|---|---|---|
| 1 | Raw structure ingest | Raw EEG ingest (MNE-Python) |
| 2 | Chain classification / interface-type detection | Recording-type classification (`detect_recording_type()`) |
| 3 | WT phenotype extraction | Baseline / class-averaged phenotype extraction per channel×band unit |
| 4 | Hotspot ranking (weighted composite + neighborhood exclusion) | Channel×band unit ranking by class-discriminative signal + spatial/spectral neighborhood exclusion |
| 5 | Mechanism-aware perturbation design table | EEG perturbation panel (see `mechanism_aware_interpretation_rubric.md`) |
| 6 | Mutation/run manifest | Perturbation/run manifest — tracked, reproducible |
| 7 | Perturbed-structure generation (deterministic, quantized) | Perturbed-signal generation, deterministic/seeded, quantized on persist |
| 8 | Batch mutant phenotype computation | Batch feature computation — same code, re-run per perturbed signal |
| 9 | WT-vs-mutant comparison (signed deltas, composite score) | Baseline-normalized signed deltas + composite disruption score — normalize from day 1 |
| 10 | Ranked batch summary | Ranked batch summary across all perturbations |
| 11 | Master summary / modeling dataset | Consolidated ML-ready modeling dataset |
| 12 | Baseline ML sanity check | Cheap non-deep baseline (logistic/RF) — pipeline-plumbing check, not a performance claim |
| 13 | Contrast-based interpretation | Amplitude- vs phase- vs timing- vs noise-dominant mechanism classification |
| 14 | Demo/communication figure | Curated figure for stakeholder communication |
| 15 | Graph export | Node = channel×band unit (first-pass choice); edge = spatial channel adjacency (first-pass choice); raw signal as a separate tensor field, not a schema column |
| 16 | GNN dataset assembly + validation | Same — schema-versioned, validator-gated |
| 17 | Tensor conversion + smoke training | Same — proves plumbing, not performance |

## Reproducibility policy

Ported directly from GeoBind:
1. **Quantize persisted artifacts** to a fixed precision at write time to kill floating-point jitter across
   runs (GeoBind rounds coordinates to 0.1 Å; Riddler's analog is TBD per signal-processing stage — decide and
   document once the smoke test is built, don't leave it implicit).
2. **Deterministic canonical serialization**, sorted by a stable identity key (e.g. channel name + band +
   epoch index), not processing order, so re-runs hash identically.
3. **Audit script with FAIL/WARN/PASS semantics** (`src/audit_reproducibility.py`, ported from GeoBind):
   feature/rank/mechanism-call instability = FAIL (science-affecting); raw-artifact-hash drift alone with
   unchanged downstream conclusions = WARN (tolerated nondeterminism, e.g. from a nondeterministic
   filtering/relaxation step — say so explicitly if this happens, don't hide it).

## Open design decisions (not yet resolved — do not presuppose the answer)

- **Graph node/edge definition** beyond the first-pass choice above: is spectral coherence a better edge
  definition than spatial adjacency? Revisit once real CHB-MIT features exist to compare against.
- **Perturbation panel finalization**: the panel in `mechanism_aware_interpretation_rubric.md` is provisional,
  pending Track A literature grounding (surrogate-data methods for `phase_scramble`, EEG artifact/noise
  literature for `structured_noise_injection`, etc.) — see `business/lit_review_science_v1.md`.
- **Quantization precision** for persisted EEG feature arrays — not yet decided (see reproducibility policy
  above). Perturbed *signals* (stage 7) have a first-pass, PROVISIONAL choice: int64 counts of a 1e-9
  signal-unit step (1 nV), recorded per artifact; see `src/core/perturbation_execution.py`. Feature-array
  precision is still open.
