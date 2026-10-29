"""Local hardware regression checks after the controlled performance runs."""
import argparse
import concurrent.futures
import http.client
import json
import pathlib
import time
from benchmark_kernel import request, PROMPTS
from dispatch_client import Dispatcher
from lan_client import ROOT, lan_address

def parse(raw):
    items=[json.loads(x) for x in raw.splitlines()]
    done=items[-1];ids=[x['token'] for x in items if 'token' in x]
    assert done.get('done') and not done.get('error') and done['output_tokens']==len(ids)
    return ids,done

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('master',type=lan_address);p.add_argument('peer',type=lan_address)
    p.add_argument('output',type=pathlib.Path)
    p.add_argument('--expected-default',choices=['dual','sram','tile4'],default='dual')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    client=Dispatcher(a.master)
    before={ip:json.loads(request(ip,'GET','/api/status')) for ip in [a.master,a.peer]}
    report={'before':before,'invalid_requests':[]}
    for port,path in [(80,'/api/generate'),(8081,'/api/jobs')]:
        for mode in ['unknown',None,7]:
            c=http.client.HTTPConnection(a.master,port,timeout=10)
            try:
                c.request('POST',path,json.dumps({'prompt':PROMPTS[0],'tokens':4,'kernel':mode}),
                          {'X-Cluster-Key':(ROOT/'.local/lan-key.txt').read_text().strip(),'Content-Type':'application/json'})
                r=c.getresponse();body=r.read().decode();assert r.status==400,(port,mode,r.status,body)
                report['invalid_requests'].append({'port':port,'kernel':mode,'status':r.status})
            finally:c.close()
    reference={j['prompt']:j['tokens'] for j in json.loads((ROOT/'data/parallel-2026-10-29/batches.json').read_text())[0]['jobs']}
    ids=[client.submit(prompt,8)['id'] for prompt in PROMPTS]
    jobs=client.wait(ids)
    assert {j['target'] for j in jobs}=={'local',a.peer}
    for prompt,job in zip(PROMPTS,jobs):
        assert job['state']=='done'
        sequence,done=parse(job['raw_ndjson'].encode())
        assert sequence==reference[prompt][:8] and done['kernel']['mode']==a.expected_default
    report['default_jobs']=jobs
    # Poll only the separate control service; port 80 retains one inference owner.
    latencies=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(request,a.master,'POST','/api/generate',{'prompt':PROMPTS[0],'tokens':64})
        while not future.done():
            start=time.perf_counter();state=client.request('GET','/api/cluster')
            latencies.append((time.perf_counter()-start)*1000)
            assert state['firmware']==before[a.master]['firmware']
            time.sleep(.5)
        raw=future.result()
    (a.output/'responsiveness.ndjson').write_bytes(raw)
    sequence,done=parse(raw);assert sequence[:24]==reference[PROMPTS[0]] and done['kernel']['mode']==a.expected_default
    report['control_latency_ms']=latencies;report['responsiveness_generation']=done
    # Longer prefill and another prompt: compare complete token sequences.
    prompt='Once upon a time, there was a little girl. She lived near a forest. '*4
    long_results=[]
    for mode in ['legacy',a.expected_default]:
        raw=request(a.peer,'POST','/api/generate',{'prompt':prompt,'tokens':24,'kernel':mode})
        (a.output/f'long-{mode}.ndjson').write_bytes(raw)
        sequence,done=parse(raw);assert len(sequence)==24
        long_results.append({'kernel':mode,'tokens':sequence,'done':done})
    assert long_results[0]['tokens']==long_results[1]['tokens']
    report['long_prompt']=prompt;report['long_results']=long_results
    raw=request(a.master,'POST','/api/generate',{'prompt':PROMPTS[0],'tokens':4,'peer':a.peer})
    (a.output/'layer-rpc.ndjson').write_bytes(raw)
    sequence,done=parse(raw)
    assert sequence==reference[PROMPTS[0]][:4] and done['boards']==2 and done['profile']['connections']==1
    report['layer_rpc']=done
    after={ip:json.loads(request(ip,'GET','/api/status')) for ip in [a.master,a.peer]}
    for ip,status in after.items():
        assert status['boot_id']==before[ip]['boot_id'] and status['model_ready']
        assert not status['worker_busy'] and not status['ota_pending']
    report['after']=after;report['cluster']=client.request('GET','/api/cluster')
    assert not report['cluster']['queued'] and not report['cluster']['running']
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':True,'control_samples':len(latencies),'max_control_ms':max(latencies),
                      'long_prompt_tokens_identical':True,'default_jobs_on_both_boards':True}),flush=True)

if __name__=='__main__':main()
