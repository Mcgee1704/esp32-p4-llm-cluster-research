"""Pinned Metaspace differential and malformed-data tests; no model weights."""
import ctypes as C
import pathlib
import sys
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT/'.local/tooling/tinytalk-host'))
from tokenizers import Tokenizer
from pack_spm import pack_tokenizer,pack_model


class SPMTokenizer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=ROOT/'.local/models/tinybrainbot-a8567bd7674f/tokenizer.json'
        if not cls.path.exists():raise unittest.SkipTest('Pinned tokenizer data not cached')
        cls.raw=pack_tokenizer(cls.path);cls.ref=Tokenizer.from_file(str(cls.path));cls.lib=C.CDLL(str(ROOT/'.local/build/tinyllm.dll'))
        l=cls.lib;l.sp_open.argtypes=[C.c_void_p,C.c_size_t,C.c_uint,C.c_uint];l.sp_open.restype=C.c_void_p
        l.sp_close.argtypes=[C.c_void_p];l.sp_encode.argtypes=[C.c_void_p,C.c_char_p,C.POINTER(C.c_int),C.c_int]
        l.sp_normalize.argtypes=[C.c_void_p,C.c_char_p,C.c_void_p,C.c_size_t]
        l.sp_decode.argtypes=[C.c_void_p,C.c_int,C.c_uint,C.c_void_p,C.c_size_t]
        cls.blob=C.create_string_buffer(cls.raw);cls.state=l.sp_open(cls.blob,len(cls.raw),32000,7);assert cls.state

    @classmethod
    def tearDownClass(cls):
        if getattr(cls,'state',None):cls.lib.sp_close(cls.state)

    def encode(self,text,cap=4096):
        out=(C.c_int*cap)();n=self.lib.sp_encode(self.state,text.encode('utf-8'),out,cap)
        self.assertGreaterEqual(n,0,repr(text));return list(out[:n])

    def test_encode_native_prompts_whitespace_added_tokens_and_unicode(self):
        probes=['','a','hello',' hello','  hello','a  b','a\r\nb','a\tb','a\nb','<s>hello','a<|user|>b','x <s> y',
                ' <|user|> What is the capital of Germany? <|end|> <|assistant|>',
                'Gr\u00fc\u00dfe! caf\u00e9 e\u0301 e\u0301\u0300 \ufb03 \uff11\uff12\uff13',
                '\u0915\u094d\u0937 \u1100\u1161\u11a8 \U0001f469\u200d\U0001f4bb',
                '<think>x</think><|mem_l1|> y <pad> z','\x01\x1ea\x7f','a\u00a0b\u2009c']
        for text in probes:self.assertEqual(self.encode(text),self.ref.encode(text,add_special_tokens=False).ids,repr(text))

    def test_decode_all_vocabulary_at_first_and_later_output_positions(self):
        out=C.create_string_buffer(1024);prefix=self.ref.token_to_id('a');plain=self.ref.decode([prefix],skip_special_tokens=False)
        for i in range(32000):
            for index in (0,1):
                n=self.lib.sp_decode(self.state,i,index,out,len(out));self.assertGreaterEqual(n,0)
                expected=self.ref.decode([i],skip_special_tokens=False) if not index else self.ref.decode([prefix,i],skip_special_tokens=False)[len(plain):]
                self.assertEqual(out.raw[:n],expected.encode('utf-8'),(i,index))

    def test_normalizer_graphemes_and_pinned_short_prefix_behavior(self):
        out=C.create_string_buffer(65536)
        for text in ['e\u0301\u0300','\u2122\x1eg','\ufdfa','\r\n','x  y  ','\u0915\u094d\u0937','\u00e9\u0300', 'a\u200db']:
            n=self.lib.sp_normalize(self.state,text.encode(),out,len(out));self.assertGreaterEqual(n,0)
            self.assertEqual(out.raw[:n].decode(),self.ref.normalizer.normalize_str(text),repr(text))

    def test_rejects_bounds_invalid_utf8_and_malformed_sections(self):
        import struct
        for cut in [0,8,63,64,len(self.raw)-1]:
            b=C.create_string_buffer(self.raw[:cut]);self.assertFalse(self.lib.sp_open(b,cut,32000,7))
        for off,val in [(8,0),(12,100001),(20,100),(24,0),(32,100000),(36,2),(40,32000),(44,2),(48,1)]:
            raw=bytearray(self.raw);struct.pack_into('<I',raw,off,val);b=C.create_string_buffer(bytes(raw))
            self.assertFalse(self.lib.sp_open(b,len(raw),32000,7),(off,val))
        out=(C.c_int*4)(123,123,123,123)
        for raw in [b'\xc0\xaf',b'\xed\xa0\x80',b'\xf4\x90\x80\x80',b'a'*4097]:self.assertEqual(self.lib.sp_encode(self.state,raw,out,4),-1)
        self.assertEqual(self.lib.sp_encode(self.state,b'a b c',out,1),-1)
        self.assertEqual(list(out)[1:],[123,123,123])

    def test_real_tokenizer_model_and_output_position_decode(self):
        from pack_supra import synthetic,np
        from check_gptneo_native import Native
        c,t,*_=synthetic();c['vocab_size']=32000;c['eos_token_id']=7
        t['model.embed_tokens.weight']=np.zeros((32000,8),dtype='float32')
        for name,w in t.items():w[:]=1 if 'norm' in name else 0
        source=self.ref.encode('hello',add_special_tokens=False).ids;self.assertEqual(len(source),1)
        target=self.ref.token_to_id('\u2581world');self.assertIsNotNone(target)
        t['model.embed_tokens.weight'][source[0]]=.25;t['model.embed_tokens.weight'][target]=1
        raw=pack_model(c,t,self.path,split=1,context=16)['full']
        path=ROOT/'.local/build/spm-integrated-test.p4qs';path.write_bytes(raw);native=Native(path)
        try:
            actual=native.generate('hello',3);self.assertEqual(actual['tokens'],[target]*3)
            self.assertEqual(actual['text'],self.ref.decode([target]*3,skip_special_tokens=False))
        finally:native.close()

    def test_rejects_corrupt_indices_merges_normalizer_and_ranges(self):
        import struct
        v,m,s,a,n,g,c,*_=struct.unpack_from('<10I',self.raw,8)
        merges=(64+(v+1)*4+s+3)&~3;added=merges+m*16;chars=added+a*8;norm=chars+c*8;ranges=(norm+n+3)&~3
        edits=[(64+4,0),(merges,v),(merges+8,m),(added,v),(chars+4,v),(norm,n),
               (norm+4,0xffffffff),(norm+n-1,65),(ranges+8,256),(ranges+12,0)]
        for offset,value in edits:
            raw=bytearray(self.raw)
            if offset==norm+n-1:raw[offset]=value
            else:struct.pack_into('<I',raw,offset,value)
            b=C.create_string_buffer(bytes(raw));self.assertFalse(self.lib.sp_open(b,len(raw),32000,7),(offset,value))


if __name__=='__main__':unittest.main()
