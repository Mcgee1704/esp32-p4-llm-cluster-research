# Firmware versions and public diagnostic builds

The version archive contains complete, versioned source reconstructions and
separately rebuilt **keyless diagnostic images**. The binaries used on our
research boards embed a private LAN key and are not distributed. Public images
are different bytes: English/redacted sources, empty access key, and ESP-IDF
path/date reproducibility settings enabled. They are not the measured private
images and have not been flashed or tested on physical hardware.

| Base version | Research stage | Complete versioned source | Public build targets |
|---|---|---|---|
| 0.2.0 | Master-owned dispatcher | [source](../firmware-versions/0.2.0/source/firmware/CMakeLists.txt) | [P4 revision 1.x](../firmware-versions/0.2.0/rev1/manifest.json) |
| 0.3.0 | Pause scheduling and dual-core matrix work | [source](../firmware-versions/0.3.0/source/firmware/CMakeLists.txt) | [P4 revision 1.x](../firmware-versions/0.3.0/rev1/manifest.json) |
| 0.4.0 | Four-row tile4 and internal vectors | [source](../firmware-versions/0.4.0/source/firmware/CMakeLists.txt) | [P4 revision 1.x](../firmware-versions/0.4.0/rev1/manifest.json) |
| 0.5.5 | GPT-Neo, GPT-2 BPE, cold model loading, LAN restart checks | [source](../firmware-versions/0.5.5/source/firmware/CMakeLists.txt) | [P4 revision 1.x](../firmware-versions/0.5.5/rev1/manifest.json), [revision 3.x](../firmware-versions/0.5.5/rev3/manifest.json) |

Version7 adds complete **source-only** snapshots for
[0.6.0](../firmware-versions/0.6.0/source/firmware/CMakeLists.txt),
[0.6.1](../firmware-versions/0.6.1/source/firmware/CMakeLists.txt) and
[0.7.0](../firmware-versions/0.7.0/source/firmware/CMakeLists.txt).
They cover full-vocabulary INT4 shards, lossless flash loading and the real
Metaspace tokenizer. [Source-addition metadata](../firmware-versions/source-additions.json)
identifies their original revisions. These redacted public source trees have
no new ESP build or device claim; only the private original builds were measured.
There are still five keyless binary bundles ending at0.5.5; no new deployment
binary is included. At the historical v7 checkpoint, top-level source was0.7.0; v8 uses0.9.0.

Each target folder provides `p4_tinystories.bin`, `bootloader.bin`,
`partition-table.bin`, `ota_data_initial.bin`, the exact flash offsets/settings
in `manifest.json`, and extended esptool image reports. These are app/boot
components, not a factory dump. No model, NVS contents, private key, ELF/map,
SDK installation or captured hardware identity is included. The
[catalog](../firmware-versions/catalog.json) records source revisions and hashes;
the repository's `SHA256SUMS.json` covers every distributed file.

## What keyless means

`CONFIG_CLUSTER_KEY=""` deliberately disables authenticated inference, model
upload and firmware upload. The images are for boot/serial/UI diagnosis and
source/binary research, **not an operational LAN cluster installation**. Do not
replace a working cluster's firmware with a keyless diagnostic image: protected
LAN APIs will be inaccessible and provisioning a different build requires USB.
No public/shared default access key is provided.

To run an operational cluster, obtain the sources, install ESP-IDF 5.5.4 and
build locally with a new, unique key shared only by your own nodes. The normal
`tools/build.ps1` generates a private local key for the current firmware. Use
the matching `sdkconfig.rev1.defaults` or `sdkconfig.rev3.defaults`. The same
Kconfig option exists in the historical sources; supply a local, untracked
defaults file with your key when compiling them. Keep that configuration and
the resulting provisioned images private. Upload a compatible model separately.
Model licences and pinned sources are documented in the research reports.

## Evidence and limits

All five target configurations were built with the existing local ESP-IDF
toolchain. The generated configuration is checked for empty key and path-hiding
settings. App and bootloader checksums/hashes are inspected with esptool;
the actual private key and private path/identity markers are scanned in each
distributed binary. Boot/revision/version information is retained with each build.
These checks establish build and file integrity, not device acceptance. Only
revision 1.3 boards were used in the original hardware studies; **revision 3.x
has no physical-board validation**. Enabling reproducibility settings is not a
proof of byte equality across independent machines/builds.

The archive does not fabricate every intermediate release. For 0.1.x only
partial transport overlays/private images remain, and not every 0.5.0-0.5.4
diagnostic stage has a complete independently pinned source tree. Their
scientific records and failed attempts remain in the data/reports; private
images are not presented as public releases. Original measured-image hashes
retain their meaning; public-build SHA-256 values identify this separate archive.

ESP-IDF and compiler-runtime notices are preserved under
`firmware-versions/third-party-licenses/`, with a manifest of original hashes.
That is a conservative component-licence superset, not a statement that every
listed SDK component is linked. Original project contributions and third-party
materials retain the terms described in `LICENSE` and `THIRD_PARTY.md`.

## Source-only additions in v8

[0.8.0](../firmware-versions/0.8.0/source/firmware/CMakeLists.txt) records the
bounded INT4/memory microbench. [0.9.0](../firmware-versions/0.9.0/source/firmware/CMakeLists.txt)
records the production INT4 byte-pair kernel. Top-level source is0.9.0.
Private originals were built/tested on the P4s; these redacted public source
representations have no new ESP binary or physical acceptance. Do not substitute
private tested-image hashes for nonexistent public0.8/0.9 binary hashes.
