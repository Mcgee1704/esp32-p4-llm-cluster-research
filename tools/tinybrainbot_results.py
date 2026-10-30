"""Derived local research records, figures and complete answer browser."""
import json
from html import escape
from tinybrainbot_study import OUT,ROOT,CONDITIONS,read,write,sha
from plot_matched_models import Canvas,OUT as FIGURES

ORDER=['supra-f16','tinybrainbot-f16','supra-int4','tinybrainbot-int4']
LABELS={'supra-f16':'Supra2 · F16 source','supra-int4':'Supra2 · row INT4','tinybrainbot-f16':'TinyBrainBot · F16 source','tinybrainbot-int4':'TinyBrainBot · row INT4'}
COLORS={n:('#2777a2' if n.startswith('supra') else '#168476') for n in CONDITIONS}
MUTED='#586c7d'


def summarize():
    p=read(OUT/'protocol.json');review=read(OUT/'manual-review.json');rows={x['id']:x for x in review['rows']};answers={n:read(OUT/('answers-'+n+'.json')) for n in CONDITIONS};counts={}
    assert review['conditions']==list(CONDITIONS) and len(rows)==30
    for i,n in enumerate(CONDITIONS):
        assert all(r['clean'][i] is not True or r['first'][i] for r in rows.values())
        counts[n]={}
        for cat in ['facts','grounded']:
            ids=[x['id'] for x in p['cases'] if x['category']==cat]
            counts[n][cat]={'total':len(ids),'first_correct':sum(rows[k]['first'][i] for k in ids),
                'confirmed_clean':sum(rows[k]['clean'][i] is True for k in ids),'uncertain_clean':sum(rows[k]['clean'][i] is None for k in ids),
                'first_correct_ids':[k for k in ids if rows[k]['first'][i]],'confirmed_clean_ids':[k for k in ids if rows[k]['clean'][i] is True]}
        exact=[x for x in p['cases'] if x['category']=='exact'];actual={x['id']:x for x in answers[n]}
        counts[n]['exact_correct']=sum(actual[x['id']]['text'].strip()==x['exact'] for x in exact)
        counts[n]['eos_of_30']=sum(x['eos'] for x in answers[n]);counts[n]['capped_of_30']=30-counts[n]['eos_of_30']
        counts[n]['supporting_fact_screen']=sum(x['screen_pass'] for x in answers[n] if x['category']=='facts')
    promising=all(counts['tinybrainbot-'+q]['facts']['first_correct']>counts['supra-'+q]['facts']['first_correct'] and
                   counts['tinybrainbot-'+q]['facts']['confirmed_clean']>=counts['supra-'+q]['facts']['confirmed_clean'] for q in ['f16','int4'])
    paired={}
    for precision in ['f16','int4']:
        a=CONDITIONS.index('supra-'+precision);b=CONDITIONS.index('tinybrainbot-'+precision);ids=[x['id'] for x in p['cases'] if x['category']=='facts']
        paired[precision]={'tiny_wins_ids':[k for k in ids if rows[k]['first'][b] and not rows[k]['first'][a]],
                           'supra_wins_ids':[k for k in ids if rows[k]['first'][a] and not rows[k]['first'][b]]}
    summary={'counts':counts,'paired_first_fact_comparison':paired,'passes_frozen_promising_rule':promising,'p4_adopted':False,'p4_ready':False,
        'interpretation':'Promising factual-generation candidate on this small fixed local sample. Exact instruction following and grounded subtraction still fail. Real Metaspace tokenizer port, parser/allocation/flash budget and P4 execution remain untested.',
        'primary_evidence':'Unblinded author review; first responsive core answer and visible clean response separately. Uncertain clean cases excluded from confirmed counts.',
        'host_math':read(OUT/'math-report.json'),'estimated_memory':p['estimated_memory'],
        'source_sha256':{str(x.relative_to(ROOT)).replace('\\','/'):sha(x) for x in [OUT/'protocol.json',OUT/'manual-review.json',OUT/'generation-receipt.json',ROOT/'tools/tinybrainbot_results.py']}}
    write(OUT/'summary.json',summary);return summary,answers,rows


def save(c,name,sources,notes):
    c.save(name,sources);path=FIGURES/(name+'-2026-10-29.json');x=read(path);x['notes']=notes;write(path,x)


def figure(s):
    c=Canvas(1280,'TinyBrainBot answers more of these facts correctly.',
        'Local host comparison | 20 new facts + 4 exact + 4 grounded + 2 known anchors | Greedy, cap 48, context 256')
    for x,title,subtitle,key in [(48,'First responsive factual answer','Correct core answer / 20; later errors may follow','first_correct'),(803,'Clean visible factual response','Confirmed / 20; no false claims or material task drift','confirmed_clean')]:
        c.rect(x,140,735 if x==48 else 749,440);c.text(x+24,184,title,27,weight='bold');c.text(x+24,218,subtitle,20,MUTED)
        for i,n in enumerate(ORDER):
            y=263+i*76;v=s['counts'][n]['facts'][key];color=COLORS[n];c.text(x+24,y,LABELS[n],21,color,'bold')
            c.rect(x+24,y+13,520,22,'#e4ebf0',0);c.rect(x+24,y+13,520*v/20,22,color,0)
            c.text(x+566,y+34,f'{v}/20',24,color,'bold')
        if x==803:c.text(x+24,559,'Supra INT4 also has two unclear capped claims, not counted.',18,MUTED)
    c.rect(48,605,1504,270);c.text(72,648,'Keep the other endpoints visible',28,weight='bold')
    for text,x in [('Condition',72),('Exact reply / 4',610),('Grounded first / clean',875),('Reached EOS / 30',1210)]:c.text(x,686,text,20,MUTED,'bold')
    for i,n in enumerate(ORDER):
        y=727+39*i;r=s['counts'][n];c.text(72,y,LABELS[n],22,COLORS[n],'bold')
        c.text(660,y,str(r['exact_correct']),23);c.text(955,y,f"{r['grounded']['first_correct']} / {r['grounded']['confirmed_clean']}",23);c.text(1295,y,str(r['eos_of_30']),23)
    c.rect(48,900,1504,200,'#f3e6d7');c.text(72,944,'Promising for further porting. Still unreliable.',28,'#905529','bold')
    c.text(72,984,'Tiny INT4: humans live on Mars; spiders and bicycles have four legs/wheels.',24)
    c.text(72,1024,'No exact reply passes. Both models fail the two-coins-minus-one task.',23)
    c.text(72,1064,'Candidate source → INT4: 15 → 12 correct first facts; quantization still loses useful behavior.',22)
    c.text(48,1150,'Unblinded manual review, one fixed small sample; source weights F16, compute FP32. No population accuracy claim.',21,MUTED)
    c.text(48,1186,'Same user content, native author templates; different tokenizers mean equal token caps are not equal word budgets.',21,MUTED)
    c.text(48,1222,'No P4 model/firmware upload. Host C weights/shards checked with a fake diagnostic tokenizer; real port remains open.',21,MUTED)
    save(c,'tinybrainbot-vs-supra-quality',[OUT/'summary.json',OUT/'manual-review.json',OUT/'protocol.json',ROOT/'tools/tinybrainbot_results.py'],
         'Small deterministic offline comparison, all 120 outputs retained. Manual review unblinded, no independent rater or confidence intervals. Clean count excludes two uncertain Supra INT4 claims. EOS is termination, not correctness. No new P4 result.')


def setup(s):
    c=Canvas(1110,'Host first: select, freeze, compare, then consider the port.',
        'One new 200.20 MB F16 weight download | Existing Supra checkpoint and NumPy/tokenizers reused | No cloud inference')
    for x,title,line1,line2,color in [(48,'PINNED SOURCES','Supra2 100.68M · already local','TinyBrainBot 100.09M · SHA verified','#2777a2'),(558,'NATIVE INPUTS','Same questions; exact author templates','Metaspace vs ByteLevel tokenizers','#7653a8'),(1068,'LOCAL EXECUTION','F16 / FP32 + same row INT4','30 cases × four conditions = 120','#168476')]:
        c.rect(x,150,484,180);c.text(x+20,194,title,24,color,'bold');c.text(x+20,242,line1,22);c.text(x+20,286,line2,20,MUTED)
    c.arrow(532,240,558,240);c.arrow(1042,240,1068,240)
    c.rect(48,380,1504,168);c.text(72,424,'Protocol committed before generation: 825a413',28,weight='bold')
    c.text(72,466,'Manual core answer and complete visible correctness separated; exact replies checked literally.',23)
    c.text(72,506,'No prompt tuning, no model fine-tuning, no second checkpoint download to search for favorable outputs.',22,MUTED)
    c.arrow(1310,330,1310,380,'#168476')
    c.rect(48,590,1504,130,'#dcebe6');c.text(72,635,'NEXT BOUNDARY: actual P4 tokenizer and allocation validation',28,'#176b58','bold')
    c.text(72,676,'Llama/INT4 C math works on host. Metaspace + precompiled normalization is not supported by current firmware.',22)
    for x,role in [(48,'coordinator'),(803,'worker')]:
        b=s['estimated_memory'][role];c.rect(x,760,735 if x==48 else 749,212);c.text(x+24,802,'PROPOSED P4 '+role.upper(),25,weight='bold')
        c.text(x+24,842,f"Estimated PSRAM {b['estimated_total_psram_bytes']/1048576:.2f} / 32 MiB",24)
        c.rect(x+24,865,600,23,'#e4ebf0',0);c.rect(x+24,865,600*b['estimated_total_psram_bytes']/(32*1048576),23,'#168476',0)
        c.text(x+24,929,f"Headroom {b['estimated_headroom_bytes']/1048576:.2f} MiB; not an allocation measurement.",20,MUTED)
    c.text(48,1022,'Assumptions: context 256, layers 4+8, FP32 KV, 2 MiB runtime reserve per role, 2 MiB tokenizer allowance on master.',21,MUTED)
    c.text(48,1060,'No new device reads, writes, speed result or compressed-flash proof. Existing cluster was left untouched.',21,MUTED)
    save(c,'tinybrainbot-local-setup',[OUT/'selection.json',OUT/'protocol.json',OUT/'math-report.json',ROOT/'tools/tinybrainbot_results.py'],
         'Actual offline workflow and a conditional future two-P4 memory estimate. No P4 execution or tokenizer implementation implied. Synthetic-tokenizer C diagnostic verifies numeric weights only.')


def html(s,answers,rows):
    p=read(OUT/'protocol.json');a={n:{x['id']:x for x in records} for n,records in answers.items()}
    h=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TinyBrainBot vs Supra — all local answers</title>',
       '<style>body{font:16px/1.55 system-ui,sans-serif;max-width:1700px;margin:35px auto;padding:0 20px;color:#193347;background:#eff4f8}article{background:white;padding:20px;border-radius:12px;margin:24px 0}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:24px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.5 ui-monospace,monospace}.note{padding:12px;background:#f3e6d7;border-left:4px solid #bd6725}.meta{font-size:14px;color:#586c7d}summary{cursor:pointer}h3{font-size:18px}@media(max-width:1150px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.grid{grid-template-columns:1fr}}</style>',
       '<h1>TinyBrainBot vs Supra2: all 120 local continuations</h1><p>Same user content, each model\'s exact native author format. Context 256, greedy, cap 48, full vocabulary. Source F16 weights / FP32 compute and matched symmetric row-INT4.</p>',
       '<p class="note"><strong>Promising factual candidate; no P4 adoption.</strong> First correct facts: Supra F16 11/20, Tiny F16 15/20; Supra INT4 7/20, Tiny INT4 12/20. Confirmed clean visible facts: 5, 14, 2, 10 respectively; two more Supra INT4 clean judgments are unclear. Exact replies 0/4 in every condition. Small sample, unblinded manual review, not general accuracy.</p>',
       '<p>Protocol was committed before generation at 825a413. New facts T01–T20, exact replies A01–A04, supplied-context tasks G01–G04. K01/K02 are known anchors, excluded from primary counts. Grounded core answers are 3/4 for all conditions, but clean grounded responses are Supra F16 2/4, Tiny F16 1/4, Supra INT4 2/4, Tiny INT4 0/4. The supporting word screen is not the semantic judge. A correct core answer can coexist with a false explanation.</p>']
    for case in p['cases']:
        r=rows[case['id']];h.append('<article><h2>'+escape(case['id']+' · '+case['category'])+'</h2><p>'+escape(case['user'])+'</p><div class="grid">')
        for n in ORDER:
            x=a[n][case['id']];i=CONDITIONS.index(n);clean='unclear' if r['clean'][i] is None else str(r['clean'][i])
            visible=escape(x['text']).replace(' \n','&#32;\n')
            h.append('<section><h3>'+escape(LABELS[n])+'</h3><pre>'+visible+'</pre><p class="meta">'+escape(f"Core correct={r['first'][i]}; clean={clean}; {len(x['tokens'])} tokens; EOS={x['eos']}")+'</p><details><summary>Prompt and token IDs</summary><pre>'+escape(case['formats'][n.rsplit('-',1)[0]]['text'])+'\nOutput IDs: '+escape(json.dumps(x['tokens']))+'</pre></details></section>')
        h.append('</div><p class="note">Review: '+escape(r['note'])+'</p></article>')
    h.append('</html>');(OUT/'comparison.html').write_bytes(('\n'.join(h)+'\n').encode('utf-8'))


if __name__=='__main__':
    s,a,r=summarize();figure(s);setup(s);html(s,a,r)
    print({n:(s['counts'][n]['facts']['first_correct'],s['counts'][n]['facts']['confirmed_clean']) for n in CONDITIONS})
