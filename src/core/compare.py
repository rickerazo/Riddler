"""Layer 1 (platform core) — baseline-vs-perturbed comparison.

Analog of GeoBind's src/compare.py: per-metric signed deltas oriented "positive = more
disruptive", rolled up into a composite disruption score via a weighted linear combination.

CRITICAL (GeoBind lesson, see CLAUDE.md's "baseline-normalize comparability from day one"):
raw disruption magnitudes are NOT comparable across hotspots without normalizing by each
hotspot's own baseline engagement. Build the normalized variant FIRST — do not ship an
un-normalized score and retrofit normalization later, the way GeoBind's
binding_disruption_score_normalized_local had to be added after the fact.

See ARCHITECTURE.md, pipeline stage 9.
"""

from __future__ import annotations


def compute_signed_deltas(*args, **kwargs):
    """Per-metric signed deltas between baseline and perturbed features, oriented so that
    positive = more disruptive.

    TODO: implement once baseline and perturbed phenotype extraction both exist.
    """
    raise NotImplementedError("compute_signed_deltas: not yet implemented.")


def compute_disruption_score_normalized(*args, **kwargs):
    """Baseline-normalized composite disruption score — the ONLY disruption score this module
    should expose. Do not add an un-normalized variant as the default; if one is needed for
    debugging, name it explicitly as raw/un-normalized so it can never be mistaken for the
    comparable one (GeoBind's _complexwide vs _normalized_local naming confusion is the
    documented cautionary example — see the GeoBind architecture report this repo was scaffolded
    from).

    TODO: implement. Weights must be an explicit, named config object (see CLAUDE.md's
    "config values are function parameters, never hardcoded").
    """
    raise NotImplementedError("compute_disruption_score_normalized: not yet implemented.")
