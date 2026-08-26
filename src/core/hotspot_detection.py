"""Layer 1 (platform core) — hotspot (channel×band unit) ranking.

Analog of GeoBind's compute_residue_contact_ranking / build_mutation_priority_table
(src/phenotypes.py, invoked in src/pipeline.py:84-110): rank candidate hotspots by a weighted
composite of class-discriminative signal, with a neighborhood-exclusion rule to avoid
redundant/adjacent picks (e.g. two adjacent frequency bins on the same channel).

See ARCHITECTURE.md, pipeline stage 4.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HotspotUnit:
    """One ranked hotspot: a (channel, frequency band) pair.

    TODO: the exact composite ranking formula and neighborhood-exclusion radius are not yet
    defined — do not invent weights here. Define them once real baseline features exist from
    the CHB-MIT smoke test, and document the formula's provenance the way GeoBind documents
    DEFAULT_BINDING_WEIGHTS as an explicit, named config object.
    """

    channel: str
    band: str  # e.g. "delta", "theta", "alpha", "beta", "gamma" — TODO confirm band edges from literature
    rank_score: float


def rank_hotspots(*args, **kwargs) -> list[HotspotUnit]:
    """Rank channel×band units by class-discriminative signal, applying neighborhood exclusion.

    TODO: implement once baseline phenotype extraction (src/core/metrics_shared.py) exists.
    """
    raise NotImplementedError(
        "rank_hotspots: not yet implemented. Depends on baseline phenotype extraction "
        "landing first (ARCHITECTURE.md pipeline stage 3)."
    )
