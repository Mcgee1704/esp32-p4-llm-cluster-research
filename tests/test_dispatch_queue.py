"""Exercise the actual portable firmware queue; its caller serializes access."""
import ctypes as C
import pathlib
import unittest

class Entry(C.Structure):
    _fields_ = [('sequence', C.c_uint64), ('created_ms', C.c_int64), ('state', C.c_int), ('lane', C.c_int)]

class Queue(C.Structure):
    _fields_ = [('sequence', C.c_uint64), ('entries', Entry*8)]

class DispatchQueueTests(unittest.TestCase):
    def setUp(self):
        path = pathlib.Path(__file__).resolve().parents[1]/'.local/build/dispatch_queue.dll'
        self.assertTrue(path.exists(), 'Portable dispatcher not implemented')
        self.lib = C.CDLL(str(path))
        self.lib.dq_submit.argtypes = [C.POINTER(Queue), C.c_int64]
        self.lib.dq_claim.argtypes = [C.POINTER(Queue), C.c_int]
        self.lib.dq_finish.argtypes = [C.POINTER(Queue), C.c_int, C.c_int]
        self.lib.dq_cancel.argtypes = [C.POINTER(Queue), C.c_int]
        self.lib.dq_expire.argtypes = [C.POINTER(Queue), C.c_int64, C.c_int64]
        self.q = Queue()

    def test_two_lanes_claim_fifo_without_duplicate_assignment(self):
        for t in [10, 20, 30]: self.lib.dq_submit(C.byref(self.q), t)
        self.assertEqual(self.lib.dq_claim(C.byref(self.q), 0), 0)
        self.assertEqual(self.lib.dq_claim(C.byref(self.q), 1), 1)
        self.assertEqual(self.q.entries[0].state, 2)
        self.lib.dq_finish(C.byref(self.q), 0, 3)
        self.assertEqual(self.lib.dq_claim(C.byref(self.q), 0), 2)
        self.assertEqual(self.lib.dq_claim(C.byref(self.q), 1), -1)

    def test_capacity_never_evicts_active_and_reclaims_oldest_terminal(self):
        for i in range(8): self.assertEqual(self.lib.dq_submit(C.byref(self.q), i), i)
        self.assertEqual(self.lib.dq_submit(C.byref(self.q), 9), -1)
        self.lib.dq_claim(C.byref(self.q), 0)
        self.assertEqual(self.lib.dq_cancel(C.byref(self.q), 0), -1)
        self.assertEqual(self.lib.dq_cancel(C.byref(self.q), 4), 0)
        self.assertEqual(self.lib.dq_cancel(C.byref(self.q), 2), 0)
        self.assertEqual(self.lib.dq_submit(C.byref(self.q), 10), 2)
        self.assertEqual(self.q.entries[0].state, 2)

    def test_deadline_only_expires_waiting_jobs(self):
        self.lib.dq_submit(C.byref(self.q), 0)
        self.lib.dq_submit(C.byref(self.q), 1)
        self.lib.dq_claim(C.byref(self.q), 0)
        self.lib.dq_expire(C.byref(self.q), 200, 100)
        self.assertEqual(self.q.entries[0].state, 2)
        self.assertEqual(self.q.entries[1].state, 4)
        self.assertEqual(self.lib.dq_claim(C.byref(self.q), 1), -1)

    def test_invalid_transitions_are_rejected(self):
        self.assertEqual(self.lib.dq_finish(C.byref(self.q), 0, 3), -1)
        self.assertEqual(self.lib.dq_cancel(C.byref(self.q), -1), -1)
        self.lib.dq_submit(C.byref(self.q), 0)
        self.assertEqual(self.lib.dq_finish(C.byref(self.q), 0, 3), -1)
        self.lib.dq_claim(C.byref(self.q), 0)
        self.assertEqual(self.lib.dq_finish(C.byref(self.q), 0, 1), -1)
