"""Forge a ROX N-branded GGUF from the open base, WITHOUT touching weights.

Raw GGUF surgery: we re-serialize only the small scalar branding metadata
keys (general.name/author/license/...); every other metadata value, the
tensor-info table and the entire tensor data section are copied
byte-for-byte. Result: a file whose identity is ROX-N while its weights are
identical (same power).

    python -m moe.forge_brand            # -> D:\\ROX_N_MODELS\\ROX-N-...gguf
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import time

from rox_config import cfg

_U32 = struct.Struct("<I")
_U64 = struct.Struct("<Q")
_SCALAR_SIZE = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8,
                11: 8, 12: 8}
STRING, ARRAY = 8, 9

BRAND = {
    "general.name": "ROX-N 35B A3B",
    "general.description": ("ROX N branded build of the open Qwen3.6-35B-A3B "
                            "weights (Apache-2.0). Bit-identical weights; "
                            "ROX N identity, tooling and packaging."),
    "general.author": "ROX N",
    "general.organization": "ROX N",
    "general.license": "apache-2.0",
    "general.license.name": "Apache License 2.0",
    "general.license.link": "https://www.apache.org/licenses/LICENSE-2.0",
    "general.base_model": "Qwen/Qwen3.6-35B-A3B",
}
BRAND_ARRAY = {
    "general.tags": ["rox-n", "rox-n-35b", "moe", "local", "agent",
                     "rox-n-silicon-lab", "qwen3.6-base"],
}


def _sha256(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def _ser_str(key: str, val: str) -> bytes:
    kb = key.encode("utf-8")
    vb = val.encode("utf-8")
    return (_U64.pack(len(kb)) + kb + _U32.pack(STRING)
            + _U64.pack(len(vb)) + vb)


def _ser_str_array(key: str, vals: list) -> bytes:
    kb = key.encode("utf-8")
    out = [_U64.pack(len(kb)) + kb + _U32.pack(ARRAY)
           + _U32.pack(STRING) + _U64.pack(len(vals))]
    for v in vals:
        vb = v.encode("utf-8")
        out.append(_U64.pack(len(vb)) + vb)
    return b"".join(out)


def _read_string(buf, off):
    n = _U64.unpack_from(buf, off)[0]
    off += 8
    s = buf[off:off + n]
    return s, off + n


def _skip_value(buf, off, vtype):
    if vtype == STRING:
        n = _U64.unpack_from(buf, off)[0]
        return off + 8 + n
    if vtype == ARRAY:
        etype = _U32.unpack_from(buf, off)[0]
        off += 4
        count = _U64.unpack_from(buf, off)[0]
        off += 8
        for _ in range(count):
            if etype == STRING:
                n = _U64.unpack_from(buf, off)[0]
                off += 8 + n
            else:
                off += _SCALAR_SIZE[etype]
        return off
    return off + _SCALAR_SIZE[vtype]


def build(src: str | None = None, dest: str | None = None) -> dict:
    src = src or cfg.model_path()
    dest = dest or r"D:\ROX_N_MODELS\ROX-N-35B-A3B-ROXN-Q4_K_M.gguf"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    t0 = time.time()
    with open(src, "rb") as f:
        buf = f.read()

    if buf[:4] != b"GGUF":
        raise ValueError("not a GGUF file")
    version = _U32.unpack_from(buf, 4)[0]
    tensor_count = _U64.unpack_from(buf, 8)[0]
    kv_count = _U64.unpack_from(buf, 16)[0]
    off = 24

    kv_spans = []          # (key, start, end)
    alignment = 32
    for _ in range(kv_count):
        start = off
        keyb, off = _read_string(buf, off)
        key = keyb.decode("utf-8", "replace")
        vtype = _U32.unpack_from(buf, off)[0]
        off += 4
        if key == "general.alignment" and vtype == 4:
            alignment = _U32.unpack_from(buf, off)[0]
        off = _skip_value(buf, off, vtype)
        kv_spans.append((key, start, off))

    # tensor-info section: parse to find its end
    infos_start = off
    for _ in range(tensor_count):
        _, off = _read_string(buf, off)
        nd = _U32.unpack_from(buf, off)[0]
        off += 4 + nd * 8 + 4 + 8     # dims(u64*n) + type(u32) + offset(u64)
    infos_end = off
    pad = (-infos_end) % alignment
    data_start = infos_end + pad

    # rebuild KV block: verbatim except branding keys; append missing brand
    brand_keys = set(BRAND) | set(BRAND_ARRAY)
    present = {k for k, _, _ in kv_spans}
    new_kv, added = [], 0
    for key, s, e in kv_spans:
        if key in BRAND:
            new_kv.append(_ser_str(key, BRAND[key]))
        elif key in BRAND_ARRAY:
            new_kv.append(_ser_str_array(key, BRAND_ARRAY[key]))
        else:
            new_kv.append(buf[s:e])
    for k, v in BRAND.items():
        if k not in present:
            new_kv.append(_ser_str(k, v))
            added += 1
    for k, v in BRAND_ARRAY.items():
        if k not in present:
            new_kv.append(_ser_str_array(k, v))
            added += 1

    new_kv_blob = b"".join(new_kv)
    header = (b"GGUF" + _U32.pack(version) + _U64.pack(tensor_count)
              + _U64.pack(len(new_kv)))

    infos_blob = buf[infos_start:infos_end]
    prefix = header + new_kv_blob + infos_blob
    prefix += b"\x00" * ((-len(prefix)) % alignment)

    with open(dest, "wb") as out:
        out.write(prefix)
        with open(src, "rb") as fin:
            fin.seek(data_start)
            while True:
                chunk = fin.read(1 << 22)
                if not chunk:
                    break
                out.write(chunk)

    src_sha = _sha256(src)
    dest_sha = _sha256(dest)
    manifest = {
        "name": "ROX-N-35B-A3B-ROXN",
        "base_model": "Qwen/Qwen3.6-35B-A3B",
        "license": "apache-2.0",
        "weights": "bit-identical to base (copied verbatim)",
        "quant": "Q4_K_M",
        "source_path": src,
        "source_sha256": src_sha,
        "built_path": dest,
        "built_sha256": dest_sha,
        "built_bytes": os.path.getsize(dest),
        "kv_count": len(new_kv),
        "branding_added": added,
        "build_seconds": round(time.time() - t0, 1),
        "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    man_dir = os.path.join(os.path.dirname(cfg.model_path() or "."),
                            "variants")
    os.makedirs(man_dir, exist_ok=True)
    with open(os.path.join(man_dir, "roxn_manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    return manifest


if __name__ == "__main__":
    import json as _j
    print(_j.dumps(build(), indent=1))