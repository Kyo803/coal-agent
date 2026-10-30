"""Coal-Compute worker — runs in the ML venv (Python 3.12 + onnxruntime).

Protocol: read ONE JSON object from stdin, write ONE JSON line to stdout.
Ops:
    ping        -> {ok, python, onnxruntime}
    probe       -> {ok, providers, devices}
    benchmark   -> {ok, directml:{ms_per_iter}, cpu:{ms_per_iter}, speedup}
    sd_generate -> text->image (Stable Diffusion ONNX); see sd.py
    depth       -> monocular depth from an image (ONNX)
"""
from __future__ import annotations

import json
import os
import sys
import time


def _ort():
    import onnxruntime as ort
    return ort


def op_ping(_):
    import platform
    try:
        import onnxruntime as ort
        ver = ort.__version__
    except Exception as e:
        ver = f"missing: {e}"
    return {"ok": True, "python": sys.version.split()[0],
            "platform": platform.platform(), "onnxruntime": ver}


def op_probe(_):
    ort = _ort()
    provs = ort.get_available_providers()
    devs = {}
    try:
        devs = ort.get_device()
    except Exception:
        pass
    return {"ok": True, "providers": provs, "device": devs}


def _conv_model(path, ch=32, size=256):
    """A small conv stack used purely to measure real GPU throughput."""
    import onnx
    from onnx import TensorProto, helper
    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 3, size, size])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT,
                                      [1, ch, size, size])
    nodes, inits = [], []
    prev = "x"
    prev_c = 3
    for i in range(4):
        w = helper.make_tensor(
            f"w{i}", TensorProto.FLOAT, [ch, prev_c, 3, 3],
            [((j % 9) - 4) * 0.01 for j in range(ch * prev_c * 9)])
        b = helper.make_tensor(f"b{i}", TensorProto.FLOAT, [ch],
                               [0.0] * ch)
        inits += [w, b]
        nodes.append(helper.make_node(
            "Conv", [prev, f"w{i}", f"b{i}"], [f"c{i}"],
            kernel_shape=[3, 3], pads=[1, 1, 1, 1]))
        relu_out = "y" if i == 3 else f"r{i}"
        nodes.append(helper.make_node("Relu", [f"c{i}"], [relu_out]))
        prev, prev_c = relu_out, ch
    graph = helper.make_graph(nodes, "roxbench", [x], [y], inits)
    model = helper.make_model(graph, opset_imports=[
        helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.save(model, path)
    return path


def op_benchmark(req):
    import numpy as np
    ort = _ort()
    size = int(req.get("size", 256))
    iters = int(req.get("iters", 20))
    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "_bench_conv.onnx")
    _conv_model(model_path, size=size)
    x = np.random.rand(1, 3, size, size).astype(np.float32)
    results = {}
    for name, prov in (("directml", "DmlExecutionProvider"),
                       ("cpu", "CPUExecutionProvider")):
        if prov not in ort.get_available_providers():
            continue
        try:
            so = ort.SessionOptions()
            so.graph_optimization_level = \
                ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess = ort.InferenceSession(model_path, so, providers=[prov])
            inp = sess.get_inputs()[0].name
            sess.run(None, {inp: x})                     # warmup
            t0 = time.time()
            for _ in range(iters):
                sess.run(None, {inp: x})
            ms = (time.time() - t0) / iters * 1000.0
            results[name] = round(ms, 2)
        except Exception as e:
            results[name] = f"error: {str(e)[:120]}"
    out = {"ok": True, "size": size, "iters": iters, "ms_per_iter": results}
    if isinstance(results.get("directml"), float) and \
            isinstance(results.get("cpu"), float):
        out["speedup"] = round(results["cpu"] / results["directml"], 2)
    return out


OPS = {"ping": op_ping, "probe": op_probe, "benchmark": op_benchmark}


def main():
    raw = sys.stdin.read()
    try:
        req = json.loads(raw) if raw.strip() else {"op": "ping"}
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"bad json: {e}"}))
        return
    op = req.get("op", "ping")
    fn = OPS.get(op)
    if fn is None:
        # lazy import for the heavy ops so probe/benchmark stay fast
        if op in ("sd_generate", "sd_generate_tiled", "sd_generate_hd",
                  "sd_tile_upscale", "sd_character_sheet", "depth"):
            try:
                from sd import dispatch
                print(json.dumps(dispatch(op, req)))
            except Exception as e:
                print(json.dumps({"ok": False, "error": str(e)[:400]}))
        else:
            print(json.dumps({"ok": False, "error": f"unknown op {op}"}))
        return
    try:
        print(json.dumps(fn(req)))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)[:400]}))


if __name__ == "__main__":
    main()
