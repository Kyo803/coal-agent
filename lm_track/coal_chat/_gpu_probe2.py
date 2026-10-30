import sys, io, json, urllib.request, time, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

def get_server_pid():
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
        "(Get-Process llama-server -ErrorAction SilentlyContinue).Id"],
        capture_output=True, text=True, timeout=10)
    return r.stdout.strip()

def sample_all(seconds=4):
    ps = ('Get-Counter \'\\GPU Engine(*)\\Utilization Percentage\' '
          '-SampleInterval 1 -MaxSamples ' + str(int(seconds)) +
          ' | Select-Object -ExpandProperty CounterSamples | '
          'Where-Object { $_.CookedValue -gt 0.5 } | '
          'ForEach-Object { "$($_.InstanceName)|$([math]::Round($_.CookedValue,1))" }')
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, timeout=60)
    return r.stdout.splitlines()

pid = get_server_pid()
print("llama-server PID:", pid)

payload = {"model": "x", "stream": False, "max_tokens": 400,
           "temperature": 0.4,
           "messages": [{"role": "user", "content":
                         "Write a 400-word essay about the history of robotics."}]}
req = urllib.request.Request("http://127.0.0.1:1234/v1/chat/completions",
                             data=json.dumps(payload).encode(),
                             headers={"Content-Type": "application/json"},
                             method="POST")
import threading
result = {}
def gen():
    with urllib.request.urlopen(req, timeout=900) as r:
        result["data"] = json.loads(r.read().decode())
th = threading.Thread(target=gen)
print("generating, sampling GPU engine counters...")
th.start()
found_server_gpu = False
while th.is_alive():
    lines = sample_all(3)
    for l in lines:
        if pid in l:
            found_server_gpu = True
            print("  llama-server GPU:", l)
th.join()
print("generation done.")
print("llama-server used GPU engine:", found_server_gpu)