"""Quantization control on frozen prompts; retain failures without prompt tuning."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import argparse
import json
from pack_supra import np,load_source
from supra_reference import Reference,row_int4
from check_supra_native import write


def generate(c,t,tokens,cap,vocab):
    ref=Reference(c,t);out=[];eos=False
    for token in tokens:logits=ref.step(token)
    for i in range(cap):
        token=int(np.argmax(logits))
        if token==c['eos_token_id'] or vocab[token]==b'<|im_end|>':eos=True;break
        out.append(token)
        if i+1<cap:logits=ref.step(token)
    return {'tokens':out,'eos':eos,'text':b''.join(vocab[i] for i in out).decode('utf-8','replace')}


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=__import__('pathlib').Path);p.add_argument('results',type=__import__('pathlib').Path);a=p.parse_args()
    c=json.loads((a.directory/'config.json').read_text('utf-8'));t,_=load_source(a.directory);q=row_int4(t)
    from pack_supra import tokenizer
    vocab,*_=tokenizer(a.directory)
    cases=json.loads((a.results/'protocol.json').read_text('utf-8'))['cases'];native=json.loads((a.results/'host-generations.json').read_text('utf-8'));rows=[]
    for case,actual in zip(cases,native):
        quant=generate(c,q,actual['prompt_tokens'],case['limit'],vocab)
        assert quant['tokens']==actual['tokens'] and quant['eos']==actual['eos'],('Complete source-layout INT4/C mismatch',case['id'])
        original=generate(c,t,actual['prompt_tokens'],case['limit'],vocab)
        rows.append({'case':case['id'],'source_precision_float32_compute':original,'int4_matches_C':True,'same_as_source':original['tokens']==quant['tokens'] and original['eos']==quant['eos']})
        write(a.results/'source-controls.json',rows);print(case['id'],'same' if rows[-1]['same_as_source'] else 'changed',flush=True)


if __name__=='__main__':main()
