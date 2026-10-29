# Simulation: measured two-node data and unmeasured third-node scenarios

## Real data collected after Kernel V3

Two six-job bursts were specified in advance. A is `Once upon a time`, B is
`One day, a little girl`, C repeats the girl/forest sentence pair four times.
Inputs tokenize to 5, 7 and 70 tokens including BOS.

| Split | Prompt/output limits in submission order | Measured duration |
| --- | --- | ---: |
| Calibration | A8, B24, C16, A48, B8, C24 | 37.757 s, 128 actual output tokens |
| Reserved validation | B16, A32, C8, B48, A24, C32 | 42.545 s, 160 actual output tokens |

Calibration assigned four jobs to the master and two to the worker; validation
assigned three each. Equal job counts are not necessarily balanced work.
Queue ranges were 241–21,448 ms and 44–24,021 ms. All requested limits were
reached. Existing reference prefixes cover 224 tokens; full identity of longer
tails to the older reference is not claimed. Forwarding residuals range
18.916–300.319 ms and include more than network time.

Records preserve requested/actual lengths, target, master clock domain,
accept/start/finish, queue/service/end-to-end times, backend elapsed/TTFT,
matrix/head/pause/barrier profiles and client submission offsets. Overlapping
interval counts are not maximum concurrency. Client offsets are relative to
each burst and must never be subtracted from board timestamps. JSON/CSV and
complete job responses are supplied.

## Frozen model V1

Fit only the six calibration backend times using three nonnegative parameters:
constant + a*(prompt tokens-1) + b*(output tokens). Backend curves are pooled
because the worker has only two training samples. Forwarding residuals, initial
probe time and refill gap are separate medians per target role. FIFO simulation
selects the earliest available lane, with master first for ties.

Fit: constant 0 ms, prompt coefficient 141.375 ms, output coefficient 269.193 ms;
training backend RMSE 136.30 ms. Forwarding medians: master 222.79 ms, worker
215.51 ms. Initial probe 253 ms per lane; refill gaps 247/203 ms.
This approximates the dispatcher; it does not execute FreeRTOS code or model
the real phase after long idle periods, nonlinear attention growth, faults,
temperature or contention introduced by an additional board.

| Check | Measured | Predicted | Relative error |
| --- | ---: | ---: | ---: |
| Reserved two-board mixed burst | 42.545 s | 42.624 s | +0.19% |
| Separate one-master A/B package | 15.235 s median | 15.281 s | +0.30% |

Median absolute service-time error: 0.79%. Exploratory criteria (10% package
error, 15% median service error) passed. The reserved data had been inspected
before this study, so this is **exploratory, not blinded prospective validation**.
A poisoning test establishes that validation values do not change fitted
parameters. Other tests use hand-calculated FIFO/parallel timelines and arrivals.

The frozen three-node scenario for the mixed validation workload is **31.165 s**
versus a simulated 42.624 s for two nodes: 1.3677 throughput factor, about 27%
less time. It assumes an added worker like the existing worker, a third
dispatcher lane, no added master/switch contention and known output lengths.
No EOS prediction and no distributed larger-model capacity are modelled.
Changing only the added worker's service scale to 0.8/1/1.2 and probe/refill scale
to 0/1/2 gives nine scenarios, **24.615–37.762 s**. This is a sensitivity range,
not a confidence interval or guaranteed error band. V1 must not be silently
retuned when a real third node becomes available.

## New prospective real-board check

Three new English openings tokenize to 15, 21 and 40 tokens. Six jobs request
16/8/24/32/8/24 outputs. Before any device access or real inference, prompts,
counts, nominal 20-ms arrivals, immutable V1 model, criteria and 1/2/3-node
predictions were saved. Exact original freeze hashes remain in the evidence.
Run two boards, then the master alone; do not refit afterwards.

| Mode | Frozen prediction | Actual | Error |
| --- | ---: | ---: | ---: |
| Two boards | 27.583 s | 27.480 s | +0.38% |
| Master only | 53.615 s | 52.973 s | +1.21% |

All twelve jobs completed their requested lengths; per-case full token sequences
matched between modes. Early EOS would have invalidated the nominal length
assumption and been reported rather than replacing the original prediction.
An explicitly labelled posthoc conditional simulation is stored separately.
Both runs passed the prewritten 10% package-error criterion. Peer configuration
was restored and boot IDs stayed equal. No firmware/model changed in this study.

The third-node prediction for this **different** workload is 22.149 s. It does
not replace the earlier 31.165-s scenario and is unmeasured. Text selection
followed knowledge of the earlier exploratory results; only these concrete new
runs were predicted prospectively. One repeat per mode is not a statistical
error bound. Broader new workloads and a real third lane remain necessary.

Data: `data/kernel-v3-2026-10-29/simulation-data/`,
`data/simulation-v1-2026-10-29/`, `data/prospective-v1-2026-10-29/`.
