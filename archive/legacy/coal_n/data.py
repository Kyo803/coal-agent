"""ECG data: MIT-BIH slice via wfdb, synthetic fallback.

Returns windows X [T, D], labels y [T] (1 = anomaly window), meta dict.
Synthetic fallback needs no downloads: 70 bpm quasi-periodic beats with
injected wide-QRS anomalies every ~2.5 s, so the surprise trace has
ground truth to correlate against.
"""
import numpy as np


def _windows(sig: np.ndarray, window: int, stride: int):
    T = (len(sig) - window) // stride + 1
    X = np.stack([sig[i * stride:i * stride + window] for i in range(T)])
    return X.astype(np.float32)


def load_mitbih_slice(record="100", n_samples=5000, window=64, stride=4):
    import wfdb
    rec = wfdb.rdrecord(record, pn_dir="mitdb",
                        sampfrom=0, sampto=n_samples)
    sig = np.asarray(rec.p_signal[:, 0], dtype=np.float32)
    ann = wfdb.rdann(record, "atr", pn_dir="mitdb",
                     sampfrom=0, sampto=n_samples)
    # Abnormal beat symbols in MIT-BIH: anything not N/L/R/B (normal-ish).
    abnormal = set(list("VSFJEQCanxsA")) | {"V", "S", "F", "Q", "E", "J", "C", "a"}
    peak = np.zeros(len(sig), dtype=np.int64)
    for s, sym in zip(ann.sample, ann.symbol):
        if 0 <= s < len(sig) and sym in abnormal and sym != "N":
            # mark +-36 samples (~100 ms) around ectopic beat
            peak[max(0, s - 36):s + 36] = 1
    X = _windows(sig, window, stride)
    # window label = 1 if any abnormal sample inside
    idx = np.arange(len(X)) * stride
    y = np.array([peak[i:i + window].max() for i in idx], dtype=np.int64)
    # z-normalise windows with global stats (no per-window leakage tricks)
    mu, sd = float(sig.mean()), float(sig.std() + 1e-8)
    return (X - mu) / sd, y, {"source": f"mitdb/{record}", "fs": rec.fs}


def synthetic_ecg(n_samples=5000, fs=360, window=64, stride=4, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n_samples) / fs
    sig = np.zeros(n_samples, dtype=np.float32)
    period = int(fs * 60 / 70)  # 70 bpm
    # PQRST-ish template: small P, sharp R, wide T
    L = min(period, 200)
    beat = np.zeros(L, dtype=np.float32)
    beat[L // 4] = 0.15
    beat[L // 2] = 1.0
    beat[L // 2 + 1] = -0.25
    beat[L * 3 // 4] = 0.3
    import math
    anomaly_at = []
    for start in range(0, n_samples - L, period):
        # drift + noise = quasi-periodic, mostly stable
        wob = 1.0 + 0.05 * math.sin(2 * math.pi * start / (period * 8))
        sig[start:start + L] += (wob * beat).astype(np.float32)
        if (start // period) % 8 == 7:  # every ~8th beat: injected anomaly
            a0 = start + L // 2 - 10
            sig[a0:a0 + 40] += (1.6 * rng.standard_normal(40)).astype(np.float32)
            anomaly_at.append(start)
    sig += (0.03 * rng.standard_normal(n_samples)).astype(np.float32)
    peak = np.zeros(n_samples, dtype=np.int64)
    for s in anomaly_at:
        peak[s:s + L] = 1
    X = _windows(sig, window, stride)
    idx = np.arange(len(X)) * stride
    y = np.array([peak[i:i + window].max() for i in idx], dtype=np.int64)
    mu, sd = float(sig.mean()), float(sig.std() + 1e-8)
    return (X - mu) / sd, y, {"source": "synthetic_70bpm", "fs": fs}


def load(cfg):
    """Try MIT-BIH, fall back to synthetic (offline-safe)."""
    try:
        return load_mitbih_slice(cfg.record, cfg.n_samples, cfg.window, cfg.stride)
    except Exception as e:
        if not cfg.synthetic_if_missing:
            raise
        print(f"[data] MIT-BIH unavailable ({type(e).__name__}: {e}); using synthetic ECG.")
        return synthetic_ecg(cfg.n_samples, cfg.fs, cfg.window, cfg.stride, seed=cfg.seed)
