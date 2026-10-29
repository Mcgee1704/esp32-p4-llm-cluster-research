"""Freeze predictions for new text inputs before running real LAN jobs."""
import argparse
import ctypes as C
import hashlib
import json
import pathlib
from benchmark_kernel import request
from dispatch_client import Dispatcher
from simulate_cluster import simulate,ROOT

PROMPTS=['Once upon a time, a small fox found a red ball.',
 'One sunny morning, two friends walked to the river. They wanted to build a small boat.',
 'There was a little bird who could not fly. Every day, its friends helped it practice. '*2]
CASES=[(0,16),(1,8),(2,24),(0,32),(2,8),(1,24)]

def token_counts():
    lib=C.CDLL(str(ROOT/'.local/build/tinyllm.dll'))
    lib.ts_open.argtypes=[C.c_void_p,C.c_size_t];lib.ts_open.restype=C.c_void_p
    lib.ts_close.argtypes=[C.c_void_p]
    lib.ts_encode.argtypes=[C.c_void_p,C.c_char_p,C.POINTER(C.c_int),C.c_int]
    data=(ROOT/'.local/models/stories15M.p4lm').read_bytes();blob=C.create_string_buffer(data)
    state=lib.ts_open(blob,len(data));assert state
    try:
        buf=(C.c_int*2048)();counts=[lib.ts_encode(state,p.encode(),buf,len(buf)) for p in PROMPTS]
        assert all(0<n<=70 for n in counts),counts
        return counts,data[48:80].hex()
    finally:lib.ts_close(state)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('master');p.add_argument('peer')
    p.add_argument('output',type=pathlib.Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    modelpath=ROOT/'data/simulation-v1-2026-10-29/model-v1.json'
    model=json.loads(modelpath.read_text(encoding='utf-8'));counts,identity=token_counts()
    assert identity==model['reference_model_id']
    jobs=[{'case_index':i,'accepted_master_ms':i*20,'prompt_tokens':counts[pi],
           'output_tokens':n} for i,(pi,n) in enumerate(CASES)]
    predictions={str(nodes):simulate(model,jobs,nodes) for nodes in [1,2,3]}
    plan={'prompts':PROMPTS,'cases':CASES,'prompt_tokens':counts,'predictions':predictions,
          'model_sha256':hashlib.sha256(modelpath.read_bytes()).hexdigest(),
          'script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
          'criteria':{'makespan_relative_error_max':.10},
          'assumptions':['all requested tokens produced','planned arrivals 20 ms apart'],
          'measurement_order':['cluster','local']}
    raw=(json.dumps(plan,indent=2)+'\n').encode();(a.output/'frozen-plan.json').write_bytes(raw)
    digest=hashlib.sha256(raw).hexdigest();print('Predictions frozen before device access:',digest,flush=True)
    client=Dispatcher(a.master);original=client.request('GET','/api/cluster')
    assert original['peer']==a.peer and not original['queued'] and not original['running']
    before={ip:json.loads(request(ip,'GET','/api/status')) for ip in [a.master,a.peer]}
    for status in before.values():
        assert status['firmware']==model['reference_firmware'] and status['model_id']==identity
        assert status['default_kernel']=='tile4' and status['model_ready'] and not status['ota_pending']
    (a.output/'status-before.json').write_text(json.dumps(before,indent=2)+'\n',encoding='utf-8')
    results={};sequences={}
    try:
        for mode,nodes in [('cluster',2),('local',1)]:
            client.request('POST','/api/cluster',{'peer':a.peer if nodes==2 else ''})
            ids=[client.submit(PROMPTS[pi],limit)['id'] for pi,limit in CASES]
            (a.output/f'{mode}-accepted.json').write_text(json.dumps(ids)+'\n',encoding='utf-8')
            completed=client.wait(ids,timeout=360,poll=.2)
            (a.output/f'{mode}-jobs.json').write_text(json.dumps(completed,indent=2)+'\n',encoding='utf-8')
            assert all(j['state']=='done' for j in completed)
            actual=max(j['finished_ms'] for j in completed)-min(j['created_ms'] for j in completed)
            full=True;conditional=[]
            for i,(job,(_,limit)) in enumerate(zip(completed,CASES)):
                lines=[json.loads(s) for s in job['raw_ndjson'].splitlines()];done=lines[-1]
                seq=[x['token'] for x in lines if 'token' in x]
                assert done['done'] and not done.get('error') and done['output_tokens']==len(seq)
                assert done['kernel']['mode']=='tile4' and done['prompt_tokens']==jobs[i]['prompt_tokens']
                full &= len(seq)==limit
                if i in sequences:assert sequences[i]==seq,'Output changed between modes'
                sequences[i]=seq
                conditional.append({'case_index':i,'accepted_master_ms':job['created_ms'],
                                    'prompt_tokens':done['prompt_tokens'],'output_tokens':len(seq)})
            predicted=predictions[str(nodes)]['makespan_ms']
            results[mode]={'nodes':nodes,'measured_ms':actual,'frozen_prediction_ms':predicted,
                          'relative_error':predicted/actual-1,'all_requested_tokens_produced':full,
                          'passes':full and abs(predicted/actual-1)<=.10,
                          'conditional_posthoc_prediction':simulate(model,conditional,nodes),
                          'targets':[j['target'] for j in completed]}
            print(mode,'measured',actual,'ms; frozen prediction error',round(100*(predicted/actual-1),2),'%',flush=True)
    finally:
        state=client.request('GET','/api/cluster')
        if not state['queued'] and not state['running']:
            client.request('POST','/api/cluster',{'peer':original['peer']})
    after={ip:json.loads(request(ip,'GET','/api/status')) for ip in [a.master,a.peer]}
    for ip in before:assert after[ip]['boot_id']==before[ip]['boot_id'] and after[ip]['model_ready']
    assert hashlib.sha256((a.output/'frozen-plan.json').read_bytes()).hexdigest()==digest
    report={'frozen_plan_sha256':digest,'results':results,'status_after':after,
            'tokens_identical_between_modes':True,'model_refitted':False,
            'three_node_prediction_is_unmeasured':True}
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
