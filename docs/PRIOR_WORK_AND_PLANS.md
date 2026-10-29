# Prior-work review and unimplemented plans

## ESP32s3-LLM-Cluster: static review only

Reference: https://github.com/Low-Zi-Hong/ESP32s3-LLM-Cluster at
`5822029b7132894d5c982041c42fda93c5b7f5d5`. Selected source/workflow/licence files
were read; the project was not built, executed or hardware-validated here.

The reviewed setup has one master and six workers with four layers per worker.
Its partially trained quantization workflow reports random-token output; a
small fully trained reference model was therefore chosen for our experiments.
The master waits on the layer chain per token, so adding workers is not itself
evidence of single-request acceleration. Xtensa assembly is part of the build
and is not a P4/RISC-V kernel. Fixed model layouts, RoPE, norms and tokenizers
mean that a different checkpoint is not just a file replacement.

SPI was configured at 10 MHz with 4,096-byte frames: ideal serialization alone
is 3.2768 ms/frame, not an end-to-end latency claim. Its runtime context 512
and FP32 KV must not be confused with a checkpoint's larger nominal position
limit. Its reported TTFT boundary precedes final norm/output; our TTFT includes
the output computation.

Static budget from the reviewed packing code: 3,735,580 bytes/layer, 89,653,920
for 24 layers, at least 14,336,000 for the packed INT4 embedding, total at least
103,989,920 bytes before firmware/tokenizer. Two 32-MiB flashes provide only
67,108,864 gross bytes. KV at context 512 is 524,288 bytes/layer, 12,582,912 total.
These are layout calculations, not measured speed/quality or proof of a usable
two-board deployment. PSRAM is not extra flash, and summed memory is not a
single address space. `data/static-budget.json` retains the machine-readable audit.

Other earlier S3/RS485/CAN board catalog material concerns a different board;
its pin assignments and electrical results must not be transferred to this P4.

## Automatic factory-board onboarding: design, not implemented

Desired behaviour: connect a matching new board by the proposed LAN/USB chain
and have an already prepared member install/enrol it without a per-board mode
or setup button. A prepared first member and a verified local installation
package are prerequisites; an all-factory set cannot bootstrap itself from
absent software. Already enrolled boards must reconnect without destructive
reset or overwriting newer data.

Proposed sequence: detect neighbours even if cables were present at boot;
try an authenticated framed application handshake before any bootloader action;
inspect an unknown intended installation target; match chip, revision, flash and
security/write-protection state; reject mismatches without bypassing protection;
write/verify the local package; wait for self-test; transfer a one-time target-bound
enrolment capability over USB; register/authenticate over LAN; persist per-device
credentials; admit work only after confirmed enrolment. A new member could then
provision its next neighbour. Interrupted installation must remain visibly incomplete.

The USB-C bridge is CH343P with DTR/RTS boot/reset wiring according to the
reviewed schematic. P4 USB-host CH343 handling, automatic boot control, board-
to-board flashing and electrical power sharing were not demonstrated. LAN has
the implemented workload/update role; USB is a proposed provisioning/recovery
path, not a proven fast tensor transport. The current dispatcher has two known
lanes, one shared lab key and no membership/discovery subsystem. Do not confuse
its completed automatic job dispatch with this future zero-touch onboarding.

Further separate experiments: prospective broader simulation validation, a real
third lane, model sharding versus a separately validated Q4 runtime, larger
compatible trained checkpoints, SD persistence, OTA fault rollback and electrical
qualification. Scope and validation should be fixed before combining changes.
