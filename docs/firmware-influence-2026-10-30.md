# Scientific interpretation: firmware influence on the retained models

Publication note: commands in the historical report retain their original research scope and integrity guards. For this redacted archive, use `python tools/verify_public_snapshot.py .` to reproduce recorded tables without model weights, credentials or devices. Original experiment/native-DLL commands require the separately supplied pinned assets and original environment; they are not claimed runnable from this archive alone.

30 October 2026. Synthesis of existing recorded experiments, not a new device
trial, quality review or change to model weights. Firmware effects must be split
into execution speed, numerical correctness, deployable capacity and the visible
response boundary.

## Execution speed: a measured firmware intervention

The accepted production INT4 byte-pair kernel processes two packed weights per
byte and avoids repeated bit-width dispatch inside the column loop. It retains
the original per-row FP32 accumulation order; no fast-math/FMA contraction or
weight change was introduced by this optimization.

| TinyBrainBot workload, 16 output tokens | Baseline median | Firmware0.9.0 median | Reduction |
|---|---:|---:|---:|
| B1, four input tokens | 51.184253 s | 32.938759 s | about35.6% |
| B2, six input tokens | 55.422124 s | 35.668861 s | about35.6% |

The same two P4s and genuine model artifacts were used, with three repetitions
per prefix. The fixed baseline-then-candidate order was not randomized. This
supports a firmware-induced latency reduction for these workloads, not a
universal speedup, statistical confidence claim or measured energy benefit.
Supra2's roughly35.4% historical old/new difference is supporting context from
separate sessions, not an equally strong new same-session intervention.

Sources: [fresh Tiny before/after trial](int4-pair-2026-10-30.md) and
[same-kernel model comparison](supra-tiny-v09-2026-10-30.md).

## Numerical execution: preserve the model's answers, including mistakes

Conceptually, inference encodes a prompt, computes logits using retained weights
and KV state, and selects the next token by the unchanged greedy rule. Faster
execution does not train those weights. An implementation error, wrong
tokenizer or changed floating-point accumulation could nevertheless change the
selected token. Correctness therefore requires evidence beyond timing.

In the production-kernel trial, all27 real streams matched archived native token
IDs, full decoded text and EOS. Fourteen complete Tiny generations matched prior
references; eight full32000-logit vectors matched the candidate scalar-row path
byte-for-byte. Primitive INT4 arithmetic tests and the95-test suite passed in
that study. This is bounded evidence for preserved computation, not equivalence
for all prompts, all contexts or the unquantized source model. Later documentation
work did not rerun those experiments or silently enlarge their denominators.

The defensible conclusion is that the optimized kernel preserved the tested
answers while reducing runtime. Identical wrong answers remain wrong answers.

## Deployable capacity and tokenizer: enabling correct execution

Firmware implements model loading, tokenizer/decoder behavior, working-memory
allocation, KV handling and Ethernet layer exchange. The retained12-layer
models use coordinator layers0–3 plus tokenizer/embedding/output and worker
layers4–11. Each board must fit its own artifact and state; two32MiB memories do
not become one freely addressable64MiB allocation.

The real TinyBrainBot tokenizer port was checked against its pinned reference,
including5031 input-ID comparisons and64000 vocabulary-piece comparisons. This
enables a faithful input/output path within the tested domain; it is not a new
language skill learned through firmware. Lossless compressed storage can make
an artifact fit flash without changing its decompressed weights. These capacity
and implementation effects are distinct from training or lossy INT4 quantization.

Source: [tokenizer, artifacts and two-P4 acceptance](tinybrainbot-p4-2026-10-29.md).

## Visible answer quality: stopping policy changes what is observed

The cap experiment changed16→32 short-task tokens and48→96 story tokens while
keeping weights, native inputs, greedy decoding, context256 and firmware0.9.0
fixed. This was a request-level stopping-policy intervention, not another
firmware version comparison. All48 old token prefixes remained exact prefixes.

There were43 fresh quality streams, five explicitly reused early-EOS streams
and three fresh controls. One previously uncertain Tiny whole response became
confirmed clean; no previously confirmed failure became a success. Three other
uncertain responses became failures when their added claims became visible.
Supra gained no confirmed success. Both remained0/4 on exact format and0/4 on
strict story completion. A larger maximum cannot force generation beyond EOS.

Thus the response boundary can change a manual whole-answer judgment without
changing the underlying greedy trajectory. More visible text is neither new
knowledge nor automatically a better answer. The same-author review of known
questions was model-label-masked, not independent or fully blind.

Source: [paired cap study, full texts and costs](quality-cap-v3-2026-10-30.md).

## What remains unidentified

The recorded runtime checks do not determine how much weak answer quality is
caused by training, model capacity, quantization or prompt framing. Quantization
changes the represented weights and is a separate intervention from this
byte-pair execution optimization. A causal quality claim needs appropriately
matched source-versus-quantized or prompt-controlled comparisons. Faster kernels,
host/reference agreement and longer continuations cannot substitute for them.

For the retained artifacts and tested inputs, firmware substantially improved
execution efficiency and enabled larger genuine shards. The kernel intervention
did not demonstrate improved semantic quality; the cap intervention mainly
revealed more of the same trajectory. No power/thermal result or general
assistant qualification follows.
