import json
import sys

from builder import build

name = sys.argv[1]
rep = build.generate_mission(name)
print(json.dumps({
    "mission": rep.get("mission"),
    "generated": rep.get("generated"),
    "kept_frozen": rep.get("kept_frozen"),
    "failed_to_generate": rep.get("failed_to_generate"),
    "compiled": rep.get("compiled"),
    "tested": rep.get("tested"),
    "accept": rep.get("accept"),
    "rounds": rep.get("rounds"),
    "diagnosis": rep.get("diagnosis"),
    "acceptance": rep.get("acceptance"),
    "hdl_verify": rep.get("hdl_verify"),
}, indent=1, default=str))