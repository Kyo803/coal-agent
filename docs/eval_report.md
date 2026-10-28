# ROX N evaluation report (generated, all numbers measured)

_epochs=2, wall=18s, CPU CPython. Synthetic ECG/IMU/vibration (MIT-BIH if wfdb present)._

## Per-deployment results (tune shape -> train -> validate)

| domain | top_k | thr_init | experts | learned thr | val F1 | val active |
|---|---|---|---|---|---|---|
| ecg | 32 | 8.0 | 2 | 9.639 | 0.5039 | 0.0055 |
| imu | 16 | 4.0 | 2 | 7.511 | 0.1667 | 0.1179 |
| vibration | 16 | 8.0 | 4 | 9.222 | 0.1654 | 0.1248 |

## Artifact roundtrips (save -> load -> predict)

| domain | max logit diff |
|---|---|
| ecg | 0.00e+00 |
| imu | 0.00e+00 |
| vibration | 0.00e+00 |

## Edge cases (`python -m rox_n.robustness`)

```json
{
  "flatline": {
    "fires_per_step": 0.0,
    "output_frozen": true,
    "f1": 0.0
  },
  "noise_storm": {
    "max_fired": 128,
    "ceiling": 16,
    "units": 128,
    "fallback_rate": 0.1233,
    "unflagged_over_budget": 0,
    "note": "over-ceiling steps exist only as flagged dense fallbacks"
  },
  "long_event": {
    "event_windows": 195,
    "fallback_rate": 0.0407,
    "fallback_fired": true,
    "active": 0.0686
  },
  "domain_shift": {
    "f1_wrong_head": 0.0,
    "note": "quantifies degradation without the right input head"
  }
}
```

## Quantisation bench, dense twin (CPU, dynamic int8)

```json
{
  "fp32_bytes": 40205,
  "int8_bytes": 15667,
  "fp32_ms": 0.0926,
  "int8_ms": 0.5044,
  "max_abs_logit_diff": 0.0066
}
```

## ONNX export

```json
{
  "ok": true,
  "path": "C:\\Users\\WERU1\\OneDrive\\Documents\\Default Project\\ROX-N\\artifacts\\ecg_dense.onnx",
  "bytes": 38861,
  "numeric_check": "max_abs_diff=7.45e-08"
}
```

## Honesty section
- Domains are synthetic except MIT-BIH-if-present; see `load_domain`.
- ms/latency are CPython wall-clock at N=128; mult-adds are the portable claim.
- TensorRT + board power need hardware: `docs/edge_checklist.md`, `bench/measure_power.py`.
