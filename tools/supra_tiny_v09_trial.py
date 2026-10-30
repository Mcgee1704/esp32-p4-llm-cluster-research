"""Frozen existing-model comparison, local host/private LAN only; no downloads."""
import argparse,ctypes as C,hashlib,json,pathlib,subprocess,time
from benchmark_kernel import request
from gptneo_p4_trial import MASTER,PEER,status,upload,idle,verify,Dispatcher
from tinybrainbot_p4_trial import sanitized

ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/'data/supra-tiny-v09-2026-10-30'
PRIVATE=ROOT/'.local/supra-tiny-v09-2026-10-30'
PRIOR=ROOT/'data/matched-p4-2026-10-30'
TINY=ROOT/'data/int4-pair-2026-10-30'
PLAN=ROOT/'docs/research/supra-tiny-v09-plan-2026-10-30.md'
DLL=ROOT/'.local/int4-pair-2026-10-30/tinyllm-pair.dll'
SOURCE=['firmware/components/tinyllm/tinyllm.c','firmware/components/tinyllm/int4_dot.h','firmware/components/tinyllm/sp_tokenizer.c','firmware/components/tinyllm/gpt2_tokenizer.c','firmware/main/service.c','firmware/main/dispatcher.c','firmware/CMakeLists.txt','tools/supra_tiny_v09_trial.py','tools/check_gptneo_native.py','tools/gptneo_p4_trial.py','tools/benchmark_kernel.py','tools/tinybrainbot_p4_trial.py','tools/dispatch_client.py','tools/lan_client.py']
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def sources():return {n:sha(ROOT/n) for n in SOURCE}
def frozen():
 p=read(DATA/'protocol.json');assert sha(DATA/'protocol.json')==(DATA/'protocol.sha256').read_text().strip()
 assert p['sources']==sources() and p['plan_sha256']==sha(PLAN)
 assert sha(DLL)==p['candidate_dll_sha256'] and sha(ROOT/'.local/build/tinyllm.dll')==p['archived_dll_sha256']
 assert all(sha(ROOT/n)==h for n,h in p['evidence_sources'].items())
 for roles in p['artifacts'].values():
  for a in roles.values():
   assert sha(ROOT/a['path'])==a['sha256']
   if 'stored_path' in a:assert sha(ROOT/a['stored_path'])==a['stored_sha256']
 rel=(DATA/'protocol.json').relative_to(ROOT).as_posix()
 commit=subprocess.check_output(['git','log','--format=%H','-1','--',rel],cwd=ROOT).decode().strip()
 assert commit and subprocess.check_output(['git','show',commit+':'+rel],cwd=ROOT)==(DATA/'protocol.json').read_bytes()
 return p,commit
def prepare():
 assert not DATA.exists() and not PRIVATE.exists();DATA.mkdir();PRIVATE.mkdir()
 p=read(PRIOR/'protocol.json');h=read(TINY/'host-check.json')
 assert sha(DLL)==h['candidate_dll_sha256'] and all(sha(ROOT/n)==v for n,v in h['sources'].items())
 reused=[TINY/('quality-'+c['id']+'.ndjson') for c in p['cases']]
 evidence=[PRIOR/'protocol.json',PRIOR/'host-references.json',PRIOR/'manual-review.json',PRIOR/'summary.json',TINY/'host-check.json',TINY/'candidate-image.json',TINY/'quality.json',TINY/'final.json',*reused]
 out={'date':'2026-10-30','firmware':'0.9.0','kernel':'tile4 INT4 byte-pair','base_commit':subprocess.check_output(['git','rev-parse','HEAD']).decode().strip(),
      'plan_sha256':sha(PLAN),'sources':sources(),'candidate_dll_sha256':sha(DLL),'archived_dll_sha256':sha(ROOT/'.local/build/tinyllm.dll'),
      'cases':p['cases'],'benchmarks':p['benchmarks'],'inputs':p['inputs'],'artifacts':p['artifacts'],'model_sources':p['model_sources'],
      'evidence_sources':{x.relative_to(ROOT).as_posix():sha(x) for x in evidence},'fresh_streams':27,'reused_tiny_quality_streams':12,
      'order':'Tiny warm + 3 blocks; Supra load/configure + warm + 3 blocks +12 quality; finally restore Tiny/control. Prefix order B1/B2, B2/B1, B1/B2. Fixed model order, no randomized pairs.',
      'quality':'Prior judgments on exactly equal outputs; same author, unblinded. Tiny actual0.9.0 quality records reused, never counted as new.',
      'historical':'Prior0.7.0 timing is descriptive historical evidence, not a fresh old-kernel control.',
      'bounds':'No inference retries, firmware/partition changes, downloads, publication, energy/thermal/third-node claims.'}
 write(DATA/'protocol.json',out);(DATA/'protocol.sha256').write_text(sha(DATA/'protocol.json')+'\n');print('FROZEN inputs prepared; commit before generations.',flush=True)
def host():
 p,commit=frozen();assert not (DATA/'host-check.json').exists()
 old=C.CDLL
 def routed(path,*a,**kw):return old(str(DLL) if pathlib.Path(path).resolve()==(ROOT/'.local/build/tinyllm.dll').resolve() else path,*a,**kw)
 C.CDLL=routed
 from check_gptneo_native import Native
 import numpy as np
 refs=read(PRIOR/'host-references.json');checks={}
 try:
  for model in ['tinybrainbot','supra']:
   a=Native(ROOT/p['artifacts'][model]['full']['path']);b=None;matched=[]
   try:
    for c in p['cases']+p['benchmarks']:
     text=p['inputs'][model][c['id']]['prompt'];r=a.generate(text,c['limit']);expected=refs[model][c['id']]
     assert all(r[k]==expected[k] for k in ['tokens','text','eos','prompt_tokens'])
     matched.append(c['id']);print('HOST',model,c['id'],'exact',flush=True)
    w=a.generate('Once upon a time',4);assert w==refs[model]['W'];matched.append('W')
    b=Native(ROOT/p['artifacts'][model]['full']['path']);a.lib.ts_set_kernel.argtypes=[C.c_void_p,C.c_int];assert a.lib.ts_set_kernel(b.state,2)==0
    a.lib.ts_reset(a.state);b.lib.ts_reset(b.state);ids=a.encode('Once upon a time')+[42,305,7,10]
    for pos,t in enumerate(ids):
     x=a.forward(t,pos);y=b.forward(t,pos);np.testing.assert_array_equal(x,y);assert x.tobytes()==y.tobytes()
    checks[model]={'complete_reference_generations':matched,'full_logit_positions':len(ids),'vocabulary':a.vocab,'scalar_tile4_logits_byte_identical':True}
   finally:
    a.close()
    if b:b.close()
 finally:C.CDLL=old
 write(DATA/'host-check.json',{'protocol_commit':commit,'checks':checks,'complete_generations':30,'all_reference_equal':True,'sources':sources(),'candidate_dll_sha256':sha(DLL),'archived_dll_preserved':sha(ROOT/'.local/build/tinyllm.dll')==p['archived_dll_sha256']})
def ready(h,model,role,p,boot=None):
 end=time.monotonic()+240;a=p['artifacts'][model][role]
 while time.monotonic()<end:
  try:
   s=status(h)
   if s['firmware']=='0.9.0' and s['model_ready'] and s['model_id']==a['model_id'] and s['artifact_id']==a['artifact_id'] and not s['worker_busy'] and not s['ota_pending'] and (boot is None or s['boot_id']!=boot):
    assert s['role']==(1 if role=='coordinator' else 2) and s['context']==256 and s['quant_bits']==4 and s['default_kernel']=='tile4' and s['free_psram']>=512*1024
    return s
  except (OSError,RuntimeError,ValueError):pass
  time.sleep(2)
 raise RuntimeError('Model readiness timeout: '+model+'/'+role)
def switch(model,p,label):
 idle(Dispatcher(MASTER));s={}
 for role,h in [('worker',PEER),('coordinator',MASTER)]:
  before=status(h);assert before['firmware']=='0.9.0' and not before['worker_busy'] and not before['ota_pending'];a=p['artifacts'][model][role]
  if before['model_id']!=a['model_id'] or before['artifact_id']!=a['artifact_id']:
   print('LOAD',model,role,flush=True);upload(h,'model',ROOT/a['stored_path']);s[role]=ready(h,model,role,p,before['boot_id'])
  else:s[role]=ready(h,model,role,p)
 c=Dispatcher(MASTER).request('POST','/api/cluster',{'peer':PEER});assert c['configured'] and c['mode']=='sharded' and c['active_lanes']==1
 write(PRIVATE/(label+'-states.json'),s);write(DATA/(label+'-states.json'),{r:sanitized(x) for r,x in s.items()});return s
def infer(model,case,label,p,cap=None):
 cap=case['limit'] if cap is None else cap;print('START',label,flush=True)
 raw=request(MASTER,'POST','/api/generate',{'prompt':p['inputs'][model][case['id']]['prompt'],'tokens':cap,'kernel':'tile4'},timeout=600)
 path=DATA/(label+'.ndjson');assert not path.exists();path.write_bytes(raw)
 ref=read(PRIOR/'host-references.json')[model]['W' if cap==4 else case['id']];done=verify(raw,ref)
 assert done['boards']==2 and done['kernel']['mode']=='tile4' and done['kernel']['owner_core_mask']==2 and done['kernel']['helper_core_mask']==1
 assert done['prompt_tokens']==len(ref['prompt_tokens']) and done['output_tokens']==len(ref['tokens'])
 print('MATCH',label,round(done['elapsed_ms']/1000,3),'s',flush=True)
 return {'model':model,'case':case['id'],'file':path.name,'done':done,'tokens_text_eos_equal':True}
def device():
 p,_=frozen();h=read(DATA/'host-check.json');assert h['all_reference_equal'] and h['sources']==sources() and h['complete_generations']==30
 assert not (DATA/'device-start.json').exists();idle(Dispatcher(MASTER))
 before={r:ready(x,'tinybrainbot',r,p) for r,x in [('coordinator',MASTER),('worker',PEER)]};write(DATA/'device-start.json',{r:sanitized(s) for r,s in before.items()})
 quality=[];timing=[];controls=[];failure=None
 try:
  for model in ['tinybrainbot','supra']:
   start=switch(model,p,model+'-loaded');controls.append(infer(model,p['benchmarks'][0],model+'-warmup',p,4));write(DATA/'controls.json',controls)
   for block in [1,2,3]:
    for case in (p['benchmarks'] if block!=2 else list(reversed(p['benchmarks']))):
     row=infer(model,case,f'{model}-block{block}-{case["id"]}',p);row['block']=block;timing.append(row);write(DATA/'timing-runs.json',timing)
   if model=='supra':
    for case in p['cases']:
     quality.append(infer(model,case,'supra-quality-'+case['id'],p));write(DATA/'quality-runs.json',quality)
   after={r:ready(x,model,r,p) for r,x in [('coordinator',MASTER),('worker',PEER)]}
   assert all(after[r]['boot_id']==start[r]['boot_id'] for r in after)
   write(DATA/(model+'-tested-states.json'),{r:sanitized(s) for r,s in after.items()})
 except BaseException as e:
  failure=type(e).__name__+': '+str(e);write(DATA/'error.json',{'error':failure,'quality_completed':len(quality),'timing_completed':len(timing)});raise
 finally:
  try:
   s=switch('tinybrainbot',p,'restored');control=infer('tinybrainbot',p['benchmarks'][0],'restoration-control',p,4);c=idle(Dispatcher(MASTER))
   final={r:ready(x,'tinybrainbot',r,p) for r,x in [('coordinator',MASTER),('worker',PEER)]}
   write(DATA/'final.json',{'completed':failure is None,'failure':failure,'devices':{r:sanitized(s) for r,s in final.items()},'restoration_control':control,'queued':c['queued'],'running':c['running'],'mode':c['mode']})
   print('RESTORED TinyBrainBot, both0.9.0 ready/idle, queue empty.',flush=True)
  except BaseException as e:
   write(DATA/'restoration-error.json',{'error':type(e).__name__+': '+str(e)});raise
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('stage',choices=['prepare','host','device']);globals()[a.parse_args().stage]()
