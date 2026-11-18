"""Layer 1 (platform core) — hotspot (channel×band unit) ranking.

Analog of GeoBind's compute_residue_contact_ranking / build_mutation_priority_table
(src/phenotypes.py, invoked in src/pipeline.py:84-110): rank candidate hotspots by a weighted
composite of class-discriminative signal, with a neighborhood-exclusion rule to avoid
redundant/adjacent picks (e.g. two adjacent frequency bands on the same channel).

See ARCHITECTURE.md, pipeline stage 4.

What is computed
----------------
Input: baseline :class:`~src.core.metrics_shared.EpochFeatures` (stage 3) plus one class label per
epoch and an explicit ``positive_label`` (e.g. the seizure class). Exactly two classes are required.

* **Effect size per component** — Cohen's d, ``(mean_pos - mean_ref) / pooled_SD`` with the
  pooled SD using ddof=1 per class (the standard textbook definition; not tuned):
  - ``log_band_power``: per channel×band unit, (n_channels, n_bands);
  - ``line_length``: per *channel*, (n_channels,), broadcast to every band of that channel.
  The signed d is kept as a column (direction matters for interpretation: a seizure can lower
  as well as raise a unit's power); ranking uses its magnitude.
* **Rank score** per unit: ``sum_k weights[k] * |d_k|`` over components with a nonzero weight
  (:class:`RankingWeights`, the analog of GeoBind's ``DEFAULT_BINDING_WEIGHTS``).
* **Neighborhood exclusion** (greedy, GeoBind-style): walk units in descending rank score; a unit
  not yet suppressed is *selected* and suppresses its not-yet-selected neighbors. Neighbors of a
  unit (:class:`NeighborhoodConfig`) form a "cross":
  - spectral: same channel, band within ``spectral_radius_bands`` hops in the band-adjacency
    graph (bands sharing an edge in the BandConfig — computed from edges, not names/order);
  - spatial: same band, channel within ``spatial_radius_hops`` hops in a caller-supplied
    channel-adjacency graph.
  Diagonal units (neighbor channel AND neighbor band) are NOT neighbors in this first pass.

No cutoff, ever
---------------
There is no minimum effect size, no "is a hotspot" threshold and no top-k default. Every unit
ends up in exactly one of ``selected`` (ranked), ``suppressed`` (with the unit that suppressed
it) or ``degenerate_units`` (score undefined). How many selected units to carry forward into the
perturbation panel is the caller's choice and is not decided here.

Provisional values (flagged, not settled)
-----------------------------------------
* :data:`PROVISIONAL_RANKING_WEIGHTS` = ``log_band_power: 1.0, line_length: 0.0``. With line
  length off, the ranking is just ``|d|`` of log band power, so the 1.0 has no effect beyond its
  sign — the score is a pure effect size. Line length is wired in but off: it is channel-level,
  blind to slow-wave changes (smoke test, stage 3), and no source documents a weighting against
  band power. A nonzero line-length weight would be an undocumented value.
* Spectral/spatial radius = 1 hop: the smallest non-trivial neighborhood, not derived from
  literature. 0 disables that axis.
* **Spatial adjacency is not known to the core.** Channel geometry is montage-specific (CLAUDE.md:
  the core must not encode a montage), so ``channel_adjacency`` defaults to ``None`` → no spatial
  exclusion. A modality module (e.g. CHB-MIT's bipolar double-banana chains) must supply it.
* Cross vs. box neighborhood, and Cohen's d vs. Hedges' g / a robust effect size, are open choices.
* Degenerate units: pooled SD exactly 0 → d is NaN, the unit is listed in ``degenerate_units`` and
  not ranked; no epsilon is invented to make it finite.
* Ties are broken deterministically by (channel index, band index). The score is float64 and is
  not quantized here (nothing is persisted); near-tie rank flips under floating-point jitter are
  what the reproducibility audit (stage 8 of ROADMAP Phase 1) must check.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Hashable, Mapping, Sequence

import numpy as np

from src.core.compare import adjacent_bands
from src.core.metrics_shared import EpochFeatures

# PROVISIONAL weights (see module docstring). Named, like GeoBind's DEFAULT_BINDING_WEIGHTS.
PROVISIONAL_RANKING_WEIGHTS: dict[str, float] = {"log_band_power": 1.0, "line_length": 0.0}
# PROVISIONAL neighborhood radii, in graph hops.
PROVISIONAL_SPECTRAL_RADIUS_BANDS = 1
PROVISIONAL_SPATIAL_RADIUS_HOPS = 1

STATUS_SELECTED = "selected"
STATUS_SUPPRESSED = "suppressed"
STATUS_DEGENERATE = "degenerate"


@dataclass(frozen=True)
class RankingWeights:
    """Composite rank-score weights on |Cohen's d| per feature component. Defaults PROVISIONAL."""

    log_band_power: float = PROVISIONAL_RANKING_WEIGHTS["log_band_power"]
    line_length: float = PROVISIONAL_RANKING_WEIGHTS["line_length"]
    provisional: bool = True

    def __post_init__(self) -> None:
        w = self.as_dict()
        if any(v < 0 or not np.isfinite(v) for v in w.values()):
            raise ValueError(f"weights must be finite and >= 0, got {w}")
        if not any(v > 0 for v in w.values()):
            raise ValueError(f"at least one weight must be > 0, got {w}")

    def as_dict(self) -> dict[str, float]:
        return {"log_band_power": self.log_band_power, "line_length": self.line_length}


@dataclass(frozen=True)
class NeighborhoodConfig:
    """Neighborhood-exclusion config. Radii PROVISIONAL; 0 disables that axis.

    channel_adjacency: ``{channel: [neighbor channels]}``, treated as undirected. Supplied by a
    modality module from its montage; ``None`` = no spatial exclusion (the core knows no geometry).
    """

    spectral_radius_bands: int = PROVISIONAL_SPECTRAL_RADIUS_BANDS
    spatial_radius_hops: int = PROVISIONAL_SPATIAL_RADIUS_HOPS
    channel_adjacency: Mapping[str, Sequence[str]] | None = None
    provisional: bool = True

    def __post_init__(self) -> None:
        for name in ("spectral_radius_bands", "spatial_radius_hops"):
            v = getattr(self, name)
            if not isinstance(v, (int, np.integer)) or v < 0:
                raise ValueError(f"{name} must be an int >= 0, got {v!r}")


@dataclass
class HotspotUnit:
    """One channel×band unit's place in the ranking.

    ``rank`` is 1-based among *selected* units (None if suppressed). ``suppressed_by`` is the
    (channel, band) of the selected unit whose neighborhood removed this one (None if selected).
    """

    channel: str
    band: str  # band names come from the (PROVISIONAL) BandConfig
    rank_score: float
    channel_index: int = -1
    band_index: int = -1
    effect_size_signed: float = float("nan")  # Cohen's d of log band power, positive-class minus reference
    rank: int | None = None
    suppressed_by: tuple[str, str] | None = None


@dataclass
class HotspotRanking:
    """Output of :func:`rank_hotspots`. Every unit is in exactly one of selected/suppressed/degenerate."""

    selected: list[HotspotUnit]
    suppressed: list[HotspotUnit]
    degenerate_units: list[tuple[str, str]]
    effect_size_log_band_power: np.ndarray  # (n_channels, n_bands), signed Cohen's d
    effect_size_line_length: np.ndarray  # (n_channels,), signed Cohen's d
    rank_score: np.ndarray  # (n_channels, n_bands); NaN for degenerate units
    channel_names: list[str]
    band_names: list[str]
    positive_label: Hashable
    reference_label: Hashable
    n_epochs: dict
    weights: RankingWeights
    neighborhood: NeighborhoodConfig
    record: dict = field(default_factory=dict)

    @property
    def top(self) -> HotspotUnit | None:
        return self.selected[0] if self.selected else None

    def to_rows(self) -> list[dict]:
        """Canonical per-unit rows sorted by (channel index, band index), for persistence/auditing."""
        by_idx = {(u.channel_index, u.band_index): u for u in self.selected + self.suppressed}
        rows = []
        for ci, ch in enumerate(self.channel_names):
            for bi, bd in enumerate(self.band_names):
                u = by_idx.get((ci, bi))
                status = STATUS_DEGENERATE if u is None else (
                    STATUS_SELECTED if u.rank is not None else STATUS_SUPPRESSED)
                rows.append({
                    "channel": ch,
                    "band": bd,
                    "effect_size_log_band_power": float(self.effect_size_log_band_power[ci, bi]),
                    "effect_size_line_length": float(self.effect_size_line_length[ci]),
                    "rank_score": float(self.rank_score[ci, bi]),
                    "status": status,
                    "rank": None if u is None else u.rank,
                    "suppressed_by": None if (u is None or u.suppressed_by is None) else list(u.suppressed_by),
                    "weights_provisional": self.weights.provisional,
                    "neighborhood_provisional": self.neighborhood.provisional,
                })
        return rows


def cohens_d(ref: np.ndarray, pos: np.ndarray) -> np.ndarray:
    """(mean(pos) - mean(ref)) / pooled SD (ddof=1 per class), along axis 0. 0/0 and x/0 → NaN."""
    na, nb = len(ref), len(pos)
    if na < 2 or nb < 2:
        raise ValueError(f"Cohen's d needs >= 2 epochs per class, got {na} and {nb}")
    pooled = np.sqrt(((na - 1) * ref.var(axis=0, ddof=1) + (nb - 1) * pos.var(axis=0, ddof=1)) / (na + nb - 2))
    diff = pos.mean(axis=0) - ref.mean(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        d = diff / pooled
    return np.where(pooled > 0, d, np.nan)


def _hop_distances(nodes: list[str], edges: Mapping[str, Sequence[str]]) -> np.ndarray:
    """All-pairs shortest hop counts on an undirected graph (BFS); unreachable = -1."""
    idx = {n: i for i, n in enumerate(nodes)}
    unknown = sorted({n for k, vs in edges.items() for n in (k, *vs)} - set(idx))
    if unknown:
        raise ValueError(f"adjacency names unknown channels/bands: {unknown}")
    nbrs: list[set[int]] = [set() for _ in nodes]
    for k, vs in edges.items():
        for v in vs:
            if v != k:
                nbrs[idx[k]].add(idx[v])
                nbrs[idx[v]].add(idx[k])
    dist = np.full((len(nodes), len(nodes)), -1, dtype=int)
    for s in range(len(nodes)):
        dist[s, s] = 0
        q = deque([s])
        while q:
            u = q.popleft()
            for v in sorted(nbrs[u]):
                if dist[s, v] < 0:
                    dist[s, v] = dist[s, u] + 1
                    q.append(v)
    return dist


def _within(dist: np.ndarray, radius: int) -> np.ndarray:
    """Boolean (n, n): reachable within ``radius`` hops, excluding self."""
    m = (dist >= 0) & (dist <= radius)
    np.fill_diagonal(m, False)
    return m


def neighborhood_masks(
    features: EpochFeatures, neighborhood: NeighborhoodConfig
) -> tuple[np.ndarray, np.ndarray]:
    """(band_nbr (n_bands, n_bands), channel_nbr (n_channels, n_channels)) boolean neighbor masks."""
    bands = features.band_config
    band_graph = {b: adjacent_bands(bands, b) for b in bands.names}
    band_nbr = _within(_hop_distances(list(features.band_names), band_graph), neighborhood.spectral_radius_bands)
    n_ch = len(features.channel_names)
    if neighborhood.channel_adjacency is None:
        chan_nbr = np.zeros((n_ch, n_ch), dtype=bool)
    else:
        chan_nbr = _within(_hop_distances(list(features.channel_names), neighborhood.channel_adjacency),
                           neighborhood.spatial_radius_hops)
    return band_nbr, chan_nbr


def rank_hotspots(
    features: EpochFeatures,
    labels,
    positive_label: Hashable,
    weights: RankingWeights | None = None,
    neighborhood: NeighborhoodConfig | None = None,
) -> HotspotRanking:
    """Rank channel×band units by class-discriminative effect size, with neighborhood exclusion.

    ``labels``: one label per epoch, exactly two distinct values; ``positive_label`` is the class
    whose shift is measured (d > 0 = higher in the positive class). See the module docstring for the
    formula, the exclusion rule and what is PROVISIONAL.
    """
    weights = weights or RankingWeights()
    neighborhood = neighborhood or NeighborhoodConfig()
    labels = np.asarray(labels)
    n_ep = features.log_band_power.shape[0]
    if labels.shape != (n_ep,):
        raise ValueError(f"need one label per epoch: {labels.shape} vs {n_ep} epochs")
    classes = sorted(set(labels.tolist()))
    if len(classes) != 2 or positive_label not in classes:
        raise ValueError(f"need exactly two classes including positive_label={positive_label!r}, got {classes}")
    reference_label = classes[0] if classes[1] == positive_label else classes[1]
    pos, ref = labels == positive_label, labels == reference_label

    d_lbp = cohens_d(features.log_band_power[ref], features.log_band_power[pos])
    d_ll = cohens_d(features.line_length[ref], features.line_length[pos])
    n_ch, n_b = d_lbp.shape

    score = np.zeros((n_ch, n_b))
    if weights.log_band_power > 0:
        score = score + weights.log_band_power * np.abs(d_lbp)
    if weights.line_length > 0:
        score = score + weights.line_length * np.abs(d_ll)[:, None]

    band_nbr, chan_nbr = neighborhood_masks(features, neighborhood)
    chs, bds = features.channel_names, features.band_names

    finite = [(ci, bi) for ci in range(n_ch) for bi in range(n_b) if np.isfinite(score[ci, bi])]
    order = sorted(finite, key=lambda u: (-score[u], u[0], u[1]))
    degenerate = [(chs[ci], bds[bi]) for ci in range(n_ch) for bi in range(n_b) if not np.isfinite(score[ci, bi])]

    suppressor: dict[tuple[int, int], tuple[int, int]] = {}
    selected, suppressed = [], []
    for ci, bi in order:
        unit = HotspotUnit(channel=chs[ci], band=bds[bi], rank_score=float(score[ci, bi]),
                           channel_index=ci, band_index=bi, effect_size_signed=float(d_lbp[ci, bi]))
        if (ci, bi) in suppressor:
            sci, sbi = suppressor[(ci, bi)]
            unit.suppressed_by = (chs[sci], bds[sbi])
            suppressed.append(unit)
            continue
        unit.rank = len(selected) + 1
        selected.append(unit)
        nbrs = [(ci, b) for b in np.flatnonzero(band_nbr[bi])] + [(c, bi) for c in np.flatnonzero(chan_nbr[ci])]
        for c, b in nbrs:
            suppressor.setdefault((int(c), int(b)), (ci, bi))

    return HotspotRanking(
        selected=selected, suppressed=suppressed, degenerate_units=degenerate,
        effect_size_log_band_power=d_lbp, effect_size_line_length=d_ll,
        rank_score=np.where(np.isfinite(score), score, np.nan),
        channel_names=list(chs), band_names=list(bds),
        positive_label=positive_label, reference_label=reference_label,
        n_epochs={reference_label: int(ref.sum()), positive_label: int(pos.sum())},
        weights=weights, neighborhood=neighborhood,
        record={"effect_size": "cohens_d_pooled_ddof1", "neighborhood_shape": "cross",
                "weights": weights.as_dict(), "weights_provisional": weights.provisional,
                "spectral_radius_bands": neighborhood.spectral_radius_bands,
                "spatial_radius_hops": neighborhood.spatial_radius_hops,
                "spatial_exclusion": neighborhood.channel_adjacency is not None},
    )
