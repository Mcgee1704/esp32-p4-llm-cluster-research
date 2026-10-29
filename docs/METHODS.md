# Methods, timing definitions and limitations

## Fixed numerical reference

The original model is Karpathy's trained TinyStories-15M checkpoint, pinned in
`tools/fetch_model.py`. The P4LM representation uses symmetric INT8 matrix weights
and one FP32 scale per row. Norms, activations and KV are FP32. Dimensions:
288 embedding, 768 feed-forward, 6 layers, 6 query/KV heads, vocabulary 32,000,
context 256. The artifact is 15,836,365 bytes, including a 433,869-byte tokenizer.
Its model ID is `5a87778471464024a58c793dac66fedca10ad169f90d1691f642fd05dc6bd18a`.

Greedy decoding and exact token IDs are used for deterministic regression
comparisons. Numerical tests use a separate small NumPy reference, including
RoPE, GQA, KV positions, corrupted-model rejection and split-layer equivalence.
Host-only times are never called P4 performance measurements.

## Timing domains

- `master_compute_ms`: local embedding, layers, output projection and argmax,
  including task interruptions/waits inside the measured interval.
- `worker_compute_ms`: worker-reported duration of RPC operations, also including
  session/reset work. It is a duration, not an absolute clock timestamp.
- `rpc_total_ms`: complete master-side RPC duration. Open/write/header-wait/read
  subphases follow SDK boundaries and are not pure network timings.
- `rpc_total_ms - worker_compute_ms`: transport/HTTP/copy/scheduling overhead,
  not Ethernet propagation latency.
- `stream_ms`: time sending generated chunks.
- TTFT includes prompt processing and the output head until the first decoded
  token. For zero visible output, the implementation may have decoded only an
  end token; do not interpret that as time to visible text.
- Dispatcher package time is `max(finished_ms) - min(created_ms)` for the jobs,
  all on the **same master's monotonic clock**. Client polling delay is measured
  separately and is not added to board computation.
- Queue time is acceptance to claim; service is claim to complete result at the
  master. Service includes communication and application overhead.

Never subtract absolute timestamps from different boards. CPU-helper intervals
use the same device clock. `finish_ms` is nested inside inference/matrix work;
helper intervals overlap owner work. Do not add all profiling fields together.
`pause_ms` is owner matrix pause wall time, including scheduling until resumption;
unchanged layer-end yields are not included. `overlap_ms` is overlap of task work
intervals, including their interruptions, not a simultaneous-instruction counter.

## Experimental controls

Keep checkpoint, tokenizer, quantization, prompt IDs, output limit, greedy choice,
context and CPU frequency fixed for performance comparisons. Change one factor
at a time where possible. Keep warm-ups separate and record failed checks rather
than silently treating them as measurements. Package throughput divides the
actual total output tokens by elapsed package time.

Early studies used prompt A `Once upon a time` and B `One day, a little girl`,
24 new tokens each. Modes were alternated or rotated in blocks as recorded in
each metadata file. Report medians, ranges and per-block paired ratios. A ratio
of medians need not exactly equal the median paired ratio.

Fixed-model quality trials use identical inputs/limits for both checkpoints,
but actual lengths can differ. A faster short answer is not evidence of a
faster matrix kernel. The engine stops on token ID 1 or 2; completion responses
do not expose the actual stop ID. `eos_inferred` therefore means an inferred
special-token stop from output shorter than the limit, not a separately proven
EOS ID. Reaching a limit is not a completed story.

## Practical verification and limits

Verification progressed from native numerical tests to real solo/layer-RPC,
LAN recovery, concurrent requests, dispatcher error paths, profiling, numerical
identity across kernels, longer prompts and model replacement. Test counts grew
with each stage; do not sum them as disjoint tests. The final source includes
the accumulated tests, while each report records its original validation scope.

Normal OTA boot confirmation and configuration persistence were tested. A busy
worker was tested, including automatic resumption, but no cable/power failure
was injected during those dispatcher trials. The 180-second queue deadline was
unit-tested, not exercised as a 180-second real outage. Full authenticated browser
interaction and screenshot-based UI acceptance were not completed; API evidence
is stronger than the recorded UI evidence. An attempted screenshot timed out.

No statistical-significance, energy-efficiency, thermal, long-duration reliability
or production-security claim is made. Different firmware baselines shifted for
reasons not fully isolated; only within-firmware controls support causal mode
comparisons. The lab HTTP service uses a shared key without TLS. It was designed
for a local experimental LAN, not assessed as an Internet-facing service.
