"""Exploration only (NOT pipeline code): what two provisional perturbations do to one real hotspot.

Hotspot: F8-T8 x delta, chb01_03.edf, first 30 s of the annotated seizure (2996-3026 s).
Band edges (0.5-4 Hz) and the 0.5 attenuation factor are illustrative, NOT calibrated values
(see mechanism_aware_interpretation_rubric.md - panel is provisional).

Usage: python -I plot_perturbations.py <edf> <outdir>
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mne
import numpy as np
from scipy.signal import welch

edf, outdir = Path(sys.argv[1]), Path(sys.argv[2])
CH, BAND = "F8-T8", (0.5, 4.0)
T0, T1 = 2996, 3026
ATTEN = 0.5   # illustrative only
SEED = 0

raw = mne.io.read_raw_edf(edf, preload=True, verbose="error").pick([CH])
fs = raw.info["sfreq"]
raw.filter(0.5, 40, verbose="error")
x = raw.copy().crop(T0, T1, include_tmax=False).get_data()[0] * 1e6  # µV, 30 s

# Split signal into (delta component) + (everything else)
band = mne.filter.filter_data(x, fs, BAND[0], BAND[1], verbose="error")
rest = x - band

# Perturbation 1: amplitude attenuation of the delta component only
amp = rest + ATTEN * band

# Perturbation 2: phase scramble of the delta component (phase-randomized surrogate)
rng = np.random.default_rng(SEED)
F = np.fft.rfft(band)
ph = rng.uniform(0, 2 * np.pi, F.size)
ph[0] = 0.0
if band.size % 2 == 0:
    ph[-1] = 0.0
scr = rest + np.fft.irfft(np.abs(F) * np.exp(1j * ph), n=band.size)

versions = {"original": x, f"amplitude x{ATTEN}": amp, "phase scrambled": scr}
colors = {"original": "#222222", f"amplitude x{ATTEN}": "#1f77b4", "phase scrambled": "#d62728"}


def delta_power(sig):
    f, p = welch(sig, fs=fs, nperseg=int(4 * fs))
    m = (f >= BAND[0]) & (f < BAND[1])
    return np.trapezoid(p[m], f[m]), f, p

powers = {k: delta_power(v) for k, v in versions.items()}
base = powers["original"][0]
for k, (pw, _, _) in powers.items():
    print(f"{k:20s} delta power ratio vs original = {pw / base:.3f}")

t = np.arange(x.size) / fs + T0
fig = plt.figure(figsize=(17, 10))
gs = fig.add_gridspec(3, 3, width_ratios=[3.2, 1.3, 0.9], hspace=0.35, wspace=0.28)
lim = np.abs(np.concatenate(list(versions.values()))).max() * 1.05
for i, (k, v) in enumerate(versions.items()):
    ax = fig.add_subplot(gs[i, 0])
    ax.plot(t, v, lw=0.6, color=colors[k])
    ax.set_ylim(-lim, lim); ax.set_xlim(T0, T1)
    ax.set_ylabel("µV"); ax.set_title(f"{CH}: {k}", loc="left", color=colors[k], fontsize=12)
    ax.spines[["top", "right"]].set_visible(False)
    if i == 2:
        ax.set_xlabel("time in recording (s), seizure window")

ax = fig.add_subplot(gs[:, 1])
for k, (_, f, p) in powers.items():
    ax.semilogy(f, p, color=colors[k], lw=1.4 if k == "original" else 1.1,
                ls="-" if k != "phase scrambled" else "--", label=k)
ax.axvspan(*BAND, color="#999", alpha=0.15, label="delta band (edited)")
ax.set_xlim(0, 20); ax.set_ylim(5, 3e4); ax.set_xlabel("frequency (Hz)"); ax.set_ylabel("power (µV²/Hz)")
ax.set_title("Power spectrum", loc="left"); ax.legend(fontsize=9, frameon=False)
ax.spines[["top", "right"]].set_visible(False)

ax = fig.add_subplot(gs[:, 2])
names = list(powers)
vals = [powers[k][0] / base for k in names]
ax.bar(range(3), vals, color=[colors[k] for k in names])
for i, v in enumerate(vals):
    ax.text(i, v + 0.02, f"{v:.2f}", ha="center", fontsize=11)
ax.set_xticks(range(3), ["orig", "amp", "scram"]); ax.set_ylim(0, 1.2)
ax.set_title("Delta power\n(relative to original)", loc="left")
ax.spines[["top", "right"]].set_visible(False)

fig.suptitle("Same hotspot, two perturbations: volume-down changes power; "
             "phase scramble keeps power but destroys the rhythm", fontsize=14)
out = outdir / "chb01_03_perturbations.png"
fig.savefig(out, dpi=115, bbox_inches="tight")
print(out)
