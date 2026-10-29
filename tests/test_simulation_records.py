"""Preserve clock domains and reject corrupt timing samples before simulation."""
import json
import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from capture_queue_workload import record_job

class SimulationRecordTests(unittest.TestCase):
    def sample(self):
        done={'done':True,'output_tokens':1,'prompt_tokens':5,'elapsed_ms':89.5,
              'ttft_ms':30,'kernel':{'mode':'tile4'}}
        job={'id':'example','state':'done','created_ms':100,'started_ms':140,
             'finished_ms':240,'queue_ms':40,'target':'local',
             'raw_ndjson':json.dumps({'token':42})+'\n'+json.dumps(done)+'\n'}
        case={'dataset':'validation','case_index':0,'prompt_index':0,'requested_tokens':8,
              'client_submit_start_ms':2,'client_accept_ms':7}
        return job,case

    def test_separates_queue_service_backend_and_client_clocks(self):
        job,case=self.sample();r=record_job(job,case,123)
        self.assertEqual((r['queue_ms'],r['service_ms'],r['total_ms']),(40,100,140))
        self.assertEqual(r['forwarding_residual_ms'],10.5)
        self.assertEqual(r['client_accept_ms'],7)
        self.assertEqual(r['output_tokens'],1)  # Early EOS is not padded to the limit.
        self.assertEqual(r['dataset'],'validation')

    def test_rejects_negative_service_mismatched_queue_and_failed_jobs(self):
        for field,value in [('finished_ms',120),('queue_ms',30),('state','failed')]:
            job,case=self.sample();job[field]=value
            with self.assertRaises(ValueError):record_job(job,case,123)
