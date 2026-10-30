"""Offline audit of the pinned, preregistered local model comparison."""
import subprocess
from tinybrainbot_study import OUT,ROOT,CANDIDATE,SUPRA,CONDITIONS,read,write,sha,code_hashes,tokenizers,prompt,screen


def validate_receipt(value):
    count=value['complete_generations_checked']
    if type(count) is not int or count!=120:
        raise ValueError('complete_generations_checked must be the integer120')
    if value['checks_passed'] is not True:
        raise ValueError('Audit did not pass')
    return value


def main():
    protocol=read(OUT/'protocol.json');receipt=read(OUT/'generation-receipt.json');selection=read(OUT/'selection.json')
    assert sha(OUT/'protocol.json')==receipt['protocol_sha256'] and code_hashes()==protocol['code_sha256']==receipt['code_sha256']
    assert sha(OUT/'inputs.json')==protocol['input_sha256']
    # This commit predates every answer file and contains the exact protocol.
    raw=subprocess.check_output(['git','show','825a413:data/tinybrainbot-local-2026-10-29/protocol.json'])
    assert raw==(OUT/'protocol.json').read_bytes()
    for item in protocol['candidate']['files']:assert sha(CANDIDATE/item['file'])==item['sha256']
    assert sha(CANDIDATE/'model.safetensors')==protocol['candidate']['weight_sha256']
    assert sha(SUPRA/protocol['baseline']['source_file'])==protocol['baseline']['sha256']
    tk=tokenizers();cases={x['id']:x for x in protocol['cases']};answers={};generation_count=0
    assert len(cases)==30 and sum(x['category']=='facts' for x in cases.values())==20
    for condition in CONDITIONS:
        path=OUT/('answers-'+condition+'.json');assert sha(path)==receipt['answer_sha256'][condition]
        rows=read(path);assert len(rows)==30 and [x['id'] for x in rows]==list(cases)
        name=condition.rsplit('-',1)[0];stop=set(protocol['stop_ids'][name]);answers[condition]={x['id']:x for x in rows}
        for row in rows:
            c=cases[row['id']];text=prompt(name,c['user']);ids=tk[name].encode(text,add_special_tokens=False).ids
            assert text==c['formats'][name]['text'] and ids==c['formats'][name]['tokens']
            assert len(row['tokens'])<=48 and len(ids)+len(row['tokens'])<=256
            assert all(0<=i<tk[name].get_vocab_size() and i not in stop for i in row['tokens'])
            assert row['eos']==(row['stop_id'] is not None) and (row['stop_id'] in stop if row['eos'] else len(row['tokens'])==48)
            assert row['text']==tk[name].decode(row['tokens'],skip_special_tokens=False)
            assert row['screen_pass']==screen(c,row['text']);generation_count+=1
    legacy=ROOT/'data/supra-quantization-v2-2026-10-29';prefixes=[]
    for condition,old in [('supra-f16','f16'),('supra-int4','row')]:
        prior={x['id']:x for x in read(legacy/('answers-'+old+'.json'))}
        for now,before in [('K01','N2'),('K02','N6')]:
            expected=prior[before]['tokens'];assert answers[condition][now]['tokens'][:len(expected)]==expected
            prefixes.append({'condition':condition,'case':now,'matched_prior_tokens':len(expected)})
    assert generation_count==receipt['complete_generations']==120
    math=read(OUT/'math-report.json');assert math['all_full_shard_logits_bit_identical'] and math['max_absolute_logit_error']<.003
    assert math['script_sha256']==sha(ROOT/'tools/check_tinybrainbot_math.py')
    manual=read(OUT/'manual-review.json');rows={x['id']:x for x in manual['rows']};summary=read(OUT/'summary.json')
    assert manual['conditions']==list(CONDITIONS) and set(rows)==set(cases)
    for i,condition in enumerate(CONDITIONS):
        for cat in ['facts','grounded']:
            ids=[x['id'] for x in cases.values() if x['category']==cat];expected=summary['counts'][condition][cat]
            assert sum(rows[k]['first'][i] for k in ids)==expected['first_correct']
            assert sum(rows[k]['clean'][i] is True for k in ids)==expected['confirmed_clean']
            assert sum(rows[k]['clean'][i] is None for k in ids)==expected['uncertain_clean']
        for row in rows.values():assert row['clean'][i] is not True or row['first'][i]
    expected_promising=all(summary['counts']['tinybrainbot-'+q]['facts']['first_correct']>summary['counts']['supra-'+q]['facts']['first_correct'] and
                           summary['counts']['tinybrainbot-'+q]['facts']['confirmed_clean']>=summary['counts']['supra-'+q]['facts']['confirmed_clean'] for q in ['f16','int4'])
    assert summary['passes_frozen_promising_rule']==expected_promising and not summary['p4_adopted'] and not summary['p4_ready']
    from html.parser import HTMLParser
    class Page(HTMLParser):
        def __init__(self):super().__init__();self.articles=0;self.sections=0;self.current=None;self.pres=[]
        def handle_starttag(self,tag,attrs):
            assert tag not in ('script','iframe','link') and all(k not in ('src','href') for k,v in attrs)
            self.articles+=tag=='article';self.sections+=tag=='section'
            if tag=='pre':self.current=''
        def handle_data(self,data):
            if self.current is not None:self.current+=data
        def handle_endtag(self,tag):
            if tag=='pre':self.pres.append(self.current);self.current=None
    page=Page();page.feed((OUT/'comparison.html').read_text('utf-8'));assert page.articles==30 and page.sections==120
    expected_texts=[answers[n][cid]['text'] for cid in cases for n in ['supra-f16','tinybrainbot-f16','supra-int4','tinybrainbot-int4']]
    assert page.pres[::2]==expected_texts
    for label in ['tinybrainbot-vs-supra-quality','tinybrainbot-local-setup']:
        meta=read(ROOT/'docs/figures'/(label+'-2026-10-29.json'))
        for path,digest in meta['source_sha256'].items():assert sha(ROOT/path)==digest
    audit={'checks_passed':True,'protocol_commit':'825a413','complete_generations_checked':generation_count,
        'source_and_companion_hashes_verified':True,'all_native_prompts_token_ids_and_decoded_text_verified':True,
        'baseline_prefixes':prefixes,'math_control_scope':math['scope'],'scope':'Offline audit, not a new generation or P4 test',
        'manual_summary_and_html_checked':True,'figure_source_hashes_match':True,
        'audit_script_sha256':sha(ROOT/'tools/verify_tinybrainbot_study.py')}
    write(OUT/'record-audit.json',validate_receipt(audit))
    print('PASS frozen protocol commit, pinned sources, 120 outputs, 4 previous Supra prefixes and host C math record')


if __name__=='__main__':main()
