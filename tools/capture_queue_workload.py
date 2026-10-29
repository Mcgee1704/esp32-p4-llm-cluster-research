"""Capture real two-board queue timings for a future simulation; no virtual node."""
import argparse
import csv
import datetime
import hashlib
import json
import math
import pathlib
import time
from benchmark_kernel import request, PROMPTS
from dispatch_client import Dispatcher
from lan_client import ROOT, lan_address

LONG = 'Once upon a time, there was a little girl. She lived near a forest. '*4
PLANS = {
    'calibration': [(0,8),(1,24),(2,16),(0,48),(1,8),(2,24)],
    'validation': [(1,16),(0,32),(2,8),(1,48),(0,24),(2,32)],
}

def record_job(job, case, boot_id):
    if job['state'] != 'done': raise ValueError('Unfinished/failed job is not a service-time sample')
    created,started,finished=(job[k] for k in ['created_ms','started_ms','finished_ms'])
    if not 0 <= created <= started <= finished: raise ValueError('Invalid master timestamps')
    if job['queue_ms'] != started-created: raise ValueError('Queue duration mismatch')
    items=[json.loads(line) for line in job['raw_ndjson'].splitlines()]
    done=items[-1];ids=[x['token'] for x in items if 'token' in x]
    if not done.get('done') or done.get('error') or done['output_tokens']!=len(ids):
        raise ValueError('Invalid backend completion')
    if not 0 < len(ids) <= case['requested_tokens']: raise ValueError('Invalid output count')
    if not all(math.isfinite(done[k]) for k in ('elapsed_ms','ttft_ms')) or not 0 <= done['ttft_ms'] <= done['elapsed_ms']:
        raise ValueError('Invalid backend durations')
    service=finished-started
    return {'job_id':job['id'],'dataset':case['dataset'],'case_index':case['case_index'],
            'master_boot_id':boot_id,'target':job['target'],'prompt_index':case['prompt_index'],
            'prompt_tokens':done['prompt_tokens'],'requested_tokens':case['requested_tokens'],
            'output_tokens':len(ids),'kernel':done['kernel']['mode'],
            'accepted_master_ms':created,'started_master_ms':started,'finished_master_ms':finished,
            'queue_ms':started-created,'service_ms':service,'total_ms':finished-created,
            'backend_elapsed_ms':done['elapsed_ms'],'backend_ttft_ms':done['ttft_ms'],
            'matmul_ms':done['kernel'].get('matmul_ms'),'finish_ms':done['kernel'].get('finish_ms'),
            'matrix_owner_pause_ms':done['kernel'].get('pause_ms'),'barrier_ms':done['kernel'].get('barrier_ms'),
            'forwarding_residual_ms':service-done['elapsed_ms'],
            'client_submit_start_ms':case['client_submit_start_ms'],
            'client_accept_ms':case['client_accept_ms']}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('master',type=lan_address);p.add_argument('peer',type=lan_address)
    p.add_argument('output',type=pathlib.Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    client=Dispatcher(a.master);state=client.request('GET','/api/cluster')
    assert state['configured'] and state['peer']==a.peer and not state['queued'] and not state['running']
    before={ip:json.loads(request(ip,'GET','/api/status')) for ip in [a.master,a.peer]}
    assert before[a.master]['firmware']==before[a.peer]['firmware']
    assert before[a.master]['model_id']==before[a.peer]['model_id']
    mode=before[a.master]['default_kernel'];assert before[a.peer]['default_kernel']==mode
    prompts=PROMPTS+[LONG]
    ref={j['prompt']:j['tokens'] for j in json.loads((ROOT/'data/parallel-2026-10-29/batches.json').read_text(encoding='utf-8'))[0]['jobs']}
    ref[LONG]=json.loads((ROOT/'data/kernel-v2-2026-10-29/integration/report.json').read_text(encoding='utf-8'))['long_results'][0]['tokens']
    metadata={'schema_version':1,'date_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'hardware_nodes':2,'simulated_nodes':0,'plans':PLANS,'prompts':prompts,
              'status_before':before,'script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
              'clock_notes':'Master timestamps share one boot clock. Client offsets are relative to each burst start; never subtract them from board clocks.',
              'split_notes':'Validation burst reserved in advance; no fitting or third-node prediction performed.'}
    (a.output/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    records=[]
    for dataset,plan in PLANS.items():
        cases=[];start=time.perf_counter()
        for index,(prompt_index,count) in enumerate(plan):
            sent=(time.perf_counter()-start)*1000
            accepted=client.submit(prompts[prompt_index],count)
            cases.append({'id':accepted['id'],'dataset':dataset,'case_index':index,
                          'prompt_index':prompt_index,'requested_tokens':count,
                          'client_submit_start_ms':sent,'client_accept_ms':(time.perf_counter()-start)*1000})
            (a.output/f'{dataset}-submitted.json').write_text(json.dumps(cases,indent=2)+'\n',encoding='utf-8')
        jobs=client.wait([c['id'] for c in cases],timeout=360,poll=.2)
        (a.output/f'{dataset}-jobs.json').write_text(json.dumps(jobs,indent=2)+'\n',encoding='utf-8')
        for job,case in zip(jobs,cases):
            row=record_job(job,case,before[a.master]['boot_id'])
            assert row['kernel']==mode
            ids=[x['token'] for x in map(json.loads,job['raw_ndjson'].splitlines()) if 'token' in x]
            expected=ref[prompts[case['prompt_index']]][:len(ids)]
            assert ids[:len(expected)]==expected
            row['verified_reference_prefix_tokens']=len(expected)
            # Work intervals share the master clock, including transport overhead.
            row['jobs_with_overlapping_service_intervals']=sum(other['id']!=job['id'] and
                max(job['started_ms'],other['started_ms'])<min(job['finished_ms'],other['finished_ms']) for other in jobs)
            row['active_jobs_at_start']=sum(other['started_ms']<=job['started_ms']<other['finished_ms'] for other in jobs)
            assert 1<=row['active_jobs_at_start']<=2
            records.append(row)
        print(dataset,'six real jobs completed; exact reference prefixes',flush=True)
    after={ip:json.loads(request(ip,'GET','/api/status')) for ip in [a.master,a.peer]}
    for ip in before:
        assert after[ip]['boot_id']==before[ip]['boot_id'] and after[ip]['model_ready'] and not after[ip]['worker_busy']
    (a.output/'status-after.json').write_text(json.dumps(after,indent=2)+'\n',encoding='utf-8')
    (a.output/'records.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
    with (a.output/'records.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    assert {r['target'] for r in records}=={'local',a.peer}
    print('Saved 12 measured jobs; calibration and validation remain separate',flush=True)

if __name__=='__main__':main()
