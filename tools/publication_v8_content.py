"""Local publication assembly: English navigation and explicit source lineage.

No network, inference, device access or modification of recorded experiments.
"""
import hashlib,json,pathlib,re,subprocess,xml.etree.ElementTree as ET
from html import escape

REPORTS=['matched-p4-2026-10-30.md','int4-memory-2026-10-30.md',
         'int4-pair-2026-10-30.md','supra-tiny-v09-2026-10-30.md',
         'quality-v2-2026-10-30.md']


def english_early_figure(b):
    stem='llm-erkenntnisse-2026-10-29';p=b.output/'docs/figures'/(stem+'.svg')
    tree=ET.fromstring(p.read_bytes())
    translations=[
      'TinyStories/SFT and TinyTalk-2: findings from the P4 experiments',
      'Shared questions: facts0/3 versus2/3, question plus format0 versus1, instructions both0. Artifacts15.84 versus21.38MB. TinyTalk request pair10.73 versus5.61 seconds. Small exploratory samples, different prompt wrappers.',
      'Two small language models: what did we learn?',
      'ESP32-P4 · recorded measurements and text checks · 29 October2026',
      'TinyStories / SFT','Llama · English stories','TinyTalk-2','GPT-Neo · short English dialogue',
      'Shared tasks','3 identical questions +3 identical instructions','SFT','TinyTalk-2',
      'Correct factual','answer','Question AND format','fully satisfied','Instruction','fully satisfied',
      'Exploratory · small sample · different prompt wrappers',
      'Artifact storage per board','INT8 artifact including tokenizer · flash limit24MiB',
      'TinyStories / SFT','TinyTalk-2','Complete model on each board.',
      'PSRAM obstacle:20.45MB block <21.38MB artifact','Cold restart before loading resolves this obstacle.',
      'More nodes do not pool model memory in this setup.',
      'Observed model capabilities','TinyStories / SFT','Focus: English stories.',
      'Appropriate ending in2 of4 stories;','requested topics only partly satisfied.',
      'TinyTalk-2','Short dialogue and simple questions.','Context name recalled in one probe.',
      'INT8 error: "A bicycle has four wheels."','Story tasks differed between these studies.',
      'This does not establish a fair story-quality winner.',
      'Cluster effect: TinyTalk-2','Two independent requests · identical output IDs / EOS',
      'Coordinator only','Both boards','1.92x throughput','4 paired blocks ·16 jobs',
      'No speed comparison with SFT here:','its timing experiment used different prompts.',
      'Shared finding','Parallelism increases throughput. More model bytes do not guarantee better answers.',
      'No evidence of a reliable general-purpose or German-language assistant.',
      'Data: qualityV1 · TinyTalk host checks · GPT-Neo P4. SFT =0rn0/llama2-15m-tinystories-sft.'
    ]
    iterator=iter(translations);changed=0
    for element in tree.iter():
        if element.tag.split('}')[-1] not in ['title','desc','text']:continue
        original=element.text or ''
        if re.fullmatch(r'[\d,/ .]+(?:MB|s)?',original):
            element.text=original.replace(',','.')
        else:element.text=next(iterator);changed+=1
    assert next(iterator,None) is None
    ET.register_namespace('','http://www.w3.org/2000/svg')
    p.write_bytes(ET.tostring(tree,encoding='utf-8'))
    runtime=pathlib.Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
    code='require('+json.dumps(str(runtime/'node_modules/sharp'))+')(process.argv[1]).png().toFile(process.argv[2])'
    png=p.with_suffix('.png');subprocess.run([str(runtime/'bin/node.exe'),'-e',code,str(p),str(png)],check=True,capture_output=True)
    from public_figure import write_figure
    write_figure(b.output,png.relative_to(b.output).as_posix(),png.read_bytes(),'translation-pixel-validation',{})
    for suffix in ['.png','.svg']:
        b.lineage['docs/figures/'+stem+suffix]['transformation']='English presentation derivative; historical original hash retained, numerical data unchanged.'
    b.put('provenance/early-figure-translation.json',json.dumps({'original_figure':stem,'translated_labels':changed,'numeric_data_changed':False,'scope':'English labels and decimal punctuation only; separate published hashes identify these derivative bytes.'}),'generated-English-figure-translation')


def enrich(b,paths):
    english_early_figure(b)
    for name in REPORTS:
        path=b.output/'docs'/name;body=path.read_text(encoding='utf-8');first,rest=body.split('\n',1)
        note='\n\nPublication note: commands in the historical report retain their original research scope and integrity guards. For this redacted archive, use `python tools/verify_public_snapshot.py .` to reproduce recorded tables without model weights, credentials or devices. Original experiment/native-DLL commands require the separately supplied pinned assets and original environment; they are not claimed runnable from this archive alone.\n'
        path.write_bytes((first+note+rest).encode('utf-8'))
    # Keep original source digests meaningful even where a figure cites an older
    # report/source revision rather than its latest bytes. These are attributed
    # historical source records, not private journals or complete Git history.
    figures=list((b.output/'docs/figures').glob('*.json'))
    for fig in figures:
        data=json.loads(fig.read_text(encoding='utf-8'));deps=data.get('source_sha256',data.get('sources',{}))
        for source,digest in deps.items():
            if any(x['source']==source and x['original_sha256']==digest for x in b.lineage.values()):continue
            assert source.startswith(('docs/research/','tools/')) and '..' not in pathlib.PurePosixPath(source).parts
            raw=b.git(b.ref,source)
            if hashlib.sha256(raw).hexdigest()!=digest:
                refs=subprocess.check_output(['git','rev-list',b.ref,'--',source],cwd=pathlib.Path(__file__).resolve().parents[1]).decode().splitlines()
                found=False
                for ref in refs:
                    raw=b.git(ref,source)
                    if hashlib.sha256(raw).hexdigest()==digest:found=True;break
                assert found,(fig.name,source,'historical source unavailable')
            assert hashlib.sha256(raw).hexdigest()==digest
            # A path may have multiple historical states; give each an explicit
            # digest suffix so no earlier archived state is overwritten.
            dest='provenance/figure-sources/'+source+'.'+digest[:12]+'.txt'
            b.put(dest,raw,source)
    # Local-only transfer notes and journals never become public editorial docs.
    index='''# Research snapshot v8: evidence index

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
'''
    b.put('docs/RESEARCH_INDEX.md',index,'English-v8-editorial/evidence-index')
    notes='''# Research snapshot v8

Adds the matched0.7.0 two-model trial, subsequent bottleneck analysis, separated
INT4/memory measurements, production byte-pair optimization and the fresh0.9.0
Supra/Tiny timing comparison with explicit Tiny quality reuse. All earlier raw
data, negative results, frozen protocols and existing public diagnostic bundles
remain. No historical measurement is overwritten or retrospectively randomized.

The transferred publication audit is applied: corrected typed receipts,
historical/public hashes kept separate, complete figure/source relationships,
offline table reproduction, explicit host/device/public-build limits and private
data exclusions. New complete source snapshots0.8.0 and0.9.0 are source-only.
There is no new model inference, firmware build or hardware test during assembly.
No DOI has been assigned. Upload status is recorded separately from archive build
status; creating these files is not online publication.

See [the evidence index](RESEARCH_INDEX.md) and [provenance](DATA.md).
'''
    b.put('docs/RELEASE_NOTES_V8.md',notes,'English-v8-editorial/release-notes')
    readme=(b.output/'README.md').read_text(encoding='utf-8')
    head='''\n## Latest evidence: firmware0.9.0 and research snapshot v8

[Start with the organized evidence index](docs/RESEARCH_INDEX.md) or
[browse reports and all figures](index.html). The latest same-kernel model
comparison, INT4 production optimization and separated memory measurements are
included with raw outputs and source hashes. Source now ends at0.9.0; public
keyless diagnostic binaries still end at0.5.5. Measured private firmware images
are not distributed. See [v8 release notes](docs/RELEASE_NOTES_V8.md).

The earlier v7 status below is historical context, not the latest device/source
status. See the indexed per-study dates, firmware versions and evidence scopes.
'''
    b.put('README.md',readme.replace('\n',head+'\n',1),'English-v8-editorial/README')
    fw=(b.output/'docs/FIRMWARE_VERSIONS.md').read_text(encoding='utf-8')
    fw=fw.replace('The top-level firmware source is0.7.0.','At the historical v7 checkpoint, top-level source was0.7.0; v8 uses0.9.0.')
    fw+='''\n## Source-only additions in v8

[0.8.0](../firmware-versions/0.8.0/source/firmware/CMakeLists.txt) records the
bounded INT4/memory microbench. [0.9.0](../firmware-versions/0.9.0/source/firmware/CMakeLists.txt)
records the production INT4 byte-pair kernel. Top-level source is0.9.0.
Private originals were built/tested on the P4s; these redacted public source
representations have no new ESP binary or physical acceptance. Do not substitute
private tested-image hashes for nonexistent public0.8/0.9 binary hashes.
'''
    b.put('docs/FIRMWARE_VERSIONS.md',fw,'English-v8-editorial/firmware-versions')
    repro=(b.output/'docs/REPRODUCIBILITY.md').read_text(encoding='utf-8')
    repro+='''\n## Latest archived studies (v8)

Run `python tools/verify_public_snapshot.py .` from the snapshot root with Python
and its standard library only. It validates public/historical digests, all figure
dependencies and links, earlier archived tables, current0.9.0 timing medians,
27 new output streams,12 reused quality streams, the kernel before/after records
and96 microbenchmark mode records. No model download, native DLL or device is used.
This is recorded-data reproduction, not a repeat hardware experiment or a new
semantic quality judgment. Optional output: `--output /your/local/audit.json`.

The original generating/analyzing scripts retain private-asset and original-source
guards. Their historical commands need the pinned weights, toolchain and original
recording environment; redacted current sources are different bytes. Never disable
those guards to make archived output appear to be a fresh model/device run.
'''
    b.put('docs/REPRODUCIBILITY.md',repro,'English-v8-editorial/reproduction')
    citation=(b.output/'CITATION.cff').read_text(encoding='utf-8').replace('research-v7-local-candidate','research-v8').replace('Version7 is prepared locally and is not a published release.','Version8 archives evidence through30 October2026. No DOI is assigned.')
    b.put('CITATION.cff',citation,'English-v8-editorial/citation')
    dep=json.loads((b.output/'DEPENDENCIES.json').read_text(encoding='utf-8'));dep['firmware_0_8_0_and_0_9_0']=dict(dep['firmware_0_7_0']);dep['assembly']='Offline-only archive assembly; no new dependency download or hardware/model experiment.'
    b.put('DEPENDENCIES.json',json.dumps(dep,indent=2),'English-v8-editorial/dependencies')
    page=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>P4 research evidence</title><style>body{font:17px system-ui;max-width:1500px;margin:32px auto;padding:0 20px;color:#193347;background:#eff4f8}img{width:100%;height:auto}figure{margin:0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:24px}a{color:#185e94}</style><h1>ESP32-P4 research archive</h1><p><a href="docs/RESEARCH_INDEX.md">Evidence index and limits</a> · <a href="docs/RELEASE_NOTES_V8.md">Version8 release notes</a> · <a href="docs/REPRODUCIBILITY.md">Offline reproduction</a></p><h2>Latest reports</h2><ul>']
    for report in REPORTS:page.append('<li><a href="docs/'+report+'">'+escape(report)+'</a></li>')
    page+=['</ul><h2>All recorded figures</h2><p>Each figure retains its own study scope and source metadata. Historical diagrams are not current device-state assertions.</p><div class="grid">']
    for fig in sorted((b.output/'docs/figures').glob('*.png')):
        name=fig.name;page.append('<figure><a href="docs/figures/'+name+'"><img loading="lazy" src="docs/figures/'+name+'" alt="'+escape(fig.stem)+'"></a><figcaption>'+escape(fig.stem)+'</figcaption></figure>')
    page.append('</div></html>');b.put('index.html','\n'.join(page),'English-v8-editorial/figure-browser')
    enrich_quality_v2(b)


def enrich_quality_v2(b):
    data=b.output/'data/quality-v2-2026-10-30'
    summary=json.loads((data/'summary.json').read_text(encoding='utf-8'))
    assert summary['actual_streams_checked']==51 and summary['new_quality_outputs']==48 and summary['reused_quality_outputs']==0
    assert (b.output/'docs/CHRONOLOGY.md').exists()
    intro='''\n## Complete history and new prospective qualityV2 study

[Read the project from its first experiments onward](CHRONOLOGY.md).
This includes negative results, corrections, measured versus simulated stages
and source availability; it does not expose private Git history or journals.

The [new24-task quality study](quality-v2-2026-10-30.md) adds48 fresh two-P4
answers and51 actual streams, with model-label-masked same-author ratings
committed before unblinding. It is not an independent/fully blinded review.
The [complete response viewer](../data/quality-v2-2026-10-30/comparison.html)
preserves every answer, cap/EOS status, frozen criterion and rating note.
Different cases/caps mean earlier rates are not pooled into an improvement claim.
'''
    p=b.output/'docs/RESEARCH_INDEX.md';s=p.read_text(encoding='utf-8').replace('snapshot v8','snapshot v9').replace('RELEASE_NOTES_V8.md','RELEASE_NOTES_V9.md');first,rest=s.split('\n',1)
    b.put('docs/RESEARCH_INDEX.md',first+intro+rest,'English-v9-editorial/evidence-index')
    notes='''# Research snapshot v9

Extends the unchanged previously published v8 archive with the prospective
24-task qualityV2 experiment,48 fresh actual outputs, committed model-label-
masked ratings, unblinding receipt, two figures and a complete response viewer.
No model weights, sampling rule, quantizer or firmware changed. This is new
measurement on the same existing models, not a model-quality upgrade.

[The full chronology](CHRONOLOGY.md) makes every retained research stage from
initial bring-up onward discoverable. Older failures, data, source snapshots,
historical hashes and evidence limits remain. Private Git history, personal
journals, device identities/credentials, model weights and provisioned firmware
images are excluded. All previous public commit metadata uses GitHub noreply
authorship; the publication does not import private source-repository metadata.

Public sources still end at0.9.0; existing keyless diagnostic binary bundles
still end at0.5.5. No new ESP/public binary build or hardware qualification is
claimed from archive assembly. No DOI has been assigned.

See [the quality report](quality-v2-2026-10-30.md), [index](RESEARCH_INDEX.md),
[provenance](DATA.md) and [read-only reproduction](REPRODUCIBILITY.md).
'''
    b.put('docs/RELEASE_NOTES_V9.md',notes,'English-v9-editorial/release-notes')
    p=b.output/'README.md';s=p.read_text(encoding='utf-8').replace('research snapshot v8','research snapshot v9').replace('RELEASE_NOTES_V8.md','RELEASE_NOTES_V9.md')
    first,rest=s.split('\n',1)
    head='''\n## From the beginning, including the new broader quality study

[Complete project chronology](docs/CHRONOLOGY.md) ·
[new qualityV2 report](docs/quality-v2-2026-10-30.md) ·
[all48 new responses](data/quality-v2-2026-10-30/comparison.html).
Original numerical results and negative findings are retained; private data
and private Git history are excluded. Review is model-label-masked by the same
author, not independent or completely blind. See individual task/cap limits.
'''
    b.put('README.md',first+head+rest,'English-v9-editorial/README')
    p=b.output/'CITATION.cff';s=p.read_text(encoding='utf-8').replace('research-v8','research-v9').replace('Version8','Version9');b.put('CITATION.cff',s,'English-v9-editorial/citation')
    p=b.output/'index.html';s=p.read_text(encoding='utf-8').replace('Version8 release notes','Version9 release notes').replace('RELEASE_NOTES_V8.md','RELEASE_NOTES_V9.md')
    s=s.replace('<h2>Latest reports</h2>','<p><a href="docs/CHRONOLOGY.md">Complete project chronology</a></p><h2>Latest reports</h2>');b.put('index.html',s,'English-v9-editorial/figure-browser')
    p=b.output/'docs/REPRODUCIBILITY.md';s=p.read_text(encoding='utf-8')
    s+='''\n## Prospective qualityV2 records

The same read-only archive checker additionally verifies all51 actual qualityV2
streams,48 paired review rows, the model-label mapping commitment and category
counts. It reproduces recorded review arithmetic, not an independent semantic
rating or proof that the author could not infer identities. No device, model
weights, private authentication or review nonce file is needed.
'''
    b.put('docs/REPRODUCIBILITY.md',s,'English-v9-editorial/reproduction')


def append_coverage(b):
    p=b.output/'docs/COVERAGE.md';s=p.read_text(encoding='utf-8')
    s+='''\n## Additions through firmware0.9.0

The older future-work paragraph is historical; larger two-board models have
since been measured. [The v8 evidence index](RESEARCH_INDEX.md) links all new
matched-model, memory, production-kernel and comparison records. Generated plots
and explicit source records preserve figure lineage. Snapshot assembly performs
archive checks only and is not a new device experiment. Firmware0.8.0/0.9.0
have complete source-only archives; keyless public BINs still end at0.5.5.

The [complete chronology](CHRONOLOGY.md) includes initial experiments onward.
The [broader qualityV2 report](quality-v2-2026-10-30.md) adds a prospective
24-task set with48 fresh outputs, explicit model-label masking and original
ratings/unblinding provenance; it does not silently replace earlier reviews.
'''
    p.write_bytes(s.encode('utf-8'))
