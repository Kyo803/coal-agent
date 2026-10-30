# compute — heavy media worker

ONNX/image generation kept out of the main interpreter.

`worker.py` (subprocess worker), `sd.py` (image generation),
`export_onnx.py`, `fetch_models.py`. Models are optional; the ladder
falls back to procedural output when none are installed.
