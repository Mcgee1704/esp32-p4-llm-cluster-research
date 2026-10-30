"""Offline audit of frozen selection, cache identities, answer bytes and admission."""
import math
import statistics
from supra_quantization_study import OUT,CACHE,SOURCE,VARIANTS,ROOT,read,sha,write,select_candidate,score_answer,provenance
from pack_supra import tokenizer


def verify():
    p=read(OUT/'protocol.json');selection=read(OUT/'selection.json');q=read(OUT/'quality-summary.json')
    assert sha(OUT/'inputs.json')==p['inputs_sha256']
    assert sha(SOURCE/p['source_file'])==p['source_sha256']
    assert sha(OUT/'protocol.json')==selection['protocol_sha256']
    assert sha(OUT/'selection.json')==q['selection_sha256_before_answers']
    assert provenance()==p['initial_code_sha256']==selection['code_sha256']==q['code_sha256']
    counts={name:sum(len(x['tokens']) for x in p[name]) for name in ('calibration','validation')}
    assert counts['calibration']==p['calibration_count']<=1024
    assert len({x['id'] for kind in ('calibration','validation','quality','known_regressions') for x in p[kind]})==44
    cal=read(OUT/'calibration.json');assert cal['tokens']==counts['calibration'] and sha(CACHE/'activations.npz')==cal['activation_sha256']
    candidate=read(OUT/'candidates.json');assert candidate['protocol_sha256']==sha(OUT/'protocol.json')
    assert candidate['code_sha256']==provenance()==cal['code_sha256']
    files=0
    for name,row in candidate['variants'].items():
        for path,digest in row['quantized_cache_sha256'].items():
            assert sha(CACHE/name/path)==digest;files+=1
    validation={}
    for name,digest in selection['validation_sha256'].items():
        assert sha(OUT/('validation-'+name+'.json'))==digest
        v=read(OUT/('validation-'+name+'.json'));validation[name]=v
        assert v['positions']==counts['validation']==sum(x['positions'] for x in v['documents'])
        assert math.isclose(statistics.mean(v['per_position_kl_nats']),v['mean_kl_nats'],abs_tol=1e-12)
        assert math.isclose(statistics.mean(v['per_position_top1_agreement']),v['top1_agreement'],abs_tol=1e-12)
        assert math.isclose(sum(x['positions']*x['mean_kl_nats'] for x in v['documents'])/v['positions'],v['mean_kl_nats'],abs_tol=1e-12)
    selected=select_candidate(validation['row'],{n:validation[n] for n in VARIANTS})
    assert selected['winner']==selection['winner'] and selected['admitted']==selection['admitted']
    vocab,*_=tokenizer(SOURCE);cases={x['id']:x for x in p['quality']+p['known_regressions']};answers={};total=0
    for name,digest in q['answer_sha256'].items():
        path=OUT/('answers-'+name+'.json');assert sha(path)==digest
        a=read(path);assert len(a)==len(cases) and {x['id'] for x in a}==set(cases)
        scores={'fact':0,'exact':0}
        for row in a:
            case=cases[row['id']]
            assert len(row['tokens'])<=case['limit'] and len(case['tokens'])+len(row['tokens'])<=256
            assert all(0<=i<len(vocab) and i not in (2,6) for i in row['tokens'])
            assert b''.join(vocab[i] for i in row['tokens']).decode('utf-8','replace')==row['text']
            if 'rule' in case:
                passed=score_answer(case,row['text']);assert passed==row['screen_pass']
                scores[case['category']]+=int(passed)
            else:assert row['screen_pass'] is None
        assert scores==q['counts'][name];answers[name]={x['id']:x for x in a};total+=len(a)
    old=ROOT/'data/supra100-2026-10-29'
    old_row={x['case']:x for x in read(old/'host-generations.json')}
    old_f16={x['case']:x['source_precision_float32_compute'] for x in read(old/'source-controls.json')}
    prefixes=[]
    for case in p['known_regressions']:
        for name,prior in [('row',old_row),('f16',old_f16)]:
            before=prior[case['id']];assert answers[name][case['id']]['tokens'][:len(before['tokens'])]==before['tokens']
            prefixes.append({'variant':name,'case':case['id'],'matched_tokens':len(before['tokens'])})
    winner=selection['winner'];admitted=bool(winner and q['counts'][winner]['fact']>=q['counts']['row']['fact'])
    assert admitted==q['quality_admitted']
    manual=read(OUT/'manual-review.json');fact_ids={x['id'] for x in p['quality'] if x['category']=='fact'}
    for name,ids in manual['correct_first_claim_ids'].items():
        assert len(set(ids))==len(ids)==manual['counts_of_16'][name] and set(ids)<=fact_ids
    assert not manual['admission_changed']
    from html.parser import HTMLParser
    class Page(HTMLParser):
        def __init__(self):super().__init__();self.articles=0;self.sections=0
        def handle_starttag(self,tag,attrs):
            assert tag not in ('script','iframe','link')
            assert all(k not in ('src','href') for k,v in attrs)
            self.articles+=tag=='article';self.sections+=tag=='section'
    page=Page();page.feed((OUT/'comparison.html').read_text('utf-8'))
    assert page.articles==24 and page.sections==72
    result={'scope':'Offline record and identity audit; not a new native/P4 execution',
            'calibration_tokens':counts['calibration'],'validation_positions':counts['validation'],'quantized_cache_files':files,
            'complete_generations_checked':total,'legacy_prefix_checks':prefixes,'winner':winner,'quality_admitted':admitted,
            'comparison_html_answers':page.sections,'manual_counts_of_16':manual['counts_of_16'],
            'firmware_or_model_written':False,'new_native_kernel_tested':False,'checks_passed':True,
            'audit_script_sha256':sha(ROOT/'tools/verify_quantization_v2.py')}
    write(OUT/'record-audit.json',result)
    print('PASS: frozen inputs, selection,',files,'candidate files,',total,'answers,',len(prefixes),'legacy prefixes; admission =',admitted)


if __name__=='__main__':verify()
