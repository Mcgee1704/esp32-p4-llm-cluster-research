"""Behavior tests: incorrect quantization, RoPE/GQA, cache positions and splitting."""
import ctypes as C
import hashlib
import importlib.util
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.local/tooling/host'))
import numpy as np


def fixture(path, vocab=272):
    rng = np.random.default_rng(42)
    d, h, n, q, kv, v, ctx = 8, 16, 2, 2, 1, vocab, 16
    shapes = [(v, d), (n, d), (n, d, d), (n, 4, d), (n, 4, d),
              (n, d, d), (n, d), (n, h, d), (n, d, h), (n, h, d), (d,)]
    a = [(rng.standard_normal(s) * .15).astype('<f4') for s in shapes]
    for i in [1, 6, 10]:
        a[i] = np.ones(shapes[i], dtype='<f4')
    with path.open('wb') as f:
        f.write(struct.pack('<7i', d, h, n, q, kv, v, ctx))
        for x in a:
            f.write(x.tobytes())
        f.write(bytes(ctx * (d // q) * 4))  # legacy unused RoPE tables
    tokens = ['<unk>', '<s>', '</s>'] + [f'<0x{i:02X}>' for i in range(256)]
    tokens += [' ', 'a', 'b', 'ab']
    tokens += [f'word{i}' for i in range(v-len(tokens))]
    tok = path.with_suffix('.tok')
    with tok.open('wb') as f:
        f.write(struct.pack('<i', 16))
        for text in tokens:
            b = text.encode()
            f.write(struct.pack('<fi', 5.0 if text == 'ab' else 0.0, len(b)) + b)
    return a, tok


def quant_ref(w):
    scale = np.max(np.abs(w), axis=-1, keepdims=True) / 127
    scale[scale == 0] = 1
    return np.clip(np.rint(w / scale), -127, 127).astype(np.int8) * scale


class Reference:
    def __init__(self, a):
        self.a = [quant_ref(x) if i not in (1, 6, 10) else x for i, x in enumerate(a)]
        self.k = np.zeros((2, 16, 4), dtype=np.float32)
        self.v = self.k.copy()

    def forward(self, token, pos):
        emb, na, wq, wk, wv, wo, nf, w1, w2, w3, final = self.a
        x = emb[token].copy()
        norm = lambda x, w: x / np.sqrt(np.mean(x*x)+1e-5) * w
        for l in range(2):
            xb = norm(x, na[l])
            q, k = wq[l] @ xb, wk[l] @ xb
            for i in range(0, 8, 2):
                angle = pos / (10000 ** ((i % 4)/4))
                c, s = np.cos(angle), np.sin(angle)
                q[i:i+2] = [q[i]*c-q[i+1]*s, q[i]*s+q[i+1]*c]
                if i < 4:
                    k[i:i+2] = [k[i]*c-k[i+1]*s, k[i]*s+k[i+1]*c]
            self.k[l, pos] = k
            self.v[l, pos] = wv[l] @ xb
            out = np.zeros(8, dtype=np.float32)
            for head in range(2):
                score = self.k[l, :pos+1] @ q[head*4:head*4+4] / 2
                att = np.exp(score - score.max())
                att /= att.sum()
                out[head*4:head*4+4] = att @ self.v[l, :pos+1]
            x += wo[l] @ out
            xb = norm(x, nf[l])
            z = w1[l] @ xb
            x += w2[l] @ ((z/(1+np.exp(-z))) * (w3[l] @ xb))
        return emb @ norm(x, final)


class InferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.raw = pathlib.Path(cls.tmp.name) / 'fixture.bin'
        cls.arrays, cls.tokenizer = fixture(cls.raw)

    def test_export_and_core_are_available(self):
        self.assertTrue((ROOT/'tools/pack_model.py').is_file(), 'INT8 exporter is not implemented')
        self.assertTrue((ROOT/'.local/build/tinyllm.dll').is_file(), 'portable inference core is not built')

    def open_core(self):
        exporter = ROOT/'tools/pack_model.py'
        self.assertTrue(exporter.is_file(), 'INT8 exporter is not implemented')
        target = pathlib.Path(self.tmp.name)/'fixture.p4lm'
        result = subprocess.run([sys.executable, str(exporter), str(self.raw), str(self.tokenizer), str(target)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = target.read_bytes()
        self.assertEqual(payload[:8], b'P4LM0001')
        self.assertEqual(payload[48:80], hashlib.sha256(payload[:48]+payload[128:]).digest())
        self.assertEqual(struct.unpack_from('<I', payload, 80)[0], zlib.crc32(payload[128:]))
        self.assertTrue((ROOT/'.local/build/tinyllm.dll').is_file(), 'portable core is not built')
        lib = C.CDLL(str(ROOT/'.local/build/tinyllm.dll'))
        lib.ts_open.argtypes = [C.c_void_p, C.c_size_t]
        lib.ts_open.restype = C.c_void_p
        lib.ts_close.argtypes = [C.c_void_p]
        for name in ['ts_x', 'ts_finish']:
            getattr(lib, name).argtypes = [C.c_void_p]
            getattr(lib, name).restype = C.POINTER(C.c_float)
        lib.ts_embed.argtypes = [C.c_void_p, C.c_int]
        lib.ts_layers.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_int]
        lib.ts_reset.argtypes = [C.c_void_p]
        lib.ts_encode.argtypes = [C.c_void_p, C.c_char_p, C.POINTER(C.c_int), C.c_int]
        self.buffers = []
        def new(data=payload):
            b = C.create_string_buffer(data)
            self.buffers.append(b)
            obj = lib.ts_open(b, len(data))
            if obj:
                self.addCleanup(lib.ts_close, obj)
            return obj
        return lib, new, payload

    def test_logits_match_independent_reference_and_split_over_multiple_positions(self):
        lib, new, _ = self.open_core()
        solo, first, last = new(), new(), new()
        self.assertTrue(solo and first and last)
        ref = Reference(self.arrays)
        for pos, token in enumerate([1, 259, 262, 42, 90]):
            self.assertEqual(lib.ts_embed(solo, token), 0)
            self.assertEqual(lib.ts_layers(solo, 0, 2, pos), 0)
            actual = np.ctypeslib.as_array(lib.ts_finish(solo), (272,)).copy()
            np.testing.assert_allclose(actual, ref.forward(token, pos), atol=2e-5, rtol=2e-4)
            self.assertEqual(lib.ts_embed(first, token), 0)
            self.assertEqual(lib.ts_layers(first, 0, 1, pos), 0)
            C.memmove(lib.ts_x(last), lib.ts_x(first), 8*4)
            self.assertEqual(lib.ts_layers(last, 1, 2, pos), 0)
            np.testing.assert_array_equal(actual, np.ctypeslib.as_array(lib.ts_finish(last), (272,)))

    def test_kernel_modes_preserve_exact_logits_and_reject_invalid_modes(self):
        lib, new, _ = self.open_core()
        lib.ts_set_kernel.argtypes = [C.c_void_p, C.c_int]
        lib.ts_set_kernel.restype = C.c_int
        lib.ts_get_kernel.argtypes = [C.c_void_p]
        lib.ts_get_kernel.restype = C.c_int
        lib.ts_work_is_internal.argtypes = [C.c_void_p]
        lib.ts_internal_work_bytes.argtypes = [C.c_void_p]
        lib.ts_internal_work_bytes.restype = C.c_size_t
        states = [new() for _ in range(5)]
        for mode, state in enumerate(states):
            self.assertEqual(lib.ts_set_kernel(state, mode), 0)
            self.assertEqual(lib.ts_set_kernel(state, -1), -1)
            self.assertEqual(lib.ts_set_kernel(state, 99), -1)
            self.assertEqual(lib.ts_get_kernel(state), mode)
            self.assertEqual(lib.ts_work_is_internal(state), mode >= 3)
            if mode >= 3:self.assertEqual(lib.ts_internal_work_bytes(state), 256)
        for pos, token in enumerate([1, 259, 262, 42, 90]):
            outputs = []
            for state in states:
                self.assertEqual(lib.ts_embed(state, token), 0)
                self.assertEqual(lib.ts_layers(state, 0, 2, pos), 0)
                outputs.append(np.ctypeslib.as_array(lib.ts_finish(state), (272,)).copy())
            for output in outputs[1:]: np.testing.assert_array_equal(outputs[0], output)
        class Profile(C.Structure):
            _fields_ = [(name, C.c_uint64) for name in (
                'matmul_us','finish_us','pause_us','pause_calls','rows',
                'helper_us','helper_pause_us','helper_pause_calls','helper_rows','parallel_calls',
                'barrier_us','overlap_us')] + [('owner_core_mask', C.c_uint32),('helper_core_mask', C.c_uint32)]
        lib.ts_get_kernel_profile.argtypes = [C.c_void_p]
        lib.ts_get_kernel_profile.restype = C.POINTER(Profile)
        for mode, state in enumerate(states):
            profile = lib.ts_get_kernel_profile(state).contents
            self.assertEqual(profile.rows, 2000)
            # Vocab=272 splits at 128: verify the uneven 144-row remainder.
            self.assertEqual(profile.helper_rows, 720 if mode >= 2 else 0)
            self.assertEqual(profile.parallel_calls, 5 if mode >= 2 else 0)
            lib.ts_reset(state)
            self.assertEqual(lib.ts_get_kernel_profile(state).contents.rows, 0)
            self.assertEqual(lib.ts_get_kernel_profile(state).contents.helper_rows, 0)
            self.assertEqual(lib.ts_get_kernel(state), mode)

    def test_tile4_tail_and_memory_bank_switch_preserve_active_state(self):
        self.raw = pathlib.Path(self.tmp.name)/'odd-vocab.bin'
        _, self.tokenizer = fixture(self.raw, vocab=275)
        lib, new, _ = self.open_core()
        lib.ts_set_kernel.argtypes = [C.c_void_p, C.c_int]
        ref, switched = new(), new()
        self.assertEqual(lib.ts_set_kernel(ref, 2), 0)
        for pos, token in enumerate([1, 259, 262, 42, 90]):
            self.assertEqual(lib.ts_set_kernel(switched, [4,2,3,0,4][pos]), 0)
            outputs=[]
            for state in [ref, switched]:
                self.assertEqual(lib.ts_embed(state, token), 0)
                self.assertEqual(lib.ts_layers(state, 0, 2, pos), 0)
                if state == switched:
                    self.assertEqual(lib.ts_set_kernel(state, [2,4,2,4,3][pos]), 0)
                outputs.append(np.ctypeslib.as_array(lib.ts_finish(state), (275,)).copy())
            np.testing.assert_array_equal(outputs[0], outputs[1])

    def test_rejects_corruption_invalid_dimensions_and_out_of_order_position(self):
        lib, new, payload = self.open_core()
        broken = bytearray(payload); broken[200] ^= 1
        self.assertFalse(new(bytes(broken)))
        broken = bytearray(payload); struct.pack_into('<I', broken, 8, 0)
        self.assertFalse(new(bytes(broken)))
        self.assertFalse(new(payload[:-4]))
        obj = new()
        self.assertEqual(lib.ts_embed(obj, 272), -1)
        self.assertEqual(lib.ts_layers(obj, 0, 2, 1), -1)
        self.assertEqual(lib.ts_layers(obj, 0, 3, 0), -1)
        self.assertEqual(lib.ts_layers(obj, 0, 2, 0), 0)
        self.assertEqual(lib.ts_layers(obj, 0, 2, 0), -1)
        lib.ts_reset(obj)
        self.assertEqual(lib.ts_layers(obj, 0, 2, 0), 0)

    def test_tokenizer_merges_and_respects_output_capacity(self):
        lib, new, _ = self.open_core()
        obj = new()
        out = (C.c_int*16)()
        n = lib.ts_encode(obj, b'ab', out, 16)
        self.assertEqual(list(out[:n]), [1, 259, 262])
        self.assertEqual(lib.ts_encode(obj, b'abcdefgh', out, 2), -1)


if __name__ == '__main__':
    unittest.main()
