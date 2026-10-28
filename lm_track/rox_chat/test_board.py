"""Board (detective board) test suite. Run:  python test_board.py

Covers the full offline pipeline: store, resolution, builder, retrieval,
cache, export, queue. No model / no Ollama required.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ok] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


print("== 1. store ==")
from board.store import BoardStore, norm_key
d = tempfile.mkdtemp()
st = BoardStore(os.path.join(d, "board.db"))
a = st.upsert_node("project", "Robot Arm", "industrial arm", salience=2.0)
b = st.upsert_node("tool", "NEMA 23", "stepper motor")
check("upsert node", a is not None and b is not None)
check("norm_key", norm_key("  Robot   Arm! ") == "robot arm")
check("get_node", st.get_node("robot arm")["id"] == a)
check("idempotent upsert", st.upsert_node("project", "robot arm") == a)
st.add_alias(a, "the arm")
check("alias resolves", st.get_node("the arm")["id"] == a)
eid = st.add_edge(a, b, "uses", source_msg=1)
check("add edge", eid is not None)
check("edge dedup increments", st.add_edge(a, b, "uses") == eid
      and st.conn.execute("SELECT weight FROM edges WHERE id=?",
                          (eid,)).fetchone()[0] >= 2.0)
check("neighbors", st.neighbors(a)[0]["name"] == "NEMA 23")
did = st.upsert_dossier(1, title="Kickoff", topics=["robotics"],
                        decisions=["use NEMA 23"], summary="started arm")
check("dossier", st.get_dossier(1)["title"] == "Kickoff")
st.add_event("decision", "use NEMA 23", node_id=a, session_id=1)
check("timeline", len(st.timeline()) == 1)
pid = st.add_provenance("dossier", did, session_id=1, msg_id=1,
                        user_text="build a robot arm",
                        thinking="user picked NEMA 23",
                        output="ok", confidence=0.9)
check("provenance", st.provenance_for("dossier", did)[0]["thinking"]
      == "user picked NEMA 23")
st.add_mention(a, 1, 1)
check("mentions", len(st.mentions_of(a)) == 1)
st.index_text("node", a, "Robot Arm NEMA 23 industrial")
check("fts", st.search_text("NEMA")[0]["card_id"] == a)

print("== 2. resolution ==")
from board.resolve import resolve_node
x = resolve_node(st, "Robot Arm")
check("resolve canonical", x == a)
y = resolve_node(st, "the arm")
check("resolve alias", y == a)
z = resolve_node(st, "Arduino")
check("resolve new", z is not None and z != a)

print("== 3. builder ==")
st2 = BoardStore(os.path.join(d, "b2.db"))
from board.builder import build_card
job = {"session_id": 5, "msg_id": 9,
       "user_text": "building a robot arm with NEMA 23",
       "thinking": "hardware project, picked NEMA 23",
       "output": "great choice"}
data = {"title": "Robot arm", "summary": "started arm", "topics": ["robotics"],
        "entities": [{"name": "robot arm", "kind": "project"},
                     {"name": "NEMA 23", "kind": "tool"}],
        "relations": [{"src": "robot arm", "dst": "NEMA 23",
                       "relation": "uses"}],
        "facts": [], "decisions": ["use NEMA 23"], "tasks": ["pick driver"],
        "questions": [], "confidence": 0.9}
res = build_card(st2, None, None, job, data)
check("builder nodes", res["nodes"] == 2)
check("builder edge", st2.count_edges() == 1)
check("builder dossier", st2.get_dossier(5) is not None)
check("builder provenance full thinking",
      st2.provenance_for("dossier", st2.get_dossier(5)["id"])[0]["thinking"]
      == "hardware project, picked NEMA 23")
check("builder events", len(st2.timeline()) == 2)

print("== 4. retrieval ==")
from board.retrieve import BoardRetriever
r = BoardRetriever(st2, None, None)
card = r.card("what motors does the robot arm use?")
check("card has entity", "robot arm" in card.lower())
check("card has relation", "uses" in card.lower())
check("card has conversation", "robot arm" in card.lower())

print("== 5. cache ==")
from board.cache import HotCache
c = HotCache(st2)
c.node(a)
c.neighbors(a)
check("cache populated", c.stats()["hot_nodes"] >= 1)
c.invalidate()
check("cache invalidated", c.stats()["hot_nodes"] == 0)

print("== 6. export ==")
from board.export import node_card, dossier_card, write_json
nc = node_card(st2, st2.get_node("robot arm")["id"])
check("node card provenance", nc["provenance"] == [])  # node has none here
dc = dossier_card(st2, 5)
check("dossier card has thinking",
      dc["provenance"][0]["thinking"].startswith("hardware"))
out, n = write_json(st2, os.path.join(d, "cards.json"))
check("write_json", os.path.exists(out) and n >= 1)

print("== 7. queue ==")
from board.queue import Queue
q = Queue(d)
q.enqueue({"session_id": 1, "msg_id": 1, "user_text": "hi", "output": "yo"})
q.enqueue({"session_id": 1, "msg_id": 2, "user_text": "bye", "output": "cya"})
check("queue count", q.count() == 2)
pend = q.pending()
q.remove([pend[0]["id"]])
check("queue remove", q.count() == 1)

print("=" * 40)
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
