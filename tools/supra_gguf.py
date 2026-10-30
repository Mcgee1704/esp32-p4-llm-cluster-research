"""Strict F16/F32 GGUF v3 data reader for the pinned author Qwen3 export."""
import struct
from pack_supra import np,shape_map


def read_gguf(raw):
    pos=0
    def take(n):
        nonlocal pos
        if n<0 or n>len(raw)-pos:raise ValueError('Truncated GGUF')
        v=memoryview(raw)[pos:pos+n];pos+=n;return v
    def number(fmt):return struct.unpack('<'+fmt,take(struct.calcsize('<'+fmt)))[0]
    def string():
        n=number('Q')
        if n>4*1024*1024:raise ValueError('GGUF string too large')
        try:return bytes(take(n)).decode('utf-8')
        except UnicodeDecodeError as e:raise ValueError('Invalid GGUF UTF-8') from e
    def value(kind,depth=0):
        formats={0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}
        if kind in formats:return number(formats[kind])
        if kind==8:return string()
        if kind==9 and depth<2:
            typ=number('I');n=number('Q')
            if n>100000:raise ValueError('GGUF array too large')
            return [value(typ,depth+1) for _ in range(n)]
        raise ValueError('Unsupported GGUF metadata type')
    if bytes(take(4))!=b'GGUF' or number('I')!=3:raise ValueError('Expected GGUF v3')
    count=number('Q');kv=number('Q')
    if not 0<count<=1000 or kv>2000:raise ValueError('Invalid GGUF inventory size')
    meta={}
    for _ in range(kv):
        name=string()
        if name in meta:raise ValueError('Duplicate GGUF metadata')
        meta[name]=value(number('I'))
    records=[];names=set()
    for _ in range(count):
        name=string();nd=number('I')
        if not 1<=nd<=2 or name in names:raise ValueError('Unsupported or duplicate GGUF tensor')
        dims=[number('Q') for _ in range(nd)];typ=number('I');off=number('Q');names.add(name)
        if typ not in (0,1) or any(not 0<x<=65536 for x in dims):raise ValueError('Only finite F16/F32 matrices/vectors allowed')
        records.append((name,tuple(reversed(dims)),typ,off))
    align=meta.get('general.alignment',32)
    if type(align)!=int or align<4 or align>4096 or align&(align-1):raise ValueError('Invalid GGUF alignment')
    base=(pos+align-1)//align*align;spans=[];out={}
    for name,shape,typ,offset in records:
        n=int(np.prod(shape))*(4 if typ==0 else 2);start=base+offset;end=start+n
        if offset%align or not base<=start<end<=len(raw):raise ValueError('GGUF tensor bounds invalid')
        a=np.frombuffer(raw,dtype='<f4' if typ==0 else '<f2',count=int(np.prod(shape)),offset=start).astype('<f4').reshape(shape)
        if not np.isfinite(a).all():raise ValueError('Non-finite GGUF tensor')
        spans.append((start,end));out[name]=a
    spans.sort()
    if any(a[1]>b[0] for a,b in zip(spans,spans[1:])) or len(raw)-spans[-1][1]>=align:raise ValueError('GGUF overlap/trailing data')
    return out,meta


def load_author_qwen(path,c):
    t,meta=read_gguf(path.read_bytes())
    required={'general.architecture':'qwen3','qwen3.block_count':c['num_hidden_layers'],'qwen3.embedding_length':c['hidden_size'],
              'qwen3.feed_forward_length':c['intermediate_size'],'qwen3.attention.head_count':c['num_attention_heads'],
              'qwen3.attention.head_count_kv':c['num_key_value_heads']}
    if any(meta.get(k)!=v for k,v in required.items()):raise ValueError('GGUF model/config mismatch')
    names={'token_embd.weight':'model.embed_tokens.weight','output_norm.weight':'model.norm.weight'}
    suffix={'attn_norm':'input_layernorm','ffn_norm':'post_attention_layernorm','attn_q':'self_attn.q_proj',
            'attn_k':'self_attn.k_proj','attn_v':'self_attn.v_proj','attn_output':'self_attn.o_proj',
            'ffn_gate':'mlp.gate_proj','ffn_down':'mlp.down_proj','ffn_up':'mlp.up_proj',
            'attn_q_norm':'self_attn.q_norm','attn_k_norm':'self_attn.k_norm'}
    for i in range(c['num_hidden_layers']):
        for a,b in suffix.items():names[f'blk.{i}.{a}.weight']=f'model.layers.{i}.{b}.weight'
    if set(t)!=set(names):raise ValueError('GGUF tensor names differ from audited inventory')
    result={names[n]:a for n,a in t.items()};shapes=shape_map(c)
    if any(result[n].shape!=shape for n,shape in shapes.items()):raise ValueError('GGUF shape/config mismatch')
    return result,{'source_format':'author F16 GGUF','tensor_count':len(result),'architecture':meta['general.architecture']}
