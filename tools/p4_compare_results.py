"""Offline raw-stream audit and derived quality/timing tables; never runs a model."""
import hashlib
import json
import pathlib
import statistics
import subprocess
from html import escape
from p4_compare_metrics import paired_summary, rates

ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/'data/matched-p4-2026-10-30'
MODELS=['tinybrainbot','supra']
LABELS={'tinybrainbot':'TinyBrainBot-100M-v3-Instruct','supra':'Supra2-100M-Instruct'}


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')


def stream(raw,expected):
    items=[json.loads(line) for line in raw.splitlines() if line.strip()]
    ids=[x['token'] for x in items if 'token' in x]
    raw_text=b''.join(bytes.fromhex(x['bytes_hex']) for x in items if 'token' in x)
    text=raw_text.decode('utf-8')
    ends=[x for x in items if x.get('done')]
    assert len(ends)==1 and items[-1]==ends[0] and not ends[0].get('error')
    d=ends[0]
    assert ids==expected['tokens'] and raw_text==expected['text'].encode('utf-8') and d['eos'] is expected['eos']
    assert d['output_tokens']==len(ids) and d['prompt_tokens']==len(expected['prompt_tokens']) and d['boards']==2
    assert d['kernel']['mode']=='tile4' and d['kernel']['owner_core_mask']==2 and d['kernel']['helper_core_mask']==1
    rates(d)
    return text,d


def audit():
    p=read(DATA/'protocol.json');h=read(DATA/'host-receipt.json');refs=read(DATA/'host-references.json')
    assert sha(DATA/'protocol.json')==(DATA/'protocol.sha256').read_text().strip()==h['protocol_sha256']
    assert subprocess.check_output(['git','show',h['protocol_commit']+':'+(DATA/'protocol.json').relative_to(ROOT).as_posix()],cwd=ROOT)==(DATA/'protocol.json').read_bytes()
    assert h['references_sha256']==sha(DATA/'host-references.json')
    assert h['source_sha256']==p['source_sha256']
    for name,digest in p['source_sha256'].items():assert sha(ROOT/name)==digest,name
    assert h['complete_generations']==30 and type(h['complete_generations']) is int
    cases={c['id']:c for c in p['cases']};q=read(DATA/'quality-runs.json');timing=read(DATA/'timing-runs.json');controls=read(DATA/'controls.json')
    assert len(q)==24 and {(r['model'],r['case']) for r in q}=={(m,c) for m in MODELS for c in cases}
    assert len(controls)==4 and [r['model'] for r in controls]==['tinybrainbot','supra','tinybrainbot','supra']
    final=read(DATA/'final.json');assert final['completed'] and final['failure'] is None
    assert final['mode']=='sharded' and final['queued']==final['running']==0
    records=[];all_rows=q+timing+controls+[final['restoration_control']]
    assert len(all_rows)==41 and len({r['file'] for r in all_rows})==41
    for r in all_rows:
        expected=refs[r['model']]['W' if 'warmup' in r['file'] or 'restoration' in r['file'] else r['case']]
        text,done=stream((DATA/r['file']).read_bytes(),expected)
        assert done==r['done'] and r['tokens_text_eos_equal'] is True
        records.append({'model':r['model'],'case':r['case'],'file':r['file'],'unicode_characters':len(text),
                        'unicode_characters_per_s':len(text)*1000/done['elapsed_ms'],**rates(done)})
    assert [(r['model'],r['block'],r['case']) for r in timing]==[
        (step['model'],b,c) for step in p['schedule'] for b in step['blocks'] for c in (['B2','B1'] if b==2 else ['B1','B2'])]
    summary=paired_summary(timing);assert summary==read(DATA/'timing-summary.json')
    for label in ['phase1','phase2','phase3','phase4','restored']:
        model='tinybrainbot' if label in ['phase1','phase3','restored'] else 'supra'
        for role,s in read(DATA/(label+'-states.json')).items():
            assert s['firmware']=='0.7.0' and s['model_ready'] and s['context']==256 and s['quant_bits']==4
            assert s['role']==(1 if role=='coordinator' else 2) and s['model_id']==p['artifacts'][model][role]['model_id']
            assert s['artifact_id']==p['artifacts'][model][role]['artifact_id'] and s['free_psram']>=512*1024
            assert not s['worker_busy'] and not s['ota_pending']
    for role,s in final['devices'].items():
        assert s['firmware']=='0.7.0' and s['model_ready'] and s['model_id']==p['artifacts']['tinybrainbot'][role]['model_id'] and not s['worker_busy'] and not s['ota_pending']
        assert s['artifact_id']==p['artifacts']['tinybrainbot'][role]['artifact_id'] and s['free_psram']>=512*1024
    write(DATA/'derived-rates.json',records)
    return p,refs,q,summary


def summarize(p,refs,q,timing):
    review=read(DATA/'manual-review.json');assert review['reviewer']=='Same assistant, unblinded; not independent'
    assert review['protocol_sha256']==sha(DATA/'protocol.json') and review['host_references_sha256']==sha(DATA/'host-references.json')
    assert len(review['rows'])==24 and {(r['model'],r['case']) for r in review['rows']}=={(m,c['id']) for m in MODELS for c in p['cases']}
    counts={}
    for model in MODELS:
        counts[model]={}
        for category in ['facts','grounded']:
            ids={c['id'] for c in p['cases'] if c['category']==category}
            rows=[r for r in review['rows'] if r['model']==model and r['case'] in ids]
            for r in rows:
                assert type(r['first']) is bool and (r['clean'] is None or type(r['clean']) is bool) and r['note']
                assert r['clean'] is not True or r['first']
            counts[model][category]={'n':len(rows),'first_correct':sum(r['first'] for r in rows),
                'confirmed_clean':sum(r['clean'] is True for r in rows),'uncertain_clean':sum(r['clean'] is None for r in rows)}
        exact=[c for c in p['cases'] if c['category']=='exact'];stories=[c for c in p['cases'] if c['category']=='story']
        exact_results={c['id']:refs[model][c['id']]['text'].strip()==c['expected'] for c in exact}
        for cid,value in exact_results.items():assert next(r for r in review['rows'] if r['model']==model and r['case']==cid)['exact'] is value
        counts[model]['exact']={'n':len(exact),'correct':sum(exact_results.values())}
        rows=[r for r in review['rows'] if r['model']==model and r['case'] in {c['id'] for c in stories}]
        for r in rows:
            assert all(type(r[k]) is bool for k in ['topic','coherent','resolution']) and r['note']
        counts[model]['story']={'n':len(rows),**{k:sum(r[k] for r in rows) for k in ['topic','coherent','resolution']}}
    paired={}
    for category in ['facts','grounded']:
        ids=[c['id'] for c in p['cases'] if c['category']==category];pairs={}
        for metric in ['first','clean']:
            joined=[tuple(next(r for r in review['rows'] if r['model']==m and r['case']==cid)[metric] for m in MODELS) for cid in ids]
            pairs[metric]={'both':sum(a is True and b is True for a,b in joined),'tiny_only':sum(a is True and b is False for a,b in joined),
                'supra_only':sum(a is False and b is True for a,b in joined),'neither':sum(a is False and b is False for a,b in joined),
                'uncertain_pair':sum(a is None or b is None for a,b in joined)}
        paired[category]=pairs
    lengths={m:{'output_tokens':sum(len(refs[m][c['id']]['tokens']) for c in p['cases']),
                  'unicode_characters':sum(len(refs[m][c['id']]['text']) for c in p['cases']),
                  'eos':sum(refs[m][c['id']]['eos'] for c in p['cases']),
                  'total_quality_seconds':sum(r['done']['elapsed_ms']/1000 for r in q if r['model']==m)} for m in MODELS}
    result={'counts':counts,'paired_quality':paired,'quality_lengths':lengths,'timing':timing,
            'scope':'Same physical pair/firmware/quantization/kernel; small author-reviewed task set. No independent semantic evaluator, global ranking, energy or isolated arithmetic claim.',
            'source_sha256':{n:sha(DATA/n) for n in ['protocol.json','host-references.json','quality-runs.json','timing-runs.json','manual-review.json']}}
    write(DATA/'summary.json',result)
    notes={(r['model'],r['case']):r for r in review['rows']};runs={(r['model'],r['case']):r for r in q}
    page=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Matched two-P4 model comparison</title>',
        '<style>body{font:16px/1.55 system-ui;max-width:1500px;margin:25px auto;padding:20px;background:#eef4f7;color:#183247}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}article{padding:22px;border-radius:12px;background:white}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}.meta{color:#536b7b}section{margin:28px 0}@media(max-width:750px){.grid{grid-template-columns:1fr}}</style>',
        '<h1>TinyBrainBot and Supra2 on the same two P4s</h1><p>30 October2026. Firmware0.7.0, row INT4, context256, 4+8 split, tile4. Native author wrappers for identical user tasks. Same unblinded assistant review; small exploratory sample. Complete actual P4 streams match these native references. Durations include prefill and varying output lengths; these quality-case times are not equal-work speedups.</p>']
    for c in p['cases']:
        page+=['<section><h2>'+c['id']+' · '+c['category']+'</h2><pre>'+escape(c['user'])+'</pre><div class="grid">']
        for m in MODELS:
            r=refs[m][c['id']];d=runs[m,c['id']]['done'];note=notes[m,c['id']]
            page+=['<article><h3>'+LABELS[m]+'</h3><p class="meta">'+f"{len(r['prompt_tokens'])} input / {len(r['tokens'])} output tokens; {len(r['text'])} Unicode characters; {d['elapsed_ms']/1000:.3f} s total; {d['ttft_ms']/1000:.3f} s first decision; "+('EOS observed' if r['eos'] else 'cap reached')+'</p><pre>'+escape(r['text']).replace('\r','&#13;').replace('\n','&#10;')+'</pre><p>'+escape(note['note'])+'</p></article>']
        page+=['</div></section>']
    (DATA/'comparison.html').write_text('\n'.join(page+['</html>'])+'\n',encoding='utf-8')
    from html.parser import HTMLParser
    class Page(HTMLParser):
        def __init__(self):super().__init__();self.current=None;self.pres=[];self.articles=0
        def handle_starttag(self,tag,attrs):
            assert tag not in ['script','iframe','link'] and not any(k in ['src','href'] for k,v in attrs)
            self.articles+=tag=='article'
            if tag=='pre':self.current=''
        def handle_data(self,text):
            if self.current is not None:self.current+=text
        def handle_endtag(self,tag):
            if tag=='pre':self.pres.append(self.current);self.current=None
    parsed=Page();parsed.feed((DATA/'comparison.html').read_text(encoding='utf-8'))
    assert parsed.articles==24
    expected=[text for c in p['cases'] for text in [c['user'],refs['tinybrainbot'][c['id']]['text'],refs['supra'][c['id']]['text']]]
    assert parsed.pres==expected
    return result


if __name__=='__main__':
    p,refs,q,t=audit();result=summarize(p,refs,q,t)
    manifest={p.name:sha(p) for p in sorted(DATA.iterdir()) if p.is_file() and p.name!='record-audit.json'}
    write(DATA/'record-audit.json',{'passed':True,'host_complete_generations':30,'device_complete_raw_streams':41,'quality_outputs':24,
        'timing_runs':12,'warmups':4,'restoration_controls':1,'protocol_commit':read(DATA/'host-receipt.json')['protocol_commit'],
        'all_tokens_text_eos_verified':True,'schedule_memory_restoration_checked':True,'manual_counts_and_html_verified':True,
        'source_sha256':manifest,'audit_script_sha256':sha(pathlib.Path(__file__)),
        'scope':'Offline audit; no inference or device calls.'})
    print('PASS: frozen protocol, 30 host refs, 41 complete actual streams, 24 manual reviews, paired metrics, restoration')
