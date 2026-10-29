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
