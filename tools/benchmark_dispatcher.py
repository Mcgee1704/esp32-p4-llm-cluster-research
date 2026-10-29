"""All job submissions target one master; worker selection happens on the P4."""
import argparse
import csv
import hashlib
import json
import pathlib
import statistics
import time
from dispatch_client import Dispatcher
from lan_client import lan_address, ROOT

PROMPTS = ['Once upon a time', 'One day, a little girl']
ORDERS = [('local','cluster'),('cluster','local'),('cluster','local'),('local','cluster')]

def tokens(job):
    assert job['state'] == 'done', job
    lines = [json.loads(line) for line in job['raw_ndjson'].splitlines()]
    done = lines[-1]
    sequence = [item['token'] for item in lines if 'token' in item]
    assert done.get('done') and not done.get('error') and done['boards'] == 1
    assert done['output_tokens'] == len(sequence) == 24
    return sequence

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('master',type=lan_address);p.add_argument('peer',type=lan_address);p.add_argument('output',type=pathlib.Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);client=Dispatcher(a.master)
    reference = {}
    previous=json.loads((ROOT/'data/parallel-2026-10-29/batches.json').read_text())
    for j in previous[0]['jobs']:reference[j['prompt']]=j['tokens']
    metadata={'master':a.master,'peer':a.peer,'job_endpoint':f'http://{a.master}:8081/api/jobs',
              'orders':ORDERS,'prompts':PROMPTS,'tokens_per_job':24,
              'script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}
    (a.output/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    batches=[]
    for block,order in enumerate(ORDERS,1):
        for mode in order:
            configuration=client.request('POST','/api/cluster',{'peer':a.peer if mode=='cluster' else ''})
            start=time.perf_counter()
            ids=[client.submit(prompt,24)['id'] for prompt in PROMPTS]
            results=client.wait(ids,poll=.15)
            client_ms=(time.perf_counter()-start)*1000
            (a.output/f'{block}-{mode}.json').write_text(json.dumps(results,indent=2)+'\n')
            for prompt,job in zip(PROMPTS,results):assert tokens(job)==reference[prompt]
            targets={j['target'] for j in results}
            assert targets==({'local',a.peer} if mode=='cluster' else {'local'}),targets
            elapsed=max(j['finished_ms'] for j in results)-min(j['created_ms'] for j in results)
            overlap=max(0,min(j['finished_ms'] for j in results)-max(j['started_ms'] for j in results))
            batch={'block':block,'mode':mode,'master_elapsed_ms':elapsed,'client_elapsed_ms':client_ms,
                   'tokens_per_second':48000/elapsed,'overlap_ms':overlap,
                   'queue_ms':[j['queue_ms'] for j in results],'targets':[j['target'] for j in results],
                   'configuration':configuration,'jobs':results}
            batches.append(batch);(a.output/'batches.json').write_text(json.dumps(batches,indent=2)+'\n')
            print(f'Block {block} {mode}: master {elapsed/1000:.3f} s, client {client_ms/1000:.3f} s, targets {batch["targets"]}, queue {batch["queue_ms"]} ms',flush=True)
    client.request('POST','/api/cluster',{'peer':a.peer})
    summary={'all_tokens_match_previous_parallel_experiment':True,'blocks':4,'jobs':16}
    for mode in ['local','cluster']:
        data=[b for b in batches if b['mode']==mode]
        summary[mode]={k:statistics.median(b[k] for b in data) for k in ['master_elapsed_ms','client_elapsed_ms','tokens_per_second','overlap_ms']}
        summary[mode]['range_ms']=[min(b['master_elapsed_ms'] for b in data),max(b['master_elapsed_ms'] for b in data)]
    ratios=[next(b['master_elapsed_ms'] for b in batches if b['block']==i and b['mode']=='local')/
            next(b['master_elapsed_ms'] for b in batches if b['block']==i and b['mode']=='cluster') for i in range(1,5)]
    summary['paired_speedups']=ratios;summary['median_paired_speedup']=statistics.median(ratios)
    summary['final_cluster']=client.request('GET','/api/cluster')
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (a.output/'batches.csv').open('w',encoding='utf-8',newline='') as f:
        fields=['block','mode','master_elapsed_ms','client_elapsed_ms','tokens_per_second','overlap_ms']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows({k:b[k] for k in fields} for b in batches)
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
