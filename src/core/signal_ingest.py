"""Layer 1 (platform core) — raw EEG ingest and recording-type classification.

Interface-agnostic: must not encode assumptions specific to one recording montage, task type,
or dataset. Analog of GeoBind's src/io_pdb.py (fetch_pdb/load_structure) and the chain-
classification half of src/core/interfaces.py (classify_chains_generic/detect_interface_type).

See ARCHITECTURE.md, pipeline stages 1-2.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RecordingMeta:
    """Minimal recording-level metadata needed before routing to a modality module.

    Fields are placeholders — finalize once the first real ingest (CHB-MIT) is wired in.
    """

    source_path: Path
    sampling_rate_hz: float
    channel_names: list[str]
    recording_type: str | None = None  # filled in by detect_recording_type()


def load_eeg_recording(path: Path) -> "RecordingMeta":
    """Load a raw EEG recording (MNE-Python backed) and return its metadata.

    TODO: implement once MNE is added to the environment (see CLAUDE.md) and the CHB-MIT
    smoke-test milestone is reached. Do not stub out fake data here — raise until real.
    """
    raise NotImplementedError(
        "load_eeg_recording: not yet implemented. See business/bp_v0.md milestone table "
        "(smoke-test pipeline running on CHB-MIT, Wk4-6)."
    )


def detect_recording_type(meta: "RecordingMeta") -> str:
    """Generic, modality-agnostic classification of what kind of recording this is
    (e.g. 'seizure_detection', 'motor_imagery', 'resting_state').

    Analog of GeoBind's detect_interface_type() in src/core/interfaces.py:224 — must stay
    interface-agnostic; do not special-case a specific modality's logic here, that belongs in
    src/modules/<modality>/.

    Currently hardcoded to the only implemented modality until a second one exists.
    """
    return "seizure_detection"
