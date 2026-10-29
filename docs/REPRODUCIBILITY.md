# Reproduction and API guide

## Scope

The final portable C runtime and experiment tools are published. Partial source
snapshots preserve selected earlier firmware stages; see `historical/README.md`.
This English/redacted source representation is not byte-identical to historical
private builds. Their recorded binary hashes are provenance, not downloadable
firmware promises. Compiled device images contain the deployment key and are
excluded. Build your own images with a new local key.

## Host setup

Use Python 3.12, NumPy and a C compiler; the recorded native builds used Zig.
For firmware use ESP-IDF 5.5.4 and its ESP32-P4 toolchain. Install dependencies
locally using your normal environment; no hosted execution is required.
`tools/test.ps1` expects Zig in `.local/tooling/host/ziglang/zig.exe` and Python
on PATH. It compiles the actual C inference/RPC and queue libraries, then runs
the accumulated unit suite. The recorded baseline metadata is included for the
static budget test; no model weights are needed for these unit tests.
Dependencies and model weights are not vendored.

The baseline can be obtained with `python tools/fetch_model.py`, which uses
pinned public assets and verifies their hashes. Export with:

```text
python tools/pack_model.py .local/models/stories15M.bin .local/models/tokenizer.bin .local/models/stories15M.p4lm
```

For SFT obtain the files at the pinned URLs in
`data/textmodel-sft-2026-10-29/sources.json` into
`.local/models/llama2-15m-sft-4d69f1c13019/`. Check their hashes and LFS evidence,
then run `tools/import_sft_checkpoint.py` and the existing exporter. The importer
is deliberately limited to the audited candidate. Do not execute arbitrary
model-repository Python. `tools/check_sft_reference.py` performs the separate
NumPy/C check. `tools/native_demo.py` checks solo versus split RPC numerically.

## Hardware setup

Use your own literal private IPv4 addresses. Generic examples in source are not
the original lab addresses. Chip revision determines the correct build defaults;
rev3 compilation is not rev3 hardware evidence. Preserve your original device
state and keep the generated `.local/lan-key.txt` private. Model/key mismatch,
not-ready state and pending OTA confirmation are meaningful errors.

Port 80 routes require `X-Cluster-Key`:

| Route | Purpose |
| --- | --- |
| GET `/api/status` | Model/firmware/readiness, memory, boot ID, kernel protocol |
| POST `/api/generate` | Prompt, token limit, optional layer-RPC peer and kernel mode |
| POST `/api/rpc` | Binary session/model/position-checked layer protocol |
| POST `/api/model` | Replace model in the data partition, validated header last |
| POST `/api/firmware` | Write inactive application slot and reboot for confirmation |

Port 8081 uses the same authentication:

| Route | Purpose |
| --- | --- |
| GET/POST `/api/cluster` | Inspect or persist a known peer; empty peer is master-only |
| POST `/api/jobs` | Submit prompt, 1–128 output limit and optional kernel |
| GET `/api/jobs/<id>` | State, target, timestamps, token stream/result |
| DELETE `/api/jobs/<id>` | Cancel queued work; running cancellation is rejected |

Modes: legacy, paced, dual, sram, tile4. Default is tile4. Public addresses and
redirects are refused by the experiment clients/dispatcher as implemented.
Queues/results are RAM-only; configuration/model persist. No automatic discovery,
third lane, durable SD history or factory-board provisioning is implemented.

## Repeat experiments

First reproduce numerical correctness, then the relevant hardware comparisons.
Use fresh output directories and no unrelated jobs during a series. Commands
that temporarily change models or peer configuration are documented in their
scripts; do not point a trial at an unknown deployment.

- `benchmark_lan.py`: solo/layer-RPC profiles. Earlier transport variants need
  the corresponding historical source; do not claim their result with final code.
- `analyze_lan_benchmark.py`: offline aggregation of the published LAN archive.
  Results are written to `.local/lan-analysis/`. Its new manifest covers
  available data; private firmware binaries are absent.
- `benchmark_parallel.py`: independent requests controlled by the client.
- `benchmark_dispatcher.py`: master-only versus two lanes.
- `benchmark_kernel.py`: same-firmware kernel comparisons; V3 uses dual/sram/tile4.
- `benchmark_cluster_kernels.py --v3`: rotated V3 package comparison.
- `capture_queue_workload.py`: real calibration/validation bursts, not simulation.
- `simulate_cluster.py`: offline V1 fitting/checks/scenario, no device access.
- `prospective_simulation_check.py`: freeze new predictions before real requests.
- `textmodel_trial.py`: baseline-to-SFT trial; expects baseline at entry.
- `text_quality_trial.py`: ten English cases; expects SFT at entry, restores SFT.
- `summarize_text_quality.py`: join a frozen masked review to its recorded texts.

Historical token references belong to a specific checkpoint. Some baseline tools
intentionally reject SFT output. Do not silently edit expected tokens to make a
different checkpoint pass. Recorded private addresses in datasets are pseudonyms;
they must not be sent as real network targets.

To restore the original model, when both queues are idle, upload the retained
baseline `.p4lm` to both nodes using `lan_client.py ... model --file ...`, then
configure the master peer again using `dispatch_client.py ... configure --peer ...`.
Model upload and firmware upload are different operations. Keep keys and binaries
out of public commits. The public offline verifier does not contact devices.

## Publication validation

The English snapshot's inference/RPC and dispatch queue C libraries were compiled
on the host with warnings treated as errors, and all 29 local unit tests passed.
The offline simulator reproduced the recorded numerical validation results.
The LAN aggregation reproduced the recorded quantitative summary. English UI
and portable path edits have not been rebuilt with ESP-IDF or installed on the
boards; device results describe the original measured firmware. See
`provenance/VALIDATION.json` for the publication checks.
