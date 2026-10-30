# Research snapshot v8: evidence index

The evidence cutoff is30 October2026. New results below are archived alongside
the earlier story/dialogue, transport, dispatch, numerical and simulation work.
No new inference or device experiment was performed while assembling this archive.

| Study | Recorded scope | Report / evidence |
|---|---|---|
| Matched0.7.0 models |41 actual streams; fixed quality set; model-specific text equality |[Report](matched-p4-2026-10-30.md) · [data](../data/matched-p4-2026-10-30/) |
| INT4 / memory microbench |96 raw modes,80 primary values; single-core synthetic scratch workloads |[Report](int4-memory-2026-10-30.md) · [data](../data/int4-memory-2026-10-30/) |
| TinyBrainBot byte-pair kernel |27 actual streams; fresh within-model before/after; about35.6% lower latency on two prefixes |[Report](int4-pair-2026-10-30.md) · [answers](../data/int4-pair-2026-10-30/comparison.html) |
| Same optimized kernel, two models |27 new streams plus12 explicitly reused Tiny quality streams |[Report](supra-tiny-v09-2026-10-30.md) · [answers](../data/supra-tiny-v09-2026-10-30/comparison.html) |

The latest direct comparison has three repetitions/model/prefix, fixed model
order, full vocabularies, row INT4, context256 and4+8 layers. Tiny medians are
32.894535/35.693947 seconds; Supra33.187949/35.931806. Less than1% separation
does not establish a general winner. First factual answers tie3/6; confirmed
clean responses are3/6 Tiny versus2/6 Supra. Judgments are inherited only after
exact output equality, small-sample, unblinded and not independent.

## Organization

- [Main research overview](RESEARCH_REPORT.md), [methods](METHODS.md),
  [data/provenance](DATA.md), [reproduction](REPRODUCIBILITY.md).
- [Four small matched models](MATCHED_MODELS.md), [Supra capacity](supra-model-parallel-2026-10-29.md),
  [negative quantizationV2](supra-quantization-v2-2026-10-29.md),
  [Tiny local quality](tinybrainbot-local-2026-10-29.md),
  [Tiny real tokenizer/device port](tinybrainbot-p4-2026-10-29.md).
- [Firmware archive](FIRMWARE_VERSIONS.md): source through0.9.0; separately
  rebuilt public keyless diagnostic BINs still stop at0.5.5. Private measured
  images carry authentication and are excluded. Redacted0.8.0/0.9.0 public bytes
  have no ESP build or physical-device acceptance claim.
- [Release notes](RELEASE_NOTES_V8.md), [coverage](COVERAGE.md),
  [browse all figures](../index.html).

## Evidence boundaries

Host arithmetic, original physical-device evidence, synthetic microbenchmarks,
simulations, public redacted source and keyless diagnostic binaries are distinct.
Old0.7.0 times in the latest model comparison are historical across-study context,
not a new same-session old-kernel control for Supra. No general assistant,
statistical significance, energy efficiency or third-physical-node claim.
Raw recorded prompts/text and attributed historical source-language material are
preserved rather than translated into different observations. Editorial reports,
new figure labels and navigation are English. Personal journals, keys, private
deployment binaries, SDKs, model weights and private Git history are excluded.
