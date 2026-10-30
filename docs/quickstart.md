# Coal quickstart (final product)

```powershell
pip install -e .                    # core only
pip install -e ".[mitbih,export]"   # + real ECG data, ONNX checks
```

```python
from coal_n.sdk import tune_then_train, CoalN

# One deployment: tune shape on validation, train, evaluate.
det, info = tune_then_train("ecg")
print(info["tuned"], info["val"])

# Ship it.
det.save("artifacts/ecg_v1.coaln")
restored = CoalN.load("artifacts/ecg_v1.coaln")
logits, fired = restored.predict_stream(X_new)
```

Live stage demo (unchanged): `python run_demo.py`
Full evaluation → `docs/eval_report.md`: `python run_final_eval.py`
Edge cases: `python -m coal_n.robustness`
Power harness: `python bench/measure_power.py`
