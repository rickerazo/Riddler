"""Side-by-side 30 s control vs 30 s seizure, all channels, identical vertical scale. Exploration only."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mne

edf, outdir = Path(sys.argv[1]), Path(sys.argv[2])
outdir.mkdir(parents=True, exist_ok=True)
CONTROL = (2600, 2630)   # ~6.6 min before onset, same session
SEIZURE = (2996, 3026)   # first 30 s of annotated seizure (2996-3036 s, chb01-summary.txt)
SPACING_UV = 400         # vertical offset between channels (same for both panels)

raw = mne.io.read_raw_edf(edf, preload=True, verbose="error")
raw.drop_channels(["T8-P8-1"])  # CHB-MIT lists T8-P8 twice; keep one copy
raw.filter(0.5, 40, verbose="error")

fig, axes = plt.subplots(1, 2, figsize=(18, 11), sharey=True)
for ax, (t0, t1), title, color in [
    (axes[0], CONTROL, "CONTROL (no seizure)", "#1f4e79"),
    (axes[1], SEIZURE, "SEIZURE (annotated)", "#a11d21"),
]:
    seg = raw.copy().crop(t0, t1)
    d = seg.get_data() * 1e6  # volts -> microvolts
    t = seg.times + t0
    for i, ch in enumerate(seg.ch_names):
        ax.plot(t, d[i] - i * SPACING_UV, lw=0.45, color=color)
    ax.set_title(f"{title}: {t0}-{t1} s", fontsize=13, color=color)
    ax.set_xlabel("time in recording (s)")
    ax.set_xlim(t0, t1)
    ax.spines[["top", "right"]].set_visible(False)

axes[0].set_yticks([-i * SPACING_UV for i in range(len(raw.ch_names))], raw.ch_names, fontsize=8)
# scale bar
axes[1].plot([SEIZURE[1] - 1] * 2, [SPACING_UV, 0], color="k", lw=2, clip_on=False)
axes[1].text(SEIZURE[1] - 1.3, SPACING_UV / 2, f"{SPACING_UV} µV", ha="right", va="center", fontsize=9)
fig.suptitle("CHB-MIT chb01_03.edf: 22 bipolar channels, 256 Hz, band-passed 0.5-40 Hz, identical scale", fontsize=14)
fig.tight_layout()
out = outdir / "chb01_03_control_vs_seizure.png"
fig.savefig(out, dpi=120)
print(out)
