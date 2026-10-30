// MERIDIAN-16 reference testbench: strict behavioral check.
`timescale 1ns / 1ps
module tb_mem;
    reg clk = 0;
    reg [15:0] addr;
    reg [15:0] din;
    reg we;
    reg [1:0] be;
    reg oe;
    wire [15:0] dout;

    mem64k uut (.clk(clk), .addr(addr), .din(din), .we(we),
                .be(be), .oe(oe), .dout(dout));

    integer __errors = 0;
    always #5 clk = ~clk;

    task step;
        input [15:0] a, d;
        input [1:0] b;
        input w, o;
        begin
            addr = a; din = d; be = b; we = w; oe = o;
            @(posedge clk);
            #1;
        end
    endtask

    initial begin
        // write 16'h1234 to addr 0, both bytes
        step(16'h0000, 16'h1234, 2'b11, 1'b1, 1'b1);
        we = 0;
        addr = 16'h0000; oe = 1'b1; #1;
        if (dout !== 16'h1234) begin $display("FAIL addr0=%h", dout); __errors = __errors + 1; end

        // zero addr1 first so the unselected low byte is a known 0
        step(16'h0001, 16'h0000, 2'b11, 1'b1, 1'b1);
        // write 16'hABCD to addr 1 with be=2'b10 (high byte only) -> AB00
        step(16'h0001, 16'hABCD, 2'b10, 1'b1, 1'b1);
        we = 0;
        addr = 16'h0001; oe = 1'b1; #1;
        if (dout !== 16'hAB00) begin $display("FAIL addr1=%h", dout); __errors = __errors + 1; end

        // tri-state when oe=0
        oe = 1'b0; #1;
        if (dout !== 16'bz) begin $display("FAIL not high-z %h", dout); __errors = __errors + 1; end

        if (__errors == 0)
            $display("MERIDIAN:PASS");
        else
            $fatal(1);
        $finish;
    end
endmodule