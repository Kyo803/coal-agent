import sys, io, os, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from types import SimpleNamespace
from tools.handlers_image import generate_image
import resources

# check resources directly
print("sd-cli exists:", os.path.exists(resources.sd_cli_path()))
d, v, l = resources.model_paths()
print("models:", bool(d), bool(v), bool(l))
print("cfg width:", resources.cfg.get("image", {}).get("width"))

# run the handler with a fresh out path
ctx = SimpleNamespace(workspace="~/.rox/work", project=None,
                      notify_callback=lambda m: print("[img]", m))
res = generate_image({"prompt": "a red apple on a table"}, ctx)
print("RESULT:", res)

# list newest files
imgs = sorted(glob.glob(os.path.expanduser("~/.rox/work/images/*.png")),
              key=os.path.getmtime)
print("newest:", [os.path.basename(i) for i in imgs[-3:]])