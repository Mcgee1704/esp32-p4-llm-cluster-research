import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from verify_tinybrainbot_study import validate_receipt


class ResearchReceiptTests(unittest.TestCase):
    def test_count_remains_integer_after_condition_loop(self):
        count=120
        for condition in ['supra-f16','tinybrainbot-int4']:
            self.assertTrue(condition)
        r=validate_receipt({'checks_passed':True,'complete_generations_checked':count})
        self.assertIs(type(r['complete_generations_checked']),int)

    def test_schema_rejects_condition_string_bool_float_and_wrong_count(self):
        for count in ['tinybrainbot-int4',True,120.0,119,None]:
            with self.subTest(count=count),self.assertRaises(ValueError):
                validate_receipt({'checks_passed':True,'complete_generations_checked':count})


if __name__=='__main__':unittest.main()
