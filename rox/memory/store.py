"""SQLite-backed persistent store for ROX N memory.

Tables: sessions, messages, facts, entities, summaries, profile.
Local file, WAL mode, thread-safe (check_same_thread=False + a lock).
"""
import json
import logging
import os
import sqlite3
import threading
import time

log = logging.getLogger("rox.memory.store")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at REAL NOT NULL, ended_at REAL, summary TEXT
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL,
  s_mean REAL DEFAULT 0, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subject TEXT, predicate TEXT, object TEXT, confidence REAL DEFAULT 0.7,
  created_at REAL NOT NULL, source_msg INTEGER
);
CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL, kind TEXT, first_seen REAL, last_seen REAL,
  count INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS summaries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER, level INTEGER DEFAULT 1, text TEXT,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS profile (
  key TEXT PRIMARY KEY, value TEXT, updated_at REAL
);
CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_msg_created ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_fact_subject ON facts(subject);
CREATE INDEX IF NOT EXISTS idx_entity_count ON entities(count);
"""


class Store:
    def __init__(self, path):
        self.path = path
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        log.debug("store opened at %s", path)

    # ---- sessions ----
    def new_session(self):
        with self._lock:
            c = self.conn.execute(
                "INSERT INTO sessions(started_at) VALUES(?)", (time.time(),))
            self.conn.commit()
            return c.lastrowid

    def end_session(self, sid, summary=None):
        with self._lock:
            self.conn.execute(
                "UPDATE sessions SET ended_at=?, summary=? WHERE id=?",
                (time.time(), summary, sid))
            self.conn.commit()

    # ---- messages ----
    def add_message(self, sid, role, text, s_mean=0.0):
        with self._lock:
            c = self.conn.execute(
                "INSERT INTO messages(session_id,role,text,s_mean,created_at)"
                " VALUES(?,?,?,?,?)", (sid, role, text, s_mean, time.time()))
            self.conn.commit()
            return c.lastrowid

    def recent_messages(self, sid=None, limit=20):
        with self._lock:
            if sid is None:
                rows = self.conn.execute(
                    "SELECT id,role,text,s_mean,created_at FROM messages "
                    "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT id,role,text,s_mean,created_at FROM messages "
                    "WHERE session_id=? ORDER BY id DESC LIMIT ?",
                    (sid, limit)).fetchall()
        return [{"id": r[0], "role": r[1], "text": r[2], "s": r[3],
                 "t": r[4]} for r in reversed(rows)]

    def messages_by_ids(self, ids):
        if not ids:
            return []
        q = ",".join("?" * len(ids))
        with self._lock:
            rows = self.conn.execute(
                f"SELECT id,role,text,s_mean,created_at FROM messages "
                f"WHERE id IN ({q})", ids).fetchall()
        return [{"id": r[0], "role": r[1], "text": r[2], "s": r[3],
                 "t": r[4]} for r in rows]

    def count_messages(self):
        with self._lock:
            return self.conn.execute(
                "SELECT COUNT(*) FROM messages").fetchone()[0]

    # ---- facts ----
    def add_fact(self, subject, predicate, obj, confidence=0.7,
                 source_msg=None):
        with self._lock:
            self.conn.execute(
                "INSERT INTO facts(subject,predicate,object,confidence,"
                "created_at,source_msg) VALUES(?,?,?,?,?,?)",
                (subject, predicate, obj, confidence, time.time(),
                 source_msg))
            self.conn.commit()

    def facts_for(self, subject=None, limit=20):
        with self._lock:
            if subject:
                rows = self.conn.execute(
                    "SELECT subject,predicate,object,confidence FROM facts "
                    "WHERE subject LIKE ? ORDER BY confidence DESC LIMIT ?",
                    (f"%{subject}%", limit)).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT subject,predicate,object,confidence FROM facts "
                    "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [{"subject": r[0], "predicate": r[1], "object": r[2],
                 "confidence": r[3]} for r in rows]

    def all_facts(self, limit=500):
        return self.facts_for(None, limit)

    # ---- entities ----
    def upsert_entity(self, name, kind="entity"):
        now = time.time()
        with self._lock:
            self.conn.execute(
                "INSERT INTO entities(name,kind,first_seen,last_seen,count)"
                " VALUES(?,?,?,?,1) ON CONFLICT(name) DO UPDATE SET "
                "last_seen=?, count=count+1", (name, kind, now, now, now))
            self.conn.commit()

    def top_entities(self, limit=20):
        with self._lock:
            rows = self.conn.execute(
                "SELECT name,kind,count FROM entities ORDER BY count DESC "
                "LIMIT ?", (limit,)).fetchall()
        return [{"name": r[0], "kind": r[1], "count": r[2]} for r in rows]

    # ---- summaries ----
    def add_summary(self, sid, level, text):
        with self._lock:
            self.conn.execute(
                "INSERT INTO summaries(session_id,level,text,created_at)"
                " VALUES(?,?,?,?)", (sid, level, text, time.time()))
            self.conn.commit()

    def recent_summaries(self, limit=5):
        with self._lock:
            rows = self.conn.execute(
                "SELECT session_id,level,text FROM summaries "
                "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"session": r[0], "level": r[1], "text": r[2]}
                for r in reversed(rows)]

    # ---- profile ----
    def set_profile(self, key, value):
        with self._lock:
            self.conn.execute(
                "INSERT INTO profile(key,value,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=?, updated_at=?",
                (key, json.dumps(value), time.time(),
                 json.dumps(value), time.time()))
            self.conn.commit()

    def get_profile(self, key, default=None):
        with self._lock:
            r = self.conn.execute("SELECT value FROM profile WHERE key=?",
                                  (key,)).fetchone()
        return json.loads(r[0]) if r else default

    def all_profile(self):
        with self._lock:
            rows = self.conn.execute(
                "SELECT key,value FROM profile").fetchall()
        return {r[0]: json.loads(r[1]) for r in rows}

    def stats(self):
        with self._lock:
            return {
                "messages": self.count_messages(),
                "sessions": self.conn.execute(
                    "SELECT COUNT(*) FROM sessions").fetchone()[0],
                "facts": self.conn.execute(
                    "SELECT COUNT(*) FROM facts").fetchone()[0],
                "entities": self.conn.execute(
                    "SELECT COUNT(*) FROM entities").fetchone()[0],
            }

    def close(self):
        with self._lock:
            self.conn.close()
