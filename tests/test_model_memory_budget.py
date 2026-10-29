import json
import pathlib
import sys
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from model_memory_budget import budget

class ModelMemoryTests(unittest.TestCase):
    def test_matches_existing_export_and_context_cache_growth(self):
        m=json.loads((ROOT/'data/baseline-model-manifest.json').read_text(encoding='utf-8'))
        b=budget(m['dimensions'],m['tokenizer_bytes'])
        self.assertEqual(b['artifact_bytes'],m['bytes'])
        self.assertEqual(b['weights_bytes'],m['weights_bytes'])
        self.assertEqual(b['kv_bytes'],m['kv_bytes'])
        larger=budget({**m['dimensions'],'context':512},m['tokenizer_bytes'])
        self.assertEqual(larger['kv_bytes'],2*b['kv_bytes'])
        self.assertEqual(larger['artifact_bytes'],b['artifact_bytes'])
