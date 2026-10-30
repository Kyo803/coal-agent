# Coal — Surprise-Gated Neuromorphic Architecture

## Chat track (`lm_track/coal_chat/`): everything code-related, done

`arch.py` (478M/1025M configs verified, train/infer FOU+EME paths, RoPE
default + PLHE flag) · `stage0.py` (PASS: trains, no collapse, PLHE kept)
· `generate.py` (streaming + warmup-calibrated S) · `retrieval.py`
(BM25 + two-stage STR) · `attachments.py` (TME, tool gate, lockout) ·
`sft.py` + `dpo.py` (CPU-tested) · `bpe.py` (CPU-tested) · `evals.py`
(ALL PASS) · `chat.py` (selftest OK) · `PLAN_500M_1B.md` (costs/stages).
Remaining: GPU rental, 32K BPE finish, SFT/DPO runs, human ratings.

## Final product: deployable per-domain artifacts + evaluation report

```powershell
pip install -e ".[mitbih,export]"
python run_final_eval.py            # trains, tunes, validates, writes docs/eval_report.md
```

- `coal_n/train.py` — supervised training: FOU/expert/gate weights + the
  surprise threshold itself (two-sided pressure: idle when quiet, fire on
  labelled events).
- `coal_n/tune.py` — per-deployment sweep (top-k, threshold init, experts):
  cheapest shape within 0.02 of best val F1.
- `coal_n/heads.py` — swappable input heads, one shared core (D=64);
  ECG (MIT-BIH if present, else synthetic) + synthetic IMU/vibration.
- `coal_n/robustness.py` — flatline / noise-storm / long-event /
  wrong-head harness incl. flagged dense fallback (`fallback_patience`).
- `coal_n/export.py` + `bench/measure_power.py` + `docs/edge_checklist.md`
  — ONNX dense-twin export (verified 7.5e-08), int8 bench, power harness.
- `coal_n/sdk.py` — `CoalN` save/load versioned artifacts
  (`artifacts/<domain>_final.coaln`), wrong-head input guard.
- `docs/` — `eval_report.md` (generated numbers), `related_work.md`
  (verified citations), `quickstart.md`, `edge_checklist.md`.
- Current measured state: ECG F1 0.50, IMU 0.17, vibration 0.17 —
  the surprise heuristic suits spiky anomalies; burst-train vibration is
  the known weak domain, stated in the report, not hidden.

## MVP demo: all three mechanisms, live, one shared surprise signal

```powershell
cd Coal
pip install -r requirements.txt   # torch, numpy, matplotlib only; server is stdlib
python run_demo.py --smoke        # headless check: 600 streamed steps + stage gates
python run_demo.py                # live demo on http://localhost:8137
```

Stage flow: watch idle (FOU grid dark, EME ECHO, PLHE HOLD, ~97% mult-adds
saved) → press **⚡ INJECT ANOMALY** → surprise spikes, units fire, EME
RE-EVALs all 4 experts, PLHE RE-LOCKs → settles back to idle.

- `coal_n/plhe.py` — helix embedding, phase-integrated, freq re-estimated
  immediately iff shared S > threshold else every 8th quiet step.
- `coal_n/eme.py` — 4 experts; incumbent reused with gate skipped iff shared
  S <= threshold, else full re-evaluation + all-expert mix.
- `coal_n/stream.py` — timestep-by-timestep runner, dense baseline
  side-by-side, analytic mult-add counts + wall ms/step for both paths.
- `demo/index.html` — signal trace, surprise trace, 32-cell unit grid,
  expert pills, FLOPs/latency numbers, inject button.

Honesty notes for stage: headline = analytic mult-adds saved (hardware
relevant). The ms/step readout is CPython wall-clock at N=128 — at this
toy scale Python gating overhead exceeds the matmul savings, so dense can
read faster; sparsity pays on hardware/at scale, not in a tiny CPU loop.
Accuracy target is *close to* baseline, not beating it (smoke gate:
F1_coal >= F1_den − 0.15).

## Prototype (days 0-2): Delta-Gated Fire-Once Units in isolation

**Goal:** prove the surprise gate correlates with real events — nothing else.

- One invention only: **Delta-Gated Fire-Once Units (FOUs)** with a global top-k surprise budget.
- One dataset slice: MIT-BIH ECG record 100 via `wfdb`, with **synthetic fallback** (no download needed).
- Batch inference only, no streaming server, no UI.
- Hard-coded hyperparams in `coal_n/config.py`. No tuning infra.
- Success = `outputs/surprise_vs_labels.png` shows surprise spiking on labelled anomalies,
  plus `outputs/metrics.json` with active-compute fraction and surprise↔label correlation.

### Quickstart

```powershell
cd Coal
pip install -r requirements.txt
python run_prototype.py
# or: python -m coal_n.evaluate
```

Outputs:
- `outputs/surprise_vs_labels.png` — surprise score over time vs ground-truth anomaly labels
- `outputs/active_fraction.png` — fraction of units fired per timestep
- `outputs/metrics.json` — mean active fraction, FLOPs saved, F1 / correlation of surprise as detector

### Layout

```
Coal/
  coal_n/
    config.py      # hard-coded hyperparams (top-k, threshold, dims)
    fou.py         # Delta-Gated Fire-Once layer + dense baseline
    baseline.py    # (thin wrapper — dense reference uses same weights)
    data.py        # MIT-BIH slice loader + synthetic ECG fallback
    evaluate.py    # batch eval: surprise trace, metrics, plots
  run_prototype.py # one-command entry point
  notebooks/
    prototype_fou.ipynb  # same eval, notebook form
  outputs/         # generated plots + metrics
```

### What FOU does (prototype semantics)

Per timestep `t`, input window `x_t in R^D`, `N` units:

1. Cheap surprise per unit: `s_i = ||x_t - x_cache_i||_2` (raw L2; the proposal's
   `1 - cos_sim` saturates on overlapping sliding windows — see `coal_n/fou.py` header).
2. Fire set = top-`k` units among those with `s_i > threshold`. If none exceed, **fire zero** (fully idle — this is the "boring world" savings).
3. Fired units compute `y_i = ReLU(W_i x_t + b_i)`, update `x_cache_i` and `y_cache_i`. Unfired return `y_cache_i`.
4. Global trace `S_t = min(s_i)` (distance to best-matching cache) is what we plot against anomaly labels.

Dense baseline = same `W, b`, computes all `N` units every step (active fraction = 1.0).

### Prototype scope (deliberately excluded)

No PLHE, no EME, no live streaming, no demo UI, no training loop.
PLHE/EME hook into the same `S_t` signal later — `fou.py` already exposes it.
