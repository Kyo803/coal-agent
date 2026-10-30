"""Intent interpreter — the purpose-first layer.

Reads a user message and decides WHICH specific tool Coal should call,
with confidence. High-confidence intent forces tool_choice so the model
MUST emit that exact tool call instead of improvising.

  from tools.intent import detect_intent
  i = detect_intent("make a file called guard.py that blocks SQLi")
  i.tool == "write_file", i.confidence == "high",
  i.args == {"path": "guard.py", "location": "workspace"}

Patterns are ordered by specificity; the first match wins.
"""
from __future__ import annotations

import os
import re

# location phrases -> absolute path templates
LOCATIONS = {
    "desktop": lambda: os.path.join(os.path.expanduser("~"), "Desktop"),
    "workspace": lambda: os.path.expanduser("~/.coal/work"),
    "documents": lambda: os.path.join(os.path.expanduser("~"), "Documents"),
    "downloads": lambda: os.path.join(os.path.expanduser("~"), "Downloads"),
    "cwd": lambda: os.getcwd(),
}

# filename extraction: "called X", "named X", "as X", "X.py" (quoted)
_FILENAME = re.compile(
    r"(?:called|named|as)\s+[\"']?([\w.\- ]+?)(?:[\"']|$|,|\s+(?:that|which|with|to|on|and))",
    re.I)
_FILENAME2 = re.compile(r"[\"']([\w.\-]+\.(?:py|js|ts|txt|json|md|html|css|"
                        r"sh|ps1|bat|sql|c|cpp|h|java|rs|go))[\"']")

_LOC = re.compile(r"\b(desktop|workspace|documents|downloads|cwd)\b", re.I)


class Intent:
    __slots__ = ("tool", "confidence", "args", "reason")

    def __init__(self, tool, confidence, args=None, reason=""):
        self.tool = tool
        self.confidence = confidence  # high | medium | low
        self.args = args or {}
        self.reason = reason

    def __repr__(self):
        return f"<Intent {self.tool} [{self.confidence}] {self.args}>"


def _locate(text):
    m = _LOC.search(text or "")
    if m:
        key = m.group(1).lower()
        fn = LOCATIONS.get(key)
        if fn:
            try:
                return key, fn()
            except Exception:
                pass
    return "workspace", os.path.expanduser("~/.coal/work")


_EXTS = (".py", ".txt", ".js", ".ts", ".json", ".md", ".html", ".css",
         ".sql", ".sh", ".ps1", ".bat", ".go", ".rs", ".c", ".cpp", ".h",
         ".java", ".yml", ".yaml", ".toml", ".xml", ".csv")

# any bare filename-with-extension token anywhere in the text
_BARE_FILE = re.compile(
    r"\b([\w][\w.\-]*\.(?:" + "|".join(e.lstrip(".") for e in _EXTS) +
    r"))\b", re.I)


def _extract_filename(text):
    # 1. explicit bare name with a known extension anywhere in the text
    m = _BARE_FILE.search(text or "")
    if m:
        return m.group(1)
    # 2. quoted "X.ext"
    m = _FILENAME2.search(text or "")
    if m:
        return m.group(1)
    # 3. "called X / named X / as X"
    m = _FILENAME.search(text or "")
    if m:
        name = m.group(1).strip()
        if not any(ch in name for ch in " .-"):
            return None
        # only keep a clean token; if it has an extension, use it
        for ext in _EXTS:
            if name.endswith(ext):
                return name
        return name.split()[0] + ".txt" if name.split() else None
    return None


# ---- rule table: (regex, tool, confidence, arg-builder) ----
_RULES = [
    # CHIP / RTL DESIGN (highest priority for chip-specific phrasing)
    (re.compile(r"\b(build|design|make|create|write|generate|implement)\b"
                r".*\b(chip|rtl|verilog|vhdl|alu|uart|counter|fsm|"
                r"shift\s*register|shiftreg|pwm|fpga|asic|soc|datapath|"
                r"state\s+machine)\b|"
                r"\b(rtl|verilog|hdl)\s+(module|design|block)\b", re.I),
     "chip_build", "high",
     lambda t, loc: {"location": loc}),
    # 3D TEXTURING (unwrap + tile-paint + bake; before generation so
    # "texture this model ... fbx" is not read as a generate request)
    (re.compile(r"\b(texture|uv[- ]?map|uv[- ]?unwrap|unwrap|bake|paint)\b"
                r".*\b(model|mesh|3d|obj|fbx|glb|gltf|stl)\b|"
                r"\b(texture|unwrap|uv[- ]?map|paint)\s+(this|the|my)\b|"
                r"\b(with|using)\s+(a\s+|an\s+)?[\w-]+\s+texture\b",
                re.I),
     "texture_3d", "high",
     lambda t, loc: {"location": loc}),
    # IMAGE -> 3D
    (re.compile(r"\b(image|photo|picture|pic|photo)\b.*\b(to|into|as)\b\s*"
                r"3d\b|\b3d\b.*\b(from|out of)\b.*\b(image|photo|picture)\b|"
                r"\b(image|photo|picture)\s*->?\s*3d\b", re.I),
     "image_to_3d", "high",
     lambda t, loc: {"location": loc}),
    # HIGH-RES / TILED IMAGE (MultiDiffusion: tiled + blended)
    (re.compile(r"\b(high[- ]?(quality|res|resolution)|hd|2k|4k|concept art|"
                r"character (sheet|design|concept)|key art|poster|"
                r"tiled image|detailed image|hi-res)\b", re.I),
     "generate_hd_image", "high",
     lambda t, loc: {"location": loc}),
    # 3D MODEL GENERATION
    (re.compile(r"\b(3d|3-d)\b.*\b(model|mesh|asset|sculpt|object|"
                r"render|print)\b|"
                r"\b(generate|make|create|build|produce|design)\b.*\b"
                r"(3d|mesh|stl|obj|gltf|fbx|low[- ]?poly|lowpoly)\b|"
                r"\b(mesh|low[- ]?poly|lowpoly)\b", re.I),
     "generate_3d", "high",
     lambda t, loc: {"location": loc}),
    # SANDBOX (Linux) — highest priority: anything explicitly about the
    # isolated Linux sandbox must run there, not on the Windows host.
    (re.compile(r"\b(sandbox|on\s+linux|in\s+linux|into\s+linux|ubuntu|"
                r"\bwsl\b|apt-get|apt\s+install|systemctl|"
                r"bash\s+script|shell\s+script)\b", re.I),
     "sandbox_run", "high",
     lambda t, loc: {"location": loc}),
    # BUILD A WHOLE PROJECT (autonomous multi-file build)
    (re.compile(r"\b(build|create|make|scaffold)\s+(me\s+|us\s+)?"
                r"(a\s+|an\s+|the\s+)?(complete|full|whole|entire)\b", re.I),
     "build_project", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(build|scaffold)\s+(me\s+|us\s+)?"
                r"(a\s+|an\s+|the\s+)?project\b", re.I),
     "build_project", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(build|create)\s+(me\s+|us\s+)?(a\s+|an\s+|the\s+)?"
                r"(portfolio|blog|dashboard|game site|website|web ?app|"
                r"landing page|webpage)\b", re.I),
     "build_project", "high",
     lambda t, loc: {"location": loc}),
    # CUSTOM IMAGE with specifications (style/mood/color/ratio present)
    (re.compile(r"\b(make|create|generate|draw|render)\s+(me\s+)?"
                r"(a|an|the|a custom|custom)\s+[\w\s,.-]{4,}?"
                r"(cyberpunk|watercolor|oil painting|pixel art|anime|"
                r"cartoon|photorealistic|3d render|minimalist|vintage|"
                r"dark|dreamy|neon|comic|sketch|fantasy|steampunk|"
                r"gothic|isometric|pastel|16:9|9:16|4:3|portrait|"
                r"landscape|square|red|blue|purple|gold|monochrome|"
                r"moody|dramatic|epic)\b", re.I),
     "custom_image", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(custom|recreate|restyle|redesign)\s+(an?|my|the)\s+"
                r"image\b.*?(with|in|as|to)\b", re.I),
     "custom_image", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(custom|recreate|restyle)\s+image\s+of\b", re.I),
     "custom_image", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(recreate|restyle|redesign|customize)\s+"
                r"(my|the|this|that)?\s*([\w.\-/\\]+\.(?:png|jpg|jpeg|"
                r"webp))\b", re.I),
     "custom_image", "high",
     lambda t, loc: {"location": loc}),
    # "make me an image of X, <style/color/ratio>"
    (re.compile(r"\b(make|generate|create|draw)\s+(me\s+)?(an?|the)\s+"
                r"image\s+of\b.*?\b(cyberpunk|watercolor|dark|neon|"
                r"portrait|landscape|16:9|square|red|blue|gold|moody|"
                r"dramatic|cartoon|anime)\b", re.I),
     "custom_image", "high",
     lambda t, loc: {"location": loc}),
    # IMAGE EDITING (highest — must beat file-write rules)
    (re.compile(r"\b(edit|change|turn|convert|transform|recolor|restyle|"
                r"recolor|redraw|retouch)\s+(this|that|the|my)?\s*"
                r"(image|picture|photo|logo|icon|artwork|screenshot|"
                r"[-\w]+\.(?:png|jpg|jpeg|webp))?\b.*?"
                r"\b(into|to|as|in|like)\b", re.I),
     "edit_image", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(edit|change|turn|convert|restyle|make)\s+(my|the|"
                r"this|that)?\s*([\w.\-/\\]+\.(?:png|jpg|jpeg|webp))\s+"
                r"(into|to|as)\b", re.I),
     "edit_image", "high",
     lambda t, loc: {"location": loc}),
    # IMAGE GENERATION (highest priority — "draw an image" must not be
    # caught by the file-write rules)
    (re.compile(r"\b(make|create|generate|draw|render|produce|paint)\s+"
                r"(me\s+)?(an?|the)\s+(image|picture|photo|photograph|"
                r"artwork|illustration|drawing|painting|portrait|logo|icon|"
                r"banner|wallpaper|background|scene|art)\b", re.I),
     "generate_image", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(generate|make|create|draw)\s+"
                r"(a|an)\s+(robot|character|landscape|portrait|creature|"
                r"fox|dragon|cat|dog|monster|forest|city|space|scene)\b",
                re.I),
     "generate_image", "high",
     lambda t, loc: {"location": loc}),
    # "a character/avatar/sprite/art for my game/app" -> image
    (re.compile(r"\b(generate|make|create|draw|design)\s+(a|an|the)\s+"
                r"(character|avatar|sprite|mascot|emblem|emote)\s+"
                r"(for|of)\b", re.I),
     "generate_image", "high",
     lambda t, loc: {"location": loc}),
    # Bare image-worthy subject prompts (no verb needed):
    # "a majestic eagle over mountains", "portrait of a knight", "landscape"
    (re.compile(r"^(a|an|the)\s+(majestic|beautiful|detailed|epic|"
                r"portrait|landscape|mountain|sunset|sunrise|forest|city|"
                r"dragon|knight|eagle|fox|wolf|robot|character|creature|"
                r"cyberpunk|futuristic|fantasy|scene|village|castle|space|"
                r"ocean|desert|pixel)\b", re.I),
     "generate_image", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(a|an)\s+(majestic|beautiful|detailed|epic|portrait"
                r"|landscape|dragon|knight|eagle|wolf|robot|creature)"
                r"\s+(of|over|in|on|with|flying|standing)\b", re.I),
     "generate_image", "high",
     lambda t, loc: {"location": loc}),
    # IMAGE UNDERSTANDING: "what is in this image / describe / look at"
    (re.compile(r"\b(what('s| is) in|describe|analyze|look at|understand|"
                r"explain)\s+(this|that|the|my)?\s*(image|picture|photo|"
                r"screenshot|diagram)\b", re.I),
     "ask_about_image", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(read|extract|ocr|recognize|read out)\s+(the\s+)?"
                r"(text|words|characters)\s+(in|from|of)\s+(this|that|the)?"
                r"\s*(image|picture|photo|screenshot)\b", re.I),
     "ocr_image", "high",
     lambda t, loc: {"location": loc}),
    # FILE CREATION (highest priority)
    (re.compile(r"\b(make|create|write|generate|build|save|produce)\s+(me\s+)?"
                r"(a|an|the|this|that)?\s*(new\s+)?(file|script|module|program|"
                r"notebook|document|page|class|function|app|website|site|"
                r"tool|bot|agent|guard)\b", re.I),
     "write_file", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(rewrite|recreate|regenerate|overwrite|fix up)\s+"
                r"(the\s+)?(file|script|module|code)\b", re.I),
     "write_file", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(rewrite|recreate|regenerate)\s+([\w.\-]+\.(?:py|js|"
                r"ts|txt|json|md|html|css|sql|sh|ps1|bat|go|rs|c|cpp|h|"
                r"java|yml|yaml|toml|xml))\b", re.I),
     "write_file", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(write|save)\s+(this|it|that)\s+(to|as)\b", re.I),
     "write_file", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(create|make|generate)\s+a\s+file\b", re.I),
     "write_file", "high",
     lambda t, loc: {"location": loc}),
    # "make me a <lang> script/app/website/game" — language in between
    (re.compile(r"\b(make|create|write|build|generate)\s+(me\s+)?"
                r"(a|an|the|this|that)?\s*(?!project\b)(?:[\w+.#]+\s+){0,4}"
                r"(script|program|app|application|website|site|page|"
                r"game|tool|bot|module|file|notebook)\b", re.I),
     "write_file", "high",
     lambda t, loc: {"location": loc}),
    # "an html+css+js app", "a snake game" (no 'script/file' word)
    (re.compile(r"\b(make|create|write|build|generate)\s+(me\s+)?"
                r"(a|an|the)\s+(html|css|js|javascript|python|python3|"
                r"web|snake|game|todo|calculator|dashboard|portfolio|"
                r"landing|blog)\b", re.I),
     "write_file", "high",
     lambda t, loc: {"location": loc}),
    # FILE EDIT
    (re.compile(r"\b(edit|update|modify|change|fix|patch|add|remove|insert|"
                r"delete)\s+(the\s+)?(file|code|script)\b", re.I),
     "edit_file", "medium",
     lambda t, loc: {"location": loc}),
    # INSPECT: "check/look at/show me my <files/project/workspace>"
    (re.compile(r"\b(check|look\s+at|look\s+into|inspect|review|examine)\s+"
                r"(the\s+|my\s+|this\s+|that\s+)?(snake|project|code|files?|"
                r"workspace|folder|directory|html|css|js|script)\b", re.I),
     "glob", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(show|list|tell)\s+(me\s+)?(what\s+)?(files?|things)"
                r"\s+(i\s+)?(have|made|created|in)\b", re.I),
     "glob", "high",
     lambda t, loc: {"location": loc}),
    # READ
    (re.compile(r"\b(read|show|open|display|print|view|cat)\s+(me\s+)?"
                r"(the\s+|my\s+)?([\w.\-]+\.(?:html|py|js|css|txt|json|md))"
                r"\b", re.I),
     "read_file", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(read|show|open|display|print|view|cat)\s+(me\s+)?"
                r"(the\s+)?(file|code|script|contents|source)\b", re.I),
     "read_file", "medium",
     lambda t, loc: {"location": loc}),
    # SEARCH / FIND
    (re.compile(r"\b(search|find|grep|look\s+for|locate)\s+(for\s+)?"
                r"(the\s+)?(pattern|string|symbol|function|code|file|text)\b",
     re.I),
     "grep", "medium",
     lambda t, loc: {"location": loc}),
    # RUN COMMAND
    (re.compile(r"\b(run|execute|launch|start)\s+(this\s+)?(command|script|"
                r"code|program|test|build)\b", re.I),
     "run_command", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(install|pip\s+install|npm\s+install)\s+", re.I),
     "install_package", "medium",
     lambda t, loc: {"location": loc}),
    # GIT
    (re.compile(r"\b(git\s+status|git\s+diff)\b", re.I),
     "git_status", "medium",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(git\s+commit)\b", re.I),
     "git_commit", "medium",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(git\s+push)\b", re.I),
     "git_push", "medium",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(git\s+pull)\b", re.I),
     "git_pull", "medium",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(git\s+log)\b", re.I),
     "git_log", "medium",
     lambda t, loc: {"location": loc}),
    # MEMORY
    (re.compile(r"\b(remember|memorize|store|note)\s+(that\s+|this\s+|my\s+)?",
                re.I),
     "remember", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(recall|search\s+my\s+memory|what\s+did\s+i|"
                r"do\s+you\s+remember|what\s+do\s+i\s+prefer)\b", re.I),
     "search_memory", "high",
     lambda t, loc: {"location": loc}),
    # WEB
    (re.compile(r"\b(fetch|download|get)\s+(the\s+)?(url|page|website|web"
                r"site|link)\b", re.I),
     "web_fetch", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(browse|open\s+in\s+browser|go\s+to)\s+(a\s+)?url\b",
                re.I),
     "browser_navigate", "medium",
     lambda t, loc: {"location": loc}),
    # DATABASE
    (re.compile(r"\b(sql|query|database)\b", re.I),
     "sql_query", "medium",
     lambda t, loc: {"location": loc}),
    # PROJECT AWARENESS
    (re.compile(r"\b(create|start|make|new)\s+(me\s+)?(a\s+)?project\b",
                re.I),
     "project_new", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(open|load)\s+(a\s+|my\s+|the\s+)?project\b", re.I),
     "project_open", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(audit|check|review)\s+(my\s+|the\s+)?project\b", re.I),
     "project_audit", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(what\s+changed|journal|history|log)\s+(in|of|for)\s+"
                r"(the\s+|my\s+)?project\b", re.I),
     "project_journal", "high",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(project\s+status|project\s+map|project\s+overview|"
                r"project\s+structure)\b", re.I),
     "project_status", "medium",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(relate|how\s+does)\s+.*\b(relate|relate\s+to|"
                r"related)\b", re.I),
     "project_related", "medium",
     lambda t, loc: {"location": loc}),
    # SYSTEM
    (re.compile(r"\b(processes|task\s+list|what('s| is)\s+running)\b", re.I),
     "process_list", "medium",
     lambda t, loc: {"location": loc}),
    (re.compile(r"\b(disk|storage|space)\b", re.I),
     "df", "medium",
     lambda t, loc: {"location": loc}),
]


def detect_intent(text):
    """Return an Intent. Never raises; defaults to low confidence chat."""
    t = (text or "").strip()
    if not t:
        return Intent("chat", "low", {}, "empty")
    loc_key, loc_path = _locate(t)
    filename = _extract_filename(t)

    for rx, tool, conf, arg_builder in _RULES:
        if rx.search(t):
            args = arg_builder(t, loc_path)
            if filename and tool in ("write_file", "edit_file"):
                args["path"] = os.path.join(loc_path, filename)
            args.setdefault("location", loc_path)
            return Intent(tool, conf, args, rx.pattern[:40])

    # fallback: explicit file mention -> read
    if filename:
        return Intent("read_file", "medium",
                      {"path": os.path.join(loc_path, filename),
                       "location": loc_path}, "filename only")
    return Intent("chat", "low", {}, "no intent detected")


def needs_force(intent):
    """Should coal.py force tool_choice for this intent?"""
    return intent.confidence == "high"


_WEB = re.compile(
    r"\b(website|web ?app|web ?site|html|css|javascript|storefront|store|"
    r"portfolio|landing page|three\.?js|react|vue|angular|app\.js|"
    r"index\.html|frontend|ui)\b", re.I)
_CHIP = re.compile(
    r"\b(chip|verilog|systemverilog|vhdl|rtl|fpga|asic|netlist|synthes\w*|"
    r"flip.?flop|lfsr|uart|spi|i2c|shift ?register|counter)\b", re.I)
_REMEMBER = re.compile(
    r"\b(remember|note that|keep in mind|don'?t forget|do not forget)\b",
    re.I)
_PROJECT = re.compile(
    r"\b(build|create|make|scaffold)\b[^.\n]{0,40}\b(project|app|"
    r"application|website|site|game|dashboard|portfolio|tool)\b", re.I)
_PATH = re.compile(r"\b[A-Za-z]:[\\/]")


def plausible_intent(tool, text):
    """Reject a forced tool that a single stray keyword happened to trigger.

    The classifier matches keywords anywhere, so 'app.js (a click counter)'
    used to force chip_build and 'storefront ... Nile' forced remember.
    Forcing the wrong tool is worse than letting the model choose.
    """
    t = text or ""
    if tool in ("chip_build", "chip_plan", "chip_review"):
        return bool(_CHIP.search(t)) and not _WEB.search(t)
    if tool in ("remember", "memory_search"):
        return bool(_REMEMBER.search(t))
    if tool == "build_project":
        # an explicit destination path means "write it here", not "make a
        # new project in Coal Projects"
        return bool(_PROJECT.search(t)) and not _PATH.search(t)
    return True


if __name__ == "__main__":
    for q in [
        "make a file called guard.py on my desktop that blocks SQL injection",
        "create a website that shows my portfolio",
        "remember that I like dark mode",
        "what do I prefer on my laptop",
        "run this python script",
        "edit the file config.json",
        "read the file notes.txt",
        "git status",
        "search the web for qwen news",
        "what is 2 + 2",
        "write a guard script to protect a backend",
    ]:
        i = detect_intent(q)
        print(f"{q[:52]:54s} -> {i.tool:16s} [{i.confidence}] {i.args}")