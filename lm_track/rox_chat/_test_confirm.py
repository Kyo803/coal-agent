import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from rox import Rox

r = Rox(session_name="toolconfirm", auto_start=False)
# decline everything -> executor must report "user declined"
r.tctx.ask_callback = lambda p: "n"

from tools.exec import ToolExecutor
from tools.permissions import Permissions
from tools.exec import ExecContext

p = Permissions()
ctx = ExecContext(workspace="~/.rox/work", ask_callback=lambda q: "n")
ex = ToolExecutor(ctx, p)
print("write_file (tier1, declined):", ex.run("write_file", {"path": "x.txt", "content": "hi"}))
print("read_file (tier0, auto):", ex.run("read_file", {"path": "x.txt"}))
print("aws_cli (tier2, blocked):", ex.run("aws_cli", {"command": "ls"}))
r.close()