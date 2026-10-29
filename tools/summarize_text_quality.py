"""Join a frozen masked review to the measured outputs, preserving provenance."""
import argparse
import hashlib
import json
import pathlib
from html import escape

def comparison_html(root,rows,pairs):
    parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">',
           '<title>Text quality V1: complete outputs</title>',
           '<style>body{font:16px/1.6 system-ui;max-width:1250px;margin:32px auto;padding:0 20px;color:#17202b;background:#f6f7f9}section{margin:36px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}article{background:white;border:1px solid #ccd2da;border-radius:8px;padding:20px}pre{white-space:pre-wrap;font:inherit}small{display:block;color:#465268}h1,h2,h3{line-height:1.25}@media(max-width:750px){.pair{grid-template-columns:1fr}}</style>',
           '<h1>Text quality V1: complete comparison</h1>',
           '<p>Model labels revealed after masked review. One greedy run per task/model. A shorter output implies an engine stop; a limit hit is truncated. Reviews are by the same assistant, not an independent user study. No external content or scripts.</p>']
    for pair in pairs:
        case=pair['case'];parts.extend(['<section><h2>'+escape(case['id'])+'</h2><pre>'+escape(case['prompt'])+'</pre><div class="pair">'])
        for model in ['baseline','sft']:
            row=next(r for r in rows if r['case']==case['id'] and r['model']==model)
            stop='Inferred engine stop' if row['indicators']['eos_inferred'] else 'Token limit reached'
            info=f"{row['output_tokens']}/{row['limit']} output tokens; {row['elapsed_ms']/1000:.3f} s inference; {stop}"
            text=escape(row['text']).replace('\r','&#13;').replace('\n','&#10;')
            parts.extend(['<article><h3>'+escape(model)+'</h3><small>'+escape(info)+'</small><pre>'+text+'</pre><hr><p>'+escape(row['review']['note'])+'</p></article>'])
        parts.append('</div></section>')
    parts.append('</html>');(root/'vergleich.html').write_text('\n'.join(parts),encoding='utf-8')

def summarize(root):
    raw=(root/'masked-review.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==(root/'masked-review.sha256').read_text(encoding='utf-8').strip()
    review=json.loads(raw)
    assert review['masked_pairs_sha256']==hashlib.sha256((root/'masked-pairs.json').read_bytes()).hexdigest()
    mapping=json.loads((root/'model-label-map.json').read_text(encoding='utf-8'))
    pairs=json.loads((root/'masked-pairs.json').read_text(encoding='utf-8'))
    rows=json.loads((root/'results.json').read_text(encoding='utf-8'))
    assert len(rows)==20 and len(review['ratings'])==10
    for pair in pairs:
        case=pair['case']['id'];assert set(mapping[case].values())=={'baseline','sft'}
        for label,rating in review['ratings'][case].items():
            row=next(r for r in rows if r['case']==case and r['model']==mapping[case][label])
            assert row['text']==pair['outputs'][label]['text']
            assert rating['coherence'] in [0,1,2]
            if row['category']=='story' and row['indicators']['limit_reached']:assert rating['ending_matches'] is None
            row['review_label']=label;row['review']=rating
    summary={}
    for model in ['sft','baseline']:
        a=[r for r in rows if r['model']==model]
        stories=[r for r in a if r['category']=='story']
        questions=[r for r in a if r['category']=='question']
        instructions=[r for r in a if r['category']=='instruction']
        summary[model]={'cases':len(a),'output_tokens':sum(r['output_tokens'] for r in a),
            'eos_count':sum(r['indicators']['eos_inferred'] for r in a),
            'repetition_flag_cases':[r['case'] for r in a if r['indicators']['repetition_flag']],
            'story_topic_scores':{r['case']:r['review']['story_topic'] for r in stories},
            'story_coherence_scores':{r['case']:r['review']['coherence'] for r in stories},
            'completed_stories_with_requested_ending':[r['case'] for r in stories if r['review']['ending_matches'] is True],
            'stories_ending_not_assessable':[r['case'] for r in stories if r['review']['ending_matches'] is None],
            'questions_first_answer_correct':[r['case'] for r in questions if r['review']['first_answer_correct']],
            'questions_fully_fulfilled':[r['case'] for r in questions if r['review']['question_request_fulfilled']],
            'instructions_fulfilled':[r['case'] for r in instructions if r['review']['instruction_fulfilled']]}
    (root/'reviewed-results.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    provenance={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['masked-review.json','masked-pairs.json','model-label-map.json','results.json']}
    provenance['join_script_sha256']=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
    (root/'review-join-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    comparison_html(root,rows,pairs)
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=pathlib.Path)
    summary=summarize(p.parse_args().directory)
    print('Frozen review joined and checked for',sum(r['cases'] for r in summary.values()),'outputs')
