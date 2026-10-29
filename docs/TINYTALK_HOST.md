# TinyTalk-2: feasibility screen before a P4 port

29 October 2026. This is a **local host experiment**, not execution on the P4.
The current Llama firmware/model were not changed. The aim is to test a model
trained for simple dialogue/questions after the two story checkpoints failed
general question/format tasks.

## Candidate and source integrity

Selected for a possible port: [TheREZOR/TinyTalk-2](https://huggingface.co/TheREZOR/TinyTalk-2/tree/2b55040281013975a4d97e3db8d634f78b31c6b1),
revision `2b55040281013975a4d97e3db8d634f78b31c6b1`.
Declared model licence: **CC BY-NC-SA 4.0**, separate from our source licence.
This research choice is not a commercial-use or general-assistant qualification.

The actual 108 F32 tensors contain **19,702,528 parameters**, including the full
50,257-token embedding and all 2,048 learned position rows. Use this count for
storage planning rather than the model family's informal 8M designation.
Hidden size 256, eight layers, 16 attention heads, FFN 1,024, alternating global
and local attention (window 256), LayerNorm epsilon 1e-5, GELU-new, tied output.
The host/deployment screen is restricted to context 256, despite the larger
position table. The author's vocabulary-pruned Q4 ESP32-S3 firmware and speed
claims are a different configuration and were not adopted or measured here.

Weights: 78,821,312-byte Safetensors, SHA-256
`40e10ee793e157f09fb94d2926db9aa3f81d42814249f1c1db023b7027f17567`.
Weights matched the pinned LFS digest. Five other downloaded assets matched
their pinned Git blob hashes; current SHA-256 values are recorded too. Roughly
82.4 MB of weights/tokenizer/generation data was downloaded, plus small metadata
and a verified local tokenizer wheel. No model-repository Python was executed,
no remote inference was used and no new project data was published.

An additional compatible story SFT would repeat the training-objective limit.
The reviewed larger Llama story family needs another storage/quantization path.
LittleKedi-tiny-instruct has a dialogue objective and far fewer parameters, but
adds MoE/MLA and a different tokenizer, making it a separate runtime project.
These are implementation tradeoffs, not a comparative model-quality ranking.

## Reproducible host implementation and numerical scope

`tools/tinytalk_reference.py` reads only F32 data with duplicate-key, range,
overlap/gap, shape, finite-value, exact architecture and pinned-weight checks.
It implements GPT-Neo in NumPy: learned positions, unscaled QK scores, causal
and local-window masks, biased LayerNorm/MLP, GELU-new and the tied output head.
The architecture was checked against the official
[Transformers v4.57.1 source](https://github.com/huggingface/transformers/blob/v4.57.1/src/transformers/models/gpt_neo/modeling_gpt_neo.py).
That source was read, not executed.

Eight new tests cover malformed data, unsupported configs, unscaled attention,
window exclusion, cached/full-sequence equivalence, zero-row/quantization error,
cache reset/context bounds and actual parameter/byte accounting. All **37**
accumulated tests passed; native inference/RPC and queue libraries rebuilt.

On real weights, cached and separately batched routes compared **all 50,257
logits at 18 prompt positions**, for each precision:

| Host route | Maximum absolute logit difference | Cached/batch argmax |
| --- | ---: | --- |
| FP32 | 0.0000267029 | 18/18 equal |
| Simulated row INT8 | 0.0000314713 | 18/18 equal |

Frozen tolerance: 0.001. This is internal cache/batch consistency, not an
independent Transformers/PyTorch numerical execution and not C/P4 validation.
The synthetic local-window test exercises exclusion; the real 18-position
prompt does not cross the 256-token window boundary.

INT8 simulation quantizes every two-dimensional tensor row, including position
embeddings, then immediately dequantizes to FP32 for NumPy computation. Norms
and biases remain FP32. It does not emit a packed artifact or run integer
matrix arithmetic. FP32/INT8 logits differ by up to 0.338172 in that prompt;
argmax agrees at 16/18 positions. Quantization is not token-preserving.

## Proposed memory layout, not a device admission proof

| Component | Bytes |
| --- | ---: |
| Row INT8 matrices/scales plus FP32 vectors/biases | 20,048,452 |
| Proposed compact vocabulary/offset/merge tables | 1,121,859 |
| Proposed artifact including 128-byte header | 21,170,439 |
| FP32 K/V at context 256 | 4,194,304 |
| Work-vector estimate | 18,432 |
| PSRAM including other buffers/index and assumed 2-MiB reserve | 28,099,795 |

Against a 24-MiB model partition and 32-MiB PSRAM this fits **statically**. The
compact GPT-2 tokenizer, search index and binary model layout are design
assumptions, not implemented/exported firmware structures. Exact alignment,
allocator fragmentation, Unicode/pretokenizer tables, task stacks and network
peaks require the real port. SD and a third node are not prerequisites for
this candidate; summed board memory is not used by this calculation.

## Frozen exploratory response screen

Protocol SHA-256 before first generation:
`3626eed0d7e3eeb330e93268c753b8f1de2d2ea1d57ed7bc86ab385abacdd48c`.
Fourteen cases, greedy decoding, FP32 first then INT8 simulation. Six reuse
Q1-Q3/I1-I3 from quality V1; three add simple questions, two cover greeting/context
recall, one unknown synthetic serial-number question, one story, one German
language-boundary probe. Chat uses the author's `User: ...\nBot:` format, history
includes the documented end marker; story uses `Summary: ...\nStory:`. Limits
are 32 output tokens, or 128 for the story. No generated output was used to
change these cases. Exact-word scoring ignores outer whitespace.

All **28 outputs** reached observed EOS before their limits. Twelve of fourteen
complete token sequences are identical across precision variants. Full texts
and token IDs are retained; host elapsed times are not P4 speed measurements.

| Observation in this screen | FP32 | INT8 simulation |
| --- | --- | --- |
| Correct factual content, six questions | 5/6 | 5/6 |
| Original one-short-sentence question task fully met | 1/3 | 1/3 |
| Exact blue / red green blue | 0/2 | 0/2 |
| Rain instruction | Failed | Failed |
| Bicycle question Q3 | Abstains | Incorrect assertion: four |
| Short context: synthetic cat name Luna | Correct | Correct |
| Unknown synthetic board serial | Declines | Declines |
| Apple-sharing story | Complete, on topic | Identical complete story |
| German banana question | Declines | Declines |

Examples: `A cow says moo!`; `I know! The banana is yellow.` The latter answers
the factual part but has two sentences, failing the requested format. The model
also answers puppy, cold and four cat legs correctly. Its rain response talks
about a relationship. The changed bicycle output is a **negative quantization
finding**: abstention becomes confident false content. Similar aggregate counts
must not hide this. The second changed case, I2, fails in both precisions.

Manual review is by the same assistant after generation, **unblinded and not
independent**. Common elementary facts may overlap training; no unseen benchmark
claim follows. The old SFT/baseline study ran on hardware and used different
model-specific wrappers; its scores/times are not a controlled paired comparison
with this host screen. One successful context/unknown/story example proves no
general memory, uncertainty-calibration or story-quality guarantee.

## Decision and next package

TinyTalk-2 is a concrete next **research port candidate**: simple dialogue and
questions are more appropriate objectives than another story-only checkpoint,
and the full-vocabulary INT8 proposal fits the static budget. It remains an
English toy model, fails general instructions and has a demonstrated harmful
quantization change. This is not a model-release or assistant-quality pass.

The P4 currently implements Llama/RMSNorm/RoPE/SwiGLU with another tokenizer and
stop IDs. It cannot load these GPT-Neo weights. Next implement a separate,
versioned GPT-Neo loader/kernel and compact GPT-2 tokenizer, while preserving
the existing Llama regression path. Verify C logits/tokens against the recorded
host reference, then check actual allocation and one-board inference before
integrating two-board dispatch. Re-evaluate quantization quality, including
the Q3 regression, rather than silently tuning it away. P4 timings remain open.

Re-run into a fresh directory with the pinned assets and local dependencies:

```powershell
$env:OPENBLAS_NUM_THREADS='1'
python tools/evaluate_tinytalk.py freeze .local/tinytalk-repeat
python tools/evaluate_tinytalk.py run .local/tinytalk-repeat
```

Use `tools/test.ps1` for the native/unit suite. The evaluator refuses source,
script or protocol changes after freezing. Large assets/dependencies remain in
`.local/`; no weights or foreign firmware are committed. Evidence:
[protocol and results](../data/tinytalk2-host-2026-10-29/),
[full comparison](../data/tinytalk2-host-2026-10-29/comparison.html),
[manual review](../data/tinytalk2-host-2026-10-29/manual-review.json),
[checks](../data/tinytalk2-host-2026-10-29/checks.json).
