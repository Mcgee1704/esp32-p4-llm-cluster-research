"""Explicit staged private-LAN acceptance; never publishes or downloads."""
import argparse
import http.client
import shutil
import time
from tinybrainbot_port import OUT,PRIVATE,PRIOR,sources
from tinybrainbot_study import ROOT,read,write,sha,freeze
from gptneo_p4_trial import MASTER,PEER,status,upload,idle,verify,Dispatcher
from benchmark_kernel import request
from check_gptneo_native import Native

VERSION='0.7.0'
OLD_ID='1e84bed3091324dca22294f002d6babbc7ca5db8728dac58a5e241bc4ef5008c'
ROLLBACK=ROOT/'.local/supra-p4-2026-10-29/p4-0.6.1.bin'
OLD_MODELS=ROOT/'.local/models/supra100-2c90ade6ab47'


def ready(host,identity,artifact=None,boot=None):
    deadline=time.monotonic()+180;last=None
    while time.monotonic()<deadline:
        try:
            last=status(host)
            if (last['firmware']==VERSION and last['model_ready'] and last['model_id']==identity and not last['ota_pending'] and not last.get('restart_pending')
                and (artifact is None or last['artifact_id']==artifact) and (boot is None or last['boot_id']!=boot)):
                return last
        except (OSError,RuntimeError,ValueError):pass
        time.sleep(2)
    raise RuntimeError(('Readiness timeout',host,last))


def sanitized(x):
    keys=['firmware','architecture','tokenizer','model_ready','model_id','artifact_id','role','first_layer','end_layer','quant_bits','context',
          'free_psram','min_free_psram','largest_psram_block','free_internal','min_free_internal','model_load_requested','model_stored_bytes','worker_busy','ota_pending']
    return {k:x.get(k) for k in keys}


def prepare():
    host=read(OUT/'host-report.json');p=read(OUT/'protocol.json');assert host['complete_generations']==30 and host['all_tokens_text_eos_equal'] and host['code_sha256']==sources()
    assert sha(ROLLBACK)=='f7cc70a2c71631b415d870004a26e3e86134855abd85e491a1f708ba693c1c9d'
    for role in ['coordinator','worker']:
        for ext in ['p4qs','p4zl']:assert (OLD_MODELS/('supra-'+role+'.'+ext)).is_file()
    cluster=idle(Dispatcher(MASTER));assert cluster['mode']=='sharded'
    states={r:status(h) for r,h in [('coordinator',MASTER),('worker',PEER)]}
    for i,(r,s) in enumerate(states.items()):
        assert s['firmware']=='0.6.1' and s['model_id']==OLD_ID and s['role']==i+1 and s['model_ready'] and not s['worker_busy'] and not s['ota_pending']
    image=PRIVATE/('p4-'+VERSION+'.bin');shutil.copyfile(ROOT/'.local/build/rev1/p4_tinystories.bin',image)
    # The C fixture files are deliberately excluded; only genuine-role filenames.
    for role in ['coordinator','worker']:
        assert sha(PRIVATE/('tinybrainbot-'+role+'.p4zl'))==p['artifacts'][role]['compressed_sha256']
    control_prompt=next(c for c in read(PRIOR/'protocol.json')['cases'] if c['id']=='T13')['formats']['supra']['text']
    native=Native(OLD_MODELS/'supra-full.p4qs')
    try:control=native.generate(control_prompt,8)
    finally:native.close()
    trial={'firmware':VERSION,'firmware_bytes':image.stat().st_size,'firmware_sha256':sha(image),'rollback_sha256':sha(ROLLBACK),
           'old_model_id':OLD_ID,'new_model_id':p['artifacts']['coordinator']['model_id'],'old_control_prompt':control_prompt,'old_control':control,
           'host_report_sha256':sha(OUT/'host-report.json'),'artifact_report_sha256':sha(OUT/'model-artifacts.json'),'trial_script_sha256':sha(ROOT/'tools/tinybrainbot_p4_trial.py'),
           'steps':'Worker OTA with Supra; distributed old control; master OTA with Supra/control; worker then master genuine Tiny model; device cases/queue/timing/Unicode; long-input rejection; master same-image OTA/control.',
           'long_input_case':{'id':'L01','prompt':'a'*1024,'tokens':1,'expected_http':400,'reason':'258 input tokens exceed context256; encoder temporary allocation exercised before rejection'},
           'device_sequence':p['hardware_cases'],'generation_cap':16,'timing_comparison':'None. Fixed T13 request, actual EOS lengths reported; no speedup baseline.'}
    freeze(OUT/'installation-protocol.json',trial);write(PRIVATE/'before-firmware.json',{'devices':states,'cluster':cluster})
    write(OUT/'before.json',{'devices':{r:sanitized(s) for r,s in states.items()},'cluster_mode':cluster['mode'],'queued':0,'running':0})
    print('Exact targets, idle state, native gate, real artifacts and rollback verified. Image',image.stat().st_size,'bytes',flush=True)


def load():
    p=read(OUT/'installation-protocol.json')
    assert p['trial_script_sha256']==sha(ROOT/'tools/tinybrainbot_p4_trial.py')
    assert p['firmware_sha256']==sha(PRIVATE/('p4-'+VERSION+'.bin')) and p['host_report_sha256']==sha(OUT/'host-report.json')
    return p


def firmware():
    p=load();idle(Dispatcher(MASTER));records=[]
    for role,host in [('worker',PEER),('coordinator',MASTER)]:
        before=status(host);assert before['firmware']=='0.6.1' and before['model_id']==OLD_ID and not before['worker_busy']
        print(role,'uploading0.7.0; retaining real Supra shard',flush=True);upload(host,'firmware',PRIVATE/('p4-'+VERSION+'.bin'))
        after=ready(host,OLD_ID,before['artifact_id'],before['boot_id']);write(PRIVATE/(role+'-firmware-ready.json'),after)
        raw=request(MASTER,'POST','/api/generate',{'prompt':p['old_control_prompt'],'tokens':8},timeout=300)
        done=verify(raw,p['old_control']);assert done['boards']==2
        (OUT/('supra-control-after-'+role+'-ota.ndjson')).write_bytes(raw)
        records.append({'updated':role,'state':sanitized(after),'old_two_board_control_equal':True,'control':done});write(OUT/'firmware-controls.json',records)
        print(role,'firmware ready; old distributed token/byte/EOS control passed',flush=True)


def models():
    p=load();idle(Dispatcher(MASTER));art=read(OUT/'model-artifacts.json');records=[]
    for role,host in [('worker',PEER),('coordinator',MASTER)]:
        before=status(host);assert before['firmware']==VERSION and before['model_id']==OLD_ID and not before['worker_busy']
        path=PRIVATE/('tinybrainbot-'+role+'.p4zl');assert sha(path)==art[role]['compressed_sha256'] and path.stat().st_size<=24*1024**2
        print(role,'uploading genuine TinyBrainBot',path.stat().st_size,'bytes',flush=True);upload(host,'model',path)
        after=ready(host,p['new_model_id'],art[role]['artifact_id'],before['boot_id'])
        assert after['role']==(2 if role=='worker' else 1) and after['free_psram']>=512*1024 and after['context']==256
        assert after['tokenizer']==('none' if role=='worker' else 'metaspace_bpe')
        write(PRIVATE/(role+'-model-ready.json'),after);records.append({'role':role,'state':sanitized(after)});write(OUT/'installation.json',records)
        print(role,'cold-loaded; free PSRAM',after['free_psram'],'low-water',after['min_free_psram'],flush=True)
    cluster=Dispatcher(MASTER).request('POST','/api/cluster',{'peer':PEER});assert cluster['mode']=='sharded' and cluster['active_lanes']==1


def study():
    load();p=read(OUT/'protocol.json');refs=read(OUT/'hardware-references.json');idle(Dispatcher(MASTER));rows=[]
    for name in p['hardware_cases']:
        case=next(c for c in p['cases'] if c['id']==name)
        raw=request(MASTER,'POST','/api/generate',{'prompt':case['prompt'],'tokens':16},timeout=300);done=verify(raw,refs[name]);assert done['boards']==2
        (OUT/(name+'-p4.ndjson')).write_bytes(raw);rows.append({'case':name,'tokens_text_eos_equal':True,'done':done});write(OUT/'p4-runs.json',rows)
        print(name,'matched',done['output_tokens'],'tokens,',round(done['elapsed_ms']/1000,3),'s',flush=True)
    client=Dispatcher(MASTER);jobs=[]
    for name in p['dispatch_cases']:
        case=next(c for c in p['cases'] if c['id']==name);jobs.append(client.submit(case['prompt'],16)['id'])
    results=client.wait(jobs,timeout=600,poll=1)
    for result,name in zip(results,p['dispatch_cases']):assert result['state']=='done';verify(result['raw_ndjson'].encode(),refs[name])
    write(PRIVATE/'dispatcher-full.json',results)
    write(OUT/'dispatcher-pair.json',[{k:r[k] for k in ['state','error','queue_ms','created_ms','started_ms','finished_ms','output_tokens','raw_ndjson']} for r in results]);print('Dispatcher pair matched, one sequential distributed lane',flush=True)
    case=next(c for c in p['cases'] if c['id']==p['timing_case']);timings=[]
    for i in range(3):
        raw=request(MASTER,'POST','/api/generate',{'prompt':case['prompt'],'tokens':16},timeout=300);done=verify(raw,refs[case['id']]);timings.append(done);write(OUT/'timing.json',timings)
        print('T13 timing',i+1,round(done['elapsed_ms']/1000,3),'s, output tokens',done['output_tokens'],flush=True)
    raw=request(MASTER,'POST','/api/generate',{'prompt':p['unicode_prompt'],'tokens':16},timeout=300);done=verify(raw,refs['U01']);(OUT/'U01-p4.ndjson').write_bytes(raw);write(OUT/'unicode-control.json',done)
    print('Unicode normalization control matched',flush=True)
    private_states={r:status(h) for r,h in [('coordinator',MASTER),('worker',PEER)]};write(PRIVATE/'after-study.json',private_states)
    write(OUT/'device-memory-before-ota.json',{r:sanitized(s) for r,s in private_states.items()})


def ota():
    trial=load();p=read(OUT/'protocol.json');refs=read(OUT/'hardware-references.json');client=Dispatcher(MASTER);idle(client)
    before=status(MASTER)
    try:request(MASTER,'POST','/api/generate',{'prompt':trial['long_input_case']['prompt'],'tokens':1},timeout=120)
    except RuntimeError as e:
        assert '400' in str(e) and 'Prompt plus output exceeds model context' in str(e)
    else:raise AssertionError('Oversized-context test unexpectedly generated')
    after=status(MASTER);assert before['model_id']==after['model_id'] and before['boot_id']==after['boot_id'] and not after['worker_busy']
    write(OUT/'long-input-rejection.json',{'http':400,'input_bytes':1024,'input_token_count':258,'boot_and_model_unchanged':True,'after':sanitized(after)})
    write(PRIVATE/'before-same-image-ota.json',after);print('Long-word encoder rejected context overflow; ready state preserved',flush=True)
    upload(MASTER,'firmware',PRIVATE/('p4-'+VERSION+'.bin'));fresh=ready(MASTER,trial['new_model_id'],after['artifact_id'],after['boot_id'])
    case=next(c for c in p['cases'] if c['id']=='T13');raw=request(MASTER,'POST','/api/generate',{'prompt':case['prompt'],'tokens':16},timeout=300)
    done=verify(raw,refs['T13']);assert done['boards']==2;(OUT/'same-image-ota-control.ndjson').write_bytes(raw)
    states={r:status(h) for r,h in [('coordinator',MASTER),('worker',PEER)]};write(PRIVATE/'final.json',states);cluster=idle(client)
    for s in states.values():assert s['firmware']==VERSION and s['model_id']==trial['new_model_id'] and s['model_ready'] and not s['worker_busy'] and not s['ota_pending'] and s['free_psram']>=512*1024
    write(OUT/'final.json',{'devices':{r:sanitized(s) for r,s in states.items()},'same_image_ota_control_equal':True,'coordinator_boot_changed':fresh['boot_id']!=after['boot_id'],'cluster_mode':cluster['mode'],'queued':cluster['queued'],'running':cluster['running']})
    print('Same-image LAN OTA + cold load passed; both real nodes ready and idle',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','firmware','models','study','ota']);a=parser.parse_args();globals()[a.stage]()
