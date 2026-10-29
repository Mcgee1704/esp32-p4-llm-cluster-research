"""Run the exact firmware C core locally, including its real RPC dispatcher."""
import argparse
import ctypes as C
import json
import pathlib
import struct
import time

root=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--model',type=pathlib.Path,default=root/'.local/models/stories15M.p4lm')
p.add_argument('--prompt',default='Once upon a time')
p.add_argument('--tokens',type=int,default=24)
args=p.parse_args()
payload=args.model.read_bytes();blob=C.create_string_buffer(payload)
lib=C.CDLL(str(root/'.local/build/tinyllm.dll'))
lib.ts_open.argtypes=[C.c_void_p,C.c_size_t];lib.ts_open.restype=C.c_void_p
lib.ts_close.argtypes=[C.c_void_p]
lib.ts_reset.argtypes=[C.c_void_p]
lib.ts_embed.argtypes=[C.c_void_p,C.c_int]
lib.ts_layers.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int]
lib.ts_encode.argtypes=[C.c_void_p,C.c_char_p,C.POINTER(C.c_int),C.c_int]
lib.ts_decode.argtypes=[C.c_void_p,C.c_int,C.c_int];lib.ts_decode.restype=C.c_char_p
lib.ts_argmax.argtypes=[C.c_void_p]
for name in ['ts_x','ts_finish']:
    getattr(lib,name).argtypes=[C.c_void_p];getattr(lib,name).restype=C.POINTER(C.c_float)
lib.rpc_open.argtypes=[C.c_void_p];lib.rpc_open.restype=C.c_void_p
lib.rpc_close.argtypes=[C.c_void_p]
lib.rpc_dispatch.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t]
d,h,layers,heads,kv,vocab,context=struct.unpack_from('<7I',payload,8)
solo=lib.ts_open(blob,len(payload));master=lib.ts_open(blob,len(payload));worker=lib.ts_open(blob,len(payload))
if not all([solo,master,worker]):raise SystemExit('Model could not be loaded')
rpc=lib.rpc_open(worker)
try:
    tokens=(C.c_int*(context+1026))();n=lib.ts_encode(solo,args.prompt.encode(),tokens,len(tokens))
    if n<1 or n+args.tokens-1>context:raise SystemExit('Prompt/output exceeds context')
    def remote(command,pos=0):
        vec=C.string_at(lib.ts_x(master),d*4) if command==2 else b''
        frame=struct.pack('<8I',0x31505250,command,1,pos,layers//2,d,len(vec),0)+payload[48:80]+vec
        request=C.create_string_buffer(frame);response=C.create_string_buffer(64+d*4)
        size=lib.rpc_dispatch(rpc,request,len(frame),response,len(response))
        if size!=64+len(vec):raise RuntimeError('RPC failed')
        if vec:C.memmove(lib.ts_x(master),C.addressof(response)+64,d*4)
    remote(1);current=tokens[0];output=[];ids=[];max_error=0;start=time.perf_counter()
    for pos in range(n+args.tokens-1):
        for obj,end in [(solo,layers),(master,layers//2)]:
            assert lib.ts_embed(obj,current)==0
            assert lib.ts_layers(obj,0,end,pos)==0
        remote(2,pos)
        a=lib.ts_finish(solo);b=lib.ts_finish(master)
        # Bit-exact on the same host/compiler, not merely matching sampled words.
        if C.string_at(a,vocab*4)!=C.string_at(b,vocab*4):raise RuntimeError(f'Logits differ at position {pos}')
        if pos<n-1:next_token=tokens[pos+1]
        else:
            next_token=lib.ts_argmax(solo)
            if next_token in (1,2):break
            output.append(lib.ts_decode(solo,current,next_token));ids.append(next_token)
        current=next_token
    remote(3)
    report={'kind':'host_only_not_P4_benchmark','model':args.model.name,'prompt':args.prompt,
            'generated':b''.join(output).decode('utf-8','replace'),'tokens':ids,
            'solo_vs_rpc_split':'all logits bit-identical','elapsed_seconds':time.perf_counter()-start}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    (root/'.local/build/native-demo.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
finally:
    lib.rpc_close(rpc)
    for obj in (solo,master,worker):lib.ts_close(obj)
