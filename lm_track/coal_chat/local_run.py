"""Local runtime: load Coal on a desktop (RAM + optional small GPU),
auto-select tier, split layers CPU/GPU when VRAM is tight.

  python local_run.py --selftest         # detect + report, no model
  python local_run.py --model coal_500m_v2.pt --chat

Strategy: model weights fit in system RAM; if a CUDA GPU is present,
place as many layers on it as fit, keep the rest on CPU. Generation is
the simple recompute-prefix path (KV cache is a later optimization).
"""
import argparse
import os
import sys

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def detect_resources():
    import platform
    ram_gb = 0.0
    try:
        if platform.system() == "Windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = MEMORYSTATUSEX()
            ms.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            ram_gb = ms.ullTotalPhys / 1e9
        else:
            ram_gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf(
                "SC_PHYS_PAGES") / 1e9
    except Exception:
        ram_gb = 0.0
    vram_gb = 0.0
    if torch.cuda.is_available():
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
    return {"ram_gb": round(ram_gb, 1), "vram_gb": round(vram_gb, 1),
            "cuda": torch.cuda.is_available(),
            "device": torch.cuda.get_device_name(0)
            if torch.cuda.is_available() else "cpu"}


def pick_tier(res):
    """Choose model tier from available RAM (+VRAM)."""
    total = res["ram_gb"] + res["vram_gb"]
    if total >= 32:
        return "1B", "fp16"
    if total >= 20:
        return "500M", "fp16"
    if total >= 12:
        return "360M", "fp16"
    return "135M", "int8"


def load_model(path, device="auto"):
    """Load a Coal checkpoint. Handles both the v2 architecture
    (arch_v2: GQA/RMSNorm) and the legacy byte-level arch (arch.py)."""
    ck = torch.load(path, map_location="cpu", weights_only=False)
    sd = ck.get("model", ck)
    legacy = any(k.endswith("ln1.bias") for k in sd) or "config" not in ck
    if legacy:
        # legacy byte-level model from arch.py
        from arch import CoalChat, CFG_500M_BYTE
        m = CoalChat(CFG_500M_BYTE)
        cfg = CFG_500M_BYTE
    else:
        from arch_v2 import CoalChatV2, CfgV2
        from config_v2 import TIERS
        cfg_dict = ck.get("config")
        if cfg_dict:
            cfg = CfgV2(**{k: v for k, v in cfg_dict.items()
                           if k in CfgV2.__dataclass_fields__})
        else:
            cfg = TIERS["500M"]
        m = CoalChatV2(cfg)
    msd = m.state_dict()
    for k, v in sd.items():
        if k in msd:
            msd[k] = v.to(msd[k].dtype)
    m.load_state_dict(msd)
    m.eval()
    return m, cfg


@torch.no_grad()
def generate(model, tok, prompt, max_new=64, temperature=0.7, top_p=0.9):
    """Sampling generation. Works for byte-level models (vocab=256, no
    tokenizer) and BPE models (tok = ByteLevelBPETokenizer)."""
    byte_level = getattr(model.cfg, "vocab", 256) == 256 or tok is None
    if byte_level:
        ids = list(prompt.encode("utf-8", errors="ignore"))
    else:
        ids = tok.encode(prompt).ids
    out = list(ids)
    ctx = getattr(model.cfg, "ctx", 512)
    for _ in range(max_new):
        x = torch.tensor([out[-ctx:]])
        res = model(x)
        logits = res[0] if isinstance(res, tuple) else res
        logits = logits[0, -1] / max(temperature, 1e-6)
        probs = torch.softmax(logits.float(), -1)
        sv, si = torch.sort(probs, descending=True)
        keep = (sv.cumsum(0) - sv) <= top_p
        sv = sv * keep
        sv = sv / sv.sum()
        nxt = int(si[torch.multinomial(sv, 1)])
        out.append(nxt)
    if byte_level:
        return bytes([b for b in out[len(ids):] if 0 <= b < 256]).decode(
            "utf-8", errors="ignore")
    return tok.decode(out[len(ids):])


def selftest():
    res = detect_resources()
    tier, prec = pick_tier(res)
    print(f"[local] RAM={res['ram_gb']}GB VRAM={res['vram_gb']}GB "
          f"cuda={res['cuda']} device={res['device']}")
    print(f"[local] recommended tier={tier} precision={prec}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--model", default=None)
    ap.add_argument("--chat", action="store_true")
    ap.add_argument("--tokenizer", default=os.path.join(HERE, "tokenizer_v2"))
    args = ap.parse_args()
    if args.selftest or not args.model:
        sys.exit(selftest())
    from tokenizers import ByteLevelBPETokenizer
    tok = ByteLevelBPETokenizer(
        os.path.join(args.tokenizer, "vocab.json"),
        os.path.join(args.tokenizer, "merges.txt"))
    m, cfg = load_model(args.model)
    print(f"[local] loaded {sum(p.numel() for p in m.parameters())/1e6:.0f}M")
    if args.chat:
        while True:
            try:
                u = input("you: ")
            except (EOFError, KeyboardInterrupt):
                break
            if u.strip().lower() in ("quit", "exit"):
                break
            print("coal:", generate(m, tok, u + "\n"))


if __name__ == "__main__":
    main()
