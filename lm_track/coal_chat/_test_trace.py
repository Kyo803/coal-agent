import sys
sys.path.insert(0, ".")
from tools import specs as S
from tools.permissions import Permissions

p = Permissions()
cats = S.categories_for_trigger("git commit")
priority = ["execution", "filesystem", "git", "web", "search",
            "database", "system", "browser", "orchestration",
            "output", "monitoring"]
ordered = [c for c in priority if c in cats] + \
          [c for c in cats if c not in priority]
names = []
for c in ordered:
    if not p.category_enabled(c):
        continue
    for s in S.by_category(c):
        if p.tier(s["name"], s["tier"]) != 2:
            names.append(s["name"])
for m in S.MEMORY_TOOLS:
    names.append(m)
for m in ("list_tools", "use_category"):
    names.append(m)
core = ["search_memory", "remember", "memory_search", "memory_read",
        "memory_write", "forget", "update_profile",
        "list_tools", "use_category"]
ordered_names = [n for n in names if n in core] + \
                [n for n in names if n not in core]
seen = set()
for i, n in enumerate(ordered_names):
    skip = n in seen
    seen.add(n)
    print(i, repr(n), "skipped" if skip else "emitted",
          "| S.get is None:", S.get(n) is None)