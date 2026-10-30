"""Data-only SPBP0001 for the pinned TinyBrainBot BPE/Metaspace tokenizer."""
import base64
import json
import pathlib
import struct
import hashlib
import zlib

def pack_tokenizer(path):
    t=json.loads(path.read_text('utf-8'));m=t['model'];norm=t['normalizer'];pre=t['pre_tokenizer']
    if m['type']!='BPE' or m['byte_fallback'] or not m['fuse_unk'] or m['unk_token']!='<unk>' or m['ignore_merges'] or m['dropout'] or m['continuing_subword_prefix'] or m['end_of_word_suffix']:raise ValueError('Unsupported BPE')
    if pre!={'type':'Metaspace','replacement':'\u2581','prepend_scheme':'first','split':True} or t['decoder']!=pre or t['post_processor'] is not None:raise ValueError('Unsupported Metaspace')
    seq=norm['normalizers']
    if norm['type']!='Sequence' or len(seq)!=3 or seq[0]['type']!='Precompiled' or seq[1]!={'type':'Strip','strip_left':False,'strip_right':True} or seq[2]!={'type':'Replace','pattern':{'Regex':' {2,}'},'content':'\u2581'}:raise ValueError('Unsupported normalization')
    vocab=[None]*len(m['vocab'])
    for token,i in m['vocab'].items():vocab[i]=token.encode('utf-8')
    if any(not v or len(v)>512 or b'\0' in v for v in vocab):raise ValueError('Invalid vocabulary')
    offsets=[0];strings=b''
    for token in vocab:strings+=token;offsets.append(len(strings))
    merges=[]
    for rank,pair in enumerate(m['merges']):
        a,b=pair.split() if isinstance(pair,str) else pair
        merges.append((m['vocab'][a],m['vocab'][b],rank,m['vocab'][a+b]))
    added=[]
    for x in t['added_tokens']:
        if any(x.get(k) for k in ('single_word','lstrip','rstrip')) or vocab[x['id']]!=x['content'].encode():raise ValueError('Unsupported added token')
        added.append((x['id'],int(x['normalized'])|int(x['special'])<<1))
    chars=sorted((ord(token),i) for token,i in m['vocab'].items() if len(token)==1)
    normalizer=base64.b64decode(seq[0]['precompiled_charsmap'],validate=True)
    data=json.loads((pathlib.Path(__file__).parent/'data/unicode-grapheme-16.json').read_text());ranges=data['ranges']
    head=struct.pack('<8s10I16x',b'SPBP0001',len(vocab),len(merges),len(strings),len(added),len(normalizer),len(ranges),len(chars),1,m['vocab']['<unk>'],m['vocab']['<|end|>'])
    raw=head+struct.pack('<'+'I'*len(offsets),*offsets)+strings;raw+=bytes(-len(raw)%4)
    raw+=b''.join(struct.pack('<4I',*x) for x in sorted(merges))+b''.join(struct.pack('<2I',*x) for x in added)
    raw+=b''.join(struct.pack('<2I',*x) for x in chars)+normalizer;raw+=bytes(-len(raw)%4)
    raw+=b''.join(struct.pack('<3I',*x) for x in ranges)
    return raw


def pack_model(c,tensors,path,split=4,context=256):
    # Reuse frozen row-weight code. Placeholder tokenizer bytes stay in memory
    # and are replaced before any artifact is returned or saved.
    from pack_supra import pack
    t=json.loads(path.read_text('utf-8'));vocab=[None]*len(t['model']['vocab'])
    for token,i in t['model']['vocab'].items():vocab[i]=token.encode('utf-8')
    original=pack(c,tensors,vocab,[],[],[x['id'] for x in t['added_tokens']],split=split,context=context)
    tok=pack_tokenizer(path);full=original['full'];weights=struct.unpack_from('<I',full,36)[0]
    dims=struct.unpack_from('<7I',full,8);meta=full[128:256];arch=struct.unpack_from('<I',meta,36)[0]
    eos,extra=struct.unpack_from('<2I',meta,52);eps,theta=struct.unpack_from('<2f',meta,60)
    canonical=struct.pack('<11I2f',*dims,arch,4,eos,extra,eps,theta)
    identity=hashlib.sha256(canonical+full[256:128+weights]+tok).digest();out={}
    for role,raw in original.items():
        w=struct.unpack_from('<I',raw,36)[0];body=bytearray(raw[128:128+w]);body[:32]=identity
        body+=tok if role!='worker' else b'';head=bytearray(raw[:128]);struct.pack_into('<I',head,40,len(tok) if role!='worker' else 0)
        head[48:80]=hashlib.sha256(head[:48]+body).digest();struct.pack_into('<I',head,80,zlib.crc32(body));out[role]=bytes(head)+body
    return out
