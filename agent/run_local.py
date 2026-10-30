"""Coal — single local entry point. Everything runs on your machine.

  python run_local.py                # auto-pick best backend
  python run_local.py --backend qwen # force local LM Studio (Qwen/Gemma)
  python run_local.py --backend v2 --model ckpt_v2/v2.pt   # our 500M
  python run_local.py --status       # show what's available

Backends:
  qwen : local LM Studio server (Qwen3.6-35B-A3B etc.) — smart, all
         inference features + direct memory tool calls
  v2   : our from-scratch 500M (FOU/EME/PLHE) — carries the inventions
  hf   : small HF instruct model — fallback
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def probe():
    status = {}
    # local model servers (LM Studio + Ollama), auto-detected
    try:
        from qwen_backend import autodetect
        url, kind, model, models = autodetect()
        status["local_llm"] = {"up": url is not None, "kind": kind,
                               "url": url, "model": model, "models": models}
    except Exception as e:
        status["local_llm"] = {"up": False, "error": str(e)}
    # our 500M checkpoints
    cks = []
    for d in ("ckpt_v2", "coal_500m"):
        p = os.path.join(HERE, d)
        if os.path.isdir(p):
            for f in os.listdir(p):
                if f.endswith(".pt"):
                    cks.append(os.path.join(d, f))
    status["v2_checkpoints"] = cks
    # hf
    try:
        import transformers  # noqa: F401
        status["hf"] = {"available": True}
    except Exception:
        status["hf"] = {"available": False}
    return status


def pick_backend(status):
    if status.get("local_llm", {}).get("up"):
        return "qwen"
    if status.get("v2_checkpoints"):
        return "v2"
    if status.get("hf", {}).get("available"):
        return "hf"
    return "qwen"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default=None,
                    choices=["qwen", "v2", "hf"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--mem-root", default="~/.coal")
    args = ap.parse_args()

    status = probe()
    if args.status:
        import json
        print(json.dumps(status, indent=1))
        return

    backend = args.backend or pick_backend(status)
    print(f"[run_local] backend={backend}")
    qwen_url = qwen_model = None
    if backend == "qwen":
        llm = status.get("local_llm", {})
        if llm.get("up"):
            qwen_url, qwen_model = llm["url"], llm["model"]
            print(f"  -> local server: {llm['kind']} ({qwen_url}) "
                  f"model={qwen_model}")
        else:
            print("  -> no local server found. Start LM Studio (port 1234) "
                  "or Ollama (port 11434).")

    from chat_v2 import CoalV2
    model = args.model
    if backend == "v2" and not model:
        cks = status.get("v2_checkpoints", [])
        model = os.path.join(HERE, cks[-1]) if cks else None
    r = CoalV2(model, backend, args.mem_root,
              qwen_url=qwen_url, qwen_model=qwen_model)
    print(f"Coal ready (backend={backend}). 'quit' exits. "
          f"memory: {r.mem.store.stats()}")
    while True:
        try:
            u = input("you: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if u.lower() in ("quit", "exit"):
            break
        if not u:
            continue
        out, st = r.respond(u)
        print(f"coal [{st}]: {out}")
    r.close()


if __name__ == "__main__":
    main()
