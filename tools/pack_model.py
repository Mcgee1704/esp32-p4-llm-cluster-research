"""Convert a tied-embedding llama2.c FP32 checkpoint to the P4LM INT8 format."""
import argparse
import hashlib
import json
import pathlib
import struct
import sys
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'.local/tooling/host'))
import numpy as np


def pack(source, tokenizer, output):
    raw = source.read_bytes()
    if len(raw) < 28:
        raise ValueError('checkpoint header truncated')
    d, h, n, heads, kvh, vocab, ctx = struct.unpack_from('<7i', raw)
    if not (0 < d <= 1024 and d % 4 == 0 and 0 < h <= 4096 and h % 4 == 0
            and 0 < n <= 32 and 0 < heads <= d and 0 < kvh <= heads
            and heads % kvh == 0 and d % heads == 0 and (d//heads) % 2 == 0
            and 259 <= vocab <= 65536 and 0 < ctx <= 1024):
        raise ValueError('unsupported model dimensions (tied embeddings required)')
    kd = d*kvh//heads
    shapes = [(vocab,d),(n,d),(n,d,d),(n,kd,d),(n,kd,d),(n,d,d),
              (n,d),(n,h,d),(n,d,h),(n,h,d),(d,)]
    offset, arrays = 28, []
    for shape in shapes:
        count = int(np.prod(shape)); end = offset+count*4
        if end > len(raw):
            raise ValueError('checkpoint weights truncated')
        a = np.frombuffer(raw, dtype='<f4', count=count, offset=offset).reshape(shape)
        if not np.isfinite(a).all():
            raise ValueError('non-finite weights')
        arrays.append(a); offset = end
    if len(raw) != offset + ctx*(d//heads)*4:
        raise ValueError('unexpected legacy checkpoint size or untied classifier')
    emb, na, q, k, v, o, nf, w1, w2, w3, final = arrays
    parts = []
    def matrix(w):
        scales = np.max(np.abs(w), axis=1).astype('<f4') / np.float32(127)
        scales[scales == 0] = 1
        quant = np.clip(np.rint(w/scales[:,None]), -127, 127).astype('i1')
        parts.extend([scales.tobytes(), quant.tobytes()])
    matrix(emb)
    for i in range(n):
        parts.extend([na[i].tobytes(), nf[i].tobytes()])
        for w in (q,k,v,o,w1,w2,w3):
            matrix(w[i])
    parts.append(final.tobytes())
    weights = b''.join(parts)
    tok = tokenizer.read_bytes()
    # Parse the entire tokenizer before producing a flashable artifact.
    if len(tok) < 4 or not 0 < struct.unpack_from('<i',tok)[0] <= 512:
        raise ValueError('invalid tokenizer header')
    pos = 4
    for _ in range(vocab):
        if pos+8 > len(tok):
            raise ValueError('tokenizer truncated')
        score, length = struct.unpack_from('<fi',tok,pos); pos += 8
        if not np.isfinite(score) or not 0 < length <= 512 or pos+length > len(tok) or b'\x00' in tok[pos:pos+length]:
            raise ValueError('invalid tokenizer entry')
        pos += length
    if pos != len(tok):
        raise ValueError('tokenizer vocabulary mismatch')
    body = weights + tok
    if len(body)+128 > 24*1024*1024:
        raise ValueError('model exceeds 24 MiB internal model partition')
    header = bytearray(128)
    struct.pack_into('<8s10I', header, 0, b'P4LM0001', d,h,n,heads,kvh,vocab,ctx,len(weights),len(tok),0)
    header[48:80] = hashlib.sha256(bytes(header[:48])+body).digest()
    struct.pack_into('<I',header,80,zlib.crc32(body))
    result = bytes(header)+body
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)
    report = {'format':'P4LM0001','quantization':'row-wise symmetric int8 weights, FP32 activations',
              'source_sha256':hashlib.sha256(raw).hexdigest(),'tokenizer_sha256':hashlib.sha256(tok).hexdigest(),
              'artifact_sha256':hashlib.sha256(result).hexdigest(),'model_id_sha256':header[48:80].hex(),
              'bytes':len(result),'weights_bytes':len(weights),'tokenizer_bytes':len(tok),
              'dimensions':dict(zip(['dim','hidden','layers','heads','kv_heads','vocab','context'],[d,h,n,heads,kvh,vocab,ctx])),
              'kv_bytes':2*n*ctx*kd*4}
    output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('checkpoint',type=pathlib.Path); p.add_argument('tokenizer',type=pathlib.Path); p.add_argument('output',type=pathlib.Path)
    args=p.parse_args()
    try:
        pack(args.checkpoint,args.tokenizer,args.output)
    except (ValueError,OSError) as e:
        p.exit(1,str(e)+'\n')
