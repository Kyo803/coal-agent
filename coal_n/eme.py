"""Expert Memory Echo (EME) routing with hysteresis, MVP-simplified.

Proposal sec 2.3: router remembers which expert handled the previous step
(logit bonus `lamsq` for the incumbent) unless the SHARED surprise score S
crosses the threshold — then it re-evaluates all experts from scratch.

MVP wiring (see stream.py): S is the exact same scalar the FOU layer
reports. One threshold knob drives firing (FOU), re-lock (PLHE) and
re-routing (EME).

Compute story per step:
  S <= threshold : reuse previous expert, skip the gate entirely.
                   Cost = 1 expert (N mult-adds).
  S >  threshold : evaluate gate + hysteresis bonus, then evaluate ALL
                   experts and mix by softmax weights ("spike to full
                   capacity only on event").
Baseline evaluates the gate + all experts every step.
"""
import math
import torch
import torch.nn as nn


class EchoRouter(nn.Module):
    def __init__(self, in_dim: int, hidden_dim: int, n_experts: int = 4,
                 lam: float = 2.0):
        super().__init__()
        self.n_experts = n_experts
        self.lam = lam
        self.gate = nn.Linear(in_dim, n_experts, bias=True)
        self.experts = nn.ModuleList(
            nn.Linear(hidden_dim, 1, bias=True) for _ in range(n_experts))
        self.prev_expert = None       # incumbent expert index (the "echo")
        self.gate_evals = 0           # steps where the gate was evaluated
        self.step_count = 0
        self.expert_evals = 0         # total expert evaluations

    def reset(self):
        self.prev_expert = None
        self.gate_evals = 0
        self.step_count = 0
        self.expert_evals = 0

    @torch.no_grad()
    def forward(self, feat: torch.Tensor, h_t: torch.Tensor,
                surprise: float, threshold: float):
        """feat: [D+4] router input; h_t: [N] FOU hidden state for experts.
        Returns (logit, expert_id, reevaluated)."""
        self.step_count += 1
        if self.prev_expert is not None and surprise <= threshold:
            # Echo: keep incumbent, skip gate math completely.
            e = self.prev_expert
            logit = self.experts[e](h_t).squeeze()
            self.expert_evals += 1
            return float(logit), int(e), False

        # Surprise (or first step): full re-evaluation from scratch.
        self.gate_evals += 1
        logits = self.gate(feat)  # [E]
        if self.prev_expert is not None:
            logits[self.prev_expert] += self.lam  # hysteresis bonus
        weights = torch.softmax(logits, dim=0)
        outs = torch.stack([ex(h_t).squeeze() for ex in self.experts])  # [E]
        self.expert_evals += self.n_experts
        mixed = (weights * outs).sum()
        top = int(torch.argmax(weights))
        self.prev_expert = top
        return float(mixed), top, True

    def gate_fraction(self) -> float:
        if self.step_count == 0:
            return 0.0
        return self.gate_evals / self.step_count

    def expert_fraction(self) -> float:
        """Mean experts evaluated per step (dense baseline = n_experts)."""
        if self.step_count == 0:
            return 0.0
        return self.expert_evals / self.step_count


@torch.no_grad()
def dense_baseline_step(gate, experts, feat: torch.Tensor,
                        h_dense: torch.Tensor) -> float:
    """Reference: gate + ALL experts every step, softmax mix."""
    logits = gate(feat)
    weights = torch.softmax(logits, dim=0)
    outs = torch.stack([ex(h_dense).squeeze() for ex in experts])
    return float((weights * outs).sum())
