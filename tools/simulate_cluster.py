"""Local discrete-event approximation of replicated-model P4 jobs, version 1."""
import argparse
import hashlib
import itertools
import json
import math
import pathlib
import statistics

ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/'data/kernel-v3-2026-10-29/simulation-data/records.json'

def solve(a,b):
    n=len(b);m=[list(row)+[v] for row,v in zip(a,b)]
    for col in range(n):
        pivot=max(range(col,n),key=lambda r:abs(m[r][col]))
        if abs(m[pivot][col])<1e-10:raise ValueError('Singular design')
        m[col],m[pivot]=m[pivot],m[col]
        scale=m[col][col];m[col]=[v/scale for v in m[col]]
        for row in range(n):
            if row!=col:
                scale=m[row][col];m[row]=[x-scale*y for x,y in zip(m[row],m[col])]
    return [row[-1] for row in m]

def features(row):return [1.,float(row['prompt_tokens']-1),float(row['output_tokens'])]

def fit(records):
    rows=[r for r in records if r['dataset']=='calibration']
    if len(rows)<3:raise ValueError('Need at least three calibration jobs')
    x=[features(r) for r in rows];y=[r['backend_elapsed_ms'] for r in rows]
    best=None
    # Enumerate the active sets of three nonnegative least-squares parameters.
    for count in range(1,4):
        for active in itertools.combinations(range(3),count):
            a=[[sum(v[i]*v[j] for v in x) for j in active] for i in active]
            b=[sum(v[i]*target for v,target in zip(x,y)) for i in active]
            try:values=solve(a,b)
            except ValueError:continue
            if any(v<0 for v in values):continue
            coef=[0.]*3
            for index,value in zip(active,values):coef[index]=value
            loss=sum((sum(c*v for c,v in zip(coef,row))-target)**2 for row,target in zip(x,y))
            if best is None or loss<best[0]:best=(loss,coef)
    if best is None:raise ValueError('No nonnegative model')
    residuals={};gaps={};initial={}
    origin=min(r['accepted_master_ms'] for r in rows)
    for role in ['local','worker']:
        selected=sorted([r for r in rows if (r['target']=='local')==(role=='local')],key=lambda r:r['started_master_ms'])
        if not selected:raise ValueError('Missing target role')
        residuals[role]=max(0.,statistics.median(r['forwarding_residual_ms'] for r in selected))
        gap=[b['started_master_ms']-a['finished_master_ms'] for a,b in zip(selected,selected[1:])]
        if any(v<0 for v in gap):raise ValueError('Overlapping jobs on one target')
        gaps[role]=statistics.median(gap) if gap else 0.
        initial[role]=selected[0]['started_master_ms']-origin
    return {'version':1,'coefficients_ms':best[1],'forwarding_ms':residuals,
            'refill_gap_ms':gaps,'initial_probe_ms':initial,
            'training_job_ids':[r['job_id'] for r in rows],
            'training_backend_rmse_ms':math.sqrt(best[0]/len(rows))}

def backend(model,row):return sum(c*v for c,v in zip(model['coefficients_ms'],features(row)))

def simulate(model,jobs,nodes,worker_scale=1.,probe_scale=1.):
    if not jobs or nodes<1 or nodes>3 or worker_scale<=0 or probe_scale<0:raise ValueError('Invalid scenario')
    ordered=sorted(jobs,key=lambda r:(r['accepted_master_ms'],r['case_index']))
    origin=ordered[0]['accepted_master_ms']
    roles=['local']+['worker']*(nodes-1)
    available=[model['initial_probe_ms'][role]*probe_scale for role in roles]
    results=[]
    for job in ordered:
        arrival=job['accepted_master_ms']-origin
        lane=min(range(nodes),key=lambda i:(max(arrival,available[i]),i))
        role=roles[lane];start=max(arrival,available[lane])
        service=backend(model,job)+model['forwarding_ms'][role]
        # Third-node uncertainty changes only the extra worker, not measured lanes.
        if lane==2:service*=worker_scale
        finish=start+service
        available[lane]=finish+model['refill_gap_ms'][role]*probe_scale
        results.append({'case_index':job['case_index'],'lane':lane,'role':role,
                        'arrival_ms':arrival,'start_ms':start,'finish_ms':finish,
                        'queue_ms':start-arrival,'service_ms':service})
    return {'nodes':nodes,'makespan_ms':max(r['finish_ms'] for r in results),
            'jobs':results,'output_tokens':sum(r['output_tokens'] for r in ordered)}

def evaluate(model,rows,prediction):
    actual=max(r['finished_master_ms'] for r in rows)-min(r['accepted_master_ms'] for r in rows)
    service=[]
    for row in rows:
        role='local' if row['target']=='local' else 'worker'
        estimate=backend(model,row)+model['forwarding_ms'][role]
        service.append({'case_index':row['case_index'],'actual_ms':row['service_ms'],
                        'predicted_ms':estimate,'relative_error':(estimate/row['service_ms']-1)})
    return {'actual_makespan_ms':actual,'predicted_makespan_ms':prediction['makespan_ms'],
            'makespan_relative_error':prediction['makespan_ms']/actual-1,
            'service_median_absolute_relative_error':statistics.median(abs(r['relative_error']) for r in service),
            'services':service}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=pathlib.Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    records=json.loads(DATA.read_text(encoding='utf-8'))
    model=fit(records)
    metadata=json.loads((DATA.parent/'metadata.json').read_text(encoding='utf-8'))
    statuses=list(metadata['status_before'].values())
    model['reference_firmware']=statuses[0]['firmware']
    model['reference_kernel']=statuses[0]['default_kernel']
    model['reference_model_id']=statuses[0]['model_id']
    model['calibration_jobs']=len(model['training_job_ids'])
    model['source_sha256']=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
    model['data_sha256']=hashlib.sha256(DATA.read_bytes()).hexdigest()
    (a.output/'model-v1.json').write_text(json.dumps(model,indent=2)+'\n',encoding='utf-8')
    validation=[r for r in records if r['dataset']=='validation']
    two=simulate(model,validation,2)
    # Store the prediction before scoring; no refitting after the score.
    (a.output/'two-node-prediction.json').write_text(json.dumps(two,indent=2)+'\n',encoding='utf-8')
    score=evaluate(model,validation,two)
    score['criteria']={'makespan_absolute_relative_error_max':.10,'service_median_absolute_relative_error_max':.15}
    score['passes_exploratory_criteria']=abs(score['makespan_relative_error'])<=.10 and score['service_median_absolute_relative_error']<=.15
    # External one-node check: same A/B package previously measured in firmware 0.4.0.
    batches=json.loads((ROOT/'data/kernel-v3-2026-10-29/cluster-comparison/batches.json').read_text(encoding='utf-8'))
    local=[b for b in batches if b['kernel']=='tile4' and b['mode']=='local']
    sample=local[0]['jobs'];jobs=[]
    for index,job in enumerate(sample):
        done=json.loads(job['raw_ndjson'].splitlines()[-1])
        jobs.append({'accepted_master_ms':job['created_ms'],'case_index':index,
                     'prompt_tokens':done['prompt_tokens'],'output_tokens':done['output_tokens']})
    one=simulate(model,jobs,1);observed=statistics.median(b['elapsed_ms'] for b in local)
    one_check={'actual_median_ms':observed,'prediction':one,'relative_error':one['makespan_ms']/observed-1}
    forecast=simulate(model,validation,3)
    sensitivities=[{'extra_worker_scale':speed,'probe_scale':probe,
                    'makespan_ms':simulate(model,validation,3,speed,probe)['makespan_ms']}
                   for speed in [.8,1.,1.2] for probe in [0.,1.,2.]]
    forecast.update({'classification':'scenario; not a validated three-node performance claim',
        'conditional_on_exploratory_check':score['passes_exploratory_criteria'],
        'speedup_vs_simulated_two_nodes':two['makespan_ms']/forecast['makespan_ms'],
        'sensitivity':sensitivities,'sensitivity_is_confidence_interval':False,
        'assumptions':['extra worker copies the existing worker',
            'third dispatcher lane will exist','no extra master or switch contention',
            'same known output lengths; no EOS prediction','independent full-model requests']})
    for name,value in [('validation.json',score),('one-node-check.json',one_check),('three-node-scenario-v1.json',forecast)]:
        (a.output/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'validation_error_percent':score['makespan_relative_error']*100,
                     'service_median_error_percent':score['service_median_absolute_relative_error']*100,
                     'one_node_error_percent':one_check['relative_error']*100,
                     'three_node_ms':forecast['makespan_ms'],'scenario_speedup':forecast['speedup_vs_simulated_two_nodes']}))

if __name__=='__main__':main()
