"""Exploratory walkthrough of one CHB-MIT recording (chb01_03.edf). NOT pipeline code.

Band edges below are conventional clinical EEG bands used for exploration only; the repo
explicitly marks band edges as TBD pending literature grounding (hotspot_detection.py).
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mne
import numpy as np
import pandas as pd

edf = Path(sys.argv[1])
outdir = Path(sys.argv[2])
SZ_START, SZ_END = 2996, 3036  # seconds, from chb01-summary.txt

raw = mne.io.read_raw_edf(edf, preload=True, verbose="error")
print(f"channels={len(raw.ch_names)}  fs={raw.info['sfreq']} Hz  duration={raw.times[-1]/60:.1f} min")
print("channel names:", raw.ch_names)
raw.filter(0.5, 40, verbose="error")  # exploration-only band-pass

BANDS = {"delta": (0.5, 4), "theta": (4, 8), "alpha": (8, 13), "beta": (13, 30)}


def band_power(t0, t1):
    seg = raw.copy().crop(t0, t1)
    psd = seg.compute_psd(fmin=0.5, fmax=40, verbose="error")
    p, f = psd.get_data(return_freqs=True)
    return pd.DataFrame(
        {b: p[:, (f >= lo) & (f < hi)].mean(axis=1) for b, (lo, hi) in BANDS.items()},
        index=raw.ch_names,
    )

pre = band_power(SZ_START - 300, SZ_START - 60)  # 5 min to 1 min before onset
ict = band_power(SZ_START, SZ_END)               # the seizure itself
ratio = np.log10(ict / pre)                      # >0 = power increased during seizure
ratio = ratio.loc[~ratio.index.duplicated()]

stack = ratio.stack().sort_values(ascending=False)
print("\nTop 10 channel x band units by log10(seizure power / pre-seizure power):")
print(stack.head(10).round(2).to_string())

# Figure 1: raw traces around onset
fig, ax = plt.subplots(figsize=(12, 8))
seg = raw.copy().crop(SZ_START - 20, SZ_END + 10)
d = seg.get_data()[:18] * 1e6
t = seg.times + SZ_START - 20
for i, ch in enumerate(seg.ch_names[:18]):
    ax.plot(t, d[i] - i * 300, lw=0.5, color="k")
    ax.text(t[0] - 1, -i * 300, ch, ha="right", va="center", fontsize=7)
ax.axvspan(SZ_START, SZ_END, color="red", alpha=0.12, label="annotated seizure")
ax.set_yticks([]); ax.set_xlabel("time (s)"); ax.legend(loc="upper right")
ax.set_title("chb01_03: 18 channels, 20 s before to 10 s after the seizure")
fig.tight_layout(); fig.savefig(outdir / "traces.png", dpi=110)

# Figure 2: hotspot heatmap
fig, ax = plt.subplots(figsize=(6, 9))
v = np.abs(ratio.values).max()
im = ax.imshow(ratio.values, cmap="RdBu_r", vmin=-v, vmax=v, aspect="auto")
ax.set_xticks(range(len(BANDS)), BANDS.keys()); ax.set_yticks(range(len(ratio)), ratio.index, fontsize=7)
fig.colorbar(im, label="log10(seizure / pre-seizure power)")
ax.set_title("Which channel x band units change most?")
fig.tight_layout(); fig.savefig(outdir / "hotspots.png", dpi=110)
print(f"\nfigures written to {outdir}")
