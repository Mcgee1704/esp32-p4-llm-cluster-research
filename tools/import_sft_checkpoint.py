"""Read pinned data-only safetensors/SPM assets; never import upstream Python."""
import argparse
import hashlib
import json
import pathlib
import struct
import sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.local/tooling/host'))
import numpy as np

def varint(raw,pos):
    value=0
    for shift in range(0,70,7):
        if pos>=len(raw):raise ValueError('Truncated varint')
        b=raw[pos];pos+=1;value|=(b&127)<<shift
        if not b&128:return value,pos
    raise ValueError('Oversize varint')

def fields(raw):
    pos=0
    while pos<len(raw):
        tag,pos=varint(raw,pos);wire=tag&7
        if wire==2:
            n,pos=varint(raw,pos);end=pos+n;value=raw[pos:end];pos=end
        elif wire in (1,5):
            end=pos+(8 if wire==1 else 4);value=raw[pos:end];pos=end
        elif wire==0:
            value,pos=varint(raw,pos);end=pos
        else:raise ValueError('Unsupported protobuf wire type')
        if pos>len(raw):raise ValueError('Truncated protobuf field')
        yield tag>>3,wire,value

def tokenizer(raw):
    pieces=[]
    for number,wire,value in fields(raw):
        if number!=1:continue
        if wire!=2:raise ValueError('Invalid piece')
        text=None;score=b'\0'*4
        for n,w,v in fields(value):
            if n==1 and w==2:text=v.decode('utf-8').replace('\u2581',' ').encode('utf-8')
            elif n==2 and w==5:score=v
        if not text or b'\0' in text or not np.isfinite(struct.unpack('<f',score)[0]):raise ValueError('Invalid tokenizer piece')
        # llama2.c tokenizer.bin export convention for BOS/EOS display pieces.
        if len(pieces) in (1,2):text=b'\n'+text+b'\n'
        pieces.append((text,score))
    if len(pieces)!=32000:raise ValueError('Expected Llama 2 vocabulary')
    return struct.pack('<I',max(len(t) for t,s in pieces))+b''.join(s+struct.pack('<I',len(t))+t for t,s in pieces)

def load_tensors(raw):
    if len(raw)<8:raise ValueError('Truncated safetensors')
    n=int.from_bytes(raw[:8],'little')
    if not 0<n<=1024*1024 or 8+n>len(raw):raise ValueError('Invalid header length')
    header=json.loads(raw[8:8+n]);body=raw[8+n:];result={};ranges=[]
    if header.get('__metadata__',{}).get('tok_embeddings.weight')!='output.weight':
        raise ValueError('Unverified tied-embedding alias')
    for name,entry in header.items():
        if name=='__metadata__':continue
        shape=entry['shape'];start,end=entry['data_offsets']
        if entry['dtype']!='BF16' or any(not isinstance(x,int) or x<=0 for x in shape):raise ValueError('Unsupported tensor')
        if not 0<=start<end<=len(body) or end-start!=int(np.prod(shape))*2:raise ValueError('Tensor length invalid')
        values=(np.frombuffer(body[start:end],dtype='<u2').astype('<u4')<<16).view('<f4').reshape(shape)
        if not np.isfinite(values).all():raise ValueError('Non-finite tensor')
        result[name]=values;ranges.append((start,end))
    ranges.sort()
    if ranges[0][0]!=0 or ranges[-1][1]!=len(body) or any(a[1]!=b[0] for a,b in zip(ranges,ranges[1:])):
        raise ValueError('Tensor gaps or overlaps')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=pathlib.Path)
    a=p.parse_args();root=a.directory
    c=json.loads((root/'config.json').read_text(encoding='utf-8'))
    expected={'dim':288,'n_layers':6,'n_heads':6,'n_kv_heads':6,'vocab_size':32000,'max_seq_len':256,'multiple_of':32,'norm_eps':1e-5}
    if any(c.get(k)!=v for k,v in expected.items()):raise ValueError('Configuration is not the audited candidate')
    t=load_tensors((root/'model.safetensors').read_bytes());arrays=[];used=[]
    def add(name,shape):
        value=t[name]
        if value.shape!=shape:raise ValueError('Wrong shape: '+name)
        arrays.append(value);used.append(name)
    add('output.weight',(32000,288))
    for kind,shape in [('attention_norm.weight',(288,)),('attention.wq.weight',(288,288)),('attention.wk.weight',(288,288)),('attention.wv.weight',(288,288)),('attention.wo.weight',(288,288)),('ffn_norm.weight',(288,)),('feed_forward.w1.weight',(768,288)),('feed_forward.w2.weight',(288,768)),('feed_forward.w3.weight',(768,288))]:
        values=[]
        for i in range(6):
            name=f'layers.{i}.{kind}';v=t[name]
            if v.shape!=shape:raise ValueError('Wrong layer shape')
            values.append(v);used.append(name)
        arrays.append(np.stack(values))
    add('norm.weight',(288,))
    if set(used)!=set(t):raise ValueError('Unexpected tensors')
    raw=struct.pack('<7i',288,768,6,6,6,32000,256)+b''.join(v.astype('<f4').tobytes() for v in arrays)+bytes(256*48*4)
    tok=tokenizer((root/'tokenizer.model').read_bytes())
    reference=(ROOT/'.local/models/tokenizer.bin').read_bytes()
    if tok!=reference:raise ValueError('Tokenizer differs from verified runtime vocabulary')
    (root/'imported-legacy.bin').write_bytes(raw);(root/'verified-tokenizer.bin').write_bytes(tok)
    report={'tensor_count':len(t),'legacy_sha256':hashlib.sha256(raw).hexdigest(),'tokenizer_identical_to_baseline':True,
            'tokenizer_sha256':hashlib.sha256(tok).hexdigest(),'external_code_executed':False}
    (root/'import-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
