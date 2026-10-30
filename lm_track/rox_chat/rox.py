"""ROX N - the complete local assistant.

One class wires everything together:
  server lifecycle (auto-start) + forever memory + adaptive personality
  + sessions + streaming + vision + RAG + router + tools + safety.

  python rox.py                 # interactive
  python rox.py --say "hi"      # one shot
  python rox.py --status
"""
import argparse
import json
import os
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from rox_config import cfg
from server_manager import ServerManager
from streaming import stream_chat
from personality import Personality
from session import Session
from router import route, needs_tools
from observability import obs
from qwen_template import split_thinking
from tools import ToolExecutor, ExecContext, lazy_schemas, Permissions
from tools import specs as tool_specs
from tools.intent import detect_intent, needs_force

try:  # make native compilers (iverilog/vvp/gtkwave/blender) discoverable
    import toolchain
    toolchain.ensure_paths()
except Exception:
    pass

import re as _re


def _extract_file_body(text):
    """Pull the real file content out of a model reply: strip chat
    chatter, extract the first ```...``` block if present, else the
    longest run of plausible code lines."""
    t = (text or "").strip()
    if not t:
        return ""
    # 0. tool-call text format: write_file(filename=..., content=...)
    m = _re.search(r"\bwrite_file\s*\(.*?content\s*=\s*\"(.*?)\"\s*\)",
                   t, _re.S | _re.I)
    if m:
        import json as _json
        try:
            return _json.loads('"' + m.group(1) + '"')
        except Exception:
            return m.group(1).strip()
    # 0b. model echoed the target path before the fence
    #     (".../PongGame.tsx\n```tsx") -> collapse to a plain fence
    t = _re.sub(r"^[^\n]{0,80}\.(?:tsx|ts|jsx|js|py|v|sv|json|html)"
                r"\n?```(?:[a-z]+)?\s*\n", "", t, flags=_re.I)
    # 1. fenced code block
    m = _re.search(r"```(?:\w+)?\s*\n(.*?)```", t, _re.S)
    if m:
        return m.group(1).strip()
    # 3. drop leading "Here's a thinking process / 1. **...**" headers
    t = _re.sub(r"^.*?process:?\s*\n", "", t, flags=_re.S | _re.I)
    t = _re.sub(r"^\d+\.\s*\*{0,2}.*?\*{0,2}\s*\n", "", t)
    # 4. strip a leading chat line like "I've created ... :"
    t = _re.sub(r"^(here(?:'s| is)|i(?:'ve)? (?:created|wrote|made|saved)|"
                r"done|sure|ok(?:ay)?[!.]*)\s*[:\-]?\s*", "", t, flags=_re.I)
    t = _re.sub(r"^[`'\"]+", "", t)
    t = _re.sub(r"^[^\n]{0,80}:\s*\n", "", t)
    return t.strip()


def _glob_v(pattern):
    try:
        from glob import glob
        return glob(pattern, recursive=True)
    except Exception:
        return []


class Rox:
    def __init__(self, mem_root=None, session_name=None, auto_start=True,
                 workspace=None, show_thinking=False):
        from memory import Memory
        from memory.tools import MemoryTools
        from rag import RAG

        self.show_thinking = show_thinking
        self.thinking_sink = None          # optional live hook (TUI/JSON)
        self.cfg = cfg
        self.sm = ServerManager()
        if auto_start:
            try:
                self.sm.ensure()
            except Exception as e:
                print(f"[rox] server not started: {e}")
        self.mem = Memory(mem_root or cfg.memory_root)
        self.tools = MemoryTools(self.mem)
        self.personality = Personality(root=self.mem.root)
        self.rag = RAG(root=self.rag_root())
        self.session = (Session.resume(session_name) if session_name
                        else Session.latest()) or Session(session_name)
        self.turns_since_consolidate = 0
        # tool layer
        self.perms = Permissions()
        self.tctx = ExecContext(
            workspace=workspace or os.path.expanduser(
                cfg.get("tools", {}).get("workspace", "~/.rox/work")),
            ask_callback=self._confirm_prompt,
            notify_callback=lambda m: print(f"\n[rox] {m}"))
        self.texec = ToolExecutor(self.tctx, self.perms)
        # project awareness
        self.project = None
        self.project_journal = None
        self._init_project_hooks()
        # detective board (derived, provenance-rich knowledge)
        self._board = None
        self._board_retriever = None
        self._archivist = None
        self._board_lock = threading.Lock()
        self._turn_active = False
        self._last_activity = 0.0
        self._init_board()
        # optional background idle archiver (opt-in via config board.auto_archive)
        try:
            if self._archivist is not None and \
                    cfg.get("board", {}).get("auto_archive", False):
                threading.Thread(target=self._idle_loop, daemon=True).start()
        except Exception:
            pass

    def _idle_loop(self, interval=30):
        idle_s = cfg.get("board", {}).get("idle_seconds", 60)
        while True:
            time.sleep(interval)
            try:
                self.board_tick(idle_seconds=idle_s)
            except Exception:
                pass

    def _init_board(self):
        try:
            from board.store import BoardStore
            from board.retrieve import BoardRetriever
            from board.archivist import Archivist
            from board.cache import HotCache
            self._board = BoardStore(os.path.join(self.mem.root, "board.db"))
            self._board_retriever = BoardRetriever(
                self._board, self.mem.embedder, self.mem.index,
                HotCache(self._board))
            self._archivist = Archivist(
                self._board, self.mem.embedder, self.mem.index,
                server_manager=self.sm)
            self.tctx.board = self._board
        except Exception as e:
            self._board = None
            self._board_retriever = None
            self._archivist = None

    def _board_card(self, query, budget_tokens=700):
        if self._board_retriever is None:
            return ""
        try:
            return self._board_retriever.card(query,
                                              budget_tokens=budget_tokens)
        except Exception:
            return ""

    def _board_forget(self, query):
        """Cascade a forget through the derived board (nodes/edges/etc)."""
        if self._board is None or not query:
            return
        try:
            key = query.lower().strip()
            cur = self._board.conn.execute(
                "SELECT id FROM nodes WHERE canonical LIKE ? OR name LIKE ?",
                (f"%{key}%", f"%{key}%"))
            ids = [r[0] for r in cur.fetchall()]
            for i in ids:
                self._board.conn.execute(
                    "DELETE FROM edges WHERE src=? OR dst=?", (i, i))
                self._board.conn.execute(
                    "DELETE FROM aliases WHERE node_id=?", (i,))
                self._board.conn.execute(
                    "DELETE FROM node_mentions WHERE node_id=?", (i,))
                self._board.conn.execute("DELETE FROM nodes WHERE id=?", (i,))
            self._board.conn.commit()
            if self._board_retriever is not None and \
                    self._board_retriever.cache is not None:
                self._board_retriever.cache.invalidate()
        except Exception:
            pass

    def board_enqueue(self, user_text, reply, thinking="", tools=None):
        """Queue an exchange for the archivist to turn into board cards."""
        if self._board is None:
            return
        try:
            from board.queue import Queue
            Queue(self.mem.root).enqueue({
                "session_id": self.mem.session_id,
                "user_text": user_text, "output": reply,
                "thinking": thinking or "", "tools": tools or []})
        except Exception:
            pass

    def board_tick(self, idle_seconds=45):
        """Run the archivist if the machine has been idle long enough and
        no turn is in flight. Safe to call from a background thread."""
        if self._archivist is None:
            return None
        if getattr(self, "_last_activity", 0) and \
                (time.time() - self._last_activity) < idle_seconds:
            return None
        if self._turn_active or self._board_lock.locked():
            return None
        with self._board_lock:
            try:
                rep = self._archivist.run()
                if self._board_retriever is not None and \
                        self._board_retriever.cache is not None:
                    self._board_retriever.cache.invalidate()
                return rep
            except Exception:
                return None

    def _init_project_hooks(self):
        from tools import handlers_fs
        from project import Project
        self._Project = Project

        def journal_hook(abs_path, action, detail=""):
            """Called after every fs mutation; journals it if the file is
            inside the open project."""
            p = self.project
            if p is None:
                return
            try:
                src = os.path.abspath(p.source)
                ap = os.path.abspath(abs_path)
                if ap == src or ap.startswith(src + os.sep):
                    rel = os.path.relpath(ap, src).replace("\\", "/")
                    if self.project_journal is None:
                        from project.journal import Journal
                        self.project_journal = Journal(p)
                    self.project_journal.record(rel, action, detail)
            except Exception:
                pass
        handlers_fs.set_journal_hook(journal_hook)

    def _open_project(self, name):
        """Open (or create if missing) a project; refresh its scan."""
        p = self._Project.open(name)
        p.scan()
        p.save_meta()
        self.project = p
        from project.journal import Journal
        self.project_journal = Journal(p)
        self.tctx.project = p
        self.tctx.workspace = p.source  # project work happens in-source
        return p

    def _topic_from_request(self, text):
        t = text.strip()
        m = _re.search(r"\b(?:for|about)\s+(?:my|our|a|an|the|this|that)?"
                       r"\s*([A-Za-z][A-Za-z0-9\s\-]{2,40})", t, _re.I)
        if m:
            topic = m.group(1).strip()
            topic = _re.sub(r"\s+(?:that|which|using|with|to|on|in)\b.*$",
                            "", topic, flags=_re.I)
            return topic.strip() or "project"
        t = _re.sub(r"^(please\s+)?(create|start|make|build|new|a|an|the"
                    r"|project)\s+", "", t, flags=_re.I)
        t = _re.sub(r"^(my|our|a|an|the)\s+", "", t, flags=_re.I)
        t = t.strip().rstrip(".!")
        words = t.split()
        return " ".join(words[:3]) if words else "project"

    def _infer_filename(self, request, body=""):
        """Pick a sensible filename when the user didn't name one:
        snake game -> snake.html, todo app -> todo.html, etc."""
        r = (request or "").lower()
        body_l = (body or "").lower()
        # 1. explicit "called X / named X" already handled by intent; here
        #    try common nouns from the request
        topic = ""
        for kw in ("snake", "game", "todo", "calculator", "portfolio",
                   "dashboard", "blog", "chat", "login", "pong", "tetris"):
            if kw in r:
                topic = kw
                break
        # 2. extension by language mention or content
        if "python" in r or "python3" in r or "def " in body_l \
                or "py" == r.strip().split()[-1].split(".")[0]:
            ext = ".py"
        elif "html" in r or "css" in r or "website" in r or "site" in r \
                or "page" in r or "app" in r or "game" in r or \
                "portfolio" in r or "dashboard" in r or "blog" in r or \
                "<!doctype" in body_l or "<html" in body_l:
            ext = ".html"
        elif "javascript" in r or "js" in r or "script" in r \
                or "function" in body_l and "<" not in body:
            ext = ".js"
        elif "json" in r or body_l.startswith("{") or body_l.startswith("["):
            ext = ".json"
        else:
            ext = ".txt"
        if not topic:
            m = _re.search(r"\b(?:a|an|the|this|that)\s+([a-z][a-z0-9\-]{2,20})"
                           r"\s*(?:app|game|script|page|site|file)", r)
            if m:
                topic = m.group(1)
        if not topic:
            m = _re.search(r"\b(?:for|about)\s+(?:my|our|the)?\s*"
                           r"([a-z][a-z0-9\-]{2,20})", r)
            if m:
                topic = m.group(1)
        name = (topic or "file").replace(" ", "-").strip("-")
        return f"{name}{ext}"

    # extension -> which language packs to inject when writing that file
    _LANG_BY_EXT = {
        ".ts": ["typescript"], ".tsx": ["react", "tailwind", "typescript"],
        ".jsx": ["react", "tailwind"], ".js": ["typescript"],
        ".css": ["tailwind"], ".scss": ["tailwind"],
        ".v": ["verilog"], ".sv": ["verilog"], ".vh": ["verilog"],
        ".vhd": ["verilog"], ".vhdl": ["verilog"],
    }

    def _langpack_context(self, path, budget=5500):
        """Return relevant language-pack docs for the file being written,
        so ROX N follows the real modern-stack conventions."""
        ext = os.path.splitext(path or "")[1].lower()
        techs = self._LANG_BY_EXT.get(ext)
        if not techs:
            return ""
        try:
            from langpacks import root as lp_root
            parts, used = [], 0
            for tech in techs:
                d = os.path.join(lp_root(), tech)
                if not os.path.isdir(d):
                    continue
                for fn in sorted(os.listdir(d)):
                    if not fn.endswith(".md"):
                        continue
                    try:
                        c = open(os.path.join(d, fn), encoding="utf-8").read()
                    except Exception:
                        continue
                    if used + len(c) > budget:
                        c = c[:max(0, budget - used)]
                    if c:
                        parts.append(c)
                        used += len(c)
            return "\n\n".join(parts)
        except Exception:
            return ""

    def _create_project_flow(self, user_text):
        """Ask the user if they have a project name, or decide; create it."""
        from project import slugify
        # 1. try to extract an explicit name from the request
        #    ("called X", "named X", "for X" where X is a proper name)
        m = _re.search(r"\b(?:called|named)\s+[\"']?([\w][\w\s\-]{1,40}?)"
                       r"[\"']?(?:\s|$)", user_text, _re.I)
        explicit = m.group(1).strip() if m else ""
        # 2. ask the user
        if explicit:
            q = (f"I'll create a project. Should I name it "
                 f"\"{explicit}\" or do you want to call it something "
                 f"else? (or type 'you decide')")
        else:
            q = ("I'll create a project for you. Do you have a name you'd "
                 "like to use, or should I pick one based on your "
                 "request? (type a name or 'you decide')")
        choice = self._confirm_prompt(q)
        name = choice.strip()
        if name.lower() in ("you decide", "your choice", "you pick", "decide"):
            name = explicit or self._topic_from_request(user_text)
        if not name or name.lower() in ("y", "yes", "n", "no", ""):
            name = explicit or "project"
        final = slugify(name)
        try:
            p = self._open_project(final)
            return (f"Created project \"{p.name}\" at:\n{p.source}\n"
                    f"It's ready — files go here and I'll remember "
                    f"everything in my project ledger.")
        except Exception as e:
            return f"Could not create project: {e}"

    # ================================================================
    # Autonomous project builder: one prompt -> plan -> build -> audit
    # -> repair -> verify. ROX N builds whole projects on its own.
    # ================================================================
    def _gen_file(self, instruction, target_path, on_token=None,
                  _retry=0):
        """Generate one file's content (langpack + project context).
        Validates the result and retries with a stricter prompt if the
        model returned nothing or just echoed the filename."""
        write_system = (
            "You generate file content only. Output the COMPLETE file "
            "contents as a single code block with the right language tag. "
            "No commentary, no planning, no filename, just the code.")
        if self.project is not None:
            try:
                arch = self.project.architecture()
                tree = ", ".join(arch["tree"][:40]) or "(empty)"
                bodies, budget = [], 3000
                for mo in arch["modules"][:12]:
                    if mo["path"] == target_path:
                        continue  # don't feed a file back to itself
                    p = os.path.join(self.project.source, mo["path"])
                    try:
                        c = open(p, encoding="utf-8",
                                 errors="ignore").read()
                    except Exception:
                        c = ""
                    if not c:
                        continue
                    c = c[:1500]
                    if len(c) > budget:
                        break
                    budget -= len(c)
                    bodies.append(f"--- {mo['path']} ---\n{c}")
                write_system += ("\n\nProject files: " + tree +
                                 "\n\nExisting contents (match interfaces):\n"
                                 + "\n\n".join(bodies))
            except Exception:
                pass
        lp = self._langpack_context(target_path, budget=3500)
        if lp:
            write_system += ("\n\nAuthoritative conventions for this file "
                             "type:\n" + lp)
        clean = [{"role": "system", "content": write_system},
                 {"role": "user", "content": instruction}]
        text, _c, reason = stream_chat(
            clean, thinking=False, on_token=on_token, max_tokens=6000)
        body = _extract_file_body(text) or _extract_file_body(reason)
        body = (body or text or reason).strip()
        # strip any stray code fences that leaked into the body
        body = _re.sub(r"^```[a-zA-Z]*\s*\n?", "", body)
        body = _re.sub(r"\n?\s*```\s*$", "", body)
        body = _re.sub(
            r"^(verilog|vhdl|systemverilog|python|typescript|javascript|"
            r"tsx|jsx|ts|js|css|scss|json|html|bash|sh|shell|makefile|"
            r"plaintext)\s*\n", "", body)
        body = body.strip()
        # HDL guardrails: strip comment bloat + hoist misplaced decls
        if os.path.splitext(target_path)[1].lower() in (".v", ".sv", ".vh"):
            try:
                from chip_architect import hdl_fix
                body = hdl_fix(body)
            except Exception:
                pass
        # reject empty output, a bare filename/path echo, or truncation
        base = os.path.basename(target_path)
        leaked = (body == target_path or body == base or body == "```"
                  or body.startswith(target_path + "\n")
                  or body.startswith(base + "\n")
                  or body.startswith("```" + target_path))
        # Verilog/VHDL: every `module` must be closed by `endmodule`
        trunc = False
        ext = os.path.splitext(target_path)[1].lower()
        if ext in (".v", ".sv", ".vh") and body:
            trunc = (len(_re.findall(r"^\s*module\b", body, _re.M))
                     > len(_re.findall(r"^\s*endmodule\b", body, _re.M)))
        bad = not body or len(body) < 12 or leaked or trunc
        if bad and _retry < 2:
            hint = (" COMPLETE THE FILE: close every module with "
                    "endmodule." if trunc else "")
            stricter = (
                f"Write the complete contents of the file \"{target_path}\". "
                f"Output ONLY the raw file body inside one fenced code "
                f"block. Do NOT print the filename. Do NOT add any "
                f"commentary.{hint}\n\n" + instruction)
            return self._gen_file(stricter, target_path, on_token=on_token,
                                  _retry=_retry + 1)
        return body

    def _plan_project(self, description, on_token=None, _try=0):
        """Ask the model for a JSON file manifest for the project."""
        sys_p = (
            "You are a senior software engineer. Plan a complete, runnable "
            "project for the request. Output ONLY valid JSON (no markdown "
            "fence, no trailing text) shaped exactly like:\n"
            '{"name":"slug","stack":"web|node|python|hdl|plain",'
            '"files":[{"path":"relative/path.ext","instruction":'
            '"precise spec of what this file contains and its interface"}],'
            '"verify":"<shell command that builds/tests it, or empty>"}\n'
            "Use a modern stack when it fits (Vite + React + TypeScript + "
            "Tailwind for web; TypeScript+node for tools; Verilog for "
            "hardware; pure Python stdlib otherwise). Keep files focused. "
            "Include config files (package.json, tsconfig.json, "
            "tailwind.config.js, vite.config.ts) when using that stack. "
            "A project must list AT LEAST 3 files.")
        text, _c, _r = stream_chat(
            [{"role": "system", "content": sys_p},
             {"role": "user", "content": description}],
            thinking=False, max_tokens=1600)
        m = _re.search(r"\{.*\}", text or "", _re.S)
        fallback = {"name": self._topic_from_request(description),
                    "stack": "plain", "files": [], "verify": ""}
        if not m:
            if _try < 2:
                return self._plan_project(
                    description + "\n\n(Output ONLY the JSON object, "
                    "nothing else.)", on_token=on_token, _try=_try + 1)
            return fallback
        blob = m.group(0)
        blob = _re.sub(r"^```(?:json)?\s*", "", blob)
        blob = _re.sub(r"```\s*$", "", blob)
        try:
            plan = json.loads(blob)
        except Exception:
            if _try < 2:
                return self._plan_project(
                    description + "\n\n(Your last reply was not valid "
                    "JSON. Output ONLY the JSON object, no fences.)",
                    on_token=on_token, _try=_try + 1)
            return fallback
        if not isinstance(plan.get("files"), list) or not plan["files"]:
            if _try < 2:
                return self._plan_project(
                    description + "\n\n(Your plan had no files. List at "
                    "least 3 concrete files in the \"files\" array.)",
                    on_token=on_token, _try=_try + 1)
            return fallback
        return plan

    def build_project(self, description, name=None, on_token=None,
                      resume=False, finish=False):
        """Build a whole project autonomously. Returns a summary string."""
        from project import slugify
        prev = getattr(self, "_auto_approve", False)
        self._auto_approve = True
        try:
            if finish:
                return self._finish_project(slugify(name or
                                            self._topic_from_request(
                                                description)),
                                            on_token=on_token)
            return self._build_project_inner(description, name, on_token,
                                             resume=resume)
        finally:
            self._auto_approve = prev

    def _finish_project(self, nm, on_token=None):
        """Continue an existing project without re-planning: install deps,
        relax tsconfig, then verify + repair until it builds."""
        p = self._open_project(nm)
        log = [f"Finishing project '{p.name}' at {p.source}"]
        if os.path.exists(os.path.join(p.source, "package.json")) and \
                not os.path.exists(os.path.join(p.source, "node_modules")):
            res = self.texec.run("run_command",
                                 {"command": "npm install",
                                  "cwd": p.source, "timeout": 900})
            log.append(f"  npm install: {'ok' if res.get('ok') else 'FAIL'}")
        self._relax_tsconfig(p, log)
        # refresh the HDL contract's module NAMES + ports from the modules
        # that actually exist, so repairs inject the correct names
        try:
            from chip_architect import ChipArchitect
            from project.contract import Contract
            _vfs = _glob_v(os.path.join(p.source, "*.v"))
            if _vfs:
                _arch = ChipArchitect()
                _c = Contract(p.ledger)
                for _vf in _vfs:
                    _rel = os.path.relpath(_vf, p.source).replace("\\", "/")
                    _t = open(_vf, encoding="utf-8",
                              errors="ignore").read()
                    _ports = _arch.extract_ports(_t)
                    if _ports:
                        _c.set_ports(_rel, _ports,
                                     _arch.extract_module_name(_t))
                for _m in _c.modules():
                    if any(k in (_c.module_name(_m) or _m).lower()
                           for k in ("top", "cpu", "core", "soc")):
                        _c.set_top(_m)
                        break
                _c.save()
                log.append(f"  hdl contract refreshed "
                           f"({len(_c.modules())} modules)")
        except Exception:
            pass
        verify = ""
        if os.path.exists(os.path.join(p.source, "package.json")):
            verify = "npm run build"
            try:
                import json as _json
                _scr = _json.load(open(
                    os.path.join(p.source, "package.json"),
                    encoding="utf-8")).get("scripts", {})
                if "run" in _scr:
                    verify += " && npm run run"
            except Exception:
                pass
        elif _glob_v(os.path.join(p.source, "**", "*.v")):
            vfiles = " ".join('"' + f + '"' for f in
                              sorted(_glob_v(os.path.join(p.source,
                                                          "*.v"))))
            verify = ("iverilog -g2012 -o tb.vvp " + vfiles +
                      " && vvp tb.vvp")
        if verify:
            self._verify_and_repair(p, verify, log, on_token=on_token)
        self.project = p
        return "\n".join(log)

    def _build_contract(self, p, files, description):
        """For HDL projects, plan each module's ports via the chip
        architect and store them as the project's interface contract."""
        hdl = [f.get("path", "").lstrip("/\\") for f in files
               if f.get("path", "").lstrip("/\\").endswith(
                   (".v", ".sv", ".vhd", ".vhdl"))]
        if not hdl:
            return None
        try:
            from project.contract import Contract
            from chip_architect import ChipArchitect
            contract = Contract(p.ledger)
            arch = ChipArchitect()
            for rel in hdl:
                desc = ""
                for f in files:
                    if f.get("path", "").lstrip("/\\") == rel:
                        desc = (f.get("instruction") or "") + " " + \
                            description
                        break
                try:
                    res = arch.plan_ports(desc)
                    if res.get("ports"):
                        contract.set_ports(rel, res["ports"],
                                           res.get("name"))
                except Exception:
                    pass
            # pick the top module (testbench instantiates it): prefer a
            # name containing top/cpu, else the one with the most ports
            mods = contract.modules()
            top = None
            for m in mods:
                if any(k in os.path.basename(m).lower()
                       for k in ("top", "cpu", "core", "soc")):
                    top = m
                    break
            if top is None and mods:
                top = max(mods, key=lambda m: len(contract.expected_ports(m)))
            if top:
                contract.set_top(top)
            contract.save()
            return contract
        except Exception:
            return None

    def _build_project_inner(self, description, name=None, on_token=None,
                             resume=False):
        from project import slugify
        plan = self._plan_project(description, on_token=on_token)
        nm = slugify(name or plan.get("name") or
                     self._topic_from_request(description))
        p = self._open_project(nm)
        files = plan.get("files") or []
        log = [f"Building project '{p.name}' ({len(files)} files) at "
               f"{p.source}"]
        # chip: build the interface contract for HDL projects so modules
        # match each other instead of drifting
        contract = self._build_contract(p, files, description)
        for f in files:
            rel = f.get("path", "").lstrip("/\\")
            if not rel:
                continue
            fp = os.path.join(p.source, rel)
            # resume: keep files already written with real content
            if (resume and os.path.exists(fp)
                    and os.path.getsize(fp) > 60):
                log.append(f"  kept  {rel} (exists)")
                continue
            instr = (f.get("instruction") or "") + \
                (f"\n\nWrite the complete contents of the file \"{rel}\" "
                 f"for this project: " + description)
            if contract is not None and rel.endswith(
                    (".v", ".sv", ".vhd", ".vhdl")):
                mname = contract.module_name(rel)
                ports = contract.ports_text(rel)
                if ports:
                    instr += (f"\n\nThis module MUST be named `{mname}`.\n"
                              f"REQUIRED PORTS — match these EXACTLY "
                              f"(names, direction, width):\n{ports}\n")
                allm = contract.all_modules_text()
                if allm:
                    instr += ("\n\nOther modules — instantiate using these "
                              "EXACT module names and ports:\n" + allm + "\n")
            body = self._gen_file(instr, rel, on_token=on_token)
            res = self.texec.run("write_file",
                                 {"path": fp, "content": body})
            log.append(f"  {'ok' if res.get('ok') else 'FAIL'} {rel} "
                       f"({len(body)} chars)")
        # install dependencies for the stack so verify can actually run
        try:
            if os.path.exists(os.path.join(p.source, "package.json")):
                res = self.texec.run("run_command",
                                     {"command": "npm install",
                                      "cwd": p.source, "timeout": 900})
                log.append(f"  npm install: "
                           f"{'ok' if res.get('ok') else 'FAIL'}")
        except Exception as e:
            log.append(f"  npm install error: {e}")
        # relax unused-symbol checks: generated code frequently leaves
        # unused imports/params; disabling these makes builds converge
        try:
            import json as _json
            for _tsp in ("tsconfig.json", "tsconfig.node.json"):
                _tf = os.path.join(p.source, _tsp)
                if os.path.exists(_tf):
                    _raw = open(_tf, encoding="utf-8").read()
                    _clean = _re.sub(r"/\*.*?\*/", "", _raw,
                                     flags=_re.S)
                    _tj = _json.loads(_clean)
                    _co = _tj.setdefault("compilerOptions", {})
                    _co = _tj.setdefault("compilerOptions", {})
                    _co["noUnusedLocals"] = False
                    _co["noUnusedParameters"] = False
                    _json.dump(_tj, open(_tf, "w", encoding="utf-8"),
                               indent=2)
                    log.append(f"  tsconfig: disabled unused-symbol "
                               f"checks ({_tsp})")
        except Exception as e:
            log.append(f"  tsconfig patch error: {e}")
        # audit + repair loop
        try:
            p.scan()
            from project.audit import Auditor
            for _round in range(2):
                issues = Auditor(p).audit()["issues"]
                if not issues:
                    break
                log.append(f"  audit: {len(issues)} issues -> repairing")
                for it in issues[:6]:
                    if it["type"] == "missing_import":
                        fn = it["file"]
                        fix = self._gen_file(
                            f"Fix {fn}: it imports '{it['detail']}'. "
                            f"Rewrite the whole file so imports match the "
                            f"real modules. Only import names that exist.",
                            fn, on_token=on_token)
                        self.texec.run("write_file",
                                       {"path": os.path.join(p.source, fn),
                                        "content": fix})
                p.scan()
        except Exception as e:
            log.append(f"  audit error: {e}")
        # verify + repair loop: run the build; on failure, regenerate the
        # files named in the compiler output and try again.
        verify = plan.get("verify") or ""
        if verify:
            self._verify_and_repair(p, verify, log, on_token=on_token)
        self.project = p
        return "\n".join(log)

    def _related_files(self, p, fn, errfiles):
        """Files relevant when repairing `fn`: other files in the error
        batch plus everything `fn` imports (so the model matches their
        real interfaces)."""
        related = [rf for rf in errfiles if rf != fn][:3]
        fp = os.path.join(p.source, fn)
        try:
            src = open(fp, encoding="utf-8", errors="ignore").read()
        except Exception:
            src = ""
        for m in _re.finditer(
                r"(?:from\s+['\"]|import\s+['\"])(\.[^'\"]+)['\"]", src):
            imp = m.group(1).replace("\\", "/")
            cand = os.path.normpath(
                os.path.join(os.path.dirname(fn), imp)).replace("\\", "/")
            for ext in ("", ".tsx", ".ts", ".jsx", ".js"):
                p2 = cand + ext
                if os.path.exists(os.path.join(p.source, p2)):
                    if p2 != fn and p2 not in related:
                        related.append(p2)
                    break
        # HDL projects: the ISA spec lives in the asm/assembler files
        if fn.endswith((".v", ".sv", ".vhd", ".vhdl")):
            for _name in ("program.asm", "assembler.py", "memory_init.v"):
                _rel = os.path.join(os.path.dirname(fn), _name)
                if os.path.exists(os.path.join(p.source, _rel)) and \
                        _rel not in related:
                    related.append(_rel)
        return related[:5]

    # TS error codes that are LOCALIZED syntax problems (safe to patch
    # the lines around the error instead of regenerating the whole file).
    _SYNTAX_CODES = {"1003", "1005", "1006", "1056", "1109", "1110",
                     "1128", "1160", "2551"}

    def _patch_file_section(self, p, fn, err_lines, on_token=None):
        """Fix localized syntax errors by regenerating only the lines
        around each reported error line (fast, targeted)."""
        fp = os.path.join(p.source, fn)
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                lines = f.read().splitlines()
        except Exception:
            return False
        if not lines:
            return False
        # regions around each error line, merged when overlapping
        regions = []
        for ln in err_lines:
            s, e = max(0, ln - 8), min(len(lines), ln + 8)
            regions.append((s, e))
        regions.sort()
        merged = []
        for s, e in regions:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))
        changed = False
        for s, e in reversed(merged):
            section = "\n".join(lines[s:e])
            fix = self._gen_file(
                f"The file \"{fn}\" has a syntax error around line "
                f"{err_lines[0] + 1}. Rewrite ONLY the section below, "
                f"keeping roughly the same number of lines and "
                f"indentation, fixing the syntax error. Output only the "
                f"corrected section:\n{section}", fn, on_token=on_token)
            new_lines = fix.splitlines()
            if not new_lines:
                continue
            lines[s:e] = new_lines
            changed = True
        if changed:
            try:
                with open(fp, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
            except Exception:
                return False
        return changed

    def _relax_tsconfig(self, p, log):
        """Disable unused-symbol checks in the project's tsconfig(s)."""
        try:
            import json as _json
            for _tsp in ("tsconfig.json", "tsconfig.node.json"):
                _tf = os.path.join(p.source, _tsp)
                if not os.path.exists(_tf):
                    continue
                _raw = open(_tf, encoding="utf-8").read()
                _clean = _re.sub(r"/\*.*?\*/", "", _raw, flags=_re.S)
                _tj = _json.loads(_clean)
                _co = _tj.setdefault("compilerOptions", {})
                if _co.get("noUnusedLocals") or \
                        _co.get("noUnusedParameters"):
                    _co["noUnusedLocals"] = False
                    _co["noUnusedParameters"] = False
                    _json.dump(_tj, open(_tf, "w", encoding="utf-8"),
                               indent=2)
                    log.append(f"  tsconfig: disabled unused-symbol "
                               f"checks ({_tsp})")
        except Exception as e:
            log.append(f"  tsconfig patch error: {e}")

    def _missing_modules(self, out):
        """npm packages the compiler says are missing."""
        mods = []
        for m in _re.finditer(
                r"Cannot find module ['\"]([^'\"]+)['\"]", out):
            mod = m.group(1)
            if mod and mod not in mods:
                mods.append(mod)
        return mods

    def _repair_instruction(self, p, fn, base, err_ctx, related, exists,
                            errfiles, clean=False):
        """Build the regeneration prompt for a failing file. Files that
        are empty/path-echo garbage get a CLEAN "write the file" prompt
        (the model echoes the path when overloaded with error noise);
        otherwise a detailed repair prompt with error + related files."""
        fp = os.path.join(p.source, fn)
        try:
            _cur = open(fp, encoding="utf-8", errors="ignore").read()
        except Exception:
            _cur = ""
        tiny = (os.path.exists(fp) and (
            os.path.getsize(fp) < 120 or len(_cur) < 200
            or _cur.rstrip().endswith("```")))
        verb = ("Rewrite the ENTIRE file" if exists else
                "Create this missing file")
        if tiny or clean:
            instr = (f"{verb} \"{fn}\" for this project. Write the "
                     f"COMPLETE file body inside one code block. Output "
                     f"only clean, compilable code — no commentary, no "
                     f"design notes, no planning in comments. Close every "
                     f"module/block. Never output the filename.")
            # HDL: force the top module to match the testbench exactly
            if fn.endswith((".v", ".sv")):
                _tb = os.path.join(p.source, "testbench.v")
                if os.path.exists(_tb):
                    try:
                        _tb_c = open(_tb, encoding="utf-8",
                                     errors="ignore").read()[:2600]
                    except Exception:
                        _tb_c = ""
                    if _tb_c:
                        instr += ("\n\nMatch this testbench's instantiation "
                                  f"EXACTLY (identical port names, widths "
                                  f"and order):\n{_tb_c}")
            return instr
        return (f"The project build failed. {verb} \"{fn}\" so it is "
                f"complete and syntactically valid (every opened "
                f"tag/brace closed, all imports resolve, and every file "
                f"it references exists). The compiler reported:\n"
                f"{err_ctx}\n\nMatch these related files exactly "
                f"(their props/imports/exports):{related}\n"
                f"If the error is about a missing/extra prop, EITHER "
                f"pass the required props where the component is used "
                f"OR make the props optional in the component "
                f"definition. If it is an unused declaration, remove "
                f"it. Do NOT invent new interfaces.\n"
                f"Output CLEAN, complete, compilable code only. Do NOT "
                f"write design notes, reasoning, 'let's assume', or "
                f"planning in comments — the file must be production "
                f"quality.")

    def _project_rel(self, p, token):
        """Resolve a possibly-absolute/prefixed path token to a path
        relative to the project source (vite/esbuild print absolute
        paths like '...Desktop/ROX Projects/<proj>/src/main.tsx', so the
        token can start mid-path)."""
        t = token.replace("\\", "/")
        parts = t.split("/")
        for i in range(len(parts)):
            rel = "/".join(parts[i:])
            if rel.startswith(".."):
                continue
            if os.path.exists(os.path.join(p.source, rel)):
                return rel
        return t

    def _fix_module_refs(self, p, log):
        """Deterministic HDL name reconciliation: if a file instantiates a
        module name that no file defines, but a defined module name is a
        near-match (e.g. 'data_memory' vs 'data_mem'), rename the
        instantiation to the defined name."""
        try:
            from chip_architect import ChipArchitect
            arch = ChipArchitect()
            vfiles = _glob_v(os.path.join(p.source, "*.v"))
            defined = {}
            for vf in vfiles:
                nm = arch.extract_module_name(
                    open(vf, encoding="utf-8", errors="ignore").read())
                if nm:
                    defined[nm] = vf
            if not defined:
                return
            KW = {"if", "else", "always", "initial", "begin", "end", "case",
                  "endcase", "assign", "module", "endmodule", "input",
                  "output", "inout", "wire", "reg", "integer", "logic",
                  "parameter", "localparam", "for", "while", "generate",
                  "endgenerate", "function", "endfunction", "task",
                  "endtask", "posedge", "negedge", "default", "return"}
            inst_re = _re.compile(r"^\s*([A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*\(",
                                  _re.M)
            for vf in vfiles:
                t = open(vf, encoding="utf-8", errors="ignore").read()
                self_name = arch.extract_module_name(t)
                changed = False
                for m in list(inst_re.finditer(t)):
                    im = m.group(1)
                    if im in defined or im in KW or im == self_name:
                        continue
                    cand = None
                    for d in defined:
                        if d == im:
                            continue
                        if (im.startswith(d) or d.startswith(im)) or \
                                im.replace("_", "") == d.replace("_", ""):
                            cand = d
                            break
                    if cand:
                        t = _re.sub(r"\b" + _re.escape(im) + r"\b", cand, t)
                        changed = True
                if changed:
                    open(vf, "w", encoding="utf-8").write(t)
                    log.append(f"    [hdl-names] fixed module refs in "
                               f"{os.path.basename(vf)}")
        except Exception:
            pass

    def _fix_port_connections(self, p, log):
        """Deterministic: in every module instantiation, drop named-port
        connections whose port doesn't exist on the instantiated module."""
        try:
            from chip_architect import ChipArchitect
            arch = ChipArchitect()
            vfiles = _glob_v(os.path.join(p.source, "*.v"))
            defined = {}
            for vf in vfiles:
                t = open(vf, encoding="utf-8", errors="ignore").read()
                nm = arch.extract_module_name(t)
                if nm:
                    defined[nm] = {q["name"] for q in arch.extract_ports(t)}
            if not defined:
                return
            inst = _re.compile(r"\b([A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*\(")
            conn = _re.compile(r"\.(\w+)\s*\([^()]*\)")
            for vf in vfiles:
                t = open(vf, encoding="utf-8", errors="ignore").read()
                res, i, changed = [], 0, False
                while True:
                    m = inst.search(t, i)
                    if not m:
                        res.append(t[i:])
                        break
                    mod = m.group(1)
                    if mod not in defined:
                        res.append(t[i:m.end()])
                        i = m.end()
                        continue
                    depth, j = 1, m.end()
                    while j < len(t) and depth > 0:
                        if t[j] == "(":
                            depth += 1
                        elif t[j] == ")":
                            depth -= 1
                        j += 1
                    block = t[m.end():j - 1]
                    valid = defined[mod]
                    items = [mm.group(0).strip()
                             for mm in conn.finditer(block)
                             if mm.group(1) in valid]
                    nb = ",\n".join(items)
                    if nb != block.strip():
                        res.append(t[i:m.end()])
                        res.append(nb)
                        res.append(")")
                        changed = True
                    else:
                        res.append(t[i:j])
                    i = j
                nt = "".join(res)
                if changed and nt != t:
                    open(vf, "w", encoding="utf-8").write(nt)
                    log.append("    [hdl-ports] filtered invalid port "
                               f"connections in {os.path.basename(vf)}")
        except Exception:
            pass

    def _fix_top_instantiation(self, p, log):
        """Deterministic: a submodule must not instantiate the top module
        (breaks circular instantiation). Remove top-module instantiations
        from non-testbench files."""
        try:
            from chip_architect import ChipArchitect
            arch = ChipArchitect()
            vfiles = _glob_v(os.path.join(p.source, "*.v"))
            top = None
            for vf in vfiles:
                nm = arch.extract_module_name(
                    open(vf, encoding="utf-8", errors="ignore").read())
                if nm and any(k in nm.lower()
                              for k in ("top", "cpu", "soc")):
                    top = nm
                    break
            if not top:
                return
            pat = _re.compile(r"\b" + _re.escape(top) +
                              r"\s+\w+\s*\([^;]*\);", _re.S)
            for vf in vfiles:
                base = os.path.basename(vf).lower()
                if "test" in base or "tb" in base:
                    continue
                t = open(vf, encoding="utf-8", errors="ignore").read()
                if arch.extract_module_name(t) == top:
                    continue
                nt = pat.sub("", t)
                if nt != t:
                    open(vf, "w", encoding="utf-8").write(nt)
                    log.append("    [hdl-top] removed top-module "
                               f"instantiation in {os.path.basename(vf)}")
        except Exception:
            pass

    def _verify_and_repair(self, p, verify, log, on_token=None, rounds=8):
        """Run the build; on failure regenerate the broken/missing files
        named in the compiler output, then retry. Localized syntax
        errors are patched first (fast); real interface problems get a
        full regeneration."""
        out = ""
        self._repair_counts = {}
        for attempt in range(rounds):
            self._patch_budget = getattr(self, "_patch_budget", {})
            # re-apply the unused-symbol relaxation (repairs regenerate
            # tsconfig.json and re-enable it) + install missing modules
            self._relax_tsconfig(p, log)
            # HDL mechanical fix: hoist misplaced declarations +
            # strip comment bloat (no model needed)
            try:
                from chip_architect import hdl_fix
                for _vf in _glob_v(os.path.join(p.source, "*.v")):
                    _t = open(_vf, encoding="utf-8",
                              errors="ignore").read()
                    _t2 = hdl_fix(_t)
                    if _t2 != _t:
                        open(_vf, "w", encoding="utf-8").write(_t2)
                        log.append(f"    [hdl-fix] {os.path.basename(_vf)}")
            except Exception:
                pass
            self._fix_module_refs(p, log)
            self._fix_port_connections(p, log)
            self._fix_top_instantiation(p, log)
            for _mod in self._missing_modules(out):
                res2 = self.texec.run("run_command",
                                      {"command": "npm install " + _mod,
                                       "cwd": p.source, "timeout": 600})
                log.append(f"    installed missing module {_mod}: "
                           f"{'ok' if res2.get('ok') else 'FAIL'}")
            res = self.texec.run("run_command",
                                 {"command": verify, "cwd": p.source,
                                  "timeout": 600})
            ok, out = res.get("ok"), res.get("output", "")
            # strip ANSI color/control codes from the build output so path
            # parsing isn't corrupted by escape sequences
            out = _re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", out)
            log.append(f"  verify (try {attempt + 1}) '{verify}': "
                       f"{'ok' if ok else 'FAIL'}")
            if ok:
                return True
            # pass 0: vite "could not resolve entry module" -> the build
            # entry in vite.config.ts points at a missing html file
            mentry = _re.search(r'Could not resolve entry module "([^"]+)"',
                                out)
            if mentry:
                cfg = "vite.config.ts"
                fix = self._gen_file(
                    f"The vite build failed: could not resolve entry "
                    f"module \"{mentry.group(1)}\". Fix {cfg} so the build "
                    f"entry points to the real \"index.html\" at the "
                    f"project root (set input to 'index.html' or remove "
                    f"the wrong rollupOptions.input). Output the complete "
                    f"corrected vite.config.ts.", cfg, on_token=on_token)
                self.texec.run("write_file",
                               {"path": os.path.join(p.source, cfg),
                                "content": fix})
                log.append(f"    fixed vite entry in {cfg} ({len(fix)} chars)")
                continue
            # pass 1: patch localized syntax errors (fast, targeted).
            # A file gets at most 2 patch attempts; if it still fails it
            # escalates to a full regeneration below.
            syn_by_file = {}
            for m in _re.finditer(
                    r"([\w./\\-]+\.(?:tsx|ts|jsx|js|css|scss|html|vue|"
                    r"svelte|v|sv|vhd|py|json))\((\d+),\d+\):\s*error\s+"
                    r"TS(\d+):", out):
                fn = self._project_rel(p, m.group(1))
                code = m.group(3)
                if code in self._SYNTAX_CODES:
                    syn_by_file.setdefault(fn, []).append(int(m.group(2)))
            if syn_by_file:
                did_patch = False
                for fn, lins in syn_by_file.items():
                    if fn in self._patch_budget or \
                            self._patch_budget.get(fn, 0) >= 2:
                        continue
                    if self._patch_file_section(p, fn, lins,
                                                on_token=on_token):
                        self._patch_budget[fn] = \
                            self._patch_budget.get(fn, 0) + 1
                        log.append(f"    patched {fn} "
                                   f"(syntax, lines {lins[0] + 1})")
                        did_patch = True
                if did_patch:
                    continue
            # pass 1b: assembler / build-script errors (no file:line
            # format) -> regenerate the assembler script
            if ("Unknown mnemonic" in out or "Error in line" in out) and \
                    os.path.exists(os.path.join(p.source, "assembler.py")):
                fix = self._gen_file(
                    "The project assembler failed. Rewrite the ENTIRE "
                    "assembler.py so it correctly skips comment lines "
                    "(lines starting with ';' or '//') and blank lines, "
                    "parses LOAD/ADD/SUB/STORE/JNE/HALT, and writes the "
                    "memory initialization file. The assembler reported:\n"
                    + out[-800:], "assembler.py", on_token=on_token)
                self.texec.run("write_file",
                               {"path": os.path.join(p.source,
                                                     "assembler.py"),
                                "content": fix})
                log.append(f"    repaired assembler.py ({len(fix)} chars)")
                continue
            errfiles = []
            # 1. files referenced by the compiler but missing -> create
            for m in _re.finditer(r"File ['\"]([^'\"]+)['\"] not found", out):
                mp = m.group(1).replace("\\", "/")
                rel = self._project_rel(p, mp)
                if rel.startswith("..") or rel in errfiles:
                    continue
                if "node_modules" in rel:
                    continue
                if not os.path.exists(os.path.join(p.source, rel)):
                    errfiles.append(rel)
            # 2. files the compiler flagged as broken -> rewrite
            for m in _re.finditer(
                    r"([\w./\\-]+\.(?:tsx|ts|jsx|js|css|scss|html|vue|"
                    r"svelte|v|sv|vhd|py|json))[\(\s:]", out):
                fn = self._project_rel(p, m.group(1))
                if (fn not in errfiles and "node_modules" not in fn
                        and not fn.startswith("File")):
                    errfiles.append(fn)
            # 2b. truncated HDL files (unclosed module) -> regenerate
            for _vf in _glob_v(os.path.join(p.source, "*.v")):
                _rel = os.path.relpath(_vf, p.source).replace("\\", "/")
                try:
                    _t = open(_vf, encoding="utf-8",
                              errors="ignore").read()
                except Exception:
                    _t = ""
                if (len(_re.findall(r"^\s*module\b", _t, _re.M)) >
                        len(_re.findall(r"^\s*endmodule\b", _t, _re.M))
                        and _rel not in errfiles):
                    errfiles.append(_rel)
            # chip: port-conformance check against the project contract
            if getattr(p, "ledger", None):
                try:
                    from project.contract import Contract
                    from chip_architect import ChipArchitect
                    _cc = Contract(p.ledger)
                    if _cc.modules():
                        _arch = ChipArchitect()
                        for _rel in _cc.modules():
                            _fp = os.path.join(p.source, _rel)
                            if not os.path.exists(_fp) or _rel in errfiles:
                                continue
                            _rtl = open(_fp, encoding="utf-8",
                                        errors="ignore").read()
                            _ok, _miss, _extra = _arch.verify_contract(
                                _rtl, _cc.expected_ports(_rel))
                            _want_name = _cc.module_name(_rel)
                            _got_name = _arch.extract_module_name(_rtl)
                            if _want_name and _got_name and \
                                    _want_name != _got_name:
                                _ok = False
                                log.append(
                                    f"    [contract] {_rel} module is "
                                    f"'{_got_name}', expected '{_want_name}'")
                            if not _ok:
                                errfiles.append(_rel)
                                log.append(
                                    f"    [contract] {_rel} ports differ "
                                    f"(missing {_miss[:3]}, "
                                    f"extra {_extra[:3]})")
                except Exception:
                    pass
            if not errfiles:
                log.append("    " + out[-400:])
                return False
            for fn in errfiles[:3]:
                base = fn.split("/")[-1]
                err_ctx = "\n".join(
                    l for l in out.splitlines() if base in l)[:1500]
                exists = os.path.exists(os.path.join(p.source, fn))
                verb = ("Rewrite the ENTIRE file" if exists
                        else "Create this missing file")
                # include the files this file imports + other error files
                # so the model matches their real interfaces
                related = ""
                for rf in self._related_files(p, fn, errfiles):
                    rp = os.path.join(p.source, rf)
                    if not os.path.exists(rp):
                        continue
                    try:
                        rc = open(rp, encoding="utf-8",
                                  errors="ignore").read()[:2200]
                    except Exception:
                        continue
                    if rc:
                        related += f"\n--- {rf} ---\n{rc}"
                instr = self._repair_instruction(
                    p, fn, base, err_ctx, related, exists, errfiles,
                    clean=(self._repair_counts.get(fn, 0) >= 2
                           or fn.endswith((".v", ".sv", ".vhd", ".vhdl"))))
                if fn.endswith((".v", ".sv", ".vhd", ".vhdl")):
                    try:
                        from project.contract import Contract
                        _c = Contract(p.ledger)
                        _mname = _c.module_name(fn)
                        _ptx = _c.ports_text(fn)
                        if _ptx:
                            instr += (f"\n\nThis module MUST be named "
                                      f"`{_mname}`.\nREQUIRED PORTS — match "
                                      f"these EXACTLY:\n{_ptx}\n")
                        _allm = _c.all_modules_text()
                        if _allm:
                            instr += ("\n\nOther modules — instantiate "
                                      "using these EXACT names + ports:\n"
                                      + _allm + "\n")
                    except Exception:
                        pass
                fix = self._gen_file(instr, fn, on_token=on_token)
                self._repair_counts[fn] = self._repair_counts.get(fn, 0) + 1
                self.texec.run("write_file",
                               {"path": os.path.join(p.source, fn),
                                "content": fix})
                log.append(f"    {'repaired' if exists else 'created'} "
                           f"{fn} ({len(fix)} chars)")
        return False

    def _confirm_prompt(self, prompt):
        # A UI client (desktop / TUI) can supply a sink so approvals are
        # answered out-of-band. This matters in --json-repl, where stdin is
        # the command channel and input() would swallow the next command.
        sink = getattr(self, "_confirm_sink", None)
        if sink is not None:
            return sink(prompt)
        if getattr(self, "_auto_approve", False):
            print(f"\n[rox] auto-approved: {prompt.strip()[:80]}")
            return "y"
        try:
            return input(prompt + " ")
        except (EOFError, KeyboardInterrupt):
            return "n"

    def _thinking_cb(self, text):
        """Show the model's reasoning live (to stderr, so it doesn't
        corrupt the normal answer stream). Dim/bracketed."""
        if text and self.thinking_sink is not None:
            self.thinking_sink(text)
            return
        if self.show_thinking and text:
            import sys as _sys
            print(f"\n\x1b[2m[thinking] {text}\x1b[0m",
                  file=_sys.stderr, end="", flush=True)

    def rag_root(self):
        return os.path.expanduser(cfg.rag.index_path)

    # ---- safety + tools ----
    def _safety(self, text):
        from attachments import lockout_check
        return lockout_check(text)

    def _calc(self, text):
        from attachments import tool_gate
        return tool_gate(text)

    # ---- tool execution ----
    def _run_tool(self, name, args):
        """Native memory/document tools first; everything else via the
        safe executor."""
        if not name:
            return "tool call missing a name; ignore this call"
        # memory + rag are always available natively
        if name == "search_documents":
            return self.rag.context(args.get("query", "")) or "no documents"
        if name == "ask_about_image":
            from vision import ask_about_image as ask_vision
            q = args.get("question") or args.get("query") or \
                "What is in this image?"
            p = args.get("path", "")
            try:
                return ask_vision(p, q)[:1500]
            except Exception as e:
                return f"vision failed: {e}"
        if name == "search_memory" or name == "memory_search":
            hits = self.mem.search(args.get("query", ""), k=6)
            return "\n".join(f"- ({h['role']}) {h['text'][:200]}"
                             for h in hits) or "no memories"
        if name == "remember" or name == "memory_write":
            self.mem.remember(args.get("text", ""))
            return f"stored: {args.get('text','')[:80]}"
        if name == "memory_read":
            hits = self.mem.search(args.get("query", ""), k=3)
            return "\n".join(f"- {h['text'][:200]}" for h in hits) \
                or "no memories"
        if name == "update_profile":
            k, v = args.get("key", ""), args.get("value", "")
            if k.startswith("trait:"):
                self.personality.traits[k.split(":", 1)[1]] = float(v)
                self.personality.save()
                return f"trait {k} = {v}"
            self.mem.profile.set(k, v)
            return f"profile.{k} = {v}"
        if name == "forget":
            out = self.tools._forget(args.get("query", ""))
            self._board_forget(args.get("query", ""))
            return out
        # meta tools
        if name == "list_tools":
            cats = tool_specs.CATEGORIES
            return "\n".join(f"- {k}: {v}" for k, v in cats.items())
        if name == "use_category":
            cat = args.get("category", "")
            names = [s["name"] for s in tool_specs.by_category(cat)]
            return f"{cat} tools: " + ", ".join(names)
        # general executor (fs, exec, git, web, db, system, ...)
        res = self.texec.run(name, args)
        if not res.get("ok"):
            return f"tool {name} failed: {res.get('output')}"
        return res.get("output", "")

    # ---- main turn ----
    def respond(self, user_text, images=None, on_token=None):
        t0 = time.perf_counter()
        self._turn_active = True
        # 1. safety
        lo = self._safety(user_text)
        if lo["locked"]:
            self._record(user_text, lo["text"], "lockout")
            return lo["text"], {"kind": "lockout", "tools": []}
        # 2. calculator
        if not images:
            handled, calc = self._calc(user_text)
            if handled:
                self._record(user_text, calc, "calculated")
                return calc, {"kind": "arithmetic", "tools": []}
        # 3. route
        r = route(user_text, has_image=bool(images))
        # 4. memory context (+ board: structured, provenance-aware knowledge)
        board_card = self._board_card(user_text)
        mem_ctx = self.mem.assemble(user_text, board_card=board_card)["text"]
        rag_ctx = self.rag.context(user_text) if self.rag.docs else ""
        extra = mem_ctx
        if rag_ctx:
            extra += "\n\nDocuments:\n" + rag_ctx
        # project context (if a project is open)
        if self.project is not None:
            try:
                from project.context import project_context
                pctx = project_context(self.project)
                if pctx:
                    extra += "\n\nActive project:\n" + pctx
            except Exception:
                pass
        system = self.personality.system_prompt(extra_context=extra)
        # hardware-design requests must use the chip flow, not bash + files:
        # chip_build generates the RTL and runs the REAL verification gate
        try:
            from tools.specs import categories_for_trigger as _cats
            if "chip" in _cats(user_text):
                system += (
                    "\n\nHARDWARE NOTE: this is a chip/hardware design "
                    "request. Call the chip_build tool with the "
                    "specification and a name. It generates the RTL and "
                    "runs the REAL verification gate - lint, simulation, "
                    "synthesis, formal, place & route - and reports "
                    "PASS/FAIL with area and timing. Do NOT write Verilog "
                    "by hand, and do NOT use bash or write_file for this. "
                    "After it passes, use chip_views if the user wants "
                    "visuals.")
        except Exception:
            pass
        # 5. build messages
        if images:
            from vision import build_message
            user_msg = build_message(images, user_text)
        else:
            user_msg = {"role": "user", "content": user_text}
        messages = [{"role": "system", "content": system},
                    *self.session.messages(limit=10), user_msg]
        # 6. lazy-load tool schemas for this turn's intent
        tools = None
        intent = detect_intent(user_text)
        force_tool = None
        if not images:
            ensure_tool = intent.tool if needs_force(intent) and \
                intent.tool != "chat" else None
            schemas = lazy_schemas(user_text, self.perms,
                                   ensure=ensure_tool)
            if schemas:
                tools = schemas
            elif self.rag.docs:
                tools = [{"type": "function", "function": {
                    "name": "search_documents", "description":
                        "Search the user's indexed documents/files.",
                    "parameters": {"type": "object", "properties": {
                        "query": {"type": "string"}},
                        "required": ["query"]}}}]
            # intent-first: force the specific tool call
            if needs_force(intent) and intent.tool != "chat":
                force_tool = intent.tool
                if intent.tool == "write_file":
                    # The local server emits tool_calls unreliably for
                    # content-heavy writes, so we run a CONTENT-ONLY pass
                    # (model writes the body), then ROX N executes
                    # write_file itself with the confirmed path.
                    system += ("\n\nThe user asked you to create a file. "
                               "Write the COMPLETE file content now as "
                               "plain text (code). Do not describe it, do "
                               "not use tool calls, just output the full "
                               "file body.\n")
                elif intent.tool == "remember":
                    system += ("\n\nUse the remember tool to store this "
                               "fact.\n")
                elif intent.tool == "project_new":
                    system += ("\n\nAsk the user whether they already have "
                               "a name for the project, or want you to "
                               "choose one. Then create it.\n")
        # 7. generate (with tool loop)
        trace = []
        answer = ""
        last_reason = ""
        # 7a0. AUTONOMOUS PROJECT BUILD: one prompt -> whole project
        if force_tool == "build_project":
            answer = self.build_project(user_text, on_token=on_token)
            trace.append(("build_project", {"description": user_text},
                          answer))
        # 7a. IMAGE-GEN intent path: park 35B, generate, reload
        elif force_tool == "generate_image":
            from tools.handlers_image import generate_image as gen_img
            args = dict(intent.args)
            args["prompt"] = args.get("prompt") or user_text
            res = gen_img(args, self.tctx)
            trace.append(("generate_image", args, res.get("output", "")))
            answer = res.get("output", "image generation failed")
        # 7a1. IMAGE-EDIT intent path: park 35B, edit existing, reload
        elif force_tool == "edit_image":
            from tools.handlers_image import edit_image as ed_img
            args = dict(intent.args)
            args["prompt"] = args.get("prompt") or user_text
            # extract a source image path if not already in args
            if not args.get("path"):
                m = _re.search(r"([\w.\-/\\]+\.(?:png|jpg|jpeg|webp|gif))",
                               user_text)
                if m:
                    args["path"] = m.group(1)
            res = ed_img(args, self.tctx)
            trace.append(("edit_image", args, res.get("output", "")))
            answer = res.get("output", "image edit failed")
        # 7a1b. CUSTOM-IMAGE intent path: parse specs, generate or recreate
        elif force_tool == "custom_image":
            from tools.handlers_image import custom_image as cst_img
            args = dict(intent.args)
            args["description"] = args.get("description") or user_text
            # allow "recreate my <file.png> as <spec>"
            if not args.get("recreate"):
                m = _re.search(r"([\w.\-/\\]+\.(?:png|jpg|jpeg|webp|gif))",
                               user_text)
                if m:
                    args["recreate"] = m.group(1)
            res = cst_img(args, self.tctx)
            trace.append(("custom_image", args, res.get("output", "")))
            answer = res.get("output", "custom image failed")
        # 7a1c. 3D-MODEL intent path: deterministic (we run the tool)
        elif force_tool == "generate_3d":
            from tools.handlers_3d import generate_3d as gen_3d
            args = dict(intent.args)
            args["description"] = args.get("description") or user_text
            low = user_text.lower()
            for shp in ("box", "sphere", "cylinder", "cone", "torus",
                        "pyramid", "terrain", "man", "human", "person",
                        "humanoid", "figure"):
                if _re.search(r"\b" + shp + r"\b", low):
                    args["shape"] = shp
                    break
            for kw in ("tree", "rocket", "robot", "house", "table", "man",
                       "human", "person", "spiderman", "figure"):
                if kw in low:
                    args["name"] = kw
                    break
            fmts = [f for f in ("fbx", "usdz", "usd", "glb", "gltf", "ply",
                                "dae", "3mf", "obj", "stl")
                    if _re.search(r"\b" + f + r"\b", low)]
            if fmts:
                args["formats"] = fmts
            res = gen_3d(args, self.tctx)
            trace.append(("generate_3d", args, res.get("output", "")))
            answer = res.get("output", "3D generation failed")
        # 7a1d. TEXTURE intent path: unwrap + tile-paint + bake + apply
        elif force_tool == "texture_3d":
            from tools.handlers_3d import texture_3d as _tex
            args = dict(intent.args)
            m = _re.search(r"([\w.\-/\\]+\.(?:obj|stl|glb|gltf|ply|fbx|dae|"
                           r"3mf))", user_text, _re.I)
            if m:
                args["path"] = m.group(1)
            low = user_text.lower()
            for st in ("spiderman", "web", "rock", "metal", "wood", "grass",
                       "fabric", "hull"):
                if _re.search(r"\b" + st + r"\b", low):
                    args["style"] = st
                    break
            fmts = [f for f in ("fbx", "glb", "obj", "usdz", "stl", "ply")
                    if _re.search(r"\b" + f + r"\b", low)]
            if fmts:
                args["formats"] = fmts
            if _re.search(r"\b(ai|diffusion|photoreal|realistic|paint)\b",
                          low):
                args["use_ai"] = True
                args["ai_prompt"] = args.get("ai_prompt") or user_text
            # No file given but they asked to *make* a textured model ->
            # generate the base model first, then texture it (one shot).
            if not args.get("path"):
                shape = None
                for shp in ("man", "human", "person", "humanoid", "figure",
                            "robot", "tree", "house", "table", "box",
                            "sphere", "cylinder", "cone", "torus",
                            "pyramid", "terrain"):
                    if _re.search(r"\b" + shp + r"\b", low):
                        shape = shp
                        break
                if shape:
                    import threed as _t3
                    _d = os.path.join(os.path.expanduser("~/.rox/work"), "3d")
                    os.makedirs(_d, exist_ok=True)
                    _g = _t3.generate(_d, shape=shape, name=shape,
                                      formats=["obj"])
                    args["path"] = _g["files"]["obj"]
                    args["name"] = args.get("name") or f"{shape}_textured"
            res = _tex(args, self.tctx)
            trace.append(("texture_3d", args, res.get("output", "")))
            answer = res.get("output", "texturing failed")
        # 7a1e. IMAGE->3D intent path
        elif force_tool == "image_to_3d":
            from tools.handlers_3d import image_to_3d as _i3
            args = dict(intent.args)
            m = _re.search(r"([\w.\-/\\]+\.(?:png|jpg|jpeg|webp|bmp|gif))",
                           user_text, _re.I)
            if m:
                args["path"] = m.group(1)
            low = user_text.lower()
            for meth in ("relief", "silhouette", "depth"):
                if meth in low:
                    args["method"] = meth
                    break
            res = _i3(args, self.tctx)
            trace.append(("image_to_3d", args, res.get("output", "")))
            answer = res.get("output", "image->3d failed")
        # 7a1f. HIGH-RES TILED IMAGE intent path (MultiDiffusion)
        elif force_tool == "generate_hd_image":
            from tools.handlers_3d import generate_hd_image as _hd
            args = dict(intent.args)
            args["prompt"] = args.get("prompt") or user_text
            low = user_text.lower()
            if _re.search(r"\b(2048|2k)\b", low):
                args["size"] = 2048
            elif _re.search(r"\b(1024|1k)\b", low):
                args["size"] = 1024
            res = _hd(args, self.tctx)
            trace.append(("generate_hd_image", args, res.get("output", "")))
            answer = res.get("output", "hd image failed")
        # 7a2. IMAGE-UNDERSTANDING intent path
        elif force_tool in ("ask_about_image", "ocr_image"):
            # image path must come from the message or a configured path
            img = intent.args.get("path") or \
                _re.search(r"([\w.\-/\\]+\.(?:png|jpg|jpeg|gif|webp|bmp))",
                           user_text)
            if not img:
                answer = ("I can understand images, but I need an image "
                          "path. Tell me the image file path (e.g. "
                          "~/.rox/work/images/foo.png).")
            else:
                from tools import handlers_web2 as _w2
                args = {"path": img.group(1) if hasattr(img, "group")
                        else img}
                tool = "ocr_image" if force_tool == "ocr_image" \
                    else "ask_about_image"
                res = self.texec.run("ocr_image", args) if tool == \
                    "ocr_image" else self._run_tool("ask_about_image",
                                                    args)
                trace.append((tool, args, str(res)[:200]))
                answer = str(res)[:600]
        # 7b. WRITE-FILE intent path: content-only pass, then we call the
        #     tool (reliable — does not depend on model tool-call emission)
        elif force_tool == "write_file":
            # Use a CLEAN prompt for the content pass: session history can
            # make the model narrate past attempts instead of writing code.
            write_system = (
                "You generate file content only. Given the user's request, "
                "output the COMPLETE file contents as a single code block "
                "with the appropriate language tag. No commentary, no "
                "explanations, no planning, no greetings — just the code.")
            # For multi-file projects, show the model the existing project
            # structure + the actual contents of existing files so new
            # files match the real interfaces (not just symbol names).
            if self.project is not None:
                try:
                    arch = self.project.architecture()
                    tree = ", ".join(arch["tree"][:40]) or "(empty)"
                    bodies = []
                    budget = 6000
                    for mo in arch["modules"][:12]:
                        p = os.path.join(self.project.source, mo["path"])
                        try:
                            with open(p, encoding="utf-8",
                                      errors="ignore") as f:
                                c = f.read()
                        except Exception:
                            c = ""
                        if not c:
                            continue
                        c = c[:2500]
                        if len(c) > budget:
                            break
                        budget -= len(c)
                        bodies.append(f"--- {mo['path']} ---\n{c}")
                    write_system += (
                        "\n\nThe project already contains these files:\n"
                        f"{tree}\n\nExisting file contents (match these "
                        "interfaces exactly — use existing method names, "
                        "field names, and signatures):\n" +
                        "\n\n".join(bodies) +
                        "\n\nIMPORTANT: import ONLY names that are actually "
                        "defined. Call methods as obj.method(), use the "
                        "exact field names shown, and pass every required "
                        "argument.")
                except Exception:
                    pass
            # Inject modern-stack language-pack docs for the target file
            # type (TypeScript, Tailwind, React, Vite, Verilog...).
            try:
                _pre = intent.args.get("path") or \
                    _re.search(r"([\w.\-]+\.(?:tsx|ts|jsx|js|css|scss|v|sv|"
                               r"vhd|vhdl|py|html|json|md))", user_text)
                _pre = _pre.group(1) if hasattr(_pre, "group") else _pre
                lp = self._langpack_context(_pre or "")
                if lp:
                    write_system += (
                        "\n\nUse these authoritative conventions for this "
                        "file type (follow them exactly):\n" + lp)
            except Exception:
                pass
            clean = [{"role": "system", "content": write_system},
                     {"role": "user", "content": user_text}]
            text, calls, reason = stream_chat(
                clean, model=r["model"], base_url=r["base_url"],
                thinking=False, on_token=on_token,
                on_thinking=self._thinking_cb,
                max_tokens=4096)
            body_c = _extract_file_body(text)
            body_r = _extract_file_body(reason)
            # Prefer the variant that looks like real code (fenced block
            # or starts with a known code marker); otherwise prefer
            # content text over reasoning prose.
            def _is_code(s):
                s2 = s.lstrip()
                return bool(_re.search(r"```", s2)) or \
                    s2.startswith(("<", "#!/", "import ", "from ", "def ",
                                   "class ", "const ", "let ", "var ",
                                   "@", "#include", "package ", "{"))
            if body_r and (_is_code(body_r) or not _is_code(body_c)):
                body = body_r
            else:
                body = body_c or body_r
            if not body:
                body = text or reason
            args = dict(intent.args)
            # When a project is open, all files go into the project source
            # (not the generic workspace), keeping the project coherent.
            target_dir = (self.project.source if self.project is not None
                          else (args.get("location")
                                or os.path.expanduser("~/.rox/work")))
            if not args.get("path"):
                args["path"] = os.path.join(
                    target_dir, self._infer_filename(user_text, body))
            elif self.project is not None:
                # intent gave an absolute workspace path -> relocate into
                # the project, keeping just the filename (+ any subdirs)
                fn = os.path.basename(args["path"])
                if not fn:
                    fn = self._infer_filename(user_text, body)
                args["path"] = os.path.join(target_dir, fn)
            args["content"] = body
            res = self.texec.run("write_file", args)
            trace.append(("write_file", args, res.get("output", "")))
            if res.get("ok"):
                answer = f"Created the file: {args['path']}"
            else:
                answer = (f"I tried to create the file but: "
                          f"{res.get('output')}\n\n{body[:300]}")
        # 7b. INSPECT intent path (glob/read_file): run the tool for real,
        #     feed the result back, then have the model report on it.
        elif force_tool in ("glob", "read_file", "grep", "project_status",
                            "project_map", "process_list", "df", "ps"):
            tool_args = dict(intent.args)
            tool_args.setdefault("location",
                                 tool_args.get("location") or
                                 os.path.expanduser("~/.rox/work"))
            if force_tool == "glob":
                tool_args.setdefault("path",
                                     os.path.expanduser("~/.rox/work"))
                tool_args.setdefault("pattern", "**/*")
            if force_tool == "read_file":
                fname = intent.args.get("path") or \
                    _re.search(r"([\w.\-]+\.(?:html|py|js|css|txt|json|md))",
                               user_text)
                tool_args["path"] = tool_args.get("path") or os.path.join(
                    os.path.expanduser("~/.rox/work"),
                    fname.group(1) if fname else "file.txt")
            res = self.texec.run(force_tool, tool_args)
            trace.append((force_tool, tool_args, res.get("output", "")))
            tool_out = res.get("output", "")
            if not res.get("ok"):
                answer = f"Couldn't inspect: {tool_out[:200]}"
            else:
                # feed the real result to the model for a grounded answer
                summary_messages = [{"role": "system", "content":
                    "The tool result below is REAL data from the user's "
                    "files. Give a concise, useful answer about what was "
                    "found — reference the actual filenames/content, do "
                    "not repeat the request."},
                    {"role": "user", "content":
                     f"Request: {user_text}\n\nTool result:\n{tool_out}"}]
                summary, _, _ = stream_chat(
                    summary_messages, model=r["model"],
                    base_url=r["base_url"], thinking=r["thinking"],
                    on_token=on_token, on_thinking=self._thinking_cb,
                    max_tokens=600)
                answer = summary or f"Found:\n{tool_out[:400]}"
        # 7c. PROJECT-NEW intent path: ask name (or decide), then create
        elif force_tool == "project_new":
            answer = self._create_project_flow(user_text)
        # 7d. normal / other-intent path
        elif force_tool:
            forced_rounds = 3
            for _round in range(forced_rounds):
                text, calls, reason = stream_chat(
                    messages, model=r["model"], base_url=r["base_url"],
                    tools=tools, thinking=r["thinking"], on_token=on_token,
                    on_thinking=self._thinking_cb)
                last_reason = reason or last_reason
                if not calls:
                    answer = text or ""
                    break
                messages.append({"role": "assistant",
                                 "content": text or ""})
                for c in calls:
                    args = dict(c.get("arguments") or {})
                    if intent and intent.tool == c.get("name"):
                        for k, v in intent.args.items():
                            args.setdefault(k, v)
                    res = self._run_tool(c.get("name"), args)
                    trace.append((c.get("name"), args, res))
                    messages.append({"role": "tool", "content": res})
        else:
            for _round in range(4):
                text, calls, reason = stream_chat(
                    messages, model=r["model"], base_url=r["base_url"],
                    tools=tools, thinking=r["thinking"], on_token=on_token,
                    on_thinking=self._thinking_cb)
                last_reason = reason or last_reason
                if not calls:
                    answer = text or ""
                    break
                messages.append({"role": "assistant",
                                 "content": text or ""})
                for c in calls:
                    args = dict(c.get("arguments") or {})
                    if intent and intent.tool == c.get("name"):
                        for k, v in intent.args.items():
                            args.setdefault(k, v)
                    res = self._run_tool(c.get("name"), args)
                    trace.append((c.get("name"), args, res))
                    messages.append({"role": "tool", "content": res})
        if not answer and trace:
            text, _, _ = stream_chat(messages, model=r["model"],
                                     base_url=r["base_url"],
                                     thinking=r["thinking"])
            answer = text
        # 8. record
        ms = (time.perf_counter() - t0) * 1000
        self._record(user_text, answer, r["kind"], trace, ms,
                     thinking=last_reason)
        return answer, {"kind": r["kind"], "tools": trace, "ms": ms}

    def _record(self, user, reply, kind, trace=None, ms=None, thinking=""):
        self.mem.add_turn("user", user, 1.0)
        self.mem.add_turn("assistant", reply, 1.0, thinking=thinking)
        self.session.add("user", user)
        self.session.add("assistant", reply)
        self.session.save()
        self.personality.observe(user)
        obs.turn(user, reply, kind=kind, tools=trace, ms=ms,
                 model=os.path.basename(cfg.model_path() or ""))
        # queue the exchange for the archivist -> detective board
        tool_names = [t[0] for t in (trace or []) if t and t[0]]
        self.board_enqueue(user, reply, thinking=thinking, tools=tool_names)
        self._last_activity = time.time()
        self._turn_active = False
        self.turns_since_consolidate += 1
        if self.turns_since_consolidate >= cfg.memory.consolidate_every:
            self.consolidate()

    def consolidate(self):
        n = self.mem.consolidator.extract_facts_model(self.mem.session_id)
        facts = self.mem.store.all_facts(limit=20)
        self.personality.absorb_facts(facts)
        self.mem.consolidator.update_profile(self.mem.profile)
        self.turns_since_consolidate = 0
        return n

    def close(self):
        try:
            self.consolidate()
            self.mem.store.close()
            self.personality.save()
        except Exception:
            pass

    def status(self):
        out = {"server": self.sm.status(), "memory": self.mem.store.stats(),
               "personality": {"traits": self.personality.traits,
                               "desc": self.personality.describe()},
               "session": self.session.stats(), "rag": self.rag.stats(),
               "tools": {"registry": len(tool_specs.SPECS),
                         "enabled_cats": sorted(self.perms.enabled_cats),
                         "executions": len(self.tctx.trace)},
               "config": cfg.report(),
               "model_source": {
                   "serving": cfg.model_path(),
                   "hf": cfg.model.get("hf_source") or None,
                   "repos": cfg.model.get("hf_repos") or []}}
        if self._board is not None:
            try:
                from board.queue import Queue
                out["board"] = dict(self._board.stats())
                out["board"]["pending"] = Queue(self.mem.root).count()
            except Exception:
                pass
        return out


def chat_loop(r):
    print(f"ROX N ready ({os.path.basename(cfg.model_path() or '?')}). "
          f"Personality: {r.personality.describe()}. 'quit' exits.")
    while True:
        try:
            u = input("you: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        try:
            from governance import gov
            gov.touch()
        except Exception:
            pass
        if u.lower() in ("quit", "exit"):
            break
        if not u:
            continue
        print("rox: ", end="", flush=True)
        streamed = [False]
        def _tok(t):
            streamed[0] = True
            print(t, end="", flush=True)
        ans, meta = r.respond(u, on_token=_tok)
        if not streamed[0] and ans:
            print(ans, end="", flush=True)
        print(f"\n      [{meta['kind']}, {len(meta['tools'])} tools, "
              f"{meta['ms']:.0f}ms]")


def main():
    # Windows consoles default to cp1252, which can't encode model output
    # (arrows, emoji, math symbols). Use UTF-8 with lossless fallback.
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--say", default=None)
    ap.add_argument("--json-events", action="store_true",
                    help="stream newline-delimited JSON events (for the TUI)")
    ap.add_argument("--json-repl", action="store_true",
                    help="persistent session: read {\"prompt\":...} lines on "
                         "stdin, emit JSON events per turn (for the TUI)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--session", default=None)
    ap.add_argument("--no-autostart", action="store_true")
    ap.add_argument("--resume", default=None,
                    help="resume building this named project (keeps "
                         "existing files, then audits + verifies)")
    ap.add_argument("--finish", default=None,
                    help="finish this named project: no re-plan, just "
                         "install deps + verify + repair until it builds")
    ap.add_argument("--show-thinking", action="store_true",
                    help="stream the model's reasoning live (dim text)")
    ap.add_argument("--archive", action="store_true",
                    help="run the archivist now (build the detective board "
                         "from pending exchanges), then exit")
    ap.add_argument("--board-export", default=None,
                    help="export openable board cards (JSON) to this path")
    ap.add_argument("--board-ui", action="store_true",
                    help="serve the detective board UI in a browser")
    ap.add_argument("--learn", nargs="?", const="", default=None,
                    help="run one autonomous learning cycle now (optional "
                         "topic), print the report, then exit")
    ap.add_argument("--learn-stats", action="store_true",
                    help="print the learning brain's state, then exit")
    ap.add_argument("--no-network", action="store_true",
                    help="keep learning offline (no web sources)")
    ap.add_argument("--improve", action="store_true",
                    help="run one self-improvement cycle (dry-run unless "
                         "selfimprove.dry_run is false), then exit")
    ap.add_argument("--improve-status", action="store_true",
                    help="print self-improvement status (genome, scoreboard, "
                         "signals), then exit")
    ap.add_argument("--build", nargs=2, metavar=("NAME", "DIR"),
                    default=None,
                    help="run the builder loop (compile/test/repair) on an "
                         "existing sandbox project dir, then exit")
    ap.add_argument("--stack", default=None, help="stack for --build")
    ap.add_argument("--criteria", default=None,
                    help="comma-separated acceptance criteria for --build")
    ap.add_argument("--no-polish", action="store_true",
                    help="skip polishing for --build")
    ap.add_argument("--daemon", action="store_true",
                    help="run the always-on autonomous daemon (learning / "
                         "improvement) in the foreground")
    ap.add_argument("--supervise", action="store_true",
                    help="run the 24/7 supervisor: keeps relaunching the "
                         "daemon worker forever")
    ap.add_argument("--manifest", action="store_true",
                    help="print the ROX N model identity + provenance "
                         "manifest, then exit")
    ap.add_argument("--mission-queue", action="store_true",
                    help="show the mission queue status, then exit")
    ap.add_argument("--mission-queue-run", type=int, default=None,
                    metavar="N", help="build the next N pending missions, "
                                      "then exit")
    ap.add_argument("--mission-queue-reset", action="store_true",
                    help="reset the mission queue to all-pending")
    ap.add_argument("--daemon-once", action="store_true",
                    help="run one daemon tick, then exit")
    ap.add_argument("--daemon-status", action="store_true",
                    help="print governance health/telemetry, then exit")
    ap.add_argument("--finetune-plan", action="store_true",
                    help="print the QLoRA fine-tune plan/estimate, then exit")
    ap.add_argument("--finetune-export", nargs="?", const="", default=None,
                    help="export the fine-tune bundle (dataset + script + "
                         "runbook) to an optional dir, then exit")
    ap.add_argument("--missions", action="store_true",
                    help="list the extreme mission catalog, then exit")
    ap.add_argument("--mission", default=None,
                    help="build an extreme mission by name (e.g. helios-16, "
                         "meridian-16, vision-2, aldra-asm, tess-emu, "
                         "parallax-3d, forge-mesh), then exit")
    ap.add_argument("--install-daemon", action="store_true",
                    help="install the always-on daemon to run at logon")
    ap.add_argument("--uninstall-daemon", action="store_true",
                    help="remove the always-on daemon startup entry")
    args = ap.parse_args()

    if args.missions:
        from builder import build, missions
        print("EXTREME MISSION CATALOG\n")
        for n in build.missions():
            s = missions.load(n)
            print(f"  {n:14s} [{s.get('stack', '?'):9s}] {s.get('title', '')}")
        return
    if args.mission:
        from builder import build
        rep = build.generate_mission(args.mission)
        print(json.dumps(rep, indent=1, default=str))
        return

    if args.install_daemon or args.uninstall_daemon:
        startup = os.path.join(
            os.environ.get("APPDATA", ""), "Microsoft", "Windows",
            "Start Menu", "Programs", "Startup")
        bat = os.path.join(startup, "ROX_N_Daemon.bat")
        if args.uninstall_daemon:
            try:
                os.remove(bat)
                print(f"[rox] removed daemon startup: {bat}")
            except Exception as e:
                print(f"[rox] nothing to remove ({e})")
            return
        os.makedirs(startup, exist_ok=True)
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.exists(pyw):
            pyw = sys.executable
        entry = os.path.abspath(__file__)
        logdir = os.path.join(os.path.expanduser("~"), ".rox", "governance")
        os.makedirs(logdir, exist_ok=True)
        log = os.path.join(logdir, "daemon.log")
        content = ("@echo off\r\n"
                   f'start "" /min "{pyw}" "{entry}" --supervise '
                   f'>> "{log}" 2>&1\r\n')
        with open(bat, "w", encoding="ascii") as f:
            f.write(content)
        print(f"[rox] installed daemon startup: {bat}")
        print(f"[rox] it will run at logon and log to {log}")
        return

    if args.finetune_plan:
        from finetune import tune
        print(json.dumps(tune.plan(), indent=1, default=str))
        return
    if args.finetune_export is not None:
        from finetune import tune
        print(json.dumps(tune.export(args.finetune_export or None),
                         indent=1, default=str))
        return

    if args.daemon_status:
        from governance import gov
        print(json.dumps({"health": gov.health(),
                          "resources": gov.resources(),
                          "summary": gov.summary()},
                         indent=1, default=str))
        return
    if args.daemon_once:
        from governance import gov
        print(json.dumps(gov.tick(force_idle=True), indent=1, default=str))
        return
    if args.manifest:
        from rox_config import cfg as _cfg
        p = os.path.join(_cfg.install_dir, "models", "variants",
                         "roxn_manifest.json")
        info = {"identity": "ROX-N 35B A3B (ROX N branded build)",
                "base": _cfg.model.get("base_model", "Qwen/Qwen3.6-35B-A3B"),
                "license": _cfg.model.get("license", "apache-2.0"),
                "model": _cfg.report()}
        if os.path.exists(p):
            try:
                info["manifest"] = json.load(open(p, encoding="utf-8"))
            except Exception:
                pass
        print(json.dumps(info, indent=1, default=str))
        return
    if args.mission_queue:
        from builder import mission_queue as _mq
        print(json.dumps(_mq.summary(), indent=1, default=str))
        return
    if args.mission_queue_reset:
        from builder import mission_queue as _mq
        print(json.dumps(_mq.reset(), indent=1, default=str))
        return
    if args.mission_queue_run is not None:
        from autonomy import activities as _act
        print(json.dumps(_act.mission_queue(limit=int(args.mission_queue_run)),
                         indent=1, default=str))
        return
    if args.supervise:
        from governance import daemon as _gd
        print(json.dumps(_gd.supervise(), indent=1, default=str))
        return
    if args.daemon:
        from governance import gov
        print("[rox] daemon starting (Ctrl-C to stop) ...")
        print(json.dumps(gov.daemon(once=False), indent=1, default=str))
        return

    if args.build:
        from builder import build
        name, d = args.build
        crit = [c for c in (args.criteria or "").split(",") if c.strip()]
        rep = build.run(name, d, stack=args.stack, criteria=crit,
                        polish=not args.no_polish)
        print(json.dumps(rep, indent=1, default=str))
        return

    if args.improve_status:
        from selfimprove import improve
        print(json.dumps(improve.status(), indent=1, default=str))
        return
    if args.improve:
        from selfimprove import improve
        print(json.dumps(improve.run(), indent=1, default=str))
        return

    if args.learn_stats:
        import learning
        print(json.dumps(learning.brain.stats(), indent=1, default=str))
        return
    if args.learn is not None:
        import learning
        rep = learning.brain.cycle(topic=(args.learn or None),
                                   allow_network=not args.no_network)
        print(json.dumps(rep, indent=1, default=str))
        return

    r = Rox(session_name=args.session,
            auto_start=not args.no_autostart,
            show_thinking=args.show_thinking)
    if args.status:
        print(json.dumps(r.status(), indent=1))
        return
    if args.archive:
        if r._archivist is None:
            print("[rox] board unavailable")
        else:
            rep = r.board_tick(idle_seconds=0)
            print(f"[rox] archive: {rep}")
        r.close()
        return
    if args.board_export:
        try:
            from board.export import write_json
            out, n = write_json(r._board, args.board_export)
            print(f"[rox] wrote {n} cards -> {out}")
        except Exception as e:
            print(f"[rox] export failed: {e}")
        r.close()
        return
    if args.board_ui:
        try:
            from board import ui as board_ui
            board_ui.serve(board=r._board, port=8790, open_browser=True)
        except Exception as e:
            print(f"[rox] board ui failed: {e}")
        r.close()
        return
    if args.json_events:
        import json as _json

        def _emit(obj):
            sys.stdout.write(_json.dumps(obj, default=str) + "\n")
            sys.stdout.flush()

        def _jtok(t):
            _emit({"t": "token", "text": t})

        def _jthink(t):
            _emit({"t": "thinking", "text": t})

        r.thinking_sink = _jthink
        try:
            from router import route as _route
            _rm = _route(args.say or "").get("model")
        except Exception:
            _rm = (cfg.get("model", {}) or {}).get("name", "local")
        _emit({"t": "start", "prompt": args.say, "model": _rm})
        _t0 = time.perf_counter()
        try:
            ans, meta = r.respond(args.say, on_token=_jtok)
            for tr in (meta.get("tools") or []):
                try:
                    name, a, out = tr
                except Exception:
                    name, a, out = str(tr), {}, ""
                _emit({"t": "tool", "name": name, "args": a,
                       "output": str(out)[:4000]})
            _emit({"t": "answer", "text": ans})
            _emit({"t": "done",
                   "ms": int((time.perf_counter() - _t0) * 1000),
                   "kind": meta.get("kind")})
        except Exception as e:
            _emit({"t": "error", "message": str(e)[:600]})
        r.close()
        return
    if args.json_repl:
        import json as _json

        def _emit(obj):
            sys.stdout.write(_json.dumps(obj, default=str) + "\n")
            sys.stdout.flush()

        def _jtok(t):
            _emit({"t": "token", "text": t})

        def _jthink(t):
            _emit({"t": "thinking", "text": t})

        r.thinking_sink = _jthink
        try:
            _rm = (cfg.get("model", {}) or {}).get("name", "local")
        except Exception:
            _rm = "local"
        try:
            _pers = r.personality.describe()
        except Exception:
            _pers = ""
        try:
            from chipflow import model as _cm
            _llm = _cm.provider_status()
        except Exception:
            _llm = {}
        _emit({"t": "ready", "model": _rm, "personality": _pers,
               "llm": _llm})
        import queue as _queue
        import threading as _threading

        _inbox = _queue.Queue()
        _replies = _queue.Queue()

        def _handle_line(_ln):
            _ln = _ln.strip()
            if not _ln:
                return
            try:
                _obj = _json.loads(_ln)
            except Exception:
                _emit({"t": "error", "message": "bad json request"})
                return
            # approvals must bypass the command queue: the main loop is
            # blocked inside the tool while it waits for this answer
            if isinstance(_obj, dict) and "confirm" in _obj:
                _replies.put(bool(_obj.get("confirm")))
            else:
                _inbox.put(_obj)

        def _reader():
            # A *blocking* read on a stdin pipe stalls the rest of the
            # process on Windows: a tool importing a module (DLL/file reads)
            # never finished while the reader sat in readline(), so chip
            # builds froze with the UI on "thinking". Avoid the blocking read
            # entirely: real non-blocking mode where allowed, else peek at the
            # pipe before reading.
            def _feed(_raw_line):
                _handle_line(_raw_line.decode("utf-8", "replace"))

            fd = None
            try:
                fd = sys.stdin.fileno()
            except Exception:
                fd = None

            if fd is not None:
                try:
                    os.set_blocking(fd, False)
                    _emit({"t": "stdin-mode", "mode": "nonblocking"})
                    _buf = b""
                    while True:
                        try:
                            _chunk = os.read(fd, 4096)
                        except BlockingIOError:
                            time.sleep(0.02)
                            continue
                        except (OSError, ValueError):
                            break
                        if not _chunk:
                            break
                        _buf += _chunk
                        while b"\n" in _buf:
                            _raw, _, _buf = _buf.partition(b"\n")
                            _feed(_raw)
                    if _buf.strip():
                        _feed(_buf)
                    _inbox.put(None)
                    return
                except Exception:
                    pass
                # Windows pipes opened by the parent refuse set_blocking
                # (WinError 5), so poll with PeekNamedPipe instead.
                try:
                    import ctypes
                    import msvcrt
                    from ctypes import wintypes

                    _k = ctypes.WinDLL("kernel32", use_last_error=True)
                    _peek = _k.PeekNamedPipe
                    _peek.argtypes = [wintypes.HANDLE, wintypes.LPVOID,
                                      wintypes.DWORD, wintypes.LPDWORD,
                                      wintypes.LPDWORD, wintypes.LPDWORD]
                    _peek.restype = wintypes.BOOL
                    _h = msvcrt.get_osfhandle(fd)
                    _avail = wintypes.DWORD(0)
                    if _peek(_h, None, 0, None, ctypes.byref(_avail), None):
                        _emit({"t": "stdin-mode", "mode": "peek"})
                        _buf = b""
                        while True:
                            _avail.value = 0
                            if not _peek(_h, None, 0, None,
                                         ctypes.byref(_avail), None):
                                # 109 = ERROR_BROKEN_PIPE -> writer closed
                                if ctypes.get_last_error() == 109:
                                    break
                                time.sleep(0.02)
                                continue
                            if _avail.value == 0:
                                time.sleep(0.02)
                                continue
                            _chunk = os.read(fd, min(int(_avail.value), 8192))
                            if not _chunk:
                                break
                            _buf += _chunk
                            while b"\n" in _buf:
                                _raw, _, _buf = _buf.partition(b"\n")
                                _feed(_raw)
                        if _buf.strip():
                            _feed(_buf)
                        _inbox.put(None)
                        return
                except Exception as _e:
                    _emit({"t": "stdin-mode", "mode": "peek-failed",
                           "error": str(_e)[:120]})
            _emit({"t": "stdin-mode", "mode": "blocking"})
            # console / unusual stream: blocking iteration is safe there
            for _ln in sys.stdin:
                _handle_line(_ln)
            _inbox.put(None)          # EOF -> stop the loop

        _threading.Thread(target=_reader, daemon=True).start()

        _cid = [0]

        def _confirm_sink(prompt):
            """Emit a confirm event and block until the client answers.

            Runs on the thread that is executing the tool, while the reader
            thread keeps draining stdin, so approvals work mid-command.
            """
            _cid[0] += 1
            cid = _cid[0]
            _emit({"t": "confirm", "id": cid, "prompt": str(prompt)[:800]})
            try:
                allow = _replies.get(timeout=120)
            except Exception:
                _emit({"t": "confirm-done", "id": cid, "allow": False})
                return "n"
            _emit({"t": "confirm-done", "id": cid, "allow": bool(allow)})
            return "y" if allow else "n"

        r._confirm_sink = _confirm_sink

        while True:
            _req = _inbox.get()
            if _req is None:                  # stdin closed
                break

            # approval reply for a pending tool
            if "confirm" in _req:
                _replies.put(bool(_req.get("confirm")))
                continue

            # direct tool invocation (desktop shell, scripts)
            if _req.get("tool"):
                _tn = str(_req.get("tool"))
                _ta = _req.get("args") or {}
                _t0 = time.perf_counter()
                _emit({"t": "start", "prompt": f"{_tn} {_ta}"})
                try:
                    _res = r.texec.run(_tn, _ta)
                    _txt = str(_res.get("output") or "")
                    _emit({"t": "tool", "name": _tn, "args": _ta,
                           "output": _txt[:4000]})
                    _emit({"t": "answer", "text": _txt})
                    _emit({"t": "done",
                           "ms": int((time.perf_counter() - _t0) * 1000),
                           "kind": "tool"})
                except Exception as _e:
                    _emit({"t": "error", "message": str(_e)[:600]})
                continue

            _p = (_req.get("prompt") or "").strip()
            if _p.lower() in ("quit", "exit"):
                break
            if not _p:
                continue
            _t0 = time.perf_counter()
            _emit({"t": "start", "prompt": _p})
            try:
                _ans, _meta = r.respond(_p, on_token=_jtok)
                for _tr in (_meta.get("tools") or []):
                    try:
                        _n, _a, _o = _tr
                    except Exception:
                        _n, _a, _o = str(_tr), {}, ""
                    _emit({"t": "tool", "name": _n, "args": _a,
                           "output": str(_o)[:4000]})
                _emit({"t": "answer", "text": _ans})
                _emit({"t": "done",
                       "ms": int((time.perf_counter() - _t0) * 1000),
                       "kind": _meta.get("kind")})
            except Exception as _e:
                _emit({"t": "error", "message": str(_e)[:600]})
        r.close()
        return
    if args.say:
        streamed = [False]
        def _tok(t):
            streamed[0] = True
            print(t, end="", flush=True)
        if args.resume:
            ans = r.build_project(args.say, name=args.resume,
                                  on_token=_tok, resume=True)
            print(ans, end="", flush=True)
            streamed[0] = True
        elif args.finish:
            ans = r.build_project(args.say or "finish project",
                                  name=args.finish, on_token=_tok,
                                  finish=True)
            print(ans, end="", flush=True)
            streamed[0] = True
        else:
            ans, meta = r.respond(args.say, on_token=_tok)
        if not streamed[0] and ans:
            print(ans, end="", flush=True)
        print()
        r.close()
        return
    try:
        chat_loop(r)
    finally:
        try:
            from board.queue import Queue
            if r._archivist is not None and Queue(r.mem.root).count() > 0:
                print("\n[rox] archiving this conversation to the board...")
                r.board_tick(idle_seconds=0)
        except Exception:
            pass
        r.close()


if __name__ == "__main__":
    main()
