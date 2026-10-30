"""Offline, staged and frozen Supra2 INT4 comparison. No downloads or device writes."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import argparse
import hashlib
import json
import pathlib
import re
import sys
import time
from pack_supra import ROOT,np,load_source,tokenizer
from supra_reference import Reference,row_int4
from supra_source_controls import generate
from quantization_v2 import group_quantize,dequantize,gptq_quantize,inverse_factor,matrix_bytes

OUT=ROOT/'data/supra-quantization-v2-2026-10-29'
CACHE=ROOT/'.local/quantization-v2'
SOURCE=ROOT/'.local/models/supra100-2c90ade6ab47'
VARIANTS=('s32','a64','gptq')


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes((json.dumps(value,indent=2,ensure_ascii=True)+'\n').encode())


def freeze(path,value):
    if path.exists():
        if json.loads(path.read_text('utf-8'))!=value:raise ValueError('Frozen evidence changed: '+str(path))
    else:write(path,value)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text('utf-8'))
def config():return read(SOURCE/'config.json')
def model():return load_source(SOURCE)[0]
def chat(user):return '<|im_start|>user\n'+user+'<|im_end|>\n<|im_start|>assistant\n'


def fidelity(source,actual):
    a=np.asarray(source,dtype='float64');b=np.asarray(actual,dtype='float64')
    if a.ndim!=2 or a.shape!=b.shape or not a.size or not np.isfinite(a).all() or not np.isfinite(b).all():raise ValueError('Invalid logit arrays')
    def logp(x):
        x=x-x.max(axis=1,keepdims=True)
        return x-np.log(np.exp(x).sum(axis=1,keepdims=True))
    lp=logp(a);lq=logp(b);kl=np.sum(np.exp(lp)*(lp-lq),axis=1)
    agreement=np.argmax(a,axis=1)==np.argmax(b,axis=1)
    return {'positions':len(a),'mean_kl_nats':float(kl.mean()),'top1_agreement':float(agreement.mean()),
            'per_position_kl_nats':kl.tolist(),'per_position_top1_agreement':agreement.tolist()}


def select_candidate(baseline,variants):
    admitted={name:row for name,row in variants.items() if row['mean_kl_nats']<=.9*baseline['mean_kl_nats']
              and row['top1_agreement']+1e-12>=baseline['top1_agreement']-.05}
    winner=min(admitted,key=lambda n:(admitted[n]['mean_kl_nats'],n)) if admitted else None
    return {'winner':winner,'admitted':list(admitted),
            'rule':'Lowest mean full-vocabulary KL; >=10% below row, top1 no more than 5 percentage points below row; QA unused'}


def score_answer(case,text):
    rule=case['rule']
    if 'exact' in rule:return text.strip()==rule['exact']
    # Only the first sentence/line is screened; decimal points stay inside numbers.
    first=re.split(r'(?<=[A-Za-z])[.!?]|[\r\n]',text.strip(),maxsplit=1)[0].lower()
    if not re.search(rule['pattern'],first,re.I):return False
    if rule.get('forbidden') and re.search(rule['forbidden'],first,re.I):return False
    if 'numbers' in rule:
        words={'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12}
        nums=[float(x) for x in re.findall(r'(?<![\w.])-?\d+(?:\.\d+)?',first)]
        nums += [value for word,value in words.items() if re.search(r'\b'+word+r'\b',first)]
        if any(x not in rule['numbers'] for x in nums):return False
    return True


def provenance():
    names=['tools/quantization_v2.py','tools/supra_quantization_study.py','tools/supra_reference.py','tools/pack_supra.py']
    return {name:sha(ROOT/name) for name in names}


def prepare():
    sys.path.insert(0,str(ROOT/'.local/tooling/tinytalk-host'))
    from tokenizers import Tokenizer
    tok=Tokenizer.from_file(str(SOURCE/'tokenizer.json'))
    inputs=read(OUT/'inputs.json');sets={}
    for key in ('calibration','validation'):
        sets[key]=[{**x,'tokens':tok.encode(x['text'],add_special_tokens=False).ids[:64]} for x in inputs[key]]
    assert sum(len(x['tokens']) for x in sets['calibration'])<=1024
    quality=[{**x,'prompt':chat(x['user']),'limit':24} for x in inputs['quality']]
    old=read(ROOT/'data/supra100-2026-10-29/protocol.json')
    known=[{**x,'limit':24,'category':'known-regression'} for x in old['cases'] if x['id'] in ('N2','N4','N6','N7')]
    for x in quality+known:x['tokens']=tok.encode(x['prompt'],add_special_tokens=False).ids
    timing=next(x for x in old['cases'] if x['id']=='S2')
    timing={**timing,'tokens':tok.encode(timing['prompt'],add_special_tokens=False).ids}
    assert not set(x['text'] for x in sets['calibration']) & set(x['text'] for x in sets['validation'])
    protocol={'source_repository':'SupraLabs/Supra2-100M-Instruct','source_revision':'2c90ade6ab47b910f48d0157a3e4c421d6311ed5',
        'source_file':'Supra2-100M-SFT-F16.gguf','source_sha256':sha(SOURCE/'Supra2-100M-SFT-F16.gguf'),
        'source_precision':'Author F16 weights, FP32 compute. Not original F32 parity.',
        'context':256,'split':4,'vocabulary':32768,'calibration_token_cap_per_document':64,
        'validation_token_cap_per_document':64,'calibration_count':sum(len(x['tokens']) for x in sets['calibration']),
        **sets,'quality':quality,'known_regressions':known,'timing':timing,'timing_repeats':3,
        'hardware_cases':['F01','F06','F08','E01','N2','N7'],'hardware_output_cap':16,
        'variants':{'s32':'All matrices symmetric group32 RTN, F16 scales',
                    'a64':'Tied embedding symmetric group32, transformer affine group64 RTN, F16 scales/u8 zeros',
                    'gptq':'Same grids as a64; static-grid GPTQ-inspired transformer compensation, source activations'},
        'shrink_grid':[1.,.98,.96,.94,.92,.90],'gptq':{'damping':.01,'block':128,'act_order':False,'true_sequential':False},
        'selection':'>=10% mean validation KL reduction vs row, top1 loss <=.05, then minimum KL; no QA-based tuning',
        'quality_rule':'Frozen lexical first-sentence fact screen (16) and case-sensitive stripped exact reply (4). Numeric cases reject other numbers. Not a general factuality metric.',
        'quality_admission':'Selected candidate fact-screen count must be >= row count. No alternative chosen using QA.',
        'limits':'Small synthetic English sets, single calibration, greedy cap24, unblinded. New QA unused for tuning, not claimed held out from pretraining.',
        'device_admission':'Compressed <=24MiB each, conservative residual PSRAM >=512KiB each. Portable C/reference validation before any upload.',
        'inputs_sha256':sha(OUT/'inputs.json'),'initial_code_sha256':provenance()}
    freeze(OUT/'protocol.json',protocol)
    CACHE.mkdir(parents=True,exist_ok=True)
    print('Frozen calibration tokens',protocol['calibration_count'],'validation',sum(len(x['tokens']) for x in sets['validation']),flush=True)


def canonical(name):
    name=name.replace('k_proj','q_proj').replace('v_proj','q_proj').replace('up_proj','gate_proj')
    return name


def calibrate():
    protocol=read(OUT/'protocol.json');path=CACHE/'activations.npz'
    if path.exists():raise ValueError('Activation cache exists; do not replace calibration')
    t=model();c=config();seen={}
    def observe(name,x):
        if name=='model.embed_tokens.weight' or name!=canonical(name):return
        seen.setdefault(name,[]).append(x)
    start=time.monotonic()
    for doc in protocol['calibration']:
        ref=Reference(c,t,observer=observe)
        for token in doc['tokens']:ref.step(token)
        print('calibration',doc['id'],len(doc['tokens']),flush=True)
    arrays={name:np.stack(values) for name,values in seen.items()};np.savez_compressed(path,**arrays)
    freeze(OUT/'calibration.json',{'tokens':protocol['calibration_count'],'matrices':{n:list(x.shape) for n,x in arrays.items()},
           'activation_sha256':sha(path),'seconds':time.monotonic()-start,'code_sha256':provenance(),
           'scope':'Source-F16/FP32 inputs; shared QKV and gate/up groups; output embedding not GPTQ optimized'})


def candidates():
    protocol=read(OUT/'protocol.json');t=model();activations=np.load(CACHE/'activations.npz',allow_pickle=False)
    stats={};sse={n:0. for n in VARIANTS};elements=0;sizes={n:{} for n in VARIANTS};last=None;factor=None;h=None
    for name,w in t.items():
        if w.ndim!=2:
            for variant in VARIANTS:sizes[variant][name]=w.size*4
            continue
        paths={n:CACHE/n/(name+'.npz') for n in VARIANTS}
        if any(p.exists() for p in paths.values()):raise ValueError('Candidate cache already exists: '+name)
        s=group_quantize(w,32);a=s if name=='model.embed_tokens.weight' else group_quantize(w,64,'affine')
        if name=='model.embed_tokens.weight':g=a
        else:
            key=canonical(name)
            if key!=last:
                x=activations[key].astype('float64');h=x.T@x/len(x);factor=inverse_factor(h);last=key
            g=gptq_quantize(w,h,a,factor=factor)
        for variant,q in zip(VARIANTS,(s,a,g)):
            paths[variant].parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(paths[variant],**q)
            sizes[variant][name]=matrix_bytes(q);sse[variant]+=float(np.sum((w-dequantize(q)).astype('float64')**2))
        elements+=w.size;print('quantized',name,flush=True)
    for variant in VARIANTS:
        paths=sorted((CACHE/variant).glob('*.npz'))
        stats[variant]={'weight_rmse':(sse[variant]/elements)**.5,'matrix_elements':elements,'matrix_bytes':sizes[variant],
                        'quantized_cache_sha256':{p.name:sha(p) for p in paths}}
    freeze(OUT/'candidates.json',{'variants':stats,'code_sha256':provenance(),'protocol_sha256':sha(OUT/'protocol.json')})


def load_variant(name,source):
    if name=='f16':return source
    if name=='row':return row_int4(source)
    t={}
    for key,w in source.items():
        if w.ndim!=2:t[key]=w
        else:
            with np.load(CACHE/name/(key+'.npz'),allow_pickle=False) as data:
                q=dict(data);q['group']=int(q['group']);q['scheme']=int(q['scheme']);t[key]=dequantize(q)
    return t


def validate():
    protocol=read(OUT/'protocol.json');c=config();source=model();summary={}
    if (OUT/'selection.json').exists():raise ValueError('Selection already frozen')
    for variant in ('f16','row',*VARIANTS):
        t=load_variant(variant,source);all_logits=[];docs=[]
        for doc in protocol['validation']:
            ref=Reference(c,t);logits=np.stack([ref.step(token) for token in doc['tokens']])
            all_logits.append(logits);path=CACHE/(doc['id']+'-f16.npy')
            if variant=='f16':np.save(path,logits,allow_pickle=False)
            result=fidelity(np.load(path,allow_pickle=False),logits);docs.append({'id':doc['id'],**result})
        if variant=='f16':reference=np.concatenate(all_logits)
        summary[variant]=fidelity(reference,np.concatenate(all_logits));summary[variant]['documents']=docs
        write(OUT/('validation-'+variant+'.json'),summary[variant]);print('validation',variant,summary[variant]['mean_kl_nats'],summary[variant]['top1_agreement'],flush=True)
        del t,all_logits
    selection=select_candidate(summary['row'],{n:summary[n] for n in VARIANTS})
    selection['validation_sha256']={n:sha(OUT/('validation-'+n+'.json')) for n in summary}
    selection['protocol_sha256']=sha(OUT/'protocol.json');selection['code_sha256']=provenance()
    freeze(OUT/'selection.json',selection);print('winner',selection['winner'],flush=True)


def quality():
    protocol=read(OUT/'protocol.json');selection=read(OUT/'selection.json');winner=selection['winner'];c=config();source=model();vocab,*_=tokenizer(SOURCE)
    variants=['f16','row']+([winner] if winner else []);scores={}
    for variant in variants:
        path=OUT/('answers-'+variant+'.json')
        if path.exists():raise ValueError('Answer evidence exists; do not overwrite')
        t=load_variant(variant,source);rows=[];counts={'fact':0,'exact':0}
        for case in protocol['quality']+protocol['known_regressions']:
            result=generate(c,t,case['tokens'],case['limit'],vocab)
            passed=score_answer(case,result['text']) if 'rule' in case else None
            if passed:counts[case['category']]+=1
            rows.append({'id':case['id'],'category':case['category'],**result,'screen_pass':passed})
            write(path,rows);print('answer',variant,case['id'],ascii(result['text']),passed,flush=True)
        scores[variant]=counts;del t
    admitted=winner is not None and scores[winner]['fact']>=scores['row']['fact']
    freeze(OUT/'quality-summary.json',{'counts':scores,'fact_cases':16,'exact_cases':4,'winner':winner,'quality_admitted':admitted,
        'selection_sha256_before_answers':sha(OUT/'selection.json'),'answer_sha256':{n:sha(OUT/('answers-'+n+'.json')) for n in variants},
        'rule':protocol['quality_rule'],'limits':protocol['limits'],'code_sha256':provenance()})
    print('quality admission',admitted,scores,flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=['freeze','calibrate','candidates','validate','quality'])
    a=parser.parse_args();{'freeze':prepare,'calibrate':calibrate,'candidates':candidates,'validate':validate,'quality':quality}[a.stage]()


if __name__=='__main__':main()
