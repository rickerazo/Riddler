#!/usr/bin/env python3
"""End-to-end pipeline smoke test on a synthetic, in-memory EEG epoch.

Analog of GeoBind's src/run_pp_smoke_test.py / run_pl_smoke_test.py: proves the pipeline's
plumbing is correct (ingest -> hotspot ranking -> perturbation panel -> comparison ->
interpretation) on synthetic data that needs no downloaded dataset file, BEFORE wiring in
CHB-MIT. Not a scientific result — a wiring check, exactly like GeoBind's smoke tests.

STATUS: partially runnable. Stage 1 (src/core/signal_ingest.py: in-memory ingest, duplicate-
channel handling, epoching) is checked by check_signal_ingest(); stage 3 (src/core/metrics_shared.py:
log band power per channel x band, line length, class-averaged phenotypes) is checked by
check_metrics_shared() against a planted mechanism; stage 7 (src/core/perturbation_execution.py:
the 4 provisional perturbation classes, seeded, quantize-on-persist) is checked by
check_perturbation_execution() on the same planted-delta generator; stage 9
(src/core/compare.py: signed deltas + baseline-normalized disruption, adjacent-band spillover as a
separate off-target column) is checked by check_compare(); stage 4 (src/core/hotspot_detection.py:
Cohen's-d ranking with PROVISIONAL weights + cross-shaped neighborhood exclusion, no cutoff) is
checked by check_hotspot_detection(). Every other stage (the perturbation_design.py table builder,
interpret_mechanism_profiles.py) is still a stub that raises NotImplementedError; the test stops
cleanly after those checks. Stages are filled in
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


# SMOKE_TEST_ONLY tolerances for the stage-7 check (log10 band-power units). They bound what the
# Hann-windowed feature reads back from a rectangular-window in-band perturbation on synthetic data;
# they are not thresholds for real data or for interpretation.
SMOKE_TEST_ONLY_ATTENUATION_TOL = 0.02     # per-epoch |delta log power - 2*log10(gain)|
SMOKE_TEST_ONLY_POWER_PRESERVED_TOL = 0.1  # |mean delta log power| for phase scramble / jitter
SMOKE_TEST_ONLY_SCRAMBLED_MAX_CORR = 0.5   # mean corr(original, scrambled) of the in-band component


def _inband(x: np.ndarray, sf: float, band: tuple[float, float]) -> np.ndarray:
    """Rectangular-window rfft bins of x inside [lo, hi), over the last axis."""
    f = np.fft.rfftfreq(x.shape[-1], d=1.0 / sf)
    return np.fft.rfft(x, axis=-1)[..., (f >= band[0]) & (f < band[1])]


def check_perturbation_execution(sampling_rate_hz: float = 256.0) -> None:
    """Stage 7 check on the planted-delta generator: each class does what its hypothesis says, at
    the target unit only, and the same seed gives bit-identical output (in memory and on disk)."""
    import dataclasses
    import hashlib
    import tempfile
    from pathlib import Path

    from src.core.perturbation_design import CANDIDATE_PANEL, PerturbationClass
    from src.core.perturbation_execution import (
        PROVISIONAL_QUANTIZATION_STEP,
        PerturbationConfig,
        apply_perturbation,
        load_perturbed_signal,
        persist_perturbed_signal,
    )

    sf = sampling_rate_hz
    names = ["C0", "C1", "C2", "C3"]
    data, _labels = make_planted_delta_recording(n_channels=4, planted_channel=2, sampling_rate_hz=sf)
    ep = epoch_recording(recording_from_array(data, sf, names), EpochConfig(window_s=2.0))
    bands = BandConfig()
    target_ch, target_band = 2, "delta"
    band_hz = bands.bands[target_band]
    cfg = PerturbationConfig()  # PROVISIONAL strengths
    base = compute_epoch_features(ep, bands)
    ci, bi = base.unit_index(names[target_ch], target_band)
    far_bands = [b for b in range(len(bands.names)) if bands.names[b] not in (target_band, "theta")]
    snapshot = ep.data.copy()

    def run(pclass, seed=7):
        res = apply_perturbation(ep.data, sf, pclass, target_ch, band_hz, seed=seed, config=cfg)
        feats = compute_epoch_features(dataclasses.replace(ep, data=res.data), bands)
        return res, feats.log_band_power - base.log_band_power

    results = {}
    for spec in CANDIDATE_PANEL:
        res, dlog = run(spec)
        results[spec.perturbation_class] = (res, dlog)
        assert res.record["perturbation_class"] == spec.perturbation_class.value
        assert res.record["provisional"] is True
        # target unit only: other channels bit-identical, out-of-band bins unchanged, far bands untouched
        assert np.array_equal(np.delete(res.data, target_ch, axis=1), np.delete(ep.data, target_ch, axis=1))
        f = np.fft.rfftfreq(ep.data.shape[-1], d=1.0 / sf)
        oob = ~((f >= band_hz[0]) & (f < band_hz[1]))
        assert np.allclose(np.fft.rfft(res.data[:, target_ch])[:, oob],
                           np.fft.rfft(ep.data[:, target_ch])[:, oob], rtol=0, atol=1e-9)
        assert np.abs(dlog[:, ci, far_bands]).max() < 1e-9, spec.perturbation_class
    assert np.array_equal(ep.data, snapshot), "apply_perturbation mutated its input"

    orig_ib = _inband(ep.data[:, target_ch], sf, band_hz)
    p0 = np.sum(np.abs(orig_ib) ** 2, axis=-1)

    # (a) amplitude attenuation: C2-delta log power drops by 2*log10(gain)
    res, dlog = results[PerturbationClass.AMPLITUDE_ATTENUATION]
    expected = 2 * np.log10(cfg.attenuation_gain)
    assert np.all(np.abs(dlog[:, ci, bi] - expected) < SMOKE_TEST_ONLY_ATTENUATION_TOL), dlog[:, ci, bi]
    p1 = np.sum(np.abs(_inband(res.data[:, target_ch], sf, band_hz)) ** 2, axis=-1)
    assert np.allclose(p1, cfg.attenuation_gain**2 * p0, rtol=1e-9)
    att = dlog[:, ci, bi]

    # (b) phase scramble: C2-delta power preserved, waveform changed
    res, dlog = results[PerturbationClass.PHASE_SCRAMBLE]
    ps_ib = _inband(res.data[:, target_ch], sf, band_hz)
    assert np.allclose(np.abs(ps_ib), np.abs(orig_ib), rtol=1e-9, atol=1e-9)  # exact magnitudes
    assert abs(dlog[:, ci, bi].mean()) < SMOKE_TEST_ONLY_POWER_PRESERVED_TOL, dlog[:, ci, bi].mean()
    # waveform: correlate the in-band time-domain components, epoch by epoch
    def inband_wave(x):
        X = np.fft.rfft(x, axis=-1)
        X[..., oob] = 0
        return np.fft.irfft(X, n=x.shape[-1], axis=-1)
    w0, w1 = inband_wave(ep.data[:, target_ch]), inband_wave(res.data[:, target_ch])
    corr = np.array([np.corrcoef(a, b)[0, 1] for a, b in zip(w0, w1)])
    assert corr.mean() < SMOKE_TEST_ONLY_SCRAMBLED_MAX_CORR, corr.mean()
    assert not np.allclose(res.data[:, target_ch], ep.data[:, target_ch])
    ps = dlog[:, ci, bi]

    # (c) temporal jitter: power preserved, timing moved within +/- jitter_max_s
    res, dlog = results[PerturbationClass.TEMPORAL_JITTER]
    assert np.allclose(np.abs(_inband(res.data[:, target_ch], sf, band_hz)), np.abs(orig_ib), rtol=1e-9, atol=1e-9)
    assert abs(dlog[:, ci, bi].mean()) < SMOKE_TEST_ONLY_POWER_PRESERVED_TOL
    assert np.all(np.abs(res.record["params"]["jitter_s"]) <= cfg.jitter_max_s)
    assert not np.allclose(res.data[:, target_ch], ep.data[:, target_ch])
    jt = dlog[:, ci, bi]

    # (d) structured noise: injected in-band noise power equals in-band signal power / 10^(snr/10)
    res, dlog = results[PerturbationClass.STRUCTURED_NOISE_INJECTION]
    added = _inband(res.data[:, target_ch] - ep.data[:, target_ch], sf, band_hz)
    assert np.allclose(np.sum(np.abs(added) ** 2, axis=-1), p0 / 10 ** (cfg.noise_snr_db / 10), rtol=1e-9)
    assert dlog[:, ci, bi].mean() > 0
    ni = dlog[:, ci, bi]

    # (e) determinism: same seed -> bit-identical; different seed -> different (stochastic classes)
    for pclass in PerturbationClass:
        a = apply_perturbation(ep.data, sf, pclass, target_ch, band_hz, seed=7, config=cfg).data
        b = apply_perturbation(ep.data, sf, pclass, target_ch, band_hz, seed=7, config=cfg).data
        c = apply_perturbation(ep.data, sf, pclass, target_ch, band_hz, seed=8, config=cfg).data
        assert np.array_equal(a, b), pclass
        assert np.array_equal(a, results[pclass][0].data), pclass
        if pclass is PerturbationClass.AMPLITUDE_ATTENUATION:
            assert np.array_equal(a, c)  # deterministic lever, seed-independent
        else:
            assert not np.array_equal(a, c), pclass

    # (f) quantize on persist: byte-identical files for identical input, round trip within step/2
    step = PROVISIONAL_QUANTIZATION_STEP
    with tempfile.TemporaryDirectory() as tmp:
        digests = []
        for k in range(2):
            res = apply_perturbation(ep.data, sf, PerturbationClass.PHASE_SCRAMBLE, target_ch, band_hz,
                                     seed=7, config=cfg)
            stem = Path(tmp) / f"run{k}" / "C2_delta_phase_scramble"
            persist_perturbed_signal(res, stem, step)
            digests.append(tuple(hashlib.sha256(stem.with_suffix(s).read_bytes()).hexdigest()
                                 for s in (".npy", ".json")))
        assert digests[0] == digests[1], digests
        back, meta = load_perturbed_signal(stem)
        assert meta["quantization_step"] == step and meta["quantization_step_provisional"] is True
        assert np.max(np.abs(back - res.data)) <= step / 2 * (1 + 1e-6)

    # (g) channel_dropout is not built (rubric open item) and must be refused, not guessed
    try:
        apply_perturbation(ep.data, sf, "channel_dropout", target_ch, band_hz, seed=7)
    except ValueError:
        pass
    else:
        raise AssertionError("channel_dropout was accepted; it must stay unbuilt until Track A")

    th = bands.names.index("theta")
    print(f"[smoke] perturb: amplitude x{cfg.attenuation_gain} on ({names[target_ch]}, {target_band}) -> "
          f"d log10 P = {att.mean():.4f} (expected {expected:.4f}; range {att.min():.4f}..{att.max():.4f})")
    print(f"[smoke] perturb: phase scramble -> d log10 P mean {ps.mean():+.4f} (SD {ps.std():.3f}; "
          f"rectangular-window power exact), in-band waveform corr mean {corr.mean():.3f}")
    print(f"[smoke] perturb: jitter (+/-{cfg.jitter_max_s} s) -> d log10 P mean {jt.mean():+.4f}; "
          f"noise @ {cfg.noise_snr_db} dB SNR -> d log10 P mean {ni.mean():+.4f} "
          f"(expected ~{np.log10(1 + 10 ** (-cfg.noise_snr_db / 10)):.4f})")
    print("[smoke] perturb: Hann-leakage spillover into adjacent (C2, theta), mean d log10 P: "
          + ", ".join(f"{p.value}={results[p][1][:, ci, th].mean():+.3f}" for p in PerturbationClass))
    print(f"[smoke] perturb: same seed bit-identical (memory + persisted files, sha256 "
          f"{digests[0][0][:12]}...); quantization step {step} (PROVISIONAL)")


# SMOKE_TEST_ONLY bound for the stage-9 check: |normalized disruption| a power-preserving perturbation
# may leave at the target unit (units of that unit's baseline SD) on synthetic data. Not an
# interpretation threshold (no tau_* value) and never used on real data.
SMOKE_TEST_ONLY_POWER_PRESERVED_MAX_NORM = 0.25
# Float round-off bound for same-channel, non-adjacent bands (rfft -> irfft round trip).
SMOKE_TEST_ONLY_ROUNDOFF_MAX_NORM = 1e-6


def check_compare(sampling_rate_hz: float = 256.0) -> None:
    """Stage 9 check on the planted-delta generator, perturbing (C2, delta) with the full panel.

    Asserts: attenuation's largest normalized disruption is at (C2, delta); phase scramble leaves
    the target near zero; adjacent-band (C2, theta) Hann-leakage spillover is reported in its own
    column, not in the target score; off-target channels are exactly 0 and same-channel far bands
    see only rfft/irfft round-off (not exactly 0); the output is deterministic; and mismatched
    features are refused.
    """
    import dataclasses

    from src.core.compare import (
        RELATION_ADJACENT,
        RELATION_OTHER_CHANNEL,
        RELATION_TARGET,
        NormalizerConfig,
        adjacent_bands,
        compute_disruption_score_normalized,
    )
    from src.core.perturbation_design import CANDIDATE_PANEL, PerturbationClass
    from src.core.perturbation_execution import apply_perturbation

    sf = sampling_rate_hz
    names = ["C0", "C1", "C2", "C3"]
    data, labels = make_planted_delta_recording(n_channels=4, planted_channel=2, sampling_rate_hz=sf)
    ep = epoch_recording(recording_from_array(data, sf, names), EpochConfig(window_s=2.0))
    bands = BandConfig()
    target = ("C2", "delta")
    base = compute_epoch_features(ep, bands)
    ci, bi = base.unit_index(*target)
    th = bands.names.index("theta")
    assert adjacent_bands(bands, "delta") == ["theta"]  # from band edges, not names/order
    assert adjacent_bands(bands, "alpha") == ["theta", "beta"]

    def run(spec, normalizer=None, mask=None):
        res = apply_perturbation(ep.data, sf, spec, ci, bands.bands[target[1]], seed=7)
        pert = compute_epoch_features(dataclasses.replace(ep, data=res.data), bands)
        return compute_disruption_score_normalized(base, pert, target, normalizer, mask, record=res.record)

    out = {spec.perturbation_class: run(spec) for spec in CANDIDATE_PANEL}
    for pclass, c in out.items():
        assert c.relation[ci, bi] == RELATION_TARGET and c.relation[ci, th] == RELATION_ADJACENT
        assert c.target_disruption_score_normalized == c.disruption_score_normalized[ci, bi]
        # in-band, single-channel perturbation: other channels exactly untouched; far bands on the
        # target channel only see rfft/irfft round-off
        assert np.all(c.disruption_score_normalized[c.relation == RELATION_OTHER_CHANNEL] == 0.0), pclass
        assert c.offtarget_other_max_disruption_normalized < SMOKE_TEST_ONLY_ROUNDOFF_MAX_NORM, pclass
        assert not c.degenerate_units
        s = c.summary()
        assert s["perturbation_class"] == pclass.value and s["normalizer_provisional"] is True
        # the separate off-target column IS the adjacent unit, and is not folded into the target score
        assert s["offtarget_adjacent_band_max_disruption_normalized"] == c.disruption_score_normalized[ci, th]
        assert s["target_disruption_score_normalized"] == abs(c.delta_mean[ci, bi] / c.baseline_spread[ci, bi])

    # (a) attenuation: largest normalized disruption anywhere is the target unit; direction negative
    att = out[PerturbationClass.AMPLITUDE_ATTENUATION]
    top = np.unravel_index(np.nanargmax(att.disruption_score_normalized), att.disruption_score_normalized.shape)
    assert (names[top[0]], bands.names[top[1]]) == target, top
    assert att.target_normalized_delta < 0
    assert att.target_disruption_score_normalized > att.offtarget_adjacent_band_max_disruption_normalized

    # (b) phase scramble: power-preserving, so the target score stays near zero
    ps = out[PerturbationClass.PHASE_SCRAMBLE]
    assert ps.target_disruption_score_normalized < SMOKE_TEST_ONLY_POWER_PRESERVED_MAX_NORM, ps.summary()
    assert ps.target_disruption_score_normalized < att.target_disruption_score_normalized
    jt = out[PerturbationClass.TEMPORAL_JITTER]
    assert jt.target_disruption_score_normalized < SMOKE_TEST_ONLY_POWER_PRESERVED_MAX_NORM, jt.summary()

    # (c) determinism: identical inputs -> bit-identical arrays and identical canonical rows
    again = run(CANDIDATE_PANEL[0])
    for name in ("delta_mean", "delta_sd", "baseline_spread", "normalized_delta", "disruption_score_normalized"):
        assert np.array_equal(getattr(again, name), getattr(att, name), equal_nan=True), name
    assert again.to_rows() == att.to_rows() and again.summary() == att.summary()
    assert [(r["channel"], r["band"]) for r in att.to_rows()] == [(c, b) for c in names for b in bands.names]

    # (d) refuse mismatched features (different epochs) rather than compare them
    shifted = dataclasses.replace(base, start_samples=base.start_samples + 1)
    try:
        compute_disruption_score_normalized(base, shifted, target)
    except ValueError:
        pass
    else:
        raise AssertionError("features from different epochs were compared")

    # (e) degenerate spread -> NaN + listed, never a made-up floor
    flat = dataclasses.replace(base, log_band_power=base.log_band_power.copy())
    flat.log_band_power[:, 0, :] = -30.0
    c_flat = compute_disruption_score_normalized(flat, flat, target)
    assert np.all(np.isnan(c_flat.normalized_delta[0])) and len(c_flat.degenerate_units) == len(bands.names)

    # (f) normalizer sensitivity (PROVISIONAL choice): report, don't hide. Control-only spread excludes
    #     the planted class difference, so the C2-delta SD is far smaller and every score scales up.
    ctrl = run(CANDIDATE_PANEL[0], mask=labels == 0)
    ps_ctrl = run(CANDIDATE_PANEL[1], mask=labels == 0)
    mad = run(CANDIDATE_PANEL[0], normalizer=NormalizerConfig(method="mad"))

    def fmt(c):
        return (f"target {c.target_disruption_score_normalized:.3f} "
                f"(signed {c.target_normalized_delta:+.3f}), adjacent-band spillover "
                f"{c.offtarget_adjacent_band_max_disruption_normalized:.3f}")
    for pclass, c in out.items():
        print(f"[smoke] compare: {pclass.value:<27} on {target}: {fmt(c)}")
    far = max(c.offtarget_other_max_disruption_normalized for c in out.values())
    print(f"[smoke] compare: other channels exactly 0; same-channel far bands max {far:.1e} (round-off); "
          f"output bit-identical on rerun")
    print(f"[smoke] compare: normalizer is PROVISIONAL (std, ddof=1, all epochs): C2-delta spread "
          f"{att.baseline_spread[ci, bi]:.3f}; control-only {ctrl.baseline_spread[ci, bi]:.3f} -> attenuation "
          f"{ctrl.target_disruption_score_normalized:.2f}, phase scramble {ps_ctrl.target_disruption_score_normalized:.2f}; "
          f"MAD -> attenuation {mad.target_disruption_score_normalized:.2f}")


def check_hotspot_detection(sampling_rate_hz: float = 256.0) -> None:
    """Stage 4 check on the planted-delta generator.

    Asserts: (C2, delta) is rank 1 with the expected sign; the effect size matches stage 3's d; every
    unit is accounted for (selected / suppressed / degenerate) with no cutoff applied; the ranking is
    bit-identical on rerun; neighborhood exclusion removes exactly the spectral (+ spatial, when an
    adjacency is supplied) neighbors of a selected unit, and does so even when a neighbor outranks a
    non-neighbor; degenerate units are listed, not ranked; bad inputs are refused.
    """
    import dataclasses

    from src.core.compare import adjacent_bands
    from src.core.hotspot_detection import (
        PROVISIONAL_RANKING_WEIGHTS,
        STATUS_SELECTED,
        NeighborhoodConfig,
        RankingWeights,
        rank_hotspots,
    )

    sf = sampling_rate_hz
    names = ["C0", "C1", "C2", "C3"]
    data, labels = make_planted_delta_recording(n_channels=4, planted_channel=2, sampling_rate_hz=sf)
    ep = epoch_recording(recording_from_array(data, sf, names), EpochConfig(window_s=2.0))
    bands = BandConfig()
    feats = compute_epoch_features(ep, bands)
    n_units = len(names) * len(bands.names)
    ci, bi = feats.unit_index("C2", "delta")

    # (a) default config: spectral exclusion only (core knows no montage)
    r = rank_hotspots(feats, labels, positive_label=1)
    assert (r.top.channel, r.top.band, r.top.rank) == ("C2", "delta", 1), r.top
    assert r.top.effect_size_signed > 0 and r.reference_label == 0
    d_ref = _cohens_d(feats.log_band_power[labels == 0], feats.log_band_power[labels == 1])
    assert np.allclose(r.effect_size_log_band_power, d_ref, rtol=1e-12)
    assert r.weights.provisional and r.neighborhood.provisional
    assert r.weights.as_dict() == PROVISIONAL_RANKING_WEIGHTS
    # no cutoff: every unit lands in exactly one bucket; nothing is dropped for being "too small"
    assert len(r.selected) + len(r.suppressed) + len(r.degenerate_units) == n_units
    assert not r.degenerate_units
    assert [u.rank for u in r.selected] == list(range(1, len(r.selected) + 1))
    scores = [u.rank_score for u in r.selected]
    assert scores == sorted(scores, reverse=True)
    # spectral neighbor of the top unit (C2, theta) is suppressed by it; nothing else is
    sup = {(u.channel, u.band): u.suppressed_by for u in r.suppressed}
    assert sup.get(("C2", "theta")) == ("C2", "delta"), sup
    # any suppressed unit is a 1-hop band neighbor, same channel, of a selected unit that outranks it
    sel_rank = {(u.channel, u.band): u.rank_score for u in r.selected}
    for u in r.suppressed:
        sch, sbd = u.suppressed_by
        assert sch == u.channel and u.band in adjacent_bands(bands, sbd)
        assert sel_rank[u.suppressed_by] >= u.rank_score

    # (b) determinism: bit-identical arrays, identical canonical rows
    again = rank_hotspots(feats, labels, positive_label=1)
    assert np.array_equal(again.rank_score, r.rank_score) and again.to_rows() == r.to_rows()
    assert [(u.channel, u.band) for u in again.selected] == [(u.channel, u.band) for u in r.selected]

    # (c) radius 0 on both axes -> no exclusion: selected == plain descending |d| sort
    r0 = rank_hotspots(feats, labels, 1, neighborhood=NeighborhoodConfig(0, 0))
    assert not r0.suppressed and len(r0.selected) == n_units
    flat_order = sorted(((c, b) for c in range(len(names)) for b in range(len(bands.names))),
                        key=lambda u: (-abs(d_ref[u]), u[0], u[1]))
    assert [(u.channel_index, u.band_index) for u in r0.selected] == flat_order

    # (d) spatial exclusion with a caller-supplied (modality-owned) chain C0-C1-C2-C3
    chain = {"C0": ["C1"], "C1": ["C2"], "C2": ["C3"]}
    rs = rank_hotspots(feats, labels, 1, neighborhood=NeighborhoodConfig(channel_adjacency=chain))
    sup_s = {(u.channel, u.band): u.suppressed_by for u in rs.suppressed}
    for nb in [("C2", "theta"), ("C1", "delta"), ("C3", "delta")]:
        assert sup_s.get(nb) == ("C2", "delta"), (nb, sup_s)
    assert ("C0", "delta") not in sup_s or sup_s[("C0", "delta")] != ("C2", "delta")  # 2 hops away
    assert ("C1", "theta") not in sup_s or sup_s[("C1", "theta")] != ("C2", "delta")  # diagonal: not a neighbor

    # (e) exclusion bites when a neighbor outranks a non-neighbor: add a class shift to (C2, theta)
    #     (~6 SD, smaller than the ~18 SD delta plant) and a smaller one (~3 SD) to (C0, beta)
    lbp = feats.log_band_power.copy()
    th, be = bands.names.index("theta"), bands.names.index("beta")
    lbp[labels == 1, ci, th] += 6.0 * lbp[:, ci, th].std(ddof=1)
    lbp[labels == 1, 0, be] += 3.0 * lbp[:, 0, be].std(ddof=1)
    f2 = dataclasses.replace(feats, log_band_power=lbp)
    raw = rank_hotspots(f2, labels, 1, neighborhood=NeighborhoodConfig(0, 0))
    assert [(u.channel, u.band) for u in raw.selected[:3]] == [("C2", "delta"), ("C2", "theta"), ("C0", "beta")]
    ex = rank_hotspots(f2, labels, 1)
    assert [(u.channel, u.band) for u in ex.selected[:2]] == [("C2", "delta"), ("C0", "beta")]
    assert {(u.channel, u.band): u.suppressed_by for u in ex.suppressed}[("C2", "theta")] == ("C2", "delta")

    # (f) degenerate: a flat channel has zero pooled SD -> NaN, listed, not ranked; no epsilon floor
    flat = dataclasses.replace(feats, log_band_power=feats.log_band_power.copy())
    flat.log_band_power[:, 0, :] = -30.0
    rf = rank_hotspots(flat, labels, 1)
    assert sorted(rf.degenerate_units) == sorted(("C0", b) for b in bands.names)
    assert all(row["status"] != STATUS_SELECTED for row in rf.to_rows() if row["channel"] == "C0")
    assert rf.top.channel == "C2" and rf.top.band == "delta"

    # (g) refusals: wrong label count, >2 classes, unknown positive label, unknown adjacency channel,
    #     all-zero weights, negative radius
    bad_calls = [
        lambda: rank_hotspots(feats, labels[:-1], 1),
        lambda: rank_hotspots(feats, np.arange(len(labels)) % 3, 1),
        lambda: rank_hotspots(feats, labels, 5),
        lambda: rank_hotspots(feats, labels, 1, neighborhood=NeighborhoodConfig(channel_adjacency={"Cz": ["C0"]})),
        lambda: RankingWeights(0.0, 0.0),
        lambda: NeighborhoodConfig(spectral_radius_bands=-1),
    ]
    for i, call in enumerate(bad_calls):
        try:
            call()
        except ValueError:
            pass
        else:
            raise AssertionError(f"bad input #{i} was not refused")

    top5 = ", ".join(f"{u.rank}:({u.channel},{u.band}) d={u.effect_size_signed:+.2f}" for u in r.selected[:5])
    print(f"[smoke] hotspots: weights PROVISIONAL {r.weights.as_dict()}, spectral radius "
          f"{r.neighborhood.spectral_radius_bands}, no spatial adjacency in core; top 5 of "
          f"{len(r.selected)} selected: {top5}")
    print(f"[smoke] hotspots: suppressed {sorted(sup.items())}; rerun bit-identical; no cutoff "
          f"({len(r.selected)} selected + {len(r.suppressed)} suppressed = {n_units} units)")
    print(f"[smoke] hotspots: with chain adjacency, (C2,delta) suppresses "
          f"{sorted(k for k, v in sup_s.items() if v == ('C2', 'delta'))}; planted (C2,theta) +6 SD is "
          f"raw rank 2 but excluded -> rank 2 becomes {ex.selected[1].channel, ex.selected[1].band}")



def main() -> None:
    check_signal_ingest()
    check_metrics_shared()
    check_perturbation_execution()
    check_compare()
    check_hotspot_detection()
    epoch = make_synthetic_epoch()
    print(f"[smoke] synthetic epoch shape: {epoch.shape}")
    print(
        "[smoke] STOPPING HERE — remaining stages (perturbation design table, "
        "interpretation) are not yet implemented. See src/core/*.py TODOs and "
        "business/bp_v0.md's milestone table."
    )


if __name__ == "__main__":
    main()
