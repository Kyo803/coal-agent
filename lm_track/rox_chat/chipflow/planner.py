"""Model-assisted composition planning.

The model is asked to choose a *graph* of blocks we already have -- never RTL.
The graph is then validated deterministically (real ports, matching widths,
exactly one driver per net, all inputs driven) before a single line is
emitted. If the graph is invalid the errors are fed back for a bounded number
of rounds.

Honesty note: a planned composition has **no curated system testbench**, so it
is proven structurally (lint + synth + formal + place&route), not
functionally. Reports mark that explicitly instead of pretending otherwise.
"""
from __future__ import annotations

import inspect
import json
import re

from . import compose, designs, model
from . import ports as P

_MAX_BLOCKS = 8


def catalogue() -> list:
    """Every block we can compose, with its ports."""
    out, seen = [], set()
    for _key, fn in sorted(designs.GENERATORS.items()):
        if fn in seen:
            continue
        seen.add(fn)
        kind = fn.__name__
        try:
            blk = designs.generate_block(kind)
        except Exception:
            continue
        ps = P.ports_of(blk["rtl"], blk["top"])
        out.append({
            "kind": kind,
            "module": blk["top"],
            "ports": {n: f"{v['dir'][0]}:{v['width']}" for n, v in ps.items()},
        })
    return out


def _catalogue_text() -> str:
    lines = []
    for b in catalogue():
        ps = ", ".join(f"{n}({spec})" for n, spec in b["ports"].items())
        lines.append(f"- {b['kind']} [{b['module']}]: {ps}")
    return "\n".join(lines)


_SYSTEM = """You are a chip architect. Design a chip by wiring together ONLY the
blocks listed below. You must NOT write Verilog.

Blocks (port(width); i=input, o=output):
{catalogue}

Answer with JSON only, no prose, no code fences:
{{
  "name": "short_name",
  "blocks": [{{"inst": "rx", "kind": "uart_rx", "params": {{}}}}],
  "nets": [
    {{"name": "serial_in", "driver": null, "sinks": ["rx.rx"], "top": "input"}},
    {{"name": "rx_data", "driver": "rx.data", "sinks": ["fifo.din"], "top": null}},
    {{"name": "serial_out", "driver": "tx.tx", "sinks": [], "top": "output"}}
  ],
  "clock": true,
  "reset": true
}}

Rules:
- use ONLY the block kinds listed above
- every net has at most one driver; "top" is "input", "output" or null
- a driver must be an OUTPUT port; sinks must be INPUT ports
- widths must match the driver port exactly
- every input port of every block must appear in some net's sinks
- "clock": true connects clk to every block that has a clk port
- "reset": true connects rst to every block that has an rst port
- to move data out of a FIFO into a block with start/busy (like uart_tx),
  include the stream_ctrl glue block: fifo.empty->ctl.empty,
  tx.busy->ctl.busy, ctl.start->tx.start, ctl.rd->fifo.rd
- keep it simple: at most {max_blocks} blocks

Example of a VALID answer (a FIFO that feeds bytes back out the UART):
{{
 "name": "echo",
 "blocks": [{{"inst": "rx", "kind": "uart_rx"}},
            {{"inst": "fifo", "kind": "fifo", "params": {{"width": 8, "depth": 8}}}},
            {{"inst": "tx", "kind": "uart_tx"}},
            {{"inst": "ctl", "kind": "stream_ctrl"}}],
 "nets": [{{"name": "sin", "driver": null, "sinks": ["rx.rx"], "top": "input"}},
          {{"name": "rx_data", "driver": "rx.data", "sinks": ["fifo.din"], "top": null}},
          {{"name": "rx_valid", "driver": "rx.valid", "sinks": ["fifo.wr"], "top": null}},
          {{"name": "tx_data", "driver": "fifo.dout", "sinks": ["tx.data"], "top": null}},
          {{"name": "fifo_empty", "driver": "fifo.empty", "sinks": ["ctl.empty"], "top": null}},
          {{"name": "tx_busy", "driver": "tx.busy", "sinks": ["ctl.busy"], "top": null}},
          {{"name": "tx_start", "driver": "ctl.start", "sinks": ["tx.start"], "top": null}},
          {{"name": "fifo_rd", "driver": "ctl.rd", "sinks": ["fifo.rd"], "top": null}},
          {{"name": "sout", "driver": "tx.tx", "sinks": [], "top": "output"}}],
 "clock": true,
 "reset": true
}}"""


def _parse(text: str) -> dict | None:
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(t[i:j + 1])
    except Exception:
        return None


def _module_map() -> dict:
    """module name -> generator kind (models often emit the module name)."""
    global _MODULE_MAP
    if _MODULE_MAP is not None:
        return _MODULE_MAP
    m = {}
    for kind, fn in designs.GENERATORS.items():
        try:
            top = designs.generate_block(kind)["top"]
        except Exception:
            continue
        m.setdefault(top, kind)
    _MODULE_MAP = m
    return m


_MODULE_MAP = None


def _resolve_kind(name: str) -> str | None:
    if name in designs.GENERATORS:
        return name
    return _module_map().get(name)


def to_composition(graph: dict) -> compose.Composition:
    """Build a Composition from a planned graph (raises on bad structure)."""
    name = str(graph.get("name") or "planned_chip")
    name = re.sub(r"[^A-Za-z0-9_]", "_", name)[:40] or "planned_chip"
    c = compose.Composition(name)
    blocks = graph.get("blocks") or []
    if not blocks:
        raise ValueError("graph has no blocks")
    for b in blocks:
        inst = str(b.get("inst") or b.get("kind") or "")
        raw = str(b.get("kind") or "")
        if not inst or not raw:
            raise ValueError(f"block missing inst/kind: {b}")
        kind = _resolve_kind(raw)
        if kind is None:
            raise ValueError(f"unknown block kind {raw!r}")
        fn = designs.GENERATORS[kind]
        # keep only params the generator actually accepts, and coerce numbers
        try:
            sig = inspect.signature(fn).parameters
        except (TypeError, ValueError):
            sig = {}
        clean = {}
        for k, v in (b.get("params") or {}).items():
            if k not in sig:
                continue
            default = sig[k].default
            if isinstance(default, int) and not isinstance(v, bool):
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    raise ValueError(f"{kind}.{k} must be an integer")
            clean[k] = v
        c.add(inst, kind, **clean)
    if graph.get("clock", True):
        c.clk()
    if graph.get("reset", True):
        c.rst()
    for n in graph.get("nets") or []:
        c.net(str(n.get("name") or "net"),
              int(n.get("width") or 0),
              driver=n.get("driver") or None,
              sinks=list(n.get("sinks") or []),
              top_dir=n.get("top") or None)
    return c


def plan(spec: str, rounds: int = 2, model_name: str | None = None) -> tuple:
    """Ask the model for a block graph. Returns (Composition|None, errors)."""
    if not model_name and not model.pick_model():
        return None, ["no model fits in RAM (deterministic only)"]
    system = _SYSTEM.format(catalogue=_catalogue_text(),
                            max_blocks=_MAX_BLOCKS)
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content": spec}]
    errors = ["no attempt made"]
    for _round in range(max(1, rounds)):
        txt = model.chat(msgs, model=model_name, temperature=0.1,
                         num_predict=1200)
        if not txt:
            return None, ["model returned nothing"]
        graph = _parse(txt)
        if not graph:
            errors = ["model did not return valid JSON"]
        else:
            try:
                comp = to_composition(graph)
                blocks = compose.generate_blocks(comp)
                problems = comp.validate(blocks)
            except Exception as e:
                problems = [str(e)]
            if not problems:
                return comp, []
            errors = problems[:12]
        msgs = msgs + [
            {"role": "assistant", "content": txt[:4000]},
            {"role": "user", "content":
                "That is invalid:\n- " + "\n- ".join(map(str, errors))
                + "\nReturn corrected JSON only."},
        ]
    return None, errors
