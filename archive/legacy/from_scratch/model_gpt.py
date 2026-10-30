"""Tiny GPT from scratch: byte-level vocab (256), learned absolute positions.
~0.9M params at defaults. Standard decoder-only transformer, no tricks —
the point is the weights are learned here, not downloaded.
"""
import math

import torch
import torch.nn as nn


class Block(nn.Module):
    def __init__(self, d, heads, ffn):
        super().__init__()
        self.ln1 = nn.LayerNorm(d)
        self.attn = nn.MultiheadAttention(d, heads, batch_first=True)
        self.ln2 = nn.LayerNorm(d)
        self.mlp = nn.Sequential(nn.Linear(d, ffn), nn.GELU(),
                                 nn.Linear(ffn, d))

    def forward(self, x):
        T = x.shape[1]
        mask = torch.triu(torch.ones(T, T, dtype=torch.bool,
                                     device=x.device), diagonal=1)
        a, _ = self.attn(self.ln1(x), self.ln1(x), self.ln1(x),
                         attn_mask=mask)
        x = x + a
        return x + self.mlp(self.ln2(x))


class TinyGPT(nn.Module):
    def __init__(self, vocab=256, ctx=128, d=128, layers=4, heads=4,
                 ffn=512):
        super().__init__()
        self.ctx = ctx
        self.tok = nn.Embedding(vocab, d)
        self.pos = nn.Embedding(ctx, d)
        self.blocks = nn.Sequential(*[Block(d, heads, ffn)
                                      for _ in range(layers)])
        self.ln = nn.LayerNorm(d)
        self.head = nn.Linear(d, vocab, bias=False)
        self.apply(self._init)

    @staticmethod
    def _init(m):
        if isinstance(m, (nn.Linear, nn.Embedding)):
            nn.init.normal_(m.weight, std=0.02)

    def forward(self, idx):
        B, T = idx.shape
        x = self.tok(idx) + self.pos(torch.arange(T, device=idx.device))
        return self.head(self.ln(self.blocks(x)))

    def n_params(self):
        return sum(p.numel() for p in self.parameters())


def encode(s: str):
    return list(s.encode("utf-8", errors="ignore"))


def decode(ids):
    return bytes([b for b in ids if 0 <= b < 256]).decode(
        "utf-8", errors="ignore")


@torch.no_grad()
def sample(model, prompt, n_new=120, temp=0.8):
    model.eval()
    ids = encode(prompt)[-model.ctx:]
    out = list(ids)
    for _ in range(n_new):
        x = torch.tensor([out[-model.ctx:]])
        logits = model(x)[0, -1] / max(temp, 1e-6)
        probs = torch.softmax(logits, dim=-1)
        out.append(int(torch.multinomial(probs, 1)))
    return decode(out)
