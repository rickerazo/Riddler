"""Layer 1 (platform core) — feature/phenotype extraction shared across all modalities.

Analog of GeoBind's core energy-proxy metrics (src/phenotypes.py, src/energy_proxies.py):
interface-agnostic phenotype computation run identically on baseline and perturbed signals
(pipeline stages 3 and 8 both call into this module — same code, different input).

See ARCHITECTURE.md, pipeline stages 3 and 8.

Features (per epoch)
--------------------
* ``log_band_power`` — (n_epochs, n_channels, n_bands). For each channel×band unit: the power
  spectral density (one-sided, ``scaling="density"``, Hann window) integrated over the band's
  frequency bins, then ``log10``. Units: log10(signal_unit^2), i.e. log10(V^2) for EDF input.
* ``line_length`` — (n_epochs, n_channels). ``sum(|x[k] - x[k-1]|)`` over the epoch, in signal
  units (Esteller et al. 2001 line-length feature). Not normalized by epoch length, so it is only
  comparable between epochs of the same window length; the window is recorded on the result.

Provisional values (flagged, not settled)
-----------------------------------------
Everything in :class:`BandConfig` / :class:`SpectralConfig` is a **provisional** config value,
not a cited or calibrated one (ROADMAP.md "Open decisions"):

* band edges: the conventional clinical-EEG delta/theta/alpha/beta/gamma split. Exact edges vary
  across the literature (e.g. delta lower edge 0.5 vs 1 Hz; alpha/beta at 12 vs 13 Hz; gamma upper
  edge anywhere from 45 to 100+ Hz). Nothing here has been checked against Track A yet.
* Welch segment length: ``None`` = a single Hann-windowed periodogram over the whole epoch. With
  the provisional 2 s epoch this gives 0.5 Hz resolution, the coarsest that still resolves the
  delta band's lower edge.
* ``log_floor``: power floor applied before ``log10`` so an all-zero channel (flat line) yields a
  finite value instead of ``-inf``. It is a numerical guard, not a physiological value.

Band membership is half-open, ``lo <= f < hi``. Every band must contain at least one frequency bin
and lie below Nyquist, otherwise extraction raises instead of returning an empty or truncated band.

No quantization happens here: nothing is persisted. Quantize-on-persist applies where feature
artifacts are written (ARCHITECTURE.md reproducibility policy; precision still undecided).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import welch

from src.core.signal_ingest import EpochedRecording

# PROVISIONAL band edges in Hz (half-open [lo, hi)). Conventional split, not yet grounded in a
# cited source (Track A). Override via BandConfig(bands=...).
PROVISIONAL_BANDS_HZ: dict[str, tuple[float, float]] = {
    "delta": (0.5, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0),
    "gamma": (30.0, 45.0),
}

# PROVISIONAL numerical guard before log10 (signal_unit^2). Not a physiological value.
PROVISIONAL_LOG_FLOOR = 1e-30


@dataclass
class BandConfig:
    """Named frequency bands, ``{name: (lo_hz, hi_hz)}``, half-open. Default is PROVISIONAL."""

    bands: dict[str, tuple[float, float]] = field(
        default_factory=lambda: dict(PROVISIONAL_BANDS_HZ)
    )

    def __post_init__(self) -> None:
        if not self.bands:
            raise ValueError("BandConfig.bands is empty")
        for name, (lo, hi) in self.bands.items():
            if not (0 <= lo < hi):
                raise ValueError(f"band {name!r}: need 0 <= lo < hi, got ({lo}, {hi})")

    @property
    def names(self) -> list[str]:
        return list(self.bands)


@dataclass
class SpectralConfig:
    """PSD estimation options. All defaults PROVISIONAL (see module doc).

    welch_segment_s: Welch segment length in seconds; ``None`` = whole epoch (one periodogram).
    welch_overlap:   fraction of a segment shared with the next, in [0, 1).
    log_floor:       power floor applied before log10.
    """

    welch_segment_s: float | None = None
    welch_overlap: float = 0.5
    log_floor: float = PROVISIONAL_LOG_FLOOR

    def __post_init__(self) -> None:
        if self.welch_segment_s is not None and self.welch_segment_s <= 0:
            raise ValueError(f"welch_segment_s must be > 0, got {self.welch_segment_s}")
        if not (0 <= self.welch_overlap < 1):
            raise ValueError(f"welch_overlap must be in [0, 1), got {self.welch_overlap}")
        if self.log_floor <= 0:
            raise ValueError(f"log_floor must be > 0, got {self.log_floor}")


@dataclass
class EpochFeatures:
    """Per-epoch features for one EpochedRecording. Arrays are float64, not quantized.

    log_band_power: (n_epochs, n_channels, n_bands)
    line_length:    (n_epochs, n_channels)
    start_samples:  (n_epochs,) copied from the EpochedRecording (stable identity key)
    """

    log_band_power: np.ndarray
    line_length: np.ndarray
    start_samples: np.ndarray
    channel_names: list[str]
    band_names: list[str]
    sampling_rate_hz: float
    window_s: float
    band_config: BandConfig
    spectral_config: SpectralConfig

    def unit_index(self, channel: str, band: str) -> tuple[int, int]:
        """(channel index, band index) of a channel×band unit."""
        return self.channel_names.index(channel), self.band_names.index(band)


def _psd(data: np.ndarray, sfreq: float, cfg: SpectralConfig) -> tuple[np.ndarray, np.ndarray]:
    """One-sided density PSD along the last axis. Returns (freqs, psd)."""
    n = data.shape[-1]
    if cfg.welch_segment_s is None:
        nperseg = n
    else:
        nperseg = int(round(cfg.welch_segment_s * sfreq))
        if not (1 <= nperseg <= n):
            raise ValueError(
                f"welch_segment_s={cfg.welch_segment_s} s -> {nperseg} samples; epoch has {n}"
            )
    noverlap = int(np.floor(cfg.welch_overlap * nperseg)) if nperseg < n else 0
    return welch(
        data, fs=sfreq, window="hann", nperseg=nperseg, noverlap=noverlap,
        detrend="constant", scaling="density", axis=-1,
    )


def band_masks(freqs: np.ndarray, bands: BandConfig, sfreq: float) -> np.ndarray:
    """(n_bands, n_freqs) boolean masks, half-open [lo, hi). Raises on empty / supra-Nyquist bands."""
    nyq = sfreq / 2
    masks = []
    for name, (lo, hi) in bands.bands.items():
        if hi > nyq:
            raise ValueError(f"band {name!r} upper edge {hi} Hz exceeds Nyquist {nyq} Hz")
        m = (freqs >= lo) & (freqs < hi)
        if not m.any():
            df = freqs[1] - freqs[0] if freqs.size > 1 else float("nan")
            raise ValueError(
                f"band {name!r} [{lo}, {hi}) Hz contains no frequency bin (resolution {df} Hz); "
                "use a longer epoch / Welch segment or a wider band"
            )
        masks.append(m)
    return np.array(masks)


def log_band_power(
    data: np.ndarray, sfreq: float, bands: BandConfig, spectral: SpectralConfig
) -> np.ndarray:
    """log10 band power for ``data`` (..., n_samples) -> (..., n_bands)."""
    freqs, psd = _psd(data, sfreq, spectral)
    df = freqs[1] - freqs[0]
    masks = band_masks(freqs, bands, sfreq).astype(psd.dtype)  # (n_bands, n_freqs)
    power = psd @ masks.T * df  # (..., n_bands)
    return np.log10(np.maximum(power, spectral.log_floor))


def line_length(data: np.ndarray) -> np.ndarray:
    """Line length ``sum(|diff|)`` along the last axis -> data.shape[:-1]."""
    return np.abs(np.diff(data, axis=-1)).sum(axis=-1)


def compute_epoch_features(
    epoched: EpochedRecording,
    bands: BandConfig | None = None,
    spectral: SpectralConfig | None = None,
) -> EpochFeatures:
    """Compute log band power per channel×band and line length per channel, for every epoch."""
    bands = bands or BandConfig()
    spectral = spectral or SpectralConfig()
    sfreq = epoched.sampling_rate_hz
    n_ep, n_ch, _ = epoched.data.shape
    if n_ep == 0:
        lbp = np.empty((0, n_ch, len(bands.bands)))
        # still validate bands against this sampling rate / window
        freqs, _ = _psd(np.zeros((1, epoched.data.shape[2])), sfreq, spectral)
        band_masks(freqs, bands, sfreq)
    else:
        lbp = log_band_power(epoched.data, sfreq, bands, spectral)
    return EpochFeatures(
        log_band_power=lbp,
        line_length=line_length(epoched.data),
        start_samples=epoched.start_samples.copy(),
        channel_names=list(epoched.channel_names),
        band_names=bands.names,
        sampling_rate_hz=sfreq,
        window_s=epoched.config.window_s,
        band_config=bands,
        spectral_config=spectral,
    )


@dataclass
class ClassPhenotypes:
    """Class-averaged features. Keys are the class labels, sorted.

    log_band_power_mean/std: {label: (n_channels, n_bands)}
    line_length_mean/std:    {label: (n_channels,)}
    n_epochs:                {label: int}
    std is the sample standard deviation (ddof=1); NaN when a class has a single epoch.
    """

    log_band_power_mean: dict
    log_band_power_std: dict
    line_length_mean: dict
    line_length_std: dict
    n_epochs: dict
    channel_names: list[str]
    band_names: list[str]


def extract_baseline_phenotypes(features: EpochFeatures, labels) -> ClassPhenotypes:
    """Class-averaged baseline phenotypes per channel×band unit (ARCHITECTURE.md stage 3).

    ``labels`` is one label per epoch (any hashable, sortable values). Averaging only; ranking
    units by class-discriminative effect size is hotspot detection (stage 4), not done here.
    """
    labels = np.asarray(labels)
    if labels.shape != (features.log_band_power.shape[0],):
        raise ValueError(f"need one label per epoch: {labels.shape} vs {features.log_band_power.shape[0]} epochs")
    out = {k: {} for k in ("lbp_m", "lbp_s", "ll_m", "ll_s", "n")}
    for lab in sorted(set(labels.tolist())):
        sel = labels == lab
        n = int(sel.sum())
        lbp, ll = features.log_band_power[sel], features.line_length[sel]
        out["lbp_m"][lab] = lbp.mean(axis=0)
        out["ll_m"][lab] = ll.mean(axis=0)
        out["lbp_s"][lab] = lbp.std(axis=0, ddof=1) if n > 1 else np.full(lbp.shape[1:], np.nan)
        out["ll_s"][lab] = ll.std(axis=0, ddof=1) if n > 1 else np.full(ll.shape[1:], np.nan)
        out["n"][lab] = n
    return ClassPhenotypes(
        log_band_power_mean=out["lbp_m"], log_band_power_std=out["lbp_s"],
        line_length_mean=out["ll_m"], line_length_std=out["ll_s"], n_epochs=out["n"],
        channel_names=list(features.channel_names), band_names=list(features.band_names),
    )
