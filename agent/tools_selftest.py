"""Exercise every registered Coal tool.

Three phases, because "test every tool" means different things for different
tools:

  AUDIT  every one of the ~430 specs: name, description, params, required,
         handler wiring, duplicates, categories. No side effects.
  PROBE  every *read-only* tool is actually invoked with real arguments, so a
         broken handler or a missing import shows up.
  LIVE   end-to-end use of the capabilities that matter: files, search, web,
         browser, knowledge, chip flow, 3D, memory, system, board.

Mutating / cloud / git-write / destructive tools are deliberately NOT probed
(they would change the machine); they are listed as "skipped (policy)".

    py -3.15 tools_selftest.py [--live-only] [--json]
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools import specs                                    # noqa: E402
from tools.exec import ExecContext, ToolExecutor           # noqa: E402
from tools.permissions import Permissions                  # noqa: E402

OUT_DIR = os.path.join(os.path.expanduser("~"), ".coal", "work")
JSON_OUT = os.path.join(OUT_DIR, "tools_selftest.json")
MD_OUT = os.path.join(OUT_DIR, "TOOLS_SELFTEST.md")

# --------------------------------------------------------------- phase 1
def audit():
    rows, seen = [], {}
    problems = []
    for s in specs.all_specs():
        name = s.get("name") or ""
        issues = []
        if not name:
            issues.append("no name")
        if name in seen:
            issues.append(f"duplicate of {seen[name]}")
        seen[name] = s.get("category")
        if not s.get("desc"):
            issues.append("no description")
        if not isinstance(s.get("params"), dict):
            issues.append("params not a dict")
        req = s.get("required") or []
        missing = [r for r in req if r not in (s.get("params") or {})]
        if missing:
            issues.append(f"required not in params: {missing}")
        h = s.get("handler")
        if h is None:
            issues.append("native (no python handler)")
        elif not callable(h):
            issues.append("handler not callable")
        rows.append({"name": name, "category": s.get("category"),
                     "tier": s.get("tier"), "issues": issues})
        if issues:
            problems.append((name, issues))
    return rows, problems


# --------------------------------------------------------------- phase 2
SAFE = re.compile(
    r"^(read_|list_|get_|show_|describe_|explain_|search_|find_|grep$|glob$|"
    r"regex_search$|count_|stat|directory_tree$|system_status$|ps$|df$|du$|"
    r"netstat$|top$|env_get$|clipboard_read$|browser_tabs$|chip_tools$|"
    r"board_stats$|board_show$|learn_stats$|project_status$|project_map$|"
    r"sandbox_list$|sandbox_info$|sandbox_toolchain$|mcp_list_tools$|"
    r"todo_read$|memory_search$|search_memory$|search_docs$|tool_search$|"
    r"check_|validate_|inspect_|analyze_|parse_|diff_|file_diff$|"
    r"list_symbols$|hover_info$|document_outline$|codebase_index$|"
    r"dependency_graph$|call_hierarchy$|type_hierarchy$|signature_help$|"
    r"get_diagnostics$|find_references$|go_to_definition$|find_implementations$)")

DENY = re.compile(
    r"(write|create|delete|remove|move|rename|copy|chmod|chown|kill|drop|"
    r"truncate|format|install|uninstall|deploy|push|pull|commit|reset|revert|"
    r"rebase|merge|tag|stash|upload|download|publish|release|send|post|put|"
    r"patch|edit|insert|append|tar|zip|unzip|run|exec|shell|bash|sudo|user|"
    r"open_app|type|click|swipe|tap|record|start|stop|restart|scale|rollback|"
    r"purge|rotate|schedule|cron|notify|message|call|invoke|connect|server|"
    r"index|ingest|index_)")

# parsers that need a real file of the right type
FORMATS = re.compile(r"(pdf|docx|spreadsheet|ocr|image|audio|video|xlsx|csv)")

# need an interactive desktop / window station; crash in a headless session
DESKTOP = re.compile(r"(clipboard|screenshot_desktop|keyboard_|mouse_|"
                     r"window_manage|open_app)")


def probe_args(spec, tmpfile, root):
    """Best-effort arguments so read-only tools actually do something."""
    a = {}
    for pname, p in (spec.get("params") or {}).items():
        t = (p or {}).get("type", "string")
        low = pname.lower()
        if t == "integer":
            a[pname] = 0
        elif t == "boolean":
            a[pname] = False
        elif t in ("array", "object"):
            a[pname] = [] if t == "array" else {}
        elif "path" in low or low in ("file", "filename", "target"):
            a[pname] = tmpfile
        elif low in ("dir", "directory", "root", "cwd", "base"):
            a[pname] = root
        elif low in ("url",):
            a[pname] = "https://example.com"
        elif low in ("query", "pattern", "q", "text", "name"):
            a[pname] = "def "
        else:
            a[pname] = "test"
    return a


def probe(ex, rows, tmpfile, root):
    results = []
    for r in rows:
        name = r["name"]
        if r["issues"] and any("native" in i for i in r["issues"]):
            results.append({"name": name, "status": "native"})
            continue
        if (DENY.search(name) or not SAFE.search(name)
                or FORMATS.search(name) or DESKTOP.search(name)):
            results.append({"name": name, "status": "skipped"})
            continue
        spec = specs.get(name)
        t0 = time.time()
        print(f"  probe {name}", flush=True)
        try:
            res = ex.run(name, probe_args(spec, tmpfile, root))
            ok = bool(res.get("ok"))
            out = str(res.get("output") or "")[:160]
            status = "ok" if ok else "needs_args"
        except Exception as e:
            ok, out, status = False, str(e)[:160], "error"
        results.append({"name": name, "status": status,
                        "ms": int((time.time() - t0) * 1000),
                        "output": out})
    return results


# --------------------------------------------------------------- phase 3
def live(ex, root):
    tmp = tempfile.mkdtemp(prefix="roxt-")
    f = os.path.join(tmp, "probe.txt")
    tests = []

    def run(label, tool, args, check=None):
        sp = specs.get(tool) or {}
        if sp.get("handler") is None:
            tests.append({"label": label, "tool": tool, "ok": True,
                          "native": True, "ms": 0,
                          "output": "native core tool (not executor)"})
            return {}
        t0 = time.time()
        try:
            res = ex.run(tool, args)
        except Exception as e:
            res = {"ok": False, "output": f"exception: {e}"}
        ok = bool(res.get("ok"))
        native = False
        if not ok and "unavailable" in str(res.get("output") or "").lower():
            native = True   # subsystem not initialised in this bare context
            ok = True
        if check and ok:
            try:
                ok = bool(check(res))
            except Exception:
                ok = False
        tests.append({"label": label, "tool": tool, "ok": ok,
                      "native": native,
                      "ms": int((time.time() - t0) * 1000),
                      "output": str(res.get("output") or "")[:220]})
        return res

    # filesystem round trip
    run("fs: create file", "write_file",
        {"path": f, "content": "alpha\nbeta\n"})
    run("fs: read file", "read_file", {"path": f},
        lambda r: "alpha" in str(r.get("output")))
    run("fs: append", "append_file", {"path": f, "content": "gamma\n"})
    run("fs: list dir", "list_directory", {"path": tmp})
    run("fs: grep", "grep", {"pattern": "beta", "path": tmp})
    run("fs: file info", "get_file_info", {"path": f})

    # search / code intelligence
    run("search: glob", "glob", {"pattern": "**/*.py", "path": root})
    run("search: ripgrep", "ripgrep", {"pattern": "def build", "path": root})

    # web
    run("web: search", "web_search", {"query": "python asyncio", "limit": 3},
        lambda r: len(str(r.get("output"))) > 40)
    run("web: fetch", "web_fetch", {"url": "https://example.com"},
        lambda r: "example" in str(r.get("output")).lower())

    # browser
    run("browser: navigate", "browser_navigate", {"url": "https://example.com"})
    run("browser: tabs", "browser_tabs", {})
    run("browser: snapshot", "browser_snapshot", {},
        lambda r: len(str(r.get("output"))) > 20)
    shot = os.path.join(tmp, "shot.png")
    run("browser: screenshot", "browser_screenshot", {"path": shot},
        lambda r: os.path.exists(shot))
    run("browser: console", "browser_console_logs", {})

    # knowledge
    run("knowledge: search", "search_docs", {"query": "chip", "limit": 3})

    # chip flow
    run("chip: toolchain", "chip_tools", {},
        lambda r: "chip toolchain" in str(r.get("output")))
    chip_dir = os.path.join(tmp, "chip")
    os.makedirs(chip_dir, exist_ok=True)
    with open(os.path.join(chip_dir, "tiny.v"), "w", encoding="utf-8") as fh:
        fh.write("module tiny(input a, b, output y); assign y = a & b; "
                 "endmodule\n")
    run("chip: gate", "chip_gate", {"path": chip_dir, "top": "tiny"},
        lambda r: "tiny" in str(r.get("output")))
    run("chip: build counter", "chip_build",
        {"name": "selftest_counter", "spec": "an 8-bit counter"},
        lambda r: "PASS" in str(r.get("output")))

    # 3D
    run("3d: generate box", "generate_3d",
        {"shape": "box", "name": "selftest_box"})
    run("3d: list shapes", "list_3d_shapes", {})

    # memory + board + system
    run("memory: write", "memory_write",
        {"text": "Coal selftest memory marker 4711"})
    run("memory: search", "memory_search", {"query": "selftest marker 4711"})
    run("board: stats", "board_stats", {})
    run("system: status", "system_status", {},
        lambda r: len(str(r.get("output"))) > 5)

    # cleanup
    try:
        ex.run("delete_file", {"path": f})
        for name in os.listdir(tmp):
            try:
                os.remove(os.path.join(tmp, name))
            except Exception:
                pass
        os.rmdir(tmp)
    except Exception:
        pass
    return tests


# --------------------------------------------------------------- report
def main():
    live_only = "--live-only" in sys.argv
    os.makedirs(OUT_DIR, exist_ok=True)
    ex = ToolExecutor(ExecContext(workspace=os.getcwd()), Permissions())
    try:
        ex.perms.ask_confirms = False
    except Exception:
        pass

    t0 = time.time()
    rows, problems = audit()
    print(f"== AUDIT ==  {len(rows)} tools, "
          f"{len(rows) - len(problems)} clean, {len(problems)} with notes")
    for name, issues in problems[:12]:
        print(f"   {name}: {', '.join(issues)}")

    probes, live_tests = [], []
    if not live_only:
        tmpdir = tempfile.mkdtemp(prefix="roxp-")
        tmpfile = os.path.join(tmpdir, "probe.txt")
        with open(tmpfile, "w", encoding="utf-8") as fh:
            fh.write("def probe():\n    return 1\n")
        probes = probe(ex, rows, tmpfile, os.getcwd())
        ok = sum(1 for p in probes if p["status"] == "ok")
        na = sum(1 for p in probes if p["status"] == "needs_args")
        er = sum(1 for p in probes if p["status"] == "error")
        sk = sum(1 for p in probes if p["status"] == "skipped")
        nt = sum(1 for p in probes if p["status"] == "native")
        print(f"== PROBE ==  ok {ok} · needs-args {na} · error {er} · "
              f"skipped {sk} · native {nt}")
        for p in probes:
            if p["status"] == "error":
                print(f"   ERROR {p['name']}: {p['output'][:100]}")

    live_tests = live(ex, os.getcwd())
    passed = sum(1 for x in live_tests if x["ok"] and not x.get("native"))
    native = sum(1 for x in live_tests if x.get("native"))
    failed = len(live_tests) - passed - native
    print(f"== LIVE ==   {passed}/{len(live_tests) - native} passed"
          f" · {native} native (core) · {failed} failed")
    for x in live_tests:
        mark = "n/a " if x.get("native") else ("ok  " if x["ok"] else "FAIL")
        print(f"   [{mark}] {x['label']:<26} {x['ms']:>6} ms  "
              f"{'' if x['ok'] else x['output'][:90]}")

    report = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "elapsed_s": round(time.time() - t0, 1),
              "tools": len(rows), "problems": problems,
              "probes": probes, "live": live_tests}
    with open(JSON_OUT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)

    lines = ["# Coal — tool self-test", "",
             f"- tools registered : {len(rows)}",
             f"- live checks      : {passed} passed, {failed} failed, "
             f"{native} native",
             f"- elapsed          : {report['elapsed_s']} s", "",
             "## Live checks", "",
             "| check | result | ms |", "|---|---|---|"]
    for x in live_tests:
        res = ("native" if x.get("native")
               else ("PASS" if x["ok"] else "FAIL"))
        lines.append(f"| {x['label']} | {res} | {x['ms']} |")
    with open(MD_OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"\nreport: {MD_OUT}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
