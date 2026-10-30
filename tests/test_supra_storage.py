"""Bounds and corruption gates for data-only GGUF and lossless flash storage."""
import pathlib
import ctypes as C
import struct
import sys
import unittest
import json
import tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from pack_supra import load_source
from supra_gguf import read_gguf
from supra_storage import wrap,unwrap


def string(x):return struct.pack('<Q',len(x))+x


class SupraStorage(unittest.TestCase):
    def test_valid_but_unpinned_source_is_refused(self):
        # A well-formed replacement must not silently change a pinned experiment.
        header=json.dumps({'x':{'dtype':'BF16','shape':[1],'data_offsets':[0,2]}}).encode()
        raw=struct.pack('<Q',len(header))+header+struct.pack('<H',0x3f80)
        with tempfile.TemporaryDirectory() as temp:
            directory=pathlib.Path(temp);(directory/'model.safetensors').write_bytes(raw)
            (directory/'source-metadata.json').write_text(json.dumps({'repository':'SupraLabs/Supra1.5-50M-Instruct-exp','revision':'f0566e6be9f1cd3530fe004ce4e56a5c4148bf73','files':[]}),encoding='utf-8')
            with self.assertRaises(ValueError):load_source(directory)

    def test_known_f16_matrix_and_shape_order(self):
        # GGUF has columns first; an HF matrix is rows first.
        info=string(b'test')+struct.pack('<IQQIQ',2,2,3,1,0)
        raw=b'GGUF'+struct.pack('<IQQ',3,1,0)+info
        raw+=bytes(-len(raw)%32)+struct.pack('<6e',1,2,3,4,5,6)
        tensors,meta=read_gguf(raw)
        self.assertEqual(tensors['test'].shape,(3,2))
        self.assertEqual(tensors['test'].tolist(),[[1,2],[3,4],[5,6]])
        for invalid in [raw[:-1],raw[:40],b'BAD!'+raw[4:]]:
            with self.assertRaises(ValueError):read_gguf(invalid)

    def test_lossless_envelope_bounds_and_corruption(self):
        raw=b'P4QS0001'+bytes(range(256))*31
        compressed=wrap(raw)
        self.assertEqual(unwrap(compressed),raw)
        for data in [compressed[:-1],compressed+bytes(1),compressed[:135]+bytes([compressed[135]^1])+compressed[136:]]:
            with self.assertRaises(ValueError):unwrap(data)
        malicious=bytearray(compressed);struct.pack_into('<I',malicious,8,1024*1024*1024)
        with self.assertRaises(ValueError):unwrap(malicious)

    def test_device_envelope_gate_before_flash_erase_or_allocation(self):
        lib=C.CDLL(str(ROOT/'.local/build/tinyllm.dll'))
        lib.ts_storage_expanded.argtypes=[C.c_void_p,C.c_size_t];lib.ts_storage_expanded.restype=C.c_size_t
        raw=b'P4QS0001'+bytes(range(256))*31;blob=wrap(raw)
        def size(data,stored=None):return lib.ts_storage_expanded(C.create_string_buffer(bytes(data[:128])),len(data) if stored is None else stored)
        self.assertEqual(size(blob),len(raw))
        self.assertEqual(size(blob,len(blob)-1),0)
        for offset,value in [(8,1024*1024*1024),(12,1),(40,1),(44,1),(116,1)]:
            invalid=bytearray(blob);struct.pack_into('<I',invalid,offset,value);self.assertEqual(size(invalid),0)


if __name__=='__main__':unittest.main()
