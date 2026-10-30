"""INT4 capacity is useful only if tokens, ranges and numerical results survive."""
import ctypes as C
import pathlib
import struct
import sys
import unittest
import zlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from pack_supra import quantize,pack,synthetic,tokenizer_v2
from check_gptneo_native import Native
from supra_reference import Reference,row_int4
import numpy as np


class SupraShards(unittest.TestCase):
    def test_int4_signed_nibbles_and_zero_row(self):
        values=np.array([[-7,-6,-1,0,1,2,6,7],[0]*8],dtype='float32')
        raw=quantize(values)
        self.assertEqual(struct.unpack_from('<2f',raw),(1.,1.))
        self.assertEqual(raw[8:12],bytes([0xa9,0x0f,0x21,0x76]))
        self.assertEqual(raw[12:],bytes(4))

    def test_shards_equal_full_and_refuse_wrong_ranges(self):
        cfg,t,v,m,r,special=synthetic()
        artifacts=pack(cfg,t,v,m,r,special,split=1,context=16)
        paths=[]
        for role,raw in artifacts.items():
            p=ROOT/'.local/build'/('supra-test-'+role+'.p4qs');p.write_bytes(raw);paths.append(p)
        full,master,worker=[Native(p) for p in paths]
        lib=full.lib
        lib.ts_x.argtypes=[C.c_void_p];lib.ts_x.restype=C.POINTER(C.c_float)
        lib.ts_role.argtypes=[C.c_void_p];lib.ts_role.restype=C.c_uint32
        lib.ts_model_id.argtypes=[C.c_void_p];lib.ts_model_id.restype=C.c_void_p
        try:
            self.assertEqual([lib.ts_role(x.state) for x in (full,master,worker)],[0,1,2])
            self.assertEqual(len({C.string_at(lib.ts_model_id(x.state),32) for x in (full,master,worker)}),1)
            self.assertEqual(lib.ts_embed(worker.state,10),-1)
            self.assertEqual(lib.ts_layers(worker.state,0,2,0),-1)
            self.assertEqual(lib.ts_layers(master.state,1,2,0),-1)
            self.assertFalse(lib.ts_finish(worker.state))
            lib.ts_reset(full.state);lib.ts_reset(master.state);lib.ts_reset(worker.state)
            for pos,token in enumerate(([10,42,7]*6)[:16]):
                self.assertEqual(lib.ts_embed(full.state,token),0);self.assertEqual(lib.ts_embed(master.state,token),0)
                self.assertEqual(lib.ts_layers(full.state,0,2,pos),0)
                self.assertEqual(lib.ts_layers(master.state,0,1,pos),0)
                C.memmove(lib.ts_x(worker.state),lib.ts_x(master.state),cfg['hidden_size']*4)
                self.assertEqual(lib.ts_layers(worker.state,1,2,pos),0)
                C.memmove(lib.ts_x(master.state),lib.ts_x(worker.state),cfg['hidden_size']*4)
                a=np.ctypeslib.as_array(lib.ts_finish(full.state),shape=(cfg['vocab_size'],)).copy()
                b=np.ctypeslib.as_array(lib.ts_finish(master.state),shape=a.shape).copy()
                np.testing.assert_array_equal(a,b)
            self.assertEqual(lib.ts_layers(worker.state,1,2,16),-1)
            self.assertEqual(lib.ts_layers(master.state,0,1,16),-1)
        finally:
            for n in (full,master,worker):n.close()

    def test_incompatible_export_rejected(self):
        cfg,t,v,m,r,special=synthetic();cfg['tie_word_embeddings']=False
        with self.assertRaises(ValueError):pack(cfg,t,v,m,r,special,split=1,context=16)

    def test_qwen_head_norms_match_independent_source_layout(self):
        cfg,t,v,m,r,special=synthetic();cfg['architectures']=['Qwen3ForCausalLM']
        for i in range(2):
            for n in ['q','k']:t[f'model.layers.{i}.self_attn.{n}_norm.weight']=np.array([.7,1.2,.9,1.1],dtype='float32')
        raw=pack(cfg,t,v,m,r,special,split=1,context=16)['full']
        p=ROOT/'.local/build/supra-qwen-test.p4qs';p.write_bytes(raw);native=Native(p)
        try:
            native.lib.ts_set_kernel.argtypes=[C.c_void_p,C.c_int];baseline=[]
            for mode in range(5):
                self.assertEqual(native.lib.ts_set_kernel(native.state,mode),0)
                reference=Reference(cfg,row_int4(t));native.lib.ts_reset(native.state)
                for pos,token in enumerate([12,72,40]):
                    actual=native.forward(token,pos)
                    np.testing.assert_allclose(actual,reference.step(token),atol=2e-5,rtol=2e-5)
                    if mode==0:baseline.append(actual)
                    else:np.testing.assert_array_equal(actual,baseline[pos])
        finally:native.close()

    def test_special_tokens_binary_pieces_and_malformed_ranges(self):
        cfg,t,v,m,r,special=synthetic();raw=pack(cfg,t,v,m,r,special,split=1,context=16)['full']
        p=ROOT/'.local/build/supra-token-test.p4qs';p.write_bytes(raw);native=Native(p)
        try:
            self.assertEqual(native.encode('<s>ab</s><pad>'),[257,256,258,259])
            self.assertEqual(native.piece(0),b'\0')
            l=native.lib
            for offset,value in [(44,3),(168,2),(172,0),(176,8),(180,999),(196,2)]:
                invalid=bytearray(raw);struct.pack_into('<I',invalid,offset,value)
                struct.pack_into('<I',invalid,80,zlib.crc32(invalid[128:]))
                blob=C.create_string_buffer(bytes(invalid));self.assertFalse(l.ts_open(blob,len(invalid)),offset)
        finally:native.close()

    def test_digit_split_precedes_bytelevel_trailing_whitespace(self):
        cfg,t,v,m,r,special=synthetic();v.append(b'  ');m.append((32,32,1,260));cfg['vocab_size']=261
        t['model.embed_tokens.weight']=np.vstack((t['model.embed_tokens.weight'],t['model.embed_tokens.weight'][0]))
        raw=pack(cfg,t,v,m,r,special,split=1,context=16,digits=True)['full']
        p=ROOT/'.local/build/supra-digits-test.p4qs';p.write_bytes(raw);native=Native(p)
        try:self.assertEqual(native.encode('  12 ab 2'),[260,49,50,32,256,32,50])
        finally:native.close()

    def test_chat_end_and_primary_eos_are_both_recognized(self):
        cfg,t,v,m,r,special=synthetic();v.append(b'<|im_end|>');special.append(260);cfg['vocab_size']=261
        t['model.embed_tokens.weight']=np.vstack((t['model.embed_tokens.weight'],t['model.embed_tokens.weight'][0]))
        raw=pack(cfg,t,v,m,r,special,split=1,context=16)['full']
        p=ROOT/'.local/build/supra-chat-end-test.p4qs';p.write_bytes(raw);native=Native(p)
        try:
            for token,expected in [(258,1),(260,1),(257,0),(1,0),(2,0)]:
                self.assertEqual(native.lib.ts_is_eos(native.state,token),expected)
        finally:native.close()


if __name__=='__main__':unittest.main()

