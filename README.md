# Riddler

A mechanism-aware EEG-signal-classification platform. Second proof point (alongside GeoBind, structural
biology) of a shared methodology: controlled, hypothesis-tagged computer perturbations used to both generate
training data and produce mechanistic interpretability for ML models — not a black-box accuracy score alone.

See `CLAUDE.md` for architecture guidance and non-negotiable working conventions, `ARCHITECTURE.md` for the
full pipeline-stage mapping ported from GeoBind, and `mechanism_aware_interpretation_rubric.md` for the
(currently provisional) EEG-native perturbation panel and interpretation logic.

## Status

Scaffold stage. First modality: seizure detection on the CHB-MIT Scalp EEG Database. No pipeline code is wired
to real data yet — see `business/bp_v0.md`'s milestone table for the current sequencing.

## Environment

No `requirements.txt` yet (placeholder, finalize once the smoke test is scaffolded):

```bash
mamba create -n riddler python=3.11 -y
mamba activate riddler
pip install mne numpy scipy pandas scikit-learn matplotlib
```

All commands run from `Riddler/` as `python -m src.<module>` — no installed package, `src` is a plain import
root, same convention as GeoBind.

## Planned runner sequence (mirrors GeoBind's stage order — not yet implemented)

```bash
python -m src.run_wt_phenotypes           # baseline/class-averaged phenotype extraction
python -m src.run_build_perturbation_plan # mechanism-aware perturbation design table
python -m src.run_batch_perturbed_phenotypes
python -m src.run_batch_compare_baseline_vs_perturbed
python -m src.run_rank_batch_summary
python -m src.interpret_mechanism_profiles
python -m src.run_pipeline_smoke_test     # synthetic in-memory EEG epoch, no dataset file needed
```

## Testing

No pytest suite planned initially, same as GeoBind — correctness checked via standalone smoke-test scripts on
synthetic in-memory data first (`run_pipeline_smoke_test.py`), then wired to CHB-MIT once the smoke test
passes.

## Output layout

- `data/raw/` — downloaded datasets (CHB-MIT first), gitignored.
- `outputs/{phenotypes,comparisons,graphs,manifests,reproducibility,audits}/` — each pipeline stage writes to
  its own subdirectory; `outputs/graphs/`, `outputs/audits/`, `outputs/reproducibility/` are gitignored
  (regenerate, don't expect them checked in).
- `business/` — prose business docs (gitignored from this repo's history; see `CLAUDE.md` for why).
