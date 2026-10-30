"""Prospective doubled-cap study; existing local assets and private LAN only."""
import argparse,ctypes as C,json,pathlib,secrets,subprocess
import quality_v2_trial as baseline
import quality_v2_results as old_results
import supra_tiny_v09_trial as devices
from gptneo_p4_trial import MASTER,PEER,status,idle,verify,Dispatcher
from benchmark_kernel import request
from tinybrainbot_p4_trial import sanitized

ROOT=baseline.ROOT
BASE=baseline.DATA
DATA=ROOT/'data/quality-cap-v3-2026-10-30'
PRIVATE=ROOT/'.local/quality-cap-v3-2026-10-30'
PLAN=ROOT/'docs/research/quality-cap-v3-plan-2026-10-30.md'
SOURCE=baseline.SOURCE+['tools/quality_v2_results.py','tools/quality_cap_v3_trial.py']
read,write,sha=baseline.read,baseline.write,baseline.sha
def sources():return {n:sha(ROOT/n) for n in SOURCE}

def prepare():
 assert not DATA.exists() and not PRIVATE.exists()
 b,_=baseline.frozen();old_results.audit_recorded();old_results.validate_ratings()
 refs=read(BASE/'host-references.json');cases=[dict(c,limit=c['limit']*2,baseline_limit=c['limit']) for c in b['cases']]
 reuse=[{'model':m,'case':cid,'file':m+'-'+cid+'.ndjson'} for m in ['tinybrainbot','supra'] for cid in b['case_order'] if refs[m][cid]['eos']]
 assert len(reuse)==5 and all(x['model']=='tinybrainbot' for x in reuse)
 assert all(len(b['inputs'][m][c['id']]['tokens'])+c['limit']-1<=256 for m in refs for c in cases)
 DATA.mkdir();PRIVATE.mkdir();positions=list(range(24));secrets.SystemRandom().shuffle(positions);a=set(positions[:12])
 key={'nonce':secrets.token_hex(32),'labels':{c['id']:{'A':'tinybrainbot' if i in a else 'supra','B':'supra' if i in a else 'tinybrainbot'} for i,c in enumerate(cases)}}
 write(PRIVATE/'mask-key.json',key)
 budget=sum(c['limit'] for m in refs for c in cases if not refs[m][c['id']]['eos']);assert budget==1888
 p={'date':'2026-10-30','base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),'firmware':'0.9.0','context':256,'split':4,'kernel':'tile4 INT4 byte-pair','cases':cases,'case_order':b['case_order'],'inputs':b['inputs'],'artifacts':b['artifacts'],'model_sources':b['model_sources'],'sources':sources(),'plan_sha256':sha(PLAN),'baseline_sha256':{x.name:sha(x) for x in BASE.iterdir() if x.is_file()},'candidate_dll_sha256':sha(baseline.DLL),'archived_dll_sha256':sha(ROOT/'.local/build/tinyllm.dll'),'mask_commitment_sha256':sha(PRIVATE/'mask-key.json'),'reused_eos':reuse,'budget':{'evaluated_higher_cap_outputs':48,'new_quality_streams':43,'reused_eos_streams':5,'new_controls':3,'new_hardware_streams':46,'max_new_hardware_output_tokens':1900},'review':'Unchanged V2 rubric; same-author model-label masking only. Earlier questions/outputs/ratings known. Commit high-cap ratings before unsealing; old ratings immutable.','scope':'Output stopping-cap intervention only; fixed order, one greedy trajectory, n=4/category. No population ranking, independent blindness, kernel-speed or energy claim.'}
 write(DATA/'protocol.json',p);(DATA/'protocol.sha256').write_bytes((sha(DATA/'protocol.json')+'\n').encode())
 print('Frozen 24 same questions, doubled32/96 caps,43 fresh +5 EOS reuse,46 new streams. Commit before answers.',flush=True)

def frozen():
 p=read(DATA/'protocol.json');assert sha(DATA/'protocol.json')==(DATA/'protocol.sha256').read_text().strip()
 assert p['sources']==sources() and p['plan_sha256']==sha(PLAN)
 assert p['candidate_dll_sha256']==sha(baseline.DLL) and p['archived_dll_sha256']==sha(ROOT/'.local/build/tinyllm.dll')
 assert sha(PRIVATE/'mask-key.json')==p['mask_commitment_sha256']
 assert all(sha(BASE/n)==h for n,h in p['baseline_sha256'].items())
 baseline.frozen()
 path=(DATA/'protocol.json').relative_to(ROOT).as_posix();commit=subprocess.check_output(['git','log','-1','--format=%H','--',path],cwd=ROOT).decode().strip()
 assert commit and subprocess.check_output(['git','show',commit+':'+path],cwd=ROOT)==(DATA/'protocol.json').read_bytes()
 return p,commit

def host():
 p,commit=frozen();assert not (DATA/'host-references.json').exists();old=baseline.route_native();refs={};low=read(BASE/'host-references.json')
 from check_gptneo_native import Native
 try:
  for m in ['tinybrainbot','supra']:
   n=Native(ROOT/p['artifacts'][m]['full']['path']);refs[m]={}
   try:
    refs[m]['W']=n.generate('Once upon a time',4);assert refs[m]['W']==low[m]['W']
    for c in p['cases']:
     cid=c['id'];inp=p['inputs'][m][cid];assert n.encode(inp['prompt'])==inp['tokens']
     r=n.generate(inp['prompt'],c['limit']);assert r['tokens'][:len(low[m][cid]['tokens'])]==low[m][cid]['tokens']
     if low[m][cid]['eos']:assert r==low[m][cid]
     refs[m][cid]=r;write(DATA/'host-references.json',refs);print('HOST',m,cid,'old-prefix-equal',flush=True)
   finally:n.close()
 finally:C.CDLL=old
 write(DATA/'host-receipt.json',{'protocol_commit':commit,'protocol_sha256':sha(DATA/'protocol.json'),'references_sha256':sha(DATA/'host-references.json'),'new_references':48,'old_prefixes_equal':48,'old_eos_answers_fully_equal':5,'known_controls_equal':2,'sources':sources(),'archived_dll_preserved':True})

def infer(m,c,label,p,refs,quality=False):
 print('START',label,flush=True);raw=request(MASTER,'POST','/api/generate',{'prompt':p['inputs'][m][c['id']]['prompt'],'tokens':c['limit'],'kernel':'tile4'},timeout=600)
 path=DATA/(label+'.ndjson');assert not path.exists();path.write_bytes(raw);done=verify(raw,refs[m][c['id']])
 assert done['boards']==2 and done['kernel']['mode']=='tile4' and done['kernel']['owner_core_mask']==2 and done['kernel']['helper_core_mask']==1
 assert done['prompt_tokens']==len(refs[m][c['id']]['prompt_tokens']) and done['output_tokens']==len(refs[m][c['id']]['tokens'])
 if quality:
  low=read(BASE/'host-references.json')[m][c['id']];pieces=[x for x in (json.loads(line) for line in raw.splitlines()) if 'token' in x]
  assert [x['token'] for x in pieces[:len(low['tokens'])]]==low['tokens']
  assert b''.join(bytes.fromhex(x['bytes_hex']) for x in pieces[:len(low['tokens'])]).decode('utf-8','replace')==low['text']
 print('MATCH',label,'reference/prefix-equal',flush=True)
 return {'model':m,'case':c['id'],'origin':'fresh','file':path.name,'done':done}

def device():
 p,_=frozen();h=read(DATA/'host-receipt.json');assert h['references_sha256']==sha(DATA/'host-references.json') and h['sources']==sources() and h['old_prefixes_equal']==48
 assert not (DATA/'device-start.json').exists();devices.DATA=DATA;devices.PRIVATE=PRIVATE;refs=read(DATA/'host-references.json');oldrefs=read(BASE/'host-references.json')
 oldrows=read(BASE/'device-runs.json');old_results.audit_recorded();idle(Dispatcher(MASTER))
 s={r:devices.ready(ip,'tinybrainbot',r,p) for r,ip in [('coordinator',MASTER),('worker',PEER)]};write(DATA/'device-start.json',{r:sanitized(v) for r,v in s.items()})
 rows=[];controls=[];failure=None;warm={'id':'W','limit':4}
 try:
  for m in ['tinybrainbot','supra']:
   start=devices.switch(m,p,m+'-loaded');controls.append(infer(m,warm,m+'-warmup',p,refs));write(DATA/'controls.json',controls)
   for cid in p['case_order']:
    c=next(c for c in p['cases'] if c['id']==cid)
    if oldrefs[m][cid]['eos']:
     assert refs[m][cid]==oldrefs[m][cid];r=next(x for x in oldrows if x['model']==m and x['case']==cid)
     rows.append({'model':m,'case':cid,'origin':'reused-baseline-eos','file':r['file'],'done':r['done'],'baseline_file_sha256':sha(BASE/r['file'])});print('REUSE',m,cid,'known-EOS',flush=True)
    else:rows.append(infer(m,c,m+'-'+cid,p,refs,True))
    write(DATA/'device-runs.json',rows)
   after={r:devices.ready(ip,m,r,p) for r,ip in [('coordinator',MASTER),('worker',PEER)]};assert all(after[r]['boot_id']==start[r]['boot_id'] for r in after)
   write(DATA/(m+'-tested-states.json'),{r:sanitized(v) for r,v in after.items()})
 except BaseException as e:
  failure=type(e).__name__+': '+str(e);write(DATA/'error.json',{'error':failure,'quality_completed':len(rows)});raise
 finally:
  try:
   devices.switch('tinybrainbot',p,'restored');control=infer('tinybrainbot',warm,'restoration-control',p,refs);q=idle(Dispatcher(MASTER))
   s={r:devices.ready(ip,'tinybrainbot',r,p) for r,ip in [('coordinator',MASTER),('worker',PEER)]}
   write(DATA/'final.json',{'completed':failure is None,'failure':failure,'devices':{r:sanitized(v) for r,v in s.items()},'restoration_control':control,'queued':q['queued'],'running':q['running'],'mode':q['mode']});print('RESTORED TinyBrainBot, both0.9.0 ready/idle.',flush=True)
  except BaseException as e:write(DATA/'restoration-error.json',{'error':type(e).__name__+': '+str(e)});raise

def mask():
 p,_=frozen();assert read(DATA/'final.json')['completed'] and len(read(DATA/'device-runs.json'))==48
 assert not (DATA/'masked-responses.json').exists();refs=read(DATA/'host-references.json');key=read(PRIVATE/'mask-key.json');rows=[]
 for c in p['cases']:
  out={}
  for label,m in key['labels'][c['id']].items():
   r=refs[m][c['id']];out[label]={'text':r['text'],'eos':r['eos'],'cap_reached':len(r['tokens'])==c['limit'] and not r['eos']}
  rows.append({'case':c['id'],'category':c['category'],'user':c['user'],'expected':c['expected'],'limit':c['limit'],'outputs':out})
 write(DATA/'masked-responses.json',{'protocol_sha256':sha(DATA/'protocol.json'),'mask_commitment_sha256':p['mask_commitment_sha256'],'scope':'Higher-cap model-label masking only; prior outputs/ratings known; not independent or fully blind.','rows':rows})
 print('48 higher-cap outputs label-masked. Rate/commit before opening mapping.',flush=True)

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('stage',choices=['prepare','host','device','mask']);globals()[a.parse_args().stage]()
