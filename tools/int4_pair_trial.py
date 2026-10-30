"""Explicit staged local-LAN firmware comparison; never changes model weights."""
import argparse,json,pathlib,statistics,time,shutil,hashlib
from gptneo_p4_trial import MASTER,PEER,status,upload,idle,verify,Dispatcher
from benchmark_kernel import request
from tinybrainbot_p4_trial import sanitized
ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/'data/int4-pair-2026-10-30'
PRIVATE=ROOT/'.local/int4-pair-2026-10-30'
OLD=ROOT/'.local/tinybrainbot-p4-2026-10-29/p4-0.7.0.bin'
ID='0a0ab7c4fd5cc1cea3f77f77c104ce0684ccdc37db1149aa78a9bdb742a716f3'
PRIOR=ROOT/'data/matched-p4-2026-10-30'
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n',encoding='utf-8')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def states(version=None):
 s={r:status(h) for r,h in [('coordinator',MASTER),('worker',PEER)]}
 for i,x in enumerate(s.values()):
  assert x['model_id']==ID and x['model_ready'] and x['role']==i+1 and not x['worker_busy'] and not x['ota_pending']
  if version:assert x['firmware']==version
 idle(Dispatcher(MASTER));return s
def ready(h,version,boot):
 end=time.monotonic()+180
 while time.monotonic()<end:
  try:
   s=status(h)
   if s['firmware']==version and s['boot_id']!=boot and s['model_ready'] and s['model_id']==ID and not s['ota_pending']:return s
  except (OSError,ValueError,RuntimeError):pass
  time.sleep(2)
 raise RuntimeError('Firmware readiness timeout')
def deploy(image,version):
 for role,h in [('worker',PEER),('coordinator',MASTER)]:
  old=status(h);print('OTA',role,version,flush=True);upload(h,'firmware',image);ready(h,version,old['boot_id'])
 Dispatcher(MASTER).request('POST','/api/cluster',{'peer':PEER})
def run(phase):
 version='0.7.0' if phase=='baseline' else '0.9.0';before=states(version)
 refs=read(PRIOR/'host-references.json')['tinybrainbot'];p=read(PRIOR/'protocol.json')
 records=[]
 for block in range(4):
  cases=['W'] if block==0 else (['B1','B2'] if block%2 else ['B2','B1'])
  for case in cases:
   prompt=next((x['prompt'] for x in p['benchmarks'] if x['id']==case),'Once upon a time')
   raw=request(MASTER,'POST','/api/generate',{'prompt':prompt,'tokens':4 if case=='W' else 16,'peer':PEER},timeout=240)
   (DATA/f'{phase}-{block}-{case}.ndjson').write_bytes(raw);done=verify(raw,refs[case])
   assert done['boards']==2 and done['kernel']['mode']=='tile4'
   records.append({'phase':phase,'block':block,'case':case,'done':done})
   write(DATA/(phase+'-runs.json'),records);print(phase,block,case,done['elapsed_ms'],flush=True)
 after=states(version)
 assert all(after[r]['boot_id']==before[r]['boot_id'] and after[r]['artifact_id']==before[r]['artifact_id'] for r in after)
 write(DATA/(phase+'-state.json'),{r:sanitized(x) for r,x in after.items()})
def main():
 a=argparse.ArgumentParser();a.add_argument('phase',choices=['baseline','candidate']);phase=a.parse_args().phase
 assert sha(OLD)=='c867d87215cbee256fcf35213b8c539e4ed5d950e3beb2e063d36394e1bd6141'
 if phase=='baseline':
  DATA.mkdir(exist_ok=False);PRIVATE.mkdir(exist_ok=False)
  write(DATA/'protocol.json',{'plan_sha256':sha(ROOT/'docs/research/int4-pair-plan-2026-10-30.md'),'script_sha256':sha(pathlib.Path(__file__)),'prior_protocol_sha256':sha(PRIOR/'protocol.json'),'prior_refs_sha256':sha(PRIOR/'host-references.json'),'design':'Baseline first, candidate second; W warmup and three repeats per B1/B2; 12 quality regression cases. See plan.'})
  run('baseline');return
 assert not (DATA/'candidate-runs.json').exists()
 image=PRIVATE/'p4-0.9.0.bin';shutil.copyfile(ROOT/'.local/build/rev1/p4_tinystories.bin',image)
 write(DATA/'candidate-image.json',{'private_firmware_sha256':sha(image),'bytes':image.stat().st_size,'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in [ROOT/'firmware/components/tinyllm/tinyllm.c',ROOT/'firmware/components/tinyllm/int4_dot.h',ROOT/'firmware/CMakeLists.txt']}})
 keep=False
 try:
  states('0.7.0');deploy(image,'0.9.0');run('candidate')
  p=read(PRIOR/'protocol.json');refs=read(PRIOR/'host-references.json')['tinybrainbot'];out=[]
  for c in p['cases']:
   prompt=p['inputs']['tinybrainbot'][c['id']] if isinstance(p['inputs']['tinybrainbot'][c['id']],str) else p['inputs']['tinybrainbot'][c['id']]['prompt']
   raw=request(MASTER,'POST','/api/generate',{'prompt':prompt,'tokens':c['limit'],'peer':PEER},timeout=240)
   (DATA/('quality-'+c['id']+'.ndjson')).write_bytes(raw);done=verify(raw,refs[c['id']]);out.append({'case':c['id'],'done':done});write(DATA/'quality.json',out)
   print('quality',c['id'],'exact',flush=True)
  baseline=read(DATA/'baseline-runs.json');candidate=read(DATA/'candidate-runs.json');summary={}
  for case in ['B1','B2']:
   b=[x['done'] for x in baseline if x['case']==case];n=[x['done'] for x in candidate if x['case']==case]
   summary[case]={'baseline_ms':statistics.median(x['elapsed_ms'] for x in b),'candidate_ms':statistics.median(x['elapsed_ms'] for x in n)}
  # Admission uses the two elapsed medians; board execution guard checked below.
  keep=all(x['candidate_ms']<x['baseline_ms'] for x in summary.values())
  for case in ['B1','B2']:
   for key in ['master_compute_ms','worker_compute_ms']:
    b=[x['done']['profile'][key] for x in baseline if x['case']==case]
    n=[x['done']['profile'][key] for x in candidate if x['case']==case]
    keep=keep and statistics.median(n)<=1.05*statistics.median(b)
  write(DATA/'decision.json',{'keep_candidate':keep,'timing':summary,'quality_regressions':len(out),'all_reference_equal':True})
 finally:
  if not keep:deploy(OLD,'0.7.0')
  refs=read(PRIOR/'host-references.json')['tinybrainbot'];raw=request(MASTER,'POST','/api/generate',{'prompt':'Once upon a time','tokens':4,'peer':PEER},timeout=240)
  (DATA/'final-control.ndjson').write_bytes(raw);verify(raw,refs['W'])
  s=states('0.9.0' if keep else '0.7.0');write(DATA/'final.json',{'kept_candidate':keep,'devices':{r:sanitized(x) for r,x in s.items()},'queued':0,'running':0})
if __name__=='__main__':main()
