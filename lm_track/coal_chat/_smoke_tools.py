import sys, io, os, tempfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from types import SimpleNamespace

tmp = tempfile.mkdtemp(prefix="coal_smoke_")
ctx = SimpleNamespace(workspace=tmp, ask_callback=lambda q: "y",
                      notify_callback=lambda m: None)

import importlib
mods = ["handlers_db", "handlers_web2", "handlers_cloud", "handlers_browser"]
for m in mods:
    importlib.import_module("tools." + m)

from tools import handlers_db as DB
from tools import handlers_web2 as W2
from tools import handlers_cloud as CL

# --- db ---
db = os.path.join(tmp, "test.db")
print("sql_execute:", DB.sql_execute({"database": db,
    "query": "CREATE TABLE t(id INTEGER, v TEXT); INSERT INTO t VALUES(1,'x')"}, ctx))
print("sql_query:", DB.sql_execute({"database": db, "query": "SELECT * FROM t"}, ctx))
print("db_backup:", DB.db_backup({"database": db}, ctx))
print("db_restore:", DB.db_restore({"database": db, "from": db + ".bak"}, ctx))
print("object_storage_put:", DB.object_storage_put({"key": "a.txt", "data": "hi"}, ctx))
print("object_storage_get:", DB.object_storage_get({"key": "a.txt"}, ctx))
print("object_storage_list:", DB.object_storage_list({}, ctx))
print("vector_db_upsert:", DB.vector_db_upsert({"text": "smoke test entry"}, ctx))
print("vector_db_search:", DB.vector_db_search({"query": "smoke"}, ctx))

# --- web2 ---
print("search_pypi:", W2.search_pypi({"query": "requests"}, ctx)["output"][:80])
print("search_github:", W2.search_github({"query": "qwen"}, ctx)["output"][:80])
print("graphql (no url):", W2.graphql_query({"url": "", "query": "{}"}, ctx)["output"][:40])
print("redis (honest):", DB.redis_command({"command": "PING"}, ctx)["output"][:40])

# --- cloud ---
print("aws (no cli):", CL.aws_cli({"command": "s3 ls"}, ctx)["output"][:60])
print("metrics_query:", CL.metrics_query({}, ctx)["output"][:40])
print("export_pdf:", CL.export_pdf({"content": "hello", "path": os.path.join(tmp, "x.pdf")}, ctx)["output"][:40])

print("SMOKE DONE")
import shutil; shutil.rmtree(tmp, ignore_errors=True)