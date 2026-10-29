"""Freeze and run the local TinyTalk-2 feasibility screen; no device/network calls."""
import argparse
import hashlib
import json
import pathlib
import sys
import time
from html import escape

from tinytalk_reference import (ROOT,REPOSITORY,REVISION,Reference,batch_forward,
                                load_checkpoint,memory_budget,row_int8)
import numpy as np

MODEL=ROOT/'.local/models'/('tinytalk2-'+REVISION[:12])


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')


def freeze(output):
    output.mkdir(parents=True,exist_ok=False)
    old=json.loads((ROOT/'data/quality-v1-2026-10-29/protocol.json').read_text(encoding='utf-8'))
    cases=[{**c,'source':'reused prior quality-V1 task','mode':'chat'} for c in old['cases'] if c['category']!='story']
    cases+=[
        {'id':'Q4','category':'question','prompt':'What is a baby dog called?','expected':['puppy'],'limit':32,'mode':'chat'},
        {'id':'Q5','category':'question','prompt':'What is the opposite of hot?','expected':['cold'],'limit':32,'mode':'chat'},
        {'id':'Q6','category':'question','prompt':'How many legs does a cat have?','expected':['four','4'],'limit':32,'mode':'chat'},
        {'id':'C1','category':'dialogue','prompt':'Hi! How are you?','limit':32,'mode':'chat'},
        {'id':'C2','category':'memory','prompt':'What is my cat\'s name?','history':[{'role':'user','content':'My cat is called Luna.'},{'role':'assistant','content':'Luna is a nice name.'}],'limit':32,'mode':'chat'},
        {'id':'U1','category':'unknown','prompt':'What is the serial number of the board on my desk?','limit':32,'mode':'chat'},
        {'id':'S1','category':'story','prompt':'a little fox shares an apple with a hungry rabbit and they become friends','limit':128,'mode':'story'},
        {'id':'D1','category':'language-boundary','prompt':'Welche Farbe hat eine reife Banane?','limit':32,'mode':'chat'},
    ]
    sources={n:digest(MODEL/n) for n in ['model.safetensors','config.json','tokenizer.json','tokenizer_config.json','README.md']}
    source_files={n:digest(ROOT/'tools'/n) for n in ['tinytalk_reference.py','evaluate_tinytalk.py']}
    p={'model':REPOSITORY,'revision':REVISION,'source_sha256':sources,'script_sha256':source_files,
       'order':['fp32','row-int8-simulation'],'sampler':'greedy','context':256,'cases':cases,
       'numerical_tolerance_absolute':.001,'cached_batch_argmax_must_match':True,
       'classification':'Exploratory host screen; no hardware or independent Transformers execution',
       'score_policy':'Exact I1/I2 equality; question lexical signals plus manual first-fact/one-sentence inspection. C2/U1/S1/D1 require manual review. Same assistant, unblinded; no general benchmark ranking.',
       'old_comparison':'Only Q1-Q3/I1-I3 reuse prior tasks; checkpoint/prompt wrapper and execution platform differ. No pooled speed or blinded paired-quality claim.',
       'quantization':'All 2-D weights including learned positions row-wise INT8 then dequantized to FP32 for host math; vectors/biases stay FP32. No packed deployment format is emitted.',
       'stopping':'EOS 50256 is excluded from displayed/output tokens; eos flag is directly observed. Otherwise stop at the fixed token limit.'}
    write(output/'protocol.json',p)
    (output/'protocol.sha256').write_text(digest(output/'protocol.json')+'\n',encoding='utf-8')
    print(json.dumps({'protocol_frozen':True,'sha256':digest(output/'protocol.json'),'cases':len(cases)}))


def prompt(case):
    if case['mode']=='story':return 'Summary: '+case['prompt']+'\nStory:'
    messages=case.get('history',[])+[{'role':'user','content':case['prompt']}]
    return ''.join(('User: ' if m['role']=='user' else 'Bot: ')+m['content']+('' if m['role']=='user' else '<|endoftext|>')+'\n' for m in messages)+'Bot:'


def run(output):
    if (output/'results.json').exists():raise ValueError('Refuse to overwrite completed screen')
    protocol=output/'protocol.json'
    if digest(protocol)!=(output/'protocol.sha256').read_text().strip():raise ValueError('Frozen protocol changed')
    p=json.loads(protocol.read_text(encoding='utf-8'))
    if p['model']!=REPOSITORY or p['revision']!=REVISION:raise ValueError('Wrong candidate')
    for n,h in p['source_sha256'].items():
        if digest(MODEL/n)!=h:raise ValueError('Source changed: '+n)
    for n,h in p['script_sha256'].items():
        if digest(ROOT/'tools'/n)!=h:raise ValueError('Script changed after freeze: '+n)
    sys.path.insert(0,str(ROOT/'.local/tooling/tinytalk-host'))
    from tokenizers import Tokenizer
    import tokenizers
    tok=Tokenizer.from_file(str(MODEL/'tokenizer.json'))
    c,tensors=load_checkpoint(MODEL)
    tj=json.loads((MODEL/'tokenizer.json').read_text(encoding='utf-8'))
    if tj['model']['type']!='BPE' or tj['pre_tokenizer']['type']!='ByteLevel':raise ValueError('Unexpected tokenizer')
    pieces=tj['model']['vocab'];merges=tj['model']['merges']
    # Each GPT-2 visible alphabet character maps to one byte. Offset table
    # includes a sentinel; each merge records left/right/result IDs in 12 bytes.
    tokenizer_bytes=sum(len(x) for x in pieces)+4*(len(pieces)+1)+12*len(merges)
    budget=memory_budget(c,tokenizer_bytes,p['context'])
    write(output/'budget.json',budget)
    write(output/'sources.json',{'repository':REPOSITORY,'revision':REVISION,
        'files':p['source_sha256'],'downloads':json.loads((MODEL/'downloads.json').read_text()),
        'declared_license':'CC BY-NC-SA 4.0','full_vocabulary':len(pieces),'merge_count':len(merges),
        'dependency':json.loads((ROOT/'.local/tooling/tinytalk-host/wheel-provenance.json').read_text()),
        'architecture_reference':json.loads((MODEL/'reference/source.json').read_text()),
        'upstream_model_python_executed':False})
    results=[];numerical=[];reference_logits=None
    for variant in p['order']:
        w=tensors if variant=='fp32' else row_int8(tensors)
        ids=tok.encode(prompt(p['cases'][0]),add_special_tokens=False).ids
        batch=batch_forward(c,w,ids)
        engine=Reference(c,w,p['context'])
        cached=np.stack([engine.step(int(x)) for x in ids])
        error=float(np.max(np.abs(batch-cached)))
        argmax_equal=bool(np.array_equal(np.argmax(batch,axis=1),np.argmax(cached,axis=1)))
        check={'variant':variant,'positions':len(ids),'full_logits_per_position':c['vocab_size'],
               'max_absolute_error':error,'cached_batch_argmax_all_equal':argmax_equal}
        if error>p['numerical_tolerance_absolute'] or not argmax_equal:raise ValueError('Numerical consistency failed: '+json.dumps(check))
        if reference_logits is None:reference_logits=cached
        else:
            check['fp32_vs_int8_max_absolute_logit_difference']=float(np.max(np.abs(reference_logits-cached)))
            check['fp32_vs_int8_argmax_equal_positions']=int(np.count_nonzero(np.argmax(reference_logits,axis=1)==np.argmax(cached,axis=1)))
        numerical.append(check);write(output/'numerical.json',numerical)
        for case in p['cases']:
            text=prompt(case);ids=tok.encode(text,add_special_tokens=False).ids
            if not ids or len(ids)+case['limit']>p['context']:raise ValueError('Case does not fit frozen context')
            engine.reset();started=time.perf_counter()
            for token in ids:logits=engine.step(int(token))
            output_ids=[];eos=False
            for index in range(case['limit']):
                token=int(np.argmax(logits))
                if token==c['eos_token_id']:eos=True;break
                output_ids.append(token)
                if index+1<case['limit']:logits=engine.step(token)
            elapsed=time.perf_counter()-started
            result={'variant':variant,'case':case['id'],'category':case['category'],
                    'formatted_prompt':text,'prompt_tokens':ids,'tokens':output_ids,
                    'output_tokens':len(output_ids),'limit':case['limit'],'eos_observed':eos,
                    'text':tok.decode(output_ids,skip_special_tokens=True),'host_elapsed_seconds':elapsed}
            if 'exact' in case:result['exact_match']=result['text'].strip()==case['exact']
            if 'expected' in case:
                import re
                words=set(re.findall(r"[a-z0-9]+",result['text'].lower()))
                result['lexical_signal']=any(x in words for x in case['expected'])
            results.append(result);write(output/'partial-results.json',results)
            print(variant,case['id'],len(output_ids),'eos' if eos else 'limit',flush=True)
    write(output/'results.json',results)
    summary={'classification':'Exploratory host feasibility only','cases_per_variant':len(p['cases']),
             'tokenizers_version':tokenizers.__version__,'p4_inference_tested':False,'firmware_modified':False,
             'same_assistant_unblinded_review':True,'quantization_token_identity_not_required':True,'variants':{}}
    for variant in p['order']:
        rows=[r for r in results if r['variant']==variant]
        summary['variants'][variant]={'output_tokens':sum(r['output_tokens'] for r in rows),
            'eos_count':sum(r['eos_observed'] for r in rows),'exact_I1_I2':sum(r.get('exact_match',False) for r in rows),
            'question_lexical_signals':sum(r.get('lexical_signal',False) for r in rows),'question_count':6}
    summary['full_token_sequences_equal_between_variants']=sum(a['tokens']==b['tokens'] and a['eos_observed']==b['eos_observed'] for a,b in zip(results[:len(p['cases'])],results[len(p['cases']):]))
    write(output/'summary.json',summary)
    html=['<!doctype html><html lang="en"><meta charset="utf-8"><title>TinyTalk-2 host feasibility</title><style>body{font:16px/1.6 system-ui;max-width:1200px;margin:30px auto;padding:20px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}article{border:1px solid #888;padding:20px}pre{white-space:pre-wrap;font:inherit}@media(max-width:700px){.pair{grid-template-columns:1fr}}</style><h1>TinyTalk-2: complete host outputs</h1><p>Exploratory, unblinded; no P4 execution. Row INT8 is simulated with dequantized FP32 matrices. Host times are not device-speed results. Lexical signals are not correctness judgements.</p>']
    for case in p['cases']:
        html+=['<section><h2>'+case['id']+' / '+case['category']+'</h2><pre>'+escape(case['prompt'])+'</pre><div class="pair">']
        for row in [r for r in results if r['case']==case['id']]:
            html+=['<article><h3>'+row['variant']+'</h3><p>'+str(row['output_tokens'])+' tokens; '+('EOS observed' if row['eos_observed'] else 'limit reached')+'</p><pre>'+escape(row['text'])+'</pre></article>']
        html+=['</div></section>']
    (output/'comparison.html').write_text('\n'.join(html)+'\n</html>\n',encoding='utf-8')
    write(output/'sha256-manifest.json',{str(x.relative_to(ROOT)).replace('\\','/'):digest(x) for x in sorted(output.iterdir()) if x.is_file() and x.name!='sha256-manifest.json'})
    print(json.dumps(summary))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['freeze','run']);parser.add_argument('output',type=pathlib.Path)
    args=parser.parse_args()
    (freeze if args.action=='freeze' else run)(args.output.resolve())
