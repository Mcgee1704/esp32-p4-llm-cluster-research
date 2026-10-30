"""Summarize frozen matched outputs without pooling unrelated earlier studies."""
import argparse
import json
from html import escape
from research_integrity import protocol, recorded_file, data_arguments, study_directory
from matched_models import DATA, CASES, MODELS, sha, write


def main(make_report=False):
    # Deriving tables/viewer from recorded evidence needs no model weights.
    p = protocol(DATA)
    if p['cases'] != CASES:
        raise ValueError('Analysis case definitions differ from recorded protocol')
    host = json.loads((DATA / 'host.json').read_text())
    review = json.loads((DATA / 'manual-review.json').read_text())
    recorded_file(DATA / 'host.json', review['source_sha256'])
    assert len(host) == len(review['rows']) == 64
    counts = {}
    for key in MODELS:
        rows = [r for r in review['rows'] if r['model'] == key]
        stories = [r for r in rows if r['case'].startswith('S')]
        counts[key] = {
            'first_fact_correct_of_6': sum(r.get('first_fact_correct', False) for r in rows),
            'question_and_format_of_3': sum(r.get('fully_meets_question_and_sentence', False) for r in rows),
            'instructions_of_3': sum(r.get('fully_fulfilled', False) for r in rows),
            'story_full_topic_of_4': sum(r['topic_continuity'] == 2 for r in stories),
            'story_no_material_contradiction_of_4': sum(r['coherence'] == 2 for r in stories),
            'story_visible_resolution_of_4': sum(r['narrated_resolution'] == 1 for r in stories),
            'story_eos_of_4': sum(r['eos_observed'] for r in stories),
            'story_cap_of_4': sum(r['cap_reached'] for r in stories),
            'all_cases_eos_of_16': sum(r['eos_observed'] for r in rows),
        }
    write(DATA / 'quality-summary.json', {'counts': counts, 'denominators': {'questions': 6, 'formatted_questions': 3, 'instructions': 3, 'stories': 4},
        'source_sha256': {'protocol.json': sha(DATA / 'protocol.json'), 'manual-review.json': sha(DATA / 'manual-review.json'), 'host.json': sha(DATA / 'host.json')},
        'interpretation': 'Exploratory unblinded descriptive counts, not a held-out benchmark. Same prompt bytes, different tokenizer IDs/training objectives. No validated total quality score.'})
    work = {}
    for key, m in p['models'].items():
        d, h, layers, heads, kv_heads, vocab, context = m['dimensions']
        assert heads == kv_heads
        matrices = layers * (4 * d * d + (3 if key == 'sft' else 2) * d * h) + vocab * d
        work[key] = {'matrix_MACs_per_generated_position': matrices,
                     'output_head_MACs': vocab * d, 'output_head_share_of_matrix_MACs': vocab * d / matrices}
    write(DATA / 'architecture-work.json', {'classification': 'Analytical count from deployed dimensions, not measured instructions or a timing prediction',
        'excluded': 'Attention score/value products varying with position, embeddings lookup, normalization, activations, sampling, scheduler and transport; prefill does not execute the output head at every position.',
        'formula': 'layers*(4*d*d + M*d*FFN) + vocab*d, M=3 for Llama SwiGLU and 2 for GPT-Neo GELU; heads=KV heads',
        'models': work, 'source_sha256': sha(DATA / 'protocol.json')})
    html = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Matched model outputs</title>',
        '<style>body{font:16px system-ui;background:#edf2f6;color:#172f43;margin:24px}section{margin:25px 0}.grid{display:grid;grid-template-columns:repeat(2,minmax(300px,1fr));gap:16px}article{background:white;padding:18px;border-radius:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:16px/1.55 system-ui}.note{color:#536579}h1,h2,h3{line-height:1.3}@media(max-width:760px){.grid{grid-template-columns:1fr}}</style>',
        '<h1>Four small English language models: matched outputs</h1><p>29 October 2026. Greedy INT8 native C outputs; identical prompt bytes per case, context 256. EOS observed directly. P4 agreement is recorded separately in hardware/. Manual review is by the same assistant, unblinded, not independent. Familiar facts may overlap training.</p>']
    for case in CASES:
        html += ['<section><h2>' + case['id'] + '</h2><pre>' + escape(case['prompt']) + '</pre><div class="grid">']
        for key, model in MODELS.items():
            r = next(r for r in host if r['model'] == key and r['case'] == case['id'])
            note = next(r for r in review['rows'] if r['model'] == key and r['case'] == case['id'])
            html += ['<article><h3>' + escape(model['name']) + '</h3><p class="note">' +
                     str(len(r['prompt_tokens'])) + ' input tokens; ' + str(len(r['tokens'])) + ' output tokens; ' +
                     str(len(r['text'])) + ' Unicode characters; ' + ('EOS observed' if r['eos'] else 'token cap reached') +
                     '</p><pre>' + escape(r['text']).replace('\r', '&#13;').replace('\n', '&#10;') + '</pre><p class="note">' + escape(note['note']) + '</p></article>']
        html += ['</div></section>']
    html += ['</html>']
    (DATA / 'comparison.html').write_text('\n'.join(html) + '\n', encoding='utf-8')
    print(json.dumps(counts))
    if make_report and (DATA / 'hardware/summary.json').exists():
        report(counts, DATA / 'report.md')


def report(counts, destination):
    from matched_models import ROOT
    timing = json.loads((DATA / 'hardware/summary.json').read_text())
    final = json.loads((DATA / 'hardware/final-state.json').read_text())
    direct = json.loads((DATA / 'hardware/direct.json').read_text())
    assert final['study_completed'] and len(direct) == 64
    assert final['peer_configured'] and final['queued'] == final['running'] == 0
    qtable = '| Model | Facts /6 | Full Q1-Q3 /3 | Instructions /3 | Story topic /4 | Coherence /4 | Resolution /4 | Story EOS /4 |\n|---|---:|---:|---:|---:|---:|---:|---:|\n'
    ttable = '| Model | One-P4 package (s) | Two-P4 package (s) | Two-P4 range (s) | Paired factor | Tokens/s | Characters/s |\n|---|---:|---:|---:|---:|---:|---:|\n'
    lengths = '| Model | S1 / S2 input tokens | Output tokens per package | Unicode output characters per package |\n|---|---:|---:|---:|\n'
    protocol = json.loads((DATA / 'hardware/protocol.json').read_text())
    for key, m in MODELS.items():
        r = counts[key]
        qtable += '| ' + m['name'] + ' | ' + ' | '.join(str(r[k]) for k in ['first_fact_correct_of_6', 'question_and_format_of_3', 'instructions_of_3', 'story_full_topic_of_4', 'story_no_material_contradiction_of_4', 'story_visible_resolution_of_4', 'story_eos_of_4']) + ' |\n'
        t = timing[key]
        low, high = t['cluster_package_range_ms']
        ttable += f'| {m["name"]} | {t["local_package_median_ms"]/1000:.4f} | {t["cluster_package_median_ms"]/1000:.4f} | {low/1000:.3f}-{high/1000:.3f} | {t["paired_throughput_factor_median"]:.3f} | {t["cluster_tokens_per_s_median"]:.3f} | {t["cluster_characters_per_s_median"]:.3f} |\n'
        refs = protocol['benchmark_references'][key]
        lengths += f'| {m["name"]} | {len(refs["S1"]["prompt_tokens"])} / {len(refs["S2"]["prompt_tokens"])} | {t["actual_output_tokens_per_package"]} | {t["actual_unicode_characters_per_package"]} |\n'
    text = '''# Matched English story and dialogue models on two ESP32-P4s

29 October 2026. This study adds two trained checkpoints to the retained
TinyStories-15M SFT and TinyTalk-2 controls. It answers a narrower question than
which model is generally best: under the same small set of input texts, what
changes in observed responses, deployed storage and independent-request throughput?
The work is local; the exported model weights are not published.

## Candidates and source admission

- Story candidate: [roneneldan/TinyStories-Instruct-8M](https://huggingface.co/roneneldan/TinyStories-Instruct-8M),
  pinned conversion PR revision `18d7c83c2d7b0685b0da3c26379dd4d4d90a1ffb`.
  The main branch has a Pickle checkpoint; we instead obtain the data-only
  Safetensors file from [upstream conversion discussion 1](https://huggingface.co/roneneldan/TinyStories-Instruct-8M/discussions/1).
  Its equivalence to the Pickle file is an upstream assertion, not our independently
  deserialized equality test. The pinned readme/config has no explicit model licence;
  no redistribution right is inferred. The author describes a TinyStories-Instruct
  training objective. GPT-Neo, width 256, eight layers, 16 heads; **19,702,528**
  actual parameters including the complete vocabulary and position table.
- Dialogue candidate: [TheREZOR/TinyTalk](https://huggingface.co/TheREZOR/TinyTalk),
  called TinyTalk 1 here, revision `61c79ad139344cdd344a687b35fa8f1c52326154`.
  Declared CC BY 4.0. GPT-Neo, width 128, eight layers, 16 heads;
  **8,278,400** actual parameters, not the informal 3M family label.
- Controls: `0rn0/llama2-15m-tinystories-sft` (retained Llama SFT) and
  [TheREZOR/TinyTalk-2](https://huggingface.co/TheREZOR/TinyTalk-2), the latter
  declared CC BY-NC-SA 4.0. The TinyTalk-2 author identifies TinyStories-Instruct-8M
  as its base. TinyTalk 1 vs 2 changes both capacity and training data/objective;
  this is not a size-only or fine-tuning-only causal ablation.

Public GET downloads of the two new candidates total about 151 MB including
their tokenizers and cards. LFS SHA-256 and ordinary Git blob IDs match the
pinned revisions; existing assets were reused. No project data, device records,
remote inference requests, Pickle loads or upstream model Python were sent/run.
The admission path checks exact configurations, tensor types/shapes, finite values,
complete non-overlapping byte ranges and the tied embedding layout. The old
story file contains eight BOOL attention masks and eight scalar masked-bias
buffers: each full global/local causal mask and each -1e9 sentinel is checked
before exclusion from the deployment artifact. The runtime implements those masks.

Artifacts including complete tokenizers: SFT **15,836,365 bytes**, story candidate
**21,380,448**, TinyTalk 1 **9,887,968**, TinyTalk-2 **21,380,448**. All fit the
existing 24-MiB partition. Each board stores a complete model. Story and TinyTalk-2
have equal dimensions/byte budgets; adding a second board does not pool their RAM.
GPT-Neo uploads use the existing verified cold-restart loader. No firmware/kernel
change is part of this comparison.

## Frozen protocol and correctness

The protocol was hashed before candidate generations. All four models receive
identical UTF-8 prompt bytes: four English story beginnings, six elementary
questions, three exact/restricted instructions, one short context recall, one
unknown-answer probe and one German boundary probe. Stories are continuations
of the same prefix, not the earlier SFT happy/sad-ending instructions or
TinyTalk Summary/Story wrapper. The shared chat wrapper is native to TinyTalk;
performance of SFT on it tests transfer, not its trained native interface.
Caps are 128 story tokens or 32 other tokens, context 256, greedy decoding.
EOS is directly observed; hitting the cap is recorded, not relabelled as a finish.

All 50,257 decoded byte pieces and all 16 prompt encodings match the pinned
tokenizer for each GPT-Neo model. Three full 50,257-logit vectors per model
match the row-quantized NumPy implementation: maximum absolute error
0.000032425 (story), 0.000030279 (TinyTalk 1) and 0.000024796 (TinyTalk-2),
below the frozen 0.002 threshold, with matching argmax. These are internal C/NumPy
checks, not an independent Transformers execution or FP32/INT8 quality proof.
The retained Llama path has earlier source-tensor numerical checks and is rerun
on real hardware here. Its tokenizer has different IDs despite the same text.

Two physical revision-1.3 P4s use firmware 0.5.5 and the dual-core `tile4` kernel.
Two initial TinyTalk-2 controls pass. For each model, the peer first reproduces
all 16 complete host outputs, then the matching master runs the paired timing
study. **All 64 direct cases and all 64 dispatched jobs match their model-specific
token sequences, decoded texts and EOS flags.** Kernel profiles confirm owner
core mask 2 and helper core mask 1 for all direct cases. This is software-profile
evidence, not independent instruction tracing. Both nodes finish on TinyTalk-2,
with peer configuration present and no queued/running jobs.

## Exploratory language findings

{QUALITY_TABLE}

Story topic means both predeclared topic components are continued (ordinal 2/2).
Coherence counts stories scoring 2/2, without a material contradiction in the
visible continuation. Resolution means a narrated positive/negative outcome,
not merely EOS. These are separate criteria, not a validated combined score.
A cap-truncated text can contain an earlier visible resolution.

The story pair preserves the central topic in four of four continuations, with
the same descriptive counts for coherence and resolution. This is **not evidence
of a clear story-quality improvement** from the new checkpoint. SFT sometimes
emits training-format/summary fragments; the new story model has repeated text,
confused speakers and an unintroduced character. Both can narrate a reunion or
sharing and still contradict parts of the setup. EOS differs (2/4 vs 1/4), which
alone is not a quality ranking. Their zero factual answers under a chat wrapper
are compatible with a story-training objective, not proof they cannot contain facts.

TinyTalk-2 gives five correct first factual answers out of six, compared with zero
for TinyTalk 1. It still says a bicycle has four wheels. Only one of the three
one-short-sentence tasks is fully met: the banana answer is factual but has two
sentences. Neither exact word/list task succeeds on any model. TinyTalk 1 gets
one of three instructions under the literal rule: "What kind of rain?" is a short
interrogative about rain without animals. Its fragment/sentence status is
debatable and it supplies no useful information; counting only informative
declaratives would yield zero, but that stricter rule was not frozen. The initial
draft incorrectly imposed that extra criterion; `review-revisions.json` records
the correction. The other three models score zero of three.
TinyTalk 1 often asks an unrelated follow-up or says it does not know; smaller
storage and a shorter answer should not be mistaken for a useful answer.

On the common story prefixes TinyTalk-2 retains full topic continuity in 3/4,
TinyTalk 1 in 1/4. Neither has a contradiction-free story under this rubric.
TinyTalk 1 develops a repetition loop around a red collar; TinyTalk-2 swaps the
hungry fox for a bird in the sharing story. Successful native-format TinyTalk
stories from the earlier study do not contradict these failures under a different
shared continuation format. Prompt interface is a research variable.

TinyTalk-2 cleanly recalls the synthetic cat name and declines the unknown serial
question. SFT and TinyTalk 1 mention the name but introduce speaker/role errors.
All four fail the German colour question. One context/unknown case proves neither
persistent memory nor calibrated uncertainty. All review judgements are by the
same assistant, unblinded and not independent. Cases reuse familiar tasks and
may overlap training. No held-out, significance, user-preference or general
assistant claim follows; raw texts and case-level reasons remain available.

## Controlled throughput results

Two identical input prefixes (S1/S2) are submitted through the master-owned queue,
with a 24-output-token cap. Four alternating AB/BA blocks compare both requests
on the master against one request on each board. Package time runs from the
first master-created timestamp to the last completion on that same monotonic
clock, including queue, prefill and transport. Repeated fixed workloads estimate
timing variability, not independent language-quality samples. Models run in a
fixed sequence to limit flash switches; model order is not randomized.

{TIMING_TABLE}

The factor is the median of within-block local/cluster ratios, not necessarily
the ratio of the two separately reported medians. Whiskers in the figure are
observed min/max, not confidence intervals. All cluster packages use both lanes
with overlapping master-clock backend intervals; cross-node clocks are not compared.
This measures independent-request throughput, not one autoregressive-chain speedup.

For this workload the new story model's two-board package median is
{STORY_SLOWER_PERCENT}% longer than SFT, with no clear quality advantage in the
four-story rubric. Story and TinyTalk-2 have practically identical package times,
consistent with their equal tensor shapes and shared tokenizer. TinyTalk 1 reaches
{SMALL_TOKEN_RATIO}x TinyTalk-2's token rate and {SMALL_CHAR_RATIO}x its character
rate here, but answers zero of the six factual questions correctly. This is a
resource/response-quality tradeoff, not a general ranking of useful text production.

An end-to-end factor slightly above two can occur in these small paired packages;
it is an observed package-clock ratio, not evidence of more than two processors'
worth of arithmetic scaling. Scheduling, board differences, allocation history
and timing variation were not independently ablated. No cause is assigned to a
small excess above the idealized factor of two.

{LENGTH_TABLE}

The input text is controlled; tokenizer IDs, prompt token lengths and generated
contents are not equal across architectures/checkpoints. Tokens/s is a tokenizer-
specific unit. Unicode characters/s counts code points including whitespace and
exposes a second normalization but still
does not equal useful answers/s: verbose or repetitive text can score highly.
Quality and speed therefore remain separate. Same-shape story/TinyTalk-2 is a
closer computational comparison than either versus width-128 TinyTalk 1 or Llama,
but is not a general latency guarantee. No energy or power-efficiency measurement
was made. Earlier 2.50, 4.84 or 6.41 tokens/s figures used different prompts and
are historical workload results, not controls for this table.

An analytical work count helps interpret the architecture contrast: dense matrix
products per generated position (excluding attention score/value products, norms,
activations and overhead) are 15,187,968 multiply-accumulates for SFT,
19,157,248 for story/TinyTalk-2 and 8,005,760 for TinyTalk 1. The two GPT-Neo
widths therefore differ by about 2.39x in this count. It is not a measured CPU
instruction or memory-bandwidth ratio, nor an exact latency prediction. Prefill
also skips most output-head calls. With the full vocabulary, the output head
alone contributes about 80% of this matrix count for TinyTalk 1 and 67% for
TinyTalk-2. These counts explain why family labels excluding embeddings understate
the deployed work; they do not prove the cause of every timing difference.

## Interpretation and next research step

The matched experiment supports a practical distinction: a narrow dialogue/fact
objective can change the kinds of answers produced, while a story objective
does not automatically become an assistant. The new story checkpoint gives no
clear quality win in this sample. TinyTalk-2 is the more promising dialogue
research control here, with substantial remaining factual/format defects; the
smaller TinyTalk 1 is a useful resource/negative-quality control. These observations
do not isolate the contribution of parameter count, data mix or training procedure.

Two-node parallelism has to be assessed within each model's paired workload,
alongside identical outputs. It does not cure weak responses or increase per-node
model capacity. A next quality study should freeze a new task set after designing
it without inspecting candidate answers, include native and shared prompt formats,
independent human/blinded review, more lexical variety, per-task latency and useful
answer rate. A third physical lane, calibrated multi-node scaling and energy
measurement remain future experiments. Scaling beyond two physical nodes remains
unmeasured in this study.

## Figures, evidence and reproduction

![Matched language quality and storage](figures/matched-model-quality-2026-10-29.png)

![Matched independent-request throughput](figures/matched-model-performance-2026-10-29.png)

![Experimental topology](figures/matched-model-setup-2026-10-29.png)

All [full outputs and manual notes](data/matched-models-2026-10-29/comparison.html),
[source hashes](data/matched-models-2026-10-29/downloads.json),
[frozen protocol](data/matched-models-2026-10-29/protocol.json),
[numerical checks](data/matched-models-2026-10-29/numerical-checks.json),
[quality counts](data/matched-models-2026-10-29/quality-summary.json) and
[P4 timing summary](data/matched-models-2026-10-29/hardware/summary.json) are retained.
Raw streams, failed build/environment checks and final device state accompany them.
The cumulative automated suite and publication/privacy checks are reported in
`validation.json` and the public provenance files, not inferred from this prose.

`matched_models.py prepare` admits/exports and freezes a fresh protocol;
`matched_models.py host` builds native references and numerical checks;
`matched_models_p4.py` performs the real local-LAN experiment and restoration.
The scripts intentionally refuse to overwrite the completed evidence directory.
Supply the pinned assets locally and use a new output identifier for a repeat;
never silently amend a completed protocol. `review_matched_models.py` records
the published manual decisions, not an independent scoring engine.
`summarize_matched_models.py` and `plot_matched_models.py` regenerate reports,
the text viewer and SVG/PNG figures from recorded data. Model weights, local
keys, private deployment binaries and operational history stay outside publication.
Separately rebuilt keyless diagnostic firmware is documented in the publication's
firmware-version archive; it is not the binary used in this experiment.
'''
    text = text.replace('{QUALITY_TABLE}', qtable).replace('{TIMING_TABLE}', ttable).replace('{LENGTH_TABLE}', lengths)
    text = text.replace('{STORY_SLOWER_PERCENT}', f'{100*(timing["story8"]["cluster_package_median_ms"]/timing["sft"]["cluster_package_median_ms"]-1):.1f}')
    text = text.replace('{SMALL_TOKEN_RATIO}', f'{timing["talk1"]["cluster_tokens_per_s_median"]/timing["talk2"]["cluster_tokens_per_s_median"]:.2f}')
    text = text.replace('{SMALL_CHAR_RATIO}', f'{timing["talk1"]["cluster_characters_per_s_median"]/timing["talk2"]["cluster_characters_per_s_median"]:.2f}')
    destination.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); data_arguments(parser)
    parser.add_argument('--report', action='store_true', help='Write report.md inside the selected data directory')
    args = parser.parse_args(); DATA = study_directory(args, DATA)
    main(args.report)
