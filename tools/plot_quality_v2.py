"""English recorded-data report, full response viewer and standalone figures."""
import json,pathlib,subprocess
from html import escape
from plot_matched_models import Canvas,MUTED
from quality_v2_results import ROOT,DATA,read,write,sha,audit_recorded,validate_ratings
DOC=ROOT/'docs/research'
NAMES={'tinybrainbot':'TinyBrainBot','supra':'Supra2-100M'}
COLORS={'tinybrainbot':'#178476','supra':'#7953a6'}
CATS={'facts':'Basic facts','reasoning':'Arithmetic / reasoning','exact':'Literal output format','grounded':'Context / dialogue','uncertainty':'Missing information','story':'Short narratives'}
def save(c,name,sources):
 stem=DOC/'figures'/(name+'-2026-10-30');stem.with_suffix('.svg').write_bytes(('\n'.join(c.s+['</svg>'])+'\n').encode('utf-8'))
 runtime=pathlib.Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node';code='require('+json.dumps(str(runtime/'node_modules/sharp'))+')(process.argv[1]).png().toFile(process.argv[2])'
 subprocess.run([str(runtime/'bin/node.exe'),'-e',code,str(stem.with_suffix('.svg')),str(stem.with_suffix('.png'))],check=True)
 write(stem.with_suffix('.json'),{'title':name,'date':'2026-10-30','source_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in sources},'scope':'24 constructed English tasks,48 new real-device answers,51 actual streams. Same-author model-label-masked review, not independent/fully blind. Criteria and cases frozen before answers; ratings committed before unmasking. No pooled ranking or quality-case speed comparison.'})
def main():
 p,raw,refs,paths=audit_recorded();validate_ratings();s=read(DATA/'summary.json');rows=read(DATA/'reviewed-results.json');counts=s['counts'];u=read(DATA/'unblinding.json')
 sources=[DATA/x for x in ['protocol.json','cases.json','summary.json','masked-responses.json','masked-ratings.json','unblinding.json','reviewed-results.json','record-audit.json','final.json']]+[ROOT/'tools/quality_v2_results.py',ROOT/'tools/plot_matched_models.py',pathlib.Path(__file__)]
 c=Canvas(1580,'Broader quality V2: TinyBrainBot versus Supra2',
          '24 new English tasks ·48 fresh two-P4 answers · firmware0.9.0 / row INT4 / context256 /4+8 layers')
 c.text(48,150,'Separate criteria, four tasks per category — no pooled model score',28,weight='bold')
 for i,(cat,title) in enumerate(CATS.items()):
  y=215+i*138;c.text(48,y,title,26,weight='bold')
  desc='First responsive core / confirmed clean' if cat not in ['exact','story'] else 'Exact literal equality only' if cat=='exact' else 'Full topic / strict four-criterion completion'
  c.text(48,y+32,desc,18,MUTED)
  for j,m in enumerate(NAMES):
   d=counts[cat][m];a=d.get('core',d.get('exact',d.get('topic',0)));b=d.get('confirmed_clean',d.get('exact',d.get('strict_completion',0)));yy=y-18+j*51
   c.text(500,yy+21,NAMES[m],21,COLORS[m],'bold');x=690;width=550
   c.rect(x,yy,width,24,'#dfe8ed',3);c.rect(x,yy,a/4*width,24,'#b7cbd4',3);c.rect(x,yy,b/4*width,24,COLORS[m],3)
   suffix=f'; {d["uncertain_clean"]} uncertain' if d.get('uncertain_clean') else ''
   c.text(1270,yy+21,f'{a}/4 · {b}/4'+suffix,20)
 c.rect(48,1090,732,310);c.text(72,1134,'Missing-information controls',27,weight='bold')
 c.text(72,1174,'Correct core / confirmed clean',21,MUTED)
 for i,g in enumerate(['unanswerable','answerable']):
  y=1222+i*91;c.text(72,y,('Not provided' if g=='unanswerable' else 'Answer supplied'),23,weight='bold')
  for m,x in [('tinybrainbot',330),('supra',570)]:
   d=counts['uncertainty'][m]['subgroups'][g];c.text(x,y,NAMES[m],20,COLORS[m],'bold');c.text(x,y+35,f'{d["core"]}/2 · {d["confirmed_clean"]}/2',24)
 c.rect(804,1090,748,310);c.text(828,1134,'Story criteria',27,weight='bold')
 c.text(1290,1134,'Tiny',20,COLORS['tinybrainbot'],'bold','end');c.text(1470,1134,'Supra',20,COLORS['supra'],'bold','end')
 for i,(key,title) in enumerate([('topic','Requested topic'),('coherent','No material contradiction'),('resolution','Visible resolution'),('two_sentences','Exactly two sentences')]):
  y=1184+i*51;c.text(828,y,title,22)
  for m,x in [('tinybrainbot',1290),('supra',1470)]:c.text(x,y,f'{counts["story"][m][key]}/4',24,COLORS[m],'bold','end')
 c.text(48,1451,'Label masking reduces model-name cues; same author remains the reviewer. No independent or complete-blinding claim.',21,MUTED)
 c.text(48,1495,'Caps:16 tokens for short tasks,48 for stories. Visible capped responses only; unknown cleanliness stays uncertain.',21,MUTED)
 c.text(48,1539,'Familiar constructed tasks may overlap pretraining. n=4/category (2 per uncertainty control). No population ranking.',21,MUTED)
 save(c,'quality-v2-comparison',sources)
 c=Canvas(1150,'Broader quality V2: protocol, physical setup and masking',
          'Existing local model artifacts · no downloads / firmware changes · original protocol commit0d5f664')
 for i,title in enumerate(CATS.values()):
  x=48+(i%3)*510;y=145+(i//3)*112;c.rect(x,y,484,90);c.text(x+24,y+37,title,24,weight='bold');c.text(x+24,y+71,'4 new tasks',21,MUTED)
 c.rect(48,410,704,160);c.text(72,453,'Coordinator P4',28,weight='bold');c.text(72,498,'Tokenizer, embedding/output, layers0–3',23);c.text(72,541,'32MiB PSRAM /32MiB flash',22,MUTED)
 c.rect(848,410,704,160);c.text(872,453,'Worker P4',28,weight='bold');c.text(872,498,'Layers4–11, own FP32 KV',23);c.text(872,541,'32MiB PSRAM /32MiB flash',22,MUTED);c.arrow(752,465,848,465);c.arrow(848,525,752,525,'#178476');c.text(800,440,'LAN',20,anchor='middle')
 c.text(48,632,'Tiny24 → Supra24 → restore Tiny. Both boards cooperate in every answer.',27,weight='bold')
 steps=[('Before answers','Freeze24 tasks + criteria + inputs','Commit model-label mapping hash'),('Recorded execution','48 native references + known controls','48 real answers +3 control streams'),('After recording','Model-label-masked A/B ratings','Commit ratings, then unseal mapping')]
 for i,(title,a,b) in enumerate(steps):
  x=48+i*510;c.rect(x,675,484,165);c.text(x+23,719,title,25,weight='bold');c.text(x+23,767,a,21,MUTED);c.text(x+23,805,b,21,MUTED)
 c.rect(48,891,1504,174,'#dce9f2');c.text(72,936,'No quality-output reuse; exact runtime reference equality for all51 streams.',27,weight='bold')
 c.text(72,981,'Same assistant designed tasks and judged outputs. Style/length may reveal identity despite labels.',23)
 c.text(72,1024,'Final recorded state: genuine TinyBrainBot restored on both0.9.0 boards; ready/idle, queue empty.',23)
 c.text(48,1111,'Different native wrappers/tokenizers; greedy outputs; fixed model order. Quality-case durations are unequal work.',21,MUTED)
 save(c,'quality-v2-setup',sources)
 # Full raw-visible text, scores, reasons and label assignment after unmasking.
 page=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Broader P4 quality V2</title><style>body{font:17px system-ui;max-width:1400px;margin:32px auto;padding:0 20px;color:#193347;background:#eff4f8}section{border-top:1px solid #b8cbd8;padding:20px 0}.pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,450px),1fr));gap:32px}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:#185e94}</style><h1>All24 new tasks: complete actual responses and review</h1><p>48 fresh real two-P4 outputs, firmware0.9.0. Model-label-masked same-author review, committed before mapping disclosure. Not independent or completely blind. No omitted failures or partial-answer cropping.</p>']
 for case in p['cases']:
  page.append('<section><h2>'+case['id']+' · '+CATS[case['category']]+'</h2><p>'+escape(case['user'])+'</p><p>Frozen criterion: '+escape(case['expected'])+'</p><div class="pair">')
  for m in NAMES:
   rr=next(x for x in rows if x['case']==case['id'] and x['model']==m);response=refs[m][case['id']];actual=next(x for x in raw if x['case']==case['id'] and x['model']==m)
   rating={k:rr[k] for k in ['core','clean','exact','topic','coherent','resolution','two_sentences'] if k in rr}
   page.append('<div><h3>'+NAMES[m]+' · masked label '+rr['label']+'</h3><pre>'+escape(response['text'] or '[Empty decoded text]')+'</pre><p>'+escape(json.dumps(rating))+'</p><p>'+escape(rr['note'])+'</p><p>'+str(rr['output_tokens'])+' output tokens · EOS '+str(rr['eos'])+' · cap '+str(rr['cap_reached'])+'</p><details><summary>Native prompt</summary><pre>'+escape(p['inputs'][m][case['id']]['prompt'])+'</pre></details><a href="'+actual['file']+'">Actual raw stream</a></div>')
  page.append('</div></section>')
 page.append('</html>');(DATA/'comparison.html').write_bytes('\n'.join(page).encode('utf-8'))
 lines=['# Broader quality V2: new tasks on TinyBrainBot and Supra2','',
 '30 October2026. Twenty-four prospective English tasks,48 fresh actual two-P4 answers, no reused quality observations. Greedy row INT4 on firmware0.9.0, production byte-pair tile4, context256 and4+8 model shards. TinyBrainBot restored on both boards after the run.','',
 '## Study scope and primary results','',
 '| Category (4 tasks) | Tiny core / confirmed clean | Supra core / confirmed clean |','|---|---|---|']
 for cat in CATS:
  vals=[]
  for m in NAMES:
   d=counts[cat][m]
   vals.append(f'{d["exact"]}/4 exact' if cat=='exact' else f'{d["topic"]}/4 topic; {d["strict_completion"]}/4 strict completion' if cat=='story' else f'{d["core"]}/4 core; {d["confirmed_clean"]}/4 clean; {d["uncertain_clean"]} uncertain')
  lines.append('| '+CATS[cat]+' | '+' | '.join(vals)+' |')
 lines+=['','![Category comparison](figures/quality-v2-comparison-2026-10-30.png)','',
 'Results are descriptive within this constructed sample. A correct first answer is not automatically a wholly correct response. Uncertain cleanliness remains separate; it is not silently treated as a success. The literal-format category tests exact copies, not a semantic JSON parser. Story topic, coherence, narrated resolution and exactly two sentences remain separate; strict completion requires all four. No pooled best-model score.','',
 'Different questions, review framing and short-task caps (16 here versus24 in the earlier matched set) prevent direct pooling with prior quality rates or interpreting changed rates as a model improvement. No weights or inference rule were improved in this study. Context/dialogue cases are supplied excerpts within one request, not an evaluation of persistent multi-turn memory.','',
 '## Interpretation of the new observations','',
 'Within these cases, TinyBrainBot has more correct first responsive answers in facts (1/4 versus0/4), reasoning (2/4 versus0/4), supplied context (2/4 versus0/4) and the combined missing-information/control category (4/4 versus1/4). Confirmed wholly clean responses are much rarer: Tiny records0/4,1/4,2/4 and2/4 respectively; Supra records0/4 in each. Four semantic/unfinished-response judgments remain uncertain across the two models and are not counted as confirmed successes. This supports retaining Tiny as the current experimental baseline, not certifying a generally reliable assistant.','',
 'Tiny correctly computes four plus three in R01, retrieves Ben\'s turtle in G02 and explicitly acknowledges the unknown card count in U02. The same model still invents a brown cup in G04 despite the supplied yellow record and adds an unsupported alternative to the supplied locker code in U03. Supra fails the subtraction with nine remaining and treats the shop name as an address. Full text and notes, including successful and failed cases, are retained together.','',
 'Both models fail all four exact-literal tasks and all four strict story completions. Supra has3/4 contradiction-free story outputs versus Tiny2/4, but this criterion alone rewards neither the requested topic nor a completed ending: unrelated or repetitive text can avoid contradiction while failing the task. Tiny narrates a fox returning the lantern in S03 but introduces mutually inconsistent sleep states and an extra sentence fragment. A hat-found claim in S01 does not repair the missing snail-loss/robin-help narrative.','',
 'All24 Supra answers and19/24 Tiny answers reach the output cap. The cap constrains what can be concluded about eventual completion; it does not erase already visible wrong arithmetic, wrong supplied facts or literal-format violations. No longer continuation was sampled. A future cap-sensitivity or prompt/template experiment needs a new frozen protocol, fresh outputs and separate reporting. Quality-case wall times reflect different token counts and tokenizers; the previously recorded fixed-prefix timing study remains the speed evidence.','',
 'Runtime-reference equality demonstrates that the P4 pair reproduced the retained quantized native engine for these inputs; it does not establish FP32/source-model fidelity or explain whether limited capacity, original training, quantization, prompting or short caps caused a quality failure. No causal allocation among those factors was tested here.','',
 '## Prospective inputs, review and limitations','',
 'Cases, expected criteria, native wrappers, input IDs, artifact/source hashes, output caps and balanced A/B mapping commitment were committed before any candidate answers in0d5f664. All24 exact user-task strings are absent from18 earlier committed protocols. This is novelty relative to our recorded strings, not evidence of pretraining-held-out tasks; familiar task templates and topics overlap earlier work. Neither questions nor caps were selected after viewing candidate answers.','',
 'Four tasks each cover facts, arithmetic/logical reasoning, exact format, provided context/dialogue, missing information and short stories. Missing-information behavior includes two genuinely unanswerable cases and two supplied-answer controls. All short-task caps are16 and story caps48. At most1024 quality output tokens were allowed across both models; EOS stops earlier. The visible capped response is the evaluation boundary; no unseen continuation is assumed.','',
 'After recording and restoring the cluster, A/B texts were shown without model name, timing, token IDs or native wrapper. EOS/cap status and frozen task criteria were visible. The same assistant rated all48 label-masked responses; these ratings were committed in'+u['ratings_commit'][:7]+' before copying the committed mapping into the unblinding receipt. The random nonce/mapping reproduce the original SHA256 commitment. No post-unblinding rating change is silently allowed.','',
 'The author also designed and executed the study and knew the model families. Style, length or self-identification can disclose the model. Therefore this is model-label masking, not independent assessment or complete blinding. Only four constructed cases/category (two per uncertainty subgroup), one greedy trajectory and one English framing pair are tested. No population ranking, confidence/significance guarantee, German-language proficiency or general-assistant qualification follows. A broader set is still not a representative standardized benchmark.','',
 '## Runtime, order and restoration','',
 'The same two physical revision1.3 P4s run each model in a single distributed inference lane. Both HP cores per board are configured; full vocabularies, FP32 KV/scales/norms,32MiB PSRAM/flash per board and existing24MiB model partitions remain. Configured CPU360MHz, PSRAM200MHz and FreeRTOS1000Hz are not independent clock/temperature/power measurements. No firmware build/update, partition change, model download or re-quantization occurred.','',
 'Existing accepted native DLL generated48 new full references and two known W controls. The known controls remain exactly equal to their earlier references. Archived DLL and genuine artifact hashes are preserved;95 existing local tests passed against the candidate DLL. Host reference correctness is distinct from answer quality. All51 new physical streams (48 tasks, two warmups and one restoration control) match model-specific token IDs, full decoded text and EOS, with both boards reported and coordinator owner/helper core masks checked.','',
 'Task order round-robins the six categories, identically for both models. Tiny runs first, Supra second; fixed model order minimizes writes and is not randomized. KV resets per request. Model-native wrappers/tokenizers differ. Quality durations have unequal actual output lengths and are not an equal-work model speed comparison. No inference retry or repeated quality sample was used. Device/runtime failures would abort further requests and trigger restoration.','',
 'Finally genuine Tiny worker/coordinator artifacts were reloaded, model-bound peer configured, distributed W verified and both nodes checked on0.9.0 ready/idle with queue0/running0. Restoration is recorded evidence, not an endurance, outage-injection or automatic factory-onboarding acceptance.','',
 '![Physical setup and review flow](figures/quality-v2-setup-2026-10-30.png)','',
 '## Complete evidence and offline reproduction','',
 '[All full texts, frozen criteria and notes](data/quality-v2-2026-10-30/comparison.html), [protocol](data/quality-v2-2026-10-30/protocol.json), [case list](data/quality-v2-2026-10-30/cases.json), [masked responses](data/quality-v2-2026-10-30/masked-responses.json), [committed masked ratings](data/quality-v2-2026-10-30/masked-ratings.json), [unblinding receipt](data/quality-v2-2026-10-30/unblinding.json), [summary](data/quality-v2-2026-10-30/summary.json), [raw audit](data/quality-v2-2026-10-30/record-audit.json), [final state](data/quality-v2-2026-10-30/final.json) and [prospective plan](quality-v2-plan-2026-10-30.md).','',
 'Recorded-data analysis: `python tools/quality_v2_results.py analyze`. This stage uses saved data, not weights, native inference or LAN. The explicit trial prepare/host/device stages require the pinned recording environment/assets and refuse overwrite. Historical protocol hashes and source guards must not be disabled to present saved output as a new experiment. All project data remain local/private LAN until a separately approved publication payload is prepared.']
 (DOC/'quality-v2-2026-10-30.md').write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
 figure_files=[DOC/'figures'/(name+'-2026-10-30'+ext) for name in ['quality-v2-comparison','quality-v2-setup'] for ext in ['.png','.svg','.json']]
 allfiles=[x for x in DATA.iterdir() if x.is_file() and x.name!='artifact-audit.json']+figure_files+[DOC/'quality-v2-2026-10-30.md',pathlib.Path(__file__)]
 write(DATA/'artifact-audit.json',{'passed':True,'actual_streams':51,'quality_outputs':48,'source_and_output_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(allfiles)}})
 print('Report, two figures, full48-answer viewer and output audit written.',flush=True)
if __name__=='__main__':main()
