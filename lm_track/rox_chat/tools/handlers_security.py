"""Security handlers: real, local blue-team scanners (no external CLIs).

  scan_secrets  regex + entropy secret detection (AWS keys, private keys,
                JWTs, tokens, high-entropy credential-looking strings)
  sast_check    pattern-based static analysis (eval/exec/shell=True, raw
                SQL, hardcoded creds, weak crypto, unsafe pickle/yaml, SSRF)
  parse_logs    structured log ingestion (JSONL / common log format) with
                filtering + IOC surfacing
  osint_lookup  passive intel for an IP/domain (geo/ASN, DNS, HTTP headers,
                certificate transparency)

All handlers resolve paths against the workspace and return
{"ok": bool, "output": str}.
"""
from __future__ import annotations

import json
import math
import os
import re
import socket
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from .handlers_fs import _resolve
except ImportError:  # run directly
    from handlers_fs import _resolve

MAX_FILES = 2000
MAX_BYTES_PER_FILE = 5_000_000
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv",
             "dist", "build", ".pytest_cache", "coverage"}
CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
             ".c", ".cpp", ".h", ".hpp", ".cs", ".php", ".rb", ".sh",
             ".ps1", ".bat", ".json", ".yaml", ".yml", ".toml", ".ini",
             ".env", ".cfg", ".conf", ".sql", ".v", ".sv", ".vhd", ".tf"}

# SAST looks at program source only: data/config files produce false
# positives (a JSON scan report that merely mentions system()).
SAST_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
             ".c", ".cpp", ".h", ".hpp", ".cs", ".php", ".rb", ".sh",
             ".ps1", ".bat", ".sql", ".v", ".sv", ".vhd", ".tf"}

SECRET_RULES = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "aws_access_key", "high"),
    (re.compile(r"(?i)-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?"
                r"PRIVATE KEY-----"), "private_key", "critical"),
    (re.compile(r"(?i)ghp_[0-9A-Za-z]{36}"), "github_token", "high"),
    (re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"), "api_key_sk", "high"),
    (re.compile(r"(?i)xox[baprs]-[0-9A-Za-z-]{10,}"), "slack_token", "high"),
    (re.compile(r"(?i)AIza[0-9A-Za-z_-]{35}"), "google_api_key", "high"),
    (re.compile(r"(?i)eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."
                r"[A-Za-z0-9_-]{10,}"), "jwt", "medium"),
]
ENTROPY_ASSIGN = re.compile(
    r"(?i)(?:api[_-]?key|token|secret|passwd|password|pwd|client[_-]?secret)"
    r"\s*[:=]\s*[\"']?([A-Za-z0-9_\-+/=!@#$%^&*.?]{12,})[\"']?")


def _entropy(s):
    if not s:
        return 0.0
    c = Counter(s)
    n = len(s)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def _walk_files(root, pattern=None, limit=MAX_FILES):
    pat = re.compile(pattern) if pattern else None
    out = []
    if os.path.isfile(root):
        out = [root]
    else:
        for dp, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if pat and not pat.search(f):
                    continue
                out.append(os.path.join(dp, f))
                if len(out) >= limit:
                    return out
    return out


def _read(p):
    try:
        if os.path.getsize(p) > MAX_BYTES_PER_FILE:
            return ""
        return open(p, encoding="utf-8", errors="ignore").read()
    except Exception:
        return ""


def _fmt(items):
    if not items:
        return "(none)"
    return "\n".join(items)


def scan_secrets(args, ctx):
    """Scan files for leaked secrets. args: path (file/dir), pattern."""
    root = _resolve(args.get("path", ""), ctx)
    if not os.path.exists(root):
        return {"ok": False, "output": f"no such path: {root}"}
    pattern = args.get("pattern")
    files = _walk_files(root, pattern)
    findings = []
    for p in files:
        if pattern and not re.search(pattern, os.path.basename(p)):
            continue
        text = _read(p)
        if not text:
            continue
        if "\x00" in text[:2048]:  # binary -> skip
            continue
        for rx, typ, sev in SECRET_RULES:
            for m in rx.finditer(text):
                findings.append(f"{p}:{text[:m.start()].count(chr(10)) + 1} "
                                f"[{sev}] {typ}: {m.group(0)[:40]}")
        for m in ENTROPY_ASSIGN.finditer(text):
            if _entropy(m.group(1)) >= 4.0:
                ln = text[:m.start()].count(chr(10)) + 1
                findings.append(f"{p}:{ln} [medium] high_entropy_secret: "
                                f"{m.group(1)[:40]}")
    return {"ok": True,
            "output": (f"secret scan of {root} ({len(files)} files): "
                       f"{len(findings)} findings\n") + _fmt(findings[:50])}


SAST_RULES = [
    (re.compile(r"\beval\s*\("), "eval", "high",
     "arbitrary code execution"),
    (re.compile(r"\bexec\s*\("), "exec", "high",
     "arbitrary code execution"),
    (re.compile(r"os\.system\s*\("), "os.system", "high",
     "shell command injection"),
    (re.compile(r"subprocess\.(?:run|call|Popen)\s*\([^)]*"
                r"shell\s*=\s*True"), "subprocess_shell_true", "high",
     "shell injection"),
    (re.compile(r"pickle\.(?:loads|load)\s*\("), "pickle.loads", "high",
     "unsafe deserialization"),
    (re.compile(r"yaml\.load\s*\([^)]*Loader\s*=\s*"
                r"yaml\.(?:Unsafe)?Loader\b"), "yaml.unsafe_load", "high",
     "unsafe YAML"),
    (re.compile(r"cursor\.execute\s*\(\s*f[\"']"), "fstring_sql", "high",
     "SQL injection via f-string"),
    (re.compile(r"(?:password|passwd|pwd)\s*=\s*[\"'][^\"']{3,}[\"']"),
     "hardcoded_pwd",
     "high", "hardcoded credential"),
    (re.compile(r"\b(hashlib\.md5|hashlib\.sha1)\s*\("), "weak_hash",
     "medium", "MD5/SHA1 not for security"),
    (re.compile(r"requests\.(get|post|put|delete)\s*\(\s*[\"']"
                r"(?:http://|file://|localhost|127\.0\.0\.1)"),
     "ssrf_plaintext", "medium", "plaintext/SSRF-prone request"),
    # C / C++ memory-safety rules
    (re.compile(r"\b(strcpy|strcat|sprintf|vsprintf|gets)\s*\("),
     "unsafe_c_string", "high",
     "unbounded C string write (buffer overflow)"),
    (re.compile(r"\b(scanf|fscanf|sscanf)\s*\(\s*\"[^\"]*%s"), "scanf_s",
     "medium", "%s without a width can overflow"),
    (re.compile(r"\b(memcpy|memmove)\s*\([^,]+,[^,]+,\s*[a-zA-Z_]\w*\s*\)"),
     "memcpy_variable", "medium", "variable-length copy: check bounds"),
    (re.compile(r"\bsystem\s*\("), "system_call", "high",
     "command injection via system()"),
    (re.compile(r"\b(mktemp|tmpnam)\s*\("), "insecure_temp", "medium",
     "race-prone temporary file"),
    (re.compile(r"\brand\s*\(\s*\)|\bsrand\s*\("), "weak_rng", "medium",
     "rand() is not cryptographic"),
    (re.compile(r"\b(printf|fprintf)\s*\([^,)]*\)\s*;"), "format_string",
     "low", "check for user-controlled format strings"),
]


def sast_check(args, ctx):
    """Static scan for insecure code patterns. args: path, pattern."""
    root = _resolve(args.get("path", ""), ctx)
    if not os.path.exists(root):
        return {"ok": False, "output": f"no such path: {root}"}
    pattern = args.get("pattern")
    files = _walk_files(root, pattern)
    findings = []
    for p in files:
        if os.path.splitext(p)[1].lower() not in SAST_EXTS and not pattern:
            continue
        text = _read(p)
        if not text:
            continue
        for rx, name, sev, why in SAST_RULES:
            for m in rx.finditer(text):
                ln = text[:m.start()].count(chr(10)) + 1
                findings.append(f"{p}:{ln} [{sev}] {name} "
                                f"({why}): {m.group(0)[:50]}")
    return {"ok": True,
            "output": (f"sast scan of {root} ({len(files)} files): "
                       f"{len(findings)} findings\n") + _fmt(findings[:60])}


_CLF = re.compile(
    r'(?P<ip>[\d.]+|[\w:]+) - - \[(?P<ts>[^\]]+)\] "(?P<method>\w+) '
    r'(?P<path>\S+) [^"]*" (?P<status>\d{3}) (?P<bytes>\S+)')


def binary_triage(args, ctx):
    """Triage a PE/ELF without executing it. args: path, symbol, disasm."""
    try:
        from security_binary import triage
    except Exception as e:
        return {"ok": False, "output": f"triage module unavailable: {e}"}
    p = _resolve(args.get("path", ""), ctx)
    symbol = args.get("symbol")
    if not symbol and args.get("disasm"):
        symbol = "main"
    return triage(p, symbol=symbol)


def parse_logs(args, ctx):
    """Parse a log file into structured rows. args: path, format
    (jsonl|clf|auto), filter (field=value or keyword), limit."""
    root = _resolve(args.get("path", ""), ctx)
    if not os.path.exists(root):
        return {"ok": False, "output": f"no such path: {root}"}
    fmt = (args.get("format") or "auto").lower()
    limit = int(args.get("limit", 200))
    fquery = args.get("filter") or ""
    rows = []
    try:
        fh = open(root, encoding="utf-8", errors="ignore")
    except Exception as e:
        return {"ok": False, "output": f"open failed: {e}"}
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = None
            if fmt in ("jsonl", "auto") and line.startswith("{"):
                try:
                    row = json.loads(line)
                except Exception:
                    row = None
            if row is None:
                m = _CLF.match(line)
                if m:
                    row = {k: (int(v) if k in ("status",) and v.isdigit()
                               else v) for k, v in m.groupdict().items()}
            if row is None:
                row = {"line": line[:300]}
            rows.append(row)
            if len(rows) >= limit:
                break
    # filter
    if fquery:
        key = val = None
        if "=" in fquery:
            key, val = fquery.split("=", 1)
            key, val = key.strip(), val.strip()
        def keep(r):
            if key is not None:
                return str(r.get(key, "")).lower() == val.lower()
            return fquery.lower() in json.dumps(r).lower()
        rows = [r for r in rows if keep(r)]
    # IOC surface: IPs, hashes, domains
    ips = Counter()
    for r in rows:
        for v in r.values():
            for ip in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", str(v)):
                ips[ip] += 1
    iocs = "iocs: " + ", ".join(f"{ip} x{c}" for ip, c in
                                ips.most_common(10)) if ips else "iocs: none"
    sample = json.dumps(rows[:6], indent=0)
    return {"ok": True,
            "output": (f"parsed {len(rows)} rows from {root} ({fmt})\n"
                       f"{iocs}\n\nsample:\n{sample[:1800]}")}


def _http_headers(url, timeout=8):
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent":
                                                   "rox-osint/1.0"},
                                     method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {k: v for k, v in r.headers.items()}
    except Exception:
        return {}


def osint_lookup(args, ctx):
    """Passive intel for an IP or domain. args: target."""
    target = (args.get("target") or "").strip()
    if not target:
        return {"ok": False, "output": "target required (IP or domain)"}
    out = [f"osint for {target}"]
    is_ip = re.match(r"^\d{1,3}(\.\d{1,3}){3}$", target)
    # DNS / hostname
    try:
        if is_ip:
            out.append("ptr: " + socket.gethostbyaddr(target)[0])
        else:
            out.append("dns: " + socket.gethostbyname(target))
    except Exception:
        pass
    # geo/ASN for IP
    if is_ip:
        try:
            import urllib.request
            with urllib.request.urlopen(
                    f"http://ip-api.com/json/{target}?fields=status,"
                    "country,city,isp,org,as,query,lat,lon", timeout=8) as r:
                g = json.loads(r.read().decode())
            if g.get("status") == "success":
                out.append(f"geo: {g.get('country')}/{g.get('city')} "
                           f"{g.get('isp')} {g.get('as')}")
        except Exception:
            pass
    # HTTP headers
    scheme = "http" if is_ip else "https"
    hdrs = _http_headers(f"{scheme}://{target}")
    if hdrs:
        picks = {k: hdrs[k] for k in ("Server", "X-Powered-By", "Via",
                                      "X-Cache", "Strict-Transport-Security",
                                      "Content-Security-Policy")
                 if k in hdrs}
        if picks:
            out.append("headers: " + "; ".join(f"{k}={v}" for k, v
                                               in picks.items()))
    # certificate transparency for domains
    if not is_ip:
        try:
            import urllib.request
            with urllib.request.urlopen(
                    f"https://crt.sh/?q=%25.{target}&output=json",
                    timeout=10) as r:
                certs = json.loads(r.read().decode())
            names = sorted({n for c in certs[:50]
                            for n in c.get("name_value", "").split("\n")})
            if names:
                out.append("cert names: " + ", ".join(names[:10]))
        except Exception:
            pass
    return {"ok": True, "output": "\n".join(out)}


if __name__ == "__main__":
    from types import SimpleNamespace
    import tempfile
    d = tempfile.mkdtemp()
    ctx = SimpleNamespace(workspace=d)
    with open(os.path.join(d, "x.py"), "w", encoding="utf-8") as f:
        f.write('import os\neval("1+1")\npassword="hunter2"\n'
                "key = 'AKIAIOSFODNN7EXAMPLE'\n")
    print(scan_secrets({"path": d}, ctx)["output"][:400])
    print(sast_check({"path": d}, ctx)["output"][:400])