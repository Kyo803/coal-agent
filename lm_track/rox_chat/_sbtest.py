from tools.exec import ExecContext, ToolExecutor
from tools.permissions import Permissions

ctx = ExecContext(workspace="~/.rox/work")
ex = ToolExecutor(ctx, Permissions())


def show(label, res):
    out = (res.get("output") or "").strip().replace("\n", " | ")[:300]
    print(f"[{label}] ok={res.get('ok')} {out}")


show("run", ex.run("sandbox_run", {
    "command": "mkdir -p /home/rox/work && echo hi > /home/rox/work/t.txt "
               "&& cat /home/rox/work/t.txt && echo ROX-OK"}))
show("write", ex.run("sandbox_write", {
    "path": "/home/rox/work/a.py", "content": "print('sum', 2 + 2)\n"}))
show("read", ex.run("sandbox_read", {"path": "/home/rox/work/a.py"}))
show("py", ex.run("sandbox_run", {"command": "python3 /home/rox/work/a.py"}))
show("list", ex.run("sandbox_list", {"path": "/home/rox/work"}))
show("info", ex.run("sandbox_info", {}))
show("toolchain", ex.run("sandbox_toolchain", {"stack": "list"}))
show("upload", ex.run("sandbox_upload", {
    "host_path": "rox_config.py", "sandbox_path": "/home/rox/work/cfg.py"}))
show("dl", ex.run("sandbox_download", {
    "sandbox_path": "/home/rox/work/a.py",
    "host_path": "C:/Users/WERU1/AppData/Local/Temp/opencode/dl_a.py"}))
