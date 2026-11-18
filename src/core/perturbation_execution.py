"""Layer 1 (platform core) — deterministic perturbed-signal generation.

Analog of GeoBind's src/mutate.py: apply one perturbation (src/core/perturbation_design.py) to
baseline EEG epochs at one hotspot (a channel x band unit) and return the perturbed epochs,
deterministically given a seed. Persisting quantizes at a fixed, recorded step to kill
floating-point jitter across runs (GeoBind's analog: coordinates rounded to 0.1 A at write time).

See ARCHITECTURE.md, pipeline stage 7, and the "Determinism over cleverness" non-negotiable in
CLAUDE.md. The panel itself is defined by mechanism_aware_interpretation_rubric.md (PROVISIONAL).

How every perturbation is applied
---------------------------------
Input is any array whose last axis is time and whose second-to-last axis is channel, e.g. one
epoch (n_channels, n_samples) or an epoched stack (n_epochs, n_channels, n_samples). Each selected
row (one epoch of one target channel) is handled independently:

1. ``X = rfft(x)`` over the whole row (rectangular window; the row is treated as one period).
2. The band's bins are the rfft bins with ``lo <= f < hi``. This is the same half-open rule as
   ``metrics_shared.band_masks``, so the perturbed band is the band the features measure.
3. Only those bins change. Out-of-band content and untargeted channels come back bit-identical.
4. ``irfft`` back to the time domain at the original length.

The four classes (rubric panel; ``channel_dropout`` deliberately NOT built, rubric open item):

* ``amplitude_attenuation``: in-band bins x ``attenuation_gain``. In-band power scales by
  ``gain**2`` exactly in the rectangular-window sense, i.e. a ``2*log10(gain)`` shift in log10
  band power (the Hann-windowed feature sees slightly less, from leakage at the band edges).
* ``phase_scramble``: each in-band bin's phase is replaced by an independent uniform phase in
  [0, 2*pi); magnitudes are kept (Fourier phase-randomized surrogate, Theiler et al. 1992 style,
  restricted to one band). Power spectrum preserved exactly (rectangular window); waveform changed.
* ``temporal_jitter``: the in-band component is circularly delayed by ``tau`` seconds, applied as a
  phase ramp ``exp(-2j*pi*f*tau)``; ``tau`` is drawn per row, uniform in
  ``[-jitter_max_s, +jitter_max_s]``. Magnitudes and the relative-phase structure across
  frequencies (the waveform shape) are preserved; only the timing relative to the rest of the
  signal (other bands, other channels) moves.
* ``structured_noise_injection``: Gaussian noise band-limited to ``noise_band_hz`` (default: the
  hotspot band), scaled per row so that in-band signal power / in-band noise power equals
  ``noise_snr_db`` (rectangular-window power, computed on the unperturbed row). Expected in-band
  power rises by ``1 + 10**(-snr_db/10)``. A row whose in-band power is exactly 0 gets no noise
  (SNR undefined), and this is recorded rather than hidden.

DC and Nyquist bins are real for a real signal, so they cannot take an arbitrary phase.
``phase_scramble`` and ``temporal_jitter`` leave them untouched if a band contains them;
``amplitude_attenuation`` and noise injection treat them like any other bin.

Determinism
-----------
All randomness comes from ``numpy.random.default_rng(seed)``, drawn in a fixed order (selected
rows in C order: leading axes, then the listed channels in the order given). NumPy's pocketfft is
deterministic, so the same input, spec, config and seed give bit-identical output on the same
platform/NumPy build. Bit-identity across different machines or NumPy versions is NOT claimed;
that is what the quantize-on-persist step and the reproducibility audit (stage 8 of ROADMAP
Phase 1) are for.

Provisional values (flagged, not settled)
-----------------------------------------
Everything in :class:`PerturbationConfig` and :data:`PROVISIONAL_QUANTIZATION_STEP` is a
**provisional** config value (ROADMAP.md "Open decisions", "perturbation strengths" and
"quantization precision"), not a cited or calibrated one:

* ``attenuation_gain = 0.5``: halves in-band amplitude (-6 dB). Same value as the
  ``outputs/exploration`` perturbation demo; arbitrary.
* ``jitter_max_s = 0.1``: the rubric requires a jitter window justified from the seizure-
  detection literature (Track A). 0.1 s is a placeholder, not that justification.
* ``noise_snr_db = 0.0``: equal in-band signal and noise power. Placeholder pending the EEG
  artifact/noise literature (Track A item 3).
* ``noise_band_hz = None``: noise confined to the hotspot band. An EMG-like (high-frequency) or
  blink-like (low-frequency) profile would be a different, literature-grounded band choice.
* Quantization step ``1e-9`` signal units (1 nV for EDF input in volts). Reasoning: CHB-MIT EDF
  channels are 12-bit over +/-800 uV (checked on chb01_03.edf header: digital -2048..2047), an
  ADC step of 1600 uV / 4095 ~= 0.39 uV, so 1 nV is ~390x finer than the recording's own
  resolution and loses nothing measurable. It is a decision for this first pass, not a validated
  standard; the reproducibility audit is where it gets tested.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

from src.core.perturbation_design import PerturbationClass, PerturbationSpec

# PROVISIONAL perturbation strengths. See module docstring. Override via PerturbationConfig(...).
PROVISIONAL_ATTENUATION_GAIN = 0.5
PROVISIONAL_JITTER_MAX_S = 0.1
PROVISIONAL_NOISE_SNR_DB = 0.0

# PROVISIONAL quantize-on-persist step, in signal units (1 nV for volts). See module docstring.
PROVISIONAL_QUANTIZATION_STEP = 1e-9

PERSIST_FORMAT_VERSION = 1


@dataclass(frozen=True)
class PerturbationConfig:
    """Strength parameters for the provisional panel. All defaults are PROVISIONAL."""

    attenuation_gain: float = PROVISIONAL_ATTENUATION_GAIN
    jitter_max_s: float = PROVISIONAL_JITTER_MAX_S
    noise_snr_db: float = PROVISIONAL_NOISE_SNR_DB
    noise_band_hz: tuple[float, float] | None = None  # None = the hotspot band

    def __post_init__(self) -> None:
        if not (0.0 <= self.attenuation_gain):
            raise ValueError(f"attenuation_gain must be >= 0, got {self.attenuation_gain}")
        if not (self.jitter_max_s > 0.0):
            raise ValueError(f"jitter_max_s must be > 0, got {self.jitter_max_s}")
        if not np.isfinite(self.noise_snr_db):
            raise ValueError(f"noise_snr_db must be finite, got {self.noise_snr_db}")
        if self.noise_band_hz is not None:
            lo, hi = self.noise_band_hz
            if not (0 <= lo < hi):
                raise ValueError(f"noise_band_hz: need 0 <= lo < hi, got {self.noise_band_hz}")


@dataclass
class PerturbedSignal:
    """Result of one perturbation.

    data:   same shape as the input, float64, NOT yet quantized (quantization happens on persist).
    record: JSON-serializable provenance (class, mode, hypothesis, target, seed, parameters,
            ``provisional: True``), the row for a perturbation/run manifest (ARCHITECTURE stage 6).
    """

    data: np.ndarray
    record: dict = field(default_factory=dict)


def _band_bins(n_samples: int, sfreq: float, band_hz: tuple[float, float]) -> np.ndarray:
    """Boolean mask over rfft bins with lo <= f < hi (same rule as metrics_shared.band_masks)."""
    lo, hi = band_hz
    if not (0 <= lo < hi):
        raise ValueError(f"band: need 0 <= lo < hi, got {band_hz}")
    if lo >= sfreq / 2:
        raise ValueError(f"band {band_hz} lies at or above Nyquist ({sfreq / 2} Hz)")
    freqs = np.fft.rfftfreq(n_samples, d=1.0 / sfreq)
    mask = (freqs >= lo) & (freqs < hi)
    if not mask.any():
        raise ValueError(
            f"band {band_hz} contains no frequency bin at {n_samples} samples / {sfreq} Hz "
            f"(resolution {sfreq / n_samples} Hz)"
        )
    return mask


def _phase_mutable(mask: np.ndarray, n_samples: int) -> np.ndarray:
    """Drop DC and (for even n) the Nyquist bin, which must stay real."""
    m = mask.copy()
    m[0] = False
    if n_samples % 2 == 0:
        m[-1] = False
    return m


def _resolve_class(spec: PerturbationSpec | PerturbationClass | str) -> tuple[PerturbationClass, dict]:
    if isinstance(spec, PerturbationSpec):
        tags = {
            "perturbation_mode": spec.perturbation_mode.value,
            "perturbation_class": spec.perturbation_class.value,
            "mechanistic_hypothesis": spec.mechanistic_hypothesis,
        }
        return spec.perturbation_class, tags
    pc = PerturbationClass(spec)  # raises ValueError on unknown names, incl. "channel_dropout"
    return pc, {"perturbation_mode": None, "perturbation_class": pc.value, "mechanistic_hypothesis": None}


def apply_perturbation(
    data: np.ndarray,
    sampling_rate_hz: float,
    spec: PerturbationSpec | PerturbationClass | str,
    channel_indices: int | Sequence[int],
    band_hz: tuple[float, float],
    seed: int,
    config: PerturbationConfig | None = None,
) -> PerturbedSignal:
    """Apply one perturbation to ``band_hz`` on ``channel_indices``; return the perturbed copy.

    ``data`` has time on the last axis and channels on the second-to-last, e.g. (n_channels,
    n_samples) or (n_epochs, n_channels, n_samples). Each (epoch, channel) row is perturbed
    independently over its full length. The input is never modified. ``seed`` is required (no
    default) so an unseeded call can't happen by accident. See the module docstring for what each
    class does and which values are provisional.
    """
    cfg = config or PerturbationConfig()
    pclass, tags = _resolve_class(spec)
    x = np.asarray(data, dtype=np.float64)
    if x.ndim < 2:
        raise ValueError(f"data must be at least 2-D (channels, samples), got shape {x.shape}")
    if not np.all(np.isfinite(x)):
        raise ValueError("data contains non-finite values")
    n_ch, n = x.shape[-2], x.shape[-1]
    chans = [int(channel_indices)] if np.isscalar(channel_indices) else [int(c) for c in channel_indices]
    if not chans or len(set(chans)) != len(chans) or any(c < 0 or c >= n_ch for c in chans):
        raise ValueError(f"channel_indices {chans} invalid for {n_ch} channels (need unique, in range)")
    sfreq = float(sampling_rate_hz)
    band = (float(band_hz[0]), float(band_hz[1]))
    mask = _band_bins(n, sfreq, band)
    freqs = np.fft.rfftfreq(n, d=1.0 / sfreq)

    out = x.copy()
    rows = out[..., chans, :].reshape(-1, n)  # (n_rows, n), C order: leading axes, then chans
    spec_rows = np.fft.rfft(rows, axis=-1)
    rng = np.random.default_rng(seed)
    params: dict = {}
    n_rows = rows.shape[0]

    if pclass is PerturbationClass.AMPLITUDE_ATTENUATION:
        spec_rows[:, mask] *= cfg.attenuation_gain
        params["attenuation_gain"] = cfg.attenuation_gain

    elif pclass is PerturbationClass.PHASE_SCRAMBLE:
        pm = _phase_mutable(mask, n)
        if not pm.any():
            raise ValueError(f"band {band} has no bin whose phase can change (only DC/Nyquist)")
        phases = rng.uniform(0.0, 2 * np.pi, size=(n_rows, int(pm.sum())))
        spec_rows[:, pm] = np.abs(spec_rows[:, pm]) * np.exp(1j * phases)

    elif pclass is PerturbationClass.TEMPORAL_JITTER:
        pm = _phase_mutable(mask, n)
        if not pm.any():
            raise ValueError(f"band {band} has no bin whose phase can change (only DC/Nyquist)")
        tau = rng.uniform(-cfg.jitter_max_s, cfg.jitter_max_s, size=n_rows)
        spec_rows[:, pm] *= np.exp(-2j * np.pi * freqs[pm][None, :] * tau[:, None])
        params["jitter_max_s"] = cfg.jitter_max_s
        params["jitter_s"] = tau.tolist()

    elif pclass is PerturbationClass.STRUCTURED_NOISE_INJECTION:
        nb = cfg.noise_band_hz if cfg.noise_band_hz is not None else band
        nmask = _band_bins(n, sfreq, nb)
        noise = np.fft.rfft(rng.standard_normal((n_rows, n)), axis=-1)
        noise[:, ~nmask] = 0.0
        # rectangular-window in-band power (Parseval up to a common constant, which cancels)
        p_sig = np.sum(np.abs(spec_rows[:, mask]) ** 2, axis=-1)
        p_noise = np.sum(np.abs(noise[:, mask]) ** 2, axis=-1)
        target = p_sig / 10 ** (cfg.noise_snr_db / 10)
        with np.errstate(divide="ignore", invalid="ignore"):
            scale = np.where((p_sig > 0) & (p_noise > 0), np.sqrt(target / p_noise), 0.0)
        spec_rows += noise * scale[:, None]
        params.update(noise_snr_db=cfg.noise_snr_db, noise_band_hz=list(nb),
                      n_rows_without_noise=int(np.sum(scale == 0.0)))

    else:  # pragma: no cover - PerturbationClass has exactly the four members above
        raise ValueError(f"unsupported perturbation_class {pclass!r}")

    new_rows = np.fft.irfft(spec_rows, n=n, axis=-1)
    out[..., chans, :] = new_rows.reshape(out[..., chans, :].shape)

    record = {
        **tags,
        "channel_indices": chans,
        "band_hz": list(band),
        "sampling_rate_hz": sfreq,
        "seed": int(seed),
        "input_shape": list(x.shape),
        "params": params,
        "provisional": True,
        "provisional_note": "panel + strengths provisional; see mechanism_aware_interpretation_rubric.md",
    }
    return PerturbedSignal(out, record)


# ---------------------------------------------------------------------------------------------
# Quantize on persist
# ---------------------------------------------------------------------------------------------


def quantize(data: np.ndarray, step: float = PROVISIONAL_QUANTIZATION_STEP) -> np.ndarray:
    """Round to integer multiples of ``step`` and return the integer counts (int64).

    Counts, not rounded floats, are what get persisted: integers are exact, so the artifact can't
    pick up float jitter on write or read. Refuses values whose count would overflow int64.
    """
    if not step > 0:
        raise ValueError(f"quantization step must be > 0, got {step}")
    scaled = np.asarray(data, dtype=np.float64) / step
    if not np.all(np.isfinite(scaled)) or np.any(np.abs(scaled) >= 2.0**62):
        raise ValueError("values non-finite or too large to quantize at this step")
    return np.rint(scaled).astype(np.int64)


def dequantize(counts: np.ndarray, step: float = PROVISIONAL_QUANTIZATION_STEP) -> np.ndarray:
    return np.asarray(counts, dtype=np.int64).astype(np.float64) * step


def persist_perturbed_signal(
    result: PerturbedSignal, out_stem: Path | str, step: float = PROVISIONAL_QUANTIZATION_STEP
) -> dict:
    """Write ``<stem>.npy`` (int64 counts) and ``<stem>.json`` (provenance); return the JSON dict.

    ``.npy`` + sorted-key JSON rather than ``.npz``: ``np.savez`` stamps the write time into the zip
    member headers, so two identical saves would hash differently. Both files written here are
    byte-identical for identical input. The JSON records the step and the counts' sha256.
    """
    stem = Path(out_stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    counts = np.ascontiguousarray(quantize(result.data, step))
    np.save(stem.with_suffix(".npy"), counts, allow_pickle=False)
    meta = {
        "format_version": PERSIST_FORMAT_VERSION,
        "quantization_step": step,
        "quantization_step_provisional": True,
        "dtype": "int64_counts",
        "shape": list(counts.shape),
        "counts_sha256": hashlib.sha256(counts.tobytes()).hexdigest(),
        "perturbation": result.record,
    }
    stem.with_suffix(".json").write_text(json.dumps(meta, sort_keys=True, indent=2) + "\n")
    return meta


def load_perturbed_signal(out_stem: Path | str) -> tuple[np.ndarray, dict]:
    """Read back a persisted perturbation: (dequantized float64 data, provenance dict)."""
    stem = Path(out_stem)
    meta = json.loads(stem.with_suffix(".json").read_text())
    counts = np.load(stem.with_suffix(".npy"), allow_pickle=False)
    if hashlib.sha256(np.ascontiguousarray(counts).tobytes()).hexdigest() != meta["counts_sha256"]:
        raise ValueError(f"{stem}.npy does not match the sha256 recorded in {stem}.json")
    return dequantize(counts, meta["quantization_step"]), meta


__all__ = [
    "PROVISIONAL_ATTENUATION_GAIN",
    "PROVISIONAL_JITTER_MAX_S",
    "PROVISIONAL_NOISE_SNR_DB",
    "PROVISIONAL_QUANTIZATION_STEP",
    "PerturbationConfig",
    "PerturbedSignal",
    "apply_perturbation",
    "dequantize",
    "load_perturbed_signal",
    "persist_perturbed_signal",
    "quantize",
]
