# Output-cap sensitivity V3: prospective plan

**Goal:** Determine whether doubling output caps improves the visible answers to
the same 24 English questions on the same two physical P4s, without changing
model, tokenizer, native wrapper, greedy rule, context, split or firmware.

**Architecture:** Reuse the accepted local native DLL and device-switch helpers;
write an isolated recording/analysis tool and new data. The historical qualityV2
protocol, raw streams and ratings are immutable controls. Native execution is
reference evidence, not independent evidence of semantic correctness.

**Scope:** User-authorized local host and private-LAN model switching/inference;
no downloads, dependency installs, firmware builds/writes, partition changes,
online transfer, subagents or unrelated planning changes. Genuine TinyBrainBot
must be restored after either success or a device failure.

## Packages, paths and checks

1. Freeze this plan, `tools/quality_cap_v3_trial.py` and new protocol under
   `docs/research/data/quality-cap-v3-2026-10-30/` before any higher-cap answer.
   Pin baseline protocol/references/ratings/raw-stream hashes, source/artifact/DLL
   hashes, exact old inputs/order, and a fresh balanced A/B mapping commitment.
   Validate all 51 historical streams and old completion/restoration evidence.
2. Generate 48 new local higher-cap references and two known four-token controls.
   Short caps change 16 to 32; stories change 48 to 96. Assert every old output
   token sequence is an exact prefix of its longer reference. Assert the five
   old EOS answers remain completely equal, including EOS. Context remains 256;
   each input-length plus cap minus one must fit. No answer-dependent selection.
3. Record the 43 formerly capped answers on the actual P4 pair, Tiny first then
   Supra, in the same round-robin category order. Both HP cores per board, tile4
   production byte-pair INT4, full vocabulary, FP32 KV/scales/norms, 4+8 layers,
   firmware0.9.0, same physical hardware. Validate token IDs, decoded full text,
   EOS, prompt/output counts and reported two-board/core masks against references.
   Check the old capped visible bytes using the corresponding new raw prefix.
   The five verified early-EOS Tiny outputs are explicitly reused actual prior
   device streams: R03, I01, G01, G02 and U02. Never label them new trials.
   Two warmups plus one restoration control make 46 new physical streams.
   Maximum new hardware output budget:1900 tokens (1888 quality plus12 controls).
   Higher-cap evaluation covers48 answers; old comparison answers also remain
   historical evidence. No retry or second quality sample. Failure aborts new
   jobs; finally reload true Tiny roles, configure peer, verify W and ready/idle,
   firmware0.9.0, empty queue. Model writes only when role identity differs.
4. After recording/restoration, create48 higher-cap outputs with A/B model labels,
   no model names, token IDs, native wrappers or timing; caps/EOS stay visible.
   Score using the unchanged qualityV2 rubric below. Commit new ratings before
   unsealing the new mapping. The author knows old questions/answers/ratings and
   model styles: this is not independent or fully blind, nor cap-blinded review.
   Do not revise old ratings. Unseal, audit, compare paired low/high outcomes per
   model/category, report regressions and uncertainty alongside improvements.
   Produce English report/full-output viewer/comparison and setup figures, German
   journal, verification receipt and scoped local commit. No publication step.

## Unchanged semantic rubric and causal limits

Use exactly the expected criteria of each qualityV2 case. For facts, reasoning,
context and missing-information tasks, `core` refers to the first responsive
answer. A later correction cannot erase an earlier wrong answer. An old non-answer
may acquire its first actual answer later; evaluate that answer as written.
`clean` evaluates the entire visible response: true only if it satisfies the
question without material false/unsupported assertions, contradiction or drift;
null for genuine semantic ambiguity or an unfinished possibly material claim.
Keep null distinct from both confirmed success and failure. Repetition by itself
is not an invented strict length rule; drifting content or false claims can fail.

Exact-format cases use case-sensitive literal equality after outer Unicode
whitespace stripping only. Stories separately score full topic/roles/actions,
absence of material contradiction, visible requested resolution and exactly two
sentences; strict completion requires all four. A third unfinished fragment fails
two-sentence format. No arbitrary stylistic/realism additions. EOS is not a story
resolution. Existing old scores remain frozen even when interpretation is hard.

The prospective intervention is only the output stopping cap. Exact deterministic
prefix checks distinguish extra visible continuation from a changed engine/input.
Greedy trajectories are not independent samples. Fixed Tiny-then-Supra order,
different model-native wrappers/tokenizers, n=4/category, possible pretraining
overlap, known previous outputs and same-author review limit inference. Questions
were not newly held out for V3. No aggregate best-model score, significance test,
general assistant qualification, source-FP32 fidelity or causal attribution of
quality to training/quantization. Longer-cap wall time uses more work; no isolated
kernel-speed or energy-efficiency claim. No unseen continuation beyond96 assumed.

## Review focus and acceptance

- Premature EOS: complete reference equality plus old physical-stream audit is
  required before five reuses; higher limits cannot force a model past EOS.
- Cap-bound multibyte decoding: compare token IDs and decoded original raw byte
  prefix; do not require replacement-character text to be a Unicode substring.
- Context headroom: freeze exact token lengths and reject overflow, no truncation.
- Visible first-answer errors versus later correction: retain prefix and assess
  whole continuation; expose case notes and separate core/clean/uncertain counts.
- Device interruption/restoration: no repeated trial presented as fresh success;
  preserve failures and finally verify genuine Tiny identities and queue idle.

Completion requires43 new quality streams, five explicitly identified prior EOS
streams, three new controls, all runtime/reference and old-prefix checks, committed
label-masked ratings before mapping disclosure, paired descriptive arithmetic,
complete raw outputs, reviewed figures and final Tiny restoration. Existing code
and published snapshots stay byte-identical; unrelated untracked files untouched.
