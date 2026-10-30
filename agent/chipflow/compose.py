"""Compose verified blocks into one chip.

Every block is generated, verified and (optionally) proven equivalent on its
own. This module wires several of them together *deterministically* -- no
model invents RTL here, it only chooses the graph. The result is emitted as a
normal Verilog top module, then pushed through the same gate (lint, sim,
synth, formal, pnr).

    c = Composition("uart_loopback")
    c.add("rx", "uart_rx", clks_per_bit=16)
    c.add("fifo", "fifo", width=8, depth=8)
    c.add("tx", "uart_tx", clks_per_bit=16)
    c.clk().rst()
    c.connect("rx.data", "fifo.din", name="wdata")
    c.connect("rx.valid", "fifo.wr", name="wvalid")
    c.connect("fifo.dout", "tx.data", name="rdata")
    c.connect("tx.busy", "fifo.rd", name="rden")   # (illustrative)
    c.bus("clk", ["rx.clk", "fifo.clk", "tx.clk"], top_name="clk")

Wiring is checked before a single line is emitted:
  * every endpoint must be a real instance port
  * widths must match exactly (no silent truncation)
  * every input must be driven, every net has exactly one driver
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Instance:
    name: str
    kind: str
    params: dict = field(default_factory=dict)


@dataclass
class Net:
    name: str
    width: int = 1
    drivers: list = field(default_factory=list)   # ["inst.port"]
    sinks: list = field(default_factory=list)
    top_dir: str | None = None                    # input | output | None
    top_name: str | None = None
    auto: str | None = None                       # expand to every instance
                                                  # that has this port name

    @property
    def ident(self) -> str:
        return self.top_name if self.top_dir else f"n_{self.name}"


def _split(endpoint: str) -> tuple[str, str]:
    if "." not in endpoint:
        raise ValueError(f"endpoint must be 'inst.port', got {endpoint!r}")
    inst, port = endpoint.split(".", 1)
    return inst.strip(), port.strip()


def generate_blocks(comp: "Composition") -> dict:
    """Generate every unique block the composition references.

    Returns {kind: {"top", "rtl", "tb", "ports"}}. A kind may only appear
    once per composition (instances of the same kind must share params).
    """
    from . import designs
    from . import ports as _ports

    out: dict = {}
    sigs: dict = {}
    for inst, ci in comp.instances.items():
        sig = tuple(sorted(ci.params.items()))
        if ci.kind in sigs and sigs[ci.kind] != sig:
            raise ValueError(
                f"{comp.name}: two {ci.kind!r} instances with different "
                f"params ({sigs[ci.kind]} vs {sig})")
        sigs[ci.kind] = sig
        if ci.kind in out:
            continue
        blk = designs.generate_block(ci.kind, **ci.params)
        blk["ports"] = _ports.ports_of(blk["rtl"], blk["top"])
        out[ci.kind] = blk
    return out


class Composition:
    def __init__(self, name: str, top: str | None = None):
        self.name = name
        self.top = top or name
        self.instances: dict[str, Instance] = {}
        self.nets: dict[str, Net] = {}
        self._owner: dict[str, str] = {}     # "inst.port" -> net name
        self.tb: str = ""                    # self-checking testbench source
        self.description: str = ""

    # ------------------------------------------------------------ building
    def add(self, inst: str, kind: str, **params) -> "Composition":
        if inst in self.instances:
            raise ValueError(f"duplicate instance {inst!r}")
        self.instances[inst] = Instance(inst, kind, params)
        return self

    def net(self, name: str, width: int = 1, driver: str | None = None,
            sinks=(), top_dir: str | None = None,
            top_name: str | None = None) -> "Composition":
        if name in self.nets:
            raise ValueError(f"duplicate net {name!r}")
        n = Net(name=name, width=int(width), top_dir=top_dir,
                top_name=top_name or (name if top_dir else None))
        if driver:
            n.drivers.append(driver)
        n.sinks.extend(sinks)
        self.nets[name] = n
        return self

    def connect(self, src: str, dst: str, name: str | None = None,
                width: int | None = None) -> "Composition":
        """One driver -> one sink."""
        nm = name or f"{src.replace('.', '_')}__{dst.replace('.', '_')}"
        return self.net(nm, width or 0, driver=src, sinks=[dst])

    def bus(self, src: str | None, dsts, name: str | None = None,
            width: int | None = None, top_dir: str | None = None) -> "Composition":
        """One driver (or top input) -> many sinks."""
        nm = name or (src.split(".")[-1] if src else "bus")
        return self.net(nm, width or 0, driver=src, sinks=list(dsts),
                        top_dir=top_dir)

    def clk(self, top_name: str = "clk") -> "Composition":
        """One clock input fanned out to every instance that has a clk port."""
        self.net("clk", 1, top_dir="input", top_name=top_name)
        self.nets["clk"].auto = "clk"
        return self

    def rst(self, top_name: str = "rst") -> "Composition":
        self.net("rst", 1, top_dir="input", top_name=top_name)
        self.nets["rst"].auto = "rst"
        return self

    # ------------------------------------------------------------ validate
    def _resolve_widths(self, blocks: dict, errors: list) -> None:
        """Fill in missing widths from the driving port."""
        for n in self.nets.values():
            p = self._port_of(blocks, n.drivers[0]) if n.drivers else None
            if p and (not n.width or n.width <= 0):
                n.width = int(p["width"])
            if n.width <= 0:
                n.width = 1

    def _port_of(self, blocks: dict, endpoint: str):
        try:
            inst, port = _split(endpoint)
        except ValueError:
            return None
        ci = self.instances.get(inst)
        if not ci:
            return None
        blk = blocks.get(ci.kind)
        if not blk:
            return None
        return (blk.get("ports") or {}).get(port)

    def _expand_auto(self, blocks: dict) -> None:
        """Resolve deferred fan-outs (clk/rst) against the real block ports."""
        for n in self.nets.values():
            if not n.auto:
                continue
            for inst, ci in self.instances.items():
                ports = (blocks.get(ci.kind) or {}).get("ports") or {}
                ep = f"{inst}.{n.auto}"
                if n.auto in ports and ep not in n.sinks:
                    n.sinks.append(ep)

    def validate(self, blocks: dict) -> list:
        """Return a list of problems (empty = good)."""
        errors = []
        self._expand_auto(blocks)
        self._resolve_widths(blocks, errors)

        for inst, ci in self.instances.items():
            if ci.kind not in blocks:
                errors.append(f"unknown block kind {ci.kind!r} for {inst}")

        # endpoints exist, widths match, no double-connect
        for n in self.nets.values():
            for ep in list(n.drivers) + list(n.sinks):
                port = self._port_of(blocks, ep)
                if port is None:
                    errors.append(f"net {n.name}: no such port {ep}")
                    continue
                if int(port["width"]) != int(n.width):
                    errors.append(
                        f"net {n.name}: width {n.width} != {ep} width "
                        f"{port['width']}")
                prev = self._owner.get(ep)
                if prev and prev != n.name:
                    errors.append(f"{ep} connected to two nets "
                                  f"({prev}, {n.name})")
                self._owner[ep] = n.name

        for n in self.nets.values():
            if n.top_dir == "input":
                if n.drivers:
                    errors.append(f"net {n.name}: top input cannot have a "
                                  f"driver ({n.drivers})")
            elif len(n.drivers) != 1:
                errors.append(f"net {n.name}: expected exactly one driver, "
                              f"got {len(n.drivers)}")
            for d in n.drivers:
                p = self._port_of(blocks, d)
                if p and p["dir"] not in ("output", "inout"):
                    errors.append(f"net {n.name}: driver {d} is an "
                                  f"{p['dir']}, not an output")

        # every input port must be driven by some net
        for inst, ci in self.instances.items():
            for pname, p in (blocks.get(ci.kind, {}).get("ports") or {}).items():
                if p["dir"] != "input":
                    continue
                ep = f"{inst}.{pname}"
                if ep not in self._owner:
                    errors.append(f"{ep} is unconnected")

        tops = [n.top_name for n in self.nets.values() if n.top_dir]
        if len(tops) != len(set(tops)):
            errors.append("duplicate top-level port names")
        return errors

    # --------------------------------------------------------------- emit
    def emit(self, blocks: dict) -> str:
        """Emit the Verilog top module. Call validate() first."""
        tops = [n for n in self.nets.values() if n.top_dir]
        ins = [n for n in tops if n.top_dir == "input"]
        outs = [n for n in tops if n.top_dir == "output"]

        def decl(n: Net) -> str:
            rng = "" if n.width == 1 else f"[{n.width - 1}:0] "
            return rng

        lines = ["`timescale 1ns/1ps",
                 f"// {self.name}: composed from "
                 + ", ".join(f"{i.kind}({i.name})"
                             for i in self.instances.values()),
                 f"module {self.top} ("]
        ports = []
        for n in ins:
            ports.append(f"    input  wire {decl(n):<8s}{n.top_name}")
        for n in outs:
            ports.append(f"    output wire {decl(n):<8s}{n.top_name}")
        lines.append(",\n".join(ports))
        lines.append(");")

        # internal wires (an instance output drives the net directly)
        for n in self.nets.values():
            if not n.top_dir:
                lines.append(f"    wire {decl(n):<8s}{n.ident};")

        # instances
        for inst, ci in self.instances.items():
            blk = blocks[ci.kind]
            ports_of_inst = blk.get("ports") or {}
            conn = []
            for pname, p in ports_of_inst.items():
                nname = self._owner.get(f"{inst}.{pname}")
                if not nname:
                    continue
                conn.append(f".{pname}({self.nets[nname].ident})")
            # Block generators bake their parameters into the module (top name
            # and literal widths), so instances never need parameter overrides.
            body = ",\n".join("        " + c for c in conn)
            lines.append(f"    {blk['top']} {inst} (")
            lines.append(body)
            lines.append("    );")

        lines.append("endmodule")
        lines.append("")
        return "\n".join(lines)

    def emit_files(self, blocks: dict) -> dict:
        """{filename: source} for the composed chip (top + block RTL)."""
        files = {f"{self.top}.v": self.emit(blocks)}
        for ci in self.instances.values():
            blk = blocks[ci.kind]
            files[f"{blk['top']}.v"] = blk["rtl"]
        if self.tb:
            files[f"tb_{self.top}.v"] = self.tb
        return files

    def summary(self) -> str:
        return (f"{self.name}: {len(self.instances)} blocks, "
                f"{len(self.nets)} nets")
