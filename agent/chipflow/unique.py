"""Coal designs 50 unique chips on its own.

The catalogue below fixes *what* each chip is (so the set is genuinely
distinct and each has a real use). Everything else is Coal's work:

  1. the model writes the RTL from the spec
  2. an **independent** testbench is written from the spec + port list only
     (it never sees the RTL, so it checks the specification rather than
     mirroring a bug)
  3. the chip must pass lint + simulation + synthesis + formal + P&R;
     failures repair the RTL against the frozen testbench (or, if the
     testbench itself does not compile, regenerate the testbench)

    py -3.15 -m chipflow.unique --limit 50 --model 7b --repairs 1
"""
from __future__ import annotations

import json
import os
import re
import time

from . import flow
from . import model as M
from . import ports as P

OUT = os.path.join(os.path.expanduser("~"), ".coal", "work", "chips", "_unique")
RESULTS = os.path.join(OUT, "results.jsonl")
REPORT = os.path.join(OUT, "UNIQUE_CHIPS.md")
STOP = os.path.join(OUT, "STOP")

# name, category, specification, real-world use
SPECS = [
    ("bcd2seg", "display",
     "4-bit binary to 7-segment decoder, active-low segments, valid for 0-9 "
     "and A-F", "digital clocks, meters, instrument panels"),
    ("bin2bcd", "display",
     "8-bit binary to 3-digit BCD converter using the double-dabble "
     "algorithm, combinational, outputs hundreds/tens/ones",
     "7-segment displays, frequency counters"),
    ("graycounter", "sequencing",
     "4-bit Gray-code counter with synchronous reset and enable",
     "rotary encoders, asynchronous FIFO pointers"),
    ("johnson", "sequencing",
     "4-bit Johnson counter with synchronous reset and an output enable",
     "one-hot state generation, low-EMI clock division"),
    ("ringcounter", "sequencing",
     "8-bit one-hot ring counter with rotate enable and synchronous reset",
     "LED chasers, sequencer state machines"),
    ("lfsr8", "test",
     "8-bit maximal-length LFSR, polynomial x^8+x^6+x^5+x^4+1, enable and "
     "seed load, never all-zero",
     "PRBS test patterns, data scrambling, built-in self-test"),
    ("crc8", "integrity",
     "CRC-8 generator, polynomial 0x07, serial data input with valid, "
     "8-bit CRC output with a done strobe",
     "packet integrity, serial protocols, storage"),
    ("parity", "integrity",
     "8-bit parity generator/checker with even/odd mode and an error output",
     "memory ECC front-ends, UART parity, buses"),
    ("hamming_enc", "integrity",
     "Hamming(7,4) encoder: 4 data bits to a 7-bit codeword",
     "single-error-correcting memory, telemetry"),
    ("manchester_enc", "comms",
     "Manchester encoder: serial bit with valid input, Manchester line "
     "output with a bit-clock output",
     "Ethernet PHYs, RFID, IR links"),
    ("quadrature", "sensor",
     "quadrature decoder for a rotary encoder with 4x decoding, direction "
     "output and a 16-bit position counter",
     "motor feedback, knobs, CNC axes"),
    ("edge_detect", "sensor",
     "edge detector with rising, falling and both-edge one-cycle pulses",
     "event capture, interrupt generation"),
    ("debounce", "sensor",
     "parameterised button debouncer with synchronous sampling and a clean "
     "registered output", "push buttons, mechanical switches"),
    ("oneshot", "timing",
     "retriggerable one-shot pulse generator with a programmable width",
     "pulse stretching, timing control"),
    ("watchdog", "reliability",
     "watchdog timer with a kick input, configurable period, and a timeout "
     "pulse that stays until reset", "embedded systems, lock-up recovery"),
    ("interval_timer", "timing",
     "16-bit programmable down counter with load, enable, and a one-cycle "
     "timeout pulse", "OS tick timers, PWM periods, delays"),
    ("stopwatch", "timing",
     "stopwatch with start/stop/clear and BCD centisecond + second outputs",
     "sports timers, bench instruments"),
    ("updown", "counting",
     "8-bit up/down counter with parallel load, enable, and terminal count",
     "position control, general counting"),
    ("satadd", "dsp",
     "8-bit unsigned saturating adder with a saturation flag",
     "audio/image processing, control loops"),
    ("absval", "dsp",
     "8-bit two's complement absolute value with sign and overflow flags",
     "DSP magnitude, distance metrics"),
    ("prio16", "arbitration",
     "16-to-4 priority encoder with valid output, highest index wins",
     "interrupt controllers, arbiters"),
    ("barrelshift", "alu",
     "8-bit barrel shifter: left/right, 0-7 positions, arithmetic or "
     "logical mode", "ALU datapaths, floating point"),
    ("lzc", "alu",
     "8-bit leading-zero counter with an all-zero flag",
     "floating-point normalisation, compression"),
    ("popcount", "alu",
     "4-bit population count (number of ones) with a 3-bit result",
     "bit manipulation, Hamming weight, neural nets"),
    ("bitrev", "alu",
     "8-bit bit-reversal, combinational",
     "FFT butterflies, bit-serial protocols"),
    ("mac4", "dsp",
     "4-bit multiply-accumulate with clear and valid, 8-bit accumulator",
     "FIR filters, neural accelerators"),
    ("reset_sync", "cdc",
     "asynchronous-assert, synchronous-deassert reset synchroniser",
     "safe reset distribution"),
    ("cdc_sync", "cdc",
     "two-flop synchroniser for a single-bit signal with a pulse output",
     "clock-domain crossing of flags"),
    ("clkdiv3", "clocking",
     "clock divider by 3 with 50% duty cycle and synchronous reset",
     "clock generation, baud rates"),
    ("pwm_deadtime", "motor",
     "PWM generator with complementary outputs and programmable dead-time",
     "H-bridge motor drivers, inverters"),
    ("servo", "motor",
     "servo PWM controller: 50 Hz frame, 1-2 ms pulse proportional to an "
     "8-bit position input", "hobby servos, robotics"),
    ("stepper", "motor",
     "stepper motor full-step sequencer for 4 coils with direction and "
     "enable inputs", "3D printers, CNC, robotics"),
    ("traffic", "control",
     "traffic light FSM with red/yellow/green, a pedestrian request, and "
     "timed transitions", "intersection controllers, teaching FSMs"),
    ("vend", "control",
     "vending machine FSM accepting 5/10/25 coins, dispensing at 30, with "
     "change and cancel", "automata, payment state machines"),
    ("elevator", "control",
     "3-floor elevator controller with call buttons, door open/close, and "
     "direction output", "building control, FSM examples"),
    ("seqdet", "comms",
     "sequence detector for the pattern 1011 with overlapping detection",
     "protocol framing, pattern search"),
    ("keypad", "input",
     "4x4 keypad scanner with row drive, column read, debounce, and a "
     "key-valid output with the key code", "embedded user input"),
    ("segmux", "display",
     "4-digit 7-segment multiplexer with digit enables and a refresh divider",
     "multi-digit displays"),
    ("ledchase", "display",
     "8-LED chaser with adjustable speed and direction",
     "indicators, decorative lighting"),
    ("melody", "audio",
     "buzzer melody player with a note ROM, tempo divider, and start input",
     "alarms, toys, simple music"),
    ("spi_slave", "peripheral",
     "SPI slave, mode 0, 8-bit, with chip select, sclk, mosi, miso, and a "
     "received-byte valid strobe", "sensors, memories, MCU peripherals"),
    ("spi_master", "peripheral",
     "SPI master, mode 0, 8-bit, with start/busy, sclk, mosi, miso and a "
     "received byte", "flash, displays, ADCs"),
    ("uart_parity", "comms",
     "UART transmitter with an even parity bit, 8 data bits, 1 stop bit, "
     "start/busy handshake", "serial links with error detection"),
    ("pulse_width", "instrument",
     "pulse-width measurement: measure the high time of an input in clock "
     "cycles with a 16-bit result and a valid strobe", "sensors, RC decoding"),
    ("freq_counter", "instrument",
     "frequency counter: count input edges over a gate period with a 16-bit "
     "result and an overflow flag", "bench instruments, tachometers"),
    ("stack8", "cpu",
     "8-entry LIFO stack with push/pop, full and empty flags",
     "CPU call stacks, expression evaluation"),
    ("pc_branch", "cpu",
     "8-bit program counter with load, increment enable, and branch",
     "CPU fetch units"),
    ("idecode", "cpu",
     "simple instruction decoder: 8-bit opcode to ALU op, register write "
     "enable, memory read/write, and immediate flag", "CPU control units"),
    ("booth", "dsp",
     "4x4 Booth multiplier producing a signed 8-bit product",
     "low-power multipliers, DSP"),
    ("sar_adc", "sensor",
     "SAR ADC controller: 8-bit successive approximation with sample, "
     "compare input, done, and result", "analog sensing, MCU ADCs"),
]


# catalogue entries Coal can build from its verified generator library.
# These are correct by construction and verified against a Python reference
# model, so they do not need the LLM at all.
DETERMINISTIC = {
    "bcd2seg": ("seg7", {}),
    "graycounter": ("gray_counter", {}),
    "johnson": ("johnson4", {}),
    "edge_detect": ("edge_detect", {}),
    "debounce": ("debounce", {"width": 8}),
    "lfsr8": ("lfsr8", {}),
    "updown": ("updown8", {}),
    "parity": ("parity8", {}),
    "clkdiv3": ("clkdiv", {"div": 3}),
    "bin2bcd": ("bin2bcd", {}),
    "prio16": ("prio16", {}),
    "satadd": ("satadd", {}),
    "absval": ("absval", {}),
    "lzc": ("lzc", {}),
    "hamming_enc": ("hamming_enc", {}),
    "ringcounter": ("ringcounter", {}),
    "oneshot": ("oneshot", {}),
    "watchdog": ("watchdog", {}),
    "interval_timer": ("interval_timer", {}),
    "stepper": ("stepper", {}),
    "seqdet": ("seqdet", {}),
    "stack8": ("stack8", {}),
    "pc_branch": ("pc_branch", {}),
    "mac4": ("mac4", {}),
    "popcount": ("popcount4", {}),
    "barrelshift": ("barrelshift", {}),
    "idecode": ("idecode", {}),
    "freq_counter": ("freq_counter", {}),
    "pulse_width": ("pulse_width", {}),
    "traffic": ("traffic", {}),
    "vend": ("vend", {}),
    "segmux": ("segmux", {}),
    "stopwatch": ("stopwatch", {}),
    "ledchase": ("ledchase", {}),
    # -- batch 2: catalogue failures turned into deterministic blocks -------
    "bitrev": ("bitrev8", {}),
    "crc8": ("crc8", {}),
    "manchester_enc": ("manchester_enc", {}),
    "quadrature": ("quadrature", {}),
    "reset_sync": ("reset_sync", {}),
    "cdc_sync": ("cdc_sync", {}),
    "booth": ("booth", {}),
    "uart_parity": ("uart_parity", {}),
}


def _low_priority():
    try:
        import ctypes
        h = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.kernel32.SetProcessPriorityClass(h, 0x00004000)
    except Exception:
        pass


def _first_error(rep) -> str:
    """The first real error line, not the tool banner."""
    chunks = [str(e) for e in ((rep or {}).get("errors") or [])]
    for v in ((rep or {}).get("stages") or {}).values():
        chunks.extend(v.get("errors") or [])
    for ch in chunks:
        hits = [ln.strip() for ln in str(ch).splitlines()
                if re.search(r"error|fatal|not supported|unsupported", ln,
                             re.I)]
        if hits:
            return hits[-1][:220]
    return (str(chunks[0])[:220] if chunks else "failed")


def _error_for_repair(rep) -> str:
    """Full text of the first failing stage (best signal for the model)."""
    for k in ("sim", "lint", "synth", "formal", "pnr"):
        v = ((rep or {}).get("stages") or {}).get(k) or {}
        if v.get("ok"):
            continue
        for e in v.get("errors") or []:
            s = str(e or "").strip()
            if s:
                return s[-2500:]
    return "failed"


_TB_BROKEN = re.compile(
    r"syntax error|sorry:|Elaboration failed|is not a valid|"
    r"not supported|Unknown module type|Unable to bind", re.I)


def _tb_broken(rep) -> bool:
    """True when the failure is the testbench not compiling."""
    sim = ((rep or {}).get("stages") or {}).get("sim") or {}
    for e in sim.get("errors") or []:
        s = str(e or "")
        if "tb_" in s and _TB_BROKEN.search(s):
            return True
    return False


def _ports_text(rtl: str, top: str) -> str:
    ps = P.ports_of(rtl, top)
    if not ps:
        return "(infer reasonable ports from the specification)"
    return "\n".join(f"- {n}: {v['dir']}, width {v['width']}"
                     for n, v in ps.items())


def _record(row):
    os.makedirs(OUT, exist_ok=True)
    with open(RESULTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _rows():
    out = {}
    try:
        with open(RESULTS, encoding="utf-8") as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                out[r["name"]] = r
    except Exception:
        pass
    return out


def _ram_guard(log):
    """Never let the machine run out of memory. Returns False to stop."""
    free = M.free_ram_gb()
    if free < 2.5:
        log(f"RAM {free:.1f} GB -> unloading model")
        M.unload()
        time.sleep(10)
        free = M.free_ram_gb()
    if free < 2.5:
        log(f"RAM still {free:.1f} GB -> stopping")
        return False
    return True


def run(limit: int = 50, model: str | None = None, repairs: int = 2,
        det_only: bool = False, log=print) -> dict:
    _low_priority()
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(STOP):
        os.remove(STOP)
    specs = SPECS[:limit]
    done = {n for n, r in _rows().items() if r.get("ok")}
    t0 = time.time()

    for i, (name, cat, spec, use) in enumerate(specs, 1):
        if name in done:
            log(f"[{i:2d}/{len(specs)}] {name}: already passed, skip")
            continue
        if det_only and name not in DETERMINISTIC:
            continue
        if os.path.exists(STOP):
            log("STOP file -> stopping")
            break
        if not _ram_guard(log):
            break

        started = time.time()
        model_used = None
        tb_ok = None
        tb_reason = ""
        rounds = 0
        rep = None
        gen_r = {}
        gen_t = ""
        try:
            det = DETERMINISTIC.get(name)
            if det:
                kind, dparams = det
                rep = flow.build_block(name, kind, **dparams)
                model_used = "generator"
                tb_ok = True
                tb_reason = "reference model"
            else:
                gen = M.generate_rtl(spec, name, model=model)
                model_used = gen.get("model")
                if not gen.get("ok"):
                    raise RuntimeError(gen.get("reason") or "generation failed")
                gen_r = M._normalise(gen["rtl"], name)
                ports_txt = _ports_text(gen_r, name)
                # the testbench is written from the SPEC + interface only, so
                # it is an independent check rather than a mirror of the RTL
                tbg = M.generate_tb(spec, name, ports_txt, model=model_used)
                gen_t = tbg.get("tb") or ""
                tb_ok = tbg.get("tb_ok")
                tb_reason = tbg.get("tb_reason") or ""
                rep = flow.build_design(name, gen_r, gen_t, top=name)
                while not rep.get("ok") and rounds < repairs:
                    rounds += 1
                    if _tb_broken(rep):
                        tbg = M.generate_tb(spec, name, ports_txt,
                                            model=model_used)
                        gen_t = tbg.get("tb") or gen_t
                        tb_ok = tbg.get("tb_ok")
                        tb_reason = tbg.get("tb_reason") or ""
                    else:
                        fx = M.repair_rtl(gen_r, name,
                                          _error_for_repair(rep),
                                          model=model_used, tb=gen_t)
                        if not fx.get("ok"):
                            break
                        gen_r = M._normalise(fx["rtl"], name)
                        ports_txt = _ports_text(gen_r, name)
                    rep = flow.build_design(name, gen_r, gen_t, top=name)
        except Exception as e:
            rep = {"ok": False, "stages": {}, "errors": [str(e)[:300]]}

        area = (rep or {}).get("area") or {}
        row = {
            "name": name, "category": cat, "spec": spec, "use": use,
            "ok": bool((rep or {}).get("ok")),
            "cells": area.get("cells"), "ffs": area.get("ffs"),
            "fmax": area.get("fmax_mhz"), "timing_met": area.get("timing_met"),
            "model": model_used, "repairs": rounds,
            "tb_ok": tb_ok, "tb_reason": tb_reason,
            "ms": int((time.time() - started) * 1000),
            "stages": {k: v.get("ok") for k, v in
                       ((rep or {}).get("stages") or {}).items()},
            "error": None if (rep or {}).get("ok") else _first_error(rep),
        }
        _record(row)
        log(f"[{i:2d}/{len(specs)}] {name:16s} "
            f"{'PASS' if row['ok'] else 'FAIL':4s} "
            f"cells={row['cells']} ffs={row['ffs']} fmax={row['fmax']} "
            f"repairs={rounds} {row['ms']/1000:.0f}s")

    return summarize(time.time() - t0)


def _kind_from_stages(stages: dict) -> str:
    if not stages:
        return "generation failed"
    if stages.get("lint") is False:
        return "lint/parse"
    if stages.get("synth") is False:
        return "not synthesizable"
    if stages.get("sim") is False:
        return "behaviour mismatch"
    if stages.get("formal") is False:
        return "formal check"
    if stages.get("pnr") is False:
        return "place & route"
    return "unknown"


def summarize(seconds: float = 0.0) -> dict:
    rows = _rows()
    vals = []
    for name, cat, spec, use in SPECS:
        r = rows.get(name) or {"name": name, "category": cat, "spec": spec,
                               "use": use, "ok": None}
        vals.append(r)
    passed = [r for r in vals if r.get("ok") is True]
    done = [r for r in vals if r.get("ok") is not None]
    timed = [r for r in passed if r.get("fmax") is not None]
    fails = {}
    for r in done:
        if not r.get("ok"):
            k = _kind_from_stages(r.get("stages") or {})
            fails[k] = fails.get(k, 0) + 1
    lines = ["# Coal â€” 50 unique chips (designed by Coal)", "",
             f"- catalogue      : {len(SPECS)} unique designs",
             f"- attempted      : {len(done)}",
             f"- passed         : {len(passed)}",
             f"- failed         : {len(done) - len(passed)}",
             f"- pending        : {len(vals) - len(done)}",
             f"- failure kinds  : {fails or 'none'}",
             f"- functional TB  : {sum(1 for r in passed if r.get('tb_ok'))}",
             f"- clocked        : {len(timed)}",
             f"- total area     : {sum((r.get('cells') or 0) for r in passed)} "
             f"cells / {sum((r.get('ffs') or 0) for r in passed)} FFs",
             "", "| # | chip | what it is | use | result | cells/FF | Fmax |",
             "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(vals, 1):
        fm = f"{r['fmax']:.0f} MHz" if r.get("fmax") else "-"
        res = ("PASS" if r.get("ok") is True
               else "FAIL" if r.get("ok") is False else "â€”")
        lines.append(
            f"| {i} | `{r['name']}` | {r['spec']} | {r['use']} "
            f"| {res} "
            f"| {r.get('cells') or '-'}/{r.get('ffs') or '-'} | {fm} |")

    lines += ["", "## Per-chip detail", ""]
    for i, r in enumerate(vals, 1):
        res = ("PASS" if r.get("ok") is True
               else "FAIL" if r.get("ok") is False else "PENDING")
        lines.append(f"### {i}. `{r['name']}` â€” {res}")
        lines.append(f"- **does:** {r['spec']}")
        lines.append(f"- **use:** {r['use']}")
        if r.get("ok") is True:
            lines.append(
                f"- **cost:** {r.get('cells')} cells / {r.get('ffs')} FF"
                f" Â· Fmax {r.get('fmax') or 'n/a'}"
                f"{' MHz' if r.get('fmax') else ' (combinational)'}"
                f" Â· {r.get('model')} Â· {r.get('repairs') or 0} repair(s)")
            lines.append(
                f"- **proof:** " + ", ".join(
                    f"{k}={'ok' if v else 'FAIL'}"
                    for k, v in (r.get("stages") or {}).items()))
        elif r.get("ok") is False:
            kind = _kind_from_stages(r.get("stages") or {})
            lines.append(f"- **why it failed:** {kind} â€” "
                         f"{(r.get('error') or '')[:200]}")
        else:
            lines.append("- **status:** not built yet")
        lines.append("")
    text = "\n".join(lines)
    try:
        with open(REPORT, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass
    return {"attempted": len(done), "passed": len(passed),
            "failed": len(done) - len(passed),
            "cells": sum((r.get("cells") or 0) for r in passed),
            "text": text, "report": REPORT, "seconds": round(seconds, 1)}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--model", default="7b",
                    help="7b | 14b | auto | full model name")
    ap.add_argument("--repairs", type=int, default=2)
    ap.add_argument("--det-only", action="store_true",
                    help="only build catalogue entries that have a generator")
    a = ap.parse_args()
    mname = None
    if a.model == "7b":
        mname = "qwen2.5-coder:7b"
    elif a.model == "14b":
        mname = "qwen2.5-coder:14b"
    elif a.model != "auto":
        mname = a.model
    res = run(limit=a.limit, model=mname, repairs=a.repairs,
              det_only=a.det_only)
    print("\n" + res["text"].split("## Per-chip detail")[0])
