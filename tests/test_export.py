"""Catch oversized or malformed inputs before any device write can happen."""
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest
import test_inference

class ExportTests(unittest.TestCase):
    def test_rejects_truncated_checkpoint_and_wrong_tokenizer(self):
        with tempfile.TemporaryDirectory() as directory:
            raw=pathlib.Path(directory)/'model.bin';_,tok=test_inference.fixture(raw)
            target=raw.with_suffix('.p4lm')
            original=raw.read_bytes();raw.write_bytes(original[:-4])
            cmd=[sys.executable,str(test_inference.ROOT/'tools/pack_model.py'),str(raw),str(tok),str(target)]
            r=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0);self.assertFalse(target.exists())
            raw.write_bytes(original);tok.write_bytes(tok.read_bytes()[:-1])
            r=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0);self.assertFalse(target.exists())

    def test_rejects_untied_model_and_nonfinite_weights(self):
        with tempfile.TemporaryDirectory() as directory:
            raw=pathlib.Path(directory)/'model.bin';_,tok=test_inference.fixture(raw)
            target=raw.with_suffix('.p4lm');original=raw.read_bytes()
            for offset,value,fmt in [(20,-272,'<i'),(28,float('nan'),'<f')]:
                broken=bytearray(original);struct.pack_into(fmt,broken,offset,value);raw.write_bytes(broken)
                r=subprocess.run([sys.executable,str(test_inference.ROOT/'tools/pack_model.py'),str(raw),str(tok),str(target)],capture_output=True,text=True)
                self.assertNotEqual(r.returncode,0);self.assertFalse(target.exists())
