"""Hard-coded hyperparameters for the days 0-2 FOU prototype + MVP demo.

Prototype config untouched. MVP adds one frozen dataclass below.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # Data
    record: str = "200"          # MIT-BIH record to try first (frequent
                               # ventricular ectopy in first 5K samples;
                               # record 100 is nearly all-normal there)
    fs: int = 360                # MIT-BIH sample rate
    n_samples: int = 5000        # stream length (~14 s @360Hz)
    window: int = 64             # input dim D (sliding window over raw ECG)
    stride: int = 4              # window step; smaller = smoother traces
    synthetic_if_missing: bool = True

    # Model
    n_units: int = 128           # N FOU units in the single test layer
    seed: int = 0

    # Gating (the two hard-coded knobs from the proposal)
    top_k: int = 16              # hard compute ceiling: <= k units fire per step
    threshold: float = 8.0       # raw-L2 surprise floor; stable consec-window
                                 # delta averages ~3 (p95 ~7.6), anomalies ~20+,
                                 # so quiet rhythm mostly idles, events fire
    eps: float = 1e-8


DEFAULT = Config()


@dataclass(frozen=True)
class MVPConfig:
    """One shared surprise threshold drives FOU firing, PLHE re-lock and
    EME re-routing — that shared signal is the demo's headline claim."""
    base: Config = DEFAULT
    n_experts: int = 4           # EME experts (simplified: 4, not dozens)
    eme_lambda: float = 2.0      # hysteresis bonus for the incumbent expert
    plhe_hold: int = 8           # re-estimate freq at most every K quiet steps
    trace_len: int = 600         # ring-buffer length for the front-end
    unit_cells: int = 32         # downsampled active/idle grid cells
    steps_per_sec: float = 30.0  # live pacing for the demo
    inject_len: int = 25         # windows per on-demand anomaly burst
    inject_amp: float = 1.6


MVP_DEFAULT = MVPConfig()
