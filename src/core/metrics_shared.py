"""Layer 1 (platform core) — feature/phenotype extraction shared across all modalities.

Analog of GeoBind's core energy-proxy metrics (src/phenotypes.py, src/energy_proxies.py):
interface-agnostic phenotype computation run identically on baseline and perturbed signals
(pipeline stages 3 and 8 both call into this module — same code, different input).

See ARCHITECTURE.md, pipeline stages 3 and 8.
"""

from __future__ import annotations


def extract_baseline_phenotypes(*args, **kwargs):
    """Extract class-averaged baseline phenotypes per channel×band unit from a recording.

    TODO: implement once src/core/signal_ingest.py's load_eeg_recording() is implemented and
    the CHB-MIT smoke-test milestone is reached (business/bp_v0.md, Wk4-6).
    """
    raise NotImplementedError("extract_baseline_phenotypes: not yet implemented.")
