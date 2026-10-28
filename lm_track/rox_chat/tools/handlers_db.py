"""Category 7 advanced handlers: migrations, backup/restore, redis/mongo,
vector DB (ROX memory index), object storage (workspace dirs).

Real capabilities use sqlite + the ROX memory vector index. Anything
requiring an external server (redis/mongo) reports honestly.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile


def _db(args, ctx):
    path = args.get("database", args.get("db", ""))
    if not os.path.isabs(path):
        path = os.path.join(ctx.workspace or ".", path)
    return path


def sql_execute(args, ctx):
    """Execute an arbitrary SQL statement on a local sqlite DB (T2)."""
    path = _db(args, ctx)
    sql = args.get("query", args.get("sql", ""))
    if not os.path.exists(path):
        sqlite3.connect(path).close()  # create fresh DB
    try:
        conn = sqlite3.connect(path)
        try:
            cur = conn.execute(sql)
            conn.commit()
        except sqlite3.Warning:
            cur = None
        except Exception:
            # multi-statement DDL/DML
            conn.executescript(sql)
            conn.commit()
            cur = None
        rows = cur.fetchmany(50) if cur and cur.description else []
        cols = [d[0] for d in cur.description] if cur and cur.description \
            else []
        out = (" | ".join(cols) + "\n") if cols else ""
        out += "\n".join(" | ".join(str(c) for c in r) for r in rows)
        conn.close()
        return {"ok": True, "output": out[:6000] or "statement executed"}
    except Exception as e:
        return {"ok": False, "output": f"sql failed: {e}"}


def run_migration(args, ctx):
    path = _db(args, ctx)
    sql = args.get("sql", args.get("query", ""))
    if not os.path.exists(path):
        # create it so migrations can bootstrap
        sqlite3.connect(path).close()
    try:
        conn = sqlite3.connect(path)
        conn.executescript(sql)
        conn.commit()
        conn.close()
        return {"ok": True, "output": "migration applied"}
    except Exception as e:
        return {"ok": False, "output": f"migration failed: {e}"}


def create_migration(args, ctx):
    name = args.get("name", "migration")
    sql = args.get("sql", "")
    mig_dir = os.path.join(ctx.workspace or ".", "migrations")
    os.makedirs(mig_dir, exist_ok=True)
    path = os.path.join(mig_dir, f"{name}.sql")
    with open(path, "w", encoding="utf-8") as f:
        f.write(sql)
    return {"ok": True, "output": f"migration created -> {path}"}


def rollback_migration(args, ctx):
    return {"ok": True, "output": "rollback: no prior migration recorded "
            "(manual: drop the applied changes)"}


def seed_database(args, ctx):
    path = _db(args, ctx)
    table = args.get("table", "")
    rows = args.get("rows") or []
    if not rows:
        return {"ok": False, "output": "no rows provided"}
    try:
        conn = sqlite3.connect(path)
        cols = ",".join(rows[0].keys()) if rows[0] else ""
        marks = ",".join("?" * len(rows[0])) if rows[0] else ""
        for r in rows:
            conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})",
                         list(r.values()))
        conn.commit()
        conn.close()
        return {"ok": True, "output": f"seeded {len(rows)} rows into {table}"}
    except Exception as e:
        return {"ok": False, "output": f"seed failed: {e}"}


def db_backup(args, ctx):
    path = _db(args, ctx)
    if not os.path.exists(path):
        return {"ok": False, "output": f"db not found: {path}"}
    backup = args.get("to") or path + ".bak"
    try:
        conn = sqlite3.connect(path)
        bak = sqlite3.connect(backup)
        with bak:
            conn.backup(bak)
        bak.close()
        conn.close()
        return {"ok": True, "output": f"backed up -> {backup}"}
    except Exception as e:
        return {"ok": False, "output": f"backup failed: {e}"}


def db_restore(args, ctx):
    path = _db(args, ctx)
    src = args.get("from", path + ".bak")
    if not os.path.exists(src):
        return {"ok": False, "output": f"backup not found: {src}"}
    try:
        conn = sqlite3.connect(path)
        src_conn = sqlite3.connect(src)
        with conn:
            src_conn.backup(conn)
        src_conn.close()
        conn.close()
        return {"ok": True, "output": f"restored from {src}"}
    except Exception as e:
        return {"ok": False, "output": f"restore failed: {e}"}


def db_branch(args, ctx):
    path = _db(args, ctx)
    branch = args.get("name", "branch")
    copy = os.path.join(os.path.dirname(path), f"{branch}.db")
    try:
        shutil.copy2(path, copy)
        return {"ok": True, "output": f"branch created -> {copy}"}
    except Exception as e:
        return {"ok": False, "output": f"branch failed: {e}"}


def redis_command(args, ctx):
    return {"ok": False, "output": "redis not running / not configured. "
            "Start redis locally or point tools to a running server."}


def mongo_query(args, ctx):
    return {"ok": False, "output": "mongodb not running / not configured."}


def vector_db_upsert(args, ctx):
    """Store an item in ROX's own vector memory index."""
    from memory import Memory
    mem = Memory("~/.rox")
    text = args.get("text", args.get("value", ""))
    mem.remember(text, kind="vector")
    n = mem.store.stats().get("messages", 0)
    mem.store.close()
    return {"ok": True, "output": f"stored in vector memory (msg #{n}): "
            f"{text[:80]}"}


def vector_db_search(args, ctx):
    from memory import Memory
    mem = Memory("~/.rox")
    q = args.get("query", "")
    hits = mem.search(q, k=int(args.get("limit", 5)))
    mem.store.close()
    if not hits:
        return {"ok": True, "output": "no matches"}
    return {"ok": True, "output": "\n".join(
        f"- ({h['role']}) {h['text'][:200]}" for h in hits)}


def _object_storage_root(ctx):
    root = os.path.join(ctx.workspace or "~/.rox", "object_storage")
    os.makedirs(root, exist_ok=True)
    return root


def object_storage_put(args, ctx):
    root = _object_storage_root(ctx)
    name = args.get("key", args.get("name", "blob"))
    data = args.get("data", args.get("content", ""))
    path = os.path.join(root, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(data)
    return {"ok": True, "output": f"stored object -> {path}"}


def object_storage_get(args, ctx):
    root = _object_storage_root(ctx)
    name = args.get("key", args.get("name", "blob"))
    path = os.path.join(root, name)
    if not os.path.exists(path):
        return {"ok": False, "output": f"object not found: {name}"}
    with open(path, encoding="utf-8") as f:
        return {"ok": True, "output": f.read()[:6000]}


def object_storage_list(args, ctx):
    root = _object_storage_root(ctx)
    try:
        files = sorted(os.listdir(root))
    except FileNotFoundError:
        files = []
    return {"ok": True, "output": "\n".join(files) or "(empty)"}


def object_storage_delete(args, ctx):
    root = _object_storage_root(ctx)
    name = args.get("key", args.get("name", "blob"))
    path = os.path.join(root, name)
    if os.path.exists(path):
        os.remove(path)
        return {"ok": True, "output": f"deleted {name}"}
    return {"ok": False, "output": f"not found: {name}"}