#!/usr/bin/env python3
"""End-to-end pipeline smoke test on a synthetic, in-memory EEG epoch.

Analog of GeoBind's src/run_pp_smoke_test.py / run_pl_smoke_test.py: proves the pipeline's
plumbing is correct (ingest -> hotspot ranking -> perturbation panel -> comparison ->
interpretation) on synthetic data that needs no downloaded dataset file, BEFORE wiring in
CHB-MIT. Not a scientific result — a wiring check, exactly like GeoBind's smoke tests.

STATUS: partially runnable. Stage 1 (src/core/signal_ingest.py: in-memory ingest, duplicate-
channel handling, epoching) is implemented and checked by check_signal_ingest(). Every later
stage (metrics_shared.py, hotspot_detection.py, perturbation_design.py,
perturbation_execution.py, compare.py, interpret_mechanism_profiles.py) is still a stub that
raises NotImplementedError; the test stops cleanly after stage 1. Stages are filled in
incrementally in ROADMAP.md Phase 1 order.
"""

from __future__ import annotations

import numpy as np

from src.core.signal_ingest import (
    EpochConfig,
    IngestConfig,
    epoch_recording,
    recording_from_array,
)


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


def check_signal_ingest(sampling_rate_hz: float = 256.0) -> None:
    """Stage 1 check on synthetic data with a planted duplicate channel (no dataset file).

    Plants the MNE de-dup pattern ("X-Y-0" / "X-Y-1", identical data) and checks it collapses to
    one "X-Y" channel; checks a non-identical duplicate is refused; checks epoch shapes and that
    every epoch is the exact source slice.
    """
    base = make_synthetic_epoch(n_channels=3, n_samples=2560, sampling_rate_hz=sampling_rate_hz)
    data = np.vstack([base, base[1:2]])  # 4th row is an exact copy of row 1
    names = ["A-B", "X-Y-0", "C-D", "X-Y-1"]

    rec = recording_from_array(data, sampling_rate_hz, names)
    assert rec.meta.channel_names == ["A-B", "X-Y", "C-D"], rec.meta.channel_names
    assert rec.meta.dropped_duplicate_channels == {"X-Y": ["X-Y-1"]}
    assert rec.data.shape == (3, 2560)
    assert np.array_equal(rec.data, base)
    print(f"[smoke] ingest: duplicate collapsed -> {rec.meta.channel_names}, "
          f"dropped {rec.meta.dropped_duplicate_channels}")

    # verbatim repeated label, identical data -> also collapsed
    rec_v = recording_from_array(data, sampling_rate_hz, ["A-B", "X-Y", "C-D", "X-Y"])
    assert rec_v.meta.channel_names == ["A-B", "X-Y", "C-D"]

    # non-identical duplicate -> refuse rather than pick one
    bad = data.copy()
    bad[3, 0] += 1e-6
    try:
        recording_from_array(bad, sampling_rate_hz, names)
    except ValueError:
        pass
    else:
        raise AssertionError("non-identical duplicate channels were not refused")
    # "keep" and "error" policies
    assert len(recording_from_array(bad, sampling_rate_hz, names, IngestConfig("keep")).meta.channel_names) == 4
    try:
        recording_from_array(data, sampling_rate_hz, names, IngestConfig("error"))
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate_policy='error' did not raise")
    # a legit name ending in -<digit> with no sibling is left alone
    assert recording_from_array(base, sampling_rate_hz, ["A-B", "C3-1", "C-D"]).meta.channel_names == ["A-B", "C3-1", "C-D"]

    # epoching: 2560 samples @ 256 Hz = 10 s
    ep = epoch_recording(rec, EpochConfig(window_s=2.0))
    assert ep.data.shape == (5, 3, 512), ep.data.shape
    assert ep.start_samples.tolist() == [0, 512, 1024, 1536, 2048]
    for k, s0 in enumerate(ep.start_samples):
        assert np.array_equal(ep.data[k], rec.data[:, s0:s0 + 512])
    ep_ov = epoch_recording(rec, EpochConfig(window_s=2.0, step_s=1.0))
    assert ep_ov.data.shape == (9, 3, 512)
    ep_seg = epoch_recording(rec, EpochConfig(window_s=3.0), start_s=1.0, stop_s=8.0)
    assert ep_seg.start_samples.tolist() == [256, 1024]  # trailing partial window dropped
    try:
        epoch_recording(rec, EpochConfig(window_s=0.001))  # 0.256 samples
    except ValueError:
        pass
    else:
        raise AssertionError("non-integer-sample window was not refused")
    print(f"[smoke] epoching: window=2.0 s -> {ep.data.shape}, 1 s hop -> {ep_ov.data.shape}, "
          f"segment [1, 8) s @ 3 s -> starts {ep_seg.start_samples.tolist()}")


def main() -> None:
    check_signal_ingest()
    epoch = make_synthetic_epoch()
    print(f"[smoke] synthetic epoch shape: {epoch.shape}")
    print(
        "[smoke] STOPPING HERE — downstream stages (hotspot ranking, perturbation panel, "
        "comparison, interpretation) are not yet implemented. See src/core/*.py TODOs and "
        "business/bp_v0.md's milestone table."
    )


if __name__ == "__main__":
    main()
