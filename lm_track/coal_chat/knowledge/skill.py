"""Skills: turn knowledge into reusable procedures Coal can re-apply."""
from __future__ import annotations

import os

from . import paths


def _fname(name: str) -> str:
    base = name.strip().replace(" ", "_")
    return base if base.endswith(".md") else base + ".md"


def add(name: str, content: str) -> str:
    p = os.path.join(paths.skills_root(), _fname(name))
    with open(p, "w", encoding="utf-8") as f:
        f.write(content or "")
    return p


def list_skills() -> list:
    return sorted(os.listdir(paths.skills_root()))


def get(name: str) -> str:
    p = os.path.join(paths.skills_root(), _fname(name))
    if os.path.exists(p):
        return open(p, encoding="utf-8").read()
    return ""


def from_notes(topic: str, llm_ok: bool = False) -> dict:
    """Distil a topic's notes into a reusable 'how to' skill."""
    from learning import notes
    recs = notes.recent(topic, limit=20)
    if not recs:
        return {"ok": False, "reason": "no notes"}
    body = "\n".join(f"- {(r.get('text') or '')[:400]}" for r in recs)
    content = f"# Skill: {topic}\n\nReusable procedure derived from notes.\n\n{body}\n"
    if llm_ok:
        try:
            from learning import llm
            out = llm.chat([
                {"role": "system",
                 "content": "Turn the notes into a concise, step-by-step "
                            "reusable skill (markdown)."},
                {"role": "user", "content": body[:3000]}], timeout=120)
            if out:
                content = f"# Skill: {topic}\n\n{out}\n"
        except Exception:
            pass
    p = add(topic, content)
    return {"ok": True, "skill": os.path.basename(p)}
