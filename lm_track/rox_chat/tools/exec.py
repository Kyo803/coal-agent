"""Safe tool executor: permission gate + timeout + result cap.

  from tools.exec import ToolExecutor, ExecContext
  ctx = ExecContext(workspace="~/.rox/work", ask_callback=confirm_fn)
  ex = ToolExecutor(ctx)
  result = ex.run("write_file", {"path": "x.txt", "content": "hi"})
  # -> {"ok": True, "output": "...", "needs_confirm": True}  (tier-1)
"""
from __future__ import annotations

import concurrent.futures
import os
import time

from .permissions import Permissions
from . import specs as S

RESULT_CAP = 6000   # characters returned to the model
TIME_LIMIT = 600    # seconds per handler (sandbox builds/installs can be long)


class ExecContext:
    def __init__(self, workspace=None, ask_callback=None,
                 notify_callback=None):
        self.workspace = os.path.abspath(os.path.expanduser(
            workspace or "~/.rox/work"))
        os.makedirs(self.workspace, exist_ok=True)
        self.ask_callback = ask_callback
        self.notify_callback = notify_callback
        self.user_text = ""
        self.todos = []
        self.scheduled = []
        self.mcp_tools = []
        self.trace = []


class ToolExecutor:
    def __init__(self, ctx=None, perms=None):
        self.ctx = ctx or ExecContext()
        self.perms = perms or Permissions()
        # One persistent worker thread for every tool call. Playwright's sync
        # objects are bound to the thread that created them, so a fresh
        # thread per call killed the browser between actions.
        self._pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="rox-tool")

    def _cap(self, output):
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
        output = str(output)
        if len(output) > RESULT_CAP:
            return output[:RESULT_CAP] + f"\n...[truncated, {len(output)} chars]"
        return output

    def _confirm(self, name, args):
        """Ask the user before a Tier-1 action. Returns True if approved."""
        if not self.perms.ask_confirms:
            return True
        if not self.ctx.ask_callback:
            return True   # headless: allow (orchestrated)
        desc = (args.get("path") or args.get("command")
                or args.get("message") or args.get("package")
                or args.get("url") or "")
        action = f"{name}({desc})" if desc else name
        try:
            ans = self.ctx.ask_callback(
                f"Allow this action? ({action}) [y/n]: ")
            return str(ans).strip().lower() in ("y", "yes", "ok")
        except Exception:
            return False

    def run(self, name, args=None, category=None):
        args = args or {}
        spec = S.get(name)
        if spec is None:
            return {"ok": False, "output": f"unknown tool: {name}",
                    "tool": name}
        # Required arguments are declared in the spec. Without this check a
        # model that emits write_file with no path silently writes into the
        # workspace default (this happened: a refusal text became file.txt).
        missing = [k for k in (spec.get("required") or [])
                   if k not in args or args.get(k) is None]
        if missing:
            return {"ok": False,
                    "output": f"{name}: missing required argument(s): "
                              f"{', '.join(missing)}",
                    "tool": name, "invalid_args": True}
        declared = spec["tier"]
        # Hard safety gate: a clear "make me malware" request must never
        # reach a mutating tool, on any route (agent loop or forced intent).
        try:
            from safety import blocks_tool_for, REFUSAL as _REF
            if blocks_tool_for(getattr(self.ctx, "user_text", ""), name):
                return {"ok": False, "policy": "refused",
                        "output": _REF + "\n\n(refused by safety policy; "
                                  "no tool was run)", "tool": name}
        except Exception:
            pass
        if self.perms.blocked(name, declared) and name not in self.perms.allow_tier2:
            return {"ok": False,
                    "output": f"tool '{name}' is disabled (Tier 2). "
                              f"Enable it via config tools.allow_tier2.",
                    "tool": name}
        if self.perms.needs_confirm(name, declared):
            ok = self._confirm(name, args)
            if not ok:
                return {"ok": False, "output": "user declined the action.",
                        "tool": name, "needs_confirm": True}

        handler = spec["handler"]
        if handler is None:
            return {"ok": False, "output":
                    f"tool '{name}' is handled natively by ROX N core, "
                    f"not the executor.", "tool": name}
        t0 = time.perf_counter()
        try:
            fut = self._pool.submit(handler, args, self.ctx)
            res = fut.result(timeout=TIME_LIMIT)
        except concurrent.futures.TimeoutError:
            return {"ok": False,
                    "output": f"tool '{name}' timed out after {TIME_LIMIT}s",
                    "tool": name}
        except Exception as e:
            return {"ok": False, "output": f"tool '{name}' error: {e}",
                    "tool": name}
        ms = (time.perf_counter() - t0) * 1000
        if not isinstance(res, dict):
            res = {"ok": True, "output": str(res)}
        res.setdefault("ok", True)
        res["output"] = self._cap(res.get("output", ""))
        res["tool"] = name
        res["ms"] = round(ms)
        self.ctx.trace.append({"tool": name, "ms": round(ms),
                               "ok": res.get("ok")})
        return res


def lazy_schemas(text, perms=None, max_tools=30, ensure=None):
    """Return OpenAI-style tool schemas for the categories a message
    triggers, plus the memory tools. Keeps per-turn tool count sane.

    ensure: a tool name that MUST be in the result (used by the intent
    layer to guarantee the forced tool is available)."""
    perms = perms or Permissions()
    cats = S.categories_for_trigger(text)
    # memory tools are always the most valuable; then the triggered cats.
    # "chip" leads: a chip-design request must always surface chip_build
    # (the real verification gate) ahead of generic execution/file tools,
    # otherwise the cap can truncate it away entirely.
    priority = ["chip", "security", "sandbox", "execution", "filesystem",
                "git", "web", "search",
                "database", "system", "browser", "orchestration",
                "output", "monitoring", "project", "knowledge", "learning"]
    ordered = [c for c in priority if c in cats]
    ordered += [c for c in cats if c not in priority]
    names = []
    for c in ordered:
        if not perms.category_enabled(c):
            continue
        for s in S.by_category(c):
            if perms.tier(s["name"], s["tier"]) != 2:
                names.append(s["name"])
    # always include memory tools (handled natively)
    for m in S.MEMORY_TOOLS:
        names.append(m)
    # guarantee the intent-forced tool is exposed
    if ensure:
        names.append(ensure)
    # ...and that a broad request can still act: a long category list must
    # never crowd out the basic file/exec tools (this made the model claim
    # it had created files while write_file was not even offered).
    for e in ("read_file", "write_file", "list_directory", "run_command"):
        if e in names:
            continue
        sp = S.get(e)
        if sp and perms.tier(e, sp["tier"]) != 2:
            names.append(e)
    # NOTE: list_tools/use_category are intentionally NOT exposed to the
    # model — they tempt it to "navigate the menu" instead of doing real
    # work (e.g. calling glob/read_file). Categories are already
    # lazy-loaded per turn, so the model never needs them.
    # cap: keep memory first, then filled categories in priority order
    seen, schemas = set(), []
    core = ["search_memory", "remember", "memory_search", "memory_read",
            "memory_write", "forget", "update_profile", "ask_about_image",
            "ocr_image", "generate_image"]
    ordered_names = [n for n in names if n in core] + \
                    [n for n in names if n not in core]
    for n in ordered_names:
        if n in seen:
            continue
        if len(schemas) >= max_tools:
            break
        seen.add(n)
        s = S.get(n)
        if s is None:
            if n in _NATIVE_SCHEMAS:
                schemas.append(_NATIVE_SCHEMAS[n])
            else:
                schemas.append(_meta_schema(n))
            continue
        schemas.append({
            "type": "function",
            "function": {
                "name": s["name"],
                "description": s["desc"],
                "parameters": {"type": "object",
                               "properties": s["params"],
                               "required": s["required"]},
            },
        })
    return schemas


def _meta_schema(name):
    if name == "list_tools":
        return {"type": "function", "function": {
            "name": "list_tools",
            "description": "List all available tool categories and "
                           "examples (use when you need a capability "
                           "not in your current tool set).",
            "parameters": {"type": "object", "properties": {}}}}
    return {"type": "function", "function": {
        "name": "use_category",
        "description": "Load a tool category into context so you can "
                       "use its tools.",
        "parameters": {"type": "object", "properties": {
            "category": {"type": "string",
                         "description": "e.g. filesystem, search, "
                                        "execution, git, web, database, "
                                        "system, orchestration, output"}},
            "required": ["category"]}}}


# schemas for native tools that rox.py executes (memory, profile, rag)
_NATIVE_SCHEMAS = {
    "ask_about_image": {"type": "function", "function": {
        "name": "ask_about_image",
        "description": "Describe / answer questions about an image using "
                       "the local vision model.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "question": {"type": "string"}},
            "required": ["path"]}}},
    "search_memory": {"type": "function", "function": {
        "name": "search_memory",
        "description": "Search the user's long-term memory for relevant "
                       "past conversations, facts, projects, preferences.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "what to look for"}},
            "required": ["query"]}}},
    "remember": {"type": "function", "function": {
        "name": "remember",
        "description": "Store an important fact about the user for "
                       "future sessions (names, projects, preferences).",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "the fact"}},
            "required": ["text"]}}},
    "forget": {"type": "function", "function": {
        "name": "forget",
        "description": "Delete matching memories (privacy request).",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}}, "required": ["query"]}}},
    "update_profile": {"type": "function", "function": {
        "name": "update_profile",
        "description": "Update the user's profile (style=concise, "
                       "name=WERU, trait:humor=0.7).",
        "parameters": {"type": "object", "properties": {
            "key": {"type": "string"}, "value": {"type": "string"}},
            "required": ["key", "value"]}}},
    "memory_read": {"type": "function", "function": {
        "name": "memory_read",
        "description": "Read relevant memories for a query.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}}, "required": ["query"]}}},
    "memory_search": {"type": "function", "function": {
        "name": "memory_search",
        "description": "Search long-term memory.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}}, "required": ["query"]}}},
    "memory_write": {"type": "function", "function": {
        "name": "memory_write",
        "description": "Write to long-term memory.",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"}}, "required": ["text"]}}},
    "search_documents": {"type": "function", "function": {
        "name": "search_documents",
        "description": "Search the user's indexed documents/files.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}}, "required": ["query"]}}},
}


def all_categories():
    return S.CATEGORIES


if __name__ == "__main__":
    p = Permissions()
    print("--- lazy schemas for 'git status' ---")
    schemas = lazy_schemas("git status and diff", p)
    print(f"{len(schemas)} tools")
    print([s["function"]["name"] for s in schemas][:12], "...")

    ctx = ExecContext(workspace="~/.rox/work")
    ex = ToolExecutor(ctx, p)
    print("--- exec tests ---")
    print(ex.run("write_file",
                 {"path": "demo.txt", "content": "hello rox"}))
    print(ex.run("read_file", {"path": "demo.txt"}))
    print(ex.run("grep", {"pattern": "hello", "path": "~/.rox/work"}))
    print(ex.run("data_analysis", {"values": [1, 2, 3, 4, 5]}))
    print(ex.run("aws_cli", {"command": "ls"}))