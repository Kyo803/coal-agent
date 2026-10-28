from builder import build, missions
from builder.loop import _parse_ports

print("missions:", build.missions())
for n in build.missions():
    s = missions.load(n)
    ok, why = missions.validate(s)
    print("  {} valid={} units={} stack={}".format(
        n, ok, len(s.get("manifest", [])) if ok else 0, s.get("stack")))

print("ports parse:", _parse_ports(
    "input clk, input rst, output reg [15:0] y, inout we"))