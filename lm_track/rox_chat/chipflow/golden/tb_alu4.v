// Self-checking testbench for alu4. Prints alu4:PASS or fails hard.
`timescale 1ns/1ps
module tb_alu4;
    reg  [3:0] a, b;
    reg  [2:0] op;
    wire [3:0] y;
    wire       zero;
    integer errors = 0;

    alu4 uut (.a(a), .b(b), .op(op), .y(y), .zero(zero));

    task check(input [3:0] ea, input ez);
        begin
            if (y !== ea || zero !== ez) begin
                $display("alu4:FAIL a=%0d b=%0d op=%0d got=%0d exp=%0d",
                         a, b, op, y, ea);
                errors = errors + 1;
            end
        end
    endtask

    initial begin
        a = 4'd3;  b = 4'd5;  op = 3'd0; #1; check(4'd8,  1'b0);
        a = 4'd3;  b = 4'd5;  op = 3'd1; #1; check(4'd14, 1'b0);
        a = 4'd6;  b = 4'd6;  op = 3'd1; #1; check(4'd0,  1'b1);
        a = 4'b1010; b = 4'b1100; op = 3'd2; #1; check(4'b1000, 1'b0);
        a = 4'b1010; b = 4'b1100; op = 3'd3; #1; check(4'b1110, 1'b0);
        a = 4'b1010; b = 4'b1100; op = 3'd4; #1; check(4'b0110, 1'b0);
        a = 4'b1010; b = 4'b0000; op = 3'd5; #1; check(4'b0101, 1'b0);
        a = 4'b1010; b = 4'b0000; op = 3'd6; #1; check(4'b0100, 1'b0);
        a = 4'b1010; b = 4'b0000; op = 3'd7; #1; check(4'b0101, 1'b0);
        if (errors == 0) $display("alu4:PASS");
        else $fatal(1, "alu4:FAIL (errors=%0d)", errors);
        $finish;
    end
endmodule
