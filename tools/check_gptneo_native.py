"""Verify actual P4GN C core/tokenizer against local TinyTalk references."""
import argparse
import ctypes as C
import hashlib
import json
import pathlib
import random
import struct
import sys
from tinytalk_reference import ROOT,REVISION,load_checkpoint,row_int8,Reference,np
from pack_gptneo import real_tokenizer
from evaluate_tinytalk import prompt


class Native:
    def __init__(self,path):
        self.raw=pathlib.Path(path).read_bytes();self.blob=C.create_string_buffer(self.raw)
        self.d,self.h,self.layers,self.heads,self.kv,self.vocab,self.context=struct.unpack_from('<7I',self.raw,8)
        self.lib=C.CDLL(str(ROOT/'.local/build/tinyllm.dll'));l=self.lib
        l.ts_open.argtypes=[C.c_void_p,C.c_size_t];l.ts_open.restype=C.c_void_p
        for name in ['ts_close','ts_reset','ts_argmax']:getattr(l,name).argtypes=[C.c_void_p]
        l.ts_embed.argtypes=[C.c_void_p,C.c_int];l.ts_layers.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int]
        l.ts_finish.argtypes=[C.c_void_p];l.ts_finish.restype=C.POINTER(C.c_float)
        l.ts_encode.argtypes=[C.c_void_p,C.c_char_p,C.POINTER(C.c_int),C.c_int]
        l.ts_decode.argtypes=[C.c_void_p,C.c_int,C.c_int];l.ts_decode.restype=C.c_void_p
        l.ts_decode_length.argtypes=[C.c_void_p,C.c_int,C.c_int];l.ts_decode_length.restype=C.c_size_t
        l.ts_is_eos.argtypes=[C.c_void_p,C.c_int]
        self.state=l.ts_open(self.blob,len(self.raw))
        if not self.state:raise ValueError('Native model rejected')

    def close(self):
        if self.state:self.lib.ts_close(self.state);self.state=None

    def encode(self,text):
        out=(C.c_int*4096)();n=self.lib.ts_encode(self.state,text.encode('utf-8'),out,len(out))
        if n<0:raise ValueError('Encoding failed')
        return list(out[:n])

    def piece(self,token):
        n=self.lib.ts_decode_length(self.state,0,token)
        return C.string_at(self.lib.ts_decode(self.state,0,token),n)

    def forward(self,token,position,finish=True):
        if self.lib.ts_embed(self.state,int(token)) or self.lib.ts_layers(self.state,0,self.layers,position):raise ValueError('Native forward rejected')
        if finish:return np.ctypeslib.as_array(self.lib.ts_finish(self.state),(self.vocab,)).copy()

    def generate(self,text,limit):
        ids=self.encode(text)
        if not ids or len(ids)+limit-1>self.context:raise ValueError('Context exceeded')
        self.lib.ts_reset(self.state);result=[];pieces=[];ended=False
        for pos,token in enumerate(ids):logits=self.forward(token,pos,finish=pos==len(ids)-1)
        for i in range(limit):
            token=int(np.argmax(logits))
            if self.lib.ts_is_eos(self.state,token):ended=True;break
            result.append(token);pieces.append(self.piece(token))
            if i+1<limit:logits=self.forward(token,len(ids)+i)
        return {'tokens':result,'text':b''.join(pieces).decode('utf-8','replace'),'eos':ended,'prompt_tokens':ids}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=pathlib.Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    directory=ROOT/'.local/models'/('tinytalk2-'+REVISION[:12]);model=ROOT/'.local/models/tinytalk2.p4gn'
    sys.path.insert(0,str(ROOT/'.local/tooling/tinytalk-host'))
    from tokenizers import Tokenizer
    tok=Tokenizer.from_file(str(directory/'tokenizer.json'))
    vocab,merges,ranges=real_tokenizer(directory)
    native=Native(model)
    try:
        for token,piece in enumerate(vocab):
            if native.piece(token)!=piece:raise AssertionError(('decode',token))
        protocol=json.loads((ROOT/'data/tinytalk2-host-2026-10-29/protocol.json').read_text(encoding='utf-8'))
        probes=[prompt(case) for case in protocol['cases']]
        probes+=['','abc ababababc',"I'm you're WE'RE they've IT'S he'll I'd",' \t\n\r  word  \n\n tail\t',
                 'Grüße! café naïve Straße １２３ 一二三 🙂🚀','a<|endoftext|>b<|endoftext|>',
                 ''.join(chr(x) for x in range(1,128))]
        for lo,hi,kind in ranges:
            probes.append('A'+chr(lo)+chr(hi)+'0! x')
        rng=random.Random(194);alphabet='abAB09 !?\t\n\r\u00a0éüß中🙂\u0301\u2009'
        probes+=[''.join(rng.choice(alphabet) for _ in range(rng.randrange(1,80))) for _ in range(250)]
        for index,text in enumerate(probes):
            expected=tok.encode(text,add_special_tokens=False).ids;actual=native.encode(text)
            if actual!=expected:raise AssertionError(('encode',index,repr(text),actual,expected))
        c,t=load_checkpoint(directory);reference=Reference(c,row_int8(t))
        ids=tok.encode(prompt(protocol['cases'][0]),add_special_tokens=False).ids
        native.lib.ts_reset(native.state);errors=[]
        for pos,token in enumerate(ids):
            actual=native.forward(token,pos);expected=reference.step(int(token))
            errors.append(float(np.max(np.abs(actual-expected))))
            if errors[-1]>.002 or int(np.argmax(actual))!=int(np.argmax(expected)):raise AssertionError(('logits',pos,errors[-1]))
        old=json.loads((ROOT/'data/tinytalk2-host-2026-10-29/results.json').read_text(encoding='utf-8'))
        runs=[]
        for case in protocol['cases']:
            row=native.generate(prompt(case),case['limit']);row['case']=case['id']
            expected=next(r for r in old if r['variant']=='row-int8-simulation' and r['case']==case['id'])
            if row['tokens']!=expected['tokens'] or row['eos']!=expected['eos_observed']:raise AssertionError(('generation',case['id'],row))
            runs.append(row)
        report={'vocabulary_decode_tokens_checked':len(vocab),'encoding_probes':len(probes),
                'unicode_class_ranges':len(ranges),'logit_positions':len(ids),'logits_per_position':native.vocab,
                'max_absolute_logit_error':max(errors),'tolerance':.002,'all_argmax_equal':True,
                'complete_generations_equal_to_numpy':len(runs),'model_sha256':hashlib.sha256(model.read_bytes()).hexdigest(),
                'scope':'Native C, not P4 hardware; real weights and full byte BPE',
                'source_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['tools/check_gptneo_native.py','tools/pack_gptneo.py','firmware/components/tinyllm/tinyllm.c','firmware/components/tinyllm/gpt2_tokenizer.c']}}
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        (args.output/'generations.json').write_text(json.dumps(runs,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report))
    finally:native.close()


if __name__=='__main__':main()
