from tools.exec import ExecContext, ToolExecutor
from tools.permissions import Permissions

ctx = ExecContext(workspace="~/.coal/work")
ex = ToolExecutor(ctx, Permissions())


def show(label, res):
    out = (res.get("output") or "").strip().replace("\n", " | ")[:300]
    print(f"[{label}] ok={res.get('ok')} {out}")


show("run", ex.run("sandbox_run", {
    "command": "mkdir -p /home/coal/work && echo hi > /home/coal/work/t.txt "
               "&& cat /home/coal/work/t.txt && echo Coal-OK"}))
show("write", ex.run("sandbox_write", {
    "path": "/home/coal/work/a.py", "content": "print('sum', 2 + 2)\n"}))
show("read", ex.run("sandbox_read", {"path": "/home/coal/work/a.py"}))
show("py", ex.run("sandbox_run", {"command": "python3 /home/coal/work/a.py"}))
show("list", ex.run("sandbox_list", {"path": "/home/coal/work"}))
show("info", ex.run("sandbox_info", {}))
show("toolchain", ex.run("sandbox_toolchain", {"stack": "list"}))
show("upload", ex.run("sandbox_upload", {
    "host_path": "coal_config.py", "sandbox_path": "/home/coal/work/cfg.py"}))
show("dl", ex.run("sandbox_download", {
    "sandbox_path": "/home/coal/work/a.py",
    "host_path": "C:/Users/WERU1/AppData/Local/Temp/opencode/dl_a.py"}))
