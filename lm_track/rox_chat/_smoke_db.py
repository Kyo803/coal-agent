import sys, os, tempfile, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from types import SimpleNamespace
tmp = tempfile.mkdtemp()
ctx = SimpleNamespace(workspace=tmp)
from tools import handlers_db as DB
db = os.path.join(tmp, "t.db")
print("create+insert:", DB.sql_execute(
    {"database": db, "query":
     "CREATE TABLE t(id INTEGER, v TEXT); INSERT INTO t VALUES(1,'x');"},
    ctx)["ok"])
print("select:", DB.sql_execute(
    {"database": db, "query": "SELECT * FROM t"}, ctx)["output"])
print("seed:", DB.seed_database(
    {"database": db, "table": "t", "rows": [{"id": 2, "v": "y"}]},
    ctx)["output"])
print("backup:", DB.db_backup({"database": db}, ctx)["ok"])
print("restore:", DB.db_restore({"database": db, "from": db + ".bak"},
                                ctx)["ok"])
import shutil
shutil.rmtree(tmp, ignore_errors=True)
print("DONE")