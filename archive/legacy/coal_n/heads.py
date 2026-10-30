"""Swappable input heads + multi-domain synthetic data (final product).

Shared core (PLHE/FOU/EME) always sees fixed-dim windows [D]. Each domain
gets a head: sampling params + fitted normalisation. ECG reuses the
existing loaders (including real MIT-BIH when `wfdb` is present); IMU and
vibration are synthetic 1D streams with event masks, same windowing
contract: heads return (X [T,D], y [T], meta).
"""
import numpy as np


class InputHead:
    def __init__(self, name, fs, window, stride):
        self.name = name
        self.fs = fs
        self.window = window
        self.stride = stride
        self.mu = 0.0
        self.sd = 1.0

    def fit(self, raw: np.ndarray):
        self.mu = float(raw.mean())
        self.sd = float(raw.std() + 1e-8)
        return self

    def transform(self, raw: np.ndarray, mask: np.ndarray):
        sig = (raw - self.mu) / self.sd
        W, S = self.window, self.stride
        T = (len(sig) - W) // S + 1
        X = np.stack([sig[i * S:i * S + W] for i in range(T)]).astype(np.float32)
        idx = np.arange(T) * S
        y = np.array([mask[i:i + W].max() for i in idx], dtype=np.int64)
        return X, y, {"source": self.name, "fs": self.fs}


HEADS = {
    # All heads emit the same window dim (D=64) so one shared core serves
    # every domain — that interchangeability is the point of the heads.
    "ecg": InputHead("ecg", fs=360, window=64, stride=4),
    "imu": InputHead("imu", fs=50, window=64, stride=4),
    "vibration": InputHead("vibration", fs=200, window=64, stride=4),
}


def synth_imu(n_samples=3000, fs=50, seed=1):
    """1.2 Hz gait cycle on accel magnitude; fall = spike + level shift."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_samples) / fs
    gait = 0.6 * np.sin(2 * np.pi * 1.2 * t) + 0.25 * np.sin(2 * np.pi * 2.4 * t)
    sig = (1.0 + gait).astype(np.float32)
    mask = np.zeros(n_samples, dtype=np.int64)
    for start in range(600, n_samples - 100, 900):
        dur = 60
        sig[start:start + dur] += (2.5 * rng.standard_normal(dur)).astype(np.float32)
        sig[start + dur:] += 0.4  # post-fall orientation shift (decays below)
        sig[start + dur:start + dur + 200] -= np.linspace(0.4, 0, 200).astype(np.float32)
        mask[start:start + dur + 40] = 1
    sig += (0.05 * rng.standard_normal(n_samples)).astype(np.float32)
    return sig, mask, fs


def synth_vibration(n_samples=6000, fs=200, seed=2):
    """30 Hz rotation + harmonics; bearing fault = periodic burst trains."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_samples) / fs
    sig = (0.8 * np.sin(2 * np.pi * 30 * t)
           + 0.3 * np.sin(2 * np.pi * 60 * t)
           + 0.1 * np.sin(2 * np.pi * 90 * t)).astype(np.float32)
    mask = np.zeros(n_samples, dtype=np.int64)
    for start in range(800, n_samples - 300, 1800):
        for b in range(6):  # burst train, one per revolution-ish
            a0 = start + b * 33
            burst = np.hanning(24) * 2.0 * rng.standard_normal(24)
            sig[a0:a0 + 24] += burst.astype(np.float32)
        mask[start:start + 6 * 33 + 24] = 1
    sig += (0.08 * rng.standard_normal(n_samples)).astype(np.float32)
    return sig, mask, fs


def load_domain(name: str, seed: int = 0):
    """Returns (X, y, meta) with the domain head fitted on the same slice
    (prototype-grade; per-deployment fit happens on train split in SDK)."""
    from . import data as data_mod
    if name == "ecg":
        try:
            return data_mod.load_mitbih_slice()
        except Exception as e:
            print(f"[heads] MIT-BIH unavailable ({type(e).__name__}); "
                  f"synthetic ECG.")
            X, y, meta = data_mod.synthetic_ecg(seed=seed)
            return X, y, meta
    head = HEADS[name]
    if name == "imu":
        raw, mask, _ = synth_imu(seed=seed)
    elif name == "vibration":
        raw, mask, _ = synth_vibration(seed=seed)
    else:
        raise ValueError(name)
    head.fit(raw)
    return head.transform(raw, mask)
