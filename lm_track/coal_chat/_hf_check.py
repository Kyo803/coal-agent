import json
import urllib.request

TARGET = {"num_hidden_layers": 40, "hidden_size": 2048,
          "num_local_experts": 256, "num_experts_per_tok": 8,
          "num_attention_heads": 16, "num_key_value_heads": 2,
          "vocab_size": 152064}


def cfg(repo):
    try:
        req = urllib.request.Request(
            "https://huggingface.co/" + repo + "/resolve/main/config.json",
            headers={"User-Agent": "coal"})
        return json.loads(urllib.request.urlopen(req, timeout=25).read().decode())
    except Exception as e:
        return {"error": str(e)}


def sizes(repo):
    try:
        req = urllib.request.Request(
            "https://huggingface.co/api/models/" + repo,
            headers={"User-Agent": "coal"})
        return json.loads(urllib.request.urlopen(req, timeout=25).read().decode())
    except Exception as e:
        return {"error": str(e)}


print("target (from GGUF):", TARGET)
for repo in ["Qwen/Qwen3.6-35B-A3B", "Qwen/Qwen3.6-35B-A3B-Base"]:
    c = cfg(repo)
    if "error" in c:
        print(f"{repo} -> ERR {c['error'][:50]}")
        continue
    got = {k: c.get(k) for k in TARGET}
    st = sizes(repo)
    n_sf = sum(1 for s in st.get("siblings", []) if s.get("rfilename", "").endswith(".safetensors"))
    print(f"{repo} -> layers={c.get('num_hidden_layers')} "
          f"experts={c.get('num_local_experts')} top={c.get('num_experts_per_tok')} "
          f"hidden={c.get('hidden_size')} heads={c.get('num_attention_heads')} "
          f"kv={c.get('num_key_value_heads')} vocab={c.get('vocab_size')} "
          f"type={c.get('model_type')} safetensors={n_sf} "
          f"| {'MATCH' if got == TARGET else 'no'}")