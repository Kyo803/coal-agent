"""Category 1 & 2 handlers: filesystem + search / code intelligence.

Every handler takes (args: dict, ctx) and returns a dict:
  {"ok": bool, "output": str}   -- output is capped by exec.py.

Path safety: all file tools resolve paths under ctx.workspace by default;
absolute paths outside the workspace are allowed only for Tier-1-confirm
tools (write/move/delete) and are gated by the permission layer.
"""
from __future__ import annotations

import fnmatch
import os
import re

_JOURNAL = None  # lazily set by rox.py (project journal hook)


def set_journal_hook(fn):
    """rox.py registers a callable(rel_path, action, detail) here so every
    file mutation inside a ROX project is journaled automatically."""
    global _JOURNAL
    _JOURNAL = fn


def _journal(rel, action, detail=""):
    if _JOURNAL:
        try:
            _JOURNAL(rel, action, detail)
        except Exception:
            pass


def _resolve(path, ctx):
    p = os.path.abspath(os.path.expanduser(path or "."))
    if not os.path.exists(p) and ctx.workspace and not os.path.isabs(path or ""):
        p = os.path.abspath(os.path.join(ctx.workspace, path))
    return p


# ---------- reads ----------
def read_file(args, ctx):
    p = _resolve(args.get("path", ""), ctx)
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return {"ok": False, "output": f"file not found: {p}"}
    except IsADirectoryError:
        return {"ok": False, "output": f"is a directory: {p}"}
    except PermissionError:
        return {"ok": False, "output": f"permission denied: {p}"}
    n = len(lines)
    start = max(0, int(args.get("offset", 0)))
    limit = int(args.get("limit", 200)) or n
    chunk = lines[start:start + limit]
    out = f"{p} ({n} lines)\n" + "\n".join(f"{start+i+1}: {l}"
                                           for i, l in enumerate(chunk))
    return {"ok": True, "output": out}


def read_file_range(args, ctx):
    a = read_file(args, ctx)
    return a


def read_multiple_files(args, ctx):
    parts = []
    for path in (args.get("paths") or []):
        r = read_file({"path": path, "limit": args.get("limit", 100)}, ctx)
        parts.append(r["output"])
    return {"ok": True, "output": "\n\n---\n\n".join(parts)}


def get_file_info(args, ctx):
    p = _resolve(args.get("path", ""), ctx)
    try:
        st = os.stat(p)
        return {"ok": True, "output":
                f"{p}\nsize={st.st_size}\nmodified={st.st_mtime}\n"
                f"dir={os.path.isdir(p)}"}
    except FileNotFoundError:
        return {"ok": False, "output": f"not found: {p}"}


def list_directory(args, ctx):
    p = _resolve(args.get("path", ctx.workspace or "."), ctx)
    try:
        entries = sorted(os.listdir(p))
    except FileNotFoundError:
        return {"ok": False, "output": f"not found: {p}"}
    lines = [f"{e}/" if os.path.isdir(os.path.join(p, e)) else e
             for e in entries]
    return {"ok": True, "output": f"{p}\n" + "\n".join(lines)}


def directory_tree(args, ctx):
    p = _resolve(args.get("path", ctx.workspace or "."), ctx)
    depth = int(args.get("depth", 3))
    maxd = int(args.get("max_depth", 3))

    def walk(d, prefix, level):
        if level > depth:
            return []
        try:
            entries = sorted(os.listdir(d))
        except Exception:
            return []
        out = []
        for e in entries:
            if e.startswith(".") or e in ("__pycache__", "node_modules"):
                continue
            fp = os.path.join(d, e)
            isdir = os.path.isdir(fp)
            out.append(prefix + ("📁 " if isdir else "   ") + e)
            if isdir:
                out += walk(fp, prefix + ("   " if False else "   "),
                            level + 1)
        return out

    return {"ok": True, "output": "\n".join(walk(p, "", 0))[:6000]}


# ---------- writes (Tier 1) ----------
def _clean_fences(content):
    """Strip stray markdown code fences / language tags that leak into
    file bodies."""
    content = re.sub(r"\n?\s*```\s*\n?\s*$", "", content)
    content = re.sub(r"^```[a-zA-Z]*\s*\n?", "", content)
    # a bare language tag leaked as the first line (e.g. "verilog")
    content = re.sub(
        r"^(verilog|vhdl|systemverilog|python|typescript|javascript|tsx|"
        r"jsx|ts|js|css|scss|json|html|bash|sh|shell|makefile|plaintext)"
        r"\s*\n", "", content)
    return content


def write_file(args, ctx):
    p = _resolve(args.get("path", ""), ctx)
    content = _clean_fences(args.get("content", ""))
    # Verilog files must start with `timescale (models often drop the `)
    if p.lower().endswith((".v", ".sv")) and \
            re.match(r"^timescale\b", content):
        content = "`" + content
    existed = os.path.exists(p)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        _journal(p, "edited" if existed else "created",
                 f"{len(content)} chars")
        return {"ok": True, "output": f"wrote {len(content)} chars to {p}"}
    except Exception as e:
        return {"ok": False, "output": f"write failed: {e}"}


def create_file(args, ctx):
    p = _resolve(args.get("path", ""), ctx)
    if os.path.exists(p):
        return {"ok": False, "output": f"already exists: {p}"}
    return write_file({"path": p, "content": args.get("content", "")}, ctx)


def append_file(args, ctx):
    p = _resolve(args.get("path", ""), ctx)
    try:
        with open(p, "a", encoding="utf-8") as f:
            f.write(args.get("content", ""))
        _journal(p, "edited", f"appended {len(args.get('content',''))} chars")
        return {"ok": True, "output": f"appended to {p}"}
    except Exception as e:
        return {"ok": False, "output": f"append failed: {e}"}


def delete_file(args, ctx):
    p = _resolve(args.get("path", ""), ctx)
    try:
        os.remove(p)
        _journal(p, "deleted")
        return {"ok": True, "output": f"deleted {p}"}
    except FileNotFoundError:
        return {"ok": False, "output": f"not found: {p}"}
    except Exception as e:
        return {"ok": False, "output": f"delete failed: {e}"}


def move_file(args, ctx):
    src = _resolve(args.get("source", args.get("src", "")), ctx)
    dst = _resolve(args.get("destination", args.get("dst", "")), ctx)
    try:
        os.rename(src, dst)
        _journal(src, "renamed", f"-> {dst}")
        return {"ok": True, "output": f"moved {src} -> {dst}"}
    except Exception as e:
        return {"ok": False, "output": f"move failed: {e}"}


def copy_file(args, ctx):
    import shutil
    src = _resolve(args.get("source", args.get("src", "")), ctx)
    dst = _resolve(args.get("destination", args.get("dst", "")), ctx)
    try:
        shutil.copy2(src, dst)
        return {"ok": True, "output": f"copied {src} -> {dst}"}
    except Exception as e:
        return {"ok": False, "output": f"copy failed: {e}"}


def rename_file(args, ctx):
    return move_file({"source": args.get("old_path", ""),
                      "destination": args.get("new_path", "")}, ctx)


def create_directory(args, ctx):
    p = _resolve(args.get("path", ""), ctx)
    try:
        os.makedirs(p, exist_ok=bool(args.get("recursive", True)))
        return {"ok": True, "output": f"created dir {p}"}
    except Exception as e:
        return {"ok": False, "output": f"mkdir failed: {e}"}


def zip_files(args, ctx):
    import zipfile
    src = _resolve(args.get("source", ""), ctx)
    dst = _resolve(args.get("destination", ""), ctx)
    try:
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
            if os.path.isdir(src):
                for root, _, files in os.walk(src):
                    for f in files:
                        fp = os.path.join(root, f)
                        z.write(fp, os.path.relpath(fp, os.path.dirname(src)))
            else:
                z.write(src, os.path.basename(src))
        return {"ok": True, "output": f"zipped -> {dst}"}
    except Exception as e:
        return {"ok": False, "output": f"zip failed: {e}"}


def unzip(args, ctx):
    import zipfile
    src = _resolve(args.get("source", ""), ctx)
    dst = _resolve(args.get("destination", args.get("to", "")), ctx)
    try:
        with zipfile.ZipFile(src) as z:
            z.extractall(dst)
        return {"ok": True, "output": f"unzipped {src} -> {dst}"}
    except Exception as e:
        return {"ok": False, "output": f"unzip failed: {e}"}


def apply_patch(args, ctx):
    """Minimal unified-diff style patch: 'old' -> 'new' replacements."""
    p = _resolve(args.get("path", ""), ctx)
    try:
        with open(p, encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        return {"ok": False, "output": f"read failed: {e}"}
    old = args.get("old", args.get("search", ""))
    new = args.get("new", args.get("replacement", ""))
    if old not in text:
        return {"ok": False, "output": f"search string not found in {p}"}
    text = text.replace(old, new, 1)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    _journal(p, "edited", f"replaced {len(old)} chars")
    return {"ok": True, "output": f"patched {p}"}


def edit_file(args, ctx):
    return apply_patch(args, ctx)


def str_replace(args, ctx):
    return apply_patch(args, ctx)


def insert_lines(args, ctx):
    p = _resolve(args.get("path", ""), ctx)
    at = int(args.get("at", args.get("line", 1)))
    lines = (args.get("lines") or [])
    try:
        with open(p, encoding="utf-8") as f:
            all_lines = f.read().splitlines()
        all_lines[at:at] = lines
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(all_lines))
        _journal(p, "edited", f"inserted {len(lines)} lines at {at}")
        return {"ok": True, "output": f"inserted {len(lines)} lines at {at}"}
    except Exception as e:
        return {"ok": False, "output": f"insert failed: {e}"}


def delete_lines(args, ctx):
    p = _resolve(args.get("path", ""), ctx)
    start = int(args.get("start", args.get("from", 1)))
    end = int(args.get("end", args.get("to", start)))
    try:
        with open(p, encoding="utf-8") as f:
            all_lines = f.read().splitlines()
        del all_lines[start - 1:end]
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(all_lines))
        _journal(p, "edited", f"deleted lines {start}-{end}")
        return {"ok": True, "output": f"deleted lines {start}-{end} of {p}"}
    except Exception as e:
        return {"ok": False, "output": f"delete failed: {e}"}


# ---------- search / code intelligence ----------
def glob_files(args, ctx):
    pat = args.get("pattern", "**/*")
    root = args.get("path", ctx.workspace or ".")
    matches = []
    for base, _, files in os.walk(root):
        for f in files:
            full = os.path.join(base, f)
            if fnmatch.fnmatch(full, pat) or fnmatch.fnmatch(f, pat):
                matches.append(full)
            if len(matches) >= int(args.get("limit", 200)):
                break
        if len(matches) >= int(args.get("limit", 200)):
            break
    return {"ok": True, "output": "\n".join(matches[:200])
            or "no matches"}


def grep_files(args, ctx):
    pat = args.get("pattern", args.get("regex", ""))
    root = args.get("path", ctx.workspace or ".")
    inc = args.get("include", "*")
    try:
        rx = re.compile(pat)
    except re.error as e:
        return {"ok": False, "output": f"bad regex: {e}"}
    hits = []
    for base, _, files in os.walk(root):
        for f in files:
            if not fnmatch.fnmatch(f, inc) or f.endswith((".pyc",)):
                continue
            fp = os.path.join(base, f)
            try:
                with open(fp, encoding="utf-8", errors="ignore") as fh:
                    for i, line in enumerate(fh, 1):
                        if rx.search(line):
                            hits.append(f"{fp}:{i}: {line.rstrip()[:160]}")
                            if len(hits) >= int(args.get("limit", 100)):
                                break
            except Exception:
                continue
            if len(hits) >= int(args.get("limit", 100)):
                break
        if len(hits) >= int(args.get("limit", 100)):
            break
    return {"ok": True, "output": "\n".join(hits) or "no matches"}


def find_symbol(args, ctx):
    name = args.get("name", "")
    return grep_files({"pattern": rf"\b{re.escape(name)}\b",
                       "path": args.get("path", ctx.workspace),
                       "include": "*.py", "limit": args.get("limit", 20)},
                      ctx)


def list_symbols(args, ctx):
    p = _resolve(args.get("path", ""), ctx)
    out = []
    try:
        with open(p, encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f, 1):
                if re.match(r"\s*(def|class|async def)\s+", line):
                    out.append(f"{i}: {line.strip()[:120]}")
    except Exception as e:
        return {"ok": False, "output": f"error: {e}"}
    return {"ok": True, "output": "\n".join(out) or "no symbols"}


def dependency_graph(args, ctx):
    p = _resolve(args.get("path", ""), ctx)
    deps = set()
    try:
        with open(p, encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = re.match(r"\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
                             line)
                if m:
                    deps.add(m.group(1) or m.group(2))
    except Exception as e:
        return {"ok": False, "output": f"error: {e}"}
    return {"ok": True, "output": f"{p} imports: " + ", ".join(sorted(deps))}