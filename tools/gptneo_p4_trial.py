"""Staged private-LAN GPT-Neo installation and controlled two-board study.

Writes real devices only in explicit peer/master/benchmark stages. The prepare
stage freezes artifacts, references and protocol. No public network is used.
"""
import argparse
import hashlib
import http.client
import json
import pathlib
import shutil
import statistics
import time
from benchmark_kernel import request
from check_gptneo_native import Native
from dispatch_client import Dispatcher
from evaluate_tinytalk import prompt
from lan_client import ROOT,lan_address
from textmodel_trial import parse

MASTER='10.0.0.121';PEER='10.0.0.131'
VERSION='0.5.5'
SFT=ROOT/'.local/models/llama2-15m-sft-4d69f1c13019/stories15M-sft.p4lm'
NEO=ROOT/'.local/models/tinytalk2.p4gn'
WORK=ROOT/'.local/gptneo-p4-2026-10-29'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
def status(host):return json.loads(request(lan_address(host),'GET','/api/status',timeout=8))
def idle(client):
    x=client.request('GET','/api/cluster')
    if x['queued'] or x['running']:raise RuntimeError('Dispatcher has active jobs')
    return x


def upload(host,kind,path):
    host=lan_address(host);c=http.client.HTTPConnection(host,timeout=180)
    try:
        c.putrequest('POST','/api/'+kind)
        c.putheader('X-Cluster-Key',(ROOT/'.local/lan-key.txt').read_text().strip())
        c.putheader('Content-Type','application/octet-stream');c.putheader('Content-Length',path.stat().st_size);c.endheaders()
        with path.open('rb') as f:
            while chunk:=f.read(65536):c.send(chunk)
        response=c.getresponse();body=response.read()
        if response.status!=200:raise RuntimeError((host,kind,response.status,body[:300]))
    finally:c.close()


def ready(host,identity,old_boot=None):
    deadline=time.monotonic()+150;last=None;last_at=None
    while time.monotonic()<deadline:
        try:
            last=status(host)
            last_at=time.monotonic()
            if last['firmware']==VERSION and last['model_ready'] and last['model_id']==identity and not last['ota_pending'] and (old_boot is None or last['boot_id']!=old_boot):return last
        except (OSError,RuntimeError,ValueError):pass
        time.sleep(2)
    raise RuntimeError(('Device readiness timeout',host,{'last_status_age_seconds':None if last_at is None else round(time.monotonic()-last_at,1),'last_status':last}))


def verify(raw,expected):
    ids,done=parse(raw)
    if ids!=expected['tokens'] or done.get('eos')!=expected['eos']:raise RuntimeError(('Hardware tokens/EOS differ',ids,expected['tokens']))
    data=b''.join(bytes.fromhex(j['bytes_hex']) for j in map(json.loads,raw.splitlines()) if 'bytes_hex' in j)
    if data.decode('utf-8','replace')!=expected['text']:raise RuntimeError('Hardware decoded text differs')
    return done


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    client=Dispatcher(MASTER);cluster=idle(client);states={h:status(h) for h in [MASTER,PEER]}
    sid=SFT.read_bytes()[48:80].hex()
    for host,x in states.items():
        allowed_versions=['0.4.0'] if host==MASTER else ['0.4.0','0.5.2']
        if x['firmware'] not in allowed_versions or x['model_id']!=sid or not x['model_ready'] or x['worker_busy'] or x['ota_pending']:raise RuntimeError('Unexpected starting device state')
    WORK.mkdir(parents=True,exist_ok=True)
    firmware=WORK/('p4-'+VERSION+'.bin');shutil.copyfile(ROOT/'.local/build/rev1/p4_tinystories.bin',firmware)
    old_protocol=json.loads((ROOT/'data/tinytalk2-host-2026-10-29/protocol.json').read_text(encoding='utf-8'))
    cases=old_protocol['cases'];references={};native=Native(NEO)
    try:
        for case in cases:references[case['id']]=native.generate(prompt(case),case['limit'])
    finally:native.close()
    legacy_prompt='Write a story about: a little girl and her dog\nWith: happy ending\n\n### Story:\n'
    native=Native(SFT)
    try:legacy=native.generate(legacy_prompt,24)
    finally:native.close()
    artifacts={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in [firmware,NEO,SFT,WORK/'rollback/p4-0.4.0.bin']}
    p={'master':MASTER,'peer':PEER,'firmware':VERSION,'old_model_id':sid,'new_model_id':NEO.read_bytes()[48:80].hex(),
       'artifacts_sha256':artifacts,'cases':cases,'legacy_prompt':legacy_prompt,'legacy_reference':legacy,
       'benchmark_cases':['Q1','Q2'],'benchmark_cap':32,'benchmark_blocks':4,
       'order':'local then cluster on odd blocks; cluster then local on even blocks',
       'timing':'master monotonic min acceptance to max completion; two independent requests',
       'model_order':'peer firmware with SFT control, peer TinyTalk with automatic cold reboot, peer same-image OTA reboot, master firmware/SFT control, master TinyTalk with automatic cold reboot, two-lane study',
       'script_sha256':sha(pathlib.Path(__file__))}
    write(out/'protocol.json',p);(out/'protocol.sha256').write_text(sha(out/'protocol.json')+'\n',encoding='utf-8')
    write(out/'native-references.json',references);write(out/'before.json',{'devices':states,'cluster':cluster})
    print('Frozen hardware protocol; both starting devices verified idle',flush=True)


def load(out):
    p=json.loads((out/'protocol.json').read_text(encoding='utf-8'))
    if sha(out/'protocol.json')!=(out/'protocol.sha256').read_text().strip() or p['script_sha256']!=sha(pathlib.Path(__file__)):raise RuntimeError('Frozen protocol/script changed')
    for name,h in p['artifacts_sha256'].items():
        if sha(ROOT/name)!=h:raise RuntimeError('Frozen artifact changed')
    return p,json.loads((out/'native-references.json').read_text(encoding='utf-8'))


def peer_stage(out,p,refs):
    client=Dispatcher(MASTER);idle(client)
    client.request('POST','/api/cluster',{'peer':''})
    previous=status(PEER);print('Peer: uploading firmware, retaining SFT',flush=True)
    upload(PEER,'firmware',WORK/('p4-'+VERSION+'.bin'))
    state=ready(PEER,p['old_model_id'],previous['boot_id']);write(out/'peer-firmware-sft.json',state)
    raw=request(PEER,'POST','/api/generate',{'prompt':p['legacy_prompt'],'tokens':24})
    (out/'peer-sft-control.ndjson').write_bytes(raw);verify(raw,p['legacy_reference'])
    print('Peer: old Llama control passed; uploading TinyTalk',flush=True)
    old_boot=state['boot_id'];upload(PEER,'model',NEO);state=ready(PEER,p['new_model_id'],old_boot);write(out/'peer-model-ready.json',state)
    rows=[]
    for case in p['cases']:
        raw=request(PEER,'POST','/api/generate',{'prompt':prompt(case),'tokens':case['limit']})
        (out/('peer-'+case['id']+'.ndjson')).write_bytes(raw);done=verify(raw,refs[case['id']])
        rows.append({'case':case['id'],**done});write(out/'peer-results.json',rows)
        print('Peer',case['id'],done['output_tokens'],'tokens matched',flush=True)
    previous=status(PEER)
    print('Peer: verifying persistent TinyTalk through same-image LAN OTA reboot',flush=True)
    upload(PEER,'firmware',WORK/('p4-'+VERSION+'.bin'))
    state=ready(PEER,p['new_model_id'],previous['boot_id'])
    case=next(c for c in p['cases'] if c['id']=='Q1')
    raw=request(PEER,'POST','/api/generate',{'prompt':prompt(case),'tokens':case['limit']})
    (out/'peer-after-reboot.ndjson').write_bytes(raw);verify(raw,refs['Q1'])
    write(out/'peer-stage-passed.json',{'state':state,'generations':len(rows),'normal_OTA_reboot_passed':True})
    print('Peer stage passed',flush=True)


def master_stage(out,p,refs):
    if not (out/'peer-stage-passed.json').exists():raise RuntimeError('One-board gate not passed')
    client=Dispatcher(MASTER);idle(client)
    if client.request('GET','/api/cluster')['peer']:raise RuntimeError('Master must still be in local-only maintenance setup')
    ready(PEER,p['new_model_id']);previous=status(MASTER)
    print('Master: uploading firmware, retaining SFT first',flush=True)
    upload(MASTER,'firmware',WORK/('p4-'+VERSION+'.bin'));ready(MASTER,p['old_model_id'],previous['boot_id'])
    raw=request(MASTER,'POST','/api/generate',{'prompt':p['legacy_prompt'],'tokens':24})
    (out/'master-sft-control.ndjson').write_bytes(raw);verify(raw,p['legacy_reference'])
    previous=status(MASTER);upload(MASTER,'model',NEO);write(out/'master-model-ready.json',ready(MASTER,p['new_model_id'],previous['boot_id']))
    rows=[]
    for identity in ['Q3','C2','S1']:
        case=next(c for c in p['cases'] if c['id']==identity)
        raw=request(MASTER,'POST','/api/generate',{'prompt':prompt(case),'tokens':case['limit']})
        (out/('master-'+identity+'.ndjson')).write_bytes(raw);rows.append({'case':identity,**verify(raw,refs[identity])})
        print('Master',identity,'matched',flush=True)
    write(out/'master-direct.json',rows)
    client.request('POST','/api/cluster',{'peer':PEER})
    write(out/'master-stage-passed.json',{'devices':{h:status(h) for h in [MASTER,PEER]},'cluster':idle(client)})
    print('Master stage passed; matching two-board pair configured',flush=True)


def benchmark(out,p,refs):
    if not (out/'master-stage-passed.json').exists():raise RuntimeError('Two-board gate not passed')
    client=Dispatcher(MASTER);idle(client);runs=[]
    try:
        for block in range(1,p['benchmark_blocks']+1):
            for mode in (['local','cluster'] if block%2 else ['cluster','local']):
                client.request('POST','/api/cluster',{'peer':PEER if mode=='cluster' else ''})
                cases=[next(c for c in p['cases'] if c['id']==i) for i in p['benchmark_cases']]
                ids=[client.submit(prompt(c),p['benchmark_cap'])['id'] for c in cases]
                jobs=client.wait(ids);write(out/f'block-{block}-{mode}.json',jobs)
                for case,job in zip(cases,jobs):
                    if job['state']!='done':raise RuntimeError('Dispatched job failed')
                    verify(job['raw_ndjson'].encode(),refs[case['id']])
                targets={j['target'] for j in jobs}
                if targets!=({'local',PEER} if mode=='cluster' else {'local'}):raise RuntimeError(('Unexpected lanes',targets))
                elapsed=max(j['finished_ms'] for j in jobs)-min(j['created_ms'] for j in jobs)
                runs.append({'block':block,'mode':mode,'elapsed_ms':elapsed,'output_tokens':sum(json.loads(j['raw_ndjson'].splitlines()[-1])['output_tokens'] for j in jobs),'targets':sorted(targets)})
                write(out/'batches.json',runs);print('Block',block,mode,elapsed,'ms matched',flush=True)
    finally:
        if not idle(client)['running']:client.request('POST','/api/cluster',{'peer':PEER})
    local=[r['elapsed_ms'] for r in runs if r['mode']=='local'];parallel=[r['elapsed_ms'] for r in runs if r['mode']=='cluster']
    summary={'blocks':p['benchmark_blocks'],'jobs':len(runs)*2,'same_tokens_and_EOS_all_jobs':True,
             'local_pair_median_ms':statistics.median(local),'cluster_pair_median_ms':statistics.median(parallel),
             'paired_throughput_factor_median':statistics.median(a/b for a,b in zip(local,parallel)),
             'interpretation':'Two independent requests, identical actual output lengths per mode; not acceleration of one autoregressive chain'}
    write(out/'summary.json',summary)
    final={'devices':{h:ready(h,p['new_model_id']) for h in [MASTER,PEER]},'cluster':idle(client)}
    write(out/'final-state.json',final);print(json.dumps(summary),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=['prepare','peer','master','benchmark']);parser.add_argument('output',type=pathlib.Path)
    args=parser.parse_args();out=args.output.resolve()
    if args.stage=='prepare':prepare(out)
    else:
        p,refs=load(out)
        try:{'peer':peer_stage,'master':master_stage,'benchmark':benchmark}[args.stage](out,p,refs)
        except BaseException as e:
            write(out/('error-'+args.stage+'.json'),{'stage':args.stage,'error':str(e),'time_utc':time.time()})
            raise
