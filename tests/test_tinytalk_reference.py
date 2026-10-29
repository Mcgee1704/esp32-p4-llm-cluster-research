import json
import importlib.util
import pathlib
import struct
import sys
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.local/tooling/host'))
sys.path.insert(0,str(ROOT/'tools'))
import numpy as np


class TinyTalkReferenceTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('tinytalk_reference'),'GPT-Neo reference is not implemented yet')
        import tinytalk_reference
        return tinytalk_reference

    def blob(self,header,body):
        h=json.dumps(header).encode()
        return struct.pack('<Q',len(h))+h+body

    def test_rejects_duplicate_tensor_names_and_invalid_ranges(self):
        m=self.module()
        entry={'dtype':'F32','shape':[1],'data_offsets':[0,4]}
        h=json.dumps({'w':entry})[:-1]+','+json.dumps('w')+':'+json.dumps(entry)+'}'
        with self.assertRaises(ValueError):m.read_tensors(struct.pack('<Q',len(h))+h.encode()+bytes(4))
        for offsets in [[1,5],[0,3],[0,8]]:
            with self.assertRaises(ValueError):m.read_tensors(self.blob({'w':{**entry,'data_offsets':offsets}},bytes(4)))
        with self.assertRaises(ValueError):m.read_tensors(self.blob({'w':entry,'x':entry},bytes(4)))

    def test_accepts_f32_and_rejects_nonfinite_or_unaccounted_data(self):
        m=self.module();entry={'dtype':'F32','shape':[2],'data_offsets':[0,8]}
        raw=self.blob({'w':entry},struct.pack('<2f',1.25,-2.5))
        np.testing.assert_array_equal(m.read_tensors(raw)['w'],[1.25,-2.5])
        with self.assertRaises(ValueError):m.read_tensors(self.blob({'w':entry},struct.pack('<2f',1,float('nan'))))
        with self.assertRaises(ValueError):m.read_tensors(raw+b'xxxx')

    def test_config_rejects_rope_architecture_or_unverified_neo_changes(self):
        m=self.module();c=m.audited_config()
        self.assertEqual(m.validate_config(c)['hidden_size'],256)
        for field,value in [('model_type','llama'),('activation_function','relu'),('window_size',128),('tie_word_embeddings',False)]:
            with self.assertRaises(ValueError):m.validate_config({**c,field:value})

    def test_attention_is_unscaled_and_local_window_excludes_oldest(self):
        m=self.module()
        q=np.array([[1,1]],dtype=np.float32)
        k=np.array([[[0,0]],[[1,1]]],dtype=np.float32)
        v=np.array([[[0,0]],[[2,4]]],dtype=np.float32)
        expected=np.array([[2,4]],dtype=np.float32)/(1+np.exp(-2))
        np.testing.assert_allclose(m.attend(q,k,v,window=None),expected,rtol=1e-6)
        np.testing.assert_array_equal(m.attend(q,k,v,window=1),[[2,4]])

    def test_cached_forward_matches_batch_with_and_without_row_quantization(self):
        m=self.module();rng=np.random.default_rng(42)
        c={'hidden_size':8,'num_layers':2,'num_heads':2,'intermediate_size':16,'vocab_size':19,
           'max_position_embeddings':12,'window_size':2,'attention_layers':['global','local'],
           'layer_norm_epsilon':1e-5,'eos_token_id':18}
        tensors={name:rng.normal(0,.15,shape).astype('float32') for name,shape in m.tensor_shapes(c).items()}
        for name,a in tensors.items():
            if name.endswith('ln_1.weight') or name.endswith('ln_2.weight') or name=='transformer.ln_f.weight':a[:]=1
        for quantized in [False,True]:
            weights=m.row_int8(tensors) if quantized else tensors
            engine=m.Reference(c,weights);ids=[2,5,1,7,9]
            batch=m.batch_forward(c,weights,ids)
            for position,token in enumerate(ids):
                np.testing.assert_allclose(engine.step(token),batch[position],atol=2e-5,rtol=2e-5)
            with self.assertRaises(ValueError):engine.step(19)
            engine.reset();np.testing.assert_allclose(engine.step(ids[0]),batch[0],atol=2e-5,rtol=2e-5)

    def test_budget_counts_positions_biases_and_full_vocabulary(self):
        m=self.module();c=m.audited_config();shapes=m.tensor_shapes(c)
        b=m.memory_budget(c,tokenizer_bytes=1000000,context=256)
        count=sum(int(np.prod(s)) for s in shapes.values())
        self.assertEqual(count,19702528)
        self.assertEqual(b['parameter_count'],count)
        self.assertEqual(b['kv_bytes'],2*8*256*256*4)
        self.assertEqual(b['artifact_bytes'],128+b['packed_weight_bytes']+1000000)
        self.assertEqual(m.memory_budget(c,1000000,128)['kv_bytes'],b['kv_bytes']//2)

    def test_quantization_error_bound_zero_rows_and_unchanged_vectors(self):
        m=self.module()
        weights={'w':np.array([[0,0,0],[.123,-2.7,1.3]],dtype=np.float32),
                 'bias':np.array([1,2,3],dtype=np.float32)}
        q=m.row_int8(weights)
        np.testing.assert_array_equal(q['w'][0],[0,0,0])
        self.assertLessEqual(float(np.max(np.abs(q['w'][1]-weights['w'][1]))),2.7/127/2+1e-6)
        self.assertIs(q['bias'],weights['bias'])

    def test_context_limit_is_enforced_before_weight_access(self):
        m=self.module();c={'num_layers':0,'num_heads':1,'hidden_size':2,
                          'max_position_embeddings':1,'vocab_size':3,'layer_norm_epsilon':1e-5}
        t={'transformer.wte.weight':np.ones((3,2),dtype=np.float32),
           'transformer.wpe.weight':np.ones((1,2),dtype=np.float32),
           'transformer.ln_f.weight':np.ones(2,dtype=np.float32),
           'transformer.ln_f.bias':np.zeros(2,dtype=np.float32)}
        engine=m.Reference(c,t);engine.step(0)
        with self.assertRaises(ValueError):engine.step(0)
        with self.assertRaises(ValueError):m.batch_forward(c,t,[])


if __name__=='__main__':unittest.main()
