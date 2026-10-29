# Research report: two real P4 boards

All measurements below were recorded on 29 October 2026. The aim was to study
cooperating small devices, not to beat a laptop. Negative scaling results are
part of the findings. Sources are linked in the data index and coverage matrix.

## 1. Initial bring-up and sequential layer split

Both boards passed identification, PSRAM checks, LAN initialization, model upload
and solo inference. The model survived a tested restart of the initial setup.
Factory backups were retained privately. Matching chip revision and OTA images
were checked before flashing; generic S3 firmware/pin assumptions were not used.

The six-layer model was divided 3+3. Three runs per mode with prompt A and 24
new tokens gave median solo 20.895 s, pair 33.982 s: **62.63% longer**. Every
token sequence matched. This proves a functioning split computation, not a
speed or model-capacity benefit. Each board still holds the complete model;
dependent layer halves wait on each other.

## 2. Controlled LAN transport investigation

Hypotheses: repeated connection setup, small-write TCP buffering, worker compute
and streaming overhead. Instrumentation was added first, then NODELAY on both
RPC sockets, then persistent connection reuse. Identical model/partition and
profiling remained in the within-study controls. There were three solo/pair
comparisons per firmware variant, 18 runs in total, with identical tokens.

| Variant | Pair median | RPC overhead | New connections per request |
| --- | ---: | ---: | ---: |
| 0.1.1 instrumented baseline | 33.985522 s | 13.082353 s | 30 |
| 0.1.2 TCP_NODELAY | 21.484968 s | 0.565262 s | 30 |
| 0.1.3 NODELAY plus reuse | 21.092464 s | 0.186020 s | 1 |

The final solo control was 20.895380 s: about 0.94% pair overhead remains.
Pair time fell about 38%; measured RPC overhead fell about 98.6%.

SDK inspection showed separate header/body writes. Each regular RPC payload is
64 header bytes plus 288 FP32 values = 1,216 bytes in each direction, below the
configured MSS of 1,440 bytes. The lwIP TCP timer is 250 ms. Nagle interacting
with delayed acknowledgement is strongly supported by the controlled socket
change and SDK implementation. **There was no packet capture**: exact ACK counts,
directional contributions and first-token anomalies were not packet-proven.
Changing the two socket endpoints separately was not tested.

Persistent RPC was also checked for wrong keys/models, competing sessions,
wrong positions and replay; expected 401/409 responses were followed by successful
step/END and an idle worker. Probe and raw response evidence is included. Some
pre-instrumentation contract probes intentionally lacked the later profile;
they are not passed profile-validation evidence.

## 3. Independent requests controlled by a host

With unchanged firmware 0.1.3, run A and B serially, then on separate boards
concurrently. Four paired blocks, 16 jobs, exact matching token sequences.
Serial median 42.535131 s versus parallel 21.593433 s: paired throughput factor
1.969818, about 1.128 versus 2.223 total tokens/s. Recorded streaming overlaps
and start skew support actual parallel execution. This accelerates a workload
of independent requests, not one dependent autoregressive chain.

## 4. Master-owned automatic dispatcher, 0.2.0

Clients submit to port 8081 on the master. Two forwarding tasks consume one
mutex-protected FIFO and call the single-owner inference servers on port 80,
one over loopback and one over LAN. The dispatcher never directly owns KV/model
state. It checks readiness/model identity and the backend rechecks expected
model identity before computation. No client-side per-job worker selection is
needed. Peer configuration is stored in NVS.

Eight total RAM slots; terminal results can be reclaimed but active jobs cannot.
Results are capped at 160 KiB each, prompt at 1,024 bytes, output at 128 tokens.
Queued jobs expire after 180 seconds. Only queued jobs can be cancelled. Jobs
do not survive reboot and result retention is not guaranteed after eviction.
Once a backend computation POST begins, it is not automatically retried after
an ambiguous failure. This avoids silently duplicating a possibly completed job.

Four paired blocks: local median 38.985 s versus cluster 21.231 s, paired factor
1.8361, total throughput 1.231 versus 2.261 tokens/s. All 16 outputs matched.
Local second-job wait was about 19.45 s; both cluster waits about 0.20–0.23 s.
Four queued jobs produced all 96 tokens in 43.171 s and used both boards.

Validation included 400/401 input/key errors, eight accepted jobs/ninth 429,
409 for active configuration/model changes and cancelling running work,
cancellation of six queued jobs, wrong expected model rejection, persisted
configuration and old RAM-job 404 after reset. Normal OTA and layer RPC worked.
A separately busy peer caused two new jobs to finish locally; later both boards
were used again without reset/reconfiguration. That was not a cable-failure test.

The local baseline differs from the older 42.535-s host-controlled series.
Loopback, task scheduling and tick phase are possible contributors; causality
was not isolated. These historical baselines are not interchangeable controls.

## 5. Kernel V2: pauses, then both HP cores

First compare legacy matrix yields after 256 rows against a paced policy:
check every 32 rows and yield one tick after at least 10 ms elapsed since the
previous pause. Layer-end/loading yields remain. Board 2: two prompts, three
repetitions per mode after four-token warm-ups, rotating/alternating order.

| Median of six direct jobs per mode | Legacy | Paced |
| --- | ---: | ---: |
| Total time | 21.210 s | 18.015 s |
| Matrix time | 20.674 s | 17.478 s |
| Owner matrix pause time | 4.672 s | 1.422 s |
| Output head | 12.000 s | 9.780 s |
| TTFT | 2.375 s | 2.072 s |

Paired factor 1.1774, about 15.1% less total time. The pause reduction largely
explains the gain; matrix time less measured pauses is about 16.00 versus 16.06 s.
This is saved waiting, not proven faster arithmetic per clock.

Next, independent matrix rows were split between an owner pinned to HP core 1
and a persistent helper on HP core 0. Inputs remain immutable until completion;
output row ranges do not overlap. Start/done semaphores synchronize work. Per-row
summation order and `-ffp-contract=off` are preserved. Split only matrices with
at least 128 rows, with the boundary rounded down to a multiple of 32.

Within the same test firmware, paced 18.021 s versus dual-core 10.700 s;
paired factor 1.6844, about 40.6% less time. The output head fell from 9.781 to
5.479 s. All 12 comparisons matched. Core masks, helper rows and overlapping work
intervals establish work on both cores; these are not instruction-level counters.
Owner pinning applies to both controls in this phase.

Final 0.3.0 cluster comparison, four rotated blocks and 32 jobs:

| Mode | Pair median | Range | Total tokens/s |
| --- | ---: | ---: | ---: |
| Legacy cluster | 22.479 s | 22.475–22.482 | 2.135 |
| Paced cluster | 19.493 s | 19.480–19.498 | 2.462 |
| Dual-core cluster | 11.737 s | 11.733–11.738 | 4.090 |
| Dual-core master only | 22.733 s | 22.729–22.747 | 2.111 |

Paired factors: 1.9152 dual/legacy, 1.6608 dual/paced and 1.9371 cluster/single
optimized master. Across the two direct studies and this cluster study, 56
controlled jobs matched references. Sixteen accumulated native tests passed.
Additional real checks: default jobs on both boards, bad mode rejection,
64-token generation, longer prompt token equality and existing layer RPC.
During generation, 53 control queries had median 24.82 ms and maximum 35.61 ms.

## 6. Kernel V3: memory placement and four-row loop

Compare three modes on the same test image: `dual` (V2), `sram` (same arithmetic,
six small vectors in internal RAM), and `tile4` (also reuse each input value for
four rows with four independent accumulators). Per-row order remains unchanged.
Remainder rows use the scalar path. No new quantization, fast-math or custom SIMD.

Vectors x/xb/xb2/q/hb/hb2 require 10,752 internal bytes (10.5 KiB). The original
PSRAM bank is retained for controls; switching copies active vectors. Weights,
tokenizer, attention, logits and KV remain in PSRAM. Address checks establish
actual internal placement. Allocation failure is visible rather than silently
falling back. All modes are warmed before direct measurement.

Two prompts, three rotated mode orders, 18 measured jobs per board. Board 2
first, then board 1, not simultaneous direct trials:

| Mode | Node 1 median | Node 2 median |
| --- | ---: | ---: |
| dual | 10.751 s | 10.744 s |
| sram | 10.569 s | 10.566 s |
| tile4 | 7.058 s | 7.052 s |

Paired dual/sram factors 1.0165/1.0170; sram/tile4 1.4980/1.4982;
dual/tile4 1.5221/1.5238. Small-vector placement alone saves only about 1.7%.
Most of the improvement comes with the loop rewrite, about 34.4% less total
time. Input-load reduction, instruction-level parallelism and cache effects
were not separately isolated. No broad PSRAM-bandwidth claim follows.

Final 0.4.0 cluster study, four rotated blocks, 32 jobs:

| Mode | Pair median | Range | Total tokens/s |
| --- | ---: | ---: | ---: |
| dual cluster | 11.239 s | 11.230–11.497 | 4.271 |
| sram cluster | 10.998 s | 10.981–11.227 | 4.364 |
| tile4 cluster | 7.495 s | 7.482–7.506 | 6.405 |
| tile4 master only | 15.235 s | 15.223–15.246 | 3.151 |

The slow control runs were retained. Paired factors: tile4/dual throughput
1.5015, tile4/sram 1.4682. All 68 controlled V3 jobs matched references.
Nineteen accumulated tests passed, including 275-row tails and memory-bank
switching during an active model state. Real control-server probing during
64-token generation: 36 responses, median 16.34 ms, maximum 34.36 ms.
Longer-prompt regression: legacy 42.446 s versus tile4 15.763 s, same 24 tokens;
one extra regression pair, not a statistical performance study.

The apparent 2.0328 factor against one master is a package-specific result, not
general superlinear scaling. In block 1, serial time consists of 220 ms initial
wait + 7,256 ms service + 244 ms inter-job gap + 7,504 ms service = 15,224 ms.
Distributed time is 224 ms initial wait + 7,259 ms to the last result = 7,483 ms.
The worker also has a different service time than the master. This motivates
separate role/queue modelling instead of assuming identical service kernels.

## 7. Modelling, prospective checks and text models

The next studies are fully described in [SIMULATION.md](SIMULATION.md) and
[MODELS_AND_QUALITY.md](MODELS_AND_QUALITY.md). They include twelve real mixed
jobs for calibration/validation, a frozen three-node scenario, a new prospective
one-/two-board experiment, a checked alternative checkpoint, and twenty real
outputs for a ten-task English quality review. These findings extend the work;
they do not imply a third physical board, larger capacity or a general assistant.
