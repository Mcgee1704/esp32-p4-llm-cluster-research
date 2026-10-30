# Reproduction and API guide

## Scope

The final portable C runtime and experiment tools are published. Partial source
snapshots preserve selected earlier firmware stages; see `historical/README.md`.
This English/redacted source representation is not byte-identical to historical
private builds. Their recorded binary hashes are provenance, not downloadable
firmware promises. Original compiled deployment images contain the private key
and are excluded. Separately rebuilt keyless diagnostics are described in
[the firmware archive](FIRMWARE_VERSIONS.md). For an operational cluster build
locally with a new private key; empty-key images block protected LAN APIs.

## Host setup

Use Python 3.12, NumPy and a C compiler; the recorded native builds used Zig.
For firmware use ESP-IDF 5.5.4 and its ESP32-P4 toolchain. Install dependencies
locally using your normal environment; no hosted execution is required.
`tools/test.ps1` expects Zig in `.local/tooling/host/ziglang/zig.exe` and Python
on PATH. It compiles the actual C inference/RPC and queue libraries, then runs
the accumulated unit suite. The recorded baseline metadata is included for the
static budget test; no model weights are needed for these unit tests.
Dependencies and model weights are not vendored.

The later GPT-Neo and matched-model studies also use tokenizers 0.22.1 for the
host reference; the P4 executes the project's C tokenizer. See
[the binary format](GPTNEO_FORMAT.md), [GPT-Neo device checks](GPTNEO_P4.md)
and [the matched protocol](MATCHED_MODELS.md). The new figures are generated
offline with `tools/plot_matched_models.py` using Node.js/Sharp; Pillow checks
PNG metadata in the snapshot builder. No remotely hosted model is called.
Model directories contain only checked assets from the pinned download manifests;
upstream Python and Pickle are not needed.

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
Model upload and firmware upload are different operations. Keep private keys and
provisioned deployment images out of public commits. The public offline verifier
does not contact devices.

## Publication validation

The English snapshot's inference/RPC and dispatch queue C libraries were compiled
on the host with warnings treated as errors. The original matched-model study
passed 47 tests; later firmware-publication checks extend that suite. The exact
current test count is recorded in `provenance/VALIDATION.json`.
The offline simulator reproduced the recorded numerical validation results.
The LAN aggregation reproduced the recorded quantitative summary. English UI
and portable path edits have now been compiled into the separately labelled
keyless firmware builds; they have not been installed on the research boards.
Device measurements describe the original private firmware. See
`provenance/VALIDATION.json` for the publication checks.

## Version7 offline smoke test and new inference runs

From a fresh copy of this public snapshot, `python tools/verify_public_snapshot.py`
checks package and historical/public checksum pairs, all authored report links,
recalculates matched-model quality/throughput tables, the120-output TinyBrainBot
quality totals and the three P4 latency records. It uses Python's standard
library, requires no model weights or credentials and never contacts devices.
`--output /local/path/result.json` saves its derived tables outside the snapshot.
This reproduces stored tables, not new answers or hardware measurements.

The older matched summary/validation scripts additionally import NumPy; use the
pinned version in `DEPENDENCIES.json`. Fresh inference is a separate workflow:
see `MATCHED_MODELS.md` for common `--run`/`--output` arguments. The TinyBrainBot
historical source audit contains exact private hashes and cached-source guards;
use the public snapshot checker for redacted archives. Do not bypass an inference
source guard to treat translated source as the original measured program.

[Version7 release notes](RELEASE_NOTES_V7.md) separate the0.7.0 source/device
results from the older public keyless binaries. All public build changes would
need new separately labelled build and device evidence before deployment.

## Latest archived studies (v8)

Run `python tools/verify_public_snapshot.py .` from the snapshot root with Python
and its standard library only. It validates public/historical digests, all figure
dependencies and links, earlier archived tables, current0.9.0 timing medians,
27 new output streams,12 reused quality streams, the kernel before/after records
and96 microbenchmark mode records. No model download, native DLL or device is used.
This is recorded-data reproduction, not a repeat hardware experiment or a new
semantic quality judgment. Optional output: `--output /your/local/audit.json`.

The original generating/analyzing scripts retain private-asset and original-source
guards. Their historical commands need the pinned weights, toolchain and original
recording environment; redacted current sources are different bytes. Never disable
those guards to make archived output appear to be a fresh model/device run.

## Prospective qualityV2 records

The same read-only archive checker additionally verifies all51 actual qualityV2
streams,48 paired review rows, the model-label mapping commitment and category
counts. It reproduces recorded review arithmetic, not an independent semantic
rating or proof that the author could not infer identities. No device, model
weights, private authentication or review nonce file is needed.

## Doubled-cap V3 recorded-data checks

The same standard-library checker additionally verifies46 new physical streams,
five old EOS reuses, all48 old token prefixes, mapping commitment, committed
review representations, paired transitions, category counts and fresh-subset
recorded costs. It performs no device/model run and no independent semantic review.
