"""Frozen, offline source/row-INT4 quality comparison; no device or network code."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import argparse
import hashlib
import json
import pathlib
import re
import sys
import time
from pack_supra import ROOT,np,load_tensors,load_source,shape_map
from supra_reference import Reference,row_int4

OUT=ROOT/'data/tinybrainbot-local-2026-10-29'
CACHE=ROOT/'.local/tinybrainbot-study'
CANDIDATE=ROOT/'.local/models/tinybrainbot-a8567bd7674f'
SUPRA=ROOT/'.local/models/supra100-2c90ade6ab47'
REV='a8567bd7674f53b3fe5f42c8abaab35229a0e00e'
WEIGHT_SHA='24e663ce03dbbd0820601341e210b40524b4fa15f9940079351eaaf48236ac62'
TEMPLATE="{{ ' ' }}{%- for m in messages -%}{{- '<|' + m['role'] + '|> ' + m['content'] + ' <|end|> ' -}}{%- endfor -%}{%- if add_generation_prompt -%}{{- '<|assistant|>' -}}{%- endif -%}"
CONDITIONS=('supra-f16','supra-int4','tinybrainbot-f16','tinybrainbot-int4')


def read(path):return json.loads(path.read_text('utf-8'))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((json.dumps(value,indent=2,ensure_ascii=True)+'\n').encode())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def freeze(path,value):
    if path.exists():
        if read(path)!=value:raise ValueError('Frozen record differs: '+str(path))
    else:write(path,value)


def prompt(model,user):
    if model=='tinybrainbot':return ' <|user|> '+user+' <|end|> <|assistant|>'
    if model=='supra':return '<|im_start|>user\n'+user+'<|im_end|>\n<|im_start|>assistant\n'
    raise ValueError('Unknown native template')


def validate_tensors(c,t):
    shapes=shape_map(c)
    if set(t)!=set(shapes) or any(t[k].shape!=s or not np.isfinite(t[k]).all() for k,s in shapes.items()):raise ValueError('Tensor inventory/values mismatch')
    if not c['tie_word_embeddings'] or c.get('hidden_act','silu')!='silu' or c.get('attention_bias',False) or c.get('mlp_bias',False):raise ValueError('Unsupported math')


def load_candidate():
    meta=read(CANDIDATE/'source-metadata.json')
    if meta['repository']!='nkthebass/tinybrainbot-100m-v3-instruct' or meta['revision']!=REV or sha(CANDIDATE/'model.safetensors')!=WEIGHT_SHA:raise ValueError('Pinned source mismatch')
    allowed={'config.json','tokenizer.json','tokenizer_config.json','README.md'}
    if {x['file'] for x in meta['files']}!=allowed:raise ValueError('Unexpected companion inventory')
    for x in meta['files']:
        if sha(CANDIDATE/x['file'])!=x['sha256']:raise ValueError('Companion digest mismatch')
    c=read(CANDIDATE/'config.json');t,_=load_tensors(CANDIDATE/'model.safetensors');validate_tensors(c,t)
    if sum(w.size for w in t.values())!=100092672:raise ValueError('Wrong parameter count')
    if read(CANDIDATE/'tokenizer_config.json')['chat_template']!=TEMPLATE:raise ValueError('Unsupported template change')
    return c,t


def budget(c,split=4,context=256,tokenizer_allowance=2*1024**2,runtime_allowance=2*1024**2):
    if not 0<split<c['num_hidden_layers']:raise ValueError('Invalid split')
    shapes=shape_map(c);sizes={n:(s[0]*4+s[0]*s[1]//2 if len(s)==2 else s[0]*4) for n,s in shapes.items()}
    kd=c['num_key_value_heads']*(c['hidden_size']//c['num_attention_heads']);result={}
    for role,first,end in [('coordinator',0,split),('worker',split,c['num_hidden_layers'])]:
        weights=256+sum(b for n,b in sizes.items() if (first<=int(n.split('.')[2])<end if n.startswith('model.layers.') else role=='coordinator'))
        tok=tokenizer_allowance if role=='coordinator' else 0;kv=2*(end-first)*context*kd*4
        work=2*(4*c['hidden_size']+2*c['intermediate_size'])*4+c['num_attention_heads']*context*4+(c['vocab_size']*4 if role=='coordinator' else 0)
        total=weights+tok+kv+work+runtime_allowance
        result[role]={'weights_header_bytes':weights,'tokenizer_allowance':tok,'kv_bytes':kv,'work_attention_logits_allowance':work,
                      'runtime_allowance':runtime_allowance,'estimated_total_psram_bytes':total,'estimated_headroom_bytes':32*1024**2-total,
                      'within_physical_psram':total<=32*1024**2}
    return result


def greedy(ref,tokens,decode,eos_ids,limit):
    if not tokens or limit<1 or len(tokens)+limit>ref.context:raise ValueError('Context or output cap invalid')
    output=[];stop=None
    for token in tokens:logits=ref.step(token)
    for i in range(limit):
        token=int(np.argmax(logits))
        if token in eos_ids:stop=token;break
        output.append(token)
        if i+1<limit:logits=ref.step(token)
    return {'tokens':output,'eos':stop is not None,'stop_id':stop,'text':decode(output)}


def screen(case,text):
    if 'exact' in case:return text.strip()==case['exact']
    first=re.split(r'[!?\r\n]|\.(?!\d)',text.strip(),maxsplit=1)[0]
    for answer in case['answers']:
        pattern=(r'(?<![\w.])'+re.escape(answer)+r'(?:\.0+)?(?![\w.]|\.\d)') if answer.isdigit() else r'(?<!\w)'+re.escape(answer)+r'(?!\w)'
        for m in re.finditer(pattern,first,re.I):
            if not re.search(r'\b(?:not|never|no)\s+(?:(?:a|an|the)\s+)?$',first[:m.start()],re.I):return True
    return False


def code_hashes():
    return {n:sha(ROOT/n) for n in ['tools/tinybrainbot_study.py','tools/pack_supra.py','tools/supra_reference.py']}


def tokenizers():
    sys.path.insert(0,str(ROOT/'.local/tooling/tinytalk-host'))
    from tokenizers import Tokenizer
    return {name:Tokenizer.from_file(str(p/'tokenizer.json')) for name,p in [('supra',SUPRA),('tinybrainbot',CANDIDATE)]}


def prepare():
    CACHE.mkdir(parents=True,exist_ok=True);c,t=load_candidate();sizes=budget(c);tok=tokenizers();inputs=read(OUT/'inputs.json');cases=[]
    for category,rows in inputs.items():
        for case in rows:
            formats={name:{'text':prompt(name,case['user']),'tokens':tokenizer.encode(prompt(name,case['user']),add_special_tokens=False).ids} for name,tokenizer in tok.items()}
            assert all(len(x['tokens'])+48<=256 for x in formats.values())
            ids=formats['tinybrainbot']['tokens'];assert ids.count(4)==ids.count(5)==ids.count(7)==1 and not ids.count(0)
            cases.append({**case,'category':category,'formats':formats})
    assert len(cases)==30 and len({x['id'] for x in cases})==30
    protocol={'date':'2026-10-29','scope':'Offline NumPy source-layout inference; no P4 writes or new tokenizer port',
        'candidate':read(CANDIDATE/'source-metadata.json'),'candidate_parameters':sum(w.size for w in t.values()),
        'baseline':{'repository':'SupraLabs/Supra2-100M-Instruct','revision':'2c90ade6ab47b910f48d0157a3e4c421d6311ed5','source_file':'Supra2-100M-SFT-F16.gguf','sha256':sha(SUPRA/'Supra2-100M-SFT-F16.gguf')},
        'conditions':list(CONDITIONS),'cases':cases,'context':256,'output_cap':48,'sampling':'greedy, no sampling or repetition penalties',
        'precision':'Author F16 weights promoted to FP32; same source-layout FP32 computation for both models; not original F32 equivalence',
        'int4':'Same symmetric per-row nearest INT4, ties-to-even, -7..7, FP32 scale, all matrix weights including tied table; FP32 norms/KV',
        'stop_ids':{'supra':[2,6],'tinybrainbot':[7]},'template_policy':'Exact author tokenizer configuration, no default system, no implicit BOS; TinyBrainBot uses spaces, not card newline example.',
        'input_sha256':sha(OUT/'inputs.json'),'code_sha256':code_hashes(),
        'primary':'Unblinded manual first directly responsive factual claim on 20 new facts, with separate clean-within-visible-cap count requiring no visible factual contradiction, evasion, role leakage or material irrelevant drift. Expected terms are examples, not mandatory phrasing.',
        'other_endpoints':'4 exact case-sensitive stripped replies; 4 grounded answers using only the stated facts. Supporting first-sentence term screen is not a semantic judge. 2 known anchors excluded from primary counts.',
        'decision_rule':'Promising if TinyBrainBot beats Supra in both F16 and row-INT4 first-fact counts and does not reduce clean-fact counts. No P4 adoption implied; tokenizer/native port and allocation still required.',
        'limits':'One deterministic cap48 run per case, small synthetic English tasks, author review not blinded or independent. Fresh relative to our prior experiments, not claimed unseen in pretraining. Native templates/tokenizers differ; same token cap is not equal word/byte budget.',
        'estimated_memory':sizes,'memory_limit':'Proposed row-INT4 layout with 2MiB tokenizer allowance on coordinator and 2MiB runtime reserve per role. Conditional, not measured allocation or compressed-flash proof.'}
    freeze(OUT/'protocol.json',protocol)
    print('Frozen',len(cases),'cases,',len(CONDITIONS),'conditions; all estimated role headrooms positive:',{k:v['estimated_headroom_bytes'] for k,v in sizes.items()},flush=True)


def run():
    protocol=read(OUT/'protocol.json')
    assert code_hashes()==protocol['code_sha256'] and sha(OUT/'inputs.json')==protocol['input_sha256']
    tok=tokenizers();supra_c=read(SUPRA/'config.json');supra_t=load_source(SUPRA)[0];candidate_c,candidate_t=load_candidate()
    for condition in CONDITIONS:
        path=OUT/('answers-'+condition+'.json')
        if path.exists():raise ValueError('Answer evidence already exists; do not overwrite')
        name,precision=condition.rsplit('-',1);c,t=(supra_c,supra_t) if name=='supra' else (candidate_c,candidate_t)
        weights=t if precision=='f16' else row_int4(t);results=[]
        for case in protocol['cases']:
            tokens=case['formats'][name]['tokens'];start=time.monotonic()
            result=greedy(Reference(c,weights,context=256),tokens,lambda ids:tok[name].decode(ids,skip_special_tokens=False),set(protocol['stop_ids'][name]),48)
            results.append({'id':case['id'],'category':case['category'],**result,'screen_pass':screen(case,result['text']),'host_seconds':time.monotonic()-start})
            write(path,results);print(condition,case['id'],ascii(result['text']),flush=True)
        del weights
    freeze(OUT/'generation-receipt.json',{'protocol_sha256':sha(OUT/'protocol.json'),'code_sha256':code_hashes(),
        'complete_generations':120,'answer_sha256':{n:sha(OUT/('answers-'+n+'.json')) for n in CONDITIONS},'scope':protocol['scope']})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['prepare','run']);a=p.parse_args();{'prepare':prepare,'run':run}[a.stage]()


if __name__=='__main__':main()
