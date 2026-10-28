"""Project Interface Contract (PIC): the authoritative per-module
interface (Verilog ports / exported symbols) so generated files match
each other instead of drifting.

Stored as contract.json in the project ledger (rebuildable, separate
from the source tree). For HDL it records each module's port list; the
builder injects it into every module's write prompt and can check the
written files against it.
"""
import json
import os


class Contract:
    def __init__(self, ledger):
        self.path = os.path.join(ledger, "contract.json")
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                return json.load(open(self.path, encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1)

    def set_ports(self, module, ports, name=None):
        self.data.setdefault("modules", {})[module] = {
            "ports": ports, "name": name or ""}

    def module(self, module):
        return (self.data.get("modules") or {}).get(module)

    def module_name(self, module):
        return (self.module(module) or {}).get("name") or ""

    def all_modules_text(self, max_modules=10):
        """`module NAME (ports)` for every planned module, so a file that
        instantiates others uses the exact names + ports."""
        lines = []
        for m in self.modules()[:max_modules]:
            nm = self.module_name(m) or m
            pt = self.ports_text(m)
            lines.append(f"module {nm} (\n{pt}\n);")
        return "\n\n".join(lines)

    def expected_ports(self, module):
        m = self.module(module)
        return (m or {}).get("ports") or []

    def ports_text(self, module):
        ports = self.expected_ports(module)
        if not ports:
            return ""
        return "\n".join(
            f"{p['dir']} {p.get('width', '1')} {p['name']}" for p in ports)

    def modules(self):
        return list((self.data.get("modules") or {}).keys())

    def set_top(self, module):
        self.data["top"] = module

    def top(self):
        return self.data.get("top")

    def all_ports_text(self, max_modules=8):
        """Every module's port list, for injecting into a testbench prompt
        so it instantiates the top module with only its declared ports."""
        lines = []
        for m in self.modules()[:max_modules]:
            pt = self.ports_text(m)
            if pt:
                lines.append(f"module {m}:\n{pt}")
        return "\n\n".join(lines)


if __name__ == "__main__":
    import tempfile
    d = tempfile.mkdtemp()
    c = Contract(d)
    c.set_ports("alu.v", [{"name": "a", "dir": "input", "width": "[3:0]"},
                          {"name": "y", "dir": "output", "width": "[3:0]"}])
    c.save()
    c2 = Contract(d)
    assert c2.ports_text("alu.v") == "input [3:0] a\noutput [3:0] y"
    print("[contract] OK")