// MERIDIAN-16 reference: 64K x 16 synchronous static RAM.
// Byte-enable writes on posedge; combinational read gated by oe (tri-state).
module mem64k (
    input clk,
    input [15:0] addr,
    input [15:0] din,
    input we,
    input [1:0] be,
    input oe,
    output reg [15:0] dout
);
    reg [15:0] ram [0:65535];

    always @(posedge clk) begin
        if (we) begin
            if (be[0]) ram[addr][7:0]   <= din[7:0];
            if (be[1]) ram[addr][15:8]  <= din[15:8];
        end
    end

    always @* begin
        dout = oe ? ram[addr] : 16'bz;
    end
endmodule