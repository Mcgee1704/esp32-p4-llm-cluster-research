"""Export audited GPT-Neo INT8 weights and byte BPE to P4GN0001 (offline)."""
import argparse
import hashlib
import json
import pathlib
import struct
import sys
import zlib
from tinytalk_reference import ROOT,REVISION,load_checkpoint,np,tensor_shapes


def tokenizer_blob(vocab,merges,ranges):
    offsets=[0];strings=b''.join(vocab)
    for piece in vocab:
        if not 0<len(piece)<=512:raise ValueError('Invalid byte piece')
        offsets.append(offsets[-1]+len(piece))
    if len({rank for a,b,rank,c in merges})!=len(merges):raise ValueError('Duplicate merge rank')
    records=sorted(merges)
    for a,b,rank,c in records:
        if not 0<=rank<len(merges) or not all(0<=n<len(vocab) for n in [a,b,c]) or vocab[c]!=vocab[a]+vocab[b]:raise ValueError('Invalid merge')
    raw=struct.pack('<8s4I',b'G2BP0001',len(vocab),len(merges),len(strings),len(ranges))
    raw+=struct.pack('<'+'I'*len(offsets),*offsets)+strings
    raw+=bytes((-len(raw))%4)
    raw+=b''.join(struct.pack('<4I',*r) for r in records)
    raw+=b''.join(struct.pack('<3I',*r) for r in ranges)
    return raw


def pack(c,tensors,vocab,merges,ranges,context=256):
    shapes=tensor_shapes(c)
    if set(tensors)!=set(shapes) or any(tensors[n].shape!=s for n,s in shapes.items()):raise ValueError('Tensor layout mismatch')
    d=c['hidden_size'];h=c.get('intermediate_size') or 4*d
    parts=[struct.pack('<3I',c['max_position_embeddings'],c['window_size'],c['eos_token_id'])]
    def matrix(name):
        w=tensors[name]
        if not np.isfinite(w).all():raise ValueError('Non-finite matrix')
        scale=np.max(np.abs(w),axis=1).astype('<f4')/np.float32(127);scale[scale==0]=1
        quant=np.clip(np.rint(w/scale[:,None]),-127,127).astype('int8')
        parts.extend([scale.tobytes(),quant.tobytes()])
    def vector(name):
        w=tensors[name]
        if not np.isfinite(w).all():raise ValueError('Non-finite vector')
        parts.append(w.astype('<f4').tobytes())
    matrix('transformer.wte.weight');matrix('transformer.wpe.weight')
    for i in range(c['num_layers']):
        p=f'transformer.h.{i}.';a=p+'attn.attention.'
        vector(p+'ln_1.weight');vector(p+'ln_1.bias')
        for name in ['q_proj','k_proj','v_proj','out_proj']:matrix(a+name+'.weight')
        vector(a+'out_proj.bias');vector(p+'ln_2.weight');vector(p+'ln_2.bias')
        matrix(p+'mlp.c_fc.weight');vector(p+'mlp.c_fc.bias')
        matrix(p+'mlp.c_proj.weight');vector(p+'mlp.c_proj.bias')
    vector('transformer.ln_f.weight');vector('transformer.ln_f.bias')
    weights=b''.join(parts);tok=tokenizer_blob(vocab,merges,ranges);body=weights+tok
    if not 0<context<=min(1024,c['max_position_embeddings']) or len(body)+128>24*1024*1024:raise ValueError('Context/partition limit exceeded')
    header=bytearray(128)
    struct.pack_into('<8s10I',header,0,b'P4GN0001',d,h,c['num_layers'],c['num_heads'],c['num_heads'],len(vocab),context,len(weights),len(tok),0)
    header[48:80]=hashlib.sha256(header[:48]+body).digest()
    struct.pack_into('<I',header,80,zlib.crc32(body))
    return bytes(header)+body


def unicode_ranges(directory):
    """Derive actual L/N/space classes from the pinned ByteLevel regex backend."""
    path=directory/'bytelevel-unicode-ranges.json'
    if path.exists():return json.loads(path.read_text(encoding='utf-8'))['ranges']
    sys.path.insert(0,str(ROOT/'.local/tooling/tinytalk-host'))
    from tokenizers.pre_tokenizers import ByteLevel
    import tokenizers
    pre=ByteLevel(add_prefix_space=False,use_regex=True);ranges=[];start=0;previous=0
    for value in range(0x110001):
        kind=0
        if value<0x110000 and not 0xd800<=value<=0xdfff:
            ch=chr(value)
            if len(pre.pre_tokenize_str('A'+ch))==1:kind=1
            elif len(pre.pre_tokenize_str('0'+ch))==1:kind=2
            elif len(pre.pre_tokenize_str('!'+ch))!=1:kind=3
        if kind!=previous:
            if previous:ranges.append((start,value-1,previous))
            start=value;previous=kind
    path.write_text(json.dumps({'backend':'tokenizers '+tokenizers.__version__+' ByteLevel','all_unicode_scalars_classified':True,'ranges':ranges},indent=2)+'\n',encoding='utf-8')
    return ranges


def real_tokenizer(directory):
    t=json.loads((directory/'tokenizer.json').read_text(encoding='utf-8'))
    if t['model']['type']!='BPE' or t['pre_tokenizer']['type']!='ByteLevel':raise ValueError('Unsupported tokenizer')
    alphabet=list(range(33,127))+list(range(161,173))+list(range(174,256))
    visible=alphabet.copy();extra=0
    for b in range(256):
        if b not in alphabet:alphabet.append(b);visible.append(256+extra);extra+=1
    inverse={chr(v):b for b,v in zip(alphabet,visible)}
    mapping=t['model']['vocab'];vocab=[None]*len(mapping)
    for text,index in mapping.items():vocab[index]=bytes(inverse[ch] for ch in text)
    merges=[]
    for rank,pair in enumerate(t['model']['merges']):
        a,b=pair.split() if isinstance(pair,str) else pair
        merges.append((mapping[a],mapping[b],rank,mapping[a+b]))
    return vocab,merges,unicode_ranges(directory)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=pathlib.Path)
    p.add_argument('--directory',type=pathlib.Path,default=ROOT/'.local/models'/('tinytalk2-'+REVISION[:12]))
    a=p.parse_args();c,t=load_checkpoint(a.directory)
    vocab,merges,ranges=real_tokenizer(a.directory)
    raw=pack(c,t,vocab,merges,ranges)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(raw)
    report={'format':'P4GN0001','bytes':len(raw),'weights_bytes':struct.unpack_from('<I',raw,36)[0],
            'tokenizer_bytes':struct.unpack_from('<I',raw,40)[0],'model_id':raw[48:80].hex(),
            'sha256':hashlib.sha256(raw).hexdigest(),'unicode_ranges':len(ranges),'unicode_backend':'tokenizers 0.22.1 ByteLevel',
            'vocabulary':len(vocab),'merges':len(merges),'context':256,'eos':c['eos_token_id']}
    a.output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
