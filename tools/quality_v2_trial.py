"""Prospective24-task private-LAN quality study, no downloads or firmware writes."""
import argparse,ctypes as C,hashlib,json,pathlib,secrets,subprocess
import supra_tiny_v09_trial as previous
from gptneo_p4_trial import MASTER,PEER,status,idle,verify,Dispatcher
from benchmark_kernel import request
from tinybrainbot_p4_trial import sanitized

ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/'data/quality-v2-2026-10-30'
PRIVATE=ROOT/'.local/quality-v2-2026-10-30'
PLAN=ROOT/'docs/research/quality-v2-plan-2026-10-30.md'
PRIOR=ROOT/'data/supra-tiny-v09-2026-10-30'
DLL=previous.DLL
SOURCE=previous.SOURCE+['tools/quality_v2_trial.py']
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,x):p.write_bytes((json.dumps(x,indent=2)+'\n').encode('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def sources():return {n:sha(ROOT/n) for n in SOURCE}
def route_native():
 old=C.CDLL
 def routed(p,*a,**kw):return old(str(DLL) if pathlib.Path(p).resolve()==(ROOT/'.local/build/tinyllm.dll').resolve() else p,*a,**kw)
 C.CDLL=routed;return old
def prompt(model,user):return ' <|user|> '+user+' <|end|> <|assistant|>' if model=='tinybrainbot' else '<|im_start|>user\n'+user+'<|im_end|>\n<|im_start|>assistant\n'
def frozen():
 p=read(DATA/'protocol.json');assert sha(DATA/'protocol.json')==(DATA/'protocol.sha256').read_text().strip()
 assert p['sources']==sources() and p['cases_sha256']==sha(DATA/'cases.json') and p['plan_sha256']==sha(PLAN)
 assert p['candidate_dll_sha256']==sha(DLL) and p['archived_dll_sha256']==sha(ROOT/'.local/build/tinyllm.dll')
 assert sha(PRIVATE/'mask-key.json')==p['mask_commitment_sha256']
 for roles in p['artifacts'].values():
  for a in roles.values():
   assert sha(ROOT/a['path'])==a['sha256']
   if 'stored_path' in a:assert sha(ROOT/a['stored_path'])==a['stored_sha256']
 rel=(DATA/'protocol.json').relative_to(ROOT).as_posix();commit=subprocess.check_output(['git','log','--format=%H','-1','--',rel],cwd=ROOT).decode().strip()
 assert commit and subprocess.check_output(['git','show',commit+':'+rel],cwd=ROOT)==(DATA/'protocol.json').read_bytes()
 return p,commit
def strings(x):
 if isinstance(x,str):yield x
 elif isinstance(x,list):
  for y in x:yield from strings(y)
 elif isinstance(x,dict):
  for y in x.values():yield from strings(y)
def prepare():
 assert not (DATA/'protocol.json').exists() and not PRIVATE.exists();PRIVATE.mkdir()
 cases=read(DATA/'cases.json');assert len(cases)==24 and len({x['id'] for x in cases})==24
 categories=['facts','reasoning','exact','grounded','uncertainty','story'];assert all(sum(x['category']==c for x in cases)==4 for c in categories)
 old_protocols=subprocess.check_output(['git','ls-files','data/**/protocol.json'],cwd=ROOT).decode().splitlines();corpus=[]
 for rel in old_protocols:corpus+=list(strings(read(ROOT/rel)))
 norm=lambda s:' '.join(s.casefold().split())
 assert all(not any(norm(c['user']) in norm(s) for s in corpus) for c in cases),'Exact task already present in earlier protocols'
 p=read(PRIOR/'protocol.json');h=read(PRIOR/'host-check.json')
 assert h['all_reference_equal'] and h['candidate_dll_sha256']==sha(DLL)
 assert p['sources']==previous.sources()
 for c in cases:c['limit']=48 if c['category']=='story' else 16
 groups={c:[x for x in cases if x['category']==c] for c in categories};order=[groups[c][i]['id'] for i in range(4) for c in categories]
 positions=list(range(24));secrets.SystemRandom().shuffle(positions);tinyA=set(positions[:12]);mapping={c['id']:{'A':'tinybrainbot' if i in tinyA else 'supra','B':'supra' if i in tinyA else 'tinybrainbot'} for i,c in enumerate(cases)}
 write(PRIVATE/'mask-key.json',{'nonce':secrets.token_hex(32),'labels':mapping})
 old=route_native();from check_gptneo_native import Native
 inputs={}
 try:
  for model in ['tinybrainbot','supra']:
   n=Native(ROOT/p['artifacts'][model]['full']['path'])
   try:
    inputs[model]={c['id']:{'prompt':prompt(model,c['user']),'tokens':n.encode(prompt(model,c['user']))} for c in cases}
    inputs[model]['W']={'prompt':'Once upon a time','tokens':n.encode('Once upon a time')}
   finally:n.close()
 finally:C.CDLL=old
 for m in inputs:
  for c in cases:assert len(inputs[m][c['id']]['tokens'])+c['limit']-1<=256
 out={'date':'2026-10-30','base_commit':subprocess.check_output(['git','rev-parse','HEAD']).decode().strip(),'firmware':'0.9.0','kernel':'tile4 INT4 byte-pair','context':256,'split':4,
      'cases':cases,'case_order':order,'inputs':inputs,'artifacts':p['artifacts'],'model_sources':p['model_sources'],'sources':sources(),'cases_sha256':sha(DATA/'cases.json'),'plan_sha256':sha(PLAN),
      'candidate_dll_sha256':sha(DLL),'archived_dll_sha256':sha(ROOT/'.local/build/tinyllm.dll'),'mask_commitment_sha256':sha(PRIVATE/'mask-key.json'),
      'novelty':{'earlier_protocol_files_checked':len(old_protocols),'exact_task_overlap_found':False,'scope':'New prompt strings in our recorded protocols, not held out from pretraining; familiar task families overlap.'},
      'budget':{'new_quality_cases':24,'models':2,'fresh_quality_streams':48,'warmups':2,'restoration_controls':1,'hardware_streams':51,'max_quality_output_tokens':1024,'max_hardware_output_tokens':1036},
      'review':'Model-label-masked A/B, same author; no independent rater or complete-blinding claim. Commit ratings before mapping disclosure. Frozen plan defines criteria.',
      'order':'Tiny all24 then Supra all24, fixed round-robin categories; warm each, restore Tiny in finally. No sampling/retries/quality reuse.',
      'limits':'Constructed English sample; small per-category denominators, possible training overlap, unequal outputs/native wrappers. No pooled ranking, matched-work timing, energy, thermal or third-node claim.'}
 write(DATA/'protocol.json',out);(DATA/'protocol.sha256').write_text(sha(DATA/'protocol.json')+'\n',encoding='utf-8');print('Prepared24 tasks, input encodings and masked-label commitment; no answers generated. Commit before host/device.',flush=True)
def host():
 p,commit=frozen();assert not (DATA/'host-references.json').exists();refs={};old=route_native();from check_gptneo_native import Native
 try:
  oldrefs=read(previous.PRIOR/'host-references.json')
  for m in ['tinybrainbot','supra']:
   n=Native(ROOT/p['artifacts'][m]['full']['path']);refs[m]={}
   try:
    refs[m]['W']=n.generate('Once upon a time',4);assert refs[m]['W']==oldrefs[m]['W']
    for c in p['cases']:
     inp=p['inputs'][m][c['id']];assert n.encode(inp['prompt'])==inp['tokens'];refs[m][c['id']]=n.generate(inp['prompt'],c['limit'])
     write(DATA/'host-references.json',refs);print('HOST',m,c['id'],'recorded',flush=True)
   finally:n.close()
 finally:C.CDLL=old
 write(DATA/'host-receipt.json',{'protocol_commit':commit,'protocol_sha256':sha(DATA/'protocol.json'),'references_sha256':sha(DATA/'host-references.json'),'new_quality_generations':48,'known_controls_equal':2,'sources':sources(),'archived_dll_preserved':sha(ROOT/'.local/build/tinyllm.dll')==p['archived_dll_sha256']})
def infer(m,c,label,p,refs):
 print('START',label,flush=True);raw=request(MASTER,'POST','/api/generate',{'prompt':p['inputs'][m][c['id']]['prompt'],'tokens':c['limit'],'kernel':'tile4'},timeout=600)
 path=DATA/(label+'.ndjson');assert not path.exists();path.write_bytes(raw);done=verify(raw,refs[m][c['id']])
 assert done['boards']==2 and done['prompt_tokens']==len(p['inputs'][m][c['id']]['tokens']) and done['output_tokens']==len(refs[m][c['id']]['tokens'])
 assert done['kernel']['mode']=='tile4' and done['kernel']['owner_core_mask']==2 and done['kernel']['helper_core_mask']==1
 print('MATCH',label,'reference-equal',flush=True)
 return {'model':m,'case':c['id'],'file':path.name,'done':done,'reference_equal':True}
def device():
 p,_=frozen();h=read(DATA/'host-receipt.json');assert h['references_sha256']==sha(DATA/'host-references.json') and h['sources']==sources() and h['new_quality_generations']==48
 assert not (DATA/'device-start.json').exists();previous.DATA=DATA;previous.PRIVATE=PRIVATE;refs=read(DATA/'host-references.json')
 idle(Dispatcher(MASTER));s={r:previous.ready(x,'tinybrainbot',r,p) for r,x in [('coordinator',MASTER),('worker',PEER)]};write(DATA/'device-start.json',{r:sanitized(x) for r,x in s.items()})
 rows=[];controls=[];failure=None;warm={'id':'W','limit':4}
 try:
  for m in ['tinybrainbot','supra']:
   start=previous.switch(m,p,m+'-loaded');controls.append(infer(m,warm,m+'-warmup',p,refs));write(DATA/'controls.json',controls)
   for cid in p['case_order']:
    c=next(x for x in p['cases'] if x['id']==cid);rows.append(infer(m,c,m+'-'+cid,p,refs));write(DATA/'device-runs.json',rows)
   after={r:previous.ready(x,m,r,p) for r,x in [('coordinator',MASTER),('worker',PEER)]};assert all(after[r]['boot_id']==start[r]['boot_id'] for r in after)
   write(DATA/(m+'-tested-states.json'),{r:sanitized(x) for r,x in after.items()})
 except BaseException as e:
  failure=type(e).__name__+': '+str(e);write(DATA/'error.json',{'error':failure,'quality_completed':len(rows)});raise
 finally:
  try:
   previous.switch('tinybrainbot',p,'restored');control=infer('tinybrainbot',warm,'restoration-control',p,refs);q=idle(Dispatcher(MASTER))
   s={r:previous.ready(x,'tinybrainbot',r,p) for r,x in [('coordinator',MASTER),('worker',PEER)]}
   write(DATA/'final.json',{'completed':failure is None,'failure':failure,'devices':{r:sanitized(x) for r,x in s.items()},'restoration_control':control,'queued':q['queued'],'running':q['running'],'mode':q['mode']})
   print('RESTORED TinyBrainBot; both0.9.0 ready/idle.',flush=True)
  except BaseException as e:write(DATA/'restoration-error.json',{'error':type(e).__name__+': '+str(e)});raise
def mask():
 p,_=frozen();assert read(DATA/'final.json')['completed'] and len(read(DATA/'device-runs.json'))==48
 assert not (DATA/'masked-responses.json').exists();key=read(PRIVATE/'mask-key.json');refs=read(DATA/'host-references.json');rows=[]
 for c in p['cases']:
  outputs={}
  for label,m in key['labels'][c['id']].items():
   r=refs[m][c['id']];outputs[label]={'text':r['text'],'eos':r['eos'],'cap_reached':len(r['tokens'])==c['limit'] and not r['eos']}
  rows.append({'case':c['id'],'category':c['category'],'user':c['user'],'expected':c['expected'],'limit':c['limit'],'outputs':outputs})
 write(DATA/'masked-responses.json',{'protocol_sha256':sha(DATA/'protocol.json'),'mask_commitment_sha256':p['mask_commitment_sha256'],'scope':'Same-author model-label masking; no claim of independent/complete blindness.','rows':rows})
 print('Masked48 responses prepared; write and commit ratings before unblinding.',flush=True)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('stage',choices=['prepare','host','device','mask']);globals()[a.parse_args().stage]()
