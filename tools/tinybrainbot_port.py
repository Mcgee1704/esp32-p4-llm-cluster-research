"""Real-tokenizer export, differential probes and full native acceptance.

No downloads, board writes or modification of earlier answer/protocol evidence.
"""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import argparse
import ctypes as C
import json
import random
import struct
import time
from tinybrainbot_study import ROOT,CANDIDATE,load_candidate,read,write,sha,freeze,prompt,tokenizers,Reference,row_int4
from pack_spm import pack_model,pack_tokenizer
from supra_storage import wrap,unwrap
from check_gptneo_native import Native

OUT=ROOT/'data/tinybrainbot-p4-2026-10-29'
PRIVATE=ROOT/'.local/tinybrainbot-p4-2026-10-29'
PRIOR=ROOT/'data/tinybrainbot-local-2026-10-29'


def sources():
    names=['tools/pack_spm.py','tools/tinybrainbot_port.py','tools/data/unicode-grapheme-16.json','firmware/components/tinyllm/sp_tokenizer.c',
           'firmware/components/tinyllm/tinyllm.c','firmware/main/service.c']
    return {n:sha(ROOT/n) for n in names}


def prepare():
    OUT.mkdir(exist_ok=False);PRIVATE.mkdir(exist_ok=True);c,t=load_candidate();artifacts=pack_model(c,t,CANDIDATE/'tokenizer.json');report={}
    for role,raw in artifacts.items():
        path=PRIVATE/('tinybrainbot-'+role+'.p4qs');path.write_bytes(raw)
        item={'bytes':len(raw),'sha256':sha(path),'artifact_id':raw[48:80].hex(),'model_id':raw[128:160].hex(),
              'weights_bytes':struct.unpack_from('<I',raw,36)[0],'tokenizer_bytes':struct.unpack_from('<I',raw,40)[0]}
        if role!='full':
            zipped=wrap(raw);assert unwrap(zipped)==raw and len(zipped)<=24*1024**2
            zpath=path.with_suffix('.p4zl');zpath.write_bytes(zipped);item.update(compressed_bytes=len(zipped),compressed_sha256=sha(zpath))
        report[role]=item
    write(OUT/'model-artifacts.json',report)
    prior=read(PRIOR/'protocol.json');cases=[]
    for case in prior['cases']:
        cases.append({'id':case['id'],'prompt':case['formats']['tinybrainbot']['text'],'tokens':case['formats']['tinybrainbot']['tokens'],'limit':48})
    unicode_prompt=prompt('tinybrainbot','\uff37hat is the capital of Germany? Answer briefly.')
    protocol={'source_revision':prior['candidate']['revision'],'source_sha256':prior['candidate']['weight_sha256'],'firmware':'0.7.0','context':256,'split':4,
        'cases':cases,'hardware_cases':['T03','T06','T13','A01','G02','K01'],'hardware_cap':16,'dispatch_cases':['T04','T09'],
        'timing_case':'T13','timing_cap':16,'timing_repeats':3,'unicode_prompt':unicode_prompt,
        'unicode_tokens':tokenizers()['tinybrainbot'].encode(unicode_prompt,add_special_tokens=False).ids,
        'tokenizer':'SPBP0001 BPE/Metaspace; exact pinned tokenizers0.22.1 semantics; no byte fallback; fuse unknown',
        'probe_seed':78123,'probe_random_count':5000,'normalization_scalar_check':'Every valid Unicode scalar except U+0000 and surrogates; C text input excludes embedded NUL',
        'acceptance':'All prior30 complete INT4 generations, input IDs and EOS/text must match NumPy/Rust. Every vocabulary token decoded at output indices0/1. All kernels and full/shard logits equal; native context boundary checked.',
        'device_acceptance':'Compressed <=24MiB, actual ready-role memory >=512KiB residual; old Supra control on staged firmware before model replacement; then6 cases, dispatcher pair,3 timings, Unicode and same-image OTA cold-load control.',
        'boundaries':'No P4 speedup comparison: variable EOS lengths; T13 is a fixed-request latency only. Do not treat wrong answers as transport failures.',
        'code_sha256':sources(),'artifacts':report,'prior_answer_sha256':sha(PRIOR/'answers-tinybrainbot-int4.json')}
    freeze(OUT/'protocol.json',protocol);print('Real SPBP artifacts prepared',json.dumps(report),flush=True)


def tokenizer_checks(native,protocol):
    # Standalone parser pointers are bound here; no unittest lifecycle is used.
    lib=native.lib;lib.sp_open.argtypes=[C.c_void_p,C.c_size_t,C.c_uint,C.c_uint];lib.sp_open.restype=C.c_void_p
    lib.sp_close.argtypes=[C.c_void_p];lib.sp_encode.argtypes=[C.c_void_p,C.c_char_p,C.POINTER(C.c_int),C.c_int]
    lib.sp_normalize.argtypes=[C.c_void_p,C.c_char_p,C.c_void_p,C.c_size_t]
    blob=C.create_string_buffer(pack_tokenizer(CANDIDATE/'tokenizer.json'));state=lib.sp_open(blob,len(blob.raw)-1,32000,7);assert state
    tok=tokenizers()['tinybrainbot'];buf=C.create_string_buffer(65536);out=(C.c_int*65536)();normal=0
    try:
        start=time.monotonic()
        for cp in range(1,0x110000):
            if 0xd800<=cp<=0xdfff:continue
            text=chr(cp);n=lib.sp_normalize(state,text.encode(),buf,len(buf));assert n>=0
            assert buf.raw[:n].decode()==tok.normalizer.normalize_str(text),('scalar normalization',hex(cp))
            normal+=1
        print('All scalar normalizations matched',normal,'in',round(time.monotonic()-start,2),'s',flush=True)
        rng=random.Random(protocol['probe_seed']);alphabet='abAB09 !?\t\n\r\x01\x1e\u00a0\u00e9\u0301\u0300\u00fc\u00df\u2122\ufb03\u0915\u094d\u0937\u1100\u1161\u11a8\u200d\U0001f469\U0001f4bb\uff21\uff11\u2581'
        tags=['<s>','</s>','<pad>','<unk>','<|user|>','<|assistant|>','<|end|>','<think>','</think>','<|mem_l1|>']
        probes=[c['prompt'] for c in protocol['cases']]+[protocol['unicode_prompt']]
        for i in range(protocol['probe_random_count']):
            text=''.join(rng.choice(alphabet) for _ in range(rng.randrange(1,80)))
            if i%3==0:
                at=rng.randrange(len(text)+1);text=text[:at]+rng.choice(tags)+text[at:]
            probes.append(text)
        for text in probes:
            n=lib.sp_encode(state,text.encode(),out,len(out));actual=list(out[:n]) if n>=0 else None
            assert actual==tok.encode(text,add_special_tokens=False).ids,('encode probe',ascii(text),actual,tok.encode(text,add_special_tokens=False).ids)
        print('Tokenizer input probes matched',len(probes),flush=True)
        return {'unicode_scalars_normalized':normal,'input_probes':len(probes),'seed':protocol['probe_seed'],'vocabulary_decode_cases':64000}
    finally:lib.sp_close(state)


def host(resume=False):
    import sys
    sys.path.insert(0,str(ROOT/'tests'))
    p=read(OUT/'protocol.json')
    if resume:
        amendment=read(OUT/'host-amendment.json')
        assert amendment['original_protocol_sha256']==sha(OUT/'protocol.json') and amendment['final_code_sha256']==sources()
        assert amendment['native_code_and_data_sections_identical'] and amendment['current_native_sha256']==sha(ROOT/'.local/build/tinyllm.dll')
    else:assert p['code_sha256']==sources()
    full=Native(PRIVATE/'tinybrainbot-full.p4qs')
    try:
        report=tokenizer_checks(full,p);tok=tokenizers()['tinybrainbot'];original={x['id']:x for x in read(PRIOR/'answers-tinybrainbot-int4.json')};rows=[]
        retained={r['case']:r for r in read(OUT/'host-generations.json')} if resume else {}
        if resume:assert len(retained)==30 and sha(OUT/'host-generations.json')==amendment['retained_generations_sha256']
        for case in p['cases']:
            assert full.encode(case['prompt'])==case['tokens'];result=retained[case['id']] if resume else full.generate(case['prompt'],48);before=original[case['id']]
            assert result['tokens']==before['tokens'] and result['text']==before['text'] and result['eos']==before['eos'],('Complete generation differs',case['id'],result)
            rows.append({'case':case['id'],**result})
            if not resume:write(OUT/'host-generations.json',rows)
            print('native',case['id'],'matched' if not resume else 'retained binary-equivalent proof',flush=True)
        if not resume:
            hardware={c['id']:full.generate(c['prompt'],p['hardware_cap']) for c in p['cases'] if c['id'] in p['hardware_cases']+p['dispatch_cases']}
            hardware['U01']=full.generate(p['unicode_prompt'],16);write(OUT/'hardware-references.json',hardware)
        master=Native(PRIVATE/'tinybrainbot-coordinator.p4qs');worker=Native(PRIVATE/'tinybrainbot-worker.p4qs')
        try:
            c,t=load_candidate();lib=full.lib;lib.ts_set_kernel.argtypes=[C.c_void_p,C.c_int];lib.ts_x.argtypes=[C.c_void_p];lib.ts_x.restype=C.POINTER(C.c_float);base=[];errors=[]
            for mode in range(5):
                for state in [full,master,worker]:assert lib.ts_set_kernel(state.state,mode)==0;lib.ts_reset(state.state)
                ref=Reference(c,row_int4(t))
                for pos,token in enumerate([4,257,1024]):
                    a=full.forward(token,pos);b=ref.step(token);import numpy as np
                    error=float(np.max(np.abs(a-b)));assert error<.003 and int(np.argmax(a))==int(np.argmax(b));errors.append(error)
                    if not mode:base.append(a)
                    else:np.testing.assert_array_equal(a,base[pos])
                    assert lib.ts_embed(master.state,token)==0 and lib.ts_layers(master.state,0,4,pos)==0
                    C.memmove(lib.ts_x(worker.state),lib.ts_x(master.state),c['hidden_size']*4);assert lib.ts_layers(worker.state,4,12,pos)==0
                    C.memmove(lib.ts_x(master.state),lib.ts_x(worker.state),c['hidden_size']*4)
                    np.testing.assert_array_equal(a,np.ctypeslib.as_array(lib.ts_finish(master.state),(32000,)))
            lib.ts_reset(master.state);lib.ts_reset(worker.state)
            for pos in range(256):
                assert lib.ts_embed(master.state,4)==0 and lib.ts_layers(master.state,0,4,pos)==0
                C.memmove(lib.ts_x(worker.state),lib.ts_x(master.state),c['hidden_size']*4)
                assert lib.ts_layers(worker.state,4,12,pos)==0
            assert lib.ts_layers(master.state,0,4,256)==-1 and lib.ts_layers(worker.state,4,12,256)==-1
            assert lib.ts_embed(worker.state,4)==-1
            report.update(complete_generations=30,all_tokens_text_eos_equal=True,full_shard_kernel_logits_identical=True,max_absolute_logit_error=max(errors),context_boundary_checked=True,sequential_KV_positions_per_role=256)
        finally:master.close();worker.close()
        report.update(code_sha256=sources(),native_dll_sha256=sha(ROOT/'.local/build/tinyllm.dll'),scope='Real tokenizer and actual weights on host; not a P4 result')
        write(OUT/'host-report.json',report);print('Host acceptance complete',json.dumps(report),flush=True)
    finally:full.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','host','host-resume']);a=p.parse_args();{'prepare':prepare,'host':host,'host-resume':lambda:host(True)}[a.stage]()
