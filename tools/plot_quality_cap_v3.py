"""Offline English cap-sensitivity report, paired viewer and source-linked figures."""
import json,pathlib,subprocess
from html import escape
from plot_matched_models import Canvas,MUTED
from quality_cap_v3_results import ROOT,DATA,BASE,MODELS,CATS,read,write,sha,audit,validate
DOC=ROOT/'docs/research'
NAMES={'tinybrainbot':'TinyBrainBot','supra':'Supra2-100M'}
COLORS={'tinybrainbot':'#178476','supra':'#7953a6'}
TITLES={'facts':'Basic facts','reasoning':'Arithmetic / reasoning','exact':'Literal output format','grounded':'Context / dialogue','uncertainty':'Missing information','story':'Short narratives'}

def save(c,name,sources):
 stem=DOC/'figures'/(name+'-2026-10-30');stem.with_suffix('.svg').write_bytes(('\n'.join(c.s+['</svg>'])+'\n').encode())
 runtime=pathlib.Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node';code='require('+json.dumps(str(runtime/'node_modules/sharp'))+')(process.argv[1]).png().toFile(process.argv[2])'
 subprocess.run([str(runtime/'bin/node.exe'),'-e',code,str(stem.with_suffix('.svg')),str(stem.with_suffix('.png'))],check=True)
 write(stem.with_suffix('.json'),{'title':name,'date':'2026-10-30','source_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in sources},'scope':'Same 24 known English tasks, doubled caps32/96 versus16/48;43 fresh quality streams,5 explicit EOS reuses,3 fresh controls. Same-author model-label-masked higher-cap ratings, not independent or fully blind. No pooled model score or equal-work speed claim.'})

def number(d,cat):return d['exact'] if cat=='exact' else d['strict_completion'] if cat=='story' else d['confirmed_clean']

def main():
 p,refs,low,raw,paths=audit();validate();s=read(DATA/'summary.json');pairs=read(DATA/'paired-results.json');u=read(DATA/'unblinding.json');by=s['categories']
 sources=[DATA/n for n in ['protocol.json','summary.json','paired-results.json','masked-ratings.json','unblinding.json','record-audit.json','final.json']]+[BASE/'summary.json',BASE/'masked-ratings.json',ROOT/'tools/quality_cap_v3_results.py',ROOT/'tools/plot_matched_models.py',pathlib.Path(__file__)]
 c=Canvas(1450,'Does more output budget improve the answers?',
          'Same 24 English questions and two P4s · firmware 0.9.0 · greedy · only the stopping cap changes')
 c.text(48,152,'Confirmed success within each criterion; four tasks per category',27,weight='bold')
 for m,x in [('tinybrainbot',500),('supra',1040)]:c.text(x,201,NAMES[m],27,COLORS[m],'bold')
 for i,cat in enumerate(CATS):
  y=250+i*145;c.text(48,y,TITLES[cat],25,weight='bold')
  c.text(48,y+33,'Exact literal match' if cat=='exact' else 'All four story criteria' if cat=='story' else 'Whole response clean',20,MUTED)
  for m,x in [('tinybrainbot',500),('supra',1040)]:
   for j,stage in enumerate(['baseline','higher']):
    d=by[m][cat][stage];v=number(d,cat);yy=y-19+j*47;cap=(48 if cat=='story' else 16)*(j+1)
    c.text(x,yy+20,str(cap)+' tok',20,MUTED);c.rect(x+82,yy,244,25,'#dfe8ed',3);c.rect(x+82,yy,v/4*244,25,'#b7cbd4' if j==0 else COLORS[m],3)
    suffix='; '+str(d['uncertain_clean'])+' ?' if d.get('uncertain_clean') else ''
    c.text(x+345,yy+21,str(v)+'/4'+suffix,21)
 c.rect(48,1150,1504,170);c.text(72,1192,'43 new quality runs +5 reused early-EOS answers; both boards in every new run.',26,weight='bold')
 c.text(72,1235,'All 48 higher references preserve the old token prefix. Old EOS answers stay exactly identical.',24)
 c.text(72,1278,'? = uncertain whole-response judgment, never counted as confirmed success. No pooled total.',23)
 c.text(48,1368,'Same author knows the old outputs; higher labels were masked until ratings were committed. Not independent or fully blind.',21,MUTED)
 c.text(48,1411,'Known constructed tasks, n=4/category. More generated tokens are extra work, not a faster-kernel result.',21,MUTED)
 save(c,'quality-cap-v3-comparison',sources)
 c=Canvas(1150,'Output-cap V3: controlled intervention and physical setup',
          'One independent variable: stopping budget · context 256 unchanged · full vocabulary / INT4 /4+8 layers')
 for i,(title,a,b) in enumerate([('Immutable baseline','Same 24 questions / native input IDs','Saved 16/48-token outputs and ratings'),('Doubled output limits','Short tasks 32, stories 96 tokens','No model/kernel/firmware change'),('Deterministic comparison','Check all old token prefixes','Five EOS outputs explicitly reused')]):
  x=48+i*510;c.rect(x,150,484,160);c.text(x+23,193,title,25,weight='bold');c.text(x+23,241,a,21);c.text(x+23,281,b,21,MUTED)
 c.rect(48,380,704,165);c.text(72,424,'Coordinator P4',28,weight='bold');c.text(72,472,'Tokenization, embedding/output, layers 0–3',23);c.text(72,516,'32 MiB PSRAM /32 MiB flash',22,MUTED)
 c.rect(848,380,704,165);c.text(872,424,'Worker P4',28,weight='bold');c.text(872,472,'Layers 4–11, own FP32 KV',23);c.text(872,516,'32 MiB PSRAM /32 MiB flash',22,MUTED);c.arrow(752,430,848,430);c.arrow(848,500,752,500,'#178476');c.text(800,407,'LAN',20,anchor='middle')
 c.text(48,610,'Tiny first → Supra second → restore genuine Tiny roles and verify W.',27,weight='bold')
 c.rect(48,658,1504,154);c.text(72,702,'43 new answers +2 warmups +1 restoration control =46 new physical streams.',27,weight='bold')
 c.text(72,748,'Five old EOS streams supply the remaining higher-cap evaluations; no redundant hardware generation.',23)
 c.text(72,787,'Maximum new output budget 1900 tokens. Greedy, one trajectory, no inference retry or selective rerun.',23)
 c.rect(48,862,1504,174,'#dce9f2');c.text(72,908,'Rate all 48 higher-cap texts with masked model labels; commit, then unseal.',27,weight='bold')
 c.text(72,953,'Keep old ratings; compare paired improvements, regressions and uncertainty by model/category.',23)
 c.text(72,999,'Recorded final state: true TinyBrainBot on both 0.9.0 nodes, ready/idle, queue empty.',23)
 c.text(48,1090,'Old outputs are known. Same-author label masking is not independent, complete or cap-blinded review.',22,MUTED)
 save(c,'quality-cap-v3-setup',sources)
 page=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Output-cap sensitivity V3</title><style>body{font:17px system-ui;max-width:1450px;margin:32px auto;padding:0 20px;background:#eff4f8;color:#193347}section{padding:24px 0;border-top:1px solid #b8cbd8}.pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,480px),1fr));gap:32px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>Same questions, doubled output budget</h1><p>All 48 paired low/high evaluations.43 fresh higher-cap quality runs and5 explicitly reused old EOS outputs. Old ratings unchanged; same-author higher-cap labels masked before commitment, not independent or fully blind.</p>']
 for case in p['cases']:
  page.append('<section><h2>'+case['id']+' · '+TITLES[case['category']]+'</h2><p>'+escape(case['user'])+'</p><p>Criterion: '+escape(case['expected'])+'</p>')
  for m in MODELS:
   pair=next(x for x in pairs if x['model']==m and x['case']==case['id']);page.append('<h3>'+NAMES[m]+' · '+pair['transition']+' · '+pair['higher_origin']+'</h3><div class="pair">')
   for stage,ref,cap,key in [('Baseline',low[m][case['id']],case['baseline_limit'],'baseline_rating'),('Higher cap',refs[m][case['id']],case['limit'],'higher_rating')]:
    rr=pair[key];score={k:rr[k] for k in ['core','clean','exact','topic','coherent','resolution','two_sentences'] if k in rr}
    page.append('<article><h4>'+stage+' · cap '+str(cap)+'</h4><pre>'+escape(ref['text'] or '[Empty decoded text]')+'</pre><p>'+escape(json.dumps(score))+'</p><p>'+escape(rr['note'])+'</p><p>'+str(len(ref['tokens']))+' tokens; EOS '+str(ref['eos'])+'</p></article>')
   page.append('</div>')
  page.append('</section>')
 page.append('</html>');(DATA/'comparison.html').write_bytes(('\n'.join(page)+'\n').encode())
 lines=['# Does doubling the output budget improve TinyBrainBot or Supra2?', '',
 '## Result and paired category counts','',
 'The same 24 known English tasks were evaluated at doubled caps:32 versus16 output tokens for short tasks,96 versus48 for stories. Models, exact native inputs, greedy decoding, context 256, firmware 0.9.0, tile4 byte-pair INT4 and the same physical P4 pair remained fixed. All 48 old token prefixes are preserved.43 new quality streams, five explicitly reused early-EOS streams and three new controls form the higher-cap evidence.','',
 '| Model | Category | Old confirmed success | Higher confirmed success | Newly confirmed | Lost confirmed | Higher uncertain |','|---|---|---:|---:|---:|---:|---:|']
 for m in MODELS:
  for cat in CATS:
   d=by[m][cat];lines.append('| '+NAMES[m]+' | '+TITLES[cat]+' | '+str(number(d['baseline'],cat))+'/4 | '+str(number(d['higher'],cat))+'/4 | '+str(d['newly_confirmed'])+' | '+str(d['lost_confirmed'])+' | '+str(d['higher'].get('uncertain_clean',0))+' |')
 lines+=['','Confirmed success means wholly clean for facts/reasoning/context/information, exact literal equality for format and all four frozen criteria for stories. Newly confirmed includes previously failed or uncertain answers; lost confirmed includes new failure or uncertainty. All nine paired success/failure/uncertain transitions remain in the JSON summary. No pooled model score.','',
 '### Missing-information controls','',
 '| Model | Information | Old core / clean | Higher core / clean | Higher uncertain |','|---|---|---:|---:|---:|']
 for m in MODELS:
  for g,title in [('unanswerable','Not provided'),('answerable','Answer supplied')]:
   a=by[m]['uncertainty']['baseline']['subgroups'][g];b=by[m]['uncertainty']['higher']['subgroups'][g]
   lines.append('| '+NAMES[m]+' | '+title+' | '+str(a['core'])+'/2 / '+str(a['confirmed_clean'])+'/2 | '+str(b['core'])+'/2 / '+str(b['confirmed_clean'])+'/2 | '+str(b['uncertain_clean'])+' |')
 lines+=['','### Observed cost on the freshly rerun subset','',
 '| Model | Fresh cases | Historical seconds | Higher-cap seconds | Old / new output tokens |','|---|---:|---:|---:|---:|']
 for m in MODELS:
  d=s['fresh_subset_cost'][m];lines.append('| '+NAMES[m]+' | '+str(d['n'])+' | '+str(round(d['historical_baseline_seconds'],3))+' | '+str(round(d['fresh_higher_seconds'],3))+' | '+str(d['baseline_output_tokens'])+' / '+str(d['higher_output_tokens'])+' |')
 lines+=['','These are server-reported generation elapsed sums for the same formerly capped cases, excluding reused EOS timings and controls. The baseline is historical, the higher-cap run fresh; output work differs and model order is fixed. This describes the observed cost of longer visible answers, not a randomized latency trial or an isolated speed change. Complete48-answer token totals and EOS/cap counts are retained in summary.json.','',
 '![Paired category comparison](figures/quality-cap-v3-comparison-2026-10-30.png)','',
 '## Interpretation','',
 'The extra budget produces substantially more text without broadly rescuing answers in this constructed set. No previously confirmed failure becomes a confirmed success. No old confirmed success is lost. Tiny has one newly confirmed clean answer, U01, whose short form had already correctly acknowledged the unspecified address but ended inside another clause. The longer completed generic name/place clause supplies no invented street, town or house number, so the frozen missing-information criterion is now judged clean. This is resolution of one earlier uncertain judgment, not evidence of a new factual or reasoning capability. The same-author nature of that judgment remains a limit.','',
 'The other three old uncertain cleanliness judgments become failures: Tiny F01 extends the correct roots answer with an unqualified leaves-absorb-it claim in the soil-uptake context; Supra G03 repeats the obsolete coat location after the basket statement; Supra U04 invents a landscape and dense forests after correctly naming the supplied road. These continuations clarify previously unfinished text; they are not regressions from formerly confirmed clean answers. Core first-answer counts do not improve in any category.','',
 'Both models remain0/4 on exact literal format and0/4 on strict story completion. Already visible wrong literal prefixes cannot be repaired by appending text; these persistent failures are not independent new evidence that a larger model or a different prompt would fail. Topic/coherence/resolution totals also remain unchanged. Tiny gains the requested two-sentence format in S04 after completing its pear-sharing sentence, but still omits both friends feeling happy. It loses two-sentence format in S01 by continuing into further sentences. The aggregate Tiny two-sentence count stays1/4, masking those opposing case changes unless full paired results are inspected. Supra stays0/4 on that format criterion.','',
 'Five early-EOS Tiny answers remain exactly unchanged: increasing a maximum cannot force generation beyond EOS. Tiny now ends with EOS on13/24 cases (including those five), while11 still reach the new cap. All24 Supra outputs still reach the new cap. Neither EOS nor reaching a cap is a quality verdict; for example, Tiny still gives the wrong cup color before an EOS stop.','',
 'Across the48 evaluated answers, Tiny output grows489→824 tokens and Supra512→1024. For the freshly rerun19 Tiny cases, recorded engine elapsed sums grow1461.236→2108.052 seconds; for all 24 Supra cases,1911.792→2883.244 seconds. These are historical-versus-fresh observed costs with more output work, not a slowdown of the unchanged kernel. No measured energy or statistically representative quality-per-token claim follows.','',
 'For these retained artifacts and questions, simply raising the default cap is not supported as a broad quality fix. Keeping the short default and permitting a larger cap when a task needs it is a reasonable prospective operational choice, not a configuration change performed here. A future prompt/framing or source-versus-INT4 study would test a different cause and requires its own frozen protocol. Nothing here establishes how much another model, larger context or output beyond 96 tokens would help.','',
 '## Design, budget and evidence boundaries','',
 'The protocol and new model-label mapping commitment were frozen in9fb72c6 before any higher-cap reference. Every previous task string, expected criterion, model-native wrapper/input token ID and category order was copied unchanged. Maximum input length41 plus highest cap96 fits the unchanged context 256 without truncation. The maximum fresh hardware output budget is1900 tokens, including controls. No model download, re-quantization, firmware build/write, partition change or second quality sample occurred.','',
 'Existing local native code generated48 higher-cap references and two known W controls. Every old token sequence is an exact prefix. Five old Tiny answers already ended with EOS: R03, I01, G01, G02 and U02. Their higher-cap references are completely identical, so their previously verified actual device streams were explicitly reused. They are not new hardware trials. All43 formerly capped answers were newly generated on both P4s. Three new controls complete46 fresh streams;51 streams including the five reuses are audited against references. Old visible-byte prefixes are checked separately so a truncated multibyte token is not misclassified from Unicode substring comparison.','',
 'The device uses both HP cores per board in one distributed lane,4+8 layers, full vocabulary, FP32 KV/scales/norms and32 MiB PSRAM/flash per board. Configured CPU360MHz, PSRAM200MHz and FreeRTOS1000Hz are not independent power/clock/temperature measurements. Tiny then Supra is fixed model order to minimize writes. KV resets per request. Prompt processing is repeated for each new full answer; this is not a KV-cache continuation benchmark.','',
 'After recording, higher-cap outputs were rated with model names, token IDs, wrappers and timing hidden; caps/EOS remained visible. Ratings were committed in'+u['ratings_commit'][:7]+' before the new mapping was unsealed. The same author knew old questions/answers/ratings and model styles. This is neither independent nor fully blind or cap-blinded review. Old ratings are unchanged; identical reused EOS answers must receive the same criterion judgments. All per-case notes and complete texts are exposed.','',
 'Longer text can complete a previously unfinished answer, but cannot erase a visible initial wrong answer or make extra prose satisfy an exact literal-copy request. Core and whole-response cleanliness remain separate. Uncertain semantic/unfinished judgments remain distinct from confirmed success and failure. Stories separately track topic, contradiction, requested resolution and exactly two sentences; EOS alone is not a resolution. No unseen output beyond the new limit is assumed.','',
 'Same deterministic prefixes isolate extra visible continuation under the retained engine; they do not prove source-FP32 fidelity or isolate training, quantization, model size or prompt effects. Questions are known and constructed, n=4/category, with possible pretraining overlap; one greedy trajectory does not support population ranking or statistical independence. Different tokenizers/native wrappers limit cross-model interpretation. More generated text changes work and wall time; no kernel-speed or energy-efficiency conclusion follows.','',
 '## Restoration and complete evidence','',
 'Genuine TinyBrainBot worker/coordinator artifacts were restored, model-bound peer configured, distributed W matched and both nodes reported0.9.0 ready/idle with queue0/running0. This is bounded recorded restoration evidence, not endurance or outage-injection qualification.','',
 '![Controlled intervention and physical setup](figures/quality-cap-v3-setup-2026-10-30.png)','',
 '[All paired full texts and notes](data/quality-cap-v3-2026-10-30/comparison.html), [protocol](data/quality-cap-v3-2026-10-30/protocol.json), [prospective plan](quality-cap-v3-plan-2026-10-30.md), [old study](quality-v2-2026-10-30.md), [paired results](data/quality-cap-v3-2026-10-30/paired-results.json), [summary](data/quality-cap-v3-2026-10-30/summary.json), [record audit](data/quality-cap-v3-2026-10-30/record-audit.json), [masked ratings](data/quality-cap-v3-2026-10-30/masked-ratings.json), [unblinding](data/quality-cap-v3-2026-10-30/unblinding.json) and [final state](data/quality-cap-v3-2026-10-30/final.json).','',
 'Offline recorded-data reproduction: `python tools/quality_cap_v3_results.py analyze`. Uses retained data only; host/device stages are explicit guarded actions. No new publication/upload is authorized by this local experiment.']
 (DOC/'quality-cap-v3-2026-10-30.md').write_bytes(('\n'.join(lines)+'\n').encode())
 files=[x for x in DATA.iterdir() if x.is_file() and x.name not in ['artifact-audit.json','verification.json']]+[DOC/'quality-cap-v3-2026-10-30.md',pathlib.Path(__file__)]+[DOC/'figures'/(name+'-2026-10-30'+ext) for name in ['quality-cap-v3-comparison','quality-cap-v3-setup'] for ext in ['.png','.svg','.json']]
 write(DATA/'artifact-audit.json',{'passed':True,'source_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in files}})
 print('Paired full-output viewer, report, two figures and artifact audit written.',flush=True)

if __name__=='__main__':main()
