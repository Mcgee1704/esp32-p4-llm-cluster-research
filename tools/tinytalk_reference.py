"""Offline GPT-Neo feasibility reference; not a P4 firmware/model exporter.

Architecture reference: Hugging Face Transformers v4.57.1 GPTNeo (Apache-2.0).
Independent NumPy implementation: unscaled QK, global/local masks, learned
positions, LayerNorm, biased GELU MLP and tied output embedding.
"""
import json
import math
import pathlib
import struct
import sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.local/tooling/host'))
import numpy as np

REPOSITORY='TheREZOR/TinyTalk-2'
REVISION='2b55040281013975a4d97e3db8d634f78b31c6b1'
WEIGHTS_SHA256='40e10ee793e157f09fb94d2926db9aa3f81d42814249f1c1db023b7027f17567'


def audited_config():
    return {'model_type':'gpt_neo','architectures':['GPTNeoForCausalLM'],
            'activation_function':'gelu_new','hidden_size':256,'num_layers':8,
            'num_heads':16,'intermediate_size':None,'vocab_size':50257,
            'max_position_embeddings':2048,'window_size':256,
            'attention_layers':['global','local']*4,'layer_norm_epsilon':1e-5,
            'eos_token_id':50256,'bos_token_id':50256,'tie_word_embeddings':True,
            'attention_dropout':0,'embed_dropout':0,'resid_dropout':0}


def validate_config(config):
    if any(config.get(k)!=v for k,v in audited_config().items()):
        raise ValueError('Configuration is not the audited TinyTalk-2 GPT-Neo candidate')
    return {**config,'intermediate_size':1024}


def unique_object(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('Duplicate JSON key')
        result[k]=v
    return result


def read_tensors(raw):
    if len(raw)<8:raise ValueError('Truncated Safetensors')
    length=struct.unpack_from('<Q',raw)[0]
    if not 0<length<=1024*1024 or 8+length>len(raw):raise ValueError('Invalid header length')
    header=json.loads(raw[8:8+length],object_pairs_hook=unique_object)
    if not isinstance(header,dict):raise ValueError('Invalid tensor header')
    body=memoryview(raw)[8+length:];ranges=[];result={}
    for name,entry in header.items():
        if name=='__metadata__':continue
        if not isinstance(entry,dict) or set(entry)!={'dtype','shape','data_offsets'}:raise ValueError('Invalid tensor entry')
        shape=entry['shape'];offsets=entry['data_offsets']
        if entry['dtype']!='F32' or not isinstance(shape,list) or not shape or len(shape)>4:
            raise ValueError('Expected non-scalar F32 tensor')
        if any(type(n) is not int or not 0<n<=1<<31 for n in shape):raise ValueError('Invalid shape')
        if not isinstance(offsets,list) or len(offsets)!=2 or any(type(n) is not int for n in offsets):raise ValueError('Invalid offsets')
        start,end=offsets
        if not 0<=start<end<=len(body) or end-start!=math.prod(shape)*4:raise ValueError('Invalid tensor range')
        value=np.frombuffer(body[start:end],dtype='<f4').reshape(shape)
        if not np.isfinite(value).all():raise ValueError('Non-finite tensor')
        result[name]=value;ranges.append((start,end))
    ranges.sort()
    if not ranges or ranges[0][0]!=0 or ranges[-1][1]!=len(body) or any(a[1]!=b[0] for a,b in zip(ranges,ranges[1:])):
        raise ValueError('Tensor gaps, overlaps or unaccounted data')
    return result


def tensor_shapes(c):
    d=c['hidden_size'];h=c.get('intermediate_size') or 4*d;v=c['vocab_size']
    result={'transformer.wte.weight':(v,d),'transformer.wpe.weight':(c['max_position_embeddings'],d),
            'transformer.ln_f.weight':(d,),'transformer.ln_f.bias':(d,)}
    for i in range(c['num_layers']):
        p=f'transformer.h.{i}.'
        for norm in ['ln_1','ln_2']:
            for kind in ['weight','bias']:result[p+norm+'.'+kind]=(d,)
        for kind in ['q_proj','k_proj','v_proj','out_proj']:
            result[p+'attn.attention.'+kind+'.weight']=(d,d)
        result[p+'attn.attention.out_proj.bias']=(d,)
        result[p+'mlp.c_fc.weight']=(h,d);result[p+'mlp.c_fc.bias']=(h,)
        result[p+'mlp.c_proj.weight']=(d,h);result[p+'mlp.c_proj.bias']=(d,)
    return result


def load_checkpoint(directory):
    import hashlib
    directory=pathlib.Path(directory)
    c=validate_config(json.loads((directory/'config.json').read_text(encoding='utf-8')))
    raw=(directory/'model.safetensors').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=WEIGHTS_SHA256:raise ValueError('Pinned checkpoint hash mismatch')
    t=read_tensors(raw);expected=tensor_shapes(c)
    if set(t)!=set(expected) or any(t[n].shape!=s for n,s in expected.items()):raise ValueError('Tensor names/shapes do not match candidate')
    return c,t


def row_int8(tensors):
    """Simulate row-wise INT8 weights, immediately dequantized for NumPy math."""
    result={}
    for name,w in tensors.items():
        if w.ndim==1:result[name]=w;continue
        scale=np.max(np.abs(w),axis=1).astype('float32')/np.float32(127)
        scale[scale==0]=1
        quant=np.clip(np.rint(w/scale[:,None]),-127,127).astype('int8')
        result[name]=quant.astype('float32')*scale[:,None]
    return result


def memory_budget(c,tokenizer_bytes,context=256):
    if not 0<context<=min(256,c['max_position_embeddings']):raise ValueError('Unverified deployment context')
    shapes=tensor_shapes(c)
    count=sum(math.prod(s) for s in shapes.values())
    packed=sum(s[0]*(s[1]+4) if len(s)==2 else s[0]*4 for s in shapes.values())
    d=c['hidden_size'];h=c.get('intermediate_size') or 4*d;v=c['vocab_size']
    kv=2*c['num_layers']*context*d*4
    # Proposed compact tokenizer: tables in the blob, 8 bytes/token search index.
    work=(10*d+2*h)*4
    buffers=kv+work+c['num_heads']*context*4+v*4+v*8
    artifact=128+packed+tokenizer_bytes
    total=artifact+buffers+2*1024*1024
    return {'parameter_count':count,'non_token_embedding_parameters':count-v*d,
            'packed_weight_bytes':packed,'tokenizer_bytes':tokenizer_bytes,
            'artifact_bytes':artifact,'kv_bytes':kv,'work_vector_bytes':work,
            'psram_including_reserve_bytes':total,'planning_reserve_bytes':2*1024*1024,
            'flash_fits':artifact<=24*1024*1024,'psram_fits_with_reserve':total<=32*1024*1024,
            'classification':'Proposed full-vocabulary row-INT8 layout; not exported or measured on P4',
            'assumptions':'All 2048 learned position rows retained and quantized; norms/biases FP32; compact length/offset vocabulary and merge table; 8-byte/token search index; FP32 KV; allocator/stacks/network peaks not proven.'}


def layer_norm(x,w,b,eps):
    centered=x-np.mean(x,axis=-1,keepdims=True)
    return centered/np.sqrt(np.mean(centered*centered,axis=-1,keepdims=True)+np.float32(eps))*w+b


def gelu(x):
    return np.float32(.5)*x*(1+np.tanh(np.float32(math.sqrt(2/math.pi))*(x+np.float32(.044715)*x*x*x)))


def attend(q,keys,values,window):
    if window is not None:keys=keys[-window:];values=values[-window:]
    scores=np.einsum('hd,thd->ht',q,keys)
    scores-=scores.max(axis=-1,keepdims=True)
    probability=np.exp(scores);probability/=probability.sum(axis=-1,keepdims=True)
    return np.einsum('ht,thd->hd',probability,values)


class Reference:
    def __init__(self,config,tensors,context=256):
        self.c=config;self.t=tensors;self.context=min(context,config['max_position_embeddings'])
        shape=(self.context,config['num_heads'],config['hidden_size']//config['num_heads'])
        self.keys=[np.empty(shape,dtype='float32') for _ in range(config['num_layers'])]
        self.values=[np.empty(shape,dtype='float32') for _ in range(config['num_layers'])]
        self.reset()

    def reset(self):self.position=0

    def step(self,token):
        c=self.c;t=self.t;pos=self.position
        if type(token) is not int or not 0<=token<c['vocab_size'] or pos>=self.context:raise ValueError('Token/context out of range')
        x=t['transformer.wte.weight'][token]+t['transformer.wpe.weight'][pos]
        heads=c['num_heads'];width=c['hidden_size']//heads
        for i in range(c['num_layers']):
            p=f'transformer.h.{i}.';a=p+'attn.attention.'
            z=layer_norm(x,t[p+'ln_1.weight'],t[p+'ln_1.bias'],c['layer_norm_epsilon'])
            q=(t[a+'q_proj.weight']@z).reshape(heads,width)
            self.keys[i][pos]=(t[a+'k_proj.weight']@z).reshape(heads,width)
            self.values[i][pos]=(t[a+'v_proj.weight']@z).reshape(heads,width)
            window=c['window_size'] if c['attention_layers'][i]=='local' else None
            z=attend(q,self.keys[i][:pos+1],self.values[i][:pos+1],window).reshape(-1)
            x=x+t[a+'out_proj.weight']@z+t[a+'out_proj.bias']
            z=layer_norm(x,t[p+'ln_2.weight'],t[p+'ln_2.bias'],c['layer_norm_epsilon'])
            x=x+t[p+'mlp.c_proj.weight']@gelu(t[p+'mlp.c_fc.weight']@z+t[p+'mlp.c_fc.bias'])+t[p+'mlp.c_proj.bias']
        x=layer_norm(x,t['transformer.ln_f.weight'],t['transformer.ln_f.bias'],c['layer_norm_epsilon'])
        logits=t['transformer.wte.weight']@x
        if not np.isfinite(logits).all():raise ValueError('Non-finite output')
        self.position+=1
        return logits


def batch_forward(c,t,ids):
    """Separate full-sequence route for cache/mask consistency checks."""
    count=len(ids);d=c['hidden_size'];heads=c['num_heads'];width=d//heads
    if not count or count>c['max_position_embeddings'] or any(type(x) is not int or not 0<=x<c['vocab_size'] for x in ids):raise ValueError('Invalid input')
    x=t['transformer.wte.weight'][ids]+t['transformer.wpe.weight'][:count]
    delta=np.arange(count)[:,None]-np.arange(count)[None,:]
    for i in range(c['num_layers']):
        p=f'transformer.h.{i}.';a=p+'attn.attention.'
        z=layer_norm(x,t[p+'ln_1.weight'],t[p+'ln_1.bias'],c['layer_norm_epsilon'])
        q=(z@t[a+'q_proj.weight'].T).reshape(count,heads,width)
        k=(z@t[a+'k_proj.weight'].T).reshape(count,heads,width)
        v=(z@t[a+'v_proj.weight'].T).reshape(count,heads,width)
        scores=np.einsum('thd,shd->hts',q,k)
        allowed=delta>=0
        if c['attention_layers'][i]=='local':allowed&=delta<c['window_size']
        scores=np.where(allowed[None,:,:],scores,-np.inf)
        scores-=np.max(scores,axis=-1,keepdims=True)
        prob=np.exp(scores);prob/=prob.sum(axis=-1,keepdims=True)
        z=np.einsum('hts,shd->thd',prob,v).reshape(count,d)
        x=x+z@t[a+'out_proj.weight'].T+t[a+'out_proj.bias']
        z=layer_norm(x,t[p+'ln_2.weight'],t[p+'ln_2.bias'],c['layer_norm_epsilon'])
        x=x+gelu(z@t[p+'mlp.c_fc.weight'].T+t[p+'mlp.c_fc.bias'])@t[p+'mlp.c_proj.weight'].T+t[p+'mlp.c_proj.bias']
    x=layer_norm(x,t['transformer.ln_f.weight'],t['transformer.ln_f.bias'],c['layer_norm_epsilon'])
    return x@t['transformer.wte.weight'].T
