import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from research_integrity import recorded_file, study_directory


class ResearchIntegrityTests(unittest.TestCase):
    def test_public_translation_needs_both_historical_and_public_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);p=root/'data/p.json';p.parent.mkdir();p.write_bytes(b'public representation')
            original=hashlib.sha256(b'original private representation').hexdigest()
            metadata=root/'provenance';metadata.mkdir()
            (metadata/'representations.json').write_text(json.dumps({'files':{'data/p.json':{
                'historical_sha256':original,'published_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}}}))
            recorded_file(p,original,root)
            with self.assertRaises(ValueError):recorded_file(p,'0'*64,root)
            p.write_bytes(b'changed')
            with self.assertRaises(ValueError):recorded_file(p,original,root)

    def test_private_freeze_remains_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);p=root/'protocol.json';p.write_bytes(b'private')
            recorded_file(p,hashlib.sha256(b'private').hexdigest(),root)
            with self.assertRaises(ValueError):recorded_file(p,'0'*64,root)

    def test_run_and_output_resolution_rejects_traversal(self):
        default=pathlib.Path('/research/data/archive')
        self.assertEqual(study_directory(SimpleNamespace(run='repeat-01',output=None),default),default.parent/'repeat-01')
        for value in ['../escape','a/b','..','C:\\other']:
            with self.assertRaises(ValueError):study_directory(SimpleNamespace(run=value,output=None),default)


if __name__=='__main__':unittest.main()
