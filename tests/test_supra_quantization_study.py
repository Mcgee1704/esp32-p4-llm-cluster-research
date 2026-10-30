"""Selection and scoring contracts, independent of the actual model answers."""
import json
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from pack_supra import np
from supra_quantization_study import fidelity,select_candidate,score_answer,freeze


class StudyContracts(unittest.TestCase):
    def test_kl_is_full_distribution_shift_invariant_and_directional(self):
        source=np.array([[1.,2.,-1.],[4.,0.,-2.]])
        same=fidelity(source,source+99)
        self.assertAlmostEqual(same['mean_kl_nats'],0.,places=12)
        self.assertEqual(same['top1_agreement'],1.)
        changed=fidelity(source,source[:,::-1])
        self.assertGreater(changed['mean_kl_nats'],1.)
        self.assertEqual(changed['top1_agreement'],.5)
        self.assertEqual(changed['positions'],2)
        with self.assertRaises(ValueError):fidelity(source,np.zeros((1,3)))

    def test_selection_requires_both_prespecified_gates_and_ignores_qa(self):
        baseline={'mean_kl_nats':1.,'top1_agreement':.7}
        rows={'small_gain':{'mean_kl_nats':.95,'top1_agreement':.8},
              'bad_top1':{'mean_kl_nats':.1,'top1_agreement':.64},
              'accepted':{'mean_kl_nats':.4,'top1_agreement':.7}}
        self.assertEqual(select_candidate(baseline,rows)['winner'],'accepted')
        self.assertIsNone(select_candidate(baseline,{'bad_top1':rows['bad_top1']})['winner'])

    def test_numeric_and_exact_scoring_rejects_wrong_extra_answer(self):
        fact={'rule':{'pattern':r'\b(three|3)\b','numbers':[3]}}
        self.assertTrue(score_answer(fact,'A triangle has three sides.'))
        self.assertFalse(score_answer(fact,'It has three or four sides.'))
        self.assertFalse(score_answer(fact,'It has 3.5 sides.'))
        exact={'rule':{'exact':'silver'}}
        self.assertTrue(score_answer(exact,' silver\n'))
        self.assertFalse(score_answer(exact,'silver.'))

    def test_protocol_cannot_be_silently_overwritten(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.local') as d:
            p=pathlib.Path(d)/'protocol.json'
            freeze(p,{'tokens':[1,2]});before=p.read_bytes()
            freeze(p,{'tokens':[1,2]})
            self.assertEqual(p.read_bytes(),before)
            with self.assertRaises(ValueError):freeze(p,{'tokens':[1,3]})


if __name__=='__main__':unittest.main()
