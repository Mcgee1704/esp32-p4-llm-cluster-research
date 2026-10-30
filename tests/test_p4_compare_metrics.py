import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from p4_compare_metrics import paired_summary, rates


class MatchedP4MetricsTests(unittest.TestCase):
    def rows(self):
        return [{'model':model,'case':case,'block':block,'done':{
            'elapsed_ms':(2000 if model=='tinybrainbot' else 3000)+block*10,
            'ttft_ms':1000,'output_tokens':16,'prompt_tokens':4 if model=='tinybrainbot' else 5,'eos':False}}
            for block in [1,2,3] for model in ['tinybrainbot','supra'] for case in ['B1','B2']]

    def test_pairs_use_same_case_and_block_with_actual_output_shape(self):
        s=paired_summary(self.rows())
        self.assertEqual(s['B1']['paired_blocks'],3)
        self.assertTrue(s['B1']['matched_capped_outputs'])
        self.assertAlmostEqual(s['B1']['supra_over_tiny_total_median'],3020/2020)
        self.assertEqual(s['B1']['models']['tinybrainbot']['prompt_tokens'],4)
        self.assertEqual(s['B1']['models']['supra']['prompt_tokens'],5)

    def test_early_eos_is_not_an_equal_work_speedup(self):
        rows=self.rows();rows[0]['done'].update(eos=True,output_tokens=3)
        s=paired_summary(rows)['B1']
        self.assertFalse(s['matched_capped_outputs'])
        self.assertIsNone(s['supra_over_tiny_total_median'])
        self.assertIsNone(rates(rows[0]['done'])['decode_proxy_tokens_per_s'])

    def test_duplicate_missing_or_changed_length_rejected(self):
        for rows in [self.rows()[:-1],self.rows()+self.rows()[:1]]:
            with self.assertRaises(ValueError):paired_summary(rows)
        rows=self.rows();rows[0]['done']['prompt_tokens']=7
        with self.assertRaises(ValueError):paired_summary(rows)

    def test_decode_interval_excludes_first_output_and_keeps_closing_overhead(self):
        self.assertEqual(rates({'elapsed_ms':2000,'ttft_ms':1000,'eos':False,'output_tokens':16})['decode_proxy_tokens_per_s'],15)
        with self.assertRaises(ValueError):rates({'elapsed_ms':999,'ttft_ms':1000,'eos':False,'output_tokens':16})


if __name__=='__main__':unittest.main()
