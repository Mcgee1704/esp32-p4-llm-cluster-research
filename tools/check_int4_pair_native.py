"""Build isolated candidate DLL, run all tests, compare genuine-model references.

Redirect only loads of the historical DLL path while running this process;
never overwrite the archived DLL or the old experiments' evidence.
"""
import ctypes as C
import hashlib
import json
import pathlib
import subprocess
import sys
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'.local/int4-pair-2026-10-30'
DATA=ROOT/'data/int4-pair-2026-10-30'
OLD=ROOT/'.local/build/tinyllm.dll'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    OUT.mkdir(exist_ok=True)
    original=sha(OLD);candidate=OUT/'tinyllm-pair.dll';src=ROOT/'firmware/components/tinyllm'
    subprocess.run([str(ROOT/'.local/tooling/host/ziglang/zig.exe'),'cc','-shared','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-I',str(src/'include'),*[str(src/x) for x in ['tinyllm.c','model_envelope.c','gpt2_tokenizer.c','sp_tokenizer.c','cluster_rpc.c']],'-o',str(candidate)],check=True)
    cdll=C.CDLL
    def routed(path,*a,**kw):
        return cdll(str(candidate) if pathlib.Path(path).resolve()==OLD.resolve() else path,*a,**kw)
    C.CDLL=routed
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/'tests')))
    assert result.wasSuccessful()
    from check_gptneo_native import Native
    prior=ROOT/'data/matched-p4-2026-10-30'
    refs=json.loads((prior/'host-references.json').read_text())['tinybrainbot']
    protocol=json.loads((prior/'protocol.json').read_text());model=ROOT/'.local/tinybrainbot-p4-2026-10-29/tinybrainbot-full.p4qs'
    native=Native(model)
    # The same true model, different kernel modes, full-vocabulary logits.
    native.lib.ts_set_kernel.argtypes=[C.c_void_p,C.c_int]
    inputs=protocol['inputs']['tinybrainbot'];matched=[]
    try:
        for case in protocol['cases']:
            prompt=inputs[case['id']]['prompt'];actual=native.generate(prompt,case['limit'])
            expected=refs[case['id']]
            assert all(actual[k]==expected[k] for k in ['tokens','text','eos','prompt_tokens'])
            matched.append(case['id'])
        for case in protocol['benchmarks']:
            actual=native.generate(case['prompt'],case['limit']);expected=refs[case['id']]
            assert all(actual[k]==expected[k] for k in ['tokens','text','eos','prompt_tokens'])
            matched.append(case['id'])
        import numpy as np
        other=Native(model)
        try:
            native.lib.ts_set_kernel(other.state,2)
            native.lib.ts_reset(native.state);other.lib.ts_reset(other.state)
            ids=native.encode('Once upon a time');positions=ids+[42,305,31899,31921]
            for i,token in enumerate(positions):
                a=native.forward(token,i);b=other.forward(token,i)
                np.testing.assert_array_equal(a,b)
                assert a.tobytes()==b.tobytes(), 'Full-logit FP32 bytes differ'
        finally:other.close()
    finally:native.close();C.CDLL=cdll
    assert sha(OLD)==original
    record={'tests':result.testsRun,'tests_passed':True,'reference_generations':matched,'all_tokens_text_eos_prompt_ids_equal':True,
            'full_vocabulary_logit_positions':len(positions),'all_logits_bit_identical_to_scalar':True,'vocabulary':32000,
            'archived_dll_preserved':True,'archived_dll_sha256':original,'candidate_dll_sha256':sha(candidate),
            'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in [src/'tinyllm.c',src/'int4_dot.h',ROOT/'tests/test_int4_pair.py',pathlib.Path(__file__)]}}
    (DATA/'host-check.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)

if __name__=='__main__':main()
