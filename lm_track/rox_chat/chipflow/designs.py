"""Deterministic RTL block generators.

Every block here is written by construction (not by a model) and ships with
a self-checking testbench, so it passes lint/sim/synth/formal by design.
The model is used for *composition and glue* on top of these.
"""
from __future__ import annotations

# Each generator: params -> {"top": name, "rtl": verilog, "tb": testbench}


def counter(width: int = 8) -> dict:
    w = int(width)
    top = f"counter{w}"
    rtl = f"""// {top}: up counter with synchronous reset + enable
`timescale 1ns/1ps
module {top} (
    input  wire         clk,
    input  wire         rst,
    input  wire         en,
    output reg  [{w-1}:0] q,
    output wire         carry
);
    assign carry = en && (q == {w}'h{(1<<w)-1:0X});
    always @(posedge clk) begin
        if (rst)      q <= {w}'h0;
        else if (en)  q <= q + {w}'h1;
    end
endmodule
"""
    tb = f"""`timescale 1ns/1ps
module tb_{top};
    reg clk = 0, rst = 0, en = 0;
    wire [{w-1}:0] q;
    wire carry;
    integer errors = 0;
    {top} uut(.clk(clk), .rst(rst), .en(en), .q(q), .carry(carry));
    always #5 clk = ~clk;
    task chk(input [{w-1}:0] exp);
        begin
            if (q !== exp) begin
                $display("{top}:FAIL got=%0d exp=%0d", q, exp);
                errors = errors + 1;
            end
        end
    endtask
    initial begin
        rst = 1; @(posedge clk); #1; chk({w}'h0);
        rst = 0; en = 0; @(posedge clk); #1; chk({w}'h0);
        en = 1; repeat(3) @(posedge clk); #1; chk({w}'h3);
        en = 0; repeat(2) @(posedge clk); #1; chk({w}'h3);
        en = 1; repeat(5) @(posedge clk); #1; chk({w}'h8);
        rst = 1; @(posedge clk); #1; chk({w}'h0);
        if (errors == 0) $display("{top}:PASS");
        else $fatal(1, "{top}:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def alu4() -> dict:
    top = "alu4"
    rtl = """`timescale 1ns/1ps
module alu4 (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire [2:0] op,
    output reg  [3:0] y,
    output wire       zero
);
    always @(*) begin
        case (op)
            3'd0: y = a + b;
            3'd1: y = a - b;
            3'd2: y = a & b;
            3'd3: y = a | b;
            3'd4: y = a ^ b;
            3'd5: y = ~a;
            3'd6: y = a << 1;
            3'd7: y = a >> 1;
            default: y = 4'b0000;
        endcase
    end
    assign zero = (y == 4'b0000);
endmodule
"""
    tb = """`timescale 1ns/1ps
module tb_alu4;
    reg [3:0] a, b; reg [2:0] op; wire [3:0] y; wire zero;
    integer errors = 0;
    alu4 uut(.a(a), .b(b), .op(op), .y(y), .zero(zero));
    task chk(input [3:0] ea, input ez);
        begin
            if (y !== ea || zero !== ez) begin
                $display("alu4:FAIL a=%0d b=%0d op=%0d got=%0d exp=%0d",
                         a, b, op, y, ea);
                errors = errors + 1;
            end
        end
    endtask
    initial begin
        a=4'd3; b=4'd5; op=3'd0; #1; chk(4'd8, 1'b0);
        a=4'd3; b=4'd5; op=3'd1; #1; chk(4'd14, 1'b0);
        a=4'd6; b=4'd6; op=3'd1; #1; chk(4'd0, 1'b1);
        a=4'b1010; b=4'b1100; op=3'd2; #1; chk(4'b1000, 1'b0);
        a=4'b1010; b=4'b1100; op=3'd3; #1; chk(4'b1110, 1'b0);
        a=4'b1010; b=4'b1100; op=3'd4; #1; chk(4'b0110, 1'b0);
        a=4'b1010; b=4'b0000; op=3'd5; #1; chk(4'b0101, 1'b0);
        a=4'b1010; b=4'b0000; op=3'd6; #1; chk(4'b0100, 1'b0);
        a=4'b1010; b=4'b0000; op=3'd7; #1; chk(4'b0101, 1'b0);
        if (errors == 0) $display("alu4:PASS");
        else $fatal(1, "alu4:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def shiftreg(width: int = 8) -> dict:
    w = int(width)
    top = f"shiftreg{w}"
    rtl = f"""`timescale 1ns/1ps
module {top} (
    input  wire         clk,
    input  wire         rst,
    input  wire         load,
    input  wire         sin,
    input  wire [{w-1}:0] din,
    output reg  [{w-1}:0] q
);
    always @(posedge clk) begin
        if (rst)       q <= {w}'h0;
        else if (load) q <= din;
        else           q <= {{q[{w-2}:0], sin}};
    end
endmodule
"""
    tb = f"""`timescale 1ns/1ps
module tb_{top};
    reg clk = 0, rst = 0, load = 0, sin = 0;
    reg [{w-1}:0] din = 0;
    wire [{w-1}:0] q;
    integer errors = 0;
    {top} uut(.clk(clk), .rst(rst), .load(load), .sin(sin), .din(din), .q(q));
    always #5 clk = ~clk;
    task chk(input [{w-1}:0] exp);
        begin
            if (q !== exp) begin
                $display("{top}:FAIL got=%b exp=%b", q, exp);
                errors = errors + 1;
            end
        end
    endtask
    initial begin
        rst = 1; @(posedge clk); #1; chk({w}'h0);
        rst = 0; load = 1; din = {w}'hA5; @(posedge clk); #1; chk({w}'hA5);
        load = 0; sin = 1; @(posedge clk); #1; chk((din << 1) | 1);
        sin = 0; @(posedge clk); #1;
        if (errors == 0) $display("{top}:PASS");
        else $fatal(1, "{top}:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def fsm() -> dict:
    top = "fsm3"
    rtl = """`timescale 1ns/1ps
module fsm3 (
    input  wire       clk,
    input  wire       rst,
    input  wire       go,
    output reg  [1:0] state,
    output reg        done
);
    localparam IDLE = 2'd0, RUN = 2'd1, DONE = 2'd2;
    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE; done <= 1'b0;
        end else begin
            case (state)
                IDLE: begin
                    done <= 1'b0;
                    if (go) state <= RUN;
                end
                RUN: begin
                    done <= 1'b1;
                    state <= DONE;
                end
                DONE: begin
                    done <= 1'b0;
                    state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
"""
    tb = """`timescale 1ns/1ps
module tb_fsm3;
    reg clk = 0, rst = 0, go = 0;
    wire [1:0] state; wire done;
    integer errors = 0;
    fsm3 uut(.clk(clk), .rst(rst), .go(go), .state(state), .done(done));
    always #5 clk = ~clk;
    task chk(input [1:0] es, input ed);
        begin
            if (state !== es || done !== ed) begin
                $display("fsm3:FAIL state=%0d done=%b exp_state=%0d exp_done=%b",
                         state, done, es, ed);
                errors = errors + 1;
            end
        end
    endtask
    initial begin
        rst = 1; @(posedge clk); #1; chk(2'd0, 1'b0);
        rst = 0; go = 0; @(posedge clk); #1; chk(2'd0, 1'b0);
        go = 1; @(posedge clk); #1; chk(2'd1, 1'b0);
        @(posedge clk); #1; chk(2'd2, 1'b1);
        @(posedge clk); #1; chk(2'd0, 1'b0);
        if (errors == 0) $display("fsm3:PASS");
        else $fatal(1, "fsm3:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def pwm(width: int = 8) -> dict:
    w = int(width)
    top = f"pwm{w}"
    rtl = f"""`timescale 1ns/1ps
module {top} (
    input  wire           clk,
    input  wire           rst,
    input  wire [{w-1}:0] duty,
    output reg            pwm
);
    reg [{w-1}:0] cnt;
    always @(posedge clk) begin
        if (rst) begin
            cnt <= {w}'h0;
            pwm <= 1'b0;
        end else begin
            cnt <= cnt + {w}'h1;
            pwm <= (cnt < duty);
        end
    end
endmodule
"""
    tb = f"""`timescale 1ns/1ps
module tb_{top};
    reg clk = 0, rst = 0;
    reg [{w-1}:0] duty = 0;
    wire pwm;
    integer high = 0, i;
    integer errors = 0;
    {top} uut(.clk(clk), .rst(rst), .duty(duty), .pwm(pwm));
    always #5 clk = ~clk;
    initial begin
        rst = 1; duty = 8'd64; @(posedge clk); #1;
        rst = 0;
        for (i = 0; i < 256; i = i + 1) begin
            @(posedge clk); #1;
            if (pwm) high = high + 1;
        end
        // duty 64/256 -> high count should be ~64 (+/- 2)
        if (high < 62 || high > 66) begin
            $display("{top}:FAIL high=%0d expected~64", high);
            errors = errors + 1;
        end
        if (errors == 0) $display("{top}:PASS");
        else $fatal(1, "{top}:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def uart_tx(clks_per_bit: int = 16) -> dict:
    cpb = int(clks_per_bit)
    top = "uart_tx"
    rtl = f"""`timescale 1ns/1ps
module uart_tx #(parameter CLKS_PER_BIT = {cpb}) (
    input  wire       clk,
    input  wire       rst,
    input  wire       start,
    input  wire [7:0] data,
    output reg        tx,
    output reg        busy
);
    localparam IDLE = 2'd0, START = 2'd1, DATA = 2'd2, STOP = 2'd3;
    reg [1:0]  state;
    reg [15:0] clk_cnt;
    reg [3:0]  bit_idx;
    reg [7:0]  shifter;

    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE; tx <= 1'b1; busy <= 1'b0;
            clk_cnt <= 16'd0; bit_idx <= 4'd0; shifter <= 8'd0;
        end else begin
            case (state)
                IDLE: begin
                    tx <= 1'b1; busy <= 1'b0; clk_cnt <= 16'd0; bit_idx <= 4'd0;
                    if (start) begin
                        shifter <= data; busy <= 1'b1; state <= START;
                    end
                end
                START: begin
                    tx <= 1'b0;
                    if (clk_cnt == CLKS_PER_BIT - 1) begin
                        clk_cnt <= 16'd0; state <= DATA;
                    end else clk_cnt <= clk_cnt + 16'd1;
                end
                DATA: begin
                    tx <= shifter[0];
                    if (clk_cnt == CLKS_PER_BIT - 1) begin
                        clk_cnt <= 16'd0;
                        shifter <= {{1'b0, shifter[7:1]}};
                        if (bit_idx == 4'd7) begin
                            bit_idx <= 4'd0; state <= STOP;
                        end else bit_idx <= bit_idx + 4'd1;
                    end else clk_cnt <= clk_cnt + 16'd1;
                end
                STOP: begin
                    tx <= 1'b1;
                    if (clk_cnt == CLKS_PER_BIT - 1) begin
                        clk_cnt <= 16'd0; state <= IDLE; busy <= 1'b0;
                    end else clk_cnt <= clk_cnt + 16'd1;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
"""
    tb = f"""`timescale 1ns/1ps
module tb_uart_tx;
    reg clk = 0, rst = 0, start = 0;
    reg [7:0] data = 0;
    wire tx, busy;
    integer errors = 0, i;
    reg [7:0] rx;
    localparam CPB = {cpb};

    uart_tx #(.CLKS_PER_BIT(CPB)) uut(
        .clk(clk), .rst(rst), .start(start), .data(data),
        .tx(tx), .busy(busy));
    always #5 clk = ~clk;

    // sample the line at the centre of each data bit
    task receive(output [7:0] r);
        integer k, half;
        begin
            @(negedge tx);            // start bit begins
            for (half = 0; half < CPB + CPB/2; half = half + 1)
                @(posedge clk);
            for (k = 0; k < 8; k = k + 1) begin
                r[k] = tx;
                for (half = 0; half < CPB; half = half + 1)
                    @(posedge clk);
            end
        end
    endtask

    initial begin
        rst = 1; @(posedge clk); #1;
        rst = 0; data = 8'hA5;
        fork
            begin
                // drive start cleanly: assert before a posedge and hold a
                // full cycle, deassert on a negedge.  Deasserting in the
                // same delta as the posedge made the DUT miss it.
                @(negedge clk); start = 1;
                @(negedge clk); start = 0;
            end
            receive(rx);
        join
        if (rx !== 8'hA5) begin
            $display("uart_tx:FAIL rx=%h exp=A5", rx);
            errors = errors + 1;
        end
        if (errors == 0) $display("uart_tx:PASS");
        else $fatal(1, "uart_tx:FAIL");
        $finish;
    end

    initial begin
        #20000;
        $display("uart_tx:FAIL timeout");
        $fatal(1, "uart_tx timeout");
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def comparator(width: int = 4) -> dict:
    w = int(width)
    top = f"cmp{w}"
    n = 1 << w
    rtl = f"""`timescale 1ns/1ps
module {top} (
    input  wire [{w-1}:0] a,
    input  wire [{w-1}:0] b,
    output wire gt,
    output wire lt,
    output wire eq
);
    assign gt = (a > b);
    assign lt = (a < b);
    assign eq = (a == b);
endmodule
"""
    maxv = (1 << w) - 1
    if w <= 8:
        stimulus = f"""        for (i = 0; i < {n}; i = i + 1)
            for (j = 0; j < {n}; j = j + 1)
                chk(i, j);"""
    else:
        # exhaustive is 2^32 pairs at 16 bits - use edges plus random
        stimulus = f"""        chk(0, 0); chk(0, 1); chk(1, 0);
        chk({maxv}, 0); chk(0, {maxv});
        chk({maxv}, {maxv}); chk({maxv}, {maxv-1}); chk({maxv-1}, {maxv});
        for (i = 0; i < {w}; i = i + 1) begin
            chk((1 << i), 0);
            chk(0, (1 << i));
            chk((1 << i), (1 << i));
            chk((1 << i) - 1, (1 << i));
        end
        for (i = 0; i < 20000; i = i + 1) chk($random, $random);"""
    tb = f"""`timescale 1ns/1ps
module tb_{top};
    reg [{w-1}:0] a, b;
    wire gt, lt, eq;
    integer i, j, errors = 0;
    {top} uut(.a(a), .b(b), .gt(gt), .lt(lt), .eq(eq));
    task chk(input [{w-1}:0] x, input [{w-1}:0] y);
        begin
            a = x; b = y; #1;
            if (gt !== (x > y) || lt !== (x < y) || eq !== (x == y)) begin
                $display("{top}:FAIL a=%0d b=%0d gt=%b lt=%b eq=%b",
                         a, b, gt, lt, eq);
                errors = errors + 1;
            end
        end
    endtask
    initial begin
{stimulus}
        if (errors == 0) $display("{top}:PASS");
        else $fatal(1, "{top}:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def fifo(width: int = 8, depth: int = 8) -> dict:
    w, d = int(width), int(depth)
    aw = max(1, (d - 1).bit_length())
    top = f"fifo{w}x{d}"
    rtl = f"""`timescale 1ns/1ps
module {top} (
    input  wire           clk,
    input  wire           rst,
    input  wire           wr,
    input  wire           rd,
    input  wire [{w-1}:0] din,
    output reg  [{w-1}:0] dout,
    output wire           full,
    output wire           empty,
    output reg  [{aw}:0]  count
);
    reg [{w-1}:0] mem [0:{d-1}];
    reg [{aw-1}:0] wptr, rptr;
    assign empty = (count == 0);
    assign full  = (count == {d});
    always @(posedge clk) begin
        if (rst) begin
            wptr <= 0; rptr <= 0; count <= 0; dout <= 0;
        end else begin
            if (wr && !full) begin
                mem[wptr] <= din;
                wptr <= wptr + 1'b1;
            end
            if (rd && !empty) begin
                dout <= mem[rptr];
                rptr <= rptr + 1'b1;
            end
            case ({{wr && !full, rd && !empty}})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule
"""
    tb = f"""`timescale 1ns/1ps
module tb_{top};
    reg clk = 0, rst = 0, wr = 0, rd = 0;
    reg [{w-1}:0] din = 0;
    wire [{w-1}:0] dout;
    wire full, empty;
    wire [{aw}:0] count;
    integer errors = 0, i;
    {top} uut(.clk(clk), .rst(rst), .wr(wr), .rd(rd), .din(din),
              .dout(dout), .full(full), .empty(empty), .count(count));
    always #5 clk = ~clk;
    initial begin
        rst = 1; @(posedge clk); #1; rst = 0;
        if (!empty) begin $display("{top}:FAIL not empty after reset"); errors = errors + 1; end
        for (i = 0; i < {d}; i = i + 1) begin
            wr = 1; din = i[{w-1}:0]; @(posedge clk); #1;
        end
        wr = 0; #1;
        if (!full) begin $display("{top}:FAIL not full after {d} writes"); errors = errors + 1; end
        for (i = 0; i < {d}; i = i + 1) begin
            rd = 1; @(posedge clk); #1;
            if (dout !== i[{w-1}:0]) begin
                $display("{top}:FAIL read %0d got %0d exp %0d", i, dout, i);
                errors = errors + 1;
            end
        end
        rd = 0; #1;
        if (!empty) begin $display("{top}:FAIL not empty after drain"); errors = errors + 1; end
        if (errors == 0) $display("{top}:PASS");
        else $fatal(1, "{top}:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def uart_rx(clks_per_bit: int = 16) -> dict:
    cpb = int(clks_per_bit)
    top = "uart_rx"
    rtl = f"""`timescale 1ns/1ps
module uart_rx #(parameter CLKS_PER_BIT = {cpb}) (
    input  wire       clk,
    input  wire       rst,
    input  wire       rx,
    output reg  [7:0] data,
    output reg        valid
);
    localparam IDLE = 2'd0, START = 2'd1, DATA = 2'd2, STOP = 2'd3;
    reg [1:0]  state;
    reg [15:0] cnt;
    reg [3:0]  bit_idx;
    reg [7:0]  sh;

    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE; cnt <= 0; bit_idx <= 0; sh <= 0;
            data <= 0; valid <= 0;
        end else begin
            valid <= 1'b0;
            case (state)
                IDLE: if (!rx) begin cnt <= 0; state <= START; end
                START: begin
                    if (cnt == CLKS_PER_BIT / 2) begin
                        if (!rx) begin cnt <= 0; bit_idx <= 0; state <= DATA; end
                        else state <= IDLE;
                    end else cnt <= cnt + 1'b1;
                end
                DATA: begin
                    if (cnt == CLKS_PER_BIT - 1) begin
                        cnt <= 0;
                        sh <= {{rx, sh[7:1]}};
                        if (bit_idx == 4'd7) state <= STOP;
                        else bit_idx <= bit_idx + 1'b1;
                    end else cnt <= cnt + 1'b1;
                end
                STOP: begin
                    if (cnt == CLKS_PER_BIT - 1) begin
                        cnt <= 0; data <= sh; valid <= 1'b1; state <= IDLE;
                    end else cnt <= cnt + 1'b1;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
"""
    tb = f"""`timescale 1ns/1ps
module tb_uart_rx;
    reg clk = 0, rst = 0, rx = 1;
    wire [7:0] data;
    wire valid;
    integer errors = 0, k;
    localparam CPB = {cpb};
    uart_rx #(.CLKS_PER_BIT(CPB)) uut(.clk(clk), .rst(rst), .rx(rx),
                                      .data(data), .valid(valid));
    always #5 clk = ~clk;
    task send(input [7:0] b);
        integer i;
        begin
            // drive on negedges so the DUT always samples a stable level
            @(negedge clk); rx = 0;                   // start bit
            repeat (CPB) @(negedge clk);
            for (i = 0; i < 8; i = i + 1) begin
                rx = b[i];
                repeat (CPB) @(negedge clk);
            end
            rx = 1;                                   // stop bit
            repeat (CPB) @(negedge clk);
        end
    endtask
    reg [7:0] captured;
    initial begin
        rst = 1; @(posedge clk); #1; rst = 0;
        fork
            send(8'h5A);
            begin
                @(posedge valid);     // valid is a one-cycle pulse
                captured = data;
            end
        join
        if (captured !== 8'h5A) begin
            $display("uart_rx:FAIL data=%h exp=5A", captured);
            errors = errors + 1;
        end
        if (errors == 0) $display("uart_rx:PASS");
        else $fatal(1, "uart_rx:FAIL");
        $finish;
    end
    initial begin
        #(CPB * 400);
        $display("uart_rx:FAIL timeout");
        $fatal(1, "uart_rx timeout");
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def vga_timing(h_total: int = 800, h_sync: int = 96, h_bp: int = 48,
               h_vis: int = 640, v_total: int = 525, v_sync: int = 2,
               v_bp: int = 33, v_vis: int = 480) -> dict:
    top = "vga_timing"
    rtl = f"""`timescale 1ns/1ps
module {top} (
    input  wire        clk,
    input  wire        rst,
    output reg         hsync,
    output reg         vsync,
    output wire [9:0]  x,
    output wire [9:0]  y,
    output wire        active
);
    localparam H_TOTAL = {h_total}, H_SYNC = {h_sync}, H_BP = {h_bp},
               H_VIS = {h_vis};
    localparam V_TOTAL = {v_total}, V_SYNC = {v_sync}, V_BP = {v_bp},
               V_VIS = {v_vis};
    reg [9:0] hc, vc;

    assign x = (hc >= H_SYNC + H_BP) ? (hc - (H_SYNC + H_BP)) : 10'd0;
    assign y = (vc >= V_SYNC + V_BP) ? (vc - (V_SYNC + V_BP)) : 10'd0;
    assign active = (hc >= H_SYNC + H_BP) &&
                    (hc <  H_SYNC + H_BP + H_VIS) &&
                    (vc >= V_SYNC + V_BP) &&
                    (vc <  V_SYNC + V_BP + V_VIS);

    always @(posedge clk) begin
        if (rst) begin
            hc <= 0; vc <= 0;
        end else begin
            if (hc == H_TOTAL - 1) begin
                hc <= 0;
                vc <= (vc == V_TOTAL - 1) ? 10'd0 : (vc + 10'd1);
            end else hc <= hc + 10'd1;
        end
    end

    always @(*) begin
        hsync = ~(hc < H_SYNC);
        vsync = ~(vc < V_SYNC);
    end
endmodule
"""
    tb = f"""`timescale 1ns/1ps
module tb_{top};
    reg clk = 0, rst = 0;
    wire hsync, vsync, active;
    wire [9:0] x, y;
    integer errors = 0, i, hs = 0, vs = 0;
    {top} uut(.clk(clk), .rst(rst), .hsync(hsync), .vsync(vsync),
              .x(x), .y(y), .active(active));
    always #5 clk = ~clk;
    initial begin
        rst = 1; repeat (2) @(posedge clk); #1; rst = 0;
        for (i = 0; i < {h_total} * 2; i = i + 1) begin
            @(posedge clk); #1;
            if (!hsync) hs = hs + 1;
            if (!vsync) vs = vs + 1;
        end
        if (hs < {h_sync}) begin
            $display("{top}:FAIL hsync pulses %0d < {h_sync}", hs);
            errors = errors + 1;
        end
        if (vs < {v_sync}) begin
            $display("{top}:FAIL vsync pulses %0d < {v_sync}", vs);
            errors = errors + 1;
        end
        if (x > {h_vis}) begin
            $display("{top}:FAIL x out of range %0d", x);
            errors = errors + 1;
        end
        if (errors == 0) $display("{top}:PASS");
        else $fatal(1, "{top}:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def regfile(width: int = 8, depth: int = 4) -> dict:
    w, d = int(width), int(depth)
    aw = max(1, (d - 1).bit_length())
    top = f"regfile{w}x{d}"
    rtl = f"""`timescale 1ns/1ps
module {top} (
    input  wire           clk,
    input  wire           we,
    input  wire [{aw-1}:0] waddr,
    input  wire [{aw-1}:0] raddr1,
    input  wire [{aw-1}:0] raddr2,
    input  wire [{w-1}:0] wdata,
    output wire [{w-1}:0] rdata1,
    output wire [{w-1}:0] rdata2
);
    reg [{w-1}:0] mem [0:{d-1}];
    assign rdata1 = mem[raddr1];
    assign rdata2 = mem[raddr2];
    always @(posedge clk) begin
        if (we) mem[waddr] <= wdata;
    end
endmodule
"""
    tb = f"""`timescale 1ns/1ps
module tb_{top};
    reg clk = 0, we = 0;
    reg [{aw-1}:0] waddr = 0, raddr1 = 0, raddr2 = 0;
    reg [{w-1}:0] wdata = 0;
    wire [{w-1}:0] rdata1, rdata2;
    integer errors = 0, i;
    {top} uut(.clk(clk), .we(we), .waddr(waddr), .raddr1(raddr1),
              .raddr2(raddr2), .wdata(wdata), .rdata1(rdata1),
              .rdata2(rdata2));
    always #5 clk = ~clk;
    initial begin
        for (i = 0; i < {d}; i = i + 1) begin
            we = 1; waddr = i; wdata = i + 1; @(posedge clk); #1;
        end
        we = 0;
        for (i = 0; i < {d}; i = i + 1) begin
            raddr1 = i; raddr2 = ({d} - 1 - i); #1;
            if (rdata1 !== (i + 1)) begin
                $display("{top}:FAIL r1[%0d]=%0d exp %0d", i, rdata1, i+1);
                errors = errors + 1;
            end
            if (rdata2 !== ({d} - i)) begin
                $display("{top}:FAIL r2[%0d]=%0d exp %0d", i, rdata2, {d}-i);
                errors = errors + 1;
            end
        end
        if (errors == 0) $display("{top}:PASS");
        else $fatal(1, "{top}:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def clkdiv(div: int = 4) -> dict:
    dv = int(div)
    aw = max(1, (dv - 1).bit_length())
    top = f"clkdiv{dv}"
    rtl = f"""`timescale 1ns/1ps
module {top} (
    input  wire          clk,
    input  wire          rst,
    output reg           tick
);
    reg [{aw-1}:0] cnt;
    always @(posedge clk) begin
        if (rst) begin
            cnt <= 0; tick <= 1'b0;
        end else begin
            if (cnt == {dv} - 1) begin
                cnt <= 0; tick <= 1'b1;
            end else begin
                cnt <= cnt + 1'b1; tick <= 1'b0;
            end
        end
    end
endmodule
"""
    tb = f"""`timescale 1ns/1ps
module tb_{top};
    reg clk = 0, rst = 0;
    wire tick;
    integer ticks = 0, i;
    {top} uut(.clk(clk), .rst(rst), .tick(tick));
    always #5 clk = ~clk;
    initial begin
        rst = 1; repeat (2) @(posedge clk); #1; rst = 0;
        for (i = 0; i < {dv} * 10; i = i + 1) begin
            @(posedge clk); #1;
            if (tick) ticks = ticks + 1;
        end
        if (ticks < 9 || ticks > 11) begin
            $display("{top}:FAIL ticks=%0d expected~10", ticks);
            $fatal(1, "{top}:FAIL");
        end
        $display("{top}:PASS");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def bcd_counter() -> dict:
    top = "bcd_counter"
    rtl = """`timescale 1ns/1ps
module bcd_counter (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    output reg  [3:0] q,
    output wire       carry
);
    assign carry = en && (q == 4'd9);
    always @(posedge clk) begin
        if (rst)      q <= 4'd0;
        else if (en)  q <= (q == 4'd9) ? 4'd0 : (q + 4'd1);
    end
endmodule
"""
    tb = """`timescale 1ns/1ps
module tb_bcd_counter;
    reg clk = 0, rst = 0, en = 0;
    wire [3:0] q; wire carry;
    integer errors = 0, i;
    bcd_counter uut(.clk(clk), .rst(rst), .en(en), .q(q), .carry(carry));
    always #5 clk = ~clk;
    initial begin
        rst = 1; @(posedge clk); #1;
        if (q !== 4'd0) begin $display("bcd_counter:FAIL reset"); errors = errors + 1; end
        rst = 0; en = 1;
        for (i = 1; i <= 10; i = i + 1) begin
            @(posedge clk); #1;
            if (q !== (i % 10)) begin
                $display("bcd_counter:FAIL i=%0d q=%0d", i, q);
                errors = errors + 1;
            end
        end
        if (errors == 0) $display("bcd_counter:PASS");
        else $fatal(1, "bcd_counter:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def seg7() -> dict:
    top = "seg7"
    rtl = """`timescale 1ns/1ps
module seg7 (
    input  wire [3:0] hex,
    output reg  [6:0] seg
);
    always @(*) begin
        case (hex)
            4'h0: seg = 7'b1000000;
            4'h1: seg = 7'b1111001;
            4'h2: seg = 7'b0100100;
            4'h3: seg = 7'b0110000;
            4'h4: seg = 7'b0011001;
            4'h5: seg = 7'b0010010;
            4'h6: seg = 7'b0000010;
            4'h7: seg = 7'b1111000;
            4'h8: seg = 7'b0000000;
            4'h9: seg = 7'b0010000;
            4'hA: seg = 7'b0001000;
            4'hB: seg = 7'b0000011;
            4'hC: seg = 7'b1000110;
            4'hD: seg = 7'b0100001;
            4'hE: seg = 7'b0000110;
            4'hF: seg = 7'b0001110;
            default: seg = 7'b1111111;
        endcase
    end
endmodule
"""
    tb = """`timescale 1ns/1ps
module tb_seg7;
    reg [3:0] hex; wire [6:0] seg;
    integer errors = 0;
    seg7 uut(.hex(hex), .seg(seg));
    initial begin
        hex = 4'h0; #1; if (seg !== 7'b1000000) begin $display("seg7:FAIL 0"); errors = errors + 1; end
        hex = 4'h1; #1; if (seg !== 7'b1111001) begin $display("seg7:FAIL 1"); errors = errors + 1; end
        hex = 4'h5; #1; if (seg !== 7'b0010010) begin $display("seg7:FAIL 5"); errors = errors + 1; end
        hex = 4'h9; #1; if (seg !== 7'b0010000) begin $display("seg7:FAIL 9"); errors = errors + 1; end
        if (errors == 0) $display("seg7:PASS");
        else $fatal(1, "seg7:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def prio_enc8() -> dict:
    top = "prio_enc8"
    rtl = """`timescale 1ns/1ps
module prio_enc8 (
    input  wire [7:0] in,
    output reg  [2:0] idx,
    output reg        valid
);
    always @(*) begin
        valid = 1'b1;
        if      (in[7]) idx = 3'd7;
        else if (in[6]) idx = 3'd6;
        else if (in[5]) idx = 3'd5;
        else if (in[4]) idx = 3'd4;
        else if (in[3]) idx = 3'd3;
        else if (in[2]) idx = 3'd2;
        else if (in[1]) idx = 3'd1;
        else if (in[0]) idx = 3'd0;
        else begin idx = 3'd0; valid = 1'b0; end
    end
endmodule
"""
    tb = """`timescale 1ns/1ps
module tb_prio_enc8;
    reg [7:0] in; wire [2:0] idx; wire valid;
    integer errors = 0, i;
    prio_enc8 uut(.in(in), .idx(idx), .valid(valid));
    initial begin
        in = 8'h00; #1;
        if (valid !== 1'b0) begin $display("prio_enc8:FAIL zero"); errors = errors + 1; end
        for (i = 0; i < 8; i = i + 1) begin
            in = (8'h01 << i); #1;
            if (idx !== i || valid !== 1'b1) begin
                $display("prio_enc8:FAIL i=%0d idx=%0d", i, idx);
                errors = errors + 1;
            end
        end
        in = 8'hFF; #1;
        if (idx !== 3'd7) begin $display("prio_enc8:FAIL all-set"); errors = errors + 1; end
        if (errors == 0) $display("prio_enc8:PASS");
        else $fatal(1, "prio_enc8:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def gray4() -> dict:
    top = "gray4"
    rtl = """`timescale 1ns/1ps
module gray4 (
    input  wire [3:0] bin,
    output wire [3:0] gray
);
    assign gray = bin ^ (bin >> 1);
endmodule
"""
    tb = """`timescale 1ns/1ps
module tb_gray4;
    reg [3:0] bin; wire [3:0] gray;
    integer errors = 0, i;
    gray4 uut(.bin(bin), .gray(gray));
    initial begin
        for (i = 0; i < 16; i = i + 1) begin
            bin = i; #1;
            if (gray !== (i ^ (i >> 1))) begin
                $display("gray4:FAIL bin=%0d gray=%b", i, gray);
                errors = errors + 1;
            end
        end
        if (errors == 0) $display("gray4:PASS");
        else $fatal(1, "gray4:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def mult4() -> dict:
    top = "mult4"
    rtl = """`timescale 1ns/1ps
module mult4 (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [7:0] p
);
    assign p = a * b;
endmodule
"""
    tb = """`timescale 1ns/1ps
module tb_mult4;
    reg [3:0] a, b; wire [7:0] p;
    integer errors = 0, i, j;
    mult4 uut(.a(a), .b(b), .p(p));
    initial begin
        for (i = 0; i < 16; i = i + 1) begin
            for (j = 0; j < 16; j = j + 1) begin
                a = i; b = j; #1;
                if (p !== (i * j)) begin
                    $display("mult4:FAIL %0d*%0d=%0d", i, j, p);
                    errors = errors + 1;
                end
            end
        end
        if (errors == 0) $display("mult4:PASS");
        else $fatal(1, "mult4:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def debounce(width: int = 8) -> dict:
    w = int(width)
    maxv = (1 << w) - 1
    top = f"debounce{w}"
    rtl = f"""`timescale 1ns/1ps
module {top} (
    input  wire       clk,
    input  wire       rst,
    input  wire       din,
    output reg        dout
);
    reg [{w-1}:0] cnt;
    reg           prev;
    always @(posedge clk) begin
        if (rst) begin
            cnt <= 0; dout <= 1'b0; prev <= 1'b0;
        end else if (din != prev) begin
            prev <= din;
            cnt  <= 0;
        end else if (cnt != {maxv}) begin
            cnt <= cnt + 1'b1;
            if (cnt == {maxv} - 1) dout <= prev;
        end
    end
endmodule
"""
    tb = f"""`timescale 1ns/1ps
module tb_{top};
    reg clk = 0, rst = 0, din = 0;
    wire dout;
    integer errors = 0, i;
    {top} uut(.clk(clk), .rst(rst), .din(din), .dout(dout));
    always #5 clk = ~clk;
    initial begin
        rst = 1; repeat (2) @(posedge clk); #1; rst = 0;
        din = 1;
        for (i = 0; i < {maxv} - 1; i = i + 1) @(posedge clk);
        #1;
        if (dout !== 1'b0) begin
            $display("{top}:FAIL asserted too early");
            errors = errors + 1;
        end
        repeat (3) @(posedge clk); #1;
        if (dout !== 1'b1) begin
            $display("{top}:FAIL did not assert after debounce");
            errors = errors + 1;
        end
        if (errors == 0) $display("{top}:PASS");
        else $fatal(1, "{top}:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def stream_ctrl() -> dict:
    """Glue FSM: pop a byte, then one cycle later start the sink.

    The FIFO used here has a registered `dout` (it updates on the cycle
    *after* `rd`), so the start pulse must come one cycle after the pop.
    """
    top = "stream_ctrl"
    rtl = """`timescale 1ns/1ps
module stream_ctrl (
    input  wire clk,
    input  wire rst,
    input  wire empty,
    input  wire busy,
    output reg  start,
    output reg  rd
);
    localparam IDLE = 1'b0, POP = 1'b1;
    reg state;

    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            start <= 1'b0;
            rd    <= 1'b0;
        end else begin
            start <= 1'b0;
            rd    <= 1'b0;
            case (state)
                IDLE: if (!empty && !busy) begin
                    rd    <= 1'b1;
                    state <= POP;
                end
                POP: begin
                    start <= 1'b1;
                    state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
"""
    tb = """`timescale 1ns/1ps
module tb_stream_ctrl;
    reg clk = 0, rst = 0, empty = 1, busy = 0;
    wire start, rd;
    integer errors = 0;
    stream_ctrl uut(.clk(clk), .rst(rst), .empty(empty), .busy(busy),
                    .start(start), .rd(rd));
    always #5 clk = ~clk;
    initial begin
        rst = 1; empty = 1; busy = 0;
        @(posedge clk); #1; rst = 0;
        repeat (2) @(posedge clk); #1;
        if (start !== 1'b0 || rd !== 1'b0) begin
            $display("stream_ctrl:FAIL idle"); errors = errors + 1;
        end
        // byte available -> pop first
        empty = 0; busy = 0;
        @(posedge clk); #1;
        if (rd !== 1'b1 || start !== 1'b0) begin
            $display("stream_ctrl:FAIL expected pop"); errors = errors + 1;
        end
        // one cycle later the byte is on dout -> start the sink
        @(posedge clk); #1;
        if (start !== 1'b1 || rd !== 1'b0) begin
            $display("stream_ctrl:FAIL expected start"); errors = errors + 1;
        end
        busy = 1;
        @(posedge clk); #1;
        if (start !== 1'b0 || rd !== 1'b0) begin
            $display("stream_ctrl:FAIL pulse too long"); errors = errors + 1;
        end
        // busy sink -> no new pops
        repeat (3) @(posedge clk); #1;
        if (start !== 1'b0 || rd !== 1'b0) begin
            $display("stream_ctrl:FAIL retrigger while busy");
            errors = errors + 1;
        end
        // empty -> nothing
        empty = 1; busy = 0;
        repeat (3) @(posedge clk); #1;
        if (start !== 1'b0 || rd !== 1'b0) begin
            $display("stream_ctrl:FAIL fired while empty");
            errors = errors + 1;
        end
        if (errors == 0) $display("stream_ctrl:PASS");
        else $fatal(1, "stream_ctrl:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


def addsub(width: int = 4) -> dict:
    w = int(width)
    top = f"addsub{w}"
    rtl = f"""`timescale 1ns/1ps
module {top} (
    input  wire [{w-1}:0] a,
    input  wire [{w-1}:0] b,
    input  wire           sub,       // 0 = add, 1 = subtract
    output wire [{w-1}:0] y,
    output wire           carry,
    output wire           overflow
);
    wire [{w}:0] ext = sub ? ({{1'b0, a}} - {{1'b0, b}})
                           : ({{1'b0, a}} + {{1'b0, b}});
    assign y = ext[{w-1}:0];
    assign carry = ext[{w}];
    assign overflow = sub ? ((a[{w-1}] != b[{w-1}]) && (y[{w-1}] != a[{w-1}]))
                          : ((a[{w-1}] == b[{w-1}]) && (y[{w-1}] != a[{w-1}]));
endmodule
"""
    n = 1 << w
    tb = f"""`timescale 1ns/1ps
module tb_{top};
    reg [{w-1}:0] a, b;
    reg sub;
    wire [{w-1}:0] y;
    wire carry, overflow;
    integer errors = 0, i, j, s;
    reg [{w}:0] exp;
    reg exp_ov;
    {top} uut(.a(a), .b(b), .sub(sub), .y(y), .carry(carry),
              .overflow(overflow));
    initial begin
        for (i = 0; i < {n}; i = i + 1) begin
            for (j = 0; j < {n}; j = j + 1) begin
                for (s = 0; s < 2; s = s + 1) begin
                    a = i; b = j; sub = s; #1;
                    exp = s ? ({{1'b0, a}} - {{1'b0, b}})
                            : ({{1'b0, a}} + {{1'b0, b}});
                    exp_ov = s
                        ? ((a[{w-1}] != b[{w-1}]) && (exp[{w-1}] != a[{w-1}]))
                        : ((a[{w-1}] == b[{w-1}]) && (exp[{w-1}] != a[{w-1}]));
                    if (y !== exp[{w-1}:0] || carry !== exp[{w}]
                        || overflow !== exp_ov) begin
                        $display("{top}:FAIL a=%0d b=%0d sub=%0d y=%0d c=%b ov=%b",
                                 a, b, sub, y, carry, overflow);
                        errors = errors + 1;
                    end
                end
            end
        end
        if (errors == 0) $display("{top}:PASS");
        else $fatal(1, "{top}:FAIL");
        $finish;
    end
endmodule
"""
    return {"top": top, "rtl": rtl, "tb": tb}


GENERATORS = {
    "counter": counter,
    "alu": alu4,
    "alu4": alu4,
    "shiftreg": shiftreg,
    "fsm": fsm,
    "fsm3": fsm,
    "pwm": pwm,
    "uart_tx": uart_tx,
    "uart": uart_tx,
    "uart_rx": uart_rx,
    "comparator": comparator,
    "cmp": comparator,
    "fifo": fifo,
    "vga": vga_timing,
    "vga_timing": vga_timing,
    "regfile": regfile,
    "clkdiv": clkdiv,
    "bcd_counter": bcd_counter,
    "bcd": bcd_counter,
    "seg7": seg7,
    "seven_seg": seg7,
    "prio_enc8": prio_enc8,
    "priority_encoder": prio_enc8,
    "gray4": gray4,
    "gray": gray4,
    "mult4": mult4,
    "multiplier": mult4,
    "debounce": debounce,
    "stream_ctrl": stream_ctrl,
    "addsub": addsub,
    "adder_subtractor": addsub,
}

# reference-model blocks (RTL + independent Python model + generated TB)
from .lib2 import BLOCKS as _LIB2  # noqa: E402

GENERATORS.update(_LIB2)

# second batch: the catalogue failures, turned into deterministic blocks
from .lib3 import BLOCKS as _LIB3  # noqa: E402

GENERATORS.update(_LIB3)


def generate_block(kind: str, **params) -> dict:
    fn = GENERATORS.get((kind or "").lower())
    if not fn:
        raise ValueError(f"unknown block '{kind}'. known: "
                         f"{sorted(set(GENERATORS))}")
    return fn(**params)
