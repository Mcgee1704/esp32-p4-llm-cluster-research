"""Prevent wrong-model, replay and cross-session activations entering the cache."""
import ctypes as C
import struct
import unittest
import test_inference


class RpcTests(unittest.TestCase):
    setUpClass = classmethod(test_inference.InferenceTests.setUpClass.__func__)
    open_core = test_inference.InferenceTests.open_core
    # Reuse the model fixture; tests below exercise the actual portable dispatcher.
    def test_rpc_identity_sequence_busy_and_end(self):
        lib,new,payload=self.open_core()
        self.assertTrue(hasattr(lib,'rpc_open'), 'cluster dispatcher not implemented')
        lib.rpc_open.argtypes=[C.c_void_p];lib.rpc_open.restype=C.c_void_p
        lib.rpc_close.argtypes=[C.c_void_p]
        lib.rpc_dispatch.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t]
        lib.rpc_active.argtypes=[C.c_void_p]
        state=new()
        lib.ts_set_kernel.argtypes=[C.c_void_p,C.c_int]
        lib.ts_get_kernel.argtypes=[C.c_void_p]
        default_mode=lib.ts_get_kernel(state)
        self.assertGreaterEqual(default_mode,2)
        self.assertEqual(lib.ts_set_kernel(state,0),0)
        worker=lib.rpc_open(state);self.addCleanup(lib.rpc_close,worker)
        model=payload[48:80]
        def call(cmd,session=123,pos=0,split=1,identity=model,values=b''):
            frame=struct.pack('<8I',0x31505250,cmd,session,pos,split,8,len(values),0)+identity+values
            buf=C.create_string_buffer(frame);out=C.create_string_buffer(4096)
            n=lib.rpc_dispatch(worker,buf,len(frame),out,len(out))
            return n,out.raw[:max(0,n)]
        self.assertLess(call(1,identity=bytes(32))[0],0)
        self.assertEqual(call(1)[0],64)
        self.assertEqual(lib.ts_get_kernel(state),default_mode)
        self.assertEqual(lib.rpc_active(worker),1)
        self.assertLess(call(1,session=999)[0],0)
        self.assertLess(call(2,session=999,values=bytes(32))[0],0)
        self.assertLess(call(2,pos=1,values=bytes(32))[0],0)
        self.assertLess(call(2,values=struct.pack('<8f',float('nan'),0,0,0,0,0,0,0))[0],0)
        self.assertEqual(call(2,values=bytes(32))[0],96)
        self.assertLess(call(2,values=bytes(32))[0],0)
        self.assertEqual(call(3)[0],64)
        self.assertEqual(lib.rpc_active(worker),0)
        self.assertEqual(call(1,session=999)[0],64)


if __name__=='__main__': unittest.main()
