"""Binary triage: inspect a PE/ELF without running it.

Reads headers and sections directly with struct, hashes the file, extracts
strings, and looks for capability indicators (process injection, keylogging,
crypto/extortion, persistence, packing). Optional Intel disassembly of one
symbol with objdump.

This is a heuristic triage aid, never a verdict, and it never executes the
sample.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import struct
import subprocess

# API / string groups that matter during triage
CAPS = {
    "process_injection": ["VirtualAllocEx", "WriteProcessMemory",
                          "CreateRemoteThread", "NtCreateThreadEx",
                          "QueueUserAPC", "SetThreadContext"],
    "keylogging": ["SetWindowsHookEx", "GetAsyncKeyState", "GetKeyState",
                   "GetKeyboardState", "WH_KEYBOARD"],
    "crypto": ["CryptEncrypt", "CryptGenKey", "CryptAcquireContext",
               "BCryptEncrypt", "BCryptGenerateSymmetricKey"],
    "persistence": ["RegSetValue", "CurrentVersion\\Run", "schtasks",
                    "CreateService", "Startup"],
    "network": ["InternetOpen", "WinHttpOpen", "URLDownloadToFile",
                "WSAStartup", "connect", "socket"],
    "evasion": ["IsDebuggerPresent", "CheckRemoteDebuggerPresent",
                "VirtualProtect", "NtQueryInformationProcess"],
    "extortion": ["bitcoin", "wallet", "ransom", "decrypt", "payment",
                  "your files"],
    "shells": ["powershell", "cmd.exe", "/bin/sh", "bash -c", "nc -e"],
}

SUSPICIOUS_STRINGS = [
    (re.compile(r"https?://[^\s\"'<>]{6,}"), "url"),
    (re.compile(r"[A-Za-z0-9+/]{60,}={0,2}"), "long_base64_blob"),
    (re.compile(r"upx[0-9!]", re.I), "upx_marker"),
    (re.compile(r"\.(onion|bit)\b", re.I), "darknet_address"),
]


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts if c)


def _pe(b: bytes):
    try:
        if len(b) < 0x40 or b[:2] != b"MZ":
            return None
        lfanew = struct.unpack_from("<I", b, 0x3C)[0]
        if b[lfanew:lfanew + 4] != b"PE\x00\x00":
            return None
        machine, nsec, _ts, _sym, _nsym, opt_size, _ch = struct.unpack_from(
            "<HHIIIHH", b, lfanew + 4)
        opt = lfanew + 24
        magic = struct.unpack_from("<H", b, opt)[0]
        pe32p = magic == 0x20B
        subsystem = struct.unpack_from("<H", b, opt + 68)[0]
        entry = struct.unpack_from("<I", b, opt + 16)[0]
        base = struct.unpack_from("<Q" if pe32p else "<I", b,
                                  opt + 24)[0]
        sec_off = opt + opt_size
        secs = []
        for i in range(nsec):
            o = sec_off + i * 40
            name = b[o:o + 8].rstrip(b"\x00").decode("latin1", "replace")
            vsize, vaddr, rawsize, rawptr = struct.unpack_from(
                "<IIII", b, o + 8)
            ent = _entropy(b[rawptr:rawptr + rawsize]) if rawptr and rawsize \
                else 0.0
            secs.append({"name": name, "vaddr": vaddr, "vsize": vsize,
                         "raw": rawsize,
                         "entropy": max(0.0, round(ent, 2))})
        return {"machine": machine, "sections_count": nsec,
                "pe32plus": pe32p, "subsystem": subsystem,
                "entry_rva": entry, "image_base": base, "sections": secs}
    except Exception:
        return None


def _elf(b: bytes):
    try:
        if b[:4] != b"\x7fELF":
            return None
        cls = "64-bit" if b[4] == 2 else "32-bit"
        endian = "little" if b[5] == 1 else "big"
        etype = struct.unpack_from("<H", b, 16)[0]
        machine = struct.unpack_from("<H", b, 18)[0]
        entry = struct.unpack_from("<Q" if b[4] == 2 else "<I", b, 24)[0]
        return {"class": cls, "endian": endian, "e_type": etype,
                "machine": machine, "entry": entry}
    except Exception:
        return None


def _strings(path: str, minimum: int = 6, limit: int = 4000):
    exe = shutil.which("strings")
    if not exe:
        return []
    try:
        r = subprocess.run([exe, "-n", str(minimum), path],
                           capture_output=True, text=True, timeout=90,
                           errors="ignore")
        return r.stdout.splitlines()[:limit]
    except Exception:
        return []


def _disasm(path: str, symbol: str, limit: int = 160):
    exe = shutil.which("objdump")
    if not exe:
        return None, "objdump not installed"
    try:
        r = subprocess.run([exe, "-d", "-M", "intel",
                            f"--disassemble={symbol}", path],
                           capture_output=True, text=True, timeout=90,
                           errors="ignore")
        lines = r.stdout.splitlines()
        if not lines:
            return None, f"symbol '{symbol}' not found"
        return "\n".join(lines[:limit]), None
    except Exception as e:
        return None, str(e)


def triage(path: str, symbol: str | None = None,
           disasm_lines: int = 160) -> dict:
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(path):
        return {"ok": False, "output": f"not a file: {path}"}
    size = os.path.getsize(path)
    if size > 80 * 1024 * 1024:
        return {"ok": False, "output": "file too large for triage (>80 MB)"}
    with open(path, "rb") as f:
        head = f.read(2 * 1024 * 1024)
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)

    fmt = "unknown"
    info = _pe(head)
    if info:
        fmt = "PE32+" if info["pe32plus"] else "PE32"
    else:
        info = _elf(head)
        if info:
            fmt = f"ELF {info['class']} {info['endian']}-endian"

    strings = _strings(path)
    joined = "\n".join(strings)
    low = joined.lower()

    caps = {}
    for cap, needles in CAPS.items():
        hits = [n for n in needles if n.lower() in low]
        if hits:
            caps[cap] = hits

    indicators = {}
    for rx, label in SUSPICIOUS_STRINGS:
        found = rx.findall(joined)
        if found:
            indicators[label] = len(found)

    lines = [f"binary triage: {path}",
             f"  size      : {size:,} bytes",
             f"  sha256    : {sha.hexdigest()}",
             f"  format    : {fmt}"]
    if info and fmt.startswith("PE"):
        lines.append(f"  machine   : 0x{info['machine']:04x}  "
                     f"subsystem {info['subsystem']}")
        lines.append(f"  entry RVA : 0x{info['entry_rva']:x}  "
                     f"image base 0x{info['image_base']:x}")
        for s in info["sections"][:12]:
            flag = "  <-- high entropy" if s["entropy"] > 7.2 else ""
            lines.append(f"  section   : {s['name']:10s} "
                         f"{s['raw']:>9,} B  H={s['entropy']:.2f}{flag}")
        if any(s["name"].startswith("UPX") for s in info["sections"]):
            lines.append("  packer    : UPX section names present")
    elif info:
        lines.append(f"  entry     : 0x{info['entry']:x}  "
                     f"machine {info['machine']}")

    lines.append(f"  strings   : {len(strings)} extracted")
    if caps:
        lines.append("  capability indicators:")
        for cap, hits in caps.items():
            lines.append(f"    {cap:20s} {', '.join(hits[:6])}")
    else:
        lines.append("  capability indicators: none of the watched APIs "
                     "appeared in the strings")
    if indicators:
        lines.append("  string indicators:")
        for label, n in indicators.items():
            lines.append(f"    {label:20s} {n}")

    verdict = []
    if "extortion" in caps and "crypto" in caps:
        verdict.append("ransomware-like: encryption APIs + extortion text")
    if "keylogging" in caps:
        verdict.append("keylogger-like: keyboard hook/state APIs")
    if "process_injection" in caps:
        verdict.append("process injection capability")
    if "persistence" in caps:
        verdict.append("persistence mechanism referenced")
    if fmt.startswith("PE") and any(s["entropy"] > 7.2
                                    for s in info["sections"]):
        verdict.append("at least one high-entropy section (packed or "
                       "compressed data)")
    lines.append("  triage    : " +
                 ("; ".join(verdict) if verdict else
                  "no strong indicator from these heuristics"))
    lines.append("  note      : heuristics only. The sample was NOT executed; "
                 "confirm in an isolated lab.")

    if symbol:
        text, err = _disasm(path, symbol, disasm_lines)
        lines.append("")
        if text:
            lines.append(f"disassembly of {symbol} (Intel syntax):")
            lines.append(text)
        else:
            lines.append(f"disassembly failed: {err}")

    return {"ok": True, "output": "\n".join(lines),
            "sha256": sha.hexdigest(), "format": fmt, "caps": caps}
