"""Explicit private-LAN diagnostic deployment, bounded trial and rollback."""
import pathlib,sys,time,json,hashlib,shutil
from gptneo_p4_trial import MASTER,PEER,status,upload,idle,Dispatcher,verify
from benchmark_kernel import request
from tinybrainbot_p4_trial import sanitized
ROOT=pathlib.Path(__file__).resolve().parents[1];DATA=ROOT/'data/int4-memory-2026-10-30';PRIVATE=ROOT/'.local/int4-memory-2026-10-30'
IDENTITY='0a0ab7c4fd5cc1cea3f77f77c104ce0684ccdc37db1149aa78a9bdb742a716f3'
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ready(h,version,boot):
 end=time.monotonic()+180
 while time.monotonic()<end:
  try:
   s=status(h)
   if s['firmware']==version and s['model_ready'] and s['model_id']==IDENTITY and s['boot_id']!=boot and not s['ota_pending']:return s
  except (OSError,RuntimeError,ValueError):pass
  time.sleep(2)
 raise RuntimeError('Readiness timeout')
def main():
 PRIVATE.mkdir(exist_ok=False);rollback=ROOT/'.local/tinybrainbot-p4-2026-10-29/p4-0.7.0.bin'
 assert sha(rollback)=='c867d87215cbee256fcf35213b8c539e4ed5d950e3beb2e063d36394e1bd6141'
 image=PRIVATE/'p4-0.8.0.bin';shutil.copyfile(ROOT/'.local/build/rev1/p4_tinystories.bin',image)
 p=json.loads((DATA/'protocol.json').read_text());assert all(sha(ROOT/n)==v for n,v in p['source_sha256'].items())
 idle(Dispatcher(MASTER));states={r:status(h) for r,h in [('coordinator',MASTER),('worker',PEER)]}
 for s in states.values():assert s['firmware']=='0.7.0' and s['model_ready'] and s['model_id']==IDENTITY and not s['worker_busy']
 write(PRIVATE/'before.json',states);write(DATA/'deployment.json',{'firmware_bytes':image.stat().st_size,'private_firmware_sha256':sha(image),'rollback_sha256':sha(rollback),'source_commit':'2e2f6aa','before':{r:sanitized(s) for r,s in states.items()}})
 refs=json.loads((ROOT/'data/matched-p4-2026-10-30/host-references.json').read_text());ref=refs['tinybrainbot']['W'];records=[];changed=[]
 try:
  for role,h in [('worker',PEER),('coordinator',MASTER)]:
   old=status(h);changed.append((role,h));print('OTA0.8',role,flush=True);upload(h,'firmware',image);s=ready(h,'0.8.0',old['boot_id']);write(DATA/(role+'-diagnostic-ready.json'),sanitized(s))
  Dispatcher(MASTER).request('POST','/api/cluster',{'peer':PEER})
  raw=request(MASTER,'POST','/api/generate',{'prompt':'Once upon a time','tokens':4,'peer':PEER},timeout=180);verify(raw,ref);(DATA/'diagnostic-control.ndjson').write_bytes(raw)
  for run in range(6):
   for role,h in ([('coordinator',MASTER),('worker',PEER)] if run%2==0 else [('worker',PEER),('coordinator',MASTER)]):
    raw=request(h,'POST','/api/microbench',run,timeout=180);(DATA/(role+'-'+str(run)+'.json')).write_bytes(raw);r=json.loads(raw)
    assert r['valid'] and r['core']==1 and r['run']==run and len(r['measurements'])==8
    records.append({'board':role,**r});write(DATA/'runs.json',records);print('MEASURE',role,run,'valid',flush=True)
 finally:
  idle(Dispatcher(MASTER))
  for role,h in changed:
   old=status(h);print('RESTORE0.7',role,flush=True);upload(h,'firmware',rollback);s=ready(h,'0.7.0',old['boot_id']);write(DATA/(role+'-restored.json'),sanitized(s))
  Dispatcher(MASTER).request('POST','/api/cluster',{'peer':PEER})
  raw=request(MASTER,'POST','/api/generate',{'prompt':'Once upon a time','tokens':4,'peer':PEER},timeout=180);verify(raw,ref);(DATA/'restored-control.ndjson').write_bytes(raw)
  x=idle(Dispatcher(MASTER));s={r:status(h) for r,h in [('coordinator',MASTER),('worker',PEER)]}
  assert all(v['firmware']=='0.7.0' and v['model_ready'] and v['model_id']==IDENTITY and not v['worker_busy'] and not v['ota_pending'] for v in s.values())
  write(DATA/'final.json',{'devices':{r:sanitized(v) for r,v in s.items()},'queued':x['queued'],'running':x['running'],'configured':x['configured'],'complete_runs':len(records)})
  print('FINAL both0.7 TinyBrainBot ready idle; records',len(records),flush=True)
if __name__=='__main__':main()
