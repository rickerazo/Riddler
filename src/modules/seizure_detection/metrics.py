"""Layer 2 (modality module) — seizure-detection-specific feature extraction.

First (and currently only) Riddler modality, targeting the CHB-MIT Scalp EEG Database. Must
only extend feature extraction — reuse src/core/'s hotspot detection, perturbation panel,
comparison, and interpretation engine unmodified. Interpretation logic must NOT be added here;
see src/core/interpret_mechanism_profiles.py.

Analog of GeoBind's src/modules/protein_dna/metrics.py.
"""

from __future__ import annotations


def compute_seizure_detection_metrics(*args, **kwargs):
    """Seizure-detection-specific features (e.g. spike-wave discharge indicators, ictal-onset
    features) layered on top of src/core/metrics_shared.py's baseline phenotypes.

    TODO: implement once CHB-MIT is wired in and the literature review (Track A item 6,
    seizure-detection-specific CHB-MIT literature) identifies which published features are
    worth reproducing as a starting point.
    """
    raise NotImplementedError("compute_seizure_detection_metrics: not yet implemented.")
