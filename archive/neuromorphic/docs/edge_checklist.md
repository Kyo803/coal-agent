# Edge checklist — from simulated FLOPs to on-device proof

Status: mult-add accounting + CPython latency are measured in CI
(`run_final_eval.py`, `bench/measure_power.py`). The hardware rows below
are procedures, not results — fill them on target silicon.

## 1. Quantisation (runs anywhere)
`quant_bench()` in `coal_n/export.py`: dynamic int8 on the dense twin.
Report: fp32 vs int8 bytes, ms, max logit diff. Gate: diff must not flip
the detector operating point (re-check F1 on int8 logits).

## 2. ONNX export (runs anywhere, needs `pip install onnx onnxruntime`)
`to_onnx()`: exports the dense twin (no data-dependent control flow —
the adaptive scheduler stays in the runtime, same split as production
MoE serving). Verifies max abs diff vs torch when onnxruntime exists.

## 3. TensorRT (needs NVIDIA GPU + TensorRT)
1. `trtexec --onnx=artifact.onnx --saveEngine=artifact.plan --fp16`
2. Compare plan latency vs onnxruntime latency, same batch=1.
3. INT8 calibration: 500 representative windows → calibration cache →
   re-measure + re-check F1.

## 4. Power draw (needs target board)
`python bench/measure_power.py --steps 2000 --out bench/board_run.csv`
- Linux + Intel: RAPL auto-sampled (`intel-rapl:0/energy_uj`).
- NVIDIA: pynvml sampled if installed.
- Jetson/edge (no sensor): power the board through a USB meter, note
  idle vs streaming watts manually, attach the CSV + meter photo to the
  eval report. Target claim format: "X uJ/step streaming, Y% below dense
  on <board>, <precision>".

## 5. Deployment artifact
`CoalN.save(path)` → versioned zip (config + weights + head stats).
Flash the zip + `docs/quickstart.md` inference snippet; never a pickle
of a live object.
