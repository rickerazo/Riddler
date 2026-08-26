#!/usr/bin/env python3
"""End-to-end pipeline smoke test on a synthetic, in-memory EEG epoch.

Analog of GeoBind's src/run_pp_smoke_test.py / run_pl_smoke_test.py: proves the pipeline's
plumbing is correct (ingest -> hotspot ranking -> perturbation panel -> comparison ->
interpretation) on synthetic data that needs no downloaded dataset file, BEFORE wiring in
CHB-MIT. Not a scientific result — a wiring check, exactly like GeoBind's smoke tests.

STATUS: not yet runnable. Every stage this test would call
(src/core/signal_ingest.py, hotspot_detection.py, perturbation_design.py,
perturbation_execution.py, compare.py, interpret_mechanism_profiles.py) is currently a stub
that raises NotImplementedError. This file exists now so the target shape is visible and the
smoke test can be filled in incrementally as each stage lands, per business/bp_v0.md's
milestone table (Wk4-6).
"""

from __future__ import annotations

import numpy as np


def make_synthetic_epoch(
    n_channels: int = 4, n_samples: int = 2560, sampling_rate_hz: float = 256.0, seed: int = 0
) -> np.ndarray:
    """Deterministic synthetic multi-channel EEG-shaped array (channels x samples) — pure
    noise/sinusoid mixture, no real signal content. Only useful for exercising the pipeline's
    plumbing, never for a scientific claim.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n_samples) / sampling_rate_hz
    epoch = np.zeros((n_channels, n_samples))
    for ch in range(n_channels):
        freq = 8 + ch * 2  # alpha-ish placeholder frequency, arbitrary
        epoch[ch] = np.sin(2 * np.pi * freq * t) + 0.1 * rng.standard_normal(n_samples)
    return epoch


def main() -> None:
    epoch = make_synthetic_epoch()
    print(f"[smoke] synthetic epoch shape: {epoch.shape}")
    print(
        "[smoke] STOPPING HERE — downstream stages (hotspot ranking, perturbation panel, "
        "comparison, interpretation) are not yet implemented. See src/core/*.py TODOs and "
        "business/bp_v0.md's milestone table."
    )


if __name__ == "__main__":
    main()
