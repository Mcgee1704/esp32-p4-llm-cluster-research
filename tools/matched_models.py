"""Offline admission, frozen common prompts and native references for four models."""
import argparse
import ctypes
import hashlib
import json
import math
import pathlib
import struct
import sys
import time

from tinytalk_reference import (ROOT, np, audited_config, tensor_shapes,
                               unique_object, Reference, row_int8)
from pack_gptneo import pack, real_tokenizer
from check_gptneo_native import Native

DATA = ROOT / 'data/matched-models-2026-10-29'
MODELS = {
    'sft': {'name': 'TinyStories-15M SFT', 'repository': '0rn0/llama2-15m-tinystories-sft',
            'artifact': '.local/models/llama2-15m-sft-4d69f1c13019/stories15M-sft.p4lm'},
    'story8': {'name': 'TinyStories-Instruct-8M', 'repository': 'roneneldan/TinyStories-Instruct-8M',
               'revision': '18d7c83c2d7b0685b0da3c26379dd4d4d90a1ffb', 'hidden': 256,
               'weights_sha256': '4d625b61fae5ca897e037b702e5774598eace89720be23a4bcce68d4cb0b665b',
               'artifact': '.local/models/story8.p4gn', 'legacy_masks': True},
    'talk1': {'name': 'TinyTalk 1', 'repository': 'TheREZOR/TinyTalk',
              'revision': '61c79ad139344cdd344a687b35fa8f1c52326154', 'hidden': 128,
              'weights_sha256': 'd7510ceac1d4f2a7d00b6f2da92cdce38706faa60a96c60884819d00ef58af77',
              'artifact': '.local/models/talk1.p4gn', 'legacy_masks': False},
    'talk2': {'name': 'TinyTalk-2', 'repository': 'TheREZOR/TinyTalk-2',
              'revision': '2b55040281013975a4d97e3db8d634f78b31c6b1', 'hidden': 256,
              'weights_sha256': '40e10ee793e157f09fb94d2926db9aa3f81d42814249f1c1db023b7027f17567',
              'artifact': '.local/models/tinytalk2.p4gn', 'legacy_masks': False},
}

STORIES = [
    ('S1', 'Once upon a time, a rabbit named Pip had a carrot. His friend Fox was hungry. Pip decided to share',
     ['rabbit and hungry friend', 'sharing food']),
    ('S2', 'Mia had a broken kite. She wanted to fly it again. She took some string and',
     ['Mia and kite', 'repair or attempt to fly']),
    ('S3', 'Lily could not find her cat, Luna. She looked in the garden. Then she heard',
     ['Lily and missing cat', 'search or discovery']),
    ('S4', 'Ben built a sandcastle by the sea. A big wave came and washed it away. Ben felt',
     ['Ben and lost sandcastle', 'reaction to loss']),
]
CASES = [{'id': i, 'category': 'story', 'prompt': p, 'limit': 128, 'rubric_topic': r}
         for i, p, r in STORIES]
QUESTIONS = [
    ('Q1', 'What sound does a cow make? Answer in one short sentence.', ['moo']),
    ('Q2', 'What color is a ripe banana? Answer in one short sentence.', ['yellow']),
    ('Q3', 'How many wheels does a bicycle usually have? Answer in one short sentence.', ['two', '2']),
    ('Q4', 'What is a baby dog called?', ['puppy']),
    ('Q5', 'What is the opposite of hot?', ['cold']),
    ('Q6', 'How many legs does a cat have?', ['four', '4']),
]
CASES += [{'id': i, 'category': 'question', 'prompt': 'User: ' + p + '\nBot:',
           'limit': 32, 'expected': a} for i, p, a in QUESTIONS]
CASES += [
    {'id': 'I1', 'category': 'instruction', 'prompt': 'User: Reply with exactly this word: blue\nBot:',
     'limit': 32, 'exact': 'blue'},
    {'id': 'I2', 'category': 'instruction', 'prompt': 'User: Write exactly three words: red green blue\nBot:',
     'limit': 32, 'exact': 'red green blue'},
    {'id': 'I3', 'category': 'instruction', 'prompt': 'User: Write one short sentence about rain. Do not mention animals.\nBot:', 'limit': 32},
    {'id': 'C2', 'category': 'memory', 'prompt': "User: My cat is called Luna.\nBot: Luna is a nice name.<|endoftext|>\nUser: What is my cat's name?\nBot:", 'limit': 32},
    {'id': 'U1', 'category': 'unknown', 'prompt': 'User: What is the serial number of the board on my desk?\nBot:', 'limit': 32},
    {'id': 'D1', 'category': 'language-boundary', 'prompt': 'User: Welche Farbe hat eine reife Banane?\nBot:', 'limit': 32},
]


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def write(path, value):
    pathlib.Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')


def directory(key):
    m = MODELS[key]
    label = 'tinytalk2' if key == 'talk2' else key
    return ROOT / '.local/models' / (label + '-' + m['revision'][:12])


def normalize_config(c, hidden):
    expected = audited_config()
    expected['hidden_size'] = hidden
    if hidden not in (128, 256):
        raise ValueError('Unreviewed hidden size')
    normalized = {**c, 'tie_word_embeddings': c.get('tie_word_embeddings', True)}
    if any(normalized.get(k) != v for k, v in expected.items()):
        raise ValueError('Unsupported GPT-Neo semantics or dimensions')
    return {**normalized, 'intermediate_size': hidden * 4}


def validate_mask(mask, positions, window):
    if mask.shape != (1, 1, positions, positions):
        raise ValueError('Unexpected mask shape')
    p = np.arange(positions)
    distance = p[:, None] - p[None, :]
    expected = distance >= 0
    if window is not None:
        expected &= distance < window
    if not np.array_equal(mask[0, 0], expected.astype('uint8')):
        raise ValueError('Attention mask does not match runtime semantics')


def load_candidate(key):
    m = MODELS[key]
    c = normalize_config(json.loads((directory(key) / 'config.json').read_text()), m['hidden'])
    path = directory(key) / 'model.safetensors'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != m['weights_sha256']:
        raise ValueError('Pinned source hash mismatch')
    size = struct.unpack_from('<Q', raw)[0]
    if not 0 < size <= 1024 * 1024 or size + 8 > len(raw):
        raise ValueError('Invalid Safetensors header')
    header = json.loads(raw[8:8 + size], object_pairs_hook=unique_object)
    body = memoryview(raw)[8 + size:]
    expected = tensor_shapes(c)
    extra = {}
    if m['legacy_masks']:
        for i in range(c['num_layers']):
            p = f'transformer.h.{i}.attn.attention.'
            extra[p + 'masked_bias'] = ('F32', ())
            extra[p + 'bias'] = ('BOOL', (1, 1, 2048, 2048))
    if set(header) - {'__metadata__'} != set(expected) | set(extra):
        raise ValueError('Unexpected or missing tensor')
    result = {}
    ranges = []
    for name, entry in header.items():
        if name == '__metadata__':
            continue
        dtype, shape = extra.get(name, ('F32', expected.get(name)))
        if set(entry) != {'dtype', 'shape', 'data_offsets'} or entry['dtype'] != dtype or tuple(entry['shape']) != shape:
            raise ValueError('Tensor type/shape mismatch: ' + name)
        offsets = entry['data_offsets']
        if len(offsets) != 2 or any(type(n) is not int for n in offsets):
            raise ValueError('Invalid tensor offsets')
        start, end = offsets
        if not 0 <= start < end <= len(body) or end - start != math.prod(shape) * (4 if dtype == 'F32' else 1):
            raise ValueError('Invalid tensor byte range')
        ranges.append((start, end))
        w = np.frombuffer(body[start:end], dtype='<f4' if dtype == 'F32' else 'uint8').reshape(shape)
        if dtype == 'F32' and not np.isfinite(w).all():
            raise ValueError('Non-finite tensor')
        if name in expected:
            result[name] = w
        elif name.endswith('masked_bias'):
            if float(w) != -1e9:
                raise ValueError('Unexpected mask sentinel')
        else:
            layer = int(name.split('.')[2])
            validate_mask(w, 2048, c['window_size'] if c['attention_layers'][layer] == 'local' else None)
    ranges.sort()
    if not ranges or ranges[0][0] != 0 or ranges[-1][1] != len(body) or any(a[1] != b[0] for a, b in zip(ranges, ranges[1:])):
        raise ValueError('Tensor overlap, gap or unaccounted bytes')
    return c, result


def prepare():
    if (DATA / 'protocol.json').exists():
        raise ValueError('Protocol already frozen')
    exports = {}
    for key in MODELS:
        m = MODELS[key]
        path = ROOT / m['artifact']
        if key in ['story8', 'talk1']:
            c, t = load_candidate(key)
            # Reuse the already measured backend table after comparing tokenizers.
            ranges = directory('talk2') / 'bytelevel-unicode-ranges.json'
            if ranges.exists():
                (directory(key) / ranges.name).write_bytes(ranges.read_bytes())
            vocab, merges, classes = real_tokenizer(directory(key))
            path.write_bytes(pack(c, t, vocab, merges, classes))
        raw = path.read_bytes()
        exports[key] = {**{k: v for k, v in m.items() if k != 'artifact'},
                        'artifact_bytes': len(raw), 'artifact_sha256': hashlib.sha256(raw).hexdigest(),
                        'model_id': raw[48:80].hex(), 'dimensions': list(struct.unpack_from('<7I', raw, 8))}
        if key != 'sft':
            c, t = load_candidate(key)
            exports[key]['actual_parameters'] = sum(w.size for w in t.values())
        print('Admitted', key, len(raw), flush=True)
    write(DATA / 'exports.json', exports)
    protocol = {'date': '2026-10-29', 'models': exports, 'cases': CASES,
        'sampling': 'greedy', 'context': 256, 'precision': 'row INT8, full vocabulary, FP32 activations/KV',
        'input_control': 'Identical UTF-8 prompt bytes and caps for all four models. Story continuation, not ending instruction. Chat wrapper is native to TinyTalk, not SFT.',
        'hypotheses': ['Story objective may preserve coherent continuation without improving Q&A.',
                       'TinyTalk-2 may improve Q&A versus TinyTalk 1, confounded by both size and training changes.',
                       'Independent request dispatch should increase aggregate throughput without changing outputs.'],
        'rubric': {'story': {'topic_continuity': '0 absent/wrong; 1 partial; 2 both listed topic components continued',
                             'coherence': '0 contradictory/incoherent; 1 noticeable contradiction or unexplained shift; 2 no material contradiction in visible text',
                             'narrated_resolution': '0 no resolution; 1 visible narrative resolution (EOS alone insufficient)'},
                   'question': 'First substantive factual answer correct, not mere lexical presence. Q1-Q3 also score one-short-sentence format.',
                   'instruction': 'I1/I2 stripped exact case-insensitive full output. I3 one short rain sentence, no animals.',
                   'memory_unknown_language': 'Descriptive manual inspection, no aggregate assistant claim.'},
        'quality_limits': 'One greedy generation per model/task, same unblinded assistant rates all. Elementary facts/subjects may overlap training. No held-out or statistical-quality claim.',
        'hardware': {'firmware': '0.5.5', 'kernel': 'tile4', 'one_board': 'All 16 cases on peer after known control and model-ID check',
                     'benchmark_cases': ['S1', 'S2'], 'benchmark_output_cap': 24, 'paired_blocks': 4,
                     'modes': ['master only two jobs', 'master plus one peer two jobs'],
                     'order': 'AB/BA alternates by block; models SFT, story8, talk1, talk2 (not randomized)',
                     'timing': 'Master monotonic created-to-last-finished package time; includes queue/prefill/transport. Actual outputs, tokens/s and Unicode characters/s.',
                     'restoration': 'TinyTalk-2 on both; peer configured; no active jobs'},
        'script_sha256': {p: sha(ROOT / 'tools' / p) for p in ['matched_models.py', 'pack_gptneo.py', 'tinytalk_reference.py', 'check_gptneo_native.py']}}
    write(DATA / 'protocol.json', protocol)
    (DATA / 'protocol.sha256').write_text(sha(DATA / 'protocol.json') + '\n')
    print('PROTOCOL FROZEN', sha(DATA / 'protocol.json'), flush=True)


def frozen():
    if sha(DATA / 'protocol.json') != (DATA / 'protocol.sha256').read_text().strip():
        raise ValueError('Frozen protocol changed')
    p = json.loads((DATA / 'protocol.json').read_text())
    for name, digest in p['script_sha256'].items():
        if sha(ROOT / 'tools' / name) != digest:
            raise ValueError('Script changed: ' + name)
    for key, model in p['models'].items():
        if sha(ROOT / MODELS[key]['artifact']) != model['artifact_sha256']:
            raise ValueError('Artifact changed')
    return p


def host():
    p = frozen()
    if (DATA / 'host.json').exists():
        raise ValueError('Refusing to overwrite host outputs')
    rows = []
    checks = []
    for key, model in p['models'].items():
        engine = Native(ROOT / MODELS[key]['artifact'])
        try:
            if key != 'sft':
                sys.path.insert(0, str(ROOT / '.local/tooling/tinytalk-host'))
                from tokenizers import Tokenizer
                tok = Tokenizer.from_file(str(directory(key) / 'tokenizer.json'))
                pieces_equal = all(engine.piece(i) == tok.decode([i], skip_special_tokens=False).encode('utf-8')
                                   for i in range(engine.vocab) if i < 256 and len(engine.piece(i)) == 1 and engine.piece(i)[0] < 128)
                # Full byte-piece equality is tested against the explicit byte alphabet;
                # decoding individual partial UTF-8 tokens through a text API is lossy.
                vocab, _, _ = real_tokenizer(directory(key))
                pieces_equal &= all(engine.piece(i) == v for i, v in enumerate(vocab))
                if not pieces_equal:
                    raise ValueError('Token piece mismatch')
                for case in CASES:
                    if engine.encode(case['prompt']) != tok.encode(case['prompt'], add_special_tokens=False).ids:
                        raise ValueError('Tokenizer mismatch')
                c, t = load_candidate(key)
                ref = Reference(c, row_int8(t))
                engine.lib.ts_reset(engine.state)
                ids = engine.encode(CASES[0]['prompt'])
                max_error = 0.
                argmax = True
                for i, token in enumerate(ids):
                    expected = ref.step(token)
                    if i in [0, len(ids) // 2, len(ids) - 1]:
                        actual = engine.forward(token, i)
                        max_error = max(max_error, float(np.max(np.abs(expected - actual))))
                        argmax &= int(np.argmax(expected)) == int(np.argmax(actual))
                    else:
                        engine.forward(token, i, finish=False)
                if max_error > .002 or not argmax:
                    raise ValueError('Native/NumPy numerical gate failed')
                checks.append({'model': key, 'positions': 3, 'logits_per_position': engine.vocab,
                               'maximum_absolute_error': max_error, 'argmax_equal': argmax,
                               'all_vocab_pieces_equal': bool(pieces_equal), 'all_16_prompt_encodings_equal': True})
            for case in CASES:
                started = time.monotonic()
                result = engine.generate(case['prompt'], case['limit'])
                rows.append({'model': key, 'case': case['id'], **result,
                             'host_elapsed_s': time.monotonic() - started})
                write(DATA / 'host-progress.json', rows)
                print('HOST', key, case['id'], len(result['tokens']), 'EOS' if result['eos'] else 'CAP', flush=True)
        finally:
            engine.close()
    write(DATA / 'host.json', rows)
    write(DATA / 'numerical-checks.json', checks)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'host'])
    args = parser.parse_args()
    {'prepare': prepare, 'host': host}[args.stage]()
