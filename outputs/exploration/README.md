# Exploration: first look at CHB-MIT (chb01_03)

Hand-run exploration from 2026-11-17. **Not pipeline code and not a scientific result:** one seizure from one
patient, with illustrative (uncalibrated) band edges and perturbation strengths. See `../../ROADMAP.md` for
where this leads.

## Figures

| File | What it shows |
|---|---|
| `chb01_03_control_vs_seizure.png` | 22 channels, 30 s control (2600–2630 s) vs. 30 s seizure (2996–3026 s), identical µV scale |
| `traces.png` | 18 channels from 20 s before to 10 s after the annotated seizure (2996–3036 s) |
| `hotspots.png` | log10(seizure / pre-seizure power) per channel × band. Right temporal (F8-T8, T8-P8, FT10-T8, FT9-FT10) leads |
| `chb01_03_perturbations.png` | F8-T8 delta: original vs amplitude ×0.5 (power ratio 0.25) vs phase scramble (power ratio 1.03, waveform destroyed) |

## Reproduce

The raw EDF (~42 MB) is gitignored. Fetch it from PhysioNet (public, no login):

```bash
mkdir -p data/raw/chbmit/chb01 && cd data/raw/chbmit/chb01
B=https://physionet.org/files/chbmit/1.0.0/chb01
curl -fLO $B/chb01-summary.txt && curl -fLO $B/chb01_03.edf
cd ../../../..
```

Environment (run from the repo root):

```bash
python3 -m venv .venv && .venv/bin/pip install mne numpy scipy pandas scikit-learn matplotlib
```

Regenerate the figures:

```bash
E=data/raw/chbmit/chb01/chb01_03.edf; O=outputs/exploration
.venv/bin/python -I $O/explore_chb01_03.py        $E $O   # traces.png, hotspots.png
.venv/bin/python -I $O/plot_control_vs_seizure.py $E $O   # chb01_03_control_vs_seizure.png
.venv/bin/python -I $O/plot_perturbations.py      $E $O   # chb01_03_perturbations.png
```

Tested with Python 3.14.3 and MNE 1.13.2. CLAUDE.md specifies 3.11, which is not yet verified here.

## Data quirk noted

CHB-MIT lists `T8-P8` twice. MNE renames the copies `T8-P8-0` / `T8-P8-1`. `plot_control_vs_seizure.py` drops
the second copy; `explore_chb01_03.py` keeps both (they show identical values in `hotspots.png`).
