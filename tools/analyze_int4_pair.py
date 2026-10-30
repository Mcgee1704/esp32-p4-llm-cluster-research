"""Offline audit and English figures of the real TinyBrainBot kernel trial."""
import hashlib,json,pathlib,statistics,subprocess
from html import escape
from plot_matched_models import Canvas,MUTED
from gptneo_p4_trial import verify
ROOT=pathlib.Path(__file__).resolve().parents[1];DOC=ROOT/'docs/research';DATA=DOC/'data/int4-pair-2026-10-30'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n',encoding='utf-8')
def main():
 p=read(DATA/'protocol.json');prior=DOC/'data/matched-p4-2026-10-30';host=read(DATA/'host-check.json')
 assert p['plan_sha256']==sha(DOC/'int4-pair-plan-2026-10-30.md')
 assert p['script_sha256']==sha(ROOT/'tools/int4_pair_trial.py')
 assert p['prior_protocol_sha256']==sha(prior/'protocol.json') and p['prior_refs_sha256']==sha(prior/'host-references.json')
 for receipt in [host,read(DATA/'candidate-image.json')]:
  assert all(sha(ROOT/n)==h for n,h in receipt['sources'].items())
 assert host['tests']==95 and host['tests_passed'] and host['all_logits_bit_identical_to_scalar']
 assert sha(ROOT/'.local/build/tinyllm.dll')==host['archived_dll_sha256']
 assert sha(ROOT/'.local/int4-pair-2026-10-30/tinyllm-pair.dll')==host['candidate_dll_sha256']
 refs=read(prior/'host-references.json')['tinybrainbot'];protocol=read(prior/'protocol.json');streams=[];summary={}
 for phase in ['baseline','candidate']:
  runs=read(DATA/(phase+'-runs.json'));assert len(runs)==7
  assert [(x['block'],x['case']) for x in runs]==[(0,'W'),(1,'B1'),(1,'B2'),(2,'B2'),(2,'B1'),(3,'B1'),(3,'B2')]
  for x in runs:
   file=DATA/f'{phase}-{x["block"]}-{x["case"]}.ndjson';done=verify(file.read_bytes(),refs[x['case']]);assert done==x['done'];streams.append(file)
   assert done['boards']==2 and done['kernel']['mode']=='tile4'
  summary[phase]={}
  for case in ['B1','B2']:
   rows=[x['done'] for x in runs if x['case']==case];metrics={}
   for key in ['elapsed_ms','ttft_ms','master_compute_ms','worker_compute_ms']:
    values=[x[key] if key in x else x['profile'][key] for x in rows]
    metrics[key]={'median':statistics.median(values),'range':[min(values),max(values)]}
   summary[phase][case]=metrics
 quality=read(DATA/'quality.json');assert [x['case'] for x in quality]==[c['id'] for c in protocol['cases']]
 for x in quality:
  file=DATA/('quality-'+x['case']+'.ndjson');assert verify(file.read_bytes(),refs[x['case']])==x['done'];streams.append(file)
 page=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TinyBrainBot kernel regression outputs</title>',
       '<style>body{font:17px system-ui;max-width:1100px;margin:32px auto;padding:0 20px;color:#193347;background:#eff4f8}section{border-top:1px solid #b8cbd8;padding:20px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:#185e94}</style>',
       '<h1>TinyBrainBot: all 12 real-device regression outputs</h1><p>Firmware0.9.0, same genuine INT4 model on two P4s. Every token ID, decoded text and EOS matches the archived native reference. Equality preserves existing answer errors too; it is not an independent quality improvement.</p>']
 for x,cse in zip(quality,protocol['cases']):
  text=refs[x['case']]['text'];done=x['done'];prompt=protocol['inputs']['tinybrainbot'][x['case']]['prompt']
  page.append('<section><h2>'+escape(x['case']+' · '+cse['category'])+'</h2><pre>'+escape(prompt)+'</pre><h3>Actual response</h3><pre>'+escape(text if text else '[Empty decoded text]')+'</pre><p>'+str(done['output_tokens'])+' output tokens · '+f'{done["elapsed_ms"]/1000:.3f}'+' s · EOS '+str(done['eos'])+' · exact reference match</p><a href="quality-'+x['case']+'.ndjson">Raw stream</a></section>')
 page.append('</html>');(DATA/'comparison.html').write_text('\n'.join(page),encoding='utf-8')
 file=DATA/'final-control.ndjson';verify(file.read_bytes(),refs['W']);streams.append(file)
 decision=read(DATA/'decision.json');final=read(DATA/'final.json');keep=True;ratios={}
 for case in ['B1','B2']:
  b=[x['done']['elapsed_ms'] for x in read(DATA/'baseline-runs.json') if x['case']==case]
  n=[x['done']['elapsed_ms'] for x in read(DATA/'candidate-runs.json') if x['case']==case]
  ratio=statistics.median(x/y for x,y in zip(b,n));ratios[case]=ratio
  keep=keep and statistics.median(n)<statistics.median(b)
  for key in ['master_compute_ms','worker_compute_ms']:
   keep=keep and summary['candidate'][case][key]['median']<=1.05*summary['baseline'][case][key]['median']
 assert keep==decision['keep_candidate']==final['kept_candidate']
 assert final['queued']==final['running']==0
 assert all(s['model_ready'] and not s['worker_busy'] and not s['ota_pending'] and s['firmware']==('0.9.0' if keep else '0.7.0') for s in final['devices'].values())
 baseline_state=read(DATA/'baseline-state.json');candidate_state=read(DATA/'candidate-state.json')
 for role in ['coordinator','worker']:
  for key in ['model_id','artifact_id','role','first_layer','end_layer','context','quant_bits','tokenizer']:
   assert baseline_state[role][key]==candidate_state[role][key]==final['devices'][role][key]
 write(DATA/'summary.json',{'metrics':summary,'paired_baseline_over_candidate':ratios,'all_streams_reference_equal':len(streams),'kept_candidate':keep})
 c=Canvas(1200,'TinyBrainBot: production INT4 byte-pair kernel',
          'Same two physical P4s | unchanged model / tokenizer / row INT4 | 4+8 layers | context 256 | 30 October 2026')
 colors={'baseline':'#3378ad','candidate':'#178476'}
 for i,case in enumerate(['B1','B2']):
  x=48+i*772;c.rect(x,145,732,340);c.text(x+24,187,case+' · '+('Once upon a time' if case=='B1' else 'One day, a little girl'),25,weight='bold')
  maximum=max(summary[v][case]['elapsed_ms']['range'][1]/1000 for v in summary)*1.12
  for j,variant in enumerate(['baseline','candidate']):
   m=summary[variant][case]['elapsed_ms'];y=250+j*88
   c.text(x+24,y,variant+' '+('0.7.0' if j==0 else '0.9.0'),22)
   c.rect(x+230,y-25,m['median']/1000/maximum*330,30,colors[variant],3)
   lo,hi=m['range'];c.line(x+230+lo/1000/maximum*330,y-10,x+230+hi/1000/maximum*330,y-10,'#193347',3)
   c.text(x+700,y,f'{m["median"]/1000:.3f} s',24,anchor='end')
  c.text(x+24,417,f'Paired time factor: {ratios[case]:.3f}x',25,weight='bold')
  c.text(x+24,456,'16 output tokens; n=3. Whiskers: observed min–max.',20,MUTED)
 c.text(48,541,'Separate recorded execution spans on each board (median seconds)',28,weight='bold')
 c.text(48,580,'Includes memory stalls, scheduling and explicit pauses; not pure arithmetic time.',22,MUTED)
 c.text(48,630,'Prefix / firmware',23,weight='bold');c.text(670,630,'Coordinator',23,weight='bold');c.text(1120,630,'Worker',23,weight='bold')
 for i,(case,v) in enumerate((case,v) for case in ['B1','B2'] for v in ['baseline','candidate']):
  y=680+i*53;c.text(48,y,case+' / '+v,23)
  for key,x in [('master_compute_ms',670),('worker_compute_ms',1120)]:c.text(x,y,f'{summary[v][case][key]["median"]/1000:.3f} s',25,colors[v],weight='bold')
 c.rect(48,920,1504,225,'#dce9f2');c.text(72,964,'Correctness and deployment decision',28,weight='bold')
 c.text(72,1007,f'{len(streams)} real streams: exact token IDs, decoded bytes/text and EOS versus archived native references.',22)
 c.text(72,1045,'95 tests; 14 complete host reference generations; 8 full-vocabulary scalar/tile4 logit positions match.',22)
 c.text(72,1083,'Firmware '+('0.9.0 retained' if keep else '0.7.0 restored')+'; genuine TinyBrainBot shards unchanged; both boards ready, queue empty.',22)
 c.text(48,1180,'Baseline first / candidate second; no randomization, energy, thermal or general quality improvement claim.',21,MUTED)
 stem=DOC/'figures/int4-pair-2026-10-30';stem.with_suffix('.svg').write_text('\n'.join(c.s+['</svg>'])+'\n',encoding='utf-8')
 runtime=pathlib.Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node';code='require('+json.dumps(str(runtime/'node_modules/sharp'))+')(process.argv[1]).png().toFile(process.argv[2])'
 subprocess.run([str(runtime/'bin/node.exe'),'-e',code,str(stem.with_suffix('.svg')),str(stem.with_suffix('.png'))],check=True)
 lines=['# TinyBrainBot production INT4 byte-pair optimization','',
 '30 October 2026. Local firmware-only experiment on the same two physical ESP32-P4 revision1.3 boards. No downloads, retraining or weight changes.','',
 'ESP-IDF5.5.4, revision1.x firmware target, performance optimization enabled, FP contraction disabled. Configured CPU360MHz, PSRAM200MHz, FreeRTOS1000Hz and both HP cores per board. Each board has32MiB PSRAM and32MiB flash; the24MiB model partition is unchanged. Clocks, temperature and energy were not independently measured.','',
 '## Result','',f'Candidate admission: **{"retained firmware0.9.0" if keep else "rejected; restored firmware0.7.0"}**. All27 real streams match archived native token IDs, complete decoded output and EOS. This is a speed/correctness experiment, not an answer-quality improvement.','',
 '| Prefix | Baseline median s | Candidate median s | Paired baseline/candidate time factor |',
 '|---|---:|---:|---:|']
 for case in ['B1','B2']:lines.append(f'| {case} | {summary["baseline"][case]["elapsed_ms"]["median"]/1000:.6f} | {summary["candidate"][case]["elapsed_ms"]["median"]/1000:.6f} | {ratios[case]:.6f} |')
 lines+=['','Final live readiness snapshots (reported allocator values, not an exhaustive memory stress test):','',
         '| Board | Firmware | Free PSRAM bytes | Free internal bytes | Model ready |','|---|---|---:|---:|---|']
 for role,s in final['devices'].items():lines.append(f'| {role} | {s["firmware"]} | {s["free_psram"]} | {s["free_internal"]} | {s["model_ready"]} |')
 lines+=['','![Real P4 comparison](figures/int4-pair-2026-10-30.png)','','## Implementation and independent checks','',
 'The existing tile4 row loop now dispatches once per four-row block on matrix bit width. Its INT4 loop reads each byte once for two consecutive input columns. Explicit signed-nibble arithmetic avoids a runtime per-column bit-width branch and retains each row\'s original FP32 accumulation sequence. Scales, remaining scalar row tails, attention, tokenizer, INT8 representation and scheduling remain unchanged. No fast-math/FMA contraction.','',
 'A failing primitive compile test preceded implementation. Both numerical tests then passed: every256 packed byte value (including signed -8), and random nonbinary FP32 inputs at widths2/6/8/256/768/2048. Independent Python scalar arithmetic rounds every multiply/add to FP32 and compares bytes. A Windows mapped-DLL cleanup issue was corrected by unloading before deleting the temporary test directory.','',
 'All95 existing/new tests pass using the separately built candidate DLL. Every load of the historical DLL path was redirected only within the test process; the historical DLL itself retains SHA256 '+host['archived_dll_sha256']+'. Fourteen genuine TinyBrainBot complete generations match previous references, and eight32000-logit vectors are exactly equal between the candidate tile4 and candidate scalar-row paths. These bounded checks do not prove equivalence for all possible contexts.','',
 '## Trial design, limits and controls','',
 'The plan was committed before baseline collection. Both nodes started on0.7.0, idle and ready with genuine unchanged model/artifact identities. W is a separate4-token warmup; B1/B2 each use16 output tokens with identical4/6 input-token lengths and three repetitions. Prompt order alternates. Worker then coordinator receive0.9.0 over authenticated private LAN. All12 retained quality cases are regression checks with their original caps; no new blinded review or new quality denominator.','',
 'Each request uses both boards: coordinator layers0–3 plus embedding/output, worker layers4–11. This is not independent-request parallel throughput. Request timings are coordinator-clock elapsed durations. Master/worker execution profiles are spans including computation, cache/PSRAM stalls, scheduling and pauses. RPC total already includes worker execution; never add it to worker time.','',
 'Baseline precedes candidate and is not interleaved/randomized. Firmware0.9.0 also inherits the bounded diagnostic microbench endpoint from0.8.0; it is not invoked here. With only three descriptive repeats per prefix, min/max are not confidence intervals and no significance, general performance, quality, thermal or energy claim is made. No third-node simulation or claim.','',
 'The predeclared decision retains the candidate only when both prefix medians improve, all checks pass and neither board execution-span median regresses more than5%. Final W control and both ready/idle states are recorded. Rollback0.7.0 remains private and hash-verified. No model upload or partition change occurred.','',
 '## Evidence','',
 '[All12 actual responses](data/int4-pair-2026-10-30/comparison.html), [frozen plan](int4-pair-plan-2026-10-30.md), [protocol](data/int4-pair-2026-10-30/protocol.json), [host checks](data/int4-pair-2026-10-30/host-check.json), [summary](data/int4-pair-2026-10-30/summary.json), [decision](data/int4-pair-2026-10-30/decision.json), [final state](data/int4-pair-2026-10-30/final.json). Every actual NDJSON stream and raw profile accompanies these files. Scientific self-review by the implementing assistant; no independent reviewer.','',
 'Offline reproduction of the recorded audit/figure: `python tools/analyze_int4_pair.py`. The explicitly staged LAN trial refuses to overwrite its baseline/candidate records. Never rerun deployment scripts merely to regenerate figures.']
 text='\n'.join(lines)+'\n'
 for old,new in [('firmware0','firmware 0'),('All27','All 27'),('All95','All 95'),('All12','All 12'),('all27','all 27'),('every256','all 256'),('widths2','widths 2'),('eight32000','eight 32000'),('separate4-token','separate 4-token'),('use16','use 16'),('identical4/6','identical 4/6'),('on0.7','on 0.7'),('receive0.9','receive 0.9'),('than5%','than 5%'),('Rollback0.7','Rollback 0.7'),('[All12','[All 12')]:text=text.replace(old,new)
 (DOC/'int4-pair-2026-10-30.md').write_text(text,encoding='utf-8')
 sources=sorted(DATA.glob('*.json'))+streams+[DATA/'comparison.html',ROOT/'tools/analyze_int4_pair.py',DOC/'int4-pair-2026-10-30.md']
 sources=[x for x in sources if x.name!='audit.json']
 receipt={'streams_checked':len(streams),'source_sha256':{x.relative_to(ROOT).as_posix():sha(x) for x in sources}}
 write(DATA/'audit.json',receipt);write(stem.with_suffix('.json'),receipt)
 print(json.dumps({'ratios':ratios,'streams':len(streams),'kept_candidate':keep}))
if __name__=='__main__':main()
