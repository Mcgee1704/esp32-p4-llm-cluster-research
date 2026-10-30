"""Freeze a Supra protocol; compare source-layout NumPy, portable C and shards."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import argparse
import ctypes as C
import hashlib
import json
import pathlib
import random
import time
from pack_supra import ROOT,np,load_source,tokenizer
from supra_reference import Reference,row_int4
from check_gptneo_native import Native


def write(path,x):path.write_text(json.dumps(x,indent=2,ensure_ascii=True)+'\n','utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=pathlib.Path);p.add_argument('output',type=pathlib.Path);p.add_argument('--resume-validation',action='store_true')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=a.resume_validation)
    if (a.output/'host-report.json').exists():raise ValueError('Completed evidence cannot be overwritten')
    prior=json.loads((ROOT/'data/matched-models-2026-10-29/protocol.json').read_text('utf-8'))
    cases=[dict(id=x['id'],category=x['category'],prompt=x['prompt'],limit=32) for x in prior['cases']]
    c=json.loads((a.directory/'config.json').read_text('utf-8'))
    qwen=c['architectures']==['Qwen3ForCausalLM']
    if qwen:
        for case in cases:case['limit']=16
        native=[('N1','What color is a ripe banana?'),('N2','How many wheels does a standard bicycle have?'),
                ('N3','What is a baby dog called?'),('N4','What is the opposite of hot?'),('N5','How many legs does a typical cat have?'),
                ('N6','Reply with exactly one word: blue.'),('N7','Write one short story about a rabbit sharing a carrot.')]
        for name,text in native:cases.append({'id':name,'category':'native-chat','prompt':'<|im_start|>user\n'+text+'<|im_end|>\n<|im_start|>assistant\n','limit':16})
    # No chat template or automatic BOS is supplied by the 50M tokenizer assets.
    # Raw common prefixes are primary. No prompt revision after seeing results.
    protocol={'source':json.loads((a.directory/'source-metadata.json').read_text('utf-8'))['repository'],
              'context':256,'generation':'greedy, no sampling, full vocabulary, EOS from metadata',
              'prompt_policy':'exact shared prefixes; no inferred chat template or implicit BOS',
              'cases':cases,'quantization':'symmetric row INT4, ties-to-even, -7..7, float32 scales',
              'logit_tolerance':.003,'numerical_tokens':[0,300,42,17,1000,2,7,9],
              'timing_case':'S2','timing_limit':16,'timing_repeats':3}
    if qwen:
        protocol['prompt_policy']='Raw shared prefixes plus separately labelled exact author ChatML template, no implicit BOS'
        protocol['hardware_cases']=['S2','Q2','Q3','I1','N1','N2','N6','N7']
        protocol['dispatch_cases']=['S2','N7']
        protocol['source_precision']='Author F16 GGUF; FP32 compute; not original-F32 parity'
        protocol['native_template_sha256']=hashlib.sha256((a.directory/'chat_template.jinja').read_bytes()).hexdigest()
    if (a.output/'protocol.json').exists():
        assert json.loads((a.output/'protocol.json').read_text('utf-8'))==protocol,'Frozen protocol changed'
    else:write(a.output/'protocol.json',protocol)
    import sys
    sys.path.insert(0,str(ROOT/'.local/tooling/tinytalk-host'))
    from tokenizers import Tokenizer
    upstream=Tokenizer.from_file(str(a.directory/'tokenizer.json'))
    vocab,merges,ranges,specials,digits=tokenizer(a.directory)
    native=Native(a.directory/'supra-full.p4qs');master=Native(a.directory/'supra-coordinator.p4qs');worker=Native(a.directory/'supra-worker.p4qs')
    l=native.lib;l.ts_x.argtypes=[C.c_void_p];l.ts_x.restype=C.POINTER(C.c_float)
    report={'scope':'Host numerical validation; not P4 hardware','tokenizer_probes':0,'vocabulary_pieces':len(vocab)}
    try:
        for i,v in enumerate(vocab):assert native.piece(i)==v,('piece',i)
        probes=[x['prompt'] for x in cases]+['','<s>Hello</s><pad><unk><|im_start|>assistant<|im_end|>',"I'm you're WE'RE they've IT'S he'll I'd",' \t\n\r  word  \n\n tail\t','012345 12.34 Ã¯Â¼â€˜Ã¯Â¼â€™Ã¯Â¼â€œ Ã™Â¡Ã™Â¢Ã™Â£','GrÃƒÂ¼ÃƒÅ¸e! cafÃƒÂ© naÃƒÂ¯ve StraÃƒÅ¸e Ã¤Â¸â‚¬Ã¤ÂºÅ’Ã¤Â¸â€° Ã°Å¸â„¢â€šÃ°Å¸Å¡â‚¬']
        rng=random.Random(194);alphabet='abAB09 !?\t\n\r\u00a0ÃƒÂ©ÃƒÂ¼ÃƒÅ¸Ã¤Â¸Â­Ã°Å¸â„¢â€š\u0301\u2009'
        probes+=[''.join(rng.choice(alphabet) for _ in range(rng.randrange(1,80))) for _ in range(100)]
        for lo,hi,kind in ranges:probes.append('A'+chr(lo)+chr(hi)+'0! x')
        for text in probes:assert native.encode(text)==upstream.encode(text,add_special_tokens=False).ids,('encode',repr(text))
        report['tokenizer_probes']=len(probes)
        t,_=load_source(a.directory);reference=Reference(c,row_int4(t));errors=[]
        for x in [native,master,worker]:l.ts_reset(x.state)
        split=int.from_bytes(master.raw[172:176],'little')
        # Global layer range is metadata offsets 40,44 (body starts at 128).
        for pos,token in enumerate(protocol['numerical_tokens']):
            actual=native.forward(token,pos);expected=reference.step(token)
            error=float(np.max(np.abs(actual-expected)));errors.append(error)
            assert error<protocol['logit_tolerance'] and int(np.argmax(actual))==int(np.argmax(expected)),('logit',pos,error)
            assert l.ts_embed(master.state,token)==0 and l.ts_layers(master.state,0,split,pos)==0
            C.memmove(l.ts_x(worker.state),l.ts_x(master.state),native.d*4)
            assert l.ts_layers(worker.state,split,native.layers,pos)==0
            C.memmove(l.ts_x(master.state),l.ts_x(worker.state),native.d*4)
            np.testing.assert_array_equal(actual,np.ctypeslib.as_array(l.ts_finish(master.state),(native.vocab,)))
        report.update(logit_positions=len(errors),logits_per_position=native.vocab,max_absolute_logit_error=max(errors),all_argmax_equal=True,full_shard_logits_bit_identical=True)
        results=[]
        for case in cases:
            start=time.monotonic();row=native.generate(case['prompt'],case['limit']);row.update(case=case['id'],host_seconds=time.monotonic()-start)
            results.append(row);write(a.output/'host-generations.json',results)
            print(case['id'],len(row['tokens']),repr(row['text'][:110]),flush=True)
        report['complete_generations']=len(results);report['artifacts']=json.loads((a.directory/'pack-report.json').read_text('utf-8'))
        report['source_sha256']={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'tools/pack_supra.py',ROOT/'tools/supra_reference.py',ROOT/'tools/check_supra_native.py',ROOT/'firmware/components/tinyllm/tinyllm.c',ROOT/'firmware/components/tinyllm/gpt2_tokenizer.c']}
        write(a.output/'host-report.json',report);print(json.dumps(report))
    finally:
        for x in (native,master,worker):x.close()


if __name__=='__main__':main()
