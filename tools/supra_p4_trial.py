"""Explicit staged local-LAN firmware/model trial. Never publishes evidence."""
import argparse
import hashlib
import json
import pathlib
import shutil
import time
from gptneo_p4_trial import MASTER,PEER,status,upload,idle,verify,Dispatcher,NEO
from benchmark_kernel import request
from check_gptneo_native import Native
from pack_supra import ROOT
from check_supra_native import write
VERSION='0.6.1'
PRIVATE=ROOT/'.local/supra-p4-2026-10-29'


def ready(host,model_id,artifact=None,old_boot=None):
    deadline=time.monotonic()+180;last=None
    while time.monotonic()<deadline:
        try:
            last=status(host)
            if (last.get('firmware')==VERSION and last.get('model_ready') and last.get('model_id')==model_id and
                not last.get('ota_pending') and not last.get('restart_pending') and
                (artifact is None or last.get('artifact_id')==artifact) and (old_boot is None or last['boot_id']!=old_boot)):
                return last
        except (OSError,RuntimeError,ValueError):pass
        time.sleep(2)
    raise RuntimeError(('Readiness timeout',host,last))


def firmware():
    PRIVATE.mkdir(parents=True,exist_ok=True);idle(Dispatcher(MASTER))
    states={h:status(h) for h in [MASTER,PEER]};write(PRIVATE/'before-firmware.json',states)
    identity=NEO.read_bytes()[48:80].hex()
    for x in states.values():assert x['model_id']==identity and x['model_ready'] and not x['worker_busy'] and not x['ota_pending']
    # Verify rollback files before touching either board.
    rollback=ROOT/'.local/gptneo-p4-2026-10-29/p4-0.5.5.bin'
    assert rollback.is_file() and NEO.is_file()
    image=PRIVATE/('p4-'+VERSION+'.bin');shutil.copyfile(ROOT/'.local/build/rev1/p4_tinystories.bin',image)
    n=Native(NEO)
    try:expected=n.generate('The color of a ripe banana is',8)
    finally:n.close()
    records=[]
    for name,host in [('worker',PEER),('coordinator',MASTER)]:
        before=status(host);upload(host,'firmware',image);after=ready(host,identity,old_boot=before['boot_id'])
        raw=request(host,'POST','/api/generate',{'prompt':'The color of a ripe banana is','tokens':8,'peer':''})
        done=verify(raw,expected);assert done['boards']==1
        records.append({'node':name,'status':after,'control':done});write(PRIVATE/'firmware-controls.json',records)
        print(name,'new firmware and legacy TinyTalk control passed',flush=True)


def models(directory,out):
    idle(Dispatcher(MASTER));report=json.loads((directory/'pack-report.json').read_text('utf-8'))
    assert (out/'host-report.json').is_file();records=[]
    for role,host in [('worker',PEER),('coordinator',MASTER)]:
        before=status(host);assert before['firmware']==VERSION and not before['worker_busy']
        raw=(directory/('supra-'+role+'.p4qs')).read_bytes();assert hashlib.sha256(raw).hexdigest()==report[role]['sha256']
        path=directory/('supra-'+role+'.p4zl')
        if path.exists():
            from supra_storage import unwrap
            assert unwrap(path.read_bytes())==raw
        else:path=directory/('supra-'+role+'.p4qs')
        assert path.stat().st_size<=24*1024*1024
        upload(host,'model',path)
        after=ready(host,report[role]['model_id'],report[role]['artifact_id'],before['boot_id'])
        assert after['role']==(2 if role=='worker' else 1) and after['quant_bits']==4
        records.append({'node':role,'status':after});write(PRIVATE/(directory.name+'-installation.json'),records)
        print(role,'shard ready',after['model_load_requested'],'bytes; free PSRAM',after['free_psram'],flush=True)
    client=Dispatcher(MASTER);configured=client.request('POST','/api/cluster',{'peer':PEER})
    assert configured['mode']=='sharded' and configured['active_lanes']==1
    write(PRIVATE/(directory.name+'-cluster.json'),configured)


def study(directory,out):
    client=Dispatcher(MASTER);cluster=idle(client);assert cluster['mode']=='sharded'
    protocol=json.loads((out/'protocol.json').read_text('utf-8'));refs={x['case']:x for x in json.loads((out/'host-generations.json').read_text('utf-8'))}
    hardware_cases=[c for c in protocol['cases'] if c['id'] in protocol.get('hardware_cases',[x['id'] for x in protocol['cases']])]
    rows=[]
    for case in hardware_cases:
        # No peer field: the coordinator must use its saved worker automatically.
        raw=request(MASTER,'POST','/api/generate',{'prompt':case['prompt'],'tokens':case['limit']},timeout=300)
        done=verify(raw,refs[case['id']]);assert done['boards']==2 and not done.get('error')
        (out/(case['id']+'-p4.ndjson')).write_bytes(raw)
        rows.append({'case':case['id'],'done':done,'host_tokens_text_eos_equal':True});write(out/'p4-runs.json',rows)
        print(case['id'],done['output_tokens'],round(done['elapsed_ms']/1000,3),'s',flush=True)
    dispatch_cases=[next(c for c in protocol['cases'] if c['id']==name) for name in protocol.get('dispatch_cases',['S1','S2'])]
    jobs=[client.submit(c['prompt'],c['limit'])['id'] for c in dispatch_cases]
    results=client.wait(jobs,timeout=600,poll=1)
    for result,case in zip(results,dispatch_cases):
        assert result['state']=='done';verify(result['raw_ndjson'].encode(),refs[case['id']])
    write(PRIVATE/(directory.name+'-dispatcher-pair.json'),results)
    write(out/'dispatcher-pair.json',[{k:x[k] for k in ['state','target','error','created_ms','started_ms','finished_ms','output_tokens','queue_ms','raw_ndjson']} for x in results])
    timing_case=next(c for c in protocol['cases'] if c['id']==protocol['timing_case'])
    n=Native(directory/'supra-full.p4qs')
    try:ref=n.generate(timing_case['prompt'],protocol['timing_limit'])
    finally:n.close()
    timings=[]
    for repeat in range(protocol['timing_repeats']):
        raw=request(MASTER,'POST','/api/generate',{'prompt':timing_case['prompt'],'tokens':protocol['timing_limit']},timeout=300)
        done=verify(raw,ref);timings.append(done);write(out/'timing.json',timings);print('timing',repeat+1,round(done['elapsed_ms']/1000,3),'s',flush=True)
    final={h:status(h) for h in [MASTER,PEER]};write(PRIVATE/(directory.name+'-after-study.json'),final)
    write(out/'device-memory.json',{role:{k:final[h].get(k) for k in ['firmware','architecture','model_ready','model_id','artifact_id','role','first_layer','end_layer','quant_bits','free_psram','largest_psram_block','free_internal','min_free_internal','model_load_requested','model_stored_bytes','worker_busy','ota_pending']} for role,h in [('coordinator',MASTER),('worker',PEER)]})


def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['firmware','models','study']);p.add_argument('--directory',type=pathlib.Path,default=ROOT/'.local/models/supra50-f0566e6be9f1');p.add_argument('--output',type=pathlib.Path,default=ROOT/'data/supra50-2026-10-29');a=p.parse_args()
    if a.stage=='firmware':firmware()
    elif a.stage=='models':models(a.directory,a.output)
    else:study(a.directory,a.output)


if __name__=='__main__':main()
