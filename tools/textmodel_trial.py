"""Local reference, direct P4 and master-dispatched trial for two text models."""
import argparse
import ctypes as C
import hashlib
import http.client
import json
import pathlib
import struct
import time
from benchmark_kernel import request
from dispatch_client import Dispatcher
from lan_client import ROOT

PROMPTS=['Write a story about: a little girl and her dog\nWith: happy ending\n\n### Story:\n',
         'Write a story about: a boy who lost his favorite toy\nWith: sad ending\n\n### Story:\n']

def native(model,prompt,limit):
    data=model.read_bytes();blob=C.create_string_buffer(data);dims=struct.unpack_from('<7I',data,8)
    lib=C.CDLL(str(ROOT/'.local/build/tinyllm.dll'))
    lib.ts_open.argtypes=[C.c_void_p,C.c_size_t];lib.ts_open.restype=C.c_void_p
    for name in ['ts_close','ts_reset','ts_argmax']:getattr(lib,name).argtypes=[C.c_void_p]
    lib.ts_embed.argtypes=[C.c_void_p,C.c_int];lib.ts_layers.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int]
    lib.ts_encode.argtypes=[C.c_void_p,C.c_char_p,C.POINTER(C.c_int),C.c_int]
    lib.ts_finish.argtypes=[C.c_void_p];lib.ts_finish.restype=C.POINTER(C.c_float)
    lib.ts_decode.argtypes=[C.c_void_p,C.c_int,C.c_int];lib.ts_decode.restype=C.c_char_p
    state=lib.ts_open(blob,len(data));assert state
    try:
        buf=(C.c_int*2048)();count=lib.ts_encode(state,prompt.encode(),buf,len(buf))
        assert 0<count and count+limit-1<=dims[6]
        lib.ts_reset(state);token=buf[0];ids=[];pieces=[]
        for pos in range(count+limit-1):
            assert lib.ts_embed(state,token)==0 and lib.ts_layers(state,0,dims[2],pos)==0
            if pos<count-1:token=buf[pos+1];continue
            lib.ts_finish(state);nxt=lib.ts_argmax(state)
            if nxt in [1,2]:break
            ids.append(nxt);pieces.append(lib.ts_decode(state,token,nxt));token=nxt
        return {'tokens':ids,'text':b''.join(pieces).decode('utf-8','replace'),'prompt_tokens':count}
    finally:lib.ts_close(state)

def upload(host,path):
    # Host is validated by both callers before this local-only update path.
    from lan_client import lan_address
    c=http.client.HTTPConnection(lan_address(host),timeout=180)
    try:
        c.request('POST','/api/model',path.read_bytes(),{'X-Cluster-Key':(ROOT/'.local/lan-key.txt').read_text().strip(),'Content-Type':'application/octet-stream'})
        r=c.getresponse();raw=r.read();assert r.status==200,(r.status,raw[:200])
    finally:c.close()

def parse(raw):
    if isinstance(raw,str):raw=raw.encode()
    lines=[json.loads(x) for x in raw.splitlines()];done=lines[-1]
    assert done.get('done') and not done.get('error')
    ids=[x['token'] for x in lines if 'token' in x]
    assert done['output_tokens']==len(ids)
    return ids,done

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=pathlib.Path)
    p.add_argument('--master',default='10.0.0.121');p.add_argument('--peer',default='10.0.0.131')
    p.add_argument('--sft',type=pathlib.Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    baseline=ROOT/'.local/models/stories15M.p4lm';models={'baseline':baseline,'sft':a.sft}
    metadata={label:{'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                     'model_id':path.read_bytes()[48:80].hex()} for label,path in models.items()}
    (a.output/'protocol.json').write_text(json.dumps({'models':metadata,'prompts':PROMPTS,'direct_rounds':2,'cluster_rounds':2,
        'timing_tokens':24,'qualitative_tokens':96,'sampler':'greedy','order':['baseline','sft'],
        'script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n',encoding='utf-8')
    references={label:[native(path,prompt,96) for prompt in PROMPTS] for label,path in models.items()}
    (a.output/'host-references.json').write_text(json.dumps(references,indent=2)+'\n',encoding='utf-8')
    print('Both local references prepared; budget fits unchanged runtime',flush=True)
    client=Dispatcher(a.master);state=client.request('GET','/api/cluster')
    assert not state['queued'] and not state['running'] and state['peer']==a.peer
    results=[];changed=False
    try:
        for label,path in models.items():
            if label=='sft':
                client.request('POST','/api/cluster',{'peer':''})
                changed=True;upload(a.peer,path)
            for host in ([a.peer] if label=='sft' else [a.master,a.peer]):
                status=json.loads(request(host,'GET','/api/status'))
                assert status['model_id']==metadata[label]['model_id'] and status['model_ready']
            for round_no in range(2):
                for index,prompt in enumerate(PROMPTS):
                    raw=request(a.peer,'POST','/api/generate',{'prompt':prompt,'tokens':24})
                    (a.output/f'{label}-direct-{round_no}-{index}.ndjson').write_bytes(raw)
                    ids,done=parse(raw);assert ids==references[label][index]['tokens'][:24]
                    results.append({'model':label,'mode':'direct','round':round_no,'prompt_index':index,**done})
            for index,prompt in enumerate(PROMPTS):
                raw=request(a.peer,'POST','/api/generate',{'prompt':prompt,'tokens':96})
                (a.output/f'{label}-quality-{index}.ndjson').write_bytes(raw)
                ids,done=parse(raw);assert ids==references[label][index]['tokens']
                results.append({'model':label,'mode':'quality','prompt_index':index,**done})
            if label=='sft':
                upload(a.master,path)
                client.request('POST','/api/cluster',{'peer':a.peer})
            for round_no in range(2):
                ids=[client.submit(prompt,24)['id'] for prompt in PROMPTS]
                jobs=client.wait(ids);(a.output/f'{label}-cluster-{round_no}.json').write_text(json.dumps(jobs,indent=2)+'\n',encoding='utf-8')
                assert {j['target'] for j in jobs}=={'local',a.peer}
                for index,job in enumerate(jobs):
                    assert job['state']=='done';sequence,done=parse(job['raw_ndjson'])
                    assert sequence==references[label][index]['tokens'][:24]
                elapsed=max(j['finished_ms'] for j in jobs)-min(j['created_ms'] for j in jobs)
                results.append({'model':label,'mode':'cluster','round':round_no,'packet_ms':elapsed})
            (a.output/'results.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
            print(label,'direct, longer text and both-board cluster checks passed',flush=True)
    except BaseException:
        if changed:
            # Original artifact was retained; restore both model and dispatcher identity.
            upload(a.peer,baseline);upload(a.master,baseline);client.request('POST','/api/cluster',{'peer':a.peer})
        raise
    statuses={host:json.loads(request(host,'GET','/api/status')) for host in [a.master,a.peer]}
    for s in statuses.values():assert s['model_id']==metadata['sft']['model_id'] and s['model_ready'] and not s['ota_pending']
    (a.output/'final-state.json').write_text(json.dumps({'devices':statuses,'cluster':client.request('GET','/api/cluster')},indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
