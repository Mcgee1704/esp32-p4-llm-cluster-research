"""Exact FP32 order against an independent packed-byte scalar oracle."""
import ctypes as C
import pathlib
import random
import subprocess
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]


class Int4Pair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir=ROOT/'.local/build')
        cls.addClassCleanup(cls.temp.cleanup)
        path=pathlib.Path(cls.temp.name)
        (path/'probe.c').write_text('#include "int4_dot.h"\nvoid probe(float *out,const unsigned char *q,const float *x,int n){ts_int4_dot4(out,q,q+n/2,q+n,q+3*n/2,x,n);}\n')
        r=subprocess.run([str(ROOT/'.local/tooling/host/ziglang/zig.exe'),'cc','-shared','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-I',str(ROOT/'firmware/components/tinyllm'),str(path/'probe.c'),'-o',str(path/'probe.dll')],capture_output=True,text=True)
        if r.returncode:raise AssertionError('INT4 pair primitive unavailable or rejected: '+r.stderr)
        cls.lib=C.CDLL(str(path/'probe.dll'));cls.lib.probe.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_int]
        if __import__('os').name=='nt':
            def unload():
                import _ctypes
                _ctypes.FreeLibrary(cls.lib._handle)
                del cls.lib
            cls.addClassCleanup(unload)

    def check(self,q,x,n):
        raw=C.create_string_buffer(q);a=(C.c_float*n)(*x);out=(C.c_float*4)()
        self.lib.probe(out,raw,a,n)
        for row in range(4):
            value=0.0
            for j in range(n):
                v=(q[row*n//2+j//2]>>((j%2)*4))&15
                value=C.c_float(value+C.c_float((v if v<8 else v-16)*a[j]).value).value
            self.assertEqual(bytes(C.c_float(out[row])),bytes(C.c_float(value)),(n,row))

    def test_all_packed_byte_values_and_signed_nibbles(self):
        self.check(bytes(range(256))*4,[(j%19-9)/16 for j in range(512)],512)

    def test_production_widths_nonbinary_inputs_and_cancellation(self):
        rng=random.Random(30010)
        for n in [2,6,8,256,768,2048]:
            self.check(bytes(rng.randrange(256) for _ in range(2*n)),[rng.uniform(-3.1,3.1) for _ in range(n)],n)


if __name__=='__main__':unittest.main()
