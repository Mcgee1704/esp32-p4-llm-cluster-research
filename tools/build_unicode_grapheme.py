"""Export Unicode16 grapheme properties from pinned unicode-segmentation1.12.0.

Input is a local copy of the MIT/Apache-2.0 author tables.rs; no network calls.
Only property data are derived, not the Rust segmenter implementation.
"""
import argparse
import hashlib
import json
import pathlib
import re

def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=pathlib.Path);a=p.parse_args();raw=a.source.read_bytes();s=raw.decode()
    cats=['Any','CR','Control','Extend','Extended_Pictographic','InCB_Consonant','L','LF','LV','LVT','Prepend','Regional_Indicator','SpacingMark','T','V','ZWJ']
    values=bytearray(0x110000)
    body=s.split('const grapheme_cat_table:',1)[1].split('\n    ];',1)[0]
    entries=re.findall(r"\('\\u\{([0-9a-f]+)\}',\s*'\\u\{([0-9a-f]+)\}',\s*GC_(\w+)\)",body)
    assert len(entries)>1000
    for lo,hi,c in entries:values[int(lo,16):int(hi,16)+1]=bytes([cats.index(c)])*(int(hi,16)-int(lo,16)+1)
    body=s.split('const InCB_Extend_table:',1)[1].split('\n    ];',1)[0]
    for lo,hi in re.findall(r"\('\\u\{([0-9a-f]+)\}',\s*'\\u\{([0-9a-f]+)\}'\)",body):
        for i in range(int(lo,16),int(hi,16)+1):values[i]|=32
    for i in [0x94d,0x9cd,0xacd,0xb4d,0xc4d,0xd4d]:values[i]|=64
    for lo,hi in [(9,13),(32,32),(0x85,0x85),(0xa0,0xa0),(0x1680,0x1680),(0x2000,0x200a),(0x2028,0x2029),(0x202f,0x202f),(0x205f,0x205f),(0x3000,0x3000)]:
        for i in range(lo,hi+1):values[i]|=128
    ranges=[];start=0
    for i in range(1,len(values)+1):
        if i==len(values) or values[i]!=values[start]:
            if values[start]:ranges.append([start,i-1,values[start]])
            start=i
    out=pathlib.Path(__file__).resolve().parent/'data/unicode-grapheme-16.json';out.parent.mkdir(exist_ok=True)
    x={'unicode':'16.0.0','source':'https://github.com/unicode-rs/unicode-segmentation/blob/v1.12.0/src/tables.rs',
       'source_sha256':hashlib.sha256(raw).hexdigest(),'license':'MIT; notice in firmware/components/tinyllm/UNICODE-LICENSE.txt','categories':cats,'ranges':ranges}
    out.write_bytes((json.dumps(x,separators=(',',':'))+'\n').encode());print(len(ranges),'ranges',out.stat().st_size,'bytes')

if __name__=='__main__':main()
