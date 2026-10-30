from tools.intent import detect_intent, needs_force

PROMPTS = [
    "Create a small website directly in C:\\Users\\gamel\\.coal\\work\\web_test"
    "\\store2 using write_file: index.html (with a link to styles.css and a "
    "script tag for app.js), styles.css (styling), and app.js (a click "
    "counter). Create all three files, then list the directory to confirm.",
    "Create an Amazon-like storefront called 'Nile' directly in the "
    "directory C:\\Users\\gamel\\.coal\\work\\web_test\\store using write_file "
    "(do NOT use build_project). HTML/CSS/JS only.",
    "build a portfolio website",
    "Create a portfolio website for a hardware engineer",
    "build a 4-bit gray to binary converter chip",
]

for p in PROMPTS:
    it = detect_intent(p)
    print(f"tool={it.tool!r} force={needs_force(it)} conf={getattr(it, 'confidence', None)}")
    print("   ", p[:90])
    print("    args:", getattr(it, "args", None))
