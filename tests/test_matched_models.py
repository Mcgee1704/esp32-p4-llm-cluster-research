import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from matched_models import validate_mask, normalize_config, CASES
from tinytalk_reference import np, audited_config


class CandidateAdmissionTests(unittest.TestCase):
    def test_global_and_local_mask_are_checked_not_ignored(self):
        pos = np.arange(8)
        distance = pos[:, None] - pos[None, :]
        for local in [False, True]:
            good = ((distance >= 0) & ((distance < 3) if local else True)).astype('uint8')
            validate_mask(good.reshape(1, 1, 8, 8), 8, 3 if local else None)
            bad = good.copy()
            bad[0, 7] = 1
            with self.assertRaises(ValueError):
                validate_mask(bad.reshape(1, 1, 8, 8), 8, 3 if local else None)

    def test_only_reviewed_dimensions_and_semantics_are_admitted(self):
        c = audited_config()
        c.pop('tie_word_embeddings')
        self.assertEqual(normalize_config(c, 256)['intermediate_size'], 1024)
        c['hidden_size'] = 128
        self.assertEqual(normalize_config(c, 128)['intermediate_size'], 512)
        for key, value in [('activation_function', 'relu'), ('num_heads', 8),
                           ('tie_word_embeddings', False), ('hidden_size', 64)]:
            bad = dict(c, **{key: value})
            with self.assertRaises(ValueError):
                normalize_config(bad, 128)

    def test_common_cases_are_fixed_and_unique(self):
        self.assertEqual(len(CASES), 16)
        self.assertEqual(len({c['id'] for c in CASES}), 16)
        self.assertEqual(sum(c['category'] == 'story' for c in CASES), 4)
        self.assertTrue(all(0 < c['limit'] <= 128 for c in CASES))


if __name__ == '__main__':
    unittest.main()
