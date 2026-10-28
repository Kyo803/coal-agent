import sys, io, json, urllib.request, time, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")

def sample_gpu(seconds=1):
    """Sample GPU 3D engine utilization via PowerShell counter."""
    ps = 'Get-Counter \'\\GPU Engine(*)\\Utilization Percentage\' ' \
         '-SampleInterval 0.5 -MaxSamples ' + str(int(seconds * 2)) + \
         ' | Select-Object -ExpandProperty CounterSamples | ' \
         'Where-Object { $_.InstanceName -match "engtype_3d" -and ' \
         '$_.CookedValue -gt 0 } | Measure-Object -Property CookedValue ' \
         '-Average -Maximum | Select-Object Average, Maximum | ConvertTo-Json'
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=20)
        d = json.loads(r.stdout or "{}")
        return d
    except Exception as e:
        return {"error": str(e)}

# start a long generation, then sample GPU during it
payload = {"model": "x", "stream": False, "max_tokens": 400,
           "temperature": 0.4,
           "messages": [{"role": "user", "content":
                         "Write a 400-word essay about the history of "
                         "robotics in detail."}]}
req = urllib.request.Request("http://127.0.0.1:1234/v1/chat/completions",
                             data=json.dumps(payload).encode(),
                             headers={"Content-Type": "application/json"},
                             method="POST")
print("starting generation, sampling GPU during it...")
t0 = time.time()
# run the generation in a thread so we can sample
import threading
result = {}
def gen():
    with urllib.request.urlopen(req, timeout=900) as r:
        result["data"] = json.loads(r.read().decode())
th = threading.Thread(target=gen)
th.start()
samples = []
while th.is_alive():
    s = sample_gpu(1.0)
    if s and not s.get("error"):
        samples.append(s)
    time.sleep(0.5)
th.join()
print("generation wall:", round(time.time() - t0, 1), "s")
if samples:
    avgs = [s.get("Average") or 0 for s in samples]
    maxs = [s.get("Maximum") or 0 for s in samples]
    print(f"GPU 3D utilization during generation: avg={max(avgs):.1f}% "
          f"max={max(maxs):.1f}% over {len(samples)} samples")
else:
    print("no GPU samples captured")