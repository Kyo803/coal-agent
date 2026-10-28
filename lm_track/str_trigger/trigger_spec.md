# STR trigger, redesigned from measurement (not from intuition)

## The problem with the draft design

The resilience plan triggers retrieval on input-side surprise S_t ("model
is in unfamiliar territory"). Measured on a real LM (SmolLM2-135M-Instruct,
36 factual questions, `lm_track/str_trigger/`, reproducible via
`measure.py` + `analyze.py`):

| signal | side | AUROC for P(answer is wrong) |
|---|---|---|
| min token prob of the draft (FLARE-style) | output | **0.84** |
| mean logprob of the draft | output | 0.83 |
| multi-sample disagreement (3 extra samples) | output | **0.85** |
| input novelty, i.e. −mean prompt logprob (**S_t analog**) | input | **0.54 ≈ chance** |

5 of 12 wrong answers came from above-median-familiarity inputs: the
question feels unsurprising, the answer is still wrong. An input-novelty
trigger at median threshold misses all five. This is the same class the
literature calls confabulation — fluent, arbitrary, seed-sensitive wrong
answers (Farquhar et al., Nature 2024) — and no input-side threshold can
catch it, because there is nothing surprising on the input side.

FLARE (Jiang et al., EMNLP 2023) got this right from the start: trigger on
the *upcoming output's* low-confidence tokens, and they further show
retrieval when confident can *hurt* (StrategyQA drops past 50% retrieval
rate) — so over-triggering has a quality cost, not just a latency cost.

## Redesigned trigger (two stages + domain policy)

- **Stage 1 — cheap gate (already paid for):** draft the span in the normal
  forward pass. S_t is free (computed anyway); min token prob is free
  (logits already exist). Candidate iff `min_prob < θ1` — S_t may widen the
  gate (`OR S_t > θs`) but must never narrow it: output-side carries.
- **Stage 2 — consistency check (bounded cost):** only for candidates, draw
  2 extra samples of the span; retrieve iff they disagree with the draft
  (discrete semantic-entropy family: exact-match clustering suffices for
  short spans). Cost is capped at `2 × span_len` tokens, and only on the
  Stage-1 candidate fraction (~70% here, lower with tuned θ1).
- **Domain policy (not a threshold):** systematic-error spans (medical,
  legal, or any low-disagreement-but-high-stakes class) retrieve always.
  Thresholds cannot catch confident-and-wrong; policy can.
- **Query formulation:** mask low-confidence draft tokens before embedding
  the query (FLARE §β-masking); symmetrically, S_t keeps one honest job
  here — masking low-surprise boilerplate so it doesn't dilute the query.

## Fallbacks (unchanged from the resilience plan)

Retrieval-miss → trained honest-uncertainty response; index down →
unverified flag, never silent confident recall; tool-failure and memory
rules untouched. The fallback hierarchy (resilience §7) still governs
multi-failure cases; only the *trigger* changes, not the failure behavior.

## Calibration protocol (replaces "train a calibration head and hope")

1. Extend `qa_set.json` to ~200 mixed-domain factual questions.
2. Run `measure.py`; report AUROC + retrieval-rate/precision table from
   `analyze.py` (same metrics as above, no new code needed).
3. Pick θ1 at the knee: cheapest retrieval rate with recall ≥ 0.9 on the
   calibration split; freeze; verify on a held-out split.
4. Re-run per model scale — thresholds do not transfer across sizes.
5. The calibration head (resilience §3) is then optional descope: ship the
   two-stage rule first; add a learned head only if it beats min_prob +
   disagreement on held-out AUROC by a margin worth its training cost.

## What S_t keeps

S_t stays exactly where it is validated: FOU firing, EME routing, PLHE
re-lock, TME compression scoring. It is a novelty signal, and novelty is
the right trigger for compute and memory decisions. It was never a
measure of truthfulness, and the numbers above say to stop asking it
to be one.
