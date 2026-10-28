"""The brain's activities — what the autonomous self actually does.

  study     read/ingest/plan a topic (full learning cycle)
  observe   discover + ingest a fresh source on its own (web scanning)
  practice  build a small project in the sandbox (learn by doing)
  reflect   measure the self + board + telemetry
  improve   run a self-improvement cycle
  archive   fold the conversation queue onto the detective board
"""
from __future__ import annotations

import time

from rox_config import cfg


def _gc():
    return cfg.get("governance", {}) or {}


def study(topic: str | None = None, network: bool = True) -> dict:
    from learning import loop
    return loop.cycle(topic=topic, allow_network=network)


def observe(topic: str | None = None, network: bool = True) -> dict:
    """Scan for and ingest one fresh source for a frontier topic."""
    try:
        from learning.curiosity.graph import CuriosityGraph
        from learning.curiosity.mood import Mood
        from learning.curiosity.drive import rank
        from learning import sources as src
        from learning.ingest import ingest_source
        g = CuriosityGraph()
        if not topic:
            ranked = rank(g, Mood(), n=1)
            topic = ranked[0][0] if ranked else None
        if not topic:
            return {"ok": False, "reason": "no topic"}
        kinds = tuple((cfg.get("learning", {}) or {}).get(
            "source_kinds", ["encyclopedia", "paper", "repo"]))
        found = src.discover(topic, kinds) if network else []
        if not found:
            return {"ok": True, "topic": topic, "sources": 0}
        n = ingest_source(topic, found[0])
        g.touch(topic, mastery_delta=0.02,
                source=found[0].get("url"))
        return {"ok": True, "topic": topic, "sources": 1, "chunks": n,
                "url": found[0].get("url")}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def practice(spec: str | None = None, stack: str = "python") -> dict:
    from sandbox import sb
    from builder import build
    if not build.model_available():
        return {"ok": False, "reason": "model server offline"}
    spec = spec or "a small, clean command-line utility"
    name = "practice_" + time.strftime("%Y%m%d-%H%M%S")
    cwd = f"/home/rox/work/{name}"
    sb.mkdir(cwd)
    rep = build.generate_project(name, cwd, spec, stack=stack,
                                 criteria=["contains:import "])
    return {"ok": bool(rep.get("compiled")), "name": name, "cwd": cwd,
            "compiled": rep.get("compiled"), "tested": rep.get("tested")}


def improve() -> dict:
    from selfimprove import improve as _imp
    return _imp.run()


def reflect(measure: bool | None = None) -> dict:
    from governance import telemetry
    out = {}
    try:
        from selfimprove import scoreboard
        if measure is None:
            measure = bool(_gc().get("reflect_measure", False))
        if measure:
            b = scoreboard.measure()
            scoreboard.record(b)
            out["scoreboard"] = {"passed": b.get("passed"),
                                 "failed": b.get("failed")}
        else:
            out["scoreboard"] = scoreboard.last()
    except Exception as e:
        out["scoreboard_error"] = str(e)
    try:
        import os
        from board.store import BoardStore
        st = BoardStore(os.path.join(cfg.memory_root, "board.db"))
        out["board"] = st.stats()
        st.close()
    except Exception:
        pass
    try:
        out["satisfaction"] = telemetry.satisfaction()
        telemetry.record("reflect", satisfaction=out["satisfaction"])
    except Exception:
        pass
    return {"ok": True, **out}


def archive() -> dict:
    try:
        import os
        from board.archivist import Archivist
        from board.queue import Queue
        from board.store import BoardStore
        from memory.embed import Embedder
        from memory.index import VectorIndex
        from server_manager import ServerManager
        root = cfg.memory_root
        if Queue(root).count() == 0:
            return {"ok": True, "processed": 0}
        st = BoardStore(os.path.join(root, "board.db"))
        em = Embedder()
        ix = VectorIndex(os.path.join(root, "vectors"), dim=em.dim)
        arch = Archivist(st, em, ix, server_manager=ServerManager())
        rep = arch.run()
        st.close()
        return {"ok": True, **rep}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def mission_retry(limit: int | None = None) -> dict:
    """Re-attempt unresolved extreme missions (the overnight grind). Only
    missions whose last checkpoint wasn't accepted are re-run, capped."""
    from builder import build, checkpoints as CK, missions as M
    from governance import scheduler as _sc
    gc = _sc.gc()
    limit = limit or int(gc.get("night_retries", 1))
    attempted = []
    for name in M.all_names():
        st = CK.load("mission_" + name)
        if st.get("accept"):
            continue
        try:
            rep = build.generate_mission(name)
            attempted.append({"name": name,
                              "accept": bool(rep.get("accept")),
                              "gate": rep.get("gate_failures"),
                              "generated": len(rep.get("generated", []))})
        except Exception as e:
            attempted.append({"name": name, "error": str(e)[:160]})
        if len(attempted) >= limit:
            break
    return {"ok": True, "attempted": attempted}


def mission_queue(limit: int | None = None) -> dict:
    """Work through the mission queue: build the next pending project(s)."""
    from builder import build
    from builder import mission_queue as Q
    Q.ensure()
    limit = limit or 1
    ran = []
    for _ in range(limit):
        name = Q.next_mission()
        if not name:
            break
        Q.mark(name, "running")
        try:
            rep = build.generate_mission(name)
            ok = bool(rep.get("accept")) and bool(rep.get("behavior_gate",
                                                          True))
            Q.mark(name, "done" if ok else "failed")
            ran.append({"name": name, "accept": bool(rep.get("accept")),
                        "gate": rep.get("gate_failures"),
                        "generated": len(rep.get("generated", []))})
        except Exception as e:
            Q.mark(name, "failed")
            ran.append({"name": name, "error": str(e)[:160]})
    return {"ok": True, "ran": ran, "queue": Q.summary()}


ACTIVITIES = {"study": study, "observe": observe, "practice": practice,
              "reflect": reflect, "improve": improve, "archive": archive,
              "mission_retry": mission_retry, "mission_queue": mission_queue}


def run(name: str, **kw) -> dict:
    fn = ACTIVITIES.get(name)
    if not fn:
        return {"ok": False, "reason": f"unknown activity: {name}"}
    return fn(**kw)
