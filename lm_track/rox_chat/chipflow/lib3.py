"""Second batch of correct-by-construction blocks: the catalogue failures.

Same contract as lib2: each block ships Verilog RTL, an independent Python
reference model of the *specification*, and a testbench generated from that
model. No LLM is involved, so these are deterministic and repeatable.

These exist to turn real catalogue failures into verified chips:

    reset_sync, cdc_sync, crc8, manchester_enc, booth, uart_parity,
    quadrature

Each one was a documented failure in the 50-design catalogue (RTL syntax
error, behaviour mismatch, or empty reply). Adding the block here removes
that failure permanently -- the generator cannot regress the way a model can.
"""
from __future__ import annotations

import random

from . import refsim
from .lib2 import _build, _rand


# ------------------------------------------------------------- reset_sync
def reset_sync() -> dict:
    """Async-assert, sync-deassert reset synchroniser (2-FF).

    Checked at clock edges: when rst_async is high the output is high, and
    after it falls the output drops two clocks later. The asynchronous edge
    behaviour between clocks is not something a synchronous testbench can
    observe, so the reference model pins the clock-edge behaviour only.
    """
    top = "reset_sync"
    rtl = """`timescale 1ns/1ps
module reset_sync (
    input  wire clk,
    input  wire rst_async,
    output wire rst_sync
);
    reg [1:0] q;
    always @(posedge clk or posedge rst_async) begin
        if (rst_async) q <= 2'b11;
        else           q <= {q[0], 1'b0};
    end
    assign rst_sync = q[1];
endmodule
"""

    class M:
        def reset(self):
            self.q = 0

        def step(self, i):
            if i["rst_async"]:
                self.q = 0b11
            else:
                self.q = (self.q & 0b01) << 1
            return {"rst_sync": (self.q >> 1) & 1}

    stim = [{"rst_async": 1}] * 3
    stim += [{"rst_async": 0}] * 10
    stim += [{"rst_async": 1}, {"rst_async": 0}] * 4
    stim += _rand(40, 21, rst_async=[0, 0, 0, 1])
    return _build(top, rtl, M(), stim, clocked=True)


# --------------------------------------------------------------- cdc_sync
def cdc_sync() -> dict:
    """Two-flop single-bit synchroniser with a one-cycle rising pulse."""
    top = "cdc_sync"
    rtl = """`timescale 1ns/1ps
module cdc_sync (
    input  wire clk,
    input  wire rst,
    input  wire d,
    output wire q,
    output reg  pulse
);
    reg [1:0] sync;
    reg       q_prev;
    always @(posedge clk) begin
        if (rst) begin
            sync   <= 2'b00;
            q_prev <= 1'b0;
        end else begin
            sync   <= {sync[0], d};
            q_prev <= sync[1];
        end
    end
    assign q = sync[1];
    always @* pulse = sync[1] & ~q_prev;
endmodule
"""

    class M:
        def reset(self):
            self.s0 = 0
            self.s1 = 0
            self.qp = 0

        def step(self, i):
            if i.get("rst", 0):
                self.s0 = self.s1 = self.qp = 0
            else:
                old_s0, old_s1 = self.s0, self.s1
                self.s0 = i["d"] & 1
                self.s1 = old_s0
                self.qp = old_s1
            return {"q": self.s1, "pulse": self.s1 & (1 - self.qp)}

    stim = [{"rst": 1, "d": 0}] * 3
    stim += [{"rst": 0, "d": v} for v in
             [0, 0, 1, 0, 0, 1, 1, 0, 1, 1, 1, 0, 0, 0, 1]]
    # rst is excluded from per-vector stimulus by refsim (reset is a startup
    # sequence), so it must not appear mid-stream or model and DUT diverge.
    stim += _rand(60, 33, d=[0, 1, 1, 1, 0])
    return _build(top, rtl, M(), stim, clocked=True)


# ------------------------------------------------------------------- crc8
def crc8() -> dict:
    """CRC-8 (poly 0x07) serial generator with a done strobe after 8 bits."""
    top = "crc8"
    rtl = """`timescale 1ns/1ps
module crc8 (
    input  wire       clk,
    input  wire       rst,
    input  wire       din,
    input  wire       valid,
    output reg  [7:0] crc,
    output reg        done
);
    reg [2:0] cnt;
    wire fb = crc[7] ^ din;
    always @(posedge clk) begin
        if (rst) begin
            crc  <= 8'h00;
            cnt  <= 3'd0;
            done <= 1'b0;
        end else begin
            done <= 1'b0;
            if (valid) begin
                crc <= {crc[6:0], 1'b0} ^ (fb ? 8'h07 : 8'h00);
                if (cnt == 3'd7) begin
                    cnt  <= 3'd0;
                    done <= 1'b1;
                end else begin
                    cnt <= cnt + 3'd1;
                end
            end
        end
    end
endmodule
"""

    class M:
        def reset(self):
            self.crc = 0
            self.cnt = 0
            self.done = 0

        def step(self, i):
            self.done = 0
            if i["valid"]:
                fb = ((self.crc >> 7) & 1) ^ (i["din"] & 1)
                self.crc = ((self.crc << 1) & 0xFF) ^ (0x07 if fb else 0)
                if self.cnt == 7:
                    self.cnt = 0
                    self.done = 1
                else:
                    self.cnt += 1
            return {"crc": self.crc, "done": self.done}

    stim = [{"rst": 1, "din": 0, "valid": 0}] * 2
    # a known byte, bit by bit
    for byte in (0xA5, 0x00, 0xFF, 0x3C):
        for k in range(8):
            stim.append({"rst": 0, "valid": 1, "din": (byte >> (7 - k)) & 1})
        stim.append({"rst": 0, "valid": 0, "din": 0})
    stim += _rand(120, 45, rst=[0, 0, 0, 1], valid=[0, 1, 1, 1],
                  din=[0, 1, 1, 0])
    return _build(top, rtl, M(), stim, clocked=True)


# --------------------------------------------------------- manchester_enc
def manchester_enc() -> dict:
    """Manchester encoder: each input bit becomes two half-bits.

    1 -> high then low, 0 -> low then high (IEEE 802.3 convention). bclk is
    high during the first half of each bit.
    """
    top = "manchester_enc"
    rtl = """`timescale 1ns/1ps
module manchester_enc (
    input  wire clk,
    input  wire rst,
    input  wire din,
    input  wire valid,
    output reg  mout,
    output reg  bclk
);
    reg bit_r;
    reg phase;    // 1 = first half of the bit, 0 = second half
    reg active;
    always @(posedge clk) begin
        if (rst) begin
            bit_r  <= 1'b0;
            phase  <= 1'b1;
            active <= 1'b0;
            mout   <= 1'b0;
            bclk   <= 1'b0;
        end else if (valid) begin
            bit_r  <= din;
            phase  <= 1'b1;
            active <= 1'b1;
            mout   <= din;
            bclk   <= 1'b1;
        end else if (active) begin
            if (phase) begin
                mout  <= ~bit_r;
                bclk  <= 1'b0;
                phase <= 1'b0;
            end else begin
                active <= 1'b0;
            end
        end
    end
endmodule
"""

    class M:
        def reset(self):
            self.bit_r = 0
            self.phase = 1
            self.active = 0
            self.mout = 0
            self.bclk = 0

        def step(self, i):
            if i["valid"]:
                self.bit_r = i["din"] & 1
                self.phase = 1
                self.active = 1
                self.mout = self.bit_r
                self.bclk = 1
            elif self.active:
                if self.phase:
                    self.mout = 1 - self.bit_r
                    self.bclk = 0
                    self.phase = 0
                else:
                    self.active = 0
            return {"mout": self.mout, "bclk": self.bclk}

    stim = [{"rst": 1, "din": 0, "valid": 0}] * 2
    for bit in (1, 0, 1, 1, 0, 0, 1, 0):
        stim.append({"rst": 0, "valid": 1, "din": bit})
        stim.append({"rst": 0, "valid": 0, "din": 0})
        stim.append({"rst": 0, "valid": 0, "din": 0})
    stim += _rand(80, 57, rst=[0, 0, 0, 1], valid=[0, 0, 0, 1],
                  din=[0, 1, 1, 0])
    return _build(top, rtl, M(), stim, clocked=True)


# ------------------------------------------------------------------ booth
def booth() -> dict:
    """4x4 Booth (radix-2) multiplier, signed, 8-bit product.

    The RTL runs the classic Booth recode unrolled in one combinational
    block. The reference model just computes the signed product, so the gate
    only passes if the Booth recoding is actually right for all 16x16 inputs.
    """
    top = "booth"
    rtl = """`timescale 1ns/1ps
module booth (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output reg  [7:0] p
);
    integer i;
    // A and M are 5 bits: the classic n-bit Booth overflow happens when the
    // multiplicand is the most negative value (-8) and A = A - M must produce
    // +8, which does not fit in 4 bits. One extra sign bit fixes that.
    reg [4:0] A, M;
    reg [3:0] Q;
    reg       Qm1;
    always @* begin
        M   = {a[3], a};        // sign-extended multiplicand
        A   = 5'b00000;
        Q   = b;
        Qm1 = 1'b0;
        for (i = 0; i < 4; i = i + 1) begin
            case ({Q[0], Qm1})
                2'b01:  A = A + M;
                2'b10:  A = A - M;
                default: ;
            endcase
            Qm1 = Q[0];
            Q   = {A[0], Q[3:1]};
            A   = {A[4], A[4:1]};
        end
        p = {A[3:0], Q};
    end
endmodule
"""

    class M:
        def reset(self):
            pass

        def step(self, i):
            a = i["a"] & 0xF
            b = i["b"] & 0xF
            sa = a - 16 if a & 8 else a
            sb = b - 16 if b & 8 else b
            return {"p": (sa * sb) & 0xFF}

    stim = [{"a": a, "b": b} for a in range(16) for b in range(16)]
    return _build(top, rtl, M(), stim, clocked=False)


# ------------------------------------------------------------ uart_parity
def uart_parity() -> dict:
    """UART transmitter: start, 8 data (LSB first), even parity, stop."""
    top = "uart_parity"
    rtl = """`timescale 1ns/1ps
module uart_parity (
    input  wire       clk,
    input  wire       rst,
    input  wire       start,
    input  wire [7:0] data,
    output reg        tx,
    output reg        busy
);
    localparam IDLE = 3'd0, DATA = 3'd1, PAR = 3'd2, STOP = 3'd3;
    reg [2:0] st;
    reg [7:0] sh;
    reg [2:0] idx;
    reg       par;
    always @(posedge clk) begin
        if (rst) begin
            st   <= IDLE;
            tx   <= 1'b1;
            busy <= 1'b0;
            sh   <= 8'h00;
            idx  <= 3'd0;
            par  <= 1'b0;
        end else begin
            case (st)
                IDLE: begin
                    tx   <= 1'b1;
                    busy <= 1'b0;
                    if (start) begin
                        sh   <= data;
                        idx  <= 3'd0;
                        par  <= ^data;
                        tx   <= 1'b0;
                        busy <= 1'b1;
                        st   <= DATA;
                    end
                end
                DATA: begin
                    tx <= sh[0];
                    sh <= {1'b0, sh[7:1]};
                    if (idx == 3'd7) st <= PAR;
                    else             idx <= idx + 3'd1;
                end
                PAR: begin
                    tx <= par;
                    st <= STOP;
                end
                STOP: begin
                    tx   <= 1'b1;
                    busy <= 1'b0;
                    st   <= IDLE;
                end
                default: st <= IDLE;
            endcase
        end
    end
endmodule
"""

    class M:
        def reset(self):
            self.st = 0
            self.sh = 0
            self.idx = 0
            self.par = 0
            self.tx = 1
            self.busy = 0

        def step(self, i):
            if self.st == 0:                       # IDLE
                self.tx = 1
                self.busy = 0
                if i["start"]:
                    d = i["data"] & 0xFF
                    self.sh = d
                    self.idx = 0
                    self.par = bin(d).count("1") & 1
                    self.tx = 0
                    self.busy = 1
                    self.st = 1
            elif self.st == 1:                     # DATA
                self.tx = self.sh & 1
                self.sh = (self.sh >> 1) & 0xFF
                if self.idx == 7:
                    self.st = 2
                else:
                    self.idx += 1
            elif self.st == 2:                     # PARITY
                self.tx = self.par
                self.st = 3
            elif self.st == 3:                     # STOP
                self.tx = 1
                self.busy = 0
                self.st = 0
            return {"tx": self.tx, "busy": self.busy}

    stim = [{"rst": 1, "start": 0, "data": 0}] * 2
    for d in (0x00, 0x01, 0x55, 0xAA, 0xFF, 0x3C, 0x81):
        stim.append({"rst": 0, "start": 1, "data": d})
        for _ in range(13):
            stim.append({"rst": 0, "start": 0, "data": d})
    stim += _rand(60, 67, rst=[0, 0, 0, 1], start=[0, 0, 0, 1],
                  data=[0, 1, 85, 170, 255, 12])
    return _build(top, rtl, M(), stim, clocked=True)


# -------------------------------------------------------------- quadrature
def quadrature() -> dict:
    """4x quadrature decoder: direction + 16-bit position counter.

    Counts on every valid single-bit A/B transition. The 00->01->11->10->00
    cycle is one direction, the reverse is the other; illegal two-bit jumps
    are ignored, which is what 4x decoding requires.
    """
    top = "quadrature"
    rtl = """`timescale 1ns/1ps
module quadrature (
    input  wire        clk,
    input  wire        rst,
    input  wire        a,
    input  wire        b,
    output reg         dir,
    output reg  [15:0] pos
);
    reg  [1:0] prev;
    wire [1:0] cur = {a, b};
    reg  signed [1:0] step;
    always @* begin
        case ({prev, cur})
            4'b0001: step =  2'sd1;
            4'b0111: step =  2'sd1;
            4'b1110: step =  2'sd1;
            4'b1000: step =  2'sd1;
            4'b0010: step = -2'sd1;
            4'b1011: step = -2'sd1;
            4'b1101: step = -2'sd1;
            4'b0100: step = -2'sd1;
            default: step =  2'sd0;
        endcase
    end
    always @(posedge clk) begin
        if (rst) begin
            prev <= cur;
            pos  <= 16'd0;
            dir  <= 1'b0;
        end else begin
            prev <= cur;
            // NB: do NOT write `pos <= pos + step` with step signed and pos
            // unsigned -- Verilog makes the whole expression unsigned, so
            // step = -1 (2'b11) zero-extends to +3, not -1. The reference
            // model caught exactly this. Use explicit +/-1 on the counter.
            if (step == 2'sd1) begin
                pos <= pos + 16'd1;
                dir <= 1'b1;
            end else if (step == -2'sd1) begin
                pos <= pos - 16'd1;
                dir <= 1'b0;
            end
        end
    end
endmodule
"""

    _CW = {(0, 1), (1, 3), (3, 2), (2, 0)}
    _CCW = {(0, 2), (2, 3), (3, 1), (1, 0)}

    class M:
        def reset(self):
            self.prev = 0
            self.pos = 0
            self.dir = 0

        def step(self, i):
            cur = ((i["a"] & 1) << 1) | (i["b"] & 1)
            if i.get("rst", 0):
                self.prev = cur
                self.pos = 0
                self.dir = 0
                return {"dir": 0, "pos": 0}
            p = self.prev
            s = 1 if (p, cur) in _CW else -1 if (p, cur) in _CCW else 0
            self.prev = cur
            if s:
                self.pos = (self.pos + s) & 0xFFFF
                self.dir = 1 if s > 0 else 0
            return {"dir": self.dir, "pos": self.pos}

    # walk the full Gray cycle forward, then backward, then jitter
    fwd = [(0, 0), (0, 1), (1, 1), (1, 0)] * 4
    back = [(1, 0), (1, 1), (0, 1), (0, 0)] * 4
    stim = [{"rst": 1, "a": 0, "b": 0}] * 2
    for a, b in fwd + back:
        stim.append({"rst": 0, "a": a, "b": b})
    rnd = random.Random(79)
    pa, pb = 0, 0
    for _ in range(60):
        if rnd.random() < 0.5:
            pa ^= 1
        else:
            pb ^= 1
        stim.append({"a": pa, "b": pb})
    return _build(top, rtl, M(), stim, clocked=True)


# registry -- merged into designs.GENERATORS by designs.py
BLOCKS = {
    "reset_sync": reset_sync,
    "cdc_sync": cdc_sync,
    "crc8": crc8,
    "manchester_enc": manchester_enc,
    "booth": booth,
    "uart_parity": uart_parity,
    "quadrature": quadrature,
}
