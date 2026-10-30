# Research snapshot v7: local candidate

This version is prepared locally. It has not been uploaded or assigned a DOI.
The public v6 snapshot and its historical hashes remain unchanged.

Adds Supra50/100M distributed capacity experiments, the negative quantizationV2
study, the120-output local TinyBrainBot/Supra comparison and the real TinyBrainBot
Metaspace port with firmware0.7.0 two-P4 acceptance. Raw answers, failed tests,
correction amendments, methods and figure sidecars remain part of the evidence.

Fixes a derived audit counter from the string `tinybrainbot-int4` to integer120;
no frozen answer or protocol was changed. Historical/private protocol digests
remain in `protocol.sha256`. New `protocol.public.sha256` files and
`provenance/representations.json` authenticate the translated/redacted public
representations without presenting them as the original preregistered bytes.

Matched-model prepare/host/hardware/summary commands now share `--run` or
`--output`. New inference runs must freeze new protocols; original generating
source hashes stay historical. Offline table checks do not run devices or models.

Current firmware source is0.7.0. The five public keyless diagnostic build bundles
still end at0.5.5 and have no physical-device validation. No0.6.x/0.7.0 binary is
included: the actual tested images carry private LAN authentication. Updated
portable source and private-device results are distinct from keyless binaries.

The two-board100M split adds model capacity and serves one shared lane. It is
not the independent-request speedup measured for earlier replicated small models.
All quality comparisons use small fixed sets and the same unblinded assistant;
there is no independent semantic review, global ranking, general-assistant
qualification, third physical node or energy measurement.

See [the TinyBrainBot device report](tinybrainbot-p4-2026-10-29.md),
[local quality comparison](tinybrainbot-local-2026-10-29.md),
[quantization study](supra-quantization-v2-2026-10-29.md),
[Supra device study](supra-model-parallel-2026-10-29.md),
[checksum methods](DATA.md), [reproduction](REPRODUCIBILITY.md) and
[dependency versions](../DEPENDENCIES.json).
