import copy
import json
import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from simulate_cluster import DATA,fit,simulate

class ClusterSimulationTests(unittest.TestCase):
    def test_validation_values_cannot_change_fit(self):
        rows=json.loads(DATA.read_text(encoding='utf-8'));before=fit(rows)
        poisoned=copy.deepcopy(rows)
        for row in poisoned:
            if row['dataset']=='validation':
                row['backend_elapsed_ms']=99999999;row['forwarding_residual_ms']=-100000
        self.assertEqual(before,fit(poisoned))

    def test_fifo_and_parallel_intervals_for_hand_calculated_example(self):
        model={'coefficients_ms':[100,0,0],'initial_probe_ms':{'local':0,'worker':0},
               'forwarding_ms':{'local':0,'worker':0},'refill_gap_ms':{'local':0,'worker':0}}
        jobs=[{'case_index':i,'accepted_master_ms':0,'prompt_tokens':1,'output_tokens':1} for i in range(6)]
        self.assertEqual(simulate(model,jobs,1)['makespan_ms'],600)
        self.assertEqual(simulate(model,jobs,2)['makespan_ms'],300)
        result=simulate(model,jobs,3)
        self.assertEqual(result['makespan_ms'],200)
        self.assertEqual([r['lane'] for r in result['jobs']],[0,1,2,0,1,2])

    def test_arrivals_respected_and_invalid_scenario_rejected(self):
        model=fit(json.loads(DATA.read_text(encoding='utf-8')))
        jobs=[{'case_index':0,'accepted_master_ms':10,'prompt_tokens':5,'output_tokens':8},
              {'case_index':1,'accepted_master_ms':10000,'prompt_tokens':5,'output_tokens':8}]
        result=simulate(model,jobs,2)
        self.assertGreaterEqual(result['jobs'][1]['start_ms'],9990)
        with self.assertRaises(ValueError):simulate(model,jobs,0)
