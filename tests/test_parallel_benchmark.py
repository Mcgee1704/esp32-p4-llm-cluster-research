"""Check throughput/overlap arithmetic against hand-calculated timelines."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'tools'))


class ParallelMeasurementTests(unittest.TestCase):
    def test_parallel_and_serial_wall_time_are_not_sum_of_device_times(self):
        from benchmark_parallel import batch_metrics
        parallel = [{'start_ms': 0, 'end_ms': 1000, 'tokens': [1]*24},
                    {'start_ms': 100, 'end_ms': 1100, 'tokens': [1]*24}]
        result = batch_metrics(parallel, 1100)
        self.assertAlmostEqual(result['overlap_ms'], 900)
        self.assertAlmostEqual(result['tokens_per_second'], 48/1.1)
        self.assertAlmostEqual(result['mean_completion_ms'], 1050)
        self.assertAlmostEqual(result['mean_request_ms'], 1000)
        self.assertEqual(result['start_skew_ms'], 100)
        serial = [{'start_ms': 0, 'end_ms': 1000, 'tokens': [1]*24},
                  {'start_ms': 1000, 'end_ms': 2000, 'tokens': [1]*24}]
        result = batch_metrics(serial, 2000)
        self.assertEqual(result['overlap_ms'], 0)
        self.assertEqual(result['tokens_per_second'], 24)
        self.assertEqual(result['mean_completion_ms'], 1500)

    def test_invalid_timing_cannot_produce_a_speedup(self):
        from benchmark_parallel import batch_metrics
        with self.assertRaises(ValueError):
            batch_metrics([{'start_ms': 10, 'end_ms': 5, 'tokens': [1]}], 10)
        with self.assertRaises(ValueError):
            batch_metrics([{'start_ms': 0, 'end_ms': 20, 'tokens': [1]}], 10)
