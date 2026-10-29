# Models, capacity and English text quality

The sections below retain the earlier SFT/quality-V1 experiment. Later results
are in [the matched four-model report](MATCHED_MODELS.md),
[TinyTalk-2 host screening](TINYTALK_HOST.md) and
[the completed GPT-Neo P4 study](GPTNEO_P4.md). GPT-Neo is now implemented in
firmware 0.5.5. Earlier statements that it requires a port describe the decision
at that earlier stage, not the current runtime.

## Capacity audit before changing models

The full model is loaded on every P4, including layer-split mode. More boards
currently improve independent-request throughput, not the largest loadable
artifact. Flash partition: 24 MiB; PSRAM per node: 32 MiB. SD does not expand
PSRAM or change the implemented loader.

The static allocator/export audit matches the real artifact exactly. It includes
row scales, norms, tokenizer copies, FP32 vectors/logits/attention and KV. The
2-MiB operating reserve below is a planning assumption, not an exact peak proof.

| Configuration | Artifact bytes | PSRAM including reserve |
| --- | ---: | ---: |
| Real 15M, context 256 | 15,836,365 | 22,595,226 |
| Same shapes, hypothetical context 128 | 15,836,365 | 20,822,682 |
| Same shapes, hypothetical context 512 | 15,836,365 | 26,140,314 |
| Hypothetical 12 layers, otherwise original shapes | 21,893,581 | 32,191,386 |

There is no trained checkpoint for the hypothetical 12-layer example. Copying
layers is not a trained larger model. Context changes are budget estimates,
not created artifacts or quality validation beyond the training context.
Internal V3 vectors add 10,752 bytes separately; allocator alignment, stacks and
network peaks still require checks for an actual candidate.

The runtime implements a particular tied-embedding Llama layout: row INT8,
RMS epsilon 1e-5, RoPE base 10,000, special-token stop IDs 1/2 and the old
llama2.c tokenizer representation. Parser bounds include dim 1024, FFN 4096,
32 layers and context 1024, plus head/divisibility constraints. File size alone
does not establish compatibility. A reviewed Qwen2 reference had FFN 4864,
different RoPE/epsilon/special IDs and is not a drop-in candidate.

## Selected alternative: trained SFT checkpoint of the same size

`0rn0/llama2-15m-tinystories-sft`, pinned revision
`4d69f1c13019afcf5c50b621c73cb9c92e01bb4e`, MIT according to its model card.
It targets English stories with requested happy/sad endings. It is **not larger**
than the original Karpathy model and uses a different pretrained base, so this
is not an SFT-only ablation. The official roughly 42M model exceeds the current
INT8 partition budget. The reviewed 19M-Instruct/TinyTalk alternatives use
GPT-Neo and require another architecture/tokenizer port.

Public checkpoint/tokenizer LFS SHA-256 values were checked at the pinned
revision. Data-only Safetensors import validates 56 BF16 tensors, names, shapes,
non-overlapping ranges, finite values and the tied embedding alias. No pickle
or upstream Python was executed. The BOS/EOS display convention is normalized
to the existing tokenizer export; all exported tokenizer bytes then match.

New artifact: 15,836,365 bytes; model ID
`5273bac5d1937595d92e1528a21ad7ac619e5fde8d2bfbb0aca04866bf10e07f`;
artifact SHA-256
`a1aa4c95d23be513adee776fc2bbb835fce2e5ab88ddd04461da3c69d35495cd`.
Same dimensions and memory requirement as the baseline.

Three importer tests passed. A separate NumPy forward directly from row-quantized
BF16 tensors matched four full C logit vectors to maximum absolute error
0.00002909 (tolerance 0.002), with matching argmax. This does not prove general
BF16/INT8 language-quality equivalence. Host references then checked complete
hardware generations.

Baseline was measured first. Node 2 changed to SFT and was validated before
changing node 1 and updating the dispatcher's model identity. Twenty real jobs
matched their **respective** host references. Two direct rounds per prompt with
24 tokens, two longer outputs up to 96, and two cluster packages per model:

| Metric | Baseline | SFT |
| --- | ---: | ---: |
| Direct median, four runs | 9.498 s | 9.504 s |
| TTFT median | 3.115 s | 3.107 s |
| Cluster package times | 10.006 / 9.832 s | 9.999 / 9.824 s |
| Package median | 9.919 s | 9.912 s |
| Longer-output actual token counts | 96 / 96 | 96 / 77 |

Essentially equal speed; fixed model order and small sample do not support a
speedup claim. Longer instruction prompts explain differences from earlier
7.5-s short-prompt packages. One SFT sad story ended by itself; the happy case
was cut at 96. Those two observations were not a general quality test.

## Ten new English tasks: frozen masked review

Before host generation/device access, freeze four stories (128-token limits),
three simple questions and three exact/short instructions (32-token limits).
Same inputs, limits and greedy decoding; SFT first, then baseline, finally
restore SFT on both nodes. Twenty real outputs all matched their own host
references. Firmware stayed 0.4.0; peer/model identity restored, no active jobs.

Stories: rabbit sharing a carrot, child repairing a kite (happy endings), girl
unable to find her cat and boy losing a sandcastle to the sea (sad endings).
Questions: cow sound, ripe banana colour, bicycle wheel count, one short sentence
each. Instructions: exactly `blue`, exactly `red green blue`, and one short rain
sentence without animals. Stories use the documented SFT story template; other
tasks intentionally test generalization outside its primary training objective.

Coherence is rated 0/1/2 (empty/unintelligible; major contradictions/repetition;
connected understandable English). Topic is rated 0/1/2 (absent/partial/central).
Requested ending is assessed only for an inferred special-token stop, not a
limit-truncated output. Automatic indicators include exact full output, a limited
rain-sentence heuristic and repetition (fourgram at least three times or a word
three times consecutively). Lexical answer signals alone do not prove correctness.

Model labels were masked per task as A/B. The same assistant froze its individual
reviews before opening the mapping. Style/prior knowledge can reveal identity:
**not an independent or fully blinded user study**. Translated review notes,
all scores, complete texts and label mapping are provided. English translation
creates a new public representation; original freeze hashes are historical.

| Observation in this small sample | Baseline | SFT |
| --- | ---: | ---: |
| Finished stories with requested emotional ending | 0/4 | 2/4 (kite, cat) |
| Story ending unassessable at limit | 2/4 | 2/4 |
| Moral only instead of a story | 2/4 | 0/4 |
| Correct first factual answer, ignoring extra prose | 1/3 (cow) | 0/3 |
| Entire requested question/format fulfilled | 0/3 | 0/3 |
| General instructions fulfilled | 0/3 | 0/3 |
| Automatic repetition flags | 1/10 (cow) | 0/10 |
| Inferred special-token stops / limit hits | 2 / 8 | 2 / 8 |

SFT still only partially fulfilled every story topic: sharing was not yet shown,
repair was asserted without a convincing repair event, ownership of the lost cat
was not established, and the sandcastle story had an odd instruction to wash it.
The baseline's two short moral outputs are fluent English but fail the narrative
task. Repeated Mary dialogue and speaker inconsistencies occur in its cat story.
Do not average these different criteria into a hidden overall ranking.

Baseline correctly begins the cow answer with `moo`, then repeats prose. Neither
model answers the banana colour or bicycle count correctly in the requested
format; the baseline mentions four wheels. Both continue stories instead of
the exact words, and both use multiple sentences for the rain task. Repetition
below the automatic threshold is still noted manually. No flags is not proof
of repetition-free language.

SFT generated 640 tokens, baseline 478: pooled elapsed times are not comparable
kernel-speed measurements. SFT remains an exploratory story/cluster model;
these tasks did not establish reliable general assistance. A next assistant
candidate should target general instruction training, not merely more parameters.
No German-language evaluation, representative benchmark or safety-critical
application qualification is claimed. A cold boot after this particular model
change was not separately tested. Historical baseline simulator parameters are
not automatically validated for the new checkpoint/EOS behaviour.

Sources: https://huggingface.co/karpathy/tinyllamas and
https://huggingface.co/0rn0/llama2-15m-tinystories-sft . See recorded revisions,
hashes and source attribution rather than assuming mutable default branches.
