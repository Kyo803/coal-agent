# ROX N quickstart (final product)

```powershell
pip install -e .                    # core only
pip install -e ".[mitbih,export]"   # + real ECG data, ONNX checks
```

```python
from rox_n.sdk import tune_then_train, RoxN

# One deployment: tune shape on validation, train, evaluate.
det, info = tune_then_train("ecg")
print(info["tuned"], info["val"])

# Ship it.
det.save("artifacts/ecg_v1.roxn")
restored = RoxN.load("artifacts/ecg_v1.roxn")
logits, fired = restored.predict_stream(X_new)
```

Live stage demo (unchanged): `python run_demo.py`
Full evaluation → `docs/eval_report.md`: `python run_final_eval.py`
Edge cases: `python -m rox_n.robustness`
Power harness: `python bench/measure_power.py`
