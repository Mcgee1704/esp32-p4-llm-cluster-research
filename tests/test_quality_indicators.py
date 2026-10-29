import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from text_quality_trial import indicators,CASES

class QualityIndicatorTests(unittest.TestCase):
    def test_limit_is_not_mistaken_for_natural_ending(self):
        r=indicators(CASES[0],'The end.',128)
        self.assertTrue(r['limit_reached']);self.assertFalse(r['eos_inferred'])
        self.assertTrue(indicators(CASES[0],'The end.',8)['eos_inferred'])

    def test_exact_output_rejects_extra_prose(self):
        c=next(c for c in CASES if c['id']=='I1')
        self.assertTrue(indicators(c,' Blue\n',1)['exact_format_pass'])
        self.assertFalse(indicators(c,'blue is a color',4)['exact_format_pass'])

    def test_repetition_and_animal_exclusion(self):
        c=CASES[-1]
        self.assertTrue(indicators(c,'Rain falls on the roof.',6)['restricted_sentence_heuristic_pass'])
        self.assertFalse(indicators(c,'Rain falls on cats.',6)['restricted_sentence_heuristic_pass'])
        self.assertTrue(indicators(c,'the bird flies away '*3,12)['repetition_flag'])
        self.assertFalse(indicators(c,'',0)['repetition_flag'])
