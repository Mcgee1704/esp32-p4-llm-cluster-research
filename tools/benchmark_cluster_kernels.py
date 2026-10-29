"""Same firmware, fixed model: compare kernel modes and local/cluster throughput."""
import argparse
import datetime
import hashlib
import json
import pathlib
import statistics
import time
from benchmark_kernel import PROMPTS, request
from benchmark_dispatcher import tokens
from dispatch_client import Dispatcher
from lan_client import ROOT, lan_address

CASES = [('legacy','cluster'),('paced','cluster'),('dual','cluster'),('dual','local')]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('master',type=lan_address)
    p.add_argument('peer',type=lan_address)
    p.add_argument('output',type=pathlib.Path)
    p.add_argument('--v3',action='store_true',help='Compare dual, sram, tile4 and tile4 on master only')
    a=p.parse_args();cases=([('dual','cluster'),('sram','cluster'),('tile4','cluster'),('tile4','local')] if a.v3 else CASES)
    a.output.mkdir(parents=True,exist_ok=False)
    client=Dispatcher(a.master)
    original=client.request('GET','/api/cluster')
    assert original['configured'] and not original['queued'] and not original['running']
    statuses={ip:json.loads(request(ip,'GET','/api/status')) for ip in [a.master,a.peer]}
    assert statuses[a.master]['model_id']==statuses[a.peer]['model_id']
    assert statuses[a.master]['firmware']==statuses[a.peer]['firmware']
    reference={j['prompt']:j['tokens'] for j in json.loads((ROOT/'data/parallel-2026-10-29/batches.json').read_text())[0]['jobs']}
    orders=[cases[n:]+cases[:n] for n in range(4)]
    metadata={'date_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'orders':orders,'prompts':PROMPTS,'tokens_per_job':24,'status_before':statuses,
              'script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}
    (a.output/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    batches=[]
    try:
        for block,order in enumerate(orders,1):
            for kernel,mode in order:
                client.request('POST','/api/cluster',{'peer':a.peer if mode=='cluster' else ''})
                start=time.perf_counter()
                ids=[client.request('POST','/api/jobs',{'prompt':prompt,'tokens':24,'kernel':kernel})['id'] for prompt in PROMPTS]
                results=client.wait(ids,poll=.15)
                client_ms=(time.perf_counter()-start)*1000
                (a.output/f'{block}-{kernel}-{mode}.json').write_text(json.dumps(results,indent=2)+'\n')
                for prompt,job in zip(PROMPTS,results):
                    assert tokens(job)==reference[prompt]
                    done=json.loads(job['raw_ndjson'].splitlines()[-1])
                    assert done['kernel']['mode']==kernel
                    if kernel in ('dual','sram','tile4'):
                        k=done['kernel']
                        assert k['owner_core_mask']==2 and k['helper_core_mask']==1
                        assert k['helper_rows']>0 and k['overlap_ms']>0 and k['parallel_calls']>0
                        if kernel in ('sram','tile4'):assert k['work_internal']
                targets={j['target'] for j in results}
                assert targets==({'local',a.peer} if mode=='cluster' else {'local'}),targets
                elapsed=max(j['finished_ms'] for j in results)-min(j['created_ms'] for j in results)
                batches.append({'block':block,'kernel':kernel,'mode':mode,'elapsed_ms':elapsed,
                                'client_ms':client_ms,'tokens_per_second':48000/elapsed,'jobs':results})
                (a.output/'batches.json').write_text(json.dumps(batches,indent=2)+'\n')
                print(f'{block} {kernel}/{mode}: {elapsed} ms; targets {sorted(targets)}; exact tokens',flush=True)
    finally:
        # Do not interfere with accepted work if an experiment failed mid-flight.
        state=client.request('GET','/api/cluster')
        if not state['queued'] and not state['running']:
            client.request('POST','/api/cluster',{'peer':original['peer']})
    after={ip:json.loads(request(ip,'GET','/api/status')) for ip in [a.master,a.peer]}
    for ip in after:
        assert after[ip]['boot_id']==statuses[ip]['boot_id'] and after[ip]['model_ready']
        assert not after[ip]['worker_busy'] and not after[ip]['ota_pending']
    summary={'all_tokens_identical':True,'jobs':len(batches)*2,'status_after':after,'cases':{}}
    for kernel,mode in cases:
        data=[b for b in batches if b['kernel']==kernel and b['mode']==mode]
        summary['cases'][kernel+'-'+mode]={'median_ms':statistics.median(b['elapsed_ms'] for b in data),
            'range_ms':[min(b['elapsed_ms'] for b in data),max(b['elapsed_ms'] for b in data)],
            'tokens_per_second':statistics.median(b['tokens_per_second'] for b in data)}
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
