# Supra2 and TinyBrainBot on the INT4 pair kernel: frozen research plan

## Scope and packages

Starting HEAD171fafb, firmware0.9.0, two physical P4 revision1.3 boards with
genuine TinyBrainBot 4+8 roles, ready/idle and empty sharded queue. No downloads,
model conversion, new dependencies, firmware build/update or partition change.
Local source/data work and authenticated private-LAN model installation/testing
are authorized by the current request. No external transfer or subagents.

1. Freeze this plan, protocol and trial script before new generations. Reuse the
   pinned genuine model artifacts, author-native prompt wrappers, 12 quality cases
   and B1/B2 speed prefixes from matched-p4-2026-10-30. Hash all inputs/artifacts.
   Preserve archived DLL and historical studies. Use the existing isolated0.9.0
   candidate DLL only after its source/binary hashes match the completed INT4 trial.
2. Host acceptance: all30 complete native generations must match the archived
   token IDs, input IDs, decoded text and EOS; compare eight complete logit vectors
   per model between tile4 and scalar rows, requiring exact FP32 bytes. No new
   answer selection/scoring or optimization after inspecting results.
3. Device trial: fresh TinyBrainBot warmup4 plus B1/B2 cap16, three repetitions
   each. Load genuine Supra worker then coordinator, reconfigure the model-bound
   cluster peer, verify roles/identities/memory. Fresh Supra warmup4 and the same
   six timing requests, alternating prefix order by repetition. Run all12 Supra
   quality cases with their original caps24/48. Every actual stream must match
   its frozen model-specific reference. No inference retry; preserve failures.
   In finally restore genuine TinyBrainBot roles, reconfigure peer, run W cap4,
   verify both ready/idle on0.9.0 and queue0/running0. Keep exact private artifacts
   for recovery; do not switch firmware or change model format.
4. Offline analysis: audit all27 fresh streams (12 timing, two warmups,12 Supra
   quality, one restoration). Incorporate the previous12 actual TinyBrainBot
   quality streams from int4-pair-2026-10-30, explicitly labelled REUSED and
   authenticated by hashes; they are not new observations. Transfer the existing
   unblinded quality judgments only after text/ID/EOS equality is established.
   English report, side-by-side response viewer, PNG/SVG figures and source
   hashes; German journal and scoped local commit. Fresh suite95 must pass.

## Comparison and limitations

Both models use firmware0.9.0, tile4/byte-pair INT4, full vocabularies, FP32 KV,
context256, 4+8 roles and both HP cores per board. Same raw speed-prefix bytes,
input counts4/6 and16 capped output tokens; model vocabularies and generated
words differ. Quality wrappers are model-native, not identical prompt bytes.

To avoid extra flash cycles, model order is Tiny then Supra then restore Tiny.
This fixed order is not randomized/interleaved. Index-matched timing ratios are
descriptive, not independent randomized pairs or significance tests. Report
medians and observed min/max for n=3; tiny differences do not establish a winner.
Historical0.7.0 times may be shown separately as historical measurements, not
a fresh same-session old-kernel causal control. The previous Tiny kernel trial
provides that separate within-model intervention evidence for Tiny only.

Quality counts are retained judgments on a familiar small fixed sample, not a
new benchmark, blind review or general model ranking. Reused Tiny output times
are not fresh latency measurements and are excluded from the new timing sample.
Report coordinator/worker execution spans separately; they include memory stalls
and scheduling. RPC total already contains worker execution and must not be added
again. No energy, thermal, measured clock, third-node or statistical claim.

## Acceptance and recovery

Any host mismatch blocks device writes. Any device mismatch/failure aborts further
inference and triggers Tiny restoration. Successful conclusion requires all27
fresh streams plus12 reused streams verified, true Tiny model/artifact IDs back
on both boards, firmware0.9.0, ready/idle, queue empty, fresh95-test suite and
offline evidence audit. No upload/push/publication is included.
