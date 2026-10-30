// ROX N golden reference: 4-bit ALU with zero flag.
`timescale 1ns/1ps
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
