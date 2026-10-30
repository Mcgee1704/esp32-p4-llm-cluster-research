# Broader model quality V2: prospective protocol and work plan

## Goal, scope and packages

Compare the retained genuine TinyBrainBot and Supra2 row-INT4 models on24 new
English tasks, on the same two physical P4s, firmware0.9.0, tile4 byte-pair,
context256, 4+8 layers and greedy decoding. No weights/dependencies downloaded,
no re-quantization, firmware build/update or partition change. User authorizes
the real private-LAN model switches/tests and final Tiny restoration. No online
publication, third node, external evaluator, subagent or mining-plan adoption.

1. Freeze cases, expected criteria, model-native wrappers, input IDs, source and
   artifact hashes, token budget, mask commitment and this plan before generating
   any candidate answers. Exact questions must be absent from earlier committed
   protocols; topic/template overlap and unknown pretraining contamination remain.
2. Generate48 complete candidate-native references with the existing isolated
   accepted DLL. Verify the old four-token W controls. Preserve the archived DLL.
   Run the existing local suite against the candidate DLL. Do not tune models,
   questions, caps or criteria after viewing answers.
3. Run24 fresh two-board answers/model plus a W warmup/model; Tiny first, Supra
   second to minimize model writes. Four round-robin passes through six categories.
   Every stream must match its own host IDs/text/EOS and report both boards.
   No inference retry. Preserve failures; restore genuine Tiny roles in finally,
   reconfigure the model-bound peer, verify W and both nodes ready/idle on0.9.0,
   sharded queue empty. Planned fresh hardware streams:51, none reused.
4. Create a model-label-masked A/B response set only after recording. Rate visible
   responses with the frozen rubric, commit ratings before opening the mapping,
   then unblind, audit, summarize by category and paired cases. English report,
   full-output viewer, comparison/setup figures, German journal and local commit.

## Tasks, budget and comparisons

Six categories, four cases each: basic facts, arithmetic/logical reasoning,
literal output format, grounded context/dialogue, missing-information behavior,
and short narratives. The uncertainty category separates two unanswerable cases
from two answerable controls, so habitual refusal is not rewarded. All tasks are
synthetic/non-sensitive or stable ordinary facts. No claim of pretraining-held-out
questions, representative language coverage, German proficiency or global ranking.

Non-story cap16, story cap48; maximum1024 quality output tokens across both
models plus12 warmup/restoration output tokens. EOS stops earlier. Case order is
fixed round-robin, identical between models. KV resets each request. Same user
task and cap, different native wrappers and tokenizer IDs. Quality-case latency
has unequal actual output lengths and is not a matched-work speed benchmark.
No repeated quality generations or sampling seeds: greedy repeated identical
inputs are not independent quality observations. No energy/thermal claim.

## Frozen review rubric

Facts, reasoning, grounded and uncertainty: `core` is true only when the visible
first responsive answer satisfies the case's expected criterion. A correct
answer followed by a material false/unsupported assertion can keep core=true
but must fail `clean`. `clean` means the complete visible response satisfies the
question without material error, unsupported fact, contradiction or task drift.
Use null for genuine semantic ambiguity/unfinished claims at the cap; never
silently count null as a success. Core=false means no visible correct answer,
including empty output. A partial/early EOS is not a correct answer by itself.
Review notes must explain every failure or uncertainty. Answers beyond the cap
are unknown, not assumed good/bad. Report confirmed clean and uncertain counts.

Literal format: exact case-sensitive equality after stripping outer Unicode
whitespace only. JSON internal spaces, wrappers, punctuation and extra prose
fail the explicit literal-copy task. This is lexical compliance, not a parser
test or a factuality metric.

Stories: separately rate full requested topic/roles/actions, absence of material
contradiction, visible narrated resolution and exactly two sentences. Topic may
be incomplete even if a story is coherent. Resolution must be narrated in the
visible text; EOS alone is not resolution. Frozen strict completion requires
all four. Small stylistic preferences do not enter these binary judgments.

## Masking and evidence limits

A balanced random per-case A/B mapping plus random nonce is created before
answers and kept ignored locally; only its SHA256 commitment is frozen. The
masked review set has task, criteria, text and cap/EOS status but no model name,
timing, token IDs or model-specific wrapper. Commit model-label-masked ratings
and their input digest before copying the committed mapping into the tracked
unblinding receipt. No post-unblinding rating changes without a named amendment.

Same assistant designs tasks, writes/runs the study and reviews output; model
style/length or prior familiarity can disclose identity. This is model-label
masking, not an independent human review or a claim of complete blinding. Keep
that limitation visible. Category denominators remain4 (uncertainty subgroups2),
paired-case outcomes descriptive. No pooled best-model score, p-value or
population-level quality guarantee from this constructed English sample.

## Acceptance and recovery

Scientific completion requires all48 answers retained and reference-equal,
all51 planned hardware streams audited, prospective protocol commit, committed
masked ratings before unblinding, explicit per-case notes and complete provenance.
Successful operation requires exact true Tiny role identities restored, version
0.9.0, ready/idle and queue0/running0. Host mismatch blocks device writes; any
device failure stops new jobs and triggers restoration. Working firmware and
existing private artifact packages remain available. Unrelated untracked planning
files and older published/frozen studies stay untouched. No push/upload.
