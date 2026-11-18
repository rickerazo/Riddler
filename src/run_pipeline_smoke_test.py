#!/usr/bin/env python3
"""End-to-end pipeline smoke test on a synthetic, in-memory EEG epoch.

Analog of GeoBind's src/run_pp_smoke_test.py / run_pl_smoke_test.py: proves the pipeline's
plumbing is correct (ingest -> hotspot ranking -> perturbation panel -> comparison ->
interpretation) on synthetic data that needs no downloaded dataset file, BEFORE wiring in
CHB-MIT. Not a scientific result — a wiring check, exactly like GeoBind's smoke tests.

STATUS: partially runnable. Stage 1 (src/core/signal_ingest.py: in-memory ingest, duplicate-
channel handling, epoching) is checked by check_signal_ingest(); stage 3 (src/core/metrics_shared.py:
log band power per channel x band, line length, class-averaged phenotypes) is checked by
check_metrics_shared() against a planted mechanism. Every later stage (hotspot_detection.py,
perturbation_design.py, perturbation_execution.py, compare.py, interpret_mechanism_profiles.py)
is still a stub that raises NotImplementedError; the test stops cleanly after stage 3. Stages are filled in
incrementally in ROADMAP.md Phase 1 order.
"""

from __future__ import annotations

import numpy as np

from src.core.metrics_shared import (
    BandConfig,
    SpectralConfig,
    compute_epoch_features,
    extract_baseline_phenotypes,
)
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


# SMOKE_TEST_ONLY separation thresholds on a standardized mean difference (Cohen's d, pooled SD).
# Used only to assert the planted unit stands out on synthetic data; never a threshold for real data
# and not a hotspot-detection criterion (that is stage 4, hotspot_detection.py).
SMOKE_TEST_ONLY_PLANTED_MIN_D = 5.0
SMOKE_TEST_ONLY_UNPLANTED_MAX_ABS_D = 1.0


def make_planted_delta_recording(
    n_channels: int = 4,
    planted_channel: int = 2,
    delta_gain: float = 3.0,
    n_epochs_per_class: int = 40,
    window_s: float = 2.0,
    sampling_rate_hz: float = 256.0,
    seed: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """Synthetic two-class recording with ONE planted mechanism (simulation level 0).

    Every epoch, every channel: white noise (SD 1) plus a delta tone (amplitude 1, frequency drawn
    uniformly from 1.5-2.5 Hz, random phase), so Hann leakage stays inside the 0.5-4 Hz band. The
    second half of the epochs is the "seizure" class, identical except that the delta tone on
    ``planted_channel`` has amplitude ``delta_gain``. Nothing else differs, so the answer key is the
    single unit (planted_channel, delta). Returns (data (n_channels, n_samples), labels per epoch).
    Arbitrary units; not physiological.
    """
    rng = np.random.default_rng(seed)
    win = int(round(window_s * sampling_rate_hz))
    t = np.arange(win) / sampling_rate_hz
    labels = np.array([0] * n_epochs_per_class + [1] * n_epochs_per_class)
    chunks = []
    for lab in labels:
        ep = rng.standard_normal((n_channels, win))
        for ch in range(n_channels):
            amp = delta_gain if (lab == 1 and ch == planted_channel) else 1.0
            f, ph = rng.uniform(1.5, 2.5), rng.uniform(0, 2 * np.pi)
            ep[ch] += amp * np.sin(2 * np.pi * f * t + ph)
        chunks.append(ep)
    return np.concatenate(chunks, axis=1), labels


def _cohens_d(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Standardized mean difference (b - a) / pooled SD, along axis 0."""
    na, nb = len(a), len(b)
    pooled = np.sqrt(((na - 1) * a.var(axis=0, ddof=1) + (nb - 1) * b.var(axis=0, ddof=1)) / (na + nb - 2))
    return (b.mean(axis=0) - a.mean(axis=0)) / pooled


def check_metrics_shared(sampling_rate_hz: float = 256.0) -> None:
    """Stage 3 check: analytic sanity of the features, then recovery of a planted mechanism."""
    sf = sampling_rate_hz
    bands, spectral = BandConfig(), SpectralConfig()  # PROVISIONAL defaults

    # (a) analytic: a bin-centred 10 Hz sine of amplitude a has power a^2/2, all inside alpha
    t = np.arange(512) / sf
    a = 3.0
    tone = recording_from_array(np.vstack([a * np.sin(2 * np.pi * 10.0 * t), np.zeros(512)]), sf, ["S", "Z"])
    ft = compute_epoch_features(epoch_recording(tone, EpochConfig(window_s=2.0)), bands, spectral)
    ci, bi = ft.unit_index("S", "alpha")
    assert np.isclose(10 ** ft.log_band_power[0, ci, bi], a**2 / 2, rtol=1e-6), 10 ** ft.log_band_power[0, ci, bi]
    others = np.delete(10 ** ft.log_band_power[0, ci], bi)
    assert np.all(others < 1e-6 * a**2), others
    # flat channel -> finite log floor, not -inf; zero line length
    assert np.all(np.isfinite(ft.log_band_power)) and ft.line_length[0, 1] == 0.0
    # line length of a ramp with slope c per sample is exactly (n - 1) * c
    ramp = recording_from_array(np.arange(512, dtype=float)[None] * 0.5, sf, ["R"])
    assert compute_epoch_features(epoch_recording(ramp, EpochConfig(window_s=2.0))).line_length[0, 0] == 511 * 0.5
    # a band with no bin, and a band above Nyquist, are refused
    for bad in ({"tiny": (1.1, 1.2)}, {"high": (100.0, 200.0)}):
        try:
            compute_epoch_features(epoch_recording(tone, EpochConfig(window_s=2.0)), BandConfig(bad))
        except ValueError:
            pass
        else:
            raise AssertionError(f"band {bad} was not refused")
    print(f"[smoke] metrics: 10 Hz sine a={a} -> alpha power {10 ** ft.log_band_power[0, ci, bi]:.4f} "
          f"(expected {a**2 / 2}); ramp line length exact")

    # (b) planted mechanism: delta amplitude raised on channel 2 only
    names = ["C0", "C1", "C2", "C3"]
    planted_ch, planted_band = "C2", "delta"
    data, labels = make_planted_delta_recording(n_channels=4, planted_channel=2, sampling_rate_hz=sf)
    rec = recording_from_array(data, sf, names)
    feats = compute_epoch_features(epoch_recording(rec, EpochConfig(window_s=2.0)), bands, spectral)
    assert feats.log_band_power.shape == (80, 4, len(bands.names))
    assert feats.line_length.shape == (80, 4)

    ctrl, seiz = labels == 0, labels == 1
    d_lbp = _cohens_d(feats.log_band_power[ctrl], feats.log_band_power[seiz])  # (n_ch, n_bands)
    ci, bi = feats.unit_index(planted_ch, planted_band)
    assert d_lbp[ci, bi] > SMOKE_TEST_ONLY_PLANTED_MIN_D, d_lbp[ci, bi]
    mask = np.ones_like(d_lbp, dtype=bool)
    mask[ci, bi] = False
    assert np.all(np.abs(d_lbp[mask]) < SMOKE_TEST_ONLY_UNPLANTED_MAX_ABS_D), d_lbp
    top = np.unravel_index(np.argmax(np.abs(d_lbp)), d_lbp.shape)
    assert (feats.channel_names[top[0]], feats.band_names[top[1]]) == (planted_ch, planted_band)

    # line length sum|x[k]-x[k-1]| is weighted towards high frequencies (the differencing filter's
    # gain ~ 2 sin(pi f / fs)), so a slow 2 Hz delta change is buried under the white-noise floor
    # and must NOT register on any channel. This documents a real blind spot of the feature for
    # slow-wave mechanisms; it is why band power, not line length, carries the channel x band unit.
    d_ll = _cohens_d(feats.line_length[ctrl], feats.line_length[seiz])
    assert np.all(np.abs(d_ll) < SMOKE_TEST_ONLY_UNPLANTED_MAX_ABS_D), d_ll

    # ...whereas a planted broadband amplitude change on one channel does show in line length there only
    bb = data.copy()
    win = int(round(2.0 * sf))
    bb[ci, 40 * win:] *= 2.0  # seizure-class epochs, channel C2 only
    feats_bb = compute_epoch_features(
        epoch_recording(recording_from_array(bb, sf, names), EpochConfig(window_s=2.0)), bands, spectral)
    d_ll_bb = _cohens_d(feats_bb.line_length[ctrl], feats_bb.line_length[seiz])
    assert d_ll_bb[ci] > SMOKE_TEST_ONLY_PLANTED_MIN_D, d_ll_bb
    assert np.all(np.abs(np.delete(d_ll_bb, ci)) < SMOKE_TEST_ONLY_UNPLANTED_MAX_ABS_D), d_ll_bb

    # class-averaged phenotypes agree with the per-epoch features
    ph = extract_baseline_phenotypes(feats, labels)
    assert ph.n_epochs == {0: 40, 1: 40}
    assert np.allclose(ph.log_band_power_mean[1] - ph.log_band_power_mean[0],
                       feats.log_band_power[seiz].mean(0) - feats.log_band_power[ctrl].mean(0))

    # determinism: identical input -> bit-identical features
    again = compute_epoch_features(epoch_recording(rec, EpochConfig(window_s=2.0)), bands, spectral)
    assert np.array_equal(again.log_band_power, feats.log_band_power)
    assert np.array_equal(again.line_length, feats.line_length)

    print(f"[smoke] metrics: planted ({planted_ch}, {planted_band}) d={d_lbp[ci, bi]:.2f}; "
          f"max |d| elsewhere={np.abs(d_lbp[mask]).max():.2f}; line length d on {planted_ch}="
          f"{d_ll[ci]:.2f} (blind to slow delta, by design); broadband x2 on {planted_ch} -> line "
          f"length d={d_ll_bb[ci]:.2f}, max |d| elsewhere={np.abs(np.delete(d_ll_bb, ci)).max():.2f}")
    print("[smoke] d (rows=channels, cols=" + ",".join(feats.band_names) + "):\n"
          + np.array2string(d_lbp, precision=2, suppress_small=True))


def main() -> None:
    check_signal_ingest()
    check_metrics_shared()
    epoch = make_synthetic_epoch()
    print(f"[smoke] synthetic epoch shape: {epoch.shape}")
    print(
        "[smoke] STOPPING HERE — downstream stages after metrics (hotspot ranking, perturbation panel, "
        "comparison, interpretation) are not yet implemented. See src/core/*.py TODOs and "
        "business/bp_v0.md's milestone table."
    )


if __name__ == "__main__":
    main()
