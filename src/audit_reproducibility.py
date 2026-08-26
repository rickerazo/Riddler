"""Reproducibility audit — FAIL/WARN/PASS, ported from GeoBind's src/audit_reproducibility.py.

Compares two runs of the pipeline and returns a verdict:
- FAIL: a feature value, hotspot ranking, or mechanism-classification call changed between
  runs — science-affecting, must not be silently tolerated.
- WARN: a raw persisted-artifact hash differs but all downstream features/classifications are
  stable — tolerated nondeterminism (e.g. a filtering step with a nondeterministic backend).
- PASS: byte-identical (or within-tolerance) on both fronts.

See ARCHITECTURE.md's "Reproducibility policy" and CLAUDE.md's validation-procedure
non-negotiable. This is one of the two legs of Riddler's validation protocol (the other is the
external-practitioner-critique-then-benchmark loop — see business/validation_protocol_v1.md
once drafted).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AuditVerdict(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class AuditResult:
    verdict: AuditVerdict
    reasons: list[str]


def audit_two_runs(*args, **kwargs) -> "AuditResult":
    """Compare two pipeline runs' outputs and return a verdict + human-readable reasons.

    TODO: implement once run_pipeline_smoke_test.py produces real, persisted outputs to
    compare across two invocations. Do not implement against fabricated/placeholder data.
    """
    raise NotImplementedError(
        "audit_two_runs: not yet implemented. Depends on the smoke test producing real "
        "persisted outputs first (business/bp_v0.md, Wk4-6 milestone)."
    )
