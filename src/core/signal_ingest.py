"""Layer 1 (platform core) — raw EEG ingest, epoching, and recording-type classification.

Interface-agnostic: must not encode assumptions specific to one recording montage, task type,
or dataset. Analog of GeoBind's src/io_pdb.py (fetch_pdb/load_structure) and the chain-
classification half of src/core/interfaces.py (classify_chains_generic/detect_interface_type).

See ARCHITECTURE.md, pipeline stages 1-2.

Duplicate channel labels
------------------------
Some EDF files carry the same channel label more than once (CHB-MIT is one example, but nothing
here is specific to it). MNE refuses duplicate names and renames them ``<label>-0``,
``<label>-1``, ... at read time. :func:`resolve_duplicate_channels` handles this generically,
for both EDF-loaded and in-memory recordings:

* a *duplicate group* is either the same label repeated verbatim, or a set of labels
  ``<base>-0 .. <base>-{n-1}`` (n >= 2, consecutive from 0) whose ``<base>`` is not itself a
  channel, i.e. exactly the pattern MNE's de-duplication produces;
* ``policy="drop_identical"`` (default): if every member of a group is sample-for-sample
  identical (exact equality, no tolerance), keep the first under ``<base>`` and drop the rest.
  If they differ, raise: picking one would be a silent guess;
* ``policy="error"``: raise on any duplicate group;
* ``policy="keep"``: keep every member under its (MNE-suffixed) name.

What gets dropped is recorded on :class:`RecordingMeta` so it is never silent.

No quantization happens here: ingest persists nothing. Quantize-on-persist (ARCHITECTURE.md
reproducibility policy) applies where artifacts are written, e.g. perturbation execution.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

DUPLICATE_POLICIES = ("drop_identical", "error", "keep")

# PROVISIONAL default epoch window, in seconds. Not grounded in a cited source yet; ROADMAP.md
# "Open decisions" lists window length as provisional until Track A / real distributions.
# Every caller can and should override it via EpochConfig.window_s.
PROVISIONAL_WINDOW_S = 2.0

_MNE_DEDUP_SUFFIX = re.compile(r"^(?P<base>.+)-(?P<idx>\d+)$")


@dataclass
class IngestConfig:
    """Ingest options. ``duplicate_policy`` is one of DUPLICATE_POLICIES (see module doc)."""

    duplicate_policy: str = "drop_identical"

    def __post_init__(self) -> None:
        if self.duplicate_policy not in DUPLICATE_POLICIES:
            raise ValueError(
                f"duplicate_policy={self.duplicate_policy!r}; expected one of {DUPLICATE_POLICIES}"
            )


@dataclass
class EpochConfig:
    """Epoching options.

    window_s: window length in seconds. Default is PROVISIONAL (see PROVISIONAL_WINDOW_S).
    step_s:   hop between window starts; ``None`` means non-overlapping (step = window).
    Both must correspond to a whole number of samples at the recording's sampling rate.
    """

    window_s: float = PROVISIONAL_WINDOW_S
    step_s: float | None = None

    def __post_init__(self) -> None:
        if self.window_s <= 0:
            raise ValueError(f"window_s must be > 0, got {self.window_s}")
        if self.step_s is not None and self.step_s <= 0:
            raise ValueError(f"step_s must be > 0, got {self.step_s}")


@dataclass
class RecordingMeta:
    """Recording-level metadata needed before routing to a modality module."""

    source_path: Path | None  # None for in-memory (e.g. synthetic) recordings
    sampling_rate_hz: float
    channel_names: list[str]
    recording_type: str | None = None  # filled in by detect_recording_type()
    n_samples: int = 0
    # {kept channel name: [dropped original names]}, from resolve_duplicate_channels()
    dropped_duplicate_channels: dict[str, list[str]] = field(default_factory=dict)

    @property
    def duration_s(self) -> float:
        return self.n_samples / self.sampling_rate_hz


@dataclass
class EEGRecording:
    """A loaded recording: ``data`` is (n_channels, n_samples) float64, in volts for EDF input."""

    data: np.ndarray
    meta: RecordingMeta


@dataclass
class EpochedRecording:
    """Fixed-length windows cut from one recording.

    data:          (n_epochs, n_channels, n_samples_per_epoch)
    start_samples: (n_epochs,) start index of each window in the source recording. This is the
                   stable identity key for canonical serialization (ARCHITECTURE.md policy 2).
    """

    data: np.ndarray
    start_samples: np.ndarray
    sampling_rate_hz: float
    channel_names: list[str]
    config: EpochConfig

    @property
    def start_times_s(self) -> np.ndarray:
        return self.start_samples / self.sampling_rate_hz


# ---------------------------------------------------------------------------------------------
# Duplicate-channel handling
# ---------------------------------------------------------------------------------------------


def find_duplicate_channel_groups(channel_names: list[str]) -> dict[str, list[int]]:
    """Return {base label: [indices]} for every duplicate group (see module doc).

    Only groups of size >= 2 are returned; indices are in channel order.
    """
    groups: dict[str, list[int]] = {}

    # (a) verbatim repeats
    by_name: dict[str, list[int]] = {}
    for i, name in enumerate(channel_names):
        by_name.setdefault(name, []).append(i)
    for name, idxs in by_name.items():
        if len(idxs) >= 2:
            groups[name] = idxs

    # (b) MNE-style "<base>-0 .. <base>-{n-1}" with <base> absent
    present = set(channel_names)
    suffixed: dict[str, list[tuple[int, int]]] = {}
    for i, name in enumerate(channel_names):
        m = _MNE_DEDUP_SUFFIX.match(name)
        if m:
            suffixed.setdefault(m["base"], []).append((int(m["idx"]), i))
    for base, members in suffixed.items():
        if base in present or len(members) < 2:
            continue
        if sorted(k for k, _ in members) != list(range(len(members))):
            continue  # not a clean 0..n-1 run, so not MNE's de-dup pattern
        groups[base] = sorted(i for _, i in members)

    return groups


def resolve_duplicate_channels(
    data: np.ndarray, channel_names: list[str], policy: str = "drop_identical"
) -> tuple[np.ndarray, list[str], dict[str, list[str]]]:
    """Apply ``policy`` to duplicate channel groups.

    Returns (data, channel_names, dropped) where ``dropped`` maps each kept channel's name to
    the original names that were removed as identical copies of it.
    """
    if policy not in DUPLICATE_POLICIES:
        raise ValueError(f"policy={policy!r}; expected one of {DUPLICATE_POLICIES}")
    groups = find_duplicate_channel_groups(channel_names)
    if not groups or policy == "keep":
        return data, list(channel_names), {}
    if policy == "error":
        raise ValueError(f"duplicate channel groups found: { {b: [channel_names[i] for i in ix] for b, ix in groups.items()} }")

    names = list(channel_names)
    drop: set[int] = set()
    dropped: dict[str, list[str]] = {}
    for base, idxs in groups.items():
        first = idxs[0]
        differing = [channel_names[i] for i in idxs[1:] if not np.array_equal(data[first], data[i])]
        if differing:
            raise ValueError(
                f"channels {[channel_names[i] for i in idxs]} share label {base!r} but are not "
                f"identical ({differing} differ from {channel_names[first]!r}). Refusing to pick one; "
                "pass duplicate_policy='keep' or resolve it in the modality module."
            )
        names[first] = base
        drop.update(idxs[1:])
        dropped[base] = [channel_names[i] for i in idxs[1:]]

    keep = [i for i in range(len(names)) if i not in drop]
    return data[keep], [names[i] for i in keep], dropped


# ---------------------------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------------------------


def recording_from_array(
    data: np.ndarray,
    sampling_rate_hz: float,
    channel_names: list[str],
    config: IngestConfig | None = None,
    source_path: Path | None = None,
) -> EEGRecording:
    """Build an EEGRecording from an in-memory (n_channels, n_samples) array.

    Same duplicate handling as the EDF path, so synthetic tests exercise the real code.
    """
    config = config or IngestConfig()
    data = np.asarray(data, dtype=np.float64)
    if data.ndim != 2:
        raise ValueError(f"data must be 2-D (n_channels, n_samples), got shape {data.shape}")
    if data.shape[0] != len(channel_names):
        raise ValueError(f"{data.shape[0]} data rows but {len(channel_names)} channel names")
    if sampling_rate_hz <= 0:
        raise ValueError(f"sampling_rate_hz must be > 0, got {sampling_rate_hz}")

    data, names, dropped = resolve_duplicate_channels(data, list(channel_names), config.duplicate_policy)
    meta = RecordingMeta(
        source_path=source_path,
        sampling_rate_hz=float(sampling_rate_hz),
        channel_names=names,
        n_samples=int(data.shape[1]),
        dropped_duplicate_channels=dropped,
    )
    return EEGRecording(data=data, meta=meta)


def load_eeg_recording(path: Path | str, config: IngestConfig | None = None) -> EEGRecording:
    """Load an EEG recording from disk via MNE-Python (EDF/BDF/etc. via ``mne.io.read_raw``).

    Only EEG-typed channels are kept. No filtering or resampling is applied here; that is a
    downstream, explicitly configured step.
    """
    import mne  # local import: keeps the synthetic path free of an MNE import cost

    path = Path(path)
    raw = mne.io.read_raw(path, preload=True, verbose="error")
    raw.pick("eeg")
    return recording_from_array(
        raw.get_data(),
        sampling_rate_hz=raw.info["sfreq"],
        channel_names=list(raw.ch_names),
        config=config,
        source_path=path,
    )


# ---------------------------------------------------------------------------------------------
# Epoching
# ---------------------------------------------------------------------------------------------


def _seconds_to_samples(seconds: float, sfreq: float, what: str) -> int:
    n = seconds * sfreq
    n_int = int(round(n))
    if abs(n - n_int) > 1e-9:
        raise ValueError(f"{what}={seconds} s is not a whole number of samples at {sfreq} Hz ({n})")
    return n_int


def epoch_recording(
    recording: EEGRecording,
    config: EpochConfig | None = None,
    start_s: float = 0.0,
    stop_s: float | None = None,
) -> EpochedRecording:
    """Cut fixed-length windows from ``recording`` over [start_s, stop_s).

    A trailing partial window is dropped, never padded. Windows are views into consecutive
    samples; no filtering or detrending.
    """
    config = config or EpochConfig()
    sfreq = recording.meta.sampling_rate_hz
    n_total = recording.data.shape[1]

    win = _seconds_to_samples(config.window_s, sfreq, "window_s")
    step = win if config.step_s is None else _seconds_to_samples(config.step_s, sfreq, "step_s")
    lo = _seconds_to_samples(start_s, sfreq, "start_s")
    hi = n_total if stop_s is None else _seconds_to_samples(stop_s, sfreq, "stop_s")
    if not (0 <= lo <= hi <= n_total):
        raise ValueError(f"segment [{start_s}, {stop_s}) s is outside the recording (0-{n_total / sfreq} s)")

    starts = np.arange(lo, hi - win + 1, step, dtype=np.int64)
    n_ch = recording.data.shape[0]
    if starts.size == 0:
        epochs = np.empty((0, n_ch, win), dtype=recording.data.dtype)
    else:
        idx = starts[:, None] + np.arange(win)[None, :]
        epochs = recording.data[:, idx].transpose(1, 0, 2)  # (n_epochs, n_ch, win)

    return EpochedRecording(
        data=np.ascontiguousarray(epochs),
        start_samples=starts,
        sampling_rate_hz=sfreq,
        channel_names=list(recording.meta.channel_names),
        config=config,
    )


# ---------------------------------------------------------------------------------------------
# Recording-type routing
# ---------------------------------------------------------------------------------------------


def detect_recording_type(meta: "RecordingMeta") -> str:
    """Generic, modality-agnostic classification of what kind of recording this is
    (e.g. 'seizure_detection', 'motor_imagery', 'resting_state').

    Analog of GeoBind's detect_interface_type() in src/core/interfaces.py:224 — must stay
    interface-agnostic; do not special-case a specific modality's logic here, that belongs in
    src/modules/<modality>/.

    Currently hardcoded to the only implemented modality until a second one exists.
    """
    return "seizure_detection"


def _summarize(path: str) -> None:
    rec = load_eeg_recording(path)
    m = rec.meta
    ep = epoch_recording(rec)
    print(f"source: {m.source_path}")
    print(f"sfreq={m.sampling_rate_hz} Hz  channels={len(m.channel_names)}  "
          f"samples={m.n_samples}  duration={m.duration_s:.1f} s")
    print(f"channels: {m.channel_names}")
    print(f"dropped duplicates: {m.dropped_duplicate_channels or 'none'}")
    print(f"epochs (window={ep.config.window_s} s, PROVISIONAL): {ep.data.shape}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m src.core.signal_ingest <recording.edf>")
    _summarize(sys.argv[1])
