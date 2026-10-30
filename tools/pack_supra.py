"""Offline, data-only HF Llama/Qwen3 -> full-vocabulary row-INT4 P4QS shards."""
import argparse
import hashlib
import json
import pathlib
import struct
import sys
import zlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.local/tooling/host'))
import numpy as np
from pack_gptneo import tokenizer_blob,unicode_ranges


def quantize(w):
    w=np.asarray(w,dtype='<f4')
    if w.ndim!=2 or w.shape[1]%4 or not np.isfinite(w).all():raise ValueError('Invalid matrix')
    scales=np.max(np.abs(w),axis=1)/np.float32(7);scales[scales==0]=1
    q=np.clip(np.rint(w/scales[:,None]),-7,7).astype('int8').view('uint8')&15
    packed=q[:,::2]|(q[:,1::2]<<4)
    return scales.astype('<f4').tobytes()+packed.tobytes()


def tokenizer_v2(vocab,merges,ranges,specials,digits=False):
    if not specials or len(specials)>64 or len(set(specials))!=len(specials):raise ValueError('Invalid special tokens')
    if any(i<0 or i>=len(vocab) or b'\0' in vocab[i] for i in specials):raise ValueError('Invalid special token')
    if any(i in specials for a,b,r,c in merges for i in (a,b,c)):raise ValueError('Special merge')
    raw=tokenizer_blob(vocab,merges,ranges)
    return b'G2BP0002'+raw[8:24]+struct.pack('<2I',int(digits),len(specials))+struct.pack('<'+'I'*len(specials),*specials)+raw[24:]


def shape_map(c):
    d=c['hidden_size'];h=c['intermediate_size'];k=c['num_key_value_heads']*(d//c['num_attention_heads'])
    result={'model.embed_tokens.weight':(c['vocab_size'],d),'model.norm.weight':(d,)}
    for i in range(c['num_hidden_layers']):
        p=f'model.layers.{i}.'
        for n,shape in [('input_layernorm',(d,)),('post_attention_layernorm',(d,)),
                        ('self_attn.q_proj',(d,d)),('self_attn.k_proj',(k,d)),('self_attn.v_proj',(k,d)),
                        ('self_attn.o_proj',(d,d)),('mlp.gate_proj',(h,d)),('mlp.down_proj',(d,h)),('mlp.up_proj',(h,d))]:
            result[p+n+'.weight']=shape
        if c['architectures']==['Qwen3ForCausalLM']:
            result[p+'self_attn.q_norm.weight']=(d//c['num_attention_heads'],)
            result[p+'self_attn.k_norm.weight']=(d//c['num_attention_heads'],)
    return result


def load_tensors(path):
    raw=path.read_bytes();n=int.from_bytes(raw[:8],'little')
    if not 2<=n<=1048576 or 8+n>len(raw):raise ValueError('Invalid safetensors header')
    meta=json.loads(raw[8:8+n]);body=memoryview(raw)[8+n:];out={};spans=[]
    for name,item in meta.items():
        if name=='__metadata__':continue
        dt=item['dtype'];shape=item['shape'];start,end=item['data_offsets']
        width={'BF16':2,'F16':2,'F32':4}.get(dt)
        if width is None or any(type(x)!=int or x<=0 for x in shape) or not 0<=start<end<=len(body) or end-start!=int(np.prod(shape))*width:raise ValueError('Invalid tensor bounds')
        a=np.frombuffer(body[start:end],dtype='<u2' if dt=='BF16' else '<f2' if dt=='F16' else '<f4')
        a=(a.astype('<u4')<<16).view('<f4') if dt=='BF16' else a.astype('<f4')
        if not np.isfinite(a).all():raise ValueError('Non-finite tensor')
        out[name]=a.reshape(shape);spans.append((start,end))
    spans.sort()
    if not spans or spans[0][0] or spans[-1][1]!=len(body) or any(a[1]!=b[0] for a,b in zip(spans,spans[1:])):raise ValueError('Tensor gaps/overlaps')
    return out,meta.get('__metadata__',{})


def load_source(directory):
    # Explicit source choice matters: adding an F32 file must not silently
    # replace the author's F16 control or change the pinned experiment.
    sources={
        'SupraLabs/Supra1.5-50M-Instruct-exp':('f0566e6be9f1cd3530fe004ce4e56a5c4148bf73','model.safetensors','5201168326dff0dce0be429b56c6bc352789e56bdcf8296b071b41fd895d3672'),
        'SupraLabs/Supra2-100M-Instruct':('2c90ade6ab47b910f48d0157a3e4c421d6311ed5','Supra2-100M-SFT-F16.gguf','f88228c3dcc13b5ee2333cbb6fc2416de908e5b8adabd39bf9ee4378f28451eb')}
    try:metadata=json.loads((directory/'source-metadata.json').read_text('utf-8'))
    except (OSError,ValueError) as e:raise ValueError('Missing or invalid source metadata') from e
    spec=sources.get(metadata.get('repository'))
    if spec is None or metadata.get('revision')!=spec[0]:raise ValueError('Source is not an admitted pinned candidate')
    files=metadata.get('files',[])
    if not {'config.json','tokenizer.json'}.issubset({x['file'] for x in files}):raise ValueError('Pinned companion inventory missing')
    for entry in files:
        name=entry['file']
        if pathlib.Path(name).name!=name or name not in {'config.json','tokenizer.json','tokenizer_config.json','generation_config.json','README.md','chat_template.jinja'}:raise ValueError('Unexpected companion path')
        if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Companion SHA256 mismatch: '+name)
    path=directory/spec[1]
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=spec[2]:raise ValueError('Pinned weight file missing or SHA256 mismatch')
    if path.suffix=='.safetensors':return load_tensors(path)
    from supra_gguf import load_author_qwen
    c=json.loads((directory/'config.json').read_text('utf-8'))
    return load_author_qwen(path,c)


def tokenizer(directory):
    t=json.loads((directory/'tokenizer.json').read_text('utf-8'));pre=t['pre_tokenizer'];digits=False
    if pre['type']=='Sequence':
        seq=pre['pretokenizers']
        if len(seq)!=2 or seq[0]!={'type':'Digits','individual_digits':True}:raise ValueError('Unknown digit splitter')
        pre=seq[1];digits=True
    if t.get('normalizer') is not None or pre['type']!='ByteLevel' or pre.get('add_prefix_space') or not pre.get('use_regex'):raise ValueError('Unsupported tokenizer normalization')
    if t['model']['type']!='BPE' or t['model'].get('dropout') or t['model'].get('byte_fallback'):raise ValueError('Unsupported BPE mode')
    alphabet=list(range(33,127))+list(range(161,173))+list(range(174,256));visible=alphabet.copy();extra=0
    for b in range(256):
        if b not in alphabet:alphabet.append(b);visible.append(256+extra);extra+=1
    inverse={chr(v):b for b,v in zip(alphabet,visible)};mapping=t['model']['vocab'];vocab=[None]*len(mapping)
    specials=[];special_text={}
    for x in t['added_tokens']:
        if not x['special'] or any(x.get(k) for k in ('single_word','lstrip','rstrip','normalized')):raise ValueError('Unsupported special matching')
        specials.append(x['id']);special_text[x['id']]=x['content'].encode('utf-8')
    for text,index in mapping.items():vocab[index]=special_text[index] if index in special_text else bytes(inverse[ch] for ch in text)
    merges=[]
    for rank,pair in enumerate(t['model']['merges']):
        a,b=pair.split() if isinstance(pair,str) else pair
        merges.append((mapping[a],mapping[b],rank,mapping[a+b]))
    return vocab,merges,unicode_ranges(directory),specials,digits


def permute(w,heads):
    """HF rotate-half row order -> adjacent complex pairs used by portable C."""
    shape=w.shape;hs=shape[0]//heads
    return w.reshape(heads,2,hs//2,*shape[1:]).swapaxes(1,2).reshape(shape)


def pack(c,tensors,vocab,merges,ranges,specials,split=4,context=256,digits=False):
    arch={'LlamaForCausalLM':1,'Qwen3ForCausalLM':2}.get(c['architectures'][0])
    if not arch or not c['tie_word_embeddings'] or c.get('attention_bias',False) or c.get('mlp_bias',False):raise ValueError('Unsupported architecture')
    shapes=shape_map(c);t=dict(tensors)
    if 'lm_head.weight' in t:
        if not np.array_equal(t.pop('lm_head.weight'),t['model.embed_tokens.weight']):raise ValueError('Untied output')
    if set(t)!=set(shapes) or any(t[n].shape!=s for n,s in shapes.items()):raise ValueError('Tensor inventory mismatch')
    d=c['hidden_size'];h=c['intermediate_size'];layers=c['num_hidden_layers'];heads=c['num_attention_heads'];kv=c['num_key_value_heads']
    if not 0<split<layers or len(vocab)!=c['vocab_size'] or not 0<context<=min(1024,c['max_position_embeddings']):raise ValueError('Invalid context/split/vocab')
    rp=c.get('rope_parameters',{});theta=rp.get('rope_theta',c.get('rope_theta',10000.))
    if rp.get('rope_type','default') not in ('default','linear') or rp.get('factor',1.)!=1.:raise ValueError('Unsupported RoPE scaling')
    tok=tokenizer_v2(vocab,merges,ranges,specials,digits)
    emb=quantize(t['model.embed_tokens.weight']);norm=t['model.norm.weight'].astype('<f4').tobytes();parts=[]
    for i in range(layers):
        p=f'model.layers.{i}.';v=[t[p+n+'.weight'].astype('<f4').tobytes() for n in ['input_layernorm','post_attention_layernorm']]
        for name in ['self_attn.q_proj','self_attn.k_proj','self_attn.v_proj','self_attn.o_proj','mlp.gate_proj','mlp.down_proj','mlp.up_proj']:
            w=t[p+name+'.weight']
            if name in ['self_attn.q_proj','self_attn.k_proj']:w=permute(w,heads if name.endswith('q_proj') else kv)
            v.append(quantize(w))
        if arch==2:
            v.extend(permute(t[p+'self_attn.'+n+'_norm.weight'],1).astype('<f4').tobytes() for n in ['q','k'])
        parts.append(b''.join(v))
    eos=c['eos_token_id'];extra=next((i for i in specials if vocab[i]==b'<|im_end|>'),0xffffffff)
    canonical=struct.pack('<11I2f',d,h,layers,heads,kv,len(vocab),context,arch,4,eos,extra,c['rms_norm_eps'],theta)
    identity=hashlib.sha256(canonical+emb+b''.join(parts)+norm+tok).digest();out={}
    for name,role,first,end in [('full',0,0,layers),('coordinator',1,0,split),('worker',2,split,layers)]:
        meta=bytearray(128);meta[:32]=identity
        struct.pack_into('<7I2f2I',meta,32,1,arch,first,end,4,eos,extra,c['rms_norm_eps'],theta,int(digits),c['max_position_embeddings'])
        weights=bytes(meta)+(emb if role!=2 else b'')+b''.join(parts[first:end])+(norm if role!=2 else b'')
        tokenizer_bytes=tok if role!=2 else b'';body=weights+tokenizer_bytes;header=bytearray(128)
        struct.pack_into('<8s10I',header,0,b'P4QS0001',d,h,layers,heads,kv,len(vocab),context,len(weights),len(tokenizer_bytes),role)
        header[48:80]=hashlib.sha256(header[:48]+body).digest();struct.pack_into('<I',header,80,zlib.crc32(body));out[name]=bytes(header)+body
    return out


def synthetic():
    c=dict(architectures=['LlamaForCausalLM'],hidden_size=8,intermediate_size=16,num_hidden_layers=2,num_attention_heads=2,
           num_key_value_heads=1,vocab_size=260,max_position_embeddings=16,rms_norm_eps=1e-6,tie_word_embeddings=True,eos_token_id=258)
    rng=np.random.default_rng(871);t={n:rng.normal(0,.15,s).astype('float32') for n,s in shape_map(c).items()}
    for n,a in t.items():
        if 'norm' in n:a[:]=1
    v=[bytes([x]) for x in range(256)]+[b'ab',b'<s>',b'</s>',b'<pad>'];m=[(97,98,0,256)]
    r=[(9,13,3),(32,32,3),(48,57,2),(65,90,1),(97,122,1)]
    return c,t,v,m,r,[257,258,259]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=pathlib.Path);p.add_argument('--split',type=int,default=4);p.add_argument('--context',type=int,default=256)
    a=p.parse_args();c=json.loads((a.directory/'config.json').read_text('utf-8'));t,metadata=load_source(a.directory)
    v,m,r,s,d=tokenizer(a.directory);artifacts=pack(c,t,v,m,r,s,a.split,a.context,d);report={}
    for role,raw in artifacts.items():
        path=a.directory/('supra-'+role+'.p4qs');path.write_bytes(raw)
        report[role]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'artifact_id':raw[48:80].hex(),'model_id':raw[128:160].hex(),'weights_bytes':struct.unpack_from('<I',raw,36)[0],'tokenizer_bytes':struct.unpack_from('<I',raw,40)[0]}
    from supra_storage import wrap,unwrap
    for role,raw in artifacts.items():
        if role!='full':
            compressed=wrap(raw);assert unwrap(compressed)==raw
            (a.directory/('supra-'+role+'.p4zl')).write_bytes(compressed)
            report[role]['compressed_bytes']=len(compressed);report[role]['compressed_sha256']=hashlib.sha256(compressed).hexdigest()
    (a.directory/'pack-report.json').write_text(json.dumps(report,indent=2)+'\n','utf-8');print(json.dumps(report))


if __name__=='__main__':main()
