"""Frozen same-firmware two-model experiment. Private LAN only; no downloads."""
import argparse
import datetime
import hashlib
import json
import pathlib
import subprocess
import time
from gptneo_p4_trial import MASTER,PEER,status,upload,idle,verify,Dispatcher
from benchmark_kernel import request
from check_gptneo_native import Native
from tinybrainbot_p4_trial import sanitized
from p4_compare_metrics import paired_summary

ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/'data/matched-p4-2026-10-30'
LOCAL=ROOT/'.local/matched-p4-2026-10-30'
MODELS={'tinybrainbot':(ROOT/'.local/tinybrainbot-p4-2026-10-29','tinybrainbot'),
        'supra':(ROOT/'.local/models/supra100-2c90ade6ab47','supra')}
CASES=[
    {'id':'F01','category':'facts','user':'How many sides does a triangle have? Answer briefly.','expected':'three / 3'},
    {'id':'F02','category':'facts','user':'How many days are in a week? Answer briefly.','expected':'seven / 7'},
    {'id':'F03','category':'facts','user':'What is the capital of France? Answer briefly.','expected':'Paris'},
    {'id':'F04','category':'facts','user':'In the four-season cycle, which season comes after summer? Answer briefly.','expected':'autumn / fall'},
    {'id':'F05','category':'facts','user':'What do we call frozen water? Answer briefly.','expected':'ice'},
    {'id':'F06','category':'facts','user':'Which sense do we mainly use with our ears? Answer briefly.','expected':'hearing'},
    {'id':'I01','category':'exact','user':'Reply with exactly this lowercase word and nothing else: marble','expected':'marble'},
    {'id':'I02','category':'exact','user':'Reply with exactly these two lowercase words and nothing else: quiet river','expected':'quiet river'},
    {'id':'G01','category':'grounded','user':"Nora put the ticket in a red box. Where is Nora's ticket? Answer briefly.",'expected':'in the red box'},
    {'id':'G02','category':'grounded','user':'Max has three pencils and gives one to Jo. How many pencils does Max have left? Answer briefly.','expected':'two / 2'},
    {'id':'S01','category':'story','user':'Write a short story about a duck helping a lost frog return to its pond.','topic':'duck; lost frog; help returning to pond'},
    {'id':'S02','category':'story','user':'Write a short story about a child who repairs a torn paper boat, then floats it on a pond.','topic':'child; torn paper boat; repair; floating on pond'}]
BENCH=[{'id':'B1','prompt':'Once upon a time','limit':16},{'id':'B2','prompt':'One day, a little girl','limit':16}]
SOURCES=['tools/compare_p4_models.py','tools/p4_compare_metrics.py','tools/check_gptneo_native.py',
         'tools/gptneo_p4_trial.py','tools/benchmark_kernel.py','tools/dispatch_client.py','tools/lan_client.py','tools/tinybrainbot_p4_trial.py',
         'firmware/components/tinyllm/tinyllm.c','firmware/components/tinyllm/sp_tokenizer.c','firmware/main/service.c']


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,obj):p.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')
def sources():return {n:sha(ROOT/n) for n in SOURCES}
def prompt(model,user):
    return ' <|user|> '+user+' <|end|> <|assistant|>' if model=='tinybrainbot' else '<|im_start|>user\n'+user+'<|im_end|>\n<|im_start|>assistant\n'


def prepare():
    if DATA.exists() or LOCAL.exists():raise ValueError('Choose fresh output and private directories')
    DATA.mkdir(parents=True,exist_ok=False);LOCAL.mkdir(parents=True,exist_ok=False)
    art={}
    for model,(folder,stem) in MODELS.items():
        roles={}
        for role in ['full','coordinator','worker']:
            p=folder/(stem+'-'+role+'.p4qs');raw=p.read_bytes()
            r={'path':p.relative_to(ROOT).as_posix(),'bytes':len(raw),'sha256':sha(p),'model_id':raw[128:160].hex(),'artifact_id':raw[48:80].hex()}
            if role!='full':
                z=p.with_suffix('.p4zl');r.update(stored_path=z.relative_to(ROOT).as_posix(),stored_bytes=z.stat().st_size,stored_sha256=sha(z))
                assert z.stat().st_size<=24*1024**2
            roles[role]=r
        assert len({r['model_id'] for r in roles.values()})==1
        art[model]=roles
    # Genuine prior deployment hashes, not just plausible filenames/headers.
    tiny=read(ROOT/'data/tinybrainbot-p4-2026-10-29/model-artifacts.json')
    supra=read(ROOT/'.local/models/supra100-2c90ade6ab47/pack-report.json')
    for model,prior in [('tinybrainbot',tiny),('supra',supra)]:
        for role in ['full','coordinator','worker']:
            assert art[model][role]['sha256']==prior[role]['sha256']
    for case in CASES:case['limit']=48 if case['category']=='story' else 24
    # Encoding is allowed before answers: pin actual wrapper bytes and input IDs.
    inputs={}
    for model in MODELS:
        native=Native(ROOT/art[model]['full']['path'])
        try:
            inputs[model]={c['id']:{'prompt':prompt(model,c['user']),'tokens':native.encode(prompt(model,c['user']))} for c in CASES}
            for b in BENCH:inputs[model][b['id']]={'prompt':b['prompt'],'tokens':native.encode(b['prompt'])}
        finally:native.close()
    for model in inputs:
        for case in CASES:assert len(inputs[model][case['id']]['tokens'])+case['limit']-1<=256
    p={'date':'2026-10-30','base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),'firmware':'0.7.0','context':256,'kernel':'tile4','split':4,
       'model_sources':{'tinybrainbot':{'repository':'nkthebass/tinybrainbot-100m-v3-instruct','revision':'a8567bd7674f53b3fe5f42c8abaab35229a0e00e','parameters':100092672},
                        'supra':{'repository':'SupraLabs/Supra2-100M-Instruct','revision':'2c90ade6ab47b910f48d0157a3e4c421d6311ed5','parameters':100684032}},
       'quantization':'Existing symmetric row INT4; FP32 scales/norms/KV. No re-quantization.',
       'cases':CASES,'benchmarks':BENCH,'inputs':inputs,'artifacts':art,'source_sha256':sources(),
       'native_dll_sha256':sha(ROOT/'.local/build/tinyllm.dll'),
       'schedule':[{'model':'tinybrainbot','quality':True,'blocks':[1]}, {'model':'supra','quality':True,'blocks':[1,2]},
                   {'model':'tinybrainbot','quality':False,'blocks':[2,3]}, {'model':'supra','quality':False,'blocks':[3]}],
       'timing_order':'AB/BA/AB across paired blocks; prefixes B1/B2 except B2/B1 in block2; warm B1 cap4 each phase.',
       'rubric':{'first':'First responsive factual claim correct; unrelated introductory statements do not count as the requested answer.',
                 'clean':'Entire visible response has no false claim, material contradiction or material task drift; null if capped evidence is ambiguous.',
                 'exact':'Strip outer Unicode whitespace only, then exact case-sensitive equality; no punctuation or extra text.',
                 'story':'Full stated topic, no material contradiction, visible resolution each binary and separate; EOS is not a resolution.',
                 'review':'Same assistant, unblinded, not independent. No pooled total quality score or population ranking.'},
       'speed_admission':'Paired latency ratio only if all six outputs for a prefix reach16 without EOS. Same bytes/cap do not equal same tokenizer IDs, output content or arithmetic.',
       'decode_proxy':'(output_tokens-1)*1000/(elapsed_ms-ttft_ms), only non-EOS capped outputs; includes final RPC/stream bookkeeping.',
       'boundaries':'Small exploratory fixed sample, familiar facts, possible training overlap; no energy/thermal/third-node measurements. No automatic inference retries.',
       'restore':'Genuine TinyBrainBot roles, control B1 cap4, final sharded ready/idle. Restore in finally on any failure. No firmware/partition change.'}
    write(DATA/'protocol.json',p);(DATA/'protocol.sha256').write_text(sha(DATA/'protocol.json')+'\n')
    print('Protocol prepared; no generations. Commit it before host or device stage.',flush=True)


def frozen():
    p=read(DATA/'protocol.json');assert sha(DATA/'protocol.json')==(DATA/'protocol.sha256').read_text().strip()
    assert p['source_sha256']==sources() and p['native_dll_sha256']==sha(ROOT/'.local/build/tinyllm.dll')
    relative=(DATA/'protocol.json').relative_to(ROOT).as_posix()
    freeze_commit=subprocess.check_output(['git','log','--format=%H','-1','--',relative],cwd=ROOT).decode().strip()
    assert freeze_commit and subprocess.check_output(['git','show',freeze_commit+':'+relative],cwd=ROOT)==(DATA/'protocol.json').read_bytes()
    for roles in p['artifacts'].values():
        for r in roles.values():
            assert sha(ROOT/r['path'])==r['sha256']
            if 'stored_path' in r:assert sha(ROOT/r['stored_path'])==r['stored_sha256']
    return p,freeze_commit


def host():
    p,commit=frozen();assert not (DATA/'host-references.json').exists();refs={}
    for model in MODELS:
        native=Native(ROOT/p['artifacts'][model]['full']['path']);refs[model]={}
        try:
            for case in p['cases']+p['benchmarks']:
                inp=p['inputs'][model][case['id']];assert native.encode(inp['prompt'])==inp['tokens']
                refs[model][case['id']]=native.generate(inp['prompt'],case['limit'])
                print('HOST',model,case['id'],len(refs[model][case['id']]['tokens']),flush=True)
            refs[model]['W']=native.generate(p['benchmarks'][0]['prompt'],4)
        finally:native.close()
    write(DATA/'host-references.json',refs);write(DATA/'host-receipt.json',{'protocol_commit':commit,'protocol_sha256':sha(DATA/'protocol.json'),
        'complete_generations':30,'references_sha256':sha(DATA/'host-references.json'),'source_sha256':sources(),'scope':'Native reference only; no answer quality scoring or hardware yet'})


def ready(host,model,role,p,old_boot=None):
    a=p['artifacts'][model][role];deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        try:
            s=status(host)
            if (s['firmware']=='0.7.0' and s['model_ready'] and s['model_id']==a['model_id'] and s['artifact_id']==a['artifact_id']
                and s['role']==(1 if role=='coordinator' else 2) and not s['worker_busy'] and not s['ota_pending'] and not s.get('restart_pending')
                and (old_boot is None or s['boot_id']!=old_boot)):
                assert s['context']==256 and s['default_kernel']=='tile4' and s['free_psram']>=512*1024
                return s
        except (OSError,RuntimeError,ValueError):pass
        time.sleep(2)
    raise RuntimeError('Readiness timeout for '+model+'/'+role)


def switch(model,p,label):
    idle(Dispatcher(MASTER));states={}
    for role,host in [('worker',PEER),('coordinator',MASTER)]:
        before=status(host);assert before['firmware']=='0.7.0' and not before['worker_busy'] and not before['ota_pending']
        a=p['artifacts'][model][role]
        if before['model_id']!=a['model_id'] or before['artifact_id']!=a['artifact_id']:
            print('LOAD',label,model,role,flush=True);upload(host,'model',ROOT/a['stored_path']);states[role]=ready(host,model,role,p,before['boot_id'])
        else:states[role]=ready(host,model,role,p)
    cluster=idle(Dispatcher(MASTER));assert cluster['mode']=='sharded' and cluster['active_lanes']==1 and cluster['peer']==PEER
    write(LOCAL/(label+'-states.json'),states);write(DATA/(label+'-states.json'),{r:sanitized(s) for r,s in states.items()})


def infer(model,case,label,p,refs,limit=None):
    cap=case['limit'] if limit is None else limit
    text=p['inputs'][model][case['id']]['prompt']
    print('START',label,'cap',cap,flush=True)
    raw=request(MASTER,'POST','/api/generate',{'prompt':text,'tokens':cap,'kernel':'tile4'},timeout=600)
    path=DATA/(label+'.ndjson');path.write_bytes(raw)  # Preserve before asserting.
    ref=refs[model]['W' if cap==4 else case['id']];done=verify(raw,ref)
    assert done['boards']==2 and done['kernel']['mode']=='tile4' and done['kernel']['owner_core_mask']==2 and done['kernel']['helper_core_mask']==1
    assert done['prompt_tokens']==len(ref['prompt_tokens']) and done['output_tokens']==len(ref['tokens'])
    print(label,'MATCH',done['output_tokens'],'tokens',round(done['elapsed_ms']/1000,3),'s',flush=True)
    return {'model':model,'case':case['id'],'file':path.name,'done':done,'tokens_text_eos_equal':True}


def device():
    p,commit=frozen();h=read(DATA/'host-receipt.json');assert h['protocol_commit']==commit and h['references_sha256']==sha(DATA/'host-references.json')
    assert not (DATA/'device-start.json').exists();refs=read(DATA/'host-references.json')
    idle(Dispatcher(MASTER));start={r:status(t) for r,t in [('coordinator',MASTER),('worker',PEER)]}
    for role,s in start.items():assert s['firmware']=='0.7.0' and s['model_ready'] and s['model_id']==p['artifacts']['tinybrainbot'][role]['model_id'] and not s['worker_busy']
    write(LOCAL/'initial.json',start);write(DATA/'device-start.json',{r:sanitized(s) for r,s in start.items()})
    quality=[];timing=[];controls=[];failure=None
    try:
        for phase,step in enumerate(p['schedule'],1):
            model=step['model'];label='phase'+str(phase);switch(model,p,label)
            if step['quality']:
                for case in p['cases']:
                    row=infer(model,case,model+'-'+case['id'],p,refs);quality.append(row);write(DATA/'quality-runs.json',quality)
            row=infer(model,p['benchmarks'][0],label+'-warmup',p,refs,4);controls.append(row);write(DATA/'controls.json',controls)
            for block in step['blocks']:
                cases=p['benchmarks'] if block!=2 else list(reversed(p['benchmarks']))
                for case in cases:
                    row=infer(model,case,f'{model}-block{block}-{case["id"]}',p,refs);row.update(block=block,phase=phase)
                    timing.append(row);write(DATA/'timing-runs.json',timing)
        write(DATA/'timing-summary.json',paired_summary(timing))
    except BaseException as e:
        failure=type(e).__name__+': '+str(e);write(DATA/'error.json',{'error':failure,'quality_completed':len(quality),'timing_completed':len(timing)});raise
    finally:
        try:
            switch('tinybrainbot',p,'restored');row=infer('tinybrainbot',p['benchmarks'][0],'restoration-control',p,refs,4)
            states={r:status(t) for r,t in [('coordinator',MASTER),('worker',PEER)]};cluster=idle(Dispatcher(MASTER))
            write(LOCAL/'final.json',states)
            write(DATA/'final.json',{'completed':failure is None,'failure':failure,'devices':{r:sanitized(s) for r,s in states.items()},
                'restoration_control':row,'queued':cluster['queued'],'running':cluster['running'],'mode':cluster['mode']})
            print('RESTORED TinyBrainBot; both ready/idle',flush=True)
        except BaseException as e:
            write(DATA/'restoration-error.json',{'error':type(e).__name__+': '+str(e)});raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=['prepare','host','device'])
    parser.add_argument('--output',type=pathlib.Path,default=DATA);parser.add_argument('--private',type=pathlib.Path,default=LOCAL)
    args=parser.parse_args();DATA=args.output.resolve();LOCAL=args.private.resolve();globals()[args.stage]()
