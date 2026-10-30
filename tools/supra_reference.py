"""Independent source-layout HF Llama/Qwen3 float32 oracle; no model code import."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
from pack_supra import np,shape_map


def row_int4(tensors):
    result={}
    for name,w in tensors.items():
        if w.ndim==2:
            scale=np.max(np.abs(w),axis=1)/np.float32(7);scale[scale==0]=1
            result[name]=np.clip(np.rint(w/scale[:,None]),-7,7).astype('float32')*scale[:,None]
        else:result[name]=w.copy()
    return result


class Reference:
    def __init__(self,c,tensors,context=256,observer=None):
        self.c=c;self.t=tensors;self.position=0;self.observer=observer
        self.k=np.zeros((c['num_hidden_layers'],context,c['num_key_value_heads'],c['hidden_size']//c['num_attention_heads']),dtype='float32')
        self.v=np.zeros_like(self.k);self.context=context

    def linear(self,name,x):
        if self.observer is not None:self.observer(name,x.copy())
        return self.t[name]@x

    def rms(self,x,w):
        return x/np.sqrt(np.mean(x*x,axis=-1,keepdims=True)+np.float32(self.c['rms_norm_eps']))*w

    def step(self,token):
        pos=self.position
        if pos>=self.context:raise ValueError('Context exceeded')
        c=self.c;t=self.t;d=c['hidden_size'];heads=c['num_attention_heads'];kv=c['num_key_value_heads'];hs=d//heads
        theta=c.get('rope_parameters',{}).get('rope_theta',c.get('rope_theta',10000.))
        angle=np.float32(pos)/np.power(np.float32(theta),np.arange(0,hs,2,dtype='float32')/np.float32(hs))
        co=np.concatenate((np.cos(angle),np.cos(angle)));sn=np.concatenate((np.sin(angle),np.sin(angle)))
        def rope(x):return x*co+np.concatenate((-x[:,hs//2:],x[:,:hs//2]),axis=-1)*sn
        x=t['model.embed_tokens.weight'][token].copy()
        for i in range(c['num_hidden_layers']):
            p=f'model.layers.{i}.';norm=self.rms(x,t[p+'input_layernorm.weight'])
            q=(self.linear(p+'self_attn.q_proj.weight',norm)).reshape(heads,hs)
            k=(self.linear(p+'self_attn.k_proj.weight',norm)).reshape(kv,hs)
            v=(self.linear(p+'self_attn.v_proj.weight',norm)).reshape(kv,hs)
            if c['architectures']==['Qwen3ForCausalLM']:
                q=self.rms(q,t[p+'self_attn.q_norm.weight']);k=self.rms(k,t[p+'self_attn.k_norm.weight'])
            q=rope(q);self.k[i,pos]=rope(k);self.v[i,pos]=v
            keys=np.repeat(self.k[i,:pos+1],heads//kv,axis=1)
            values=np.repeat(self.v[i,:pos+1],heads//kv,axis=1)
            scores=np.einsum('hd,thd->ht',q,keys)/np.sqrt(np.float32(hs));scores-=scores.max(axis=-1,keepdims=True)
            attention=np.exp(scores);attention/=attention.sum(axis=-1,keepdims=True)
            out=np.einsum('ht,thd->hd',attention,values).reshape(d)
            x+=self.linear(p+'self_attn.o_proj.weight',out)
            norm=self.rms(x,t[p+'post_attention_layernorm.weight']);gate=self.linear(p+'mlp.gate_proj.weight',norm)
            x+=self.linear(p+'mlp.down_proj.weight',(gate/(1+np.exp(-gate)))*self.linear(p+'mlp.up_proj.weight',norm))
        self.position+=1
        return self.linear('model.embed_tokens.weight',self.rms(x,t['model.norm.weight']))
