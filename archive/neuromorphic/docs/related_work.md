# Related work — precise positioning (final product)

Claim discipline: the defensible contribution is the **one shared surprise
signal driving embedding (PLHE), firing (FOU) and routing (EME) together
with a hard per-step compute ceiling**. Each piece alone has prior art,
cited below. No "first ever" claims beyond that combination.

## Per-component prior art

| Coal piece | Closest prior art | Distinction |
|---|---|---|
| PLHE (freq-adaptive embedding) | Rotary position embeddings, RoPE (Su et al., 2021); hyperspherical embeddings | RoPE uses fixed rotation rates as a position code; PLHE derives the rate from the signal itself, integrated as phase (no jumps) |
| FOU hard top-k budget | Early-exit nets: BranchyNet (Teerapittayanon, McDanel & Kung, ICPR 2016); SkipNet (Wang et al., CVPR 2018); BlockDrop (Wu et al., 2018) | Early-exit is layer-level and input-independent once trained; FOU is neuron-level with a hard global per-step ceiling |
| FOU caching | Neural memoization / activation memoization (e.g. Deep Reuse literature); event-based sensing | Same reuse intuition, applied per-unit with a shared budget |
| Spiking comparison | Leaky integrate-and-fire SNNs (see e.g. Tavanaei et al., Neural Networks 2019 review) | FOUs are rate-coded ReLU units with cache-gating, not temporal spike codes; no surrogate-gradient training needed |
| EME hysteresis routing | Switch Transformer (Fedus, Zoph & Shazeer, arXiv:2101.03961, JMLR 2022); Mixtral 8x7B (Jiang et al., arXiv:2401.04088, 2024) | Both route statelessly per token; EME adds an incumbent bonus + surprise-forced full re-evaluation |
| Conditional compute generally | Adaptive Computation Time (Graves, 2016); Runtime Neural Pruning (Lin et al., 2017) | Same family; Coal's ceiling is per-step hard (latency guarantee), not amortised |
| Threshold learning | Sparsity penalties / L0 regularisation (Louizos et al., 2018) | Same mechanism (soft gate + sparsity loss); applied to a deployment threshold, not weights |

## What would strengthen this into a publication

1. Beat-aligned evaluation on MIT-BIH with the official train/test split
   (our record-100 slice + synthetic fallback is prototype-grade).
2. Wall-clock comparison on target silicon (our ms numbers are CPython;
   see docs/edge_checklist.md).
3. Ablations: shared-S vs three independent signals (the core claim
   predicts shared wins on stability: fewer expert flaps, fewer PLHE
   re-locks at equal F1).
