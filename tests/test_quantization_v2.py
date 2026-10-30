"""Numerical and byte contracts independent of model-specific answer examples."""
import pathlib
import sys
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from quantization_v2 import group_quantize,dequantize,gptq_quantize,matrix_bytes
from pack_supra import np
from pack_supra import synthetic
from supra_reference import Reference


class QuantizationV2(unittest.TestCase):
    def test_activation_observer_cannot_change_reference_inputs(self):
        cfg,t,*_=synthetic();seen={}
        def observer(name,x):seen.setdefault(name,[]).append(x.copy());x[:]=1000
        plain=Reference(cfg,t);observed=Reference(cfg,t,observer=observer)
        for token in [12,34,56]:np.testing.assert_array_equal(plain.step(token),observed.step(token))
        self.assertEqual(len(seen),15)
        self.assertTrue(all(len(v)==3 for v in seen.values()))
        self.assertEqual(seen['model.layers.0.mlp.down_proj.weight'][0].shape,(16,))

    def test_group_scales_are_stored_precision_and_zero_is_exact(self):
        w=np.array([[-1.,-.3,0,.7,0,0,0,0],[2,3,4,5,-5,-4,-3,-2]],dtype='float32')
        for scheme in ['symmetric','affine']:
            q=group_quantize(w,4,scheme,shrink=(1.,))
            self.assertEqual(q['scale'].dtype,np.dtype('<f2'))
            self.assertTrue(np.isfinite(dequantize(q)).all())
            self.assertEqual(float(dequantize(q)[0,2]),0.)
            self.assertTrue(np.all(dequantize(q)[0,4:]==0))
            self.assertTrue(np.all(q['q']<=15))
            self.assertGreater(matrix_bytes(q),w.size//2)

    def test_affine_can_represent_non_centered_grid_exactly(self):
        w=np.arange(16,dtype='float32')[None,:]
        q=group_quantize(w,16,'affine',shrink=(1.,))
        np.testing.assert_array_equal(dequantize(q),w)
        self.assertEqual(q['zero'].tolist(),[[0]])

    def test_gptq_on_uncorrelated_identity_metric_equals_rounding(self):
        rng=np.random.default_rng(144);w=rng.normal(0,.2,(7,16)).astype('float32')
        q=group_quantize(w,4,'affine');g=gptq_quantize(w,np.eye(16,dtype='float32'),q,blocksize=8)
        np.testing.assert_array_equal(dequantize(q),dequantize(g))

    def test_gptq_preserves_representable_matrix_and_rejects_invalid_inputs(self):
        w=np.tile(np.arange(16,dtype='float32'),(3,1));q=group_quantize(w,16,'affine',shrink=(1.,))
        h=np.eye(16,dtype='float32')+.1
        np.testing.assert_array_equal(dequantize(gptq_quantize(w,h,q)),w)
        for value in [np.array([[np.nan]*16]),np.ones((2,15))]:
            with self.assertRaises(ValueError):group_quantize(value,16,'affine')
        with self.assertRaises(ValueError):gptq_quantize(w,np.eye(4),q)


if __name__=='__main__':unittest.main()
