"""Contracts for data-only model evaluation, template fidelity and stop handling."""
import pathlib
import sys
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from pack_supra import synthetic,np
from supra_reference import Reference
from tinybrainbot_study import prompt,validate_tensors,greedy,screen,budget


class TinyBrainBotStudy(unittest.TestCase):
    def test_author_native_template_preserves_all_spaces(self):
        self.assertEqual(prompt('tinybrainbot','Hi!'),' <|user|> Hi! <|end|> <|assistant|>')
        self.assertEqual(prompt('supra','Hi!'),'<|im_start|>user\nHi!<|im_end|>\n<|im_start|>assistant\n')
        with self.assertRaises(ValueError):prompt('unknown','Hi!')

    def test_inventory_rejects_missing_extra_wrong_or_nonfinite_tensor(self):
        c,t,*_=synthetic();validate_tensors(c,t)
        for bad in [{k:v for k,v in t.items() if k!='model.norm.weight'},
                    {**t,'extra':np.ones((1,))},
                    {**t,'model.norm.weight':np.ones(1)},
                    {**t,'model.norm.weight':np.full(8,np.nan)}]:
            with self.assertRaises(ValueError):validate_tensors(c,bad)

    def test_stop_id_works_for_token_not_tagged_special(self):
        c,t,*_=synthetic()
        for n,w in t.items():w[:]=1 if 'norm' in n else 0
        t['model.embed_tokens.weight'][7]=1;t['model.embed_tokens.weight'][12]=.25
        result=greedy(Reference(c,t),[12],lambda ids:str(ids),{7},3)
        self.assertEqual(result['tokens'],[]);self.assertTrue(result['eos']);self.assertEqual(result['stop_id'],7)
        result=greedy(Reference(c,t),[12],lambda ids:str(ids),{258},3)
        self.assertEqual(result['tokens'],[7,7,7]);self.assertFalse(result['eos'])

    def test_supporting_screen_handles_direct_negation_decimals_and_exact_case(self):
        c={'answers':['star']}
        self.assertFalse(screen(c,'It is not a star.'))
        self.assertTrue(screen(c,'A star, not a planet.'))
        self.assertFalse(screen({'answers':['100']},'100.5 degrees.'))
        self.assertTrue(screen({'answers':['100']},'100.0 degrees.'))
        self.assertTrue(screen({'exact':'violet'},' violet\n'))
        self.assertFalse(screen({'exact':'violet'},'Violet'))

    def test_budget_counts_each_role_kv_and_full_tied_table_once(self):
        c,t,*_=synthetic();b=budget(c,split=1,context=16,tokenizer_allowance=100,runtime_allowance=0)
        self.assertEqual(b['coordinator']['kv_bytes'],512)
        self.assertEqual(b['worker']['kv_bytes'],512)
        self.assertEqual(b['coordinator']['tokenizer_allowance'],100)
        self.assertEqual(b['worker']['tokenizer_allowance'],0)
        larger=budget(c,split=1,context=32,tokenizer_allowance=100,runtime_allowance=0)
        self.assertEqual(larger['worker']['kv_bytes'],2*b['worker']['kv_bytes'])


if __name__=='__main__':unittest.main()
