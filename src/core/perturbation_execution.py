"""Layer 1 (platform core) — deterministic perturbed-signal generation.

Analog of GeoBind's src/mutate.py: apply one PerturbationSpec (src/core/perturbation_design.py)
to a baseline EEG epoch and produce a perturbed epoch, deterministically/seeded, then quantize
on persist to kill floating-point jitter across runs (GeoBind's analog: coordinates rounded to
0.1 A at write time — the EEG-appropriate quantization precision is TBD, see ARCHITECTURE.md's
"Open design decisions").

See ARCHITECTURE.md, pipeline stage 7, and the "Determinism over cleverness" non-negotiable in
CLAUDE.md.
"""

from __future__ import annotations


def apply_perturbation(*args, **kwargs):
    """Apply one perturbation spec to a baseline epoch; return the perturbed epoch.

    TODO: implement per perturbation_class once src/core/perturbation_design.py's panel is
    finalized (not before — the panel is still provisional). Must be deterministic given a
    fixed seed; must quantize the output at a documented, fixed precision before persisting.
    """
    raise NotImplementedError(
        "apply_perturbation: not yet implemented. Perturbation panel is still provisional — "
        "see mechanism_aware_interpretation_rubric.md."
    )
