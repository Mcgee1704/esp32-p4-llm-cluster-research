import json
import pathlib
import struct
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from import_sft_checkpoint import load_tensors,fields

class SFTImportTests(unittest.TestCase):
    def blob(self,offsets=(0,4),payload=struct.pack('<2H',0x3f80,0xc000)):
        header=json.dumps({'__metadata__':{'tok_embeddings.weight':'output.weight'},
                           'output.weight':{'dtype':'BF16','shape':[2],'data_offsets':list(offsets)}}).encode()
        return struct.pack('<Q',len(header))+header+payload

    def test_bfloat16_conversion_is_exact_and_data_only(self):
        self.assertEqual(load_tensors(self.blob())['output.weight'].tolist(),[1.,-2.])

    def test_rejects_truncated_out_of_bounds_and_nonfinite_tensors(self):
        for raw in [b'bad',self.blob((0,8)),self.blob(payload=struct.pack('<2H',0x7fc0,0))]:
            with self.assertRaises(ValueError):load_tensors(raw)

    def test_rejects_truncated_protobuf(self):
        with self.assertRaises(ValueError):list(fields(b'\x0a\x08bad'))
