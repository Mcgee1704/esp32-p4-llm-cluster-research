"""Portable GPT-Neo numerical/parser/tokenizer regression fixtures."""
import ctypes as C
import importlib.util
import pathlib
import struct
import sys
import unittest
import zlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from tinytalk_reference import np,tensor_shapes,row_int8,Reference


class GPTNeoCoreTests(unittest.TestCase):
    def exporter(self):
        self.assertIsNotNone(importlib.util.find_spec('pack_gptneo'),'GPT-Neo exporter missing')
        import pack_gptneo
        return pack_gptneo

    def fixture(self):
        m=self.exporter();rng=np.random.default_rng(73)
        c={'hidden_size':8,'intermediate_size':16,'num_layers':2,'num_heads':2,
           'vocab_size':260,'max_position_embeddings':16,'window_size':2,
           'attention_layers':['global','local'],'layer_norm_epsilon':1e-5,'eos_token_id':257}
        w={n:rng.normal(0,.15,s).astype('float32') for n,s in tensor_shapes(c).items()}
        for n,a in w.items():
            if '.ln_' in n and n.endswith('.weight'):a[:]=1
        vocab=[bytes([x]) for x in range(256)]+[b'ab',b'<|endoftext|>',b'abc',b'el']
        merges=[(97,98,0,256),(256,99,1,258),(101,108,2,259)]
        ranges=[(9,13,3),(32,32,3),(48,57,2),(65,90,1),(97,122,1)]
        return c,w,m.pack(c,w,vocab,merges,ranges,context=12)

    def core(self,raw):
        lib=C.CDLL(str(ROOT/'.local/build/tinyllm.dll'))
        lib.ts_open.argtypes=[C.c_void_p,C.c_size_t];lib.ts_open.restype=C.c_void_p
        for n in ['ts_close','ts_reset','ts_argmax']:getattr(lib,n).argtypes=[C.c_void_p]
        lib.ts_embed.argtypes=[C.c_void_p,C.c_int]
        lib.ts_layers.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int]
        lib.ts_set_kernel.argtypes=[C.c_void_p,C.c_int]
        lib.ts_x.argtypes=[C.c_void_p];lib.ts_x.restype=C.POINTER(C.c_float)
        lib.ts_finish.argtypes=[C.c_void_p];lib.ts_finish.restype=C.POINTER(C.c_float)
        lib.ts_encode.argtypes=[C.c_void_p,C.c_char_p,C.POINTER(C.c_int),C.c_int]
        blob=C.create_string_buffer(raw);state=lib.ts_open(blob,len(raw))
        self.assertTrue(state,'P4GN0001 model rejected')
        return lib,blob,state

    def test_forward_all_kernels_match_numpy_and_split(self):
        c,w,raw=self.fixture();lib,blob,s=self.core(raw);_,blob2,peer=self.core(raw);_,blob3,solo=self.core(raw)
        try:
            expected=Reference(c,row_int8(w),context=12)
            tokens=[3,5,8,11,16]
            refs=[expected.step(t) for t in tokens]
            for mode in range(5):
                for state in [s,peer,solo]:self.assertEqual(lib.ts_set_kernel(state,mode),0);lib.ts_reset(state)
                for pos,t in enumerate(tokens):
                    self.assertEqual(lib.ts_embed(s,t),0)
                    self.assertEqual(lib.ts_layers(s,0,1,pos),0)
                    C.memmove(lib.ts_x(peer),lib.ts_x(s),8*4)
                    self.assertEqual(lib.ts_layers(peer,1,2,pos),0)
                    split=np.ctypeslib.as_array(lib.ts_finish(peer),(260,)).copy()
                    np.testing.assert_allclose(split,refs[pos],atol=2e-5,rtol=2e-5)
                    self.assertEqual(lib.ts_embed(solo,t),0);self.assertEqual(lib.ts_layers(solo,0,2,pos),0)
                    np.testing.assert_array_equal(split,np.ctypeslib.as_array(lib.ts_finish(solo),(260,)))
        finally:lib.ts_close(s);lib.ts_close(peer);lib.ts_close(solo)

    def test_tokenizer_ranked_merges_boundaries_special_and_binary_piece(self):
        _,_,raw=self.fixture();lib,blob,s=self.core(raw)
        try:
            def enc(text,cap=100):
                out=(C.c_int*cap)();n=lib.ts_encode(s,text,out,cap)
                return n,list(out[:n]) if n>=0 else []
            self.assertEqual(enc(b'abc ab')[1],[258,32,256])
            self.assertEqual(enc(b'ab<|endoftext|>abc')[1],[256,257,258])
            self.assertEqual(enc(b"a's  ab\n")[1],[97,39,115,32,32,256,10])
            self.assertEqual(enc(b'abc',cap=1)[1],[258])
            self.assertLess(enc(b'a b',cap=1)[0],0)
            self.assertLess(enc(b'\xff')[0],0)
            lib.ts_decode.argtypes=[C.c_void_p,C.c_int,C.c_int];lib.ts_decode.restype=C.c_void_p
            lib.ts_decode_length.argtypes=[C.c_void_p,C.c_int,C.c_int];lib.ts_decode_length.restype=C.c_size_t
            self.assertEqual(lib.ts_decode_length(s,0,0),1)
            self.assertEqual(C.string_at(lib.ts_decode(s,0,0),1),b'\0')
            lib.ts_is_eos.argtypes=[C.c_void_p,C.c_int]
            self.assertEqual(lib.ts_is_eos(s,257),1);self.assertEqual(lib.ts_is_eos(s,1),0)
        finally:lib.ts_close(s)

    def test_parser_rejects_corruption_truncation_and_invalid_tokenizer(self):
        _,_,raw=self.fixture();lib=C.CDLL(str(ROOT/'.local/build/tinyllm.dll'))
        lib.ts_open.argtypes=[C.c_void_p,C.c_size_t];lib.ts_open.restype=C.c_void_p
        cases=[raw[:127],raw[:-1],raw[:160]+bytes([raw[160]^1])+raw[161:]]
        invalid=bytearray(raw);struct.pack_into('<I',invalid,128,0)
        struct.pack_into('<I',invalid,80,zlib.crc32(invalid[128:]));cases.append(invalid)
        w=struct.unpack_from('<I',raw,36)[0];invalid=bytearray(raw)
        invalid[128+w:128+w+8]=b'BADTOK00'
        struct.pack_into('<I',invalid,80,zlib.crc32(invalid[128:]));cases.append(invalid)
        for value in cases:
            b=C.create_string_buffer(bytes(value));self.assertFalse(lib.ts_open(b,len(value)))


if __name__=='__main__':unittest.main()
