# TinyBrainBot production INT4 pair kernel: design and frozen trial plan

## Goal and scope

Keep genuine TinyBrainBot weights, tokenizer, context256, 4+8 shards and greedy
outputs unchanged. Optimize only the existing tile4 INT4 inner loop by decoding
both nibbles of each loaded byte and keeping each row's accumulation order.
Alternatives: lookup tables add memory traffic; vector/reordered reductions risk
different FP32 results. Select byte-pair scalar unrolling first. No retraining,
new model, external downloads, partition change or public transfer.

## Packages and acceptance

1. Core: add a small static INT4 four-row primitive; independent host tests of
   every packed byte, random non-binary FP32 inputs and production widths;
   exact scalar FP32 results required. Preserve generic INT8 and row tails.
   Compile a separate native DLL; preserve the archived DLL byte-for-byte.
   Run the complete suite redirected to the candidate DLL and compare genuine
   TinyBrainBot logits/output IDs with archived references.
2. Devices: first record both current 0.7.0 identities/readiness and idle queue.
   Warm W, then B1/B2 with16 output tokens, three repetitions per prompt, before
   and after0.9.0. Alternate prompt order by repetition. Both nodes cooperate
   in every request; do not claim independent per-board end-to-end speed.
   Baseline first/candidate second is explicitly not randomized; small timing
   differences remain descriptive. Compare coordinator and worker profile spans
   separately, including their memory/scheduling effects. No pure CPU claims.
   Firmware-only OTA worker then coordinator; keep model bytes unchanged.
   Run all12 retained quality cases on candidate, requiring token/text/EOS exact
   equality to archived native references. They are regression cases, not new
   independent quality observations. Preserve every response/failure.
3. Analysis: paired within-prefix baseline/candidate elapsed ratios, n=3 and
   min/max (not confidence intervals). Show separate board execution spans and
   TTFT. Scientific English report/figure, German journal, scoped local commit.

## Rollback and decision

Existing private0.7.0 rollback SHA256
`c867d87215cbee256fcf35213b8c539e4ed5d950e3beb2e063d36394e1bd6141`.
Any correctness failure: restore changed nodes to0.7.0 and run W reference.
Keep0.9.0 only if all host/device checks pass and both benchmark-prefix medians
are faster, with no >5% median regression in either board's recorded execution
span. Otherwise restore0.7.0 and report a negative result. No claim of statistical
significance, better language quality, energy or thermal benefit.

## Execution record

Starting HEAD473337b, clean worktree. Both genuine model roles live/readiness
checked over private LAN, firmware0.7.0, queue0/running0. User authorized the
optimization and physical two-board test in the current request and prior
autonomous research workflow. All work local; no subagents.
