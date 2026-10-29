# Third-party sources

The portable Llama forward pass and BPE algorithm are based on the algorithms in
Andrej Karpathy's `llama2.c` at commit
`350e04fe35433e6d2941dce5a1f53308f87058eb` (MIT). The implementation here adds a
different, validated row-wise INT8 format, bounded tokenizer parsing, PSRAM
allocation and a split-layer interface. It is not the upstream `runq.c` format.

https://github.com/karpathy/llama2.c

MIT License

Copyright (c) 2023 Andrej

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Model: https://huggingface.co/karpathy/tinyllamas (MIT according to model card).
ESP-IDF 5.5.4 and toolchains are downloaded under `.local/tooling/`; their
licenses remain in the original packages. Board wiring reference:
https://github.com/waveshareteam/ESP32-P4-Platform at
`6f78fa810ec505048c1941e3d09cefc9f29129bd` and the Waveshare board schematic.


Additional text checkpoint (local research trial):
0rn0/llama2-15m-tinystories-sft, revision
`4d69f1c13019afcf5c50b621c73cb9c92e01bb4e`, MIT according to its model card.
https://huggingface.co/0rn0/llama2-15m-tinystories-sft
Author-supplied BF16 safetensors converted locally to the existing P4LM INT8
format. Downloaded weights, original model card and source material remain under
`.local/models/llama2-15m-sft-4d69f1c13019/`; source hashes are recorded in the
research evidence. Upstream Python was read for architecture verification and
was not imported or executed. This is a separate pretrained/SFT model, not an
SFT-only ablation of the Karpathy baseline.

TinyTalk-2 local host and ESP32-P4 research:
https://huggingface.co/TheREZOR/TinyTalk-2 at
`2b55040281013975a4d97e3db8d634f78b31c6b1`, declared CC BY-NC-SA 4.0.
Its weights/tokenizer/card remain in ignored local storage and are not
redistributed. Their terms are separate from the project's original code.
GPT-Neo architecture was checked against Hugging Face Transformers v4.57.1
`src/transformers/models/gpt_neo/modeling_gpt_neo.py` (Apache-2.0), read only.
The independent NumPy and C implementations are local source; no model-repository
Python was executed. A verified tokenizers 0.22.1 wheel is used locally for the
GPT-2 BPE reference and deriving Unicode classes. The P4 runs the project's C
tokenizer; dependency binaries are not committed. Source/dependency hashes are
retained in `data/tinytalk2-host-2026-10-29/` and
`data/gptneo-p4-2026-10-29/`.

Matched-model research adds TheREZOR/TinyTalk (TinyTalk 1), revision
`61c79ad139344cdd344a687b35fa8f1c52326154`, declared CC BY 4.0, and
roneneldan/TinyStories-Instruct-8M, pinned Safetensors-conversion PR revision
`18d7c83c2d7b0685b0da3c26379dd4d4d90a1ffb` from upstream discussion 1.
https://huggingface.co/TheREZOR/TinyTalk
https://huggingface.co/roneneldan/TinyStories-Instruct-8M/discussions/1
The pinned TinyStories readme/config has no explicit model-licence declaration;
no redistribution permission is inferred. Original and converted model weights,
tokenizer assets and upstream cards remain local and are not included in Git.
The conversion's equivalence to the Pickle checkpoint is an upstream assertion;
we verify the pinned LFS digest and tensor/mask semantics, not a separately
deserialized Pickle-to-Safetensors equality check. No upstream model code runs.

Public keyless diagnostic firmware bundles additionally retain ESP-IDF v5.5.4
and compiler-runtime licence/notice files under the firmware-version archive.
The SDK source is https://github.com/espressif/esp-idf/tree/v5.5.4 . The compiler
distribution is riscv32-esp-elf esp-14.2.0_20260121; GCC runtime exception and
newlib/picolibc notices are preserved alongside a conservative SDK-component
notice superset. This does not relicense SDK/runtime materials as project MIT
code, or claim that every listed component is linked. Original private deployment
images and model weights are not distributed.
