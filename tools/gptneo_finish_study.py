"""Freeze a documented continuation after the recorded 0.5.3 one-board gate.

Avoid repeating unchanged 14-case arithmetic/byte tests: validate identical
core sources, recheck representative cases, and test the revised LAN restart
path before touching the master. No public network is used.
"""
import argparse
import json
import pathlib
import shutil
from gptneo_p4_trial import (ROOT,WORK,VERSION,MASTER,PEER,SFT,NEO,sha,write,status,
                            idle,Dispatcher,upload,ready,verify,load,master_stage,benchmark)
from benchmark_kernel import request
from evaluate_tinytalk import prompt

PARENT=ROOT/'data/gptneo-p4-2026-10-29'


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    prior=PARENT/'final-study';p=json.loads((prior/'protocol.json').read_text(encoding='utf-8'))
    actual=json.loads((prior/'peer-results.json').read_text(encoding='utf-8'))
    if len(actual)!=14:raise RuntimeError('Earlier complete one-board numerical gate missing')
    host=json.loads((WORK/'native-check/report.json').read_text(encoding='utf-8'))
    for n,h in host['source_sha256'].items():
        if sha(ROOT/n)!=h:raise RuntimeError('Core/exporter/reference changed; cannot reuse prior gate')
    client=Dispatcher(MASTER);idle(client)
    states={h:status(h) for h in [MASTER,PEER]}
    if states[MASTER]['firmware']!='0.4.0' or states[MASTER]['model_id']!=p['old_model_id']:raise RuntimeError('Unexpected master')
    if states[PEER]['firmware']!='0.5.4' or states[PEER]['model_id']!=p['new_model_id'] or not states[PEER]['model_ready']:raise RuntimeError('Unexpected peer')
    fw=WORK/('p4-'+VERSION+'.bin');shutil.copyfile(ROOT/'.local/build/rev1/p4_tinystories.bin',fw)
    p.update({'firmware':VERSION,'script_sha256':sha(ROOT/'tools/gptneo_p4_trial.py'),
              'continuation_script_sha256':sha(pathlib.Path(__file__)),
              'prior_gate':'14 complete P4 generations on 0.5.3; unchanged portable core/exporter/reference hashes verified',
              'continuation_cases':['Q1','Q3','S1'],
              'restart_gate':'LAN OTA after a long story, then same-model LAN upload with automatic restart; new boot IDs and Q1 token checks',
              'amendment_reason':'Earlier same-image OTA did not regain LAN readiness; preserve failed evidence and test revised controlled restart separately',
              'artifacts_sha256':{str(x.relative_to(ROOT)).replace('\\','/'):sha(x) for x in [fw,NEO,SFT,WORK/'rollback/p4-0.4.0.bin']}})
    write(out/'protocol.json',p);(out/'protocol.sha256').write_text(sha(out/'protocol.json')+'\n',encoding='utf-8')
    shutil.copyfile(prior/'native-references.json',out/'native-references.json')
    write(out/'before.json',{'devices':states,'cluster':idle(client),'unchanged_core_checks':host})
    print('Continuation frozen; master unchanged and prior one-board gate verified',flush=True)


def peer(out,p,refs):
    client=Dispatcher(MASTER);idle(client)
    if client.request('GET','/api/cluster')['peer']:raise RuntimeError('Peer must remain disabled during first-board work')
    previous=status(PEER);upload(PEER,'firmware',WORK/('p4-'+VERSION+'.bin'))
    state=ready(PEER,p['new_model_id'],previous['boot_id']);write(out/'peer-firmware-ready.json',state)
    rows=[]
    for identity in p['continuation_cases']:
        case=next(c for c in p['cases'] if c['id']==identity)
        raw=request(PEER,'POST','/api/generate',{'prompt':prompt(case),'tokens':case['limit']})
        (out/('peer-'+identity+'.ndjson')).write_bytes(raw);rows.append({'case':identity,**verify(raw,refs[identity])})
        print('Peer final',identity,'matched',flush=True)
    write(out/'peer-direct.json',rows)
    print('Peer: testing LAN OTA after long inference, no serial connection',flush=True)
    old=status(PEER);upload(PEER,'firmware',WORK/('p4-'+VERSION+'.bin'))
    state=ready(PEER,p['new_model_id'],old['boot_id']);write(out/'peer-after-OTA.json',state)
    print('Peer: testing same-model LAN upload and automatic cold restart',flush=True)
    old=status(PEER);upload(PEER,'model',NEO)
    state=ready(PEER,p['new_model_id'],old['boot_id']);write(out/'peer-after-model-restart.json',state)
    case=next(c for c in p['cases'] if c['id']=='Q1')
    raw=request(PEER,'POST','/api/generate',{'prompt':prompt(case),'tokens':32})
    (out/'peer-after-model-restart.ndjson').write_bytes(raw);verify(raw,refs['Q1'])
    write(out/'peer-stage-passed.json',{'state':state,'prior_complete_generations':14,
                                     'final_firmware_cases':3,'LAN_OTA_after_long_inference':True,
                                     'LAN_model_upload_automatic_restart':True,'serial_intervention_in_this_stage':False})
    print('Final peer gate passed',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=['prepare','peer','master','benchmark']);parser.add_argument('output',type=pathlib.Path)
    args=parser.parse_args();out=args.output.resolve()
    if args.stage=='prepare':prepare(out)
    else:
        p,refs=load(out)
        if sha(pathlib.Path(__file__))!=p['continuation_script_sha256']:raise RuntimeError('Continuation script changed')
        try:{'peer':peer,'master':master_stage,'benchmark':benchmark}[args.stage](out,p,refs)
        except BaseException as e:
            write(out/('error-'+args.stage+'.json'),{'stage':args.stage,'error':str(e)})
            raise
