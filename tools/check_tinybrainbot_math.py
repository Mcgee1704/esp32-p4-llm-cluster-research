"""Host C matrix control with a synthetic tokenizer. NEVER an installable model.

Numeric token IDs bypass the deliberately fake ByteLevel vocabulary. This tests
actual candidate INT4 weights / Llama math and sharding, not Metaspace support.
"""
import ctypes as C
from tinybrainbot_study import OUT,CACHE,ROOT,load_candidate,code_hashes,sha,write,freeze,np,row_int4,Reference
from pack_supra import pack
from check_gptneo_native import Native


def main():
    protocol={'scope':'Host C numerical IDs only, synthetic unsupported-for-real-text tokenizer; no P4 or actual tokenizer test',
              'tokens':[4,257,1024],'kernel_modes':[0,1,2,3,4],'tolerance':.003,'split':4,
              'source_code_sha256':code_hashes(),'script_sha256':sha(ROOT/'tools/check_tinybrainbot_math.py')}
    freeze(OUT/'math-protocol.json',protocol)
    c,t=load_candidate();q=row_int4(t)
    vocab=[('diagnostic-'+str(i)).encode() for i in range(16)]+[bytes([i]) for i in range(256)]
    vocab += [('unused-'+str(i)).encode() for i in range(len(vocab),c['vocab_size'])]
    artifacts=pack(c,t,vocab,[],[(9,13,3),(32,32,3),(48,57,2),(65,90,1),(97,122,1)],list(range(16)),split=4,context=256)
    states=[]
    try:
        for role,raw in artifacts.items():
            path=CACHE/('MATH-ONLY-FAKE-TOKENIZER-'+role+'.p4qs');path.write_bytes(raw);states.append(Native(path))
        full,master,worker=states;lib=full.lib
        lib.ts_set_kernel.argtypes=[C.c_void_p,C.c_int];lib.ts_x.argtypes=[C.c_void_p];lib.ts_x.restype=C.POINTER(C.c_float)
        errors=[];baseline=[]
        for mode in protocol['kernel_modes']:
            for state in states:assert lib.ts_set_kernel(state.state,mode)==0;lib.ts_reset(state.state)
            reference=Reference(c,q)
            for pos,token in enumerate(protocol['tokens']):
                actual=full.forward(token,pos);expected=reference.step(token)
                error=float(np.max(np.abs(actual-expected)));assert error<protocol['tolerance']
                assert int(np.argmax(actual))==int(np.argmax(expected));errors.append(error)
                if mode==0:baseline.append(actual)
                else:np.testing.assert_array_equal(actual,baseline[pos])
                assert lib.ts_embed(master.state,token)==0 and lib.ts_layers(master.state,0,4,pos)==0
                C.memmove(lib.ts_x(worker.state),lib.ts_x(master.state),c['hidden_size']*4)
                assert lib.ts_layers(worker.state,4,12,pos)==0
                C.memmove(lib.ts_x(master.state),lib.ts_x(worker.state),c['hidden_size']*4)
                sharded=np.ctypeslib.as_array(lib.ts_finish(master.state),shape=(c['vocab_size'],)).copy()
                np.testing.assert_array_equal(actual,sharded)
        freeze(OUT/'math-report.json',{'scope':protocol['scope'],'kernels':5,'positions_per_kernel':3,'logits_per_position':32000,
            'max_absolute_logit_error':max(errors),'all_source_layout_int4_argmax_equal':True,'all_kernel_logits_bit_identical':True,
            'all_full_shard_logits_bit_identical':True,'source_tensor_inventory_verified':True,
            'math_only_artifact_sha256':{r:sha(CACHE/('MATH-ONLY-FAKE-TOKENIZER-'+r+'.p4qs')) for r in artifacts},
            'native_dll_sha256':sha(ROOT/'.local/build/tinyllm.dll'),'script_sha256':protocol['script_sha256']})
        print('PASS actual candidate INT4 math, 5 kernels x 3 full-vocabulary positions, full/shard equality. Tokenizer NOT tested.')
    finally:
        for state in states:state.close()


if __name__=='__main__':main()
