"""A small library of composed chips.

Each entry wires verified blocks together and ships a self-checking system
testbench. These are the deterministic shapes Coal can build end-to-end
today; the model picks between them (or proposes a graph for validation),
it never writes the RTL.

    from chipflow.compositions import get, names
    build_composition(get("uart_loopback"))
"""
from __future__ import annotations

from .compose import Composition


# ---------------------------------------------------------------- counter_cmp
_COUNTER_CMP_TB = """`timescale 1ns/1ps
module tb_counter_cmp;
    reg clk = 0, rst = 0, en = 0;
    reg [7:0] threshold = 0;
    wire gt, lt, eq;
    integer errors = 0, i;
    counter_cmp uut(.clk(clk), .rst(rst), .en(en), .threshold(threshold),
                    .gt(gt), .lt(lt), .eq(eq));
    always #5 clk = ~clk;
    initial begin
        rst = 1; en = 0; threshold = 8'd5;
        @(posedge clk); #1;
        if (gt !== 1'b0 || lt !== 1'b1 || eq !== 1'b0) begin
            $display("counter_cmp:FAIL reset gt=%b lt=%b eq=%b", gt, lt, eq);
            errors = errors + 1;
        end
        rst = 0; en = 1;
        for (i = 1; i <= 10; i = i + 1) begin
            @(posedge clk); #1;
            if (gt !== ((i > 5) ? 1'b1 : 1'b0)
             || lt !== ((i < 5) ? 1'b1 : 1'b0)
             || eq !== ((i == 5) ? 1'b1 : 1'b0)) begin
                $display("counter_cmp:FAIL i=%0d gt=%b lt=%b eq=%b",
                         i, gt, lt, eq);
                errors = errors + 1;
            end
        end
        en = 0;
        repeat (2) @(posedge clk); #1;
        if (gt !== 1'b1 || lt !== 1'b0 || eq !== 1'b0) begin
            $display("counter_cmp:FAIL hold gt=%b lt=%b eq=%b", gt, lt, eq);
            errors = errors + 1;
        end
        if (errors == 0) $display("counter_cmp:PASS");
        else $fatal(1, "counter_cmp:FAIL");
        $finish;
    end
    initial begin
        #50000;
        $display("counter_cmp:FAIL timeout");
        $fatal(1, "counter_cmp timeout");
    end
endmodule
"""


def counter_cmp() -> Composition:
    c = Composition("counter_cmp")
    c.add("cnt", "counter", width=8)
    c.add("cmp", "comparator", width=8)
    c.clk().rst()
    c.bus(None, ["cnt.en"], name="en", top_dir="input")
    c.bus(None, ["cmp.b"], name="threshold", width=8, top_dir="input")
    c.connect("cnt.q", "cmp.a", name="q")
    c.net("gt", 1, driver="cmp.gt", top_dir="output")
    c.net("lt", 1, driver="cmp.lt", top_dir="output")
    c.net("eq", 1, driver="cmp.eq", top_dir="output")
    c.tb = _COUNTER_CMP_TB
    c.description = "8-bit counter feeding a magnitude comparator"
    return c


# --------------------------------------------------------------- uart_loopback
_UART_LOOPBACK_TB = """`timescale 1ns/1ps
module tb_uart_loopback;
    reg clk = 0, rst = 1;
    reg serial_in = 1;
    wire serial_out;
    integer errors = 0;
    reg [7:0] got;
    localparam CPB = 16;

    uart_loopback uut(.clk(clk), .rst(rst), .serial_in(serial_in),
                      .serial_out(serial_out));
    always #5 clk = ~clk;

    task send_byte(input [7:0] b);
        integer k;
        begin
            @(negedge clk); serial_in = 1'b0;          // start bit
            repeat (CPB) @(negedge clk);
            for (k = 0; k < 8; k = k + 1) begin
                serial_in = b[k];
                repeat (CPB) @(negedge clk);
            end
            serial_in = 1'b1;                          // stop bit
            repeat (CPB) @(negedge clk);
        end
    endtask

    task recv_byte(output [7:0] b);
        integer k;
        begin
            @(negedge serial_out);                     // start bit
            repeat (CPB + CPB/2) @(posedge clk);       // middle of bit 0
            for (k = 0; k < 8; k = k + 1) begin
                b[k] = serial_out;
                repeat (CPB) @(posedge clk);
            end
        end
    endtask

    initial begin
        rst = 1; serial_in = 1;
        repeat (3) @(posedge clk);
        #1 rst = 0;
        fork
            send_byte(8'h5A);
            recv_byte(got);
        join
        if (got !== 8'h5A) begin
            $display("uart_loopback:FAIL got=%h exp=5A", got);
            errors = errors + 1;
        end
        if (errors == 0) $display("uart_loopback:PASS");
        else $fatal(1, "uart_loopback:FAIL");
        $finish;
    end
    initial begin
        #200000;
        $display("uart_loopback:FAIL timeout");
        $fatal(1, "uart_loopback timeout");
    end
endmodule
"""


def uart_loopback() -> Composition:
    """uart_rx -> fifo -> uart_tx: a byte sent in comes back out."""
    c = Composition("uart_loopback")
    c.add("rx", "uart_rx")
    c.add("fifo", "fifo", width=8, depth=8)
    c.add("tx", "uart_tx")
    c.add("ctl", "stream_ctrl")
    c.clk().rst()

    c.bus(None, ["rx.rx"], name="serial_in", top_dir="input")
    c.net("serial_out", 1, driver="tx.tx", top_dir="output")

    c.connect("rx.data", "fifo.din", name="rx_data")
    c.connect("rx.valid", "fifo.wr", name="rx_valid")
    c.connect("fifo.dout", "tx.data", name="tx_data")
    c.connect("fifo.empty", "ctl.empty", name="fifo_empty")
    c.connect("tx.busy", "ctl.busy", name="tx_busy")
    c.connect("ctl.start", "tx.start", name="tx_start")
    c.connect("ctl.rd", "fifo.rd", name="fifo_rd")
    c.tb = _UART_LOOPBACK_TB
    c.description = "UART loopback: receive a byte into a FIFO, transmit it back"
    return c


# ------------------------------------------------------------------- registry
REGISTRY = {
    "counter_cmp": counter_cmp,
    "uart_loopback": uart_loopback,
}


def names() -> list:
    return sorted(REGISTRY)


def get(name: str) -> Composition:
    key = (name or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key not in REGISTRY:
        raise KeyError(f"unknown composition {name!r}; known: {names()}")
    return REGISTRY[key]()


def match(spec: str) -> Composition | None:
    """Pick a composition from a free-text spec (deterministic fallback)."""
    low = (spec or "").lower()
    if ("uart" in low or "serial" in low) and (
            "loop" in low or "echo" in low or "bridge" in low):
        return uart_loopback()
    if "comparator" in low and ("counter" in low or "count" in low):
        return counter_cmp()
    return None


_BLOCK_WORDS = ("uart", "serial", "fifo", "buffer", "counter", "count",
                "comparator", "compare", "alu", "shift", "regfile",
                "register file", "pwm", "vga", "fsm", "state machine",
                "debounce", "encoder", "decoder", "multiplier", "clkdiv",
                "divider", "arbiter", "spi")

_MARKERS = ("loopback", "echo", "pipeline", "chain", "soc", "subsystem",
            "buffer", "buffers", "feed", "feeds", "into a fifo", "->", "-->",
            "wired to", "and then", "plus")


def looks_composed(spec: str) -> bool:
    """True when a spec clearly asks for several blocks wired together."""
    low = (spec or "").lower()
    words = sum(1 for w in _BLOCK_WORDS if w in low)
    return words >= 2 and any(m in low for m in _MARKERS)
