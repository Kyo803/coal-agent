"""Correct-by-construction blocks with reference-model testbenches.

Each block here ships three things:

  * Verilog RTL (the design)
  * a Python reference model of the *specification*
  * a testbench generated from that model: same stimulus, every output
    checked every cycle

That makes the verification independent -- the RTL is not checked against
itself. If the two disagree the chip fails the gate.

Adding a block is therefore mechanical and safe: write the RTL, write the
model, describe the stimulus. No model (LLM) is involved.
"""
from __future__ import annotations

import random

from . import ports as P
from . import refsim


def _build(top: str, rtl: str, model, stimuli, clocked: bool) -> dict:
    ps = P.ports_of(rtl, top)
    model.reset()
    vectors = []
    for inp in stimuli:
        vectors.append((dict(inp), model.step(inp)))
    tb, checks = refsim.build_tb(top, ps, vectors, clocked=clocked)
    return {"top": top, "rtl": rtl, "tb": tb,
            "vectors": len(vectors), "checks": checks}


def _rand(n: int, _seed: int, **choices) -> list:
    rnd = random.Random(_seed)
    out = []
    for _ in range(n):
        out.append({k: rnd.choice(v) for k, v in choices.items()})
    return out


# ------------------------------------------------------------------ parity8
def parity8() -> dict:
    top = "parity8"
    rtl = """`timescale 1ns/1ps
module parity8 (
    input  wire [7:0] data,
    input  wire       odd,      // 0 = even parity, 1 = odd parity
    output wire       err
);
    assign err = (^data) ^ odd;
endmodule
"""

    class M:
        def reset(self):
            pass

        def step(self, i):
            p = bin(i["data"] & 0xFF).count("1") & 1
            return {"err": p ^ (i["odd"] & 1)}

    stim = [{"data": d, "odd": o} for d in range(256) for o in (0, 1)]
    return _build(top, rtl, M(), stim, clocked=False)


# ---------------------------------------------------------------- popcount4
def popcount4() -> dict:
    top = "popcount4"
    rtl = """`timescale 1ns/1ps
module popcount4 (
    input  wire [3:0] a,
    output wire [2:0] cnt
);
    assign cnt = a[0] + a[1] + a[2] + a[3];
endmodule
"""

    class M:
        def reset(self):
            pass

        def step(self, i):
            return {"cnt": bin(i["a"] & 0xF).count("1")}

    stim = [{"a": a} for a in range(16)]
    return _build(top, rtl, M(), stim, clocked=False)


# ------------------------------------------------------------------ bitrev8
def bitrev8() -> dict:
    top = "bitrev8"
    rtl = """`timescale 1ns/1ps
module bitrev8 (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    input  wire [7:0] a,
    output reg  [7:0] y
);
    always @(posedge clk) begin
        if (rst)     y <= 8'd0;
        else if (en) y <= {a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]};
    end
endmodule
"""

    class M:
        def reset(self):
            self.y = 0

        def step(self, i):
            if i.get("en"):
                a = i["a"] & 0xFF
                self.y = int(f"{a:08b}"[::-1], 2)
            return {"y": self.y}

    stim = ([{"en": 1, "a": a} for a in range(256)]
            + _rand(120, 16, en=[0, 1, 1], a=[0, 1, 2, 85, 170, 255]))
    return _build(top, rtl, M(), stim, clocked=True)


# ------------------------------------------------------------- gray_counter
def gray_counter() -> dict:
    top = "gray_counter"
    rtl = """`timescale 1ns/1ps
module gray_counter (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    output wire [3:0] gray,
    output wire [3:0] bin
);
    reg [3:0] b;
    wire [3:0] b_next = b + 4'd1;
    always @(posedge clk) begin
        if (rst)     b <= 4'd0;
        else if (en) b <= b_next;
    end
    assign bin  = b;
    assign gray = b ^ (b >> 1);
endmodule
"""

    class M:
        def reset(self):
            self.b = 0

        def step(self, i):
            if i.get("en"):
                self.b = (self.b + 1) & 0xF
            return {"gray": self.b ^ (self.b >> 1), "bin": self.b}

    stim = ([{"en": 1} for _ in range(20)]
            + _rand(160, 11, en=[0, 0, 1, 1, 1]))
    return _build(top, rtl, M(), stim, clocked=True)


# ---------------------------------------------------------------- johnson4
def johnson4() -> dict:
    top = "johnson4"
    rtl = """`timescale 1ns/1ps
module johnson4 (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    output reg  [3:0] q
);
    always @(posedge clk) begin
        if (rst)     q <= 4'b0000;
        else if (en) q <= {q[2:0], ~q[3]};
    end
endmodule
"""

    class M:
        def reset(self):
            self.q = 0

        def step(self, i):
            if i.get("en"):
                self.q = ((self.q << 1) | (1 - ((self.q >> 3) & 1))) & 0xF
            return {"q": self.q}

    stim = ([{"en": 1} for _ in range(12)]
            + _rand(120, 12, en=[0, 1, 1]))
    return _build(top, rtl, M(), stim, clocked=True)


# -------------------------------------------------------------- edge_detect
def edge_detect() -> dict:
    top = "edge_detect"
    rtl = """`timescale 1ns/1ps
module edge_detect (
    input  wire clk,
    input  wire rst,
    input  wire din,
    output reg  rising,
    output reg  falling,
    output reg  both
);
    reg prev;
    always @(posedge clk) begin
        if (rst) begin
            prev <= 1'b0; rising <= 1'b0; falling <= 1'b0; both <= 1'b0;
        end else begin
            rising  <=  din & ~prev;
            falling <= ~din &  prev;
            both    <= ( din & ~prev) | (~din & prev);
            prev    <= din;
        end
    end
endmodule
"""

    class M:
        def reset(self):
            self.prev = 0

        def step(self, i):
            x = i["din"] & 1
            r = 1 if (x and not self.prev) else 0
            f = 1 if ((not x) and self.prev) else 0
            self.prev = x
            return {"rising": r, "falling": f, "both": r | f}

    stim = ([{"din": 0}] + [{"din": 1}, {"din": 0}, {"din": 1}, {"din": 1}]
            * 10 + _rand(120, 13, din=[0, 1, 1, 0]))
    return _build(top, rtl, M(), stim, clocked=True)


# ---------------------------------------------------------------- updown8
def updown8() -> dict:
    top = "updown8"
    rtl = """`timescale 1ns/1ps
module updown8 (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    input  wire       up,
    input  wire       load,
    input  wire [7:0] din,
    output reg  [7:0] q
);
    always @(posedge clk) begin
        if (rst)       q <= 8'd0;
        else if (load) q <= din;
        else if (en)   q <= up ? q + 8'd1 : q - 8'd1;
    end
endmodule
"""

    class M:
        def reset(self):
            self.q = 0

        def step(self, i):
            if i.get("load"):
                self.q = i["din"] & 0xFF
            elif i.get("en"):
                self.q = (self.q + (1 if i.get("up") else -1)) & 0xFF
            return {"q": self.q}

    stim = ([{"en": 1, "up": 1, "load": 0, "din": 0} for _ in range(10)]
            + [{"en": 0, "up": 0, "load": 1, "din": 200},
               {"en": 1, "up": 0, "load": 0, "din": 0}]
            + _rand(160, 14, en=[0, 1, 1], up=[0, 1],
                    load=[0, 0, 0, 1], din=[0, 1, 2, 127, 128, 255]))
    return _build(top, rtl, M(), stim, clocked=True)


# ------------------------------------------------------------------- lfsr8
def lfsr8() -> dict:
    top = "lfsr8"
    rtl = """`timescale 1ns/1ps
module lfsr8 (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    input  wire       load,
    input  wire [7:0] seed,
    output reg  [7:0] q
);
    wire fb = q[7] ^ q[5] ^ q[4] ^ q[3];
    always @(posedge clk) begin
        if (rst)       q <= 8'h01;
        else if (load) q <= (seed == 8'h00) ? 8'h01 : seed;
        else if (en)   q <= {q[6:0], fb};
    end
endmodule
"""

    class M:
        def reset(self):
            self.q = 0x01

        def step(self, i):
            if i.get("load"):
                s = i["seed"] & 0xFF
                self.q = 0x01 if s == 0 else s
            elif i.get("en"):
                fb = (((self.q >> 7) ^ (self.q >> 5)
                       ^ (self.q >> 4) ^ (self.q >> 3)) & 1)
                self.q = ((self.q << 1) | fb) & 0xFF
            return {"q": self.q}

    stim = ([{"en": 1, "load": 0, "seed": 0} for _ in range(30)]
            + [{"en": 0, "load": 1, "seed": 0xA5},
               {"en": 1, "load": 0, "seed": 0}]
            + _rand(160, 15, en=[0, 1, 1], load=[0, 0, 0, 1],
                    seed=[0, 1, 2, 0x55, 0xFF]))
    return _build(top, rtl, M(), stim, clocked=True)


# ----------------------------------------------------------------- bin2bcd
def bin2bcd() -> dict:
    top = "bin2bcd"
    rtl = """`timescale 1ns/1ps
module bin2bcd (
    input  wire [7:0] bin,
    output reg  [3:0] hundreds,
    output reg  [3:0] tens,
    output reg  [3:0] ones
);
    integer i;
    reg [19:0] sh;
    always @(*) begin
        sh = {12'b0, bin};
        for (i = 0; i < 8; i = i + 1) begin
            if (sh[11:8]  >= 5) sh[11:8]  = sh[11:8]  + 3;
            if (sh[15:12] >= 5) sh[15:12] = sh[15:12] + 3;
            if (sh[19:16] >= 5) sh[19:16] = sh[19:16] + 3;
            sh = sh << 1;
        end
        ones     = sh[11:8];
        tens     = sh[15:12];
        hundreds = sh[19:16];
    end
endmodule
"""

    class M:
        def reset(self):
            pass

        def step(self, i):
            v = i["bin"] & 0xFF
            return {"hundreds": v // 100, "tens": (v // 10) % 10,
                    "ones": v % 10}

    stim = [{"bin": v} for v in range(256)]
    return _build(top, rtl, M(), stim, clocked=False)


# ------------------------------------------------------------------ prio16
def prio16() -> dict:
    top = "prio16"
    rtl = """`timescale 1ns/1ps
module prio16 (
    input  wire [15:0] in,
    output reg  [3:0]  idx,
    output reg         valid
);
    integer i;
    always @(*) begin
        idx = 4'd0;
        valid = 1'b0;
        for (i = 15; i >= 0; i = i - 1) begin
            if (!valid && in[i]) begin
                idx = i[3:0];
                valid = 1'b1;
            end
        end
    end
endmodule
"""

    class M:
        def reset(self):
            pass

        def step(self, i):
            v = i["in"] & 0xFFFF
            if v == 0:
                return {"idx": 0, "valid": 0}
            return {"idx": v.bit_length() - 1, "valid": 1}

    stim = [{"in": 1 << b} for b in range(16)]
    stim += [{"in": 0}, {"in": 0xFFFF}, {"in": 0x8001}, {"in": 0x00F0}]
    stim += [{"in": v} for v in range(0, 65536, 257)]
    return _build(top, rtl, M(), stim, clocked=False)


# ------------------------------------------------------------------ satadd
def satadd() -> dict:
    top = "satadd"
    rtl = """`timescale 1ns/1ps
module satadd (
    input  wire [7:0] a,
    input  wire [7:0] b,
    output reg  [7:0] y,
    output reg        sat
);
    wire [8:0] s = {1'b0, a} + {1'b0, b};
    always @(*) begin
        if (s > 9'd255) begin
            y = 8'd255;
            sat = 1'b1;
        end else begin
            y = s[7:0];
            sat = 1'b0;
        end
    end
endmodule
"""

    class M:
        def reset(self):
            pass

        def step(self, i):
            s = (i["a"] & 0xFF) + (i["b"] & 0xFF)
            return {"y": min(s, 255), "sat": 1 if s > 255 else 0}

    stim = [{"a": a, "b": b} for a in (0, 1, 127, 128, 200, 255)
            for b in (0, 1, 55, 56, 127, 128, 255)]
    stim += _rand(200, 21, a=[0, 1, 2, 100, 128, 200, 254, 255],
                  b=[0, 1, 2, 100, 128, 200, 254, 255])
    return _build(top, rtl, M(), stim, clocked=False)


# ------------------------------------------------------------------ absval
def absval() -> dict:
    top = "absval"
    rtl = """`timescale 1ns/1ps
module absval (
    input  wire [7:0] a,
    output reg  [7:0] y,
    output wire       neg,
    output wire       ov
);
    assign neg = a[7];
    assign ov  = (a == 8'h80);
    always @(*) begin
        y = a[7] ? (~a + 8'd1) : a;
    end
endmodule
"""

    class M:
        def reset(self):
            pass

        def step(self, i):
            a = i["a"] & 0xFF
            v = a - 256 if a & 0x80 else a
            return {"y": abs(v) & 0xFF, "neg": 1 if a & 0x80 else 0,
                    "ov": 1 if a == 0x80 else 0}

    stim = [{"a": a} for a in range(256)]
    return _build(top, rtl, M(), stim, clocked=False)


# --------------------------------------------------------------------- lzc
def lzc() -> dict:
    top = "lzc"
    rtl = """`timescale 1ns/1ps
module lzc (
    input  wire [7:0] a,
    output reg  [3:0] cnt,
    output wire       allzero
);
    assign allzero = (a == 8'h00);
    integer i;
    reg found;
    always @(*) begin
        cnt = 4'd8;
        found = 1'b0;
        for (i = 7; i >= 0; i = i - 1) begin
            if (!found && a[i]) begin
                cnt = 4'd7 - i[3:0];
                found = 1'b1;
            end
        end
    end
endmodule
"""

    class M:
        def reset(self):
            pass

        def step(self, i):
            a = i["a"] & 0xFF
            if a == 0:
                return {"cnt": 8, "allzero": 1}
            return {"cnt": 8 - a.bit_length(), "allzero": 0}

    stim = [{"a": a} for a in range(256)]
    return _build(top, rtl, M(), stim, clocked=False)


# ------------------------------------------------------------- hamming_enc
def hamming_enc() -> dict:
    top = "hamming_enc"
    rtl = """`timescale 1ns/1ps
module hamming_enc (
    input  wire [3:0] d,
    output wire [6:0] code      // bit i = position i+1
);
    assign code[2] = d[0];
    assign code[4] = d[1];
    assign code[5] = d[2];
    assign code[6] = d[3];
    assign code[0] = code[2] ^ code[4] ^ code[6];
    assign code[1] = code[2] ^ code[5] ^ code[6];
    assign code[3] = code[4] ^ code[5] ^ code[6];
endmodule
"""

    class M:
        def reset(self):
            pass

        def step(self, i):
            d = i["d"] & 0xF
            c = [0] * 7
            c[2] = (d >> 0) & 1
            c[4] = (d >> 1) & 1
            c[5] = (d >> 2) & 1
            c[6] = (d >> 3) & 1
            c[0] = c[2] ^ c[4] ^ c[6]
            c[1] = c[2] ^ c[5] ^ c[6]
            c[3] = c[4] ^ c[5] ^ c[6]
            v = 0
            for b in range(7):
                if c[b]:
                    v |= 1 << b
            return {"code": v}

    stim = [{"d": d} for d in range(16)]
    return _build(top, rtl, M(), stim, clocked=False)


# ------------------------------------------------------------- ringcounter
def ringcounter() -> dict:
    top = "ringcounter"
    rtl = """`timescale 1ns/1ps
module ringcounter (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    output reg  [7:0] q
);
    always @(posedge clk) begin
        if (rst)     q <= 8'b0000_0001;
        else if (en) q <= {q[6:0], q[7]};
    end
endmodule
"""

    class M:
        def reset(self):
            self.q = 1

        def step(self, i):
            if i.get("en"):
                self.q = ((self.q << 1) | (self.q >> 7)) & 0xFF
            return {"q": self.q}

    stim = [{"en": 1} for _ in range(12)] + _rand(60, 31, en=[0, 1, 1])
    return _build(top, rtl, M(), stim, clocked=True)


# ------------------------------------------------------------------ oneshot
def oneshot() -> dict:
    top = "oneshot"
    W = 8
    rtl = """`timescale 1ns/1ps
module oneshot (
    input  wire clk,
    input  wire rst,
    input  wire trig,
    output wire pulse
);
    reg [3:0] cnt;
    always @(posedge clk) begin
        if (rst)                 cnt <= 4'd0;
        else if (trig)           cnt <= 4'd8;
        else if (cnt != 4'd0)    cnt <= cnt - 4'd1;
    end
    assign pulse = (cnt != 4'd0);
endmodule
"""

    class M:
        def reset(self):
            self.cnt = 0

        def step(self, i):
            if i.get("trig"):
                self.cnt = W
            elif self.cnt != 0:
                self.cnt -= 1
            return {"pulse": 1 if self.cnt != 0 else 0}

    stim = ([{"trig": 1}] + [{"trig": 0} for _ in range(6)]
            + [{"trig": 1}, {"trig": 1}] + [{"trig": 0} for _ in range(12)]
            + _rand(60, 32, trig=[0, 0, 0, 1]))
    return _build(top, rtl, M(), stim, clocked=True)


# ---------------------------------------------------------------- watchdog
def watchdog() -> dict:
    top = "watchdog"
    P = 16
    rtl = """`timescale 1ns/1ps
module watchdog (
    input  wire clk,
    input  wire rst,
    input  wire kick,
    output reg  timeout
);
    reg [4:0] cnt;
    always @(posedge clk) begin
        if (rst) begin
            cnt <= 5'd0; timeout <= 1'b0;
        end else if (kick) begin
            cnt <= 5'd0; timeout <= 1'b0;
        end else if (cnt < 5'd15) begin
            cnt <= cnt + 5'd1;
        end else begin
            timeout <= 1'b1;
        end
    end
endmodule
"""

    class M:
        def reset(self):
            self.cnt = 0
            self.t = 0

        def step(self, i):
            if i.get("kick"):
                self.cnt = 0
                self.t = 0
            elif self.cnt < P - 1:
                self.cnt += 1
            else:
                self.t = 1
            return {"timeout": self.t}

    stim = ([{"kick": 1}] + [{"kick": 0} for _ in range(10)]
            + [{"kick": 1}] + [{"kick": 0} for _ in range(25)]
            + _rand(60, 33, kick=[0, 0, 0, 1]))
    return _build(top, rtl, M(), stim, clocked=True)


# ---------------------------------------------------------- interval_timer
def interval_timer() -> dict:
    top = "interval_timer"
    rtl = """`timescale 1ns/1ps
module interval_timer (
    input  wire        clk,
    input  wire        rst,
    input  wire        load,
    input  wire        en,
    input  wire [15:0] din,
    output reg  [15:0] cnt,
    output reg         timeout
);
    always @(posedge clk) begin
        if (rst) begin
            cnt <= 16'd0; timeout <= 1'b0;
        end else if (load) begin
            cnt <= din; timeout <= 1'b0;
        end else if (en && cnt == 16'd1) begin
            cnt <= 16'd0; timeout <= 1'b1;
        end else if (en && cnt > 16'd1) begin
            cnt <= cnt - 16'd1; timeout <= 1'b0;
        end else begin
            timeout <= 1'b0;
        end
    end
endmodule
"""

    class M:
        def reset(self):
            self.c = 0
            self.t = 0

        def step(self, i):
            if i.get("load"):
                self.c = i["din"] & 0xFFFF
                self.t = 0
            elif i.get("en") and self.c == 1:
                self.c = 0
                self.t = 1
            elif i.get("en") and self.c > 1:
                self.c -= 1
                self.t = 0
            else:
                self.t = 0
            return {"cnt": self.c, "timeout": self.t}

    stim = ([{"load": 1, "en": 0, "din": 5}, {"load": 0, "en": 1, "din": 0}]
            + [{"load": 0, "en": 1, "din": 0} for _ in range(8)]
            + [{"load": 1, "en": 0, "din": 3}, {"load": 0, "en": 0, "din": 0}]
            + _rand(80, 34, load=[0, 0, 0, 1], en=[0, 1, 1],
                    din=[0, 1, 2, 7, 100]))
    return _build(top, rtl, M(), stim, clocked=True)


# ----------------------------------------------------------------- stepper
def stepper() -> dict:
    top = "stepper"
    rtl = """`timescale 1ns/1ps
module stepper (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    input  wire       dir,
    output reg  [3:0] coils
);
    wire [3:0] nxt = dir ? {coils[2:0], coils[3]}
                         : {coils[0], coils[3:1]};
    always @(posedge clk) begin
        if (rst)     coils <= 4'b0001;
        else if (en) coils <= nxt;
    end
endmodule
"""

    class M:
        def reset(self):
            self.coils = 1

        def step(self, i):
            if i.get("en"):
                if i.get("dir"):
                    self.coils = ((self.coils << 1) | (self.coils >> 3)) & 0xF
                else:
                    self.coils = ((self.coils >> 1) | (self.coils << 3)) & 0xF
            return {"coils": self.coils}

    stim = ([{"en": 1, "dir": 1} for _ in range(8)]
            + [{"en": 1, "dir": 0} for _ in range(8)]
            + _rand(60, 35, en=[0, 1, 1], dir=[0, 1]))
    return _build(top, rtl, M(), stim, clocked=True)


# ------------------------------------------------------------------ seqdet
def seqdet() -> dict:
    top = "seqdet"
    rtl = """`timescale 1ns/1ps
module seqdet (
    input  wire clk,
    input  wire rst,
    input  wire din,
    output reg  found
);
    reg [2:0] hist;
    always @(posedge clk) begin
        if (rst) begin
            hist <= 3'b000; found <= 1'b0;
        end else begin
            found <= ({hist, din} == 4'b1011);
            hist  <= {hist[1:0], din};
        end
    end
endmodule
"""

    class M:
        def reset(self):
            self.h = 0
            self.f = 0

        def step(self, i):
            d = i["din"] & 1
            self.f = 1 if (((self.h << 1) | d) & 0xF) == 0b1011 else 0
            self.h = ((self.h << 1) | d) & 0x7
            return {"found": self.f}

    bits = [1, 0, 1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1, 0, 0, 1, 0, 1, 1]
    stim = [{"din": b} for b in bits] + _rand(80, 36, din=[0, 1, 1, 0])
    return _build(top, rtl, M(), stim, clocked=True)


# ------------------------------------------------------------------ stack8
def stack8() -> dict:
    top = "stack8"
    rtl = """`timescale 1ns/1ps
module stack8 (
    input  wire       clk,
    input  wire       rst,
    input  wire       push,
    input  wire       pop,
    input  wire [7:0] din,
    output wire [7:0] dout,
    output wire       full,
    output wire       empty
);
    reg [7:0] mem [0:7];
    reg [3:0] sp;
    integer i;
    assign empty = (sp == 4'd0);
    assign full  = (sp == 4'd8);
    assign dout  = empty ? 8'h00 : mem[sp - 4'd1];
    always @(posedge clk) begin
        if (rst) begin
            sp <= 4'd0;
            for (i = 0; i < 8; i = i + 1) mem[i] <= 8'h00;
        end else if (push && !full) begin
            mem[sp] <= din;
            sp <= sp + 4'd1;
        end else if (pop && !empty) begin
            sp <= sp - 4'd1;
        end
    end
endmodule
"""

    class M:
        def reset(self):
            self.st = []
            self.dout = 0

        def step(self, i):
            full = len(self.st) == 8
            empty = len(self.st) == 0
            if i.get("push") and not full:
                self.st.append(i["din"] & 0xFF)
            elif i.get("pop") and not empty:
                self.st.pop()
            self.dout = self.st[-1] if self.st else 0
            return {"dout": self.dout,
                    "full": 1 if len(self.st) == 8 else 0,
                    "empty": 1 if not self.st else 0}

    stim = ([{"push": 1, "pop": 0, "din": v} for v in (0x11, 0x22, 0x33)]
            + [{"push": 1, "pop": 0, "din": 0x44}]
            + [{"push": 0, "pop": 1, "din": 0}] * 2
            + [{"push": 1, "pop": 0, "din": 0x55}]
            + _rand(80, 37, push=[0, 1, 1], pop=[0, 0, 1],
                    din=[0, 1, 0x7F, 0x80, 0xFF]))
    return _build(top, rtl, M(), stim, clocked=True)


# ---------------------------------------------------------------- pc_branch
def pc_branch() -> dict:
    top = "pc_branch"
    rtl = """`timescale 1ns/1ps
module pc_branch (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    input  wire       load,
    input  wire [7:0] din,
    output reg  [7:0] pc
);
    always @(posedge clk) begin
        if (rst)       pc <= 8'd0;
        else if (load) pc <= din;
        else if (en)   pc <= pc + 8'd1;
    end
endmodule
"""

    class M:
        def reset(self):
            self.pc = 0

        def step(self, i):
            if i.get("load"):
                self.pc = i["din"] & 0xFF
            elif i.get("en"):
                self.pc = (self.pc + 1) & 0xFF
            return {"pc": self.pc}

    stim = ([{"en": 1, "load": 0, "din": 0} for _ in range(10)]
            + [{"en": 0, "load": 1, "din": 0xF0}]
            + [{"en": 1, "load": 0, "din": 0} for _ in range(4)]
            + _rand(60, 38, en=[0, 1, 1], load=[0, 0, 0, 1],
                    din=[0, 1, 42, 0xFF]))
    return _build(top, rtl, M(), stim, clocked=True)


# -------------------------------------------------------------------- mac4
def mac4() -> dict:
    top = "mac4"
    rtl = """`timescale 1ns/1ps
module mac4 (
    input  wire       clk,
    input  wire       rst,
    input  wire       clear,
    input  wire       valid,
    input  wire [3:0] a,
    input  wire [3:0] b,
    output reg  [7:0] acc
);
    always @(posedge clk) begin
        if (rst || clear) acc <= 8'd0;
        else if (valid)   acc <= acc + (a * b);
    end
endmodule
"""

    class M:
        def reset(self):
            self.acc = 0

        def step(self, i):
            if i.get("clear"):
                self.acc = 0
            elif i.get("valid"):
                self.acc = (self.acc + (i["a"] & 0xF) * (i["b"] & 0xF)) & 0xFF
            return {"acc": self.acc}

    stim = ([{"clear": 0, "valid": 1, "a": 3, "b": 4} for _ in range(4)]
            + [{"clear": 1, "valid": 0, "a": 0, "b": 0}]
            + _rand(80, 39, clear=[0, 0, 0, 1], valid=[0, 1, 1],
                    a=[0, 1, 7, 15], b=[0, 1, 5, 15]))
    return _build(top, rtl, M(), stim, clocked=True)


# ------------------------------------------------------------- barrelshift
def barrelshift() -> dict:
    top = "barrelshift"
    rtl = """`timescale 1ns/1ps
module barrelshift (
    input  wire [7:0] a,
    input  wire [2:0] sh,
    input  wire       dir,      // 0 = left, 1 = right
    input  wire       arith,    // right-shift mode: 1 = arithmetic
    output wire [7:0] y
);
    wire [7:0] l = a << sh;
    wire [15:0] sx = {{8{a[7]}}, a};          // sign-extend to 16 bits
    wire [7:0] r = arith ? (sx >> sh) : (a >> sh);
    assign y = dir ? r : l;
endmodule
"""

    class M:
        def reset(self):
            pass

        def step(self, i):
            a = i["a"] & 0xFF
            s = i["sh"] & 7
            if not i.get("dir"):
                return {"y": (a << s) & 0xFF}
            if i.get("arith"):
                v = a - 256 if a & 0x80 else a
                return {"y": (v >> s) & 0xFF}
            return {"y": a >> s}

    stim = [{"a": a, "sh": s, "dir": d, "arith": ar}
            for a in (0x00, 0x01, 0x7F, 0x80, 0xAA, 0xFF)
            for s in (0, 1, 3, 7)
            for d in (0, 1) for ar in (0, 1)]
    return _build(top, rtl, M(), stim, clocked=False)


# ----------------------------------------------------------------- idecode
def idecode() -> dict:
    top = "idecode"
    rtl = """`timescale 1ns/1ps
module idecode (
    input  wire [7:0] op,
    output reg  [2:0] alu_op,
    output reg        reg_we,
    output reg        mem_rd,
    output reg        mem_wr,
    output reg        imm
);
    always @(*) begin
        alu_op = 3'd0;
        reg_we = 1'b0;
        mem_rd = 1'b0;
        mem_wr = 1'b0;
        imm    = 1'b0;
        case (op[7:6])
            2'b00: begin alu_op = op[2:0]; reg_we = 1'b1; end
            2'b01: begin mem_rd = 1'b1;    reg_we = 1'b1; end
            2'b10: begin mem_wr = 1'b1; end
            default: begin imm = 1'b1; reg_we = 1'b1; alu_op = 3'd1; end
        endcase
    end
endmodule
"""

    class M:
        def reset(self):
            pass

        def step(self, i):
            op = i["op"] & 0xFF
            top2 = op >> 6
            r = {"alu_op": 0, "reg_we": 0, "mem_rd": 0, "mem_wr": 0,
                 "imm": 0}
            if top2 == 0:
                r.update(alu_op=op & 7, reg_we=1)
            elif top2 == 1:
                r.update(mem_rd=1, reg_we=1)
            elif top2 == 2:
                r.update(mem_wr=1)
            else:
                r.update(imm=1, reg_we=1, alu_op=1)
            return r

    stim = [{"op": v} for v in range(256)]
    return _build(top, rtl, M(), stim, clocked=False)


# ------------------------------------------------------------- freq_counter
def freq_counter() -> dict:
    top = "freq_counter"
    rtl = """`timescale 1ns/1ps
module freq_counter (
    input  wire        clk,
    input  wire        rst,
    input  wire        gate,
    input  wire        sig,
    output reg  [15:0] count,
    output reg         done
);
    reg sig_d, gate_d, measuring;
    reg [15:0] c;
    always @(posedge clk) begin
        if (rst) begin
            c <= 16'd0; count <= 16'd0; done <= 1'b0;
            sig_d <= 1'b0; gate_d <= 1'b0; measuring <= 1'b0;
        end else begin
            sig_d  <= sig;
            gate_d <= gate;
            done   <= 1'b0;
            if (gate) begin
                measuring <= 1'b1;
                if (sig && !sig_d) c <= c + 16'd1;
            end else if (measuring) begin
                measuring <= 1'b0;
                count <= c;
                c <= 16'd0;
                done <= 1'b1;
            end
        end
    end
endmodule
"""

    class M:
        def reset(self):
            self.c = 0
            self.count = 0
            self.sig_d = 0
            self.measuring = 0
            self.done = 0

        def step(self, i):
            sig = i["sig"] & 1
            gate = i["gate"] & 1
            self.done = 0
            if gate:
                self.measuring = 1
                if sig and not self.sig_d:
                    self.c = (self.c + 1) & 0xFFFF
            elif self.measuring:
                self.measuring = 0
                self.count = self.c
                self.c = 0
                self.done = 1
            self.sig_d = sig
            return {"count": self.count, "done": self.done}

    stim = ([{"gate": 1, "sig": 1}, {"gate": 1, "sig": 0}] * 6
            + [{"gate": 1, "sig": 1}, {"gate": 1, "sig": 0}] * 4
            + [{"gate": 0, "sig": 0}, {"gate": 0, "sig": 0}]
            + [{"gate": 1, "sig": 1}, {"gate": 1, "sig": 0}] * 3
            + [{"gate": 0, "sig": 0}])
    return _build(top, rtl, M(), stim, clocked=True)


# -------------------------------------------------------------- pulse_width
def pulse_width() -> dict:
    top = "pulse_width"
    rtl = """`timescale 1ns/1ps
module pulse_width (
    input  wire        clk,
    input  wire        rst,
    input  wire        sig,
    output reg  [15:0] width,
    output reg         done
);
    reg sig_d, measuring;
    reg [15:0] c;
    always @(posedge clk) begin
        if (rst) begin
            width <= 16'd0; done <= 1'b0; c <= 16'd0;
            sig_d <= 1'b0; measuring <= 1'b0;
        end else begin
            sig_d <= sig;
            done  <= 1'b0;
            if (sig && !sig_d) begin
                c <= 16'd1;
                measuring <= 1'b1;
            end else if (measuring && !sig) begin
                width <= c;
                measuring <= 1'b0;
                done <= 1'b1;
            end else if (measuring) begin
                c <= c + 16'd1;
            end
        end
    end
endmodule
"""

    class M:
        def reset(self):
            self.width = 0
            self.done = 0
            self.c = 0
            self.sig_d = 0
            self.measuring = 0

        def step(self, i):
            sig = i["sig"] & 1
            self.done = 0
            if sig and not self.sig_d:
                self.c = 1
                self.measuring = 1
            elif self.measuring and not sig:
                self.width = self.c
                self.measuring = 0
                self.done = 1
            elif self.measuring:
                self.c = (self.c + 1) & 0xFFFF
            self.sig_d = sig
            return {"width": self.width, "done": self.done}

    stim = ([{"sig": 1} for _ in range(5)] + [{"sig": 0} for _ in range(2)]
            + [{"sig": 1} for _ in range(9)] + [{"sig": 0} for _ in range(2)]
            + [{"sig": 1}] + [{"sig": 0} for _ in range(2)]
            + [{"sig": 1} for _ in range(3)] + [{"sig": 0} for _ in range(2)]
            + _rand(60, 41, sig=[0, 1, 1, 0]))
    return _build(top, rtl, M(), stim, clocked=True)


# ----------------------------------------------------------------- traffic
def traffic() -> dict:
    top = "traffic"
    G, Y, R = 8, 4, 8
    rtl = """`timescale 1ns/1ps
module traffic (
    input  wire       clk,
    input  wire       rst,
    input  wire       ped,
    output reg  [2:0] light,     // {green, yellow, red}
    output reg        ped_go
);
    reg [1:0] state;
    reg [3:0] t;
    reg       want;
    always @(posedge clk) begin
        if (rst) begin
            state <= 2'd0; t <= 4'd0; light <= 3'b100; ped_go <= 1'b0;
            want <= 1'b0;
        end else begin
            if (ped) want <= 1'b1;
            t <= t + 4'd1;
            case (state)
                2'd0: if (t == 4'd7) begin
                    state <= 2'd1; t <= 4'd0; light <= 3'b010;
                end
                2'd1: if (t == 4'd3) begin
                    state <= 2'd2; t <= 4'd0; light <= 3'b001;
                    ped_go <= want; want <= 1'b0;
                end
                2'd2: if (t == 4'd7) begin
                    state <= 2'd0; t <= 4'd0; light <= 3'b100;
                    ped_go <= 1'b0;
                end
                default: state <= 2'd0;
            endcase
        end
    end
endmodule
"""

    class M:
        def reset(self):
            self.state = 0
            self.t = 0
            self.light = 0b100
            self.ped_go = 0
            self.want = 0

        def step(self, i):
            ped = i["ped"] & 1
            if ped:
                self.want = 1
            t = self.t
            if self.state == 0:
                if t == G - 1:
                    self.state, self.t, self.light = 1, 0, 0b010
                else:
                    self.t = (t + 1) & 0xF
            elif self.state == 1:
                if t == Y - 1:
                    self.state, self.t, self.light = 2, 0, 0b001
                    self.ped_go = self.want
                    self.want = 0
                else:
                    self.t = (t + 1) & 0xF
            else:
                if t == R - 1:
                    self.state, self.t, self.light = 0, 0, 0b100
                    self.ped_go = 0
                else:
                    self.t = (t + 1) & 0xF
            return {"light": self.light, "ped_go": self.ped_go}

    stim = ([{"ped": 0} for _ in range(5)] + [{"ped": 1}]
            + [{"ped": 0} for _ in range(30)] + [{"ped": 1}]
            + [{"ped": 0} for _ in range(20)])
    return _build(top, rtl, M(), stim, clocked=True)


# -------------------------------------------------------------------- vend
def vend() -> dict:
    top = "vend"
    rtl = """`timescale 1ns/1ps
module vend (
    input  wire clk,
    input  wire rst,
    input  wire coin5,
    input  wire coin10,
    input  wire coin25,
    input  wire cancel,
    output reg  dispense,
    output reg  change,
    output reg  [5:0] credit
);
    wire [5:0] add = coin25 ? 6'd25 : coin10 ? 6'd10 : coin5 ? 6'd5 : 6'd0;
    wire [5:0] ns  = credit + add;
    always @(posedge clk) begin
        if (rst) begin
            credit <= 6'd0; dispense <= 1'b0; change <= 1'b0;
        end else begin
            dispense <= 1'b0;
            change   <= 1'b0;
            if (cancel) begin
                change <= (credit != 6'd0);
                credit <= 6'd0;
            end else if (ns >= 6'd30) begin
                dispense <= 1'b1;
                change   <= (ns > 6'd30);
                credit   <= 6'd0;
            end else begin
                credit <= ns;
            end
        end
    end
endmodule
"""

    class M:
        def reset(self):
            self.credit = 0
            self.disp = 0
            self.change = 0

        def step(self, i):
            add = 25 if i.get("coin25") else 10 if i.get("coin10") else \
                5 if i.get("coin5") else 0
            ns = self.credit + add
            self.disp = 0
            self.change = 0
            if i.get("cancel"):
                self.change = 1 if self.credit else 0
                self.credit = 0
            elif ns >= 30:
                self.disp = 1
                self.change = 1 if ns > 30 else 0
                self.credit = 0
            else:
                self.credit = ns
            return {"dispense": self.disp, "change": self.change,
                    "credit": self.credit}

    stim = ([{"coin25": 1, "coin10": 0, "coin5": 0, "cancel": 0}]
            + [{"coin25": 0, "coin10": 0, "coin5": 1, "cancel": 0}]
            + [{"coin25": 0, "coin10": 0, "coin5": 0, "cancel": 1}]
            + [{"coin25": 0, "coin10": 1, "coin5": 0, "cancel": 0}] * 3
            + [{"coin25": 0, "coin10": 0, "coin5": 0, "cancel": 1}]
            + [{"coin25": 0, "coin10": 0, "coin5": 1, "cancel": 0}] * 7
            + [{"coin25": 0, "coin10": 0, "coin5": 0, "cancel": 1}])
    return _build(top, rtl, M(), stim, clocked=True)


# ------------------------------------------------------------------ segmux
_SEG = [0b1000000, 0b1111001, 0b0100100, 0b0110000, 0b0011001,
        0b0010010, 0b0000010, 0b1111000, 0b0000000, 0b0010000,
        0b0001000, 0b0000011, 0b1000110, 0b0100001, 0b0000110,
        0b0001110]


def segmux() -> dict:
    top = "segmux"
    case_lines = "\n".join(
        f"            4'h{i:X}: seg = 7'b{_SEG[i]:07b};" for i in range(16))
    rtl = f"""`timescale 1ns/1ps
module segmux (
    input  wire       clk,
    input  wire       rst,
    input  wire [15:0] digits,
    output reg  [6:0] seg,
    output reg  [3:0] an
);
    reg [1:0] idx;
    reg [3:0] d;
    always @(posedge clk) begin
        if (rst) idx <= 2'd0;
        else     idx <= idx + 2'd1;
    end
    always @(*) begin
        case (idx)
            2'd0: d = digits[3:0];
            2'd1: d = digits[7:4];
            2'd2: d = digits[11:8];
            default: d = digits[15:12];
        endcase
        case (d)
{case_lines}
            default: seg = 7'b1111111;
        endcase
        an = ~(4'b0001 << idx);
    end
endmodule
"""

    class M:
        def reset(self):
            self.idx = 0

        def step(self, i):
            # the DUT advances its index on the clock edge, so the outputs
            # sampled after that edge belong to the *new* index
            self.idx = (self.idx + 1) & 3
            idx = self.idx
            d = (i["digits"] >> (4 * idx)) & 0xF
            seg = _SEG[d]
            an = (~(1 << idx)) & 0xF
            return {"seg": seg, "an": an}

    stim = [{"digits": 0x1234}, {"digits": 0x1234}, {"digits": 0x1234},
            {"digits": 0x1234}, {"digits": 0xABCD}, {"digits": 0xABCD},
            {"digits": 0xABCD}, {"digits": 0xABCD}, {"digits": 0x0000},
            {"digits": 0x0000}, {"digits": 0x0000}, {"digits": 0x0000}]
    return _build(top, rtl, M(), stim, clocked=True)


# --------------------------------------------------------------- stopwatch
def stopwatch() -> dict:
    top = "stopwatch"
    rtl = """`timescale 1ns/1ps
module stopwatch (
    input  wire       clk,
    input  wire       rst,
    input  wire       start,
    input  wire       stop,
    input  wire       clear,
    output reg  [3:0] tenths,
    output reg  [3:0] sec_lo,
    output reg  [3:0] sec_hi
);
    reg running;
    wire run_next = start ? 1'b1 : (stop ? 1'b0 : running);
    always @(posedge clk) begin
        if (rst || clear) begin
            running <= 1'b0; tenths <= 4'd0;
            sec_lo <= 4'd0; sec_hi <= 4'd0;
        end else begin
            running <= run_next;
            if (running) begin
                if (tenths == 4'd9) begin
                    tenths <= 4'd0;
                    if (sec_lo == 4'd9) begin
                        sec_lo <= 4'd0;
                        sec_hi <= (sec_hi == 4'd5) ? 4'd0 : sec_hi + 4'd1;
                    end else begin
                        sec_lo <= sec_lo + 4'd1;
                    end
                end else begin
                    tenths <= tenths + 4'd1;
                end
            end
        end
    end
endmodule
"""

    class M:
        def reset(self):
            self.running = 0
            self.t = 0
            self.slo = 0
            self.shi = 0

        def step(self, i):
            if i.get("clear"):
                self.running = 0
                self.t = self.slo = self.shi = 0
            else:
                nxt = 1 if i.get("start") else (0 if i.get("stop")
                                                else self.running)
                if self.running:
                    if self.t == 9:
                        self.t = 0
                        if self.slo == 9:
                            self.slo = 0
                            self.shi = 0 if self.shi == 5 else self.shi + 1
                        else:
                            self.slo += 1
                    else:
                        self.t += 1
                self.running = nxt
            return {"tenths": self.t, "sec_lo": self.slo, "sec_hi": self.shi}

    stim = ([{"start": 1, "stop": 0, "clear": 0}]
            + [{"start": 0, "stop": 0, "clear": 0} for _ in range(12)]
            + [{"start": 0, "stop": 1, "clear": 0}]
            + [{"start": 0, "stop": 0, "clear": 0} for _ in range(3)]
            + [{"start": 0, "stop": 0, "clear": 1}]
            + [{"start": 1, "stop": 0, "clear": 0}]
            + [{"start": 0, "stop": 0, "clear": 0} for _ in range(25)])
    return _build(top, rtl, M(), stim, clocked=True)


# --------------------------------------------------------------- ledchase
def ledchase() -> dict:
    top = "ledchase"
    rtl = """`timescale 1ns/1ps
module ledchase (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    input  wire       dir,
    input  wire [1:0] speed,
    output reg  [7:0] leds
);
    reg [7:0] div;
    wire [7:0] nxt = dir ? {leds[0], leds[7:1]}
                         : {leds[6:0], leds[7]};
    always @(posedge clk) begin
        if (rst) begin
            leds <= 8'b0000_0001; div <= 8'd0;
        end else if (en) begin
            if (div >= {6'b0, speed}) begin
                div <= 8'd0;
                leds <= nxt;
            end else begin
                div <= div + 8'd1;
            end
        end
    end
endmodule
"""

    class M:
        def reset(self):
            self.leds = 1
            self.div = 0

        def step(self, i):
            if i.get("en"):
                if self.div >= (i["speed"] & 3):
                    self.div = 0
                    if i.get("dir"):
                        self.leds = ((self.leds >> 1) |
                                     ((self.leds & 1) << 7)) & 0xFF
                    else:
                        self.leds = ((self.leds << 1) |
                                     ((self.leds >> 7) & 1)) & 0xFF
                else:
                    self.div += 1
            return {"leds": self.leds}

    stim = ([{"en": 1, "dir": 0, "speed": 0} for _ in range(10)]
            + [{"en": 1, "dir": 1, "speed": 0} for _ in range(6)]
            + [{"en": 1, "dir": 0, "speed": 3} for _ in range(20)]
            + _rand(60, 42, en=[0, 1, 1], dir=[0, 1], speed=[0, 1, 2, 3]))
    return _build(top, rtl, M(), stim, clocked=True)


BLOCKS = {
    "parity8": parity8,
    "popcount4": popcount4,
    "bitrev8": bitrev8,
    "gray_counter": gray_counter,
    "johnson4": johnson4,
    "edge_detect": edge_detect,
    "updown8": updown8,
    "lfsr8": lfsr8,
    "bin2bcd": bin2bcd,
    "prio16": prio16,
    "satadd": satadd,
    "absval": absval,
    "lzc": lzc,
    "hamming_enc": hamming_enc,
    "ringcounter": ringcounter,
    "oneshot": oneshot,
    "watchdog": watchdog,
    "interval_timer": interval_timer,
    "stepper": stepper,
    "seqdet": seqdet,
    "stack8": stack8,
    "pc_branch": pc_branch,
    "mac4": mac4,
    "barrelshift": barrelshift,
    "idecode": idecode,
    "freq_counter": freq_counter,
    "pulse_width": pulse_width,
    "traffic": traffic,
    "vend": vend,
    "segmux": segmux,
    "stopwatch": stopwatch,
    "ledchase": ledchase,
}