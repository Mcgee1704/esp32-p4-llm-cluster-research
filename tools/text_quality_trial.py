"""Frozen ten-case English text evaluation, with data-only LAN execution."""
import argparse
import hashlib
import json
import pathlib
import re
from collections import Counter
from benchmark_kernel import request
from dispatch_client import Dispatcher
from textmodel_trial import native,upload,parse
from lan_client import ROOT

def story(case,topic,ending):
    return {'id':case,'category':'story','topic':topic,'ending':ending,'limit':128,
            'prompt':f'Write a story about: {topic}\nWith: {ending} ending\n\n### Story:\n'}

CASES=[story('S1','a rabbit who shares a carrot with a hungry friend','happy'),
       story('S2','a child who repairs a broken kite','happy'),
       story('S3','a girl who cannot find her lost cat','sad'),
       story('S4','a boy whose sandcastle is washed away by the sea','sad'),
       {'id':'Q1','category':'question','limit':32,'expected':['moo'],
        'prompt':'What sound does a cow make? Answer in one short sentence.'},
       {'id':'Q2','category':'question','limit':32,'expected':['yellow'],
        'prompt':'What color is a ripe banana? Answer in one short sentence.'},
       {'id':'Q3','category':'question','limit':32,'expected':['two','2'],
        'prompt':'How many wheels does a bicycle usually have? Answer in one short sentence.'},
       {'id':'I1','category':'instruction','limit':32,'exact':'blue',
        'prompt':'Reply with exactly this word: blue'},
       {'id':'I2','category':'instruction','limit':32,'exact':'red green blue',
        'prompt':'Write exactly three words: red green blue'},
       {'id':'I3','category':'instruction','limit':32,
        'prompt':'Write one short sentence about rain. Do not mention animals.'}]

def indicators(case,text,count):
    words=re.findall(r"[a-z0-9]+(?:'[a-z]+)?",text.lower())
    grams=Counter(tuple(words[i:i+4]) for i in range(max(0,len(words)-3)))
    consecutive=any(words[i]==words[i+1]==words[i+2] for i in range(max(0,len(words)-2)))
    result={'words':len(words),'limit_reached':count==case['limit'],
            'eos_inferred':count<case['limit'],'max_fourgram_occurrences':max(grams.values(),default=0),
            'repetition_flag':consecutive or max(grams.values(),default=0)>=3}
    if 'expected' in case:
        result['answer_signal_in_first_20_words']=any(x in words[:20] for x in case['expected'])
    if 'exact' in case:result['exact_format_pass']=text.strip().lower()==case['exact']
    if case['id']=='I3':
        sentences=[s for s in re.split(r'[.!?]+',text.strip()) if s.strip()]
        animals=re.search(r'\b(dogs?|cats?|birds?|rabbits?|fox(?:es)?|bears?|horses?|mice|mouse|cows?|ducks?|sheep)\b',text,re.I)
        result['restricted_sentence_heuristic_pass']=len(sentences)==1 and 3<=len(words)<=15 and bool(re.search(r'\brains?\b',text,re.I)) and animals is None
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=pathlib.Path)
    p.add_argument('--master',default='10.0.0.121');p.add_argument('--peer',default='10.0.0.131')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    paths={'baseline':ROOT/'.local/models/stories15M.p4lm',
           'sft':ROOT/'.local/models/llama2-15m-sft-4d69f1c13019/stories15M-sft.p4lm'}
    ids={k:v.read_bytes()[48:80].hex() for k,v in paths.items()}
    protocol={'cases':CASES,'model_ids':ids,'sampler':'greedy','order':['sft','baseline'],
              'language':'English','quality_review':'Same assistant, masked model labels per pair; not an independent or fully blinded study',
              'rubric':{'coherence':'0 empty/unintelligible; 1 understandable with major contradictions/repetition; 2 connected understandable English',
                        'story_topic':'0 absent; 1 partial; 2 central topic/action present',
                        'story_ending':'assess only a completed, EOS-ended story; otherwise not assessable',
                        'questions':'manually judge first answer; lexical signal alone is not proof',
                        'instructions':'exact-output rules or rain sentence heuristic plus manual judgement',
                        'repetition':'flag if any fourgram occurs at least three times or a word repeats three times consecutively'},
              'script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}
    raw=(json.dumps(protocol,indent=2)+'\n').encode();(a.output/'protocol.json').write_bytes(raw)
    protocol_hash=hashlib.sha256(raw).hexdigest();print('Protocol frozen:',protocol_hash,flush=True)
    refs={label:{c['id']:native(path,c['prompt'],c['limit']) for c in CASES} for label,path in paths.items()}
    (a.output/'host-references.json').write_text(json.dumps(refs,indent=2)+'\n',encoding='utf-8')
    client=Dispatcher(a.master);initial=client.request('GET','/api/cluster')
    assert initial['peer']==a.peer and not initial['queued'] and not initial['running']
    before={ip:json.loads(request(ip,'GET','/api/status')) for ip in [a.master,a.peer]}
    assert all(s['model_id']==ids['sft'] and s['model_ready'] and s['firmware']=='0.4.0' for s in before.values())
    (a.output/'status-before.json').write_text(json.dumps(before,indent=2)+'\n',encoding='utf-8')
    rows=[];changed=False
    try:
        for label in ['sft','baseline']:
            if label=='baseline':
                client.request('POST','/api/cluster',{'peer':''});changed=True
                upload(a.peer,paths[label]);upload(a.master,paths[label])
                client.request('POST','/api/cluster',{'peer':a.peer})
            for at in [0,6]:
                cases=CASES[at:at+6]
                accepted=[client.submit(c['prompt'],c['limit'])['id'] for c in cases]
                (a.output/f'{label}-{at}-accepted.json').write_text(json.dumps(accepted)+'\n',encoding='utf-8')
                jobs=client.wait(accepted,timeout=360,poll=.3)
                (a.output/f'{label}-{at}-jobs.json').write_text(json.dumps(jobs,indent=2)+'\n',encoding='utf-8')
                for case,job in zip(cases,jobs):
                    assert job['state']=='done',job['id']
                    tokens,done=parse(job['raw_ndjson']);ref=refs[label][case['id']]
                    assert tokens==ref['tokens'] and done['prompt_tokens']==ref['prompt_tokens']
                    rows.append({'model':label,'case':case['id'],'category':case['category'],
                                 'text':ref['text'],'output_tokens':len(tokens),'prompt_tokens':done['prompt_tokens'],
                                 'limit':case['limit'],'elapsed_ms':done['elapsed_ms'],'ttft_ms':done['ttft_ms'],
                                 'queue_ms':job['queue_ms'],'target':job['target'],
                                 'indicators':indicators(case,ref['text'],len(tokens))})
                (a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
                print(label,'completed cases',at+len(cases),flush=True)
    finally:
        # Never replace models while accepted dispatcher work is still active.
        state=client.request('GET','/api/cluster')
        if changed:
            if state['queued'] or state['running']:raise RuntimeError('Active jobs remain; defer model restoration until they finish')
            upload(a.peer,paths['sft']);upload(a.master,paths['sft'])
            client.request('POST','/api/cluster',{'peer':a.peer})
    masked=[];mapping={}
    for case in CASES:
        reverse=hashlib.sha256(('quality-v1:'+case['id']).encode()).digest()[0]%2
        labels=['baseline','sft'] if not reverse else ['sft','baseline']
        mapping[case['id']]={'A':labels[0],'B':labels[1]}
        pair={'case':case,'outputs':{}}
        for name,label in zip(['A','B'],labels):
            row=next(r for r in rows if r['case']==case['id'] and r['model']==label)
            pair['outputs'][name]={k:row[k] for k in ['text','output_tokens','limit','indicators']}
        masked.append(pair)
    (a.output/'masked-pairs.json').write_text(json.dumps(masked,indent=2)+'\n',encoding='utf-8')
    (a.output/'model-label-map.json').write_text(json.dumps(mapping,indent=2)+'\n',encoding='utf-8')
    after={ip:json.loads(request(ip,'GET','/api/status')) for ip in [a.master,a.peer]}
    for ip,s in after.items():assert s['model_id']==ids['sft'] and s['model_ready'] and s['boot_id']==before[ip]['boot_id']
    assert hashlib.sha256((a.output/'protocol.json').read_bytes()).hexdigest()==protocol_hash
    final={'devices':after,'cluster':client.request('GET','/api/cluster'),'protocol_sha256':protocol_hash,'hardware_outputs_match_host':True}
    (a.output/'final-state.json').write_text(json.dumps(final,indent=2)+'\n',encoding='utf-8')
    print('20 quality cases complete; both boards restored to SFT',flush=True)

if __name__=='__main__':main()
