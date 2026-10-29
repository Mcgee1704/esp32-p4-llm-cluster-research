"""Independent NumPy quantized forward versus the portable C implementation."""
import argparse
import ctypes as C
import json
import pathlib
from import_sft_checkpoint import load_tensors, np, ROOT

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=pathlib.Path);p.add_argument('output',type=pathlib.Path)
    a=p.parse_args();t=load_tensors((a.directory/'model.safetensors').read_bytes());weights={}
    for name,w in t.items():
        if w.ndim==2:
            scale=np.max(np.abs(w),axis=1,keepdims=True)/np.float32(127);scale[scale==0]=1
            weights[name]=np.clip(np.rint(w/scale),-127,127).astype(np.int8).astype(np.float32)*scale
        else:weights[name]=w
    lib=C.CDLL(str(ROOT/'.local/build/tinyllm.dll'));data=(a.directory/'stories15M-sft.p4lm').read_bytes();blob=C.create_string_buffer(data)
    lib.ts_open.argtypes=[C.c_void_p,C.c_size_t];lib.ts_open.restype=C.c_void_p
    for name in ['ts_close','ts_reset']:getattr(lib,name).argtypes=[C.c_void_p]
    lib.ts_embed.argtypes=[C.c_void_p,C.c_int];lib.ts_layers.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int]
    lib.ts_finish.argtypes=[C.c_void_p];lib.ts_finish.restype=C.POINTER(C.c_float)
    state=lib.ts_open(blob,len(data));assert state;lib.ts_reset(state)
    kc=np.zeros((6,4,288),np.float32);vc=kc.copy();checks=[]
    def rms(x,w):return x*(np.float32(1)/np.sqrt(np.sum(x*x,dtype=np.float32)/np.float32(288)+np.float32(1e-5)))*w
    try:
        for pos,token in enumerate([1,727,471,263]):
            x=weights['output.weight'][token].copy()
            for layer in range(6):
                prefix=f'layers.{layer}.';z=rms(x,weights[prefix+'attention_norm.weight'])
                q=weights[prefix+'attention.wq.weight']@z;k=weights[prefix+'attention.wk.weight']@z;v=weights[prefix+'attention.wv.weight']@z
                for i in range(0,288,2):
                    angle=np.float32(pos)/np.float32(10000**((i%48)/48));co=np.float32(np.cos(angle));si=np.float32(np.sin(angle))
                    qa,qb=q[i:i+2].copy();ka,kb=k[i:i+2].copy();q[i:i+2]=[qa*co-qb*si,qa*si+qb*co];k[i:i+2]=[ka*co-kb*si,ka*si+kb*co]
                kc[layer,pos]=k;vc[layer,pos]=v;att=np.zeros(288,np.float32)
                for head in range(6):
                    start=head*48;end=start+48;scores=kc[layer,:pos+1,start:end]@q[start:end]/np.sqrt(np.float32(48));scores=np.exp(scores-scores.max());scores/=scores.sum();att[start:end]=scores@vc[layer,:pos+1,start:end]
                x+=weights[prefix+'attention.wo.weight']@att;z=rms(x,weights[prefix+'ffn_norm.weight'])
                aa=weights[prefix+'feed_forward.w1.weight']@z;b=weights[prefix+'feed_forward.w3.weight']@z
                x+=weights[prefix+'feed_forward.w2.weight']@((aa/(1+np.exp(-aa)))*b)
            expected=weights['output.weight']@rms(x,weights['norm.weight'])
            assert lib.ts_embed(state,token)==0 and lib.ts_layers(state,0,6,pos)==0
            actual=np.ctypeslib.as_array(lib.ts_finish(state),(32000,)).copy();error=float(np.max(np.abs(actual-expected)))
            assert error<.002 and int(np.argmax(actual))==int(np.argmax(expected))
            checks.append({'position':pos,'max_absolute_logit_error':error,'argmax_equal':True})
    finally:lib.ts_close(state)
    a.output.write_text(json.dumps({'source':'BF16 tensors independently row-quantized; NumPy forward versus packed portable C','positions':checks,'absolute_tolerance':.002},indent=2)+'\n',encoding='utf-8')
    print('NumPy reference passed; max absolute logit error',max(x['max_absolute_logit_error'] for x in checks))

if __name__=='__main__':main()
