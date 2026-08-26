"""Layer 2 (modality module) — seizure-detection input validation.

Analog of GeoBind's src/modules/protein_dna/validation.py's validate_structure(): checks the
recording actually looks like a seizure-detection-shaped input (expected channels, sampling
rate, presence of seizure annotations) before compute_seizure_detection_metrics() runs.
"""

from __future__ import annotations


def validate_recording(*args, **kwargs):
    """Validate that a loaded recording matches what compute_seizure_detection_metrics()
    expects (annotated seizure onset/offset, minimum channel set, etc.).

    TODO: implement once CHB-MIT's annotation format is inspected directly (don't assume its
    shape — read a real file first).
    """
    raise NotImplementedError("validate_recording: not yet implemented.")
