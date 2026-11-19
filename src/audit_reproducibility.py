"""Reproducibility audit — FAIL/WARN/PASS, ported from GeoBind's src/audit_reproducibility.py.

Compares two persisted runs of the pipeline and returns a verdict (ARCHITECTURE.md "Reproducibility
policy", item 3; CLAUDE.md validation non-negotiable):

- FAIL: a science-affecting artifact changed between runs — a hotspot-ranking row (rank, status,
  effect size), a perturbation design row, a compare summary (feature-derived disruption score) or a
  mechanism call. Also FAIL when a run is incomplete (a conclusion file or a raw artifact is missing
  on one side), because then the conclusions cannot be shown to be stable.
- WARN: a raw persisted artifact (perturbed-signal ``.npy`` counts / ``.json`` provenance sidecar)
  hashes differently, but every conclusion artifact is identical. Tolerated nondeterminism, reported
  explicitly, never hidden.
- PASS: conclusion artifacts identical and every raw artifact byte-identical.

Layout of one persisted run directory (written by :func:`persist_run`)::

    <run_dir>/hotspot_ranking.json      HotspotRanking.to_rows()           (conclusion)
    <run_dir>/design_table.json         build_perturbation_design_table()  (conclusion)
    <run_dir>/compare_summaries.json    ComparisonResult.summary() rows    (conclusion)
    <run_dir>/mechanism_calls.json      MechanismCall.to_row() rows        (conclusion)
    <run_dir>/perturbed/<tag>.npy|.json persist_perturbed_signal()         (raw)

Conclusion files are canonical JSON (sorted keys, fixed indent, non-finite floats as strings).
FLAGGED, NOT DECIDED: the persisted *feature* precision is still an open item in ARCHITECTURE.md
("Quantization precision"). Until it is decided, floats are written at full float64 ``repr``
(``float_decimals=None``), the strictest choice: any feature jitter at all is a FAIL. A decided
precision can later be passed as ``float_decimals`` without changing this module's logic.

CLI:
    python -m src.audit_reproducibility                  # two planted-amplitude runs -> audit
    python -m src.audit_reproducibility RUN_A RUN_B      # audit two existing run directories
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping

AUDIT_SCHEMA_VERSION = 1

RANKING_FILE = "hotspot_ranking.json"
DESIGN_FILE = "design_table.json"
SUMMARIES_FILE = "compare_summaries.json"
CALLS_FILE = "mechanism_calls.json"
CONCLUSION_FILES = (RANKING_FILE, DESIGN_FILE, SUMMARIES_FILE, CALLS_FILE)
PERTURBED_SUBDIR = "perturbed"
RESULT_FILE = "audit_result.json"

DEFAULT_OUT_DIR = Path("outputs/reproducibility/phase1_planted_amplitude")  # gitignored


class AuditVerdict(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class AuditResult:
    verdict: AuditVerdict
    reasons: list[str]
    checked: dict = field(default_factory=dict)  # what was compared, for the persisted audit record

    def to_dict(self) -> dict:
        return {"audit_schema_version": AUDIT_SCHEMA_VERSION, "verdict": self.verdict.value,
                "reasons": list(self.reasons), "checked": self.checked}


# ---------------------------------------------------------------------------------------------
# canonical serialization
# ---------------------------------------------------------------------------------------------

def _canonical(obj: Any, float_decimals: int | None) -> Any:
    """Recursively convert to plain JSON types. Non-finite floats become strings so the output is
    strict JSON; tuples become lists; numpy scalars become Python scalars."""
    if hasattr(obj, "item") and not isinstance(obj, (list, tuple, dict, str)):  # numpy scalar
        obj = obj.item()
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj):
            return "NaN"
        if math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
        return obj if float_decimals is None else round(obj, float_decimals)
    if isinstance(obj, Mapping):
        return {str(k): _canonical(v, float_decimals) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_canonical(v, float_decimals) for v in obj]
    if isinstance(obj, Enum):
        return _canonical(obj.value, float_decimals)
    raise TypeError(f"cannot canonicalize {type(obj).__name__}: {obj!r}")


def canonical_json(obj: Any, float_decimals: int | None = None) -> str:
    """Byte-stable JSON text: sorted keys, indent 2, ``\\n``-terminated, strict (no NaN tokens).

    ``float_decimals=None`` keeps full float64 ``repr`` (see the module note: feature precision
    is an open decision, so the default is the strictest setting).
    """
    if float_decimals is not None and (not isinstance(float_decimals, int) or float_decimals < 0):
        raise ValueError(f"float_decimals must be None or an int >= 0, got {float_decimals!r}")
    return json.dumps(_canonical(obj, float_decimals), sort_keys=True, indent=2,
                      ensure_ascii=True, allow_nan=False) + "\n"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------------------------
# persist one run
# ---------------------------------------------------------------------------------------------

def persist_run(out: Mapping, run_dir: Path | str, float_decimals: int | None = None) -> dict[str, str]:
    """Write a run's conclusion artifacts as canonical JSON; return {relative path: sha256}.

    ``out`` is the dict returned by ``run_end_to_end`` (keys ``ranking``, ``design``,
    ``summaries``, ``calls``). Perturbed signals are persisted by the run itself into
    ``<run_dir>/perturbed/`` (``run_end_to_end(..., perturbed_out_dir=...)``); they are hashed here
    too so the return value lists every artifact the audit will compare.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        RANKING_FILE: out["ranking"].to_rows(),
        DESIGN_FILE: list(out["design"]),
        SUMMARIES_FILE: list(out["summaries"]),
        CALLS_FILE: [c.to_row() for c in out["calls"]],
    }
    for name, rows in payloads.items():
        (run_dir / name).write_text(canonical_json(rows, float_decimals))
    return {rel: _sha256(run_dir / rel) for rel in _artifact_paths(run_dir)}


def _artifact_paths(run_dir: Path) -> list[str]:
    """Relative paths of every audited artifact present in ``run_dir``, sorted."""
    paths = [n for n in CONCLUSION_FILES if (run_dir / n).is_file()]
    pdir = run_dir / PERTURBED_SUBDIR
    if pdir.is_dir():
        paths += sorted(p.relative_to(run_dir).as_posix() for p in pdir.rglob("*") if p.is_file())
    return paths


# ---------------------------------------------------------------------------------------------
# compare two runs
# ---------------------------------------------------------------------------------------------

def _first_row_diff(a: list, b: list) -> str:
    if not (isinstance(a, list) and isinstance(b, list)):
        return "top-level type differs"
    if len(a) != len(b):
        return f"row count {len(a)} vs {len(b)}"
    for i, (ra, rb) in enumerate(zip(a, b)):
        if ra != rb:
            if isinstance(ra, dict) and isinstance(rb, dict):
                keys = sorted(k for k in set(ra) | set(rb) if ra.get(k, "<missing>") != rb.get(k, "<missing>"))
                shown = "; ".join(f"{k}: {ra.get(k, '<missing>')!r} -> {rb.get(k, '<missing>')!r}" for k in keys[:4])
                more = f" (+{len(keys) - 4} more keys)" if len(keys) > 4 else ""
                return f"row {i}: {shown}{more}"
            return f"row {i} differs"
    return "content differs"


def audit_two_runs(run_a: Path | str, run_b: Path | str) -> AuditResult:
    """Compare two persisted run directories (see module docstring for layout) -> verdict.

    Conclusion files are compared as parsed JSON (so a pure formatting difference cannot FAIL).
    Raw artifacts are compared by sha256. Raises ``ValueError`` if a directory is missing or
    neither run has any raw artifact (nothing to audit is not a PASS).
    """
    a, b = Path(run_a), Path(run_b)
    for d in (a, b):
        if not d.is_dir():
            raise ValueError(f"run directory {d} does not exist")
    fail: list[str] = []
    warn: list[str] = []
    checked: dict[str, Any] = {"conclusion_files": {}, "raw_artifacts": {}}

    for name in CONCLUSION_FILES:
        pa, pb = a / name, b / name
        if not (pa.is_file() and pb.is_file()):
            missing = [str(p) for p in (pa, pb) if not p.is_file()]
            fail.append(f"FAIL {name}: missing in {', '.join(missing)}")
            checked["conclusion_files"][name] = "missing"
            continue
        ja, jb = json.loads(pa.read_text()), json.loads(pb.read_text())
        same = ja == jb
        checked["conclusion_files"][name] = {"identical": same, "n_rows": len(ja) if isinstance(ja, list) else None,
                                             "sha256_a": _sha256(pa), "sha256_b": _sha256(pb)}
        if not same:
            fail.append(f"FAIL {name} changed: {_first_row_diff(ja, jb)}")

    raw_a = {p for p in _artifact_paths(a) if p.startswith(PERTURBED_SUBDIR + "/")}
    raw_b = {p for p in _artifact_paths(b) if p.startswith(PERTURBED_SUBDIR + "/")}
    if not raw_a and not raw_b:
        raise ValueError(f"no raw artifacts under {a / PERTURBED_SUBDIR} or {b / PERTURBED_SUBDIR}; nothing to audit")
    for rel in sorted(raw_a ^ raw_b):
        side = "run B" if rel in raw_a else "run A"
        fail.append(f"FAIL raw artifact {rel} missing in {side} (incomplete run)")
        checked["raw_artifacts"][rel] = "missing"
    for rel in sorted(raw_a & raw_b):
        ha, hb = _sha256(a / rel), _sha256(b / rel)
        checked["raw_artifacts"][rel] = {"identical": ha == hb, "sha256_a": ha, "sha256_b": hb}
        if ha != hb:
            warn.append(f"WARN raw artifact {rel} hash drifted ({ha[:12]} -> {hb[:12]})")

    if fail:
        return AuditResult(AuditVerdict.FAIL, fail + warn, checked)
    if warn:
        return AuditResult(AuditVerdict.WARN, warn + ["conclusion artifacts identical: drift is raw-only"], checked)
    n = len(CONCLUSION_FILES) + len(raw_a)
    return AuditResult(AuditVerdict.PASS, [f"all {n} artifacts identical ({len(CONCLUSION_FILES)} conclusion, "
                                           f"{len(raw_a)} raw)"], checked)


def run_two_and_audit(
    run_fn: Callable[[Path], Mapping],
    out_dir: Path | str,
    float_decimals: int | None = None,
) -> tuple[AuditResult, Mapping, Mapping]:
    """Run ``run_fn`` twice (into ``out_dir/run_a`` and ``out_dir/run_b``), persist, audit.

    ``run_fn(perturbed_dir)`` must perform one full pipeline run, persisting its perturbed
    signals under ``perturbed_dir``, and return the ``run_end_to_end``-style output dict. Writes
    ``out_dir/audit_result.json``. Returns (result, out_a, out_b).
    """
    out_dir = Path(out_dir)
    outs = []
    for name in ("run_a", "run_b"):
        run_dir = out_dir / name
        if run_dir.exists() and any(run_dir.iterdir()):
            raise ValueError(f"{run_dir} is not empty; refusing to mix runs (use a fresh out_dir)")
        out = run_fn(run_dir / PERTURBED_SUBDIR)
        persist_run(out, run_dir, float_decimals)
        outs.append(out)
    result = audit_two_runs(out_dir / "run_a", out_dir / "run_b")
    result.checked["float_decimals"] = float_decimals
    result.checked["float_decimals_provisional"] = True
    (out_dir / RESULT_FILE).write_text(canonical_json(result.to_dict()))
    return result, outs[0], outs[1]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 2:
        result = audit_two_runs(argv[0], argv[1])
    elif not argv:
        from src.run_pipeline_smoke_test import run_planted_reproducibility_audit
        if DEFAULT_OUT_DIR.exists() and any(DEFAULT_OUT_DIR.iterdir()):
            print(f"[audit] {DEFAULT_OUT_DIR} is not empty; delete it to rerun", file=sys.stderr)
            return 2
        result, _, _ = run_planted_reproducibility_audit(DEFAULT_OUT_DIR)
        print(f"[audit] wrote {DEFAULT_OUT_DIR / RESULT_FILE}")
    else:
        print(__doc__.split("CLI:")[1], file=sys.stderr)
        return 2
    print(f"[audit] verdict: {result.verdict.value}")
    for r in result.reasons:
        print(f"[audit]   {r}")
    return {AuditVerdict.PASS: 0, AuditVerdict.WARN: 0, AuditVerdict.FAIL: 1}[result.verdict]


__all__ = [
    "AuditResult",
    "AuditVerdict",
    "CONCLUSION_FILES",
    "audit_two_runs",
    "canonical_json",
    "persist_run",
    "run_two_and_audit",
]


if __name__ == "__main__":
    raise SystemExit(main())
