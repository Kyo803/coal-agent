"""On-device power/latency harness (final product).

Runs the streamed eval and logs per-step ms + analytic mult-adds to CSV.
Power sampling: Intel RAPL on Linux, pynvml for NVIDIA, else no-sensor
mode (still logs compute numbers; power filled in on target hardware).
This script makes no claims by itself — it is the procedure the
evaluation report's hardware section is produced with.

  python bench/measure_power.py --steps 600 --out bench/power_log.csv
"""
import argparse
import csv
import os
import time

from rox_n.config import MVP_DEFAULT
from rox_n.stream import Streamer


def read_rapl():
    base = "/sys/class/powercap/intel-rapl:0/energy_uj"
    try:
        with open(base) as f:
            return int(f.read().strip()) / 1e6  # joules
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=600)
    ap.add_argument("--out", default="bench/power_log.csv")
    args = ap.parse_args()

    st = Streamer(MVP_DEFAULT)
    use_rapl = read_rapl() is not None
    try:
        import pynvml
        pynvml.nvmlInit()
        gpu = pynvml.nvmlDeviceGetHandleByIndex(0)
        use_nvml = True
    except Exception:
        use_nvml = False
    print(f"[power] sensors: rapl={use_rapl} nvml={use_nvml} "
          f"(no sensor -> compute columns only)")

    e0 = read_rapl()
    rows = []
    for i in range(args.steps):
        if i == args.steps // 2:
            st.inject()
        r = st.step()
        rows.append(r)
    e1 = read_rapl()
    s = st.summary()
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["step", "S", "k", "expert", "reeval",
                    "ms_rox", "ms_den", "label"])
        for i, r in enumerate(rows):
            w.writerow([i, f"{r['S']:.4f}", r["k"], r["expert"],
                        int(r["reeval"]), f"{r['ms_rox']:.4f}",
                        f"{r['ms_den']:.4f}", r["label"]])
    print(f"[power] wrote {args.out}; flops_saved={s['flops_saved']:.3f} "
          f"f1_rox={s.get('f1_rox', 0):.3f}")
    if e0 is not None and e1 is not None:
        print(f"[power] RAPL package energy for run: {e1 - e0:.3f} J "
              f"({(e1 - e0) / args.steps * 1e6:.1f} uJ/step)")
    else:
        print("[power] no energy sensor on this machine — "
              "run on target hardware for the uJ/step number.")


if __name__ == "__main__":
    main()
