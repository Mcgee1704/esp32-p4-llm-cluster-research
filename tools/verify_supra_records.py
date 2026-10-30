"""Audit saved research contracts; optional non-destructive LAN rejection checks."""
import argparse
import hashlib
import http.client
import json
import struct
from pack_supra import ROOT
from check_supra_native import write
from gptneo_p4_trial import MASTER,PEER,status,Dispatcher,idle,verify


def audit(model):
    out=ROOT/'docs/research/data'/(model+'-2026-10-29')
    protocol=json.loads((out/'protocol.json').read_text('utf-8'))
    refs={r['case']:r for r in json.loads((out/'host-generations.json').read_text('utf-8'))}
    rows=json.loads((out/'p4-runs.json').read_text('utf-8'));expected=protocol.get('hardware_cases',[c['id'] for c in protocol['cases']])
    assert {r['case'] for r in rows}==set(expected) and len(rows)==len(expected)
    for r in rows:
        raw=(out/(r['case']+'-p4.ndjson')).read_bytes();done=verify(raw,refs[r['case']]);assert done==r['done']
        assert done['done'] and not done.get('error') and done['boards']==2 and done['output_tokens']==len(refs[r['case']]['tokens'])
        assert done['prompt_tokens']==len(refs[r['case']]['prompt_tokens'])
        assert done['kernel']['owner_core_mask']==2 and done['kernel']['helper_core_mask']==1 and done['kernel']['overlap_ms']>0
        p=done['profile'];assert p['connections']==1 and p['worker_reports']==p['rpc_calls']
        assert p['rpc_total_ms']>=p['worker_compute_ms'] and done['elapsed_ms']+1>=p['master_compute_ms']+p['worker_compute_ms']
    jobs=json.loads((out/'dispatcher-pair.json').read_text('utf-8'));names=protocol.get('dispatch_cases',['S1','S2'])
    for job,name in zip(jobs,names):assert job['state']=='done' and job['target']=='local';verify(job['raw_ndjson'].encode(),refs[name])
    assert len(jobs)==2 and jobs[0]['finished_ms']<=jobs[1]['started_ms'],'Sharded job intervals overlap'
    timing=json.loads((out/'timing.json').read_text('utf-8'));assert len(timing)==protocol['timing_repeats']
    assert all(x['done'] and x['boards']==2 and not x.get('error') and x['output_tokens']==protocol['timing_limit'] for x in timing)
    states=json.loads((out/'device-memory.json').read_text('utf-8'));artifacts=json.loads((out/'model-artifacts.json').read_text('utf-8'))
    assert states['coordinator']['model_id']==states['worker']['model_id'] and states['coordinator']['end_layer']==states['worker']['first_layer']
    for role in ['coordinator','worker']:
        assert states[role]['artifact_id']==artifacts[role]['artifact_id'] and states[role]['model_ready'] and not states[role]['worker_busy'] and not states[role]['ota_pending']
    result={'direct_verified':len(rows),'dispatched_verified':len(jobs),'timing_repetitions':len(timing),
            'single_lane_nonoverlap':True,'token_bytes_eos_equal':True,'persistent_RPC_connection':True,
            'source_files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.suffix in ['.json','.ndjson'] and p.name!='record-audit.json'}}
    write(out/'record-audit.json',result);print(model,{k:v for k,v in result.items() if k!='source_files_sha256'})


def lan_checks():
    idle(Dispatcher(MASTER));before={h:status(h) for h in [MASTER,PEER]};key=(ROOT/'.local/lan-key.txt').read_text().strip();records=[]
    def check(name,host,path,body,expected,port=80,auth=True,method='POST'):
        headers={'Content-Type':'application/octet-stream'}
        if auth:headers['X-Cluster-Key']=key
        c=http.client.HTTPConnection(host,port,timeout=15)
        try:
            c.request(method,path,body,headers);r=c.getresponse();text=r.read(2048).decode('utf-8','replace')
            assert r.status==expected,(name,r.status,text)
            records.append({'check':name,'expected_http':expected,'observed_http':r.status,'response':text})
        finally:c.close()
    identity=bytes.fromhex(before[PEER]['model_id']);dim=before[PEER]['dim'];split=before[PEER]['first_layer']
    # Struct has eight uint32 fields followed by the 32-byte identity.
    frame=lambda layer,model:struct.pack('<8I32s',0x31505250,1,0x5397a2,0,layer,dim,0,0,model)
    check('status requires LAN key',MASTER,'/api/status',None,401,auth=False,method='GET')
    check('layer worker rejects text generation',PEER,'/api/generate',b'{"prompt":"Hello","tokens":1}',409)
    check('worker rejects wrong layer split',PEER,'/api/rpc',frame(split+1,identity),409)
    check('worker rejects wrong logical model',PEER,'/api/rpc',frame(split,bytes(32)),409)
    check('coordinator rejects worker RPC role',MASTER,'/api/rpc',frame(split,identity),409)
    check('coordinator rejects removal of required worker',MASTER,'/api/cluster',b'{"peer":""}',409,port=8081)
    invalid=bytearray(128);invalid[:8]=b'P4ZL0001';struct.pack_into('<I',invalid,8,256)
    check('empty compressed model rejected before erase',MASTER,'/api/model',invalid,400)
    invalid+=bytes(8);struct.pack_into('<I',invalid,8,1024*1024*1024);struct.pack_into('<I',invalid,36,8)
    check('oversize expansion rejected before erase',MASTER,'/api/model',invalid,400)
    after={h:status(h) for h in [MASTER,PEER]};cluster=idle(Dispatcher(MASTER));assert cluster['configured'] and cluster['mode']=='sharded'
    for h in [MASTER,PEER]:
        assert after[h]['boot_id']==before[h]['boot_id'] and after[h]['model_id']==before[h]['model_id'] and after[h]['artifact_id']==before[h]['artifact_id'] and after[h]['model_ready'] and not after[h]['worker_busy'] and not after[h]['restart_pending']
    write(ROOT/'data/supra100-2026-10-29/lan-rejection-checks.json',{'checks':records,'boots_models_artifacts_unchanged':True,'cluster_configured_idle':True})
    print('LAN rejection checks',len(records),'passed; model and configuration retained')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--lan',action='store_true');a=p.parse_args()
    for model in ['supra50','supra100']:audit(model)
    if a.lan:lan_checks()
