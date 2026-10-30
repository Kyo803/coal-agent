from builder import generator as G

SYS_MINE = {"role": "system",
            "content": "You are Coal's builder. Write a single Verilog "
                       "file. Output ONLY the file contents in one code "
                       "block, no prose."}
U = {"role": "user",
     "content": "FILE: mem64k.v\nSTACK: hdl\nMUST EXPORT: []\nIMPORTS: []"
                "\n\nSPEC:\nsync 64Kx16 RAM; PORTS: input clk, input "
                "[15:0] addr, input [15:0] din, input we, input [1:0] be, "
                "input oe, output [15:0] dout\n\nCONTEXT: verilog"}
U2 = {"role": "user",
      "content": "write module mem64k(clk, addr, din, we, be, oe, dout) "
                 "with addr [15:0], dout [15:0]. Emit code now."}

print("mine+that_user:", len(G._chat([SYS_MINE, U], max_tokens=2000,
                                     temperature=0.2)))
print("mine+simple_user:", len(G._chat([SYS_MINE, U2], max_tokens=2000,
                                       temperature=0.2)))
print("G._SYS+that_user:", len(G._chat([{"role": "system",
                                         "content": G._SYS}, U],
                                       max_tokens=2000, temperature=0.2)))