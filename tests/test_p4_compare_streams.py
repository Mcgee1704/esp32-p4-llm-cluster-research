import json
import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from p4_compare_results import stream


class MatchedStreamTests(unittest.TestCase):
    def fixture(self):
        done={'done':True,'boards':2,'eos':False,'output_tokens':2,'prompt_tokens':1,
              'elapsed_ms':2000,'ttft_ms':1000,'kernel':{'mode':'tile4','owner_core_mask':2,'helper_core_mask':1}}
        return [{'token':1,'bytes_hex':'c3'},{'token':2,'bytes_hex':'a9'},done],{'tokens':[1,2],'text':'é','eos':False,'prompt_tokens':[4]}

    def raw(self,rows):return '\n'.join(json.dumps(r) for r in rows)

    def test_utf8_may_span_tokens_but_full_bytes_must_match(self):
        rows,ref=self.fixture();text,done=stream(self.raw(rows),ref)
        self.assertEqual(text,'é');self.assertEqual(done,rows[-1])
        rows[0]['bytes_hex']='c2'
        with self.assertRaises(AssertionError):stream(self.raw(rows),ref)

    def test_missing_duplicate_or_failed_done_is_rejected(self):
        for change in ['missing','duplicate','error']:
            rows,ref=self.fixture()
            if change=='missing':rows=rows[:-1]
            elif change=='duplicate':rows.append(rows[-1])
            else:rows[-1]['error']='failed'
            with self.subTest(change=change),self.assertRaises(AssertionError):stream(self.raw(rows),ref)

    def test_wrong_board_count_token_or_output_length_is_rejected(self):
        for change in ['boards','token','length']:
            rows,ref=self.fixture()
            if change=='boards':rows[-1]['boards']=1
            elif change=='token':rows[0]['token']=7
            else:rows[-1]['output_tokens']=3
            with self.subTest(change=change),self.assertRaises(AssertionError):stream(self.raw(rows),ref)


if __name__=='__main__':unittest.main()
