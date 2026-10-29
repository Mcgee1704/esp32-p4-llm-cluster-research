"""Download public model assets only; never sends project files or device data."""
import hashlib
import json
import pathlib
import urllib.request

root = pathlib.Path(__file__).resolve().parents[1]
dest = root/'.local/models'
dest.mkdir(parents=True,exist_ok=True)
revision='0bd21da7698eaf29a0d7de3992de8a46ef624add'
sources={
    'stories15M.bin':f'https://huggingface.co/karpathy/tinyllamas/resolve/{revision}/stories15M.bin',
    'tokenizer.bin':'https://raw.githubusercontent.com/karpathy/llama2.c/350e04fe35433e6d2941dce5a1f53308f87058eb/tokenizer.bin',
    'model-card.md':f'https://huggingface.co/karpathy/tinyllamas/resolve/{revision}/README.md',
}
report={}
expected={
    'stories15M.bin':'cd590644d963867a2b6e5a1107f51fad663c41d79c149fbecbbb1f95fa81f49a',
    'tokenizer.bin':'50a52ef822ee9e83de5ce9d0be0a025a773d019437f58b5ff9dcafb063ece361',
    'model-card.md':'f5d36081d79fc18b2b8ee80fbf05f307c30ea8d6f3ce605c3f393be29f7d8863',
}
for name,url in sources.items():
    target=dest/name
    if not target.exists():
        temp=target.with_suffix(target.suffix+'.download')
        with urllib.request.urlopen(url,timeout=120) as r,temp.open('wb') as f:
            while chunk:=r.read(1024*1024): f.write(chunk)
        if hashlib.sha256(temp.read_bytes()).hexdigest()!=expected[name]:
            raise ValueError('Downloaded asset hash mismatch: '+name)
        temp.replace(target)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    if digest!=expected[name]:raise ValueError('Existing asset hash mismatch: '+name)
    report[name]={'url':url,'sha256':digest,'bytes':target.stat().st_size}
(dest/'sources.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
