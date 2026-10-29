# Data and publication provenance

## Representation and privacy

`data/` contains recorded measurements, token streams, complete generated texts,
protocols, summaries, model references, numerical checks and review judgements.
Additional original LAN/layer-split evidence has been recovered from the local
experiment archive. Factory flash contents, keys, model weights, tool/SDK installs,
personal paths, serial/MAC identifiers and original Git author metadata are not
part of this public snapshot.

Original measured times, token IDs, numeric profiles, fits, scores and flags are
preserved. Model-generated English text is not translated or improved. Human
German review notes are translated to English without changing scores. Operational
addresses become node/client pseudonyms; port names and machine roots are redacted.
Opaque per-run boot/job identifiers remain for cross-record clock and job joins;
they are not authentication credentials or factory hardware identifiers.

This processing changes file bytes. `SHA256SUMS.json` verifies this public tree.
`provenance/source-files.json` maps public paths to original source-content hashes
and published hashes. `provenance/historical-hash-manifests.json` retains sanitized
historical manifests separately: their hashes refer to original local files,
not necessarily to translated/redacted public files. Some original binary/source
artifacts are intentionally absent. A hash without those bytes is provenance,
not a claim that the artifact can be rebuilt or validated from that hash alone.

Recorded `script_sha256`, `source_sha256`, protocol/model-of-simulation hashes and
similar historical fields retain their recorded meaning unless specifically
documented as publication-derived. Do not compare them blindly with the final
English source or anonymized JSON. Original firmware images include a private
deployment key and are never distributed here. Public English UI/path changes
also change firmware bytes; historical app hashes are not public release hashes.

For the English quality-review representation, current review/pair checksums are
recalculated so the published join tool can validate its inputs. The original
frozen review hash remains in publication provenance and the report. A newly
translated review was **not** frozen before the historical model-label opening.
`vergleich.html` is replaced by the English static `comparison.html`; no external
assets or JavaScript are required to view it.

## Evidence index

| Directory | Evidence |
| --- | --- |
| `initial-two-board-2026-10-29/` | Initial three solo/pair runs and streams |
| `lan-2026-10-29/` | Controlled transport summary/CSV |
| `lan-raw-2026-10-29/` | Instrumented, NODELAY/reuse raw streams, probes/error tests |
| `parallel-2026-10-29/` | Host-controlled serial/parallel jobs and overlap |
| `dispatcher-2026-10-29/` | Autonomous dispatcher, queue/error/restart/busy-peer evidence |
| `kernel-v2-2026-10-29/` | Pause/core comparisons, cluster results, regression checks |
| `kernel-v3-2026-10-29/` | Both-board memory/tile trials, cluster study and real queue data |
| `simulation-v1-2026-10-29/` | Fit, exploratory checks and frozen three-node scenario |
| `prospective-v1-2026-10-29/` | New frozen predictions, real one-/two-board outputs, budgets |
| `textmodel-sft-2026-10-29/` | Source/licence selection, conversion, references, model trial |
| `quality-v1-2026-10-29/` | Ten-task raw outputs, masked review, mapping and English comparison |
| `static-budget.json` | Prior-project packing calculation, not physical measurement |

## Reuse correctly

Preserve checkpoint/firmware identity, clock domains, output lengths and split
definitions. A numerical equality test is not a text-quality score. Samples with
different actual output lengths are not equal-work speed tests. No p95,
significance or confidence guarantee should be inferred from a few related runs.
Calibration/validation separation and prior inspection status are documented
rather than retrospectively claiming blinded data.

The measured firmware has only two lanes. Third-node scenarios assume a future
implementation and are not real measurements. Static memory fits do not prove
runtime admission or useful language quality. Automatic factory onboarding,
electrical power-sharing safety and durable SD state remain unimplemented or
unqualified, as recorded in the respective reports.
