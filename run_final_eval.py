"""Final-product evaluation: trains per-domain deployments, tunes budgets,
validates across domains, runs edge cases + quant bench, writes
docs/eval_report.md with real measured numbers. No hand-waving.

  python run_final_eval.py [--epochs 2]
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

epochs = 2
for a in sys.argv[1:]:
    if a.startswith("--epochs="):
        epochs = int(a.split("=")[1])

from rox_n.sdk import tune_then_train, RoxN  # noqa: E402
from rox_n.heads import load_domain  # noqa: E402
from rox_n import robustness as rob  # noqa: E402
from rox_n import export as expmod  # noqa: E402

t0 = time.time()
domains, artifacts = {}, {}
for dom in ("ecg", "imu", "vibration"):
    det, info = tune_then_train(dom)
    domains[dom] = {"tuned": info["tuned"], "val": info["val"],
                    "final_thr": round(det.streamer.fou.eff_threshold(), 3)}
    ap = os.path.join(HERE, "artifacts", f"{dom}_final.roxn")
    os.makedirs(os.path.join(HERE, "artifacts"), exist_ok=True)
    det.save(ap)
    # roundtrip: reload + compare logits on 64 windows
    X, _, _ = load_domain(dom)
    r1, _ = det.predict_stream(X[:64])
    r2, _ = RoxN.load(ap).predict_stream(X[:64])
    import numpy as np
    artifacts[dom] = {"path": ap,
                      "roundtrip_max_diff": float(np.abs(r1 - r2).max())}
    print(f"[final] {dom}: tuned={info['tuned']} val={info['val']} "
          f"thr={domains[dom]['final_thr']}")

edge = {k: v for k, v in rob.main().items()}
ecg_det = RoxN.load(os.path.join(HERE, "artifacts", "ecg_final.roxn"))
qb = expmod.quant_bench(ecg_det.streamer)
onnx = expmod.to_onnx(ecg_det.streamer,
                       os.path.join(HERE, "artifacts", "ecg_dense.onnx"))

lines = ["# ROX N evaluation report (generated, all numbers measured)",
         "", f"_epochs={epochs}, wall={time.time()-t0:.0f}s, "
         "CPU CPython. Synthetic ECG/IMU/vibration (MIT-BIH if wfdb present)._",
         "", "## Per-deployment results (tune shape → train → validate)",
         "", "| domain | top_k | thr_init | experts | learned thr | val F1 | val active |",
         "|---|---|---|---|---|---|---|"]
for dom, d in domains.items():
    t = d["tuned"]
    lines.append(f"| {dom} | {t['top_k']} | {t['threshold']} | {t['n_experts']} "
                 f"| {d['final_thr']} | {d['val']['f1']} | {d['val']['active']} |")
lines += ["", "## Artifact roundtrips (save → load → predict)",
          "", "| domain | max logit diff |",
          "|---|---|"]
for dom, a in artifacts.items():
    lines.append(f"| {dom} | {a['roundtrip_max_diff']:.2e} |")
lines += ["", "## Edge cases (`python -m rox_n.robustness`)",
          "", "```json", json.dumps(edge, indent=2), "```",
          "", "## Quantisation bench, dense twin (CPU, dynamic int8)",
          "", "```json", json.dumps(qb, indent=2), "```",
          "", "## ONNX export", "", "```json",
          json.dumps(onnx, indent=2), "```",
          "", "## Honesty section",
          "- Domains are synthetic except MIT-BIH-if-present; see `load_domain`.",
          "- ms/latency are CPython wall-clock at N=128; mult-adds are the portable claim.",
          "- TensorRT + board power need hardware: `docs/edge_checklist.md`, "
          "`bench/measure_power.py`.",
          ""]
rep = os.path.join(HERE, "docs", "eval_report.md")
with open(rep, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"[final] wrote {rep}")
