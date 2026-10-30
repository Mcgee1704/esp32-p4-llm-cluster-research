"""Offline, provenance-aware model comparison: new timing / reused Tiny quality."""
import hashlib,json,pathlib,re,statistics,subprocess
from html import escape
from plot_matched_models import Canvas,MUTED
from p4_compare_metrics import paired_summary
from gptneo_p4_trial import verify
from supra_tiny_v09_trial import DATA,ROOT,PRIOR,TINY,PLAN,frozen,read,write,sha

DOC=ROOT/'docs/research'
NAMES={'tinybrainbot':'TinyBrainBot','supra':'Supra2-100M'}
COLORS={'tinybrainbot':'#178476','supra':'#7953a6'}

def save(c,name,sources):
 stem=DOC/'figures'/(name+'-2026-10-30')
 stem.with_suffix('.svg').write_text('\n'.join(c.s+['</svg>'])+'\n',encoding='utf-8')
 runtime=pathlib.Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
 code='require('+json.dumps(str(runtime/'node_modules/sharp'))+')(process.argv[1]).png().toFile(process.argv[2])'
 subprocess.run([str(runtime/'bin/node.exe'),'-e',code,str(stem.with_suffix('.svg')),str(stem.with_suffix('.png'))],check=True)
 write(stem.with_suffix('.json'),{'title':name,'date':'2026-10-30','sources':{x.relative_to(ROOT).as_posix():sha(x) for x in sources},'scope':'Same firmware0.9.0, fresh fixed-order timing;12 fresh Supra quality streams and12 explicitly reused Tiny quality streams. Historical 0.7.0 is not a fresh causal control. Author unblinded review inherited only after output equality.'})

def main():
 p,commit=frozen();h=read(DATA/'host-check.json');assert h['complete_generations']==30 and h['all_reference_equal'] and h['sources']==p['sources'] and h['archived_dll_preserved']
 assert all(x['full_logit_positions']==8 and x['scalar_tile4_logits_byte_identical'] for x in h['checks'].values())
 refs=read(PRIOR/'host-references.json');q=read(DATA/'quality-runs.json');t=read(DATA/'timing-runs.json');controls=read(DATA/'controls.json');final=read(DATA/'final.json')
 assert len(t)==12 and len(q)==12 and len(controls)==2 and final['completed'] and final['failure'] is None
 assert [(r['model'],r['case']) for r in q]==[('supra',c['id']) for c in p['cases']]
 assert [(r['model'],r['block'],r['case']) for r in t]==[(m,b,c) for m in ['tinybrainbot','supra'] for b in [1,2,3] for c in (['B2','B1'] if b==2 else ['B1','B2'])]
 assert [r['model'] for r in controls]==['tinybrainbot','supra']
 rows=t+q+controls+[final['restoration_control']];files=[]
 for row in rows:
  path=DATA/row['file'];assert path not in files;files.append(path)
  case='W' if row in controls or row==final['restoration_control'] else row['case']
  done=verify(path.read_bytes(),refs[row['model']][case]);assert done==row['done']
  assert done['boards']==2 and done['kernel']['mode']=='tile4' and done['kernel']['owner_core_mask']==2 and done['kernel']['helper_core_mask']==1
  assert done['prompt_tokens']==len(refs[row['model']][case]['prompt_tokens'])
 assert len(files)==27
 reused=[]
 for c in p['cases']:
  path=TINY/('quality-'+c['id']+'.ndjson');done=verify(path.read_bytes(),refs['tinybrainbot'][c['id']]);reused.append({'model':'tinybrainbot','case':c['id'],'origin':path.relative_to(ROOT).as_posix(),'sha256':sha(path),'evidence':'REUSED real0.9.0 stream, not new','done':done})
 for label,model in [('tinybrainbot-loaded','tinybrainbot'),('tinybrainbot-tested','tinybrainbot'),('supra-loaded','supra'),('supra-tested','supra'),('restored','tinybrainbot')]:
  states=read(DATA/(label+'-states.json'))
  for role,s in states.items():
   assert s['firmware']=='0.9.0' and s['model_ready'] and not s['worker_busy'] and not s['ota_pending']
   assert s['model_id']==p['artifacts'][model][role]['model_id'] and s['artifact_id']==p['artifacts'][model][role]['artifact_id']
 for role,s in final['devices'].items():
  assert s['firmware']=='0.9.0' and s['model_ready'] and not s['worker_busy'] and not s['ota_pending']
  assert s['model_id']==p['artifacts']['tinybrainbot'][role]['model_id'] and s['artifact_id']==p['artifacts']['tinybrainbot'][role]['artifact_id']
 assert final['queued']==final['running']==0 and final['mode']=='sharded'
 timing=paired_summary(t);old=read(PRIOR/'summary.json');counts=old['counts'];review=read(PRIOR/'manual-review.json')
 assert review['protocol_sha256']==sha(PRIOR/'protocol.json') and review['host_references_sha256']==sha(PRIOR/'host-references.json')
 assert len(review['rows'])==24 and {(x['model'],x['case']) for x in review['rows']}=={(m,c['id']) for m in NAMES for c in p['cases']}
 inherited={}
 for m in NAMES:
  inherited[m]={}
  for category in ['facts','grounded']:
   ids={c['id'] for c in p['cases'] if c['category']==category};rr=[x for x in review['rows'] if x['model']==m and x['case'] in ids]
   assert all(type(x['first']) is bool and (x['clean'] is None or type(x['clean']) is bool) for x in rr)
   inherited[m][category]={'n':len(rr),'first_correct':sum(x['first'] for x in rr),'confirmed_clean':sum(x['clean'] is True for x in rr),'uncertain_clean':sum(x['clean'] is None for x in rr)}
  exact=[c for c in p['cases'] if c['category']=='exact']
  inherited[m]['exact']={'n':len(exact),'correct':sum(refs[m][c['id']]['text'].strip()==c['expected'] for c in exact)}
  rr=[x for x in review['rows'] if x['model']==m and x['case'] in {c['id'] for c in p['cases'] if c['category']=='story'}]
  inherited[m]['story']={'n':len(rr),**{k:sum(x[k] for x in rr) for k in ['topic','coherent','resolution']}}
 assert inherited==counts, 'Inherited quality counts do not reproduce the original judgments'
 assert all(timing[c]['matched_capped_outputs'] and all(v['prompt_tokens']==(4 if c=='B1' else 6) for v in timing[c]['models'].values()) for c in ['B1','B2'])
 historical={};spans={}
 for c in ['B1','B2']:
  historical[c]={};spans[c]={}
  for m in NAMES:
   before=old['timing'][c]['models'][m]['total_median_seconds'];after=timing[c]['models'][m]['total_median_seconds']
   historical[c][m]={'historical0.7.0_seconds':before,'fresh0.9.0_seconds':after,'descriptive_time_reduction_percent':100*(1-after/before),'scope':'Across studies and fixed phase orders; not a new same-session causal control.'}
   ds=[x['done'] for x in t if x['model']==m and x['case']==c]
   spans[c][m]={k.replace('_ms','_seconds'):statistics.median(x['profile'][k] for x in ds)/1000 for k in ['master_compute_ms','worker_compute_ms']}
 write(DATA/'reused-tiny-quality.json',reused)
 summary={'timing':timing,'quality_counts':counts,'quality_basis':'Inherited existing unblinded judgments after exact response equality; not newly scored independent observations. Tiny physical quality reused explicitly.',
          'fresh_streams':27,'fresh_quality_streams':12,'reused_quality_streams':12,'inherited_quality_counts_reproduced':True,'historical_comparison':historical,'execution_span_medians_seconds':spans,'restored_tinybrainbot':True}
 write(DATA/'summary.json',summary)
 # Complete, local side-by-side response viewer.
 notes={(x['model'],x['case']):x.get('note','') for x in review['rows']}
 page=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Supra2 versus TinyBrainBot, firmware0.9.0</title>',
       '<style>body{font:17px system-ui;max-width:1400px;margin:32px auto;padding:0 20px;color:#193347;background:#eff4f8}section{border-top:1px solid #b8cbd8;padding:20px 0}.pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,450px),1fr));gap:32px}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:#185e94}</style>',
       '<h1>Same kernel, two models: complete observed responses</h1><p>Firmware0.9.0, row INT4, context256, two physical P4s. Supra outputs are fresh; Tiny outputs are reused from the immediately preceding0.9.0 study. Every response matches its archived native reference. Notes are inherited unblinded judgments, not an independent new rating.</p>']
 for case in p['cases']:
  page.append('<section><h2>'+escape(case['id']+' · '+case['category'])+'</h2><p>'+escape(case['user'])+'</p><div class="pair">')
  for m in NAMES:
   text=refs[m][case['id']]['text'];is_tiny=m=='tinybrainbot'
   url='../int4-pair-2026-10-30/quality-'+case['id']+'.ndjson' if is_tiny else 'supra-quality-'+case['id']+'.ndjson'
   page.append('<div><h3>'+NAMES[m]+' · '+('REUSED' if is_tiny else 'FRESH')+'</h3><details><summary>Native prompt</summary><pre>'+escape(p['inputs'][m][case['id']]['prompt'])+'</pre></details><pre>'+escape(text if text else '[Empty decoded text]')+'</pre><p>'+escape(notes[m,case['id']])+'</p><a href="'+url+'">Verified raw stream</a></div>')
  page.append('</div></section>')
 page.append('</html>');(DATA/'comparison.html').write_text('\n'.join(page),encoding='utf-8')
 # Primary scientific comparison figure.
 c=Canvas(1550,'Supra2 and TinyBrainBot: the same optimized INT4 kernel',
          'Two real P4s | firmware0.9.0 | tile4 byte-pair | context256 | 4+8 layers | 30 October 2026')
 c.text(48,153,'Fresh speed measurements: same raw prefix, 16 output tokens, n=3/model',28,weight='bold')
 for j,case in enumerate(['B1','B2']):
  x=48+j*772;c.rect(x,182,732,352);c.text(x+24,224,case+' · '+('Once upon a time' if case=='B1' else 'One day, a little girl'),24,weight='bold')
  maximum=max(timing[case]['models'][m]['total_range_seconds'][1] for m in NAMES)*1.13
  for i,m in enumerate(NAMES):
   y=289+i*82;z=timing[case]['models'][m];v=z['total_median_seconds'];lo,hi=z['total_range_seconds']
   c.text(x+24,y,NAMES[m],22);c.rect(x+220,y-23,v/maximum*340,29,COLORS[m],3)
   c.line(x+220+lo/maximum*340,y-9,x+220+hi/maximum*340,y-9,'#193347',3);c.text(x+706,y,f'{v:.3f} s',23,anchor='end')
  ratio=timing[case]['supra_over_tiny_total_median'];c.text(x+24,453,f'Index-matched Supra/Tiny time ratio: {ratio:.4f}',23,weight='bold')
  c.text(x+24,493,'Observed min–max; fixed model order; no significance test.',19,MUTED)
 c.text(48,590,'Historical 0.7.0 versus fresh0.9.0 — separate studies, not a fresh control',27,weight='bold')
 c.text(48,635,'Model / prefix',22,weight='bold');c.text(665,635,'Historical seconds',22,weight='bold');c.text(1120,635,'Fresh seconds',22,weight='bold')
 for i,(m,case) in enumerate((m,case) for m in NAMES for case in ['B1','B2']):
  y=681+i*47;v=historical[case][m];c.text(48,y,NAMES[m]+' / '+case,22)
  c.text(665,y,f'{v["historical0.7.0_seconds"]:.3f}',24);c.text(1120,y,f'{v["fresh0.9.0_seconds"]:.3f}',24,COLORS[m],weight='bold')
 c.text(48,919,'Retained quality judgments on exactly matching responses',28,weight='bold')
 c.text(48,959,'Tiny:12 reused actual0.9.0 cases. Supra:12 fresh cases. Same unblinded author; no new quality score.',21,MUTED)
 c.text(48,1008,'Criterion',22,weight='bold');c.text(1000,1008,'Tiny',22,COLORS['tinybrainbot'],'bold');c.text(1270,1008,'Supra',22,COLORS['supra'],'bold')
 for i,(label,key,field) in enumerate([('First factual answer','facts','first_correct'),('Confirmed clean factual response','facts','confirmed_clean'),('Exact requested output','exact','correct'),('Given facts: first answer','grounded','first_correct'),('Given facts: clean response','grounded','confirmed_clean'),('Full requested story topic','story','topic'),('Visible story resolution','story','resolution')]):
  y=1053+i*44;c.text(48,y,label,22)
  for m,x in [('tinybrainbot',1030),('supra',1300)]:c.text(x,y,f'{counts[m][key][field]}/{counts[m][key]["n"]}',24,COLORS[m],'bold','middle')
 c.text(48,1410,'Tiny grounded G01 uses a generous box criterion; strict explicit-red scoring reduces its count by one.',21,MUTED)
 c.text(48,1452,'Supra has one additional uncertain grounded-clean judgment. No pooled score or general model ranking.',21,MUTED)
 c.text(48,1505,'Same speed-prefix token counts4/6; model token IDs and generated words differ. Tiny restored, queue empty.',21,MUTED)
 helpers=[ROOT/'tools/p4_compare_metrics.py',ROOT/'tools/plot_matched_models.py']
 evidence=[DATA/'protocol.json',DATA/'host-check.json',DATA/'summary.json',DATA/'reused-tiny-quality.json',DATA/'final.json',PRIOR/'manual-review.json',pathlib.Path(__file__),*helpers]
 save(c,'supra-tiny-v09-comparison',evidence)
 # Evidence flow and real topology: fresh and reused are visibly different.
 c=Canvas(1050,'One physical P4 pair; explicit evidence reuse',
          'Firmware0.9.0 stays installed | model-only private-LAN switches | existing local artifacts, no downloads')
 c.rect(48,145,1504,135);c.text(800,190,'Same LAN client → coordinator → worker → coordinator',29,weight='bold',anchor='middle')
 c.text(800,237,'One sharded request lane. Both boards participate in every inference.',24,MUTED,anchor='middle')
 for x,title,lines in [(48,'Coordinator P4',['Layers0–3 + tokenizer + tied embedding/output','32MiB PSRAM / 32MiB flash']), (848,'Worker P4',['Layers4–11 + its own FP32 KV state','32MiB PSRAM / 32MiB flash'])]:
  c.rect(x,320,704,174);c.text(x+24,362,title,28,weight='bold')
  for i,line in enumerate(lines):c.text(x+24,410+i*42,line,23,MUTED)
 c.arrow(752,383,848,383);c.arrow(848,451,752,451,'#178476');c.text(800,359,'LAN',20,anchor='middle')
 c.text(48,551,'Fresh measurements',28,weight='bold')
 for i,(title,lines) in enumerate([('TinyBrainBot first',['Warmup4 + six timing streams','Existing genuine model stays loaded']),('Supra2 second',['Warmup4 + six timing +12 quality','Load true worker, then coordinator']),('Restore TinyBrainBot',['Load true roles, reconfigure peer','W control4; both ready/idle'])]):
  x=48+i*510;c.rect(x,584,484,165);c.text(x+22,625,title,25,weight='bold')
  for j,line in enumerate(lines):c.text(x+22,674+j*38,line,21,MUTED)
 c.rect(48,800,1504,180,'#dce9f2');c.text(72,844,'REUSED separately:12 Tiny quality streams from the preceding0.9.0 study',26,weight='bold')
 c.text(72,886,'Hashes and native-reference equality checked. Not counted as fresh data or new quality samples.',23)
 c.text(72,930,'27 fresh real streams +12 reused streams. Host:30 generations +8 logit positions/model.',23)
 c.text(48,1023,'Fixed model order limits causal/ranking claims. Restoring weights is tested; no firmware or partition change.',21,MUTED)
 save(c,'supra-tiny-v09-setup',evidence)
 # Report generated only after all data and restoration have passed audit.
 lines=['# Supra2 and TinyBrainBot on the optimized INT4 pair kernel','',
        '30 October 2026. Completed local experiment on the same two physical ESP32-P4 revision1.3 boards, firmware0.9.0. No downloads, new firmware build, re-quantization or partition change. TinyBrainBot restored on both boards after testing.','',
        '## Fresh speed comparison','',
        '| Prefix | Tiny median s | Tiny observed range s | Supra median s | Supra observed range s | Index-matched Supra/Tiny ratio |',
        '|---|---:|---|---:|---|---:|']
 for case in ['B1','B2']:
  a=timing[case]['models']['tinybrainbot'];b=timing[case]['models']['supra'];lines.append(f'| {case} | {a["total_median_seconds"]:.6f} | {a["total_range_seconds"][0]:.6f}–{a["total_range_seconds"][1]:.6f} | {b["total_median_seconds"]:.6f} | {b["total_range_seconds"][0]:.6f}–{b["total_range_seconds"][1]:.6f} | {timing[case]["supra_over_tiny_total_median"]:.6f} |')
 lines+=['','![Model comparison](figures/supra-tiny-v09-comparison-2026-10-30.png)','',
 'Each prefix has three actual timing repetitions per model,16 output tokens without EOS and exactly4/6 input tokens for B1/B2. Input bytes match; vocabularies/token IDs and generated words differ. These are deployed-system latency observations, not an isolated arithmetic benchmark or meaningful-answer throughput. The index-matched ratio uses repeat number, not randomized/interleaved model pairs. Model order is fixed Tiny then Supra to limit model writes. Min/max are observed ranges, not confidence intervals; small differences do not establish a reliable winner.','',
 'Median first-token latency and execution spans (spans include memory stalls, scheduling and pauses):','',
 '| Model / prefix | First token s | Coordinator execution s | Worker execution s |','|---|---:|---:|---:|']
 for m in NAMES:
  for case in ['B1','B2']:
   z=spans[case][m];first=timing[case]['models'][m]['ttft_median_seconds']
   lines.append(f'| {NAMES[m]} / {case} | {first:.6f} | {z["master_compute_seconds"]:.6f} | {z["worker_compute_seconds"]:.6f} |')
 lines+=['','## Historical old-kernel context','',
 '| Model / prefix | Historical 0.7.0 s | Fresh0.9.0 s | Descriptive reduction % |','|---|---:|---:|---:|']
 for m in NAMES:
  for case in ['B1','B2']:
   x=historical[case][m];lines.append(f'| {NAMES[m]} / {case} | {x["historical0.7.0_seconds"]:.6f} | {x["fresh0.9.0_seconds"]:.6f} | {x["descriptive_time_reduction_percent"]:.3f} |')
 lines+=['','These old measurements come from the separate matched0.7.0 experiment. They are not a new same-session old-kernel control for Supra. The prior Tiny byte-pair trial separately measured its own fresh before/after intervention. No source/configuration/temperature ablation isolates every contribution to differences between studies.','',
 '## Answer quality and evidence reuse','',
 'All12 fresh Supra quality streams and12 reused actual Tiny0.9.0 quality streams match the pinned native token IDs, complete decoded output and EOS. Therefore the existing manual judgments are carried forward, not silently rescored. The twelve Tiny cases were generated in the immediately preceding kernel trial and are individually hash-bound here; they are not new observations or included in this study\'s fresh timing samples. The same author reviewed them unblinded, with no independent rater. Known mistakes remain unchanged.','',
 '| Criterion | TinyBrainBot | Supra2 |','|---|---:|---:|']
 for label,key,field in [('First factual answer','facts','first_correct'),('Confirmed clean factual response','facts','confirmed_clean'),('Exact output','exact','correct'),('Grounded first answer','grounded','first_correct'),('Grounded clean response','grounded','confirmed_clean'),('Full story topic','story','topic'),('Visible story resolution','story','resolution')]:
  lines.append('| '+label+' | '+' | '.join(str(counts[m][key][field])+'/'+str(counts[m][key]['n']) for m in NAMES)+' |')
 lines+=['','Tiny grounded G01 is a generous pass for box without explicit red. Strict explicit-colour scoring reduces Tiny grounded first/clean from2/2 to1/2; this is an inherited sensitivity, not a changed primary rule. Supra also has one uncertain grounded-clean judgment, additional to zero confirmed clean. No material contradiction is a separate story criterion and can pass an off-topic story; it must not be presented as successful story completion. No pooled quality score, new held-out benchmark, population ranking or new language competence follows.','',
 'The observed first-fact counts tie at 3/6. Tiny has 3/6 confirmed clean factual responses versus 2/6 for Supra2, but this small retained set is insufficient for a general best-model claim. Neither model satisfies either exact-output case or the full topic/resolution criteria for the two stories. The faster kernel preserves the answers; it does not improve their truth or instruction-following.','',
 '[All complete model responses, native wrappers and inherited notes](data/supra-tiny-v09-2026-10-30/comparison.html).','',
 '## Implementation, memory and physical setup','',
 'Both complete-vocabulary row-INT4 models use the unchanged production byte-pair tile4 loop, FP32 scales/norms/KV, context256 and a4+8 layer split. Coordinator keeps tokenizer/embedding/output; worker keeps layers4–11. Both HP cores participate on each board. Same firmware0.9.0; configured CPU360MHz, PSRAM200MHz, FreeRTOS1000Hz;32MiB PSRAM/flash per board. Clocks, temperature and power were not independently measured. No SD or board-to-board USB test.','',
 'Both artifact families are the exact locally retained source-pinned files from the earlier matched study, authenticated by full hashes and model/artifact IDs. TinyBrainBot has 100092672 parameters (Llama), Supra2 has 100684032 (Qwen3 with Q/K head normalization). Norm/architecture differences and tokenizer output differ, so model comparison does not isolate training, parameter count or tokenizer effects.','',
 '| Model | Coordinator free PSRAM bytes after trial | Worker free PSRAM bytes after trial |','|---|---:|---:|']
 for m in NAMES:
  s=read(DATA/(m+'-tested-states.json'));lines.append(f'| {NAMES[m]} | {s["coordinator"]["free_psram"]} | {s["worker"]["free_psram"]} |')
 lines+=['','These are reported free allocator bytes after the trial, not an exhaustive memory/fragmentation stress test. Coordinator and worker execution-span medians, including memory stalls/scheduling/pauses, are retained in summary.json. RPC total includes worker execution; do not add RPC and worker time.','',
 '![Experimental setup and evidence reuse](figures/supra-tiny-v09-setup-2026-10-30.png)','',
 '## Checks, restoration and reproduction','',
 'Before physical writes,30 full candidate-native generations match archived references, including prompt-token IDs. Eight full-vocabulary logit vectors per model match the scalar-row path byte-for-byte. The historical DLL is preserved; the existing isolated candidate DLL is hash-bound to the accepted byte-pair source. All95 local tests pass. These bounded checks are not exhaustive for every possible input.','',
 'All27 new streams and12 reused streams are independently re-audited offline. Twelve fresh timing streams are kept apart from the quality cases and warmups. Model switching invalidates the saved model-bound peer configuration; the harness explicitly reconfigures the peer after each switch. In finally it restores genuine Tiny roles, reconfigures the peer, performs the four-token distributed native-reference control and verifies both0.9.0 nodes ready/idle with queue0/running0. No firmware replacement was necessary.','',
 'The plan/protocol and trial script were committed before new generations ('+commit[:7]+'). Source hashes, artifacts, all retained responses, fresh and reused counts, role identities and the final state are checked by `python tools/analyze_supra_tiny_v09.py`, which is offline. The explicit `supra_tiny_v09_trial.py device` stage performs real private-LAN writes and refuses to overwrite a completed start record; do not run it to regenerate charts.','',
 'Evidence: [plan](supra-tiny-v09-plan-2026-10-30.md), [protocol](data/supra-tiny-v09-2026-10-30/protocol.json), [host checks](data/supra-tiny-v09-2026-10-30/host-check.json), [summary](data/supra-tiny-v09-2026-10-30/summary.json), [reuse receipt](data/supra-tiny-v09-2026-10-30/reused-tiny-quality.json), [final state](data/supra-tiny-v09-2026-10-30/final.json), [verification](data/supra-tiny-v09-2026-10-30/verification.json), [audit](data/supra-tiny-v09-2026-10-30/audit.json). Author self-review, no independent reviewer. All project data stayed local/private LAN; no public transfer.']
 (DOC/'supra-tiny-v09-2026-10-30.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 sources=[x for x in DATA.iterdir() if x.suffix in ['.json','.ndjson','.html','.sha256'] and x.name!='audit.json']+[DOC/'supra-tiny-v09-2026-10-30.md',PLAN,pathlib.Path(__file__),*helpers]
 sources += [DOC/'figures'/(name+'-2026-10-30'+ext) for name in ['supra-tiny-v09-comparison','supra-tiny-v09-setup'] for ext in ['.png','.svg','.json']]
 receipt={'fresh_streams_checked':27,'reused_streams_checked':12,'restored_tinybrainbot':True,'source_sha256':{x.relative_to(ROOT).as_posix():sha(x) for x in sorted(sources)}}
 write(DATA/'audit.json',receipt)
 print(json.dumps({'ratios':{c:timing[c]['supra_over_tiny_total_median'] for c in timing},'fresh_streams':27,'reused_streams':12,'restored_tinybrainbot':True}))

if __name__=='__main__':main()
