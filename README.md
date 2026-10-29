# ESP32-P4 LLM Cluster Research

Reproducible experiments with two Waveshare ESP32-P4-WIFI6-POE-ETH boards:
distributed text inference, Ethernet transport, autonomous job dispatch,
dual-core matrix computation, memory access, predictive simulation, and text quality.

This is a research prototype. Measurements were made on **two real boards**.
Three-node results are explicitly labelled simulations. No larger model capacity
or useful general-purpose assistant is claimed.

## Main results

| Controlled experiment | Reference | Modified configuration | Interpretation |
| --- | ---: | ---: | --- |
| Initial sequential layer split, 24 tokens | 20.895 s solo | 33.982 s on two boards | About 63% slower; splitting dependent layers does not create parallel work |
| Instrumented layer RPC transport | 33.986 s | 21.092 s after NODELAY and reuse | Transport overhead was the main removable bottleneck |
| Independent requests, PC dispatch | 42.535 s serial | 21.593 s parallel | Median paired throughput factor 1.97 |
| Master-owned dispatcher, firmware 0.2.0 | 38.985 s local | 21.231 s distributed | Median paired throughput factor 1.84 |
| Kernel V2, same firmware, request pair | 22.479 s legacy cluster | 11.737 s dual-core cluster | Paired throughput factor 1.915 |
| Kernel V3, same firmware, request pair | 11.239 s V2 path | 7.495 s tiled cluster | Paired throughput factor 1.502 |

Do not chain ratios across firmware versions: their baselines differ.
The pair experiments use two independent outputs of 24 tokens each; they are
not speedups of one autoregressive generation across boards.

The final runtime is firmware 0.4.0, row-wise INT8 weights, FP32 activations/KV,
both HP CPU cores per P4, and a four-row matrix loop. The current text checkpoint
is `0rn0/llama2-15m-tinystories-sft`, the **same size** as the original TinyStories
baseline. It is a different trained checkpoint, not a larger model.

## Reading guide

- [Complete research report](docs/RESEARCH_REPORT.md): all experiment stages and measured results.
- [Hardware and electrical status](docs/HARDWARE.md).
- [Timing definitions, validation and limitations](docs/METHODS.md).
- [Text-model selection and ten-task quality review](docs/MODELS_AND_QUALITY.md).
- [Simulation and prospective real-board validation](docs/SIMULATION.md).
- [Data, redaction and checksum provenance](docs/DATA.md).
- [Reproduction and API guide](docs/REPRODUCIBILITY.md).
- [Prior project review and future automatic onboarding](docs/PRIOR_WORK_AND_PLANS.md).
- [Research log and coverage of the original records](docs/COVERAGE.md).

## What is included

Portable inference/RPC/queue source, ESP-IDF application source, experiment
tools and tests, recorded results and generated texts, quantitative summaries,
translated qualitative judgements, and partial historical source snapshots.
`data/` contains published experiment evidence. Original numerical measurements
and generated texts are preserved; identifiers and private paths are redacted.

Model weights, LAN keys, factory flash dumps, compiled device images, SDK/tool
installations, personal machine paths and private Git history are excluded.
Obtain the original model assets from the pinned sources documented below;
their licences remain separate. The researcher handle is Mcgee1704.

## Publication representation

This is an English editorial reconstruction of the local research records,
not a claim that the experiments were originally conducted in English.
The public snapshot has a fresh Git history. UI translations and portable setup
paths make its bytes differ from the measured private build. Historical binary,
source and frozen-protocol hashes describe the original experiments; use
`SHA256SUMS.json` for integrity of this public representation.

The recorded private addresses are replaced by `node-1` and `node-2` in data.
Source examples use generic lab addresses. Substitute your own private LAN
addresses before hardware commands. No cloud inference or external telemetry is
required. Study data and browser comparison pages load locally.

Original contributions are provided under the MIT licence. Upstream algorithms,
model licences and attribution are documented in [THIRD_PARTY.md](THIRD_PARTY.md).
