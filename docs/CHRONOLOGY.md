# The project from its first experiments onward

This is a chronological scientific record, not a publication of the private Git
repository, personal chats or device backups. All retained research stages,
negative results and documented corrections belong to the archive. A planned
feature is not relabelled as implemented, and a simulated node is not a real P4.
Original records use their own dates, prompts, versions and denominators.

| Stage | What the record establishes | Report and retained data |
|---|---|---|
| Initial board/model bring-up | Two physical revision1.3 P4s; a complete small model and a dependent layer split. The first two-board split was slower than one board. | [Research §1](RESEARCH_REPORT.md) · [hardware](HARDWARE.md) · [first runs](../data/initial-two-board-2026-10-29/) |
| Ethernet transport | Instrumented baseline, NODELAY and connection reuse; output equality and negative/positive timing results retained. | [Research §2](RESEARCH_REPORT.md) · [summary](../data/lan-2026-10-29/) · [raw records](../data/lan-raw-2026-10-29/) |
| Independent request parallelism | Two complete model replicas serve separate requests. This is a throughput experiment, not a faster single autoregressive chain. | [Research §3](RESEARCH_REPORT.md) · [data](../data/parallel-2026-10-29/) |
| Master-owned dispatcher | On-board queue distributes independent work; its recorded recovery and queue checks are bounded acceptance evidence. | [Research §4](RESEARCH_REPORT.md) · [data](../data/dispatcher-2026-10-29/) |
| Rechenkern V2 | Separate interventions on yield/pause scheduling and both HP CPU cores per board. | [Research §5](RESEARCH_REPORT.md) · [data](../data/kernel-v2-2026-10-29/) |
| Rechenkern V3 | Internal working vectors and a four-row loop, with direct and cluster comparisons. | [Research §6](RESEARCH_REPORT.md) · [data](../data/kernel-v3-2026-10-29/) |
| Scaling simulation | Calibrated recorded workloads and a prospective check; third-node numbers are explicitly simulation results. | [Simulation](SIMULATION.md) · [model](../data/simulation-v1-2026-10-29/) · [prospective check](../data/prospective-v1-2026-10-29/) |
| Same-size story SFT and qualityV1 | A different trained checkpoint, not a larger memory pool; complete outputs and qualitative judgments retained. | [Models/quality](MODELS_AND_QUALITY.md) · [model](../data/textmodel-sft-2026-10-29/) · [review](../data/quality-v1-2026-10-29/) |
| GPT-Neo / TinyTalk-2 | New architecture/tokenizer; source-layout checks, actual P4 trials, failed warm allocation and amended cold-load path. | [Host](TINYTALK_HOST.md) · [device](GPTNEO_P4.md) · [data](../data/gptneo-p4-2026-10-29/) |
| Four small matched models | Story and dialogue checkpoints on identical task bytes; quality, size and replicated-request throughput kept distinct. | [Report](MATCHED_MODELS.md) · [data](../data/matched-models-2026-10-29/) |
| Supra50 and Supra100 | Genuine larger model shards on both P4s; full vocabularies and one distributed lane, not two independent replicas. | [Report](supra-model-parallel-2026-10-29.md) · [50M](../data/supra50-2026-10-29/) · [100M](../data/supra100-2026-10-29/) |
| Supra quantizationV2 | Better source-distribution fidelity did not improve the frozen answer screen; the candidate was rejected and not deployed. | [Report](supra-quantization-v2-2026-10-29.md) · [data](../data/supra-quantization-v2-2026-10-29/) |
| TinyBrainBot local selection | Source/INT4 comparisons, all120 continuations and later typed-receipt correction; no answers were silently replaced. | [Report](tinybrainbot-local-2026-10-29.md) · [data](../data/tinybrainbot-local-2026-10-29/) |
| TinyBrainBot tokenizer and P4 port | Real Metaspace/BPE tokenizer, genuine compressed shards, measured admission, native-reference checks and LAN recovery. | [Report](tinybrainbot-p4-2026-10-29.md) · [data](../data/tinybrainbot-p4-2026-10-29/) |
| Matched firmware0.7.0 comparison | Same physical pair and representation; complete output equality, fixed case set and descriptive three-repeat speed prefixes. | [Report](matched-p4-2026-10-30.md) · [data](../data/matched-p4-2026-10-30/) |
| INT4/memory diagnostics |96 raw workload-mode samples; single-core synthetic scratch loops, not physical bus bandwidth or end-to-end inference. | [Report](int4-memory-2026-10-30.md) · [data](../data/int4-memory-2026-10-30/) |
| Production INT4 byte-pair kernel | Fresh within-Tiny before/after timing; exact output preservation; firmware0.9.0 retained after recorded gates. | [Report](int4-pair-2026-10-30.md) · [data](../data/int4-pair-2026-10-30/) |
| Same new kernel, Supra versus Tiny | Fresh timing for both models,12 fresh Supra quality cases and12 explicitly reused Tiny cases; genuine Tiny roles restored. | [Report](supra-tiny-v09-2026-10-30.md) · [data](../data/supra-tiny-v09-2026-10-30/) |
| Broader qualityV2 | Prospective24-task English set,48 new answers, committed model-label-masked ratings before unblinding. Different questions/caps mean earlier quality scores are not directly pooled. | [Report](quality-v2-2026-10-30.md) · [protocol/data](../data/quality-v2-2026-10-30/) |

## Firmware and evidence availability

[The firmware archive](FIRMWARE_VERSIONS.md) distinguishes complete source
snapshots, partial historical overlays and separately rebuilt public keyless
diagnostic binaries. Incomplete old source states are not invented or presented
as independently build-validated releases. The actual provisioned device images
contain a private key and are never included. Public source and private tested
bytes have different integrity/evidence scopes.

## Privacy and honest boundaries

Personal journals, chat exports, private Git history, credentials, private host
paths, hardware identifiers, model weights, private firmware images and unrelated
planning material are excluded. Public authorship uses the public pseudonym and
GitHub noreply identity. Synthetic names and fictional records in test questions
are part of the scientific stimuli, not personal data about real people.

Raw task text, generated output and original numerical values are retained.
English presentations and redacted public representations have separate hashes;
they are not passed off as the originally frozen private bytes. No outside
upload, repeated device experiment or new semantic review is needed to run
[the read-only archive checks](REPRODUCIBILITY.md).

The studies do not establish a reliable general-purpose/German assistant,
independent blinded quality ratings, energy efficiency or a third physical node.
PoE/USB power sharing and factory onboarding remain separate qualifications.
