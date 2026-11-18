"""Layer 1 (platform core) — baseline-vs-perturbed comparison.

Analog of GeoBind's src/compare.py: signed per-epoch feature deltas between baseline and perturbed
signals, plus a disruption score per channel×band unit that is **baseline-normalized from day one**.

CRITICAL (GeoBind lesson, see CLAUDE.md's "baseline-normalize comparability from day one"): raw
disruption magnitudes are NOT comparable across hotspots without normalizing by each hotspot's own
baseline. This module exposes ONLY the normalized score. There is no un-normalized score here; the
raw signed deltas are returned as deltas, never as a "score".

See ARCHITECTURE.md, pipeline stage 9.

What is computed
----------------
Inputs are two :class:`~src.core.metrics_shared.EpochFeatures` computed by the same code on the
same epochs (stage 3 on baseline, stage 8 on the perturbed copy), plus the target unit the
perturbation was applied to.

* **Signed deltas** (:func:`compute_signed_deltas`): ``perturbed - baseline`` per epoch, for
  ``log_band_power`` (n_epochs, n_channels, n_bands) and ``line_length`` (n_epochs, n_channels).
  The sign is the feature's own direction (negative = feature went down), NOT re-oriented to
  "positive = more disruptive": for log band power an increase (noise) and a decrease
  (attenuation) are both disruptive, so a sign flip would throw information away.
* **Normalized disruption** (:func:`compute_disruption_score_normalized`), per channel×band unit::

      normalized_delta[u]            = mean_epochs(delta[u]) / baseline_spread[u]
      disruption_score_normalized[u] = |normalized_delta[u]|

  i.e. the mean shift of that unit's log band power, in units of that unit's own baseline
  spread across epochs (a Glass's-delta-style standardization). Using the *mean* signed shift
  (not the mean of |delta|) is deliberate: a perturbation that only reshuffles a unit's power
  epoch to epoch without moving its level (phase scramble under a Hann window) scores near zero.

Off-target spillover is a separate column, never folded into the target score
-----------------------------------------------------------------------------
Perturbations edit rectangular-window rfft bins (perturbation_execution.py); the feature reads a
Hann-windowed PSD. Hann leakage therefore moves the *adjacent* band on the same channel a little
(e.g. C2-theta under a C2-delta perturbation; see HANDOFF 2026-11-17). Each unit is labelled with
its ``relation`` to the target:

* ``target``                          the perturbed channel×band unit;
* ``adjacent_band_same_channel``      same channel, a band sharing an edge with the target band
                                      (computed from the BandConfig edges, not from band names or order);
* ``other_band_same_channel``         same channel, non-adjacent band;
* ``other_channel``                   any band on an unperturbed channel.

:class:`ComparisonResult` reports ``target_disruption_score_normalized`` (the target unit only) and,
as separate fields, ``offtarget_adjacent_band_max_disruption_normalized`` /
``offtarget_other_max_disruption_normalized``. Nothing in this module adds them together. Whether
and how spillover should discount a mechanism call is interpretation logic (stage 13) and is not
decided here.

Provisional values (flagged, not settled)
-----------------------------------------
* **Normalizer choice** (:class:`NormalizerConfig`): ``"std"`` = sample SD (ddof=1) of the unit's
  baseline log band power across the baseline epochs passed in. PROVISIONAL. Open sub-choices:
  - which epochs define "baseline spread": all epochs passed in (default) vs. one class only vs.
    within-class pooled SD. On a two-class recording the all-epochs SD includes the class
    difference itself, which inflates the spread of a class-discriminative unit and so *shrinks*
    its normalized score. Pass ``spread_epoch_mask`` to restrict it;
  - SD vs. a robust scale (``"mad"``: 1.4826 × median absolute deviation, offered as an
    alternative, not calibrated);
  - whether the normalizer should be the unit's spread at all, versus its class-discriminative
    effect size (GeoBind's "baseline engagement").
  None of these is grounded in literature or in real CHB-MIT distributions yet.
* **Degenerate spread**: a unit whose baseline spread is exactly 0 (e.g. a flat channel at the log
  floor) gets ``NaN`` normalized values and is listed in ``degenerate_units``; no floor/epsilon is
  invented to make it finite.
* **Composite score**: GeoBind combines several metrics with named weights. Here only one feature
  (log band power) is defined per channel×band unit, so the "composite" is that single feature and
  no weights are introduced. Line length is per *channel*, not per unit; its signed delta is
  returned but kept out of the unit score until a weighting is documented.
* **No quantization**: nothing is persisted here. Feature-array quantization precision is still an
  open decision (ARCHITECTURE.md). :meth:`ComparisonResult.to_rows` gives a canonical,
  stably-sorted (channel index, band index) row list for whoever persists it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from src.core.metrics_shared import BandConfig, EpochFeatures

# PROVISIONAL normalizer. See module docstring.
PROVISIONAL_NORMALIZER_METHOD = "std"
PROVISIONAL_NORMALIZER_DDOF = 1
_MAD_TO_SD = 1.4826  # consistency constant: MAD -> SD for a normal distribution (standard, not tuned)

RELATION_TARGET = "target"
RELATION_ADJACENT = "adjacent_band_same_channel"
RELATION_OTHER_BAND = "other_band_same_channel"
RELATION_OTHER_CHANNEL = "other_channel"


@dataclass(frozen=True)
class NormalizerConfig:
    """How each unit's baseline spread is measured. Defaults are PROVISIONAL (see module doc).

    method: ``"std"`` (sample SD with ``ddof``) or ``"mad"`` (1.4826 × median absolute deviation).
    ddof:   delta degrees of freedom for ``"std"``.
    """

    method: Literal["std", "mad"] = PROVISIONAL_NORMALIZER_METHOD
    ddof: int = PROVISIONAL_NORMALIZER_DDOF

    def __post_init__(self) -> None:
        if self.method not in ("std", "mad"):
            raise ValueError(f"NormalizerConfig.method must be 'std' or 'mad', got {self.method!r}")
        if self.ddof < 0:
            raise ValueError(f"ddof must be >= 0, got {self.ddof}")


@dataclass
class SignedDeltas:
    """Per-epoch ``perturbed - baseline`` feature deltas (float64, unrounded).

    log_band_power: (n_epochs, n_channels, n_bands)
    line_length:    (n_epochs, n_channels)
    """

    log_band_power: np.ndarray
    line_length: np.ndarray
    channel_names: list[str]
    band_names: list[str]
    start_samples: np.ndarray


@dataclass
class ComparisonResult:
    """Baseline-vs-perturbed comparison for ONE perturbation at ONE target unit.

    Per-unit arrays are (n_channels, n_bands):
      delta_mean, delta_sd           mean / SD (ddof=1) over epochs of the signed log-power delta
      baseline_spread                the normalizer, per unit
      normalized_delta               delta_mean / baseline_spread (signed)
      disruption_score_normalized    |normalized_delta|
      relation                       str array, see module docstring
    """

    deltas: SignedDeltas
    target: tuple[int, int]
    delta_mean: np.ndarray
    delta_sd: np.ndarray
    baseline_spread: np.ndarray
    normalized_delta: np.ndarray
    disruption_score_normalized: np.ndarray
    relation: np.ndarray
    degenerate_units: list[tuple[str, str]]
    normalizer: NormalizerConfig
    n_spread_epochs: int
    record: dict = field(default_factory=dict)

    @property
    def target_name(self) -> tuple[str, str]:
        ci, bi = self.target
        return self.deltas.channel_names[ci], self.deltas.band_names[bi]

    @property
    def target_disruption_score_normalized(self) -> float:
        return float(self.disruption_score_normalized[self.target])

    @property
    def target_normalized_delta(self) -> float:
        return float(self.normalized_delta[self.target])

    def _max_over(self, rel: str) -> float:
        sel = self.relation == rel
        vals = self.disruption_score_normalized[sel]
        vals = vals[np.isfinite(vals)]
        return float(vals.max()) if vals.size else float("nan")

    @property
    def offtarget_adjacent_band_max_disruption_normalized(self) -> float:
        """Max normalized disruption over same-channel bands adjacent to the target band (Hann
        leakage spillover). NaN if the target band has no adjacent band. Separate from the target score."""
        return self._max_over(RELATION_ADJACENT)

    @property
    def offtarget_other_max_disruption_normalized(self) -> float:
        """Max normalized disruption over every non-target, non-adjacent unit (should be ~0 for an
        in-band, single-channel perturbation)."""
        a, b = self._max_over(RELATION_OTHER_BAND), self._max_over(RELATION_OTHER_CHANNEL)
        finite = [v for v in (a, b) if np.isfinite(v)]
        return max(finite) if finite else float("nan")

    def summary(self) -> dict:
        """One flat row for a ranked batch summary (stage 10). Target and off-target are separate keys."""
        ch, bd = self.target_name
        return {
            **{k: self.record.get(k) for k in ("perturbation_class", "perturbation_mode", "mechanistic_hypothesis", "seed")},
            "target_channel": ch,
            "target_band": bd,
            "target_delta_mean": float(self.delta_mean[self.target]),
            "target_normalized_delta": self.target_normalized_delta,
            "target_disruption_score_normalized": self.target_disruption_score_normalized,
            "offtarget_adjacent_band_max_disruption_normalized": self.offtarget_adjacent_band_max_disruption_normalized,
            "offtarget_other_max_disruption_normalized": self.offtarget_other_max_disruption_normalized,
            "normalizer_method": self.normalizer.method,
            "normalizer_provisional": True,
            "n_spread_epochs": self.n_spread_epochs,
            "n_degenerate_units": len(self.degenerate_units),
        }

    def to_rows(self) -> list[dict]:
        """Canonical per-unit rows, sorted by (channel index, band index), for persistence/auditing."""
        rows = []
        for ci, ch in enumerate(self.deltas.channel_names):
            for bi, bd in enumerate(self.deltas.band_names):
                rows.append({
                    "channel": ch,
                    "band": bd,
                    "relation": str(self.relation[ci, bi]),
                    "delta_mean": float(self.delta_mean[ci, bi]),
                    "delta_sd": float(self.delta_sd[ci, bi]),
                    "baseline_spread": float(self.baseline_spread[ci, bi]),
                    "normalized_delta": float(self.normalized_delta[ci, bi]),
                    "disruption_score_normalized": float(self.disruption_score_normalized[ci, bi]),
                })
        return rows


def _check_paired(baseline: EpochFeatures, perturbed: EpochFeatures) -> None:
    if baseline.channel_names != perturbed.channel_names:
        raise ValueError("baseline and perturbed features have different channels")
    if baseline.band_names != perturbed.band_names:
        raise ValueError("baseline and perturbed features have different bands")
    if baseline.band_config.bands != perturbed.band_config.bands:
        raise ValueError("baseline and perturbed features used different band edges")
    if baseline.spectral_config != perturbed.spectral_config:
        raise ValueError("baseline and perturbed features used different spectral configs")
    if baseline.sampling_rate_hz != perturbed.sampling_rate_hz or baseline.window_s != perturbed.window_s:
        raise ValueError("baseline and perturbed features differ in sampling rate or window")
    if not np.array_equal(baseline.start_samples, perturbed.start_samples):
        raise ValueError("baseline and perturbed features are not the same epochs (start_samples differ)")


def compute_signed_deltas(baseline: EpochFeatures, perturbed: EpochFeatures) -> SignedDeltas:
    """Per-epoch ``perturbed - baseline`` deltas, paired epoch by epoch.

    Refuses to compare features that aren't from the same epochs, channels, bands and spectral
    settings, since a delta between mismatched features would be meaningless.
    """
    _check_paired(baseline, perturbed)
    return SignedDeltas(
        log_band_power=perturbed.log_band_power - baseline.log_band_power,
        line_length=perturbed.line_length - baseline.line_length,
        channel_names=list(baseline.channel_names),
        band_names=list(baseline.band_names),
        start_samples=baseline.start_samples.copy(),
    )


def adjacent_bands(bands: BandConfig, band: str) -> list[str]:
    """Bands sharing an edge with ``band`` (one's ``hi`` equals the other's ``lo``), in config order."""
    lo, hi = bands.bands[band]
    return [n for n, (l2, h2) in bands.bands.items() if n != band and (l2 == hi or h2 == lo)]


def unit_relations(
    channel_names: list[str], bands: BandConfig, target: tuple[int, int]
) -> np.ndarray:
    """(n_channels, n_bands) array of relation labels w.r.t. the target unit."""
    ci, bi = target
    names = bands.names
    adj = set(adjacent_bands(bands, names[bi]))
    rel = np.full((len(channel_names), len(names)), RELATION_OTHER_CHANNEL, dtype=object)
    for b, n in enumerate(names):
        rel[ci, b] = RELATION_ADJACENT if n in adj else RELATION_OTHER_BAND
    rel[ci, bi] = RELATION_TARGET
    return rel


def baseline_spread(values: np.ndarray, normalizer: NormalizerConfig) -> np.ndarray:
    """Spread over axis 0 (epochs) per the normalizer config."""
    if normalizer.method == "std":
        if values.shape[0] <= normalizer.ddof:
            raise ValueError(f"need > {normalizer.ddof} epochs for std with ddof={normalizer.ddof}")
        return values.std(axis=0, ddof=normalizer.ddof)
    if values.shape[0] < 1:
        raise ValueError("need >= 1 epoch for mad")
    med = np.median(values, axis=0)
    return _MAD_TO_SD * np.median(np.abs(values - med), axis=0)


def compute_disruption_score_normalized(
    baseline: EpochFeatures,
    perturbed: EpochFeatures,
    target: tuple[str, str] | tuple[int, int],
    normalizer: NormalizerConfig | None = None,
    spread_epoch_mask: np.ndarray | None = None,
    record: dict | None = None,
) -> ComparisonResult:
    """Signed deltas + baseline-normalized disruption per channel×band unit for one perturbation.

    ``target`` is the perturbed unit, as (channel name, band name) or (channel index, band index).
    ``spread_epoch_mask`` (bool, one per epoch) restricts which *baseline* epochs define each unit's
    spread; the delta mean is always over all epochs passed in. ``record`` is the perturbation's
    provenance (``PerturbedSignal.record``), carried into :meth:`ComparisonResult.summary`.
    This is the ONLY disruption score the module exposes; see the module docstring for what is
    provisional (the normalizer above all).
    """
    norm = normalizer or NormalizerConfig()
    deltas = compute_signed_deltas(baseline, perturbed)
    if isinstance(target[0], str):
        tgt = baseline.unit_index(str(target[0]), str(target[1]))
    else:
        tgt = (int(target[0]), int(target[1]))
        if not (0 <= tgt[0] < len(deltas.channel_names) and 0 <= tgt[1] < len(deltas.band_names)):
            raise ValueError(f"target {tgt} out of range")

    base = baseline.log_band_power
    if spread_epoch_mask is not None:
        m = np.asarray(spread_epoch_mask, dtype=bool)
        if m.shape != (base.shape[0],):
            raise ValueError(f"spread_epoch_mask must have shape ({base.shape[0]},), got {m.shape}")
        base = base[m]
    spread = baseline_spread(base, norm)

    d = deltas.log_band_power
    if d.shape[0] < 2:
        raise ValueError("need >= 2 epochs to compare")
    delta_mean = d.mean(axis=0)
    delta_sd = d.std(axis=0, ddof=1)
    degenerate = spread == 0
    with np.errstate(divide="ignore", invalid="ignore"):
        nd = np.where(degenerate, np.nan, delta_mean / np.where(degenerate, 1.0, spread))

    rel = unit_relations(deltas.channel_names, baseline.band_config, tgt)
    return ComparisonResult(
        deltas=deltas,
        target=tgt,
        delta_mean=delta_mean,
        delta_sd=delta_sd,
        baseline_spread=spread,
        normalized_delta=nd,
        disruption_score_normalized=np.abs(nd),
        relation=rel,
        degenerate_units=[(deltas.channel_names[c], deltas.band_names[b]) for c, b in zip(*np.nonzero(degenerate))],
        normalizer=norm,
        n_spread_epochs=int(base.shape[0]),
        record=dict(record or {}),
    )


__all__ = [
    "PROVISIONAL_NORMALIZER_DDOF",
    "PROVISIONAL_NORMALIZER_METHOD",
    "RELATION_ADJACENT",
    "RELATION_OTHER_BAND",
    "RELATION_OTHER_CHANNEL",
    "RELATION_TARGET",
    "ComparisonResult",
    "NormalizerConfig",
    "SignedDeltas",
    "adjacent_bands",
    "baseline_spread",
    "compute_disruption_score_normalized",
    "compute_signed_deltas",
    "unit_relations",
]
