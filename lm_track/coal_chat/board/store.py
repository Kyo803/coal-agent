"""Board store: SQLite schema + CRUD for the detective board.

Tables:
  nodes        entities / concepts / decisions / tasks / topics ...
  aliases      alternate surface forms -> node (entity resolution)
  edges        typed relationships between nodes
  dossiers     per-conversation card (topics/facts/decisions/...)
  events       chronological timeline entries
  provenance   what Coal thought/said for each card (the "why")
  node_mentions where a node appeared
  board_fts    FTS5 index over card text (keyword recall)

All local. WAL mode. No network.
"""
import json
import os
import re
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT,
  name TEXT,
  canonical TEXT UNIQUE,
  summary TEXT,
  salience REAL DEFAULT 0,
  first_seen REAL,
  last_seen REAL,
  embedding_id INTEGER,
  meta TEXT
);
CREATE TABLE IF NOT EXISTS aliases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  node_id INTEGER,
  alias TEXT,
  norm TEXT
);
CREATE INDEX IF NOT EXISTS idx_alias_norm ON aliases(norm);
CREATE INDEX IF NOT EXISTS idx_alias_node ON aliases(node_id);
CREATE TABLE IF NOT EXISTS edges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  src INTEGER,
  dst INTEGER,
  relation TEXT,
  weight REAL DEFAULT 1.0,
  source_msg INTEGER,
  created_at REAL,
  UNIQUE(src, dst, relation)
);
CREATE INDEX IF NOT EXISTS idx_edge_src ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edge_dst ON edges(dst);
CREATE TABLE IF NOT EXISTS dossiers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER UNIQUE,
  title TEXT,
  topics TEXT,
  entities TEXT,
  facts TEXT,
  decisions TEXT,
  tasks TEXT,
  questions TEXT,
  summary TEXT,
  created_at REAL,
  embedding_id INTEGER
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL,
  kind TEXT,
  text TEXT,
  node_id INTEGER,
  session_id INTEGER,
  msg_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_event_ts ON events(ts);
CREATE TABLE IF NOT EXISTS provenance (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  card_type TEXT,
  card_id INTEGER,
  session_id INTEGER,
  msg_id INTEGER,
  user_text TEXT,
  thinking TEXT,
  output TEXT,
  archivist_notes TEXT,
  confidence REAL,
  created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_prov_card ON provenance(card_type, card_id);
CREATE TABLE IF NOT EXISTS node_mentions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  node_id INTEGER,
  msg_id INTEGER,
  session_id INTEGER,
  ts REAL
);
CREATE INDEX IF NOT EXISTS idx_mention_node ON node_mentions(node_id);
CREATE VIRTUAL TABLE IF NOT EXISTS board_fts USING fts5(
  card_type, card_id, text
);
"""


def norm_key(s):
    """Normalize a surface form into a canonical key."""
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\s&+.#-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


class BoardStore:
    def __init__(self, path):
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)),
                        exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        if path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---- nodes ----
    def upsert_node(self, kind, name, summary="", salience=0.0,
                    embedding_id=None, meta=None):
        canon = norm_key(name)
        if not canon:
            return None
        now = time.time()
        row = self.conn.execute("SELECT id, salience FROM nodes WHERE "
                                "canonical=?", (canon,)).fetchone()
        if row:
            nid, sal = row
            self.conn.execute(
                "UPDATE nodes SET last_seen=?, salience=?, summary=COALESCE("
                "NULLIF(?,''),summary), kind=COALESCE(NULLIF(?,''),kind), "
                "embedding_id=COALESCE(?,embedding_id), meta=COALESCE(?,"
                "meta) WHERE id=?",
                (now, max(sal or 0.0, salience), summary, kind,
                 embedding_id, json.dumps(meta) if meta else None, nid))
            self.conn.commit()
            return nid
        c = self.conn.execute(
            "INSERT INTO nodes(kind,name,canonical,summary,salience,"
            "first_seen,last_seen,embedding_id,meta) VALUES(?,?,?,?,?,?,?,?,?)",
            (kind, name, canon, summary, salience, now, now, embedding_id,
             json.dumps(meta) if meta else None))
        self.conn.commit()
        return c.lastrowid

    def get_node(self, canonical):
        canon = norm_key(canonical)
        r = self.conn.execute(
            "SELECT id,kind,name,canonical,summary,salience,first_seen,"
            "last_seen,embedding_id FROM nodes WHERE canonical=?",
            (canon,)).fetchone()
        if r:
            return self._node(r)
        # fall back to alias resolution
        aid = self.find_alias(canonical)
        return self.get_node_by_id(aid) if aid else None

    def get_node_by_id(self, nid):
        r = self.conn.execute(
            "SELECT id,kind,name,canonical,summary,salience,first_seen,"
            "last_seen,embedding_id FROM nodes WHERE id=?", (nid,)).fetchone()
        return self._node(r) if r else None

    def top_nodes(self, limit=30):
        rows = self.conn.execute(
            "SELECT id,kind,name,canonical,summary,salience,first_seen,"
            "last_seen,embedding_id FROM nodes ORDER BY salience DESC, "
            "last_seen DESC LIMIT ?", (limit,)).fetchall()
        return [self._node(r) for r in rows]

    def count_nodes(self):
        return self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]

    @staticmethod
    def _node(r):
        return {"id": r[0], "kind": r[1], "name": r[2], "canonical": r[3],
                "summary": r[4], "salience": r[5], "first_seen": r[6],
                "last_seen": r[7], "embedding_id": r[8]}

    # ---- aliases ----
    def add_alias(self, node_id, alias):
        n = norm_key(alias)
        if not n:
            return
        ex = self.conn.execute("SELECT id FROM aliases WHERE node_id=? AND "
                               "norm=?", (node_id, n)).fetchone()
        if not ex:
            self.conn.execute("INSERT INTO aliases(node_id,alias,norm) "
                              "VALUES(?,?,?)", (node_id, alias, n))
            self.conn.commit()

    def find_alias(self, alias):
        n = norm_key(alias)
        r = self.conn.execute("SELECT node_id FROM aliases WHERE norm=? "
                              "LIMIT 1", (n,)).fetchone()
        return r[0] if r else None

    # ---- edges ----
    def add_edge(self, src, dst, relation, weight=1.0, source_msg=None):
        if src is None or dst is None or src == dst:
            return None
        ex = self.conn.execute("SELECT id,weight FROM edges WHERE src=? AND "
                               "dst=? AND relation=?",
                               (src, dst, relation)).fetchone()
        if ex:
            self.conn.execute("UPDATE edges SET weight=weight+?, "
                              "source_msg=COALESCE(?,source_msg) WHERE id=?",
                              (weight, source_msg, ex[0]))
            self.conn.commit()
            return ex[0]
        c = self.conn.execute(
            "INSERT INTO edges(src,dst,relation,weight,source_msg,"
            "created_at) VALUES(?,?,?,?,?,?)",
            (src, dst, relation, weight, source_msg, time.time()))
        self.conn.commit()
        return c.lastrowid

    def neighbors(self, node_id, limit=50):
        rows = self.conn.execute(
            "SELECT e.dst, e.relation, e.weight, n.name, n.kind FROM edges e "
            "JOIN nodes n ON n.id=e.dst WHERE e.src=? ORDER BY e.weight DESC "
            "LIMIT ?", (node_id, limit)).fetchall()
        out = self.conn.execute(
            "SELECT e.src, e.relation, e.weight, n.name, n.kind FROM edges e "
            "JOIN nodes n ON n.id=e.src WHERE e.dst=? ORDER BY e.weight DESC "
            "LIMIT ?", (node_id, limit)).fetchall()
        res = [{"node_id": r[0], "relation": r[1], "weight": r[2],
                "name": r[3], "kind": r[4], "dir": "out"} for r in rows]
        res += [{"node_id": r[0], "relation": r[1], "weight": r[2],
                 "name": r[3], "kind": r[4], "dir": "in"} for r in out]
        return res

    def all_edges(self, limit=5000):
        rows = self.conn.execute(
            "SELECT src,dst,relation,weight FROM edges ORDER BY weight DESC "
            "LIMIT ?", (limit,)).fetchall()
        return [{"src": r[0], "dst": r[1], "relation": r[2], "weight": r[3]}
                for r in rows]

    def count_edges(self):
        return self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    # ---- dossiers ----
    def upsert_dossier(self, session_id, title="", topics=None, entities=None,
                       facts=None, decisions=None, tasks=None, questions=None,
                       summary="", embedding_id=None):
        def j(x):
            return json.dumps(x) if x is not None else None
        ex = self.conn.execute("SELECT id FROM dossiers WHERE session_id=?",
                               (session_id,)).fetchone()
        if ex:
            self.conn.execute(
                "UPDATE dossiers SET title=COALESCE(NULLIF(?,''),title),"
                "topics=?,entities=?,facts=?,decisions=?,tasks=?,questions=?,"
                "summary=COALESCE(NULLIF(?,''),summary),"
                "embedding_id=COALESCE(?,embedding_id) WHERE id=?",
                (title, j(topics), j(entities), j(facts), j(decisions),
                 j(tasks), j(questions), summary, embedding_id, ex[0]))
            self.conn.commit()
            return ex[0]
        c = self.conn.execute(
            "INSERT INTO dossiers(session_id,title,topics,entities,facts,"
            "decisions,tasks,questions,summary,created_at,embedding_id) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (session_id, title, j(topics), j(entities), j(facts), j(decisions),
             j(tasks), j(questions), summary, time.time(), embedding_id))
        self.conn.commit()
        return c.lastrowid

    def get_dossier(self, session_id):
        r = self.conn.execute(
            "SELECT id,session_id,title,topics,entities,facts,decisions,"
            "tasks,questions,summary FROM dossiers WHERE session_id=?",
            (session_id,)).fetchone()
        if not r:
            return None
        return {"id": r[0], "session_id": r[1], "title": r[2],
                "topics": json.loads(r[3] or "[]"),
                "entities": json.loads(r[4] or "[]"),
                "facts": json.loads(r[5] or "[]"),
                "decisions": json.loads(r[6] or "[]"),
                "tasks": json.loads(r[7] or "[]"),
                "questions": json.loads(r[8] or "[]"),
                "summary": r[9]}

    def recent_dossiers(self, limit=10):
        rows = self.conn.execute(
            "SELECT session_id FROM dossiers ORDER BY created_at DESC LIMIT ?",
            (limit,)).fetchall()
        return [self.get_dossier(r[0]) for r in rows]

    # ---- events (timeline) ----
    def add_event(self, kind, text, ts=None, node_id=None, session_id=None,
                  msg_id=None):
        c = self.conn.execute(
            "INSERT INTO events(ts,kind,text,node_id,session_id,msg_id) "
            "VALUES(?,?,?,?,?,?)",
            (ts or time.time(), kind, text, node_id, session_id, msg_id))
        self.conn.commit()
        return c.lastrowid

    def timeline(self, limit=50, node_id=None):
        if node_id:
            rows = self.conn.execute(
                "SELECT ts,kind,text,node_id FROM events WHERE node_id=? "
                "ORDER BY ts DESC LIMIT ?", (node_id, limit)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT ts,kind,text,node_id FROM events ORDER BY ts DESC "
                "LIMIT ?", (limit,)).fetchall()
        return [{"ts": r[0], "kind": r[1], "text": r[2], "node_id": r[3]}
                for r in rows]

    # ---- provenance ----
    def add_provenance(self, card_type, card_id, session_id=None, msg_id=None,
                       user_text="", thinking="", output="",
                       archivist_notes="", confidence=0.0):
        c = self.conn.execute(
            "INSERT INTO provenance(card_type,card_id,session_id,msg_id,"
            "user_text,thinking,output,archivist_notes,confidence,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (card_type, card_id, session_id, msg_id, user_text, thinking,
             output, archivist_notes, confidence, time.time()))
        self.conn.commit()
        return c.lastrowid

    def provenance_for(self, card_type, card_id, limit=5):
        rows = self.conn.execute(
            "SELECT user_text,thinking,output,archivist_notes,confidence,"
            "msg_id FROM provenance WHERE card_type=? AND card_id=? "
            "ORDER BY id DESC LIMIT ?", (card_type, card_id, limit)).fetchall()
        return [{"user_text": r[0], "thinking": r[1], "output": r[2],
                 "archivist_notes": r[3], "confidence": r[4], "msg_id": r[5]}
                for r in rows]

    # ---- mentions ----
    def add_mention(self, node_id, msg_id, session_id, ts=None):
        self.conn.execute(
            "INSERT INTO node_mentions(node_id,msg_id,session_id,ts) "
            "VALUES(?,?,?,?)", (node_id, msg_id, session_id, ts or time.time()))
        self.conn.commit()

    def mentions_of(self, node_id, limit=20):
        rows = self.conn.execute(
            "SELECT msg_id,session_id,ts FROM node_mentions WHERE node_id=? "
            "ORDER BY ts DESC LIMIT ?", (node_id, limit)).fetchall()
        return [{"msg_id": r[0], "session_id": r[1], "ts": r[2]}
                for r in rows]

    # ---- FTS ----
    def index_text(self, card_type, card_id, text):
        if not text:
            return
        self.conn.execute(
            "INSERT INTO board_fts(card_type,card_id,text) VALUES(?,?,?)",
            (card_type, str(card_id), text))
        self.conn.commit()

    def search_text(self, query, limit=10):
        try:
            rows = self.conn.execute(
                "SELECT card_type,card_id FROM board_fts WHERE board_fts "
                "MATCH ? ORDER BY rank LIMIT ?",
                (self._fts_query(query), limit)).fetchall()
            return [{"card_type": r[0], "card_id": int(r[1])} for r in rows]
        except Exception:
            return []

    @staticmethod
    def _fts_query(q):
        toks = re.findall(r"[a-zA-Z0-9]+", q or "")
        return " OR ".join(toks) if toks else '""'

    def stats(self):
        return {
            "nodes": self.count_nodes(),
            "edges": self.count_edges(),
            "dossiers": self.conn.execute(
                "SELECT COUNT(*) FROM dossiers").fetchone()[0],
            "events": self.conn.execute(
                "SELECT COUNT(*) FROM events").fetchone()[0],
            "provenance": self.conn.execute(
                "SELECT COUNT(*) FROM provenance").fetchone()[0],
        }

    def close(self):
        self.conn.close()


if __name__ == "__main__":
    import tempfile
    d = tempfile.mkdtemp()
    st = BoardStore(os.path.join(d, "board.db"))
    a = st.upsert_node("project", "Robot Arm", "industrial arm project",
                       salience=2.0)
    b = st.upsert_node("tool", "NEMA 23", "stepper motor")
    st.add_edge(a, b, "uses", source_msg=1)
    st.add_alias(a, "the arm")
    st.add_event("decision", "chose NEMA 23 motors", node_id=a, session_id=1)
    st.upsert_dossier(1, title="Robot arm kickoff", topics=["robotics"],
                      decisions=["use NEMA 23"], summary="started the arm")
    st.add_provenance("node", a, session_id=1, msg_id=1,
                      user_text="building a robot arm",
                      thinking="user needs motors", output="great project",
                      archivist_notes="project start", confidence=0.9)
    st.index_text("node", a, "Robot Arm NEMA 23 industrial")
    print("[board.store] stats:", st.stats())
    print("[board.store] node:", st.get_node("the arm"))
    print("[board.store] neighbors:", st.neighbors(a))
    print("[board.store] fts:", st.search_text("NEMA"))
    print("[board.store] prov:", st.provenance_for("node", a))
    assert st.get_node("the arm")["id"] == a
    assert st.search_text("NEMA")
    print("[board.store] OK")
