"""Read-only, standard-library public snapshot audit. Never accesses devices."""
import argparse
import hashlib
import json
import pathlib
import re
import statistics
from urllib.parse import unquote


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))


def verify(root):
    root=root.resolve(); hashes=read(root/'SHA256SUMS.json'); representations=read(root/'provenance/representations.json')['files']
    for path,digest in hashes.items():
        target=(root/path).resolve();assert target.is_relative_to(root)
        assert sha(target)==digest,path
    for path,entry in representations.items():assert sha(root/path)==entry['published_sha256'],path
    protocols=[]
    for marker in sorted(root.glob('data/**/protocol.sha256')):
        p=marker.with_name('protocol.json');entry=representations[p.relative_to(root).as_posix()]
        assert marker.read_text().strip()==entry['historical_sha256'],str(marker)
        assert p.with_name('protocol.public.sha256').read_text().strip()==sha(p)==entry['published_sha256']
        protocols.append(p.relative_to(root).as_posix())
    index=root/'provenance/protocols.json'
    if index.exists():
        indexed=read(index)
        assert set(protocols)=={x['path'] for x in indexed if x['legacy_marker_present']}
        assert {x['path'] for x in indexed}=={x.relative_to(root).as_posix() for x in root.glob('data/**/protocol.json')}
        for x in indexed:
            path=root/x['path'];entry=representations[x['path']]
            assert x['historical_sha256']==entry['historical_sha256']==path.with_name('protocol.historical.sha256').read_text().strip()
            assert x['public_sha256']==entry['published_sha256']==sha(path)==path.with_name('protocol.public.sha256').read_text().strip()
    else:assert len(protocols)==5
    lineage=read(root/'provenance/source-files.json');figure_dependencies=0
    for sidecar in sorted((root/'docs/figures').glob('*.json')):
        data=read(sidecar)
        for source,digest in data.get('source_sha256',data.get('sources',{})).items():
            matches=[(name,entry) for name,entry in lineage.items()
                     if entry['source']==source and entry['original_sha256']==digest]
            assert matches,(sidecar.name,source,'Missing original figure dependency')
            for name,entry in matches:assert sha(root/name)==entry['published_sha256']
            figure_dependencies+=1
    links=0
    for p in [root/'README.md',root/'THIRD_PARTY.md',*sorted((root/'docs').glob('*.md'))]:
        for url in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
            if re.match(r'^[a-zA-Z]+:',url) or url.startswith('#'):continue
            url=unquote(url.split('#',1)[0].strip('<>'))
            target=(p.parent/url).resolve()
            assert target.is_relative_to(root) and target.exists(),(p.relative_to(root).as_posix(),url)
            links+=1
    d=root/'data/matched-models-2026-10-29'; review=read(d/'manual-review.json'); counts={}
    for model in ['sft','story8','talk1','talk2']:
        rows=[r for r in review['rows'] if r['model']==model];stories=[r for r in rows if r['case'].startswith('S')]
        counts[model]={'first_fact_correct_of_6':sum(r.get('first_fact_correct',False) for r in rows),
            'question_and_format_of_3':sum(r.get('fully_meets_question_and_sentence',False) for r in rows),
            'instructions_of_3':sum(r.get('fully_fulfilled',False) for r in rows),
            'story_full_topic_of_4':sum(r['topic_continuity']==2 for r in stories),
            'story_no_material_contradiction_of_4':sum(r['coherence']==2 for r in stories),
            'story_visible_resolution_of_4':sum(r['narrated_resolution']==1 for r in stories),
            'story_eos_of_4':sum(r['eos_observed'] for r in stories),
            'story_cap_of_4':sum(r['cap_reached'] for r in stories),
            'all_cases_eos_of_16':sum(r['eos_observed'] for r in rows)}
    assert counts==read(d/'quality-summary.json')['counts']
    batches=read(d/'hardware/batches.json');timing=read(d/'hardware/summary.json')
    for model in counts:
        local=[r['elapsed_ms'] for r in batches if r['model']==model and r['mode']=='local']
        cluster=[r['elapsed_ms'] for r in batches if r['model']==model and r['mode']=='cluster']
        assert len(local)==len(cluster)==4
        assert statistics.median(local)==timing[model]['local_package_median_ms']
        assert statistics.median(cluster)==timing[model]['cluster_package_median_ms']
        assert statistics.median(a/b for a,b in zip(local,cluster))==timing[model]['paired_throughput_factor_median']
    tiny=root/'data/tinybrainbot-local-2026-10-29';audit=read(tiny/'record-audit.json')
    assert type(audit['complete_generations_checked']) is int and audit['complete_generations_checked']==120
    conditions=['supra-f16','supra-int4','tinybrainbot-f16','tinybrainbot-int4'];manual=read(tiny/'manual-review.json')
    cases=read(tiny/'protocol.json')['cases'];s=read(tiny/'summary.json');n=0
    for i,condition in enumerate(conditions):
        answers=read(tiny/('answers-'+condition+'.json'));assert len(answers)==30;n+=len(answers)
        for cat in ['facts','grounded']:
            ids={c['id'] for c in cases if c['category']==cat};rows=[r for r in manual['rows'] if r['id'] in ids]
            expected=s['counts'][condition][cat]
            assert sum(r['first'][i] for r in rows)==expected['first_correct']
            assert sum(r['clean'][i] is True for r in rows)==expected['confirmed_clean']
            assert sum(r['clean'][i] is None for r in rows)==expected['uncertain_clean']
    p4=root/'data/tinybrainbot-p4-2026-10-29';latency=[r['elapsed_ms']/1000 for r in read(p4/'timing.json')]
    assert statistics.median(latency)==read(p4/'device-summary.json')['timing']['median_seconds']
    matched_timing=timing;latest={}
    fresh=root/'data/supra-tiny-v09-2026-10-30'
    if fresh.exists():
        refs=read(root/'data/matched-p4-2026-10-30/host-references.json')
        def check_stream(path,model,case,reference_set=None):
            items=[json.loads(line) for line in path.read_bytes().splitlines()]
            assert sum(bool(x.get('done')) for x in items)==1 and items[-1].get('done') and not items[-1].get('error')
            tokens=[x['token'] for x in items if 'token' in x]
            text=b''.join(bytes.fromhex(x['bytes_hex']) for x in items if 'bytes_hex' in x).decode('utf-8','replace')
            expected=(refs if reference_set is None else reference_set)[model][case];assert tokens==expected['tokens'] and text==expected['text'] and items[-1]['eos']==expected['eos']
            return items[-1]
        rows=read(fresh/'timing-runs.json');assert len(rows)==12
        for row in rows:assert check_stream(fresh/row['file'],row['model'],row['case'])==row['done']
        timing=read(fresh/'summary.json')['timing']
        for case in ['B1','B2']:
            for model in ['tinybrainbot','supra']:
                ds=[x for x in rows if x['model']==model and x['case']==case]
                assert sorted(x['block'] for x in ds)==[1,2,3]
                assert all(x['done']['output_tokens']==16 and not x['done']['eos'] for x in ds)
                assert statistics.median(x['done']['elapsed_ms']/1000 for x in ds)==timing[case]['models'][model]['total_median_seconds']
        quality=read(fresh/'quality-runs.json');assert len(quality)==12
        for row in quality:assert check_stream(fresh/row['file'],'supra',row['case'])==row['done']
        controls=read(fresh/'controls.json');assert len(controls)==2
        for row in controls:assert check_stream(fresh/row['file'],row['model'],'W')==row['done']
        final=read(fresh/'final.json');row=final['restoration_control'];assert check_stream(fresh/row['file'],'tinybrainbot','W')==row['done']
        assert final['queued']==final['running']==0 and final['completed']
        reuse=read(fresh/'reused-tiny-quality.json');assert len(reuse)==12
        for row in reuse:
            rel=row['origin'].removeprefix('docs/research/');path=root/rel
            assert check_stream(path,'tinybrainbot',row['case'])==row['done']
            assert representations[rel]['historical_sha256']==row['sha256']
        kernel=root/'data/int4-pair-2026-10-30';ks=read(kernel/'summary.json')
        for phase in ['baseline','candidate']:
            runs=read(kernel/(phase+'-runs.json'));assert len(runs)==7
            for row in runs:assert check_stream(kernel/f'{phase}-{row["block"]}-{row["case"]}.ndjson','tinybrainbot',row['case'])==row['done']
        micro=root/'data/int4-memory-2026-10-30';runs=read(micro/'runs.json');assert len(runs)==12
        assert sum(len(x['measurements']) for x in runs)==96 and all(x['valid'] for x in runs)
        latest={'v09_fresh_streams':27,'v09_reused_streams':12,'v09_timing':timing,
                'kernel_speedup':ks['paired_baseline_over_candidate'],'microbench_raw_modes':96,'restored_tinybrainbot_recorded':True}
    q2=root/'data/quality-v2-2026-10-30'
    if q2.exists():
        assert fresh.exists(),'Full chronology requires the preceding model study'
        qp=read(q2/'protocol.json');qr=read(q2/'host-references.json');runs=read(q2/'device-runs.json');controls=read(q2/'controls.json');final=read(q2/'final.json')
        assert len(qp['cases'])==24 and len(runs)==48 and len(controls)==2 and final['completed'] and final['queued']==final['running']==0
        assert [(x['model'],x['case']) for x in runs]==[(m,c) for m in ['tinybrainbot','supra'] for c in qp['case_order']]
        allrows=runs+controls+[final['restoration_control']];assert len({x['file'] for x in allrows})==51
        for row in allrows:assert check_stream(q2/row['file'],row['model'],row['case'],qr)==row['done']
        masked=read(q2/'masked-responses.json');ratings=read(q2/'masked-ratings.json');u=read(q2/'unblinding.json');resolved=read(q2/'reviewed-results.json');summary=read(q2/'summary.json')
        assert len(masked['rows'])==24 and len(ratings['rows'])==len(resolved)==48 and summary['actual_streams_checked']==51
        mapping=u['mapping'];digest=hashlib.sha256((json.dumps(mapping,indent=2)+'\n').encode()).hexdigest();assert digest==qp['mask_commitment_sha256']==u['mapping_sha256']
        assert u['ratings_sha256']==representations['data/quality-v2-2026-10-30/masked-ratings.json']['historical_sha256']
        assert u['masked_responses_sha256']==representations['data/quality-v2-2026-10-30/masked-responses.json']['historical_sha256']
        assert {(x['case'],x['label']) for x in ratings['rows']}=={(c['id'],lab) for c in qp['cases'] for lab in ['A','B']}
        for rating in ratings['rows']:
            case=next(c for c in qp['cases'] if c['id']==rating['case']);model=mapping['labels'][case['id']][rating['label']]
            output=next(x for x in masked['rows'] if x['case']==case['id'])['outputs'][rating['label']]
            assert output['text']==qr[model][case['id']]['text'] and output['eos']==qr[model][case['id']]['eos']
            rr=next(x for x in resolved if x['case']==case['id'] and x['model']==model)
            assert all(rr[k]==v for k,v in rating.items())
            if case['category']=='exact':assert rating['exact']==(output['text'].strip()==case['expected'])
        for category,models in summary['counts'].items():
            for model,cnt in models.items():
                rr=[x for x in resolved if x['model']==model and x['category']==category];assert len(rr)==cnt['n']==4
                if category=='exact':assert sum(x['exact'] for x in rr)==cnt['exact']
                elif category=='story':
                    assert all(sum(x[k] for x in rr)==cnt[k] for k in ['topic','coherent','resolution','two_sentences'])
                    assert sum(all(x[k] for k in ['topic','coherent','resolution','two_sentences']) for x in rr)==cnt['strict_completion']
                else:
                    assert sum(x['core'] for x in rr)==cnt['core'] and sum(x['clean'] is True for x in rr)==cnt['confirmed_clean'] and sum(x['clean'] is None for x in rr)==cnt['uncertain_clean']
        latest['quality_v2']={'new_cases':24,'fresh_quality_outputs':48,'actual_streams':51,'reused_quality_outputs':0,'masked_rows':48,'mapping_commitment_verified':True,'counts':summary['counts'],'scope':'Recorded review arithmetic, not independent semantic re-rating or proof of complete blindness.'}
    cap=root/'data/quality-cap-v3-2026-10-30'
    if cap.exists():
        cp=read(cap/'protocol.json');cr=read(cap/'host-references.json');baseline=read(q2/'host-references.json');runs=read(cap/'device-runs.json');controls=read(cap/'controls.json');cf=read(cap/'final.json')
        assert len(runs)==48 and len(controls)==2 and cf['completed'] and cf['failure'] is None and cf['queued']==cf['running']==0
        assert [(x['model'],x['case']) for x in runs]==[(m,c) for m in ['tinybrainbot','supra'] for c in cp['case_order']]
        for name,digest in cp['baseline_sha256'].items():assert representations['data/quality-v2-2026-10-30/'+name]['historical_sha256']==digest
        reuse={(x['model'],x['case']) for x in cp['reused_eos']};assert len(reuse)==5
        fresh_count=0;paths=set()
        for row in runs+controls+[cf['restoration_control']]:
            reused=row['origin']=='reused-baseline-eos';m,cid=row['model'],row['case'];assert reused==((m,cid) in reuse)
            path=(q2 if reused else cap)/row['file'];assert path not in paths;paths.add(path)
            assert check_stream(path,m,cid,cr)==row['done']
            if reused:
                assert cr[m][cid]==baseline[m][cid] and cr[m][cid]['eos']
                assert row['baseline_file_sha256']==representations[path.relative_to(root).as_posix()]['historical_sha256']
            else:
                assert row['origin']=='fresh';fresh_count+=1
                if cid!='W':
                    low=baseline[m][cid];items=[json.loads(x) for x in path.read_bytes().splitlines()];pieces=[x for x in items if 'token' in x][:len(low['tokens'])]
                    assert [x['token'] for x in pieces]==low['tokens']
                    assert b''.join(bytes.fromhex(x['bytes_hex']) for x in pieces).decode('utf-8','replace')==low['text']
        assert fresh_count==46 and len(paths)==51 and sum(x['origin']=='fresh' for x in runs)==43
        for c in cp['cases']:
            assert c['limit']==2*c['baseline_limit']
            for m in ['tinybrainbot','supra']:
                low=baseline[m][c['id']];high=cr[m][c['id']];assert high['tokens'][:len(low['tokens'])]==low['tokens'] and high['prompt_tokens']==low['prompt_tokens']
        masked=read(cap/'masked-responses.json');ratings=read(cap/'masked-ratings.json');u=read(cap/'unblinding.json');resolved=read(cap/'reviewed-results.json');paired=read(cap/'paired-results.json');cs=read(cap/'summary.json')
        assert len(masked['rows'])==24 and len(ratings['rows'])==len(resolved)==len(paired)==48
        mapping=u['mapping'];assert hashlib.sha256((json.dumps(mapping,indent=2)+'\n').encode()).hexdigest()==cp['mask_commitment_sha256']==u['mapping_sha256']
        assert sum(x['A']=='tinybrainbot' for x in mapping['labels'].values())==12
        for name,k in [('masked-ratings.json','ratings_sha256'),('masked-responses.json','masked_responses_sha256')]:assert u[k]==representations['data/quality-cap-v3-2026-10-30/'+name]['historical_sha256']
        for rating in ratings['rows']:
            model=mapping['labels'][rating['case']][rating['label']];rr=next(x for x in resolved if x['case']==rating['case'] and x['model']==model)
            assert all(rr[k]==v for k,v in rating.items())
            out=next(x for x in masked['rows'] if x['case']==rating['case'])['outputs'][rating['label']];assert out['text']==cr[model][rating['case']]['text'] and out['eos']==cr[model][rating['case']]['eos']
            pair=next(x for x in paired if x['case']==rating['case'] and x['model']==model);old=next(x for x in read(q2/'reviewed-results.json') if x['case']==rating['case'] and x['model']==model)
            assert pair['higher_rating']==rr and pair['baseline_rating']==old
        def success(row,cat):return row['exact'] if cat=='exact' else all(row[k] for k in ['topic','coherent','resolution','two_sentences']) if cat=='story' else row['clean']
        def state(v):return 'success' if v is True else 'failure' if v is False else 'uncertain'
        for m,cc in cs['categories'].items():
            for cat,d in cc.items():
                pp=[x for x in paired if x['model']==m and x['category']==cat];assert len(pp)==4
                for pair in pp:
                    a,b=success(pair['baseline_rating'],cat),success(pair['higher_rating'],cat);assert pair['baseline_success']==a and pair['higher_success']==b and pair['transition']==state(a)+'_to_'+state(b)
                for transition,transition_count in d['transitions'].items():assert transition_count==sum(x['transition']==transition for x in pp)
                assert sum(d['transitions'].values())==4 and d['newly_confirmed']==sum(x['baseline_success'] is not True and x['higher_success'] is True for x in pp) and d['lost_confirmed']==sum(x['baseline_success'] is True and x['higher_success'] is not True for x in pp)
                for stage,key in [('baseline','baseline_rating'),('higher','higher_rating')]:
                    rr=[x[key] for x in pp];cnt=d[stage];assert cnt['n']==4
                    if cat=='exact':assert cnt['exact']==sum(x['exact'] for x in rr)
                    elif cat=='story':assert all(cnt[k]==sum(x[k] for x in rr) for k in ['topic','coherent','resolution','two_sentences']) and cnt['strict_completion']==sum(success(x,cat) for x in rr)
                    else:assert cnt['core']==sum(x['core'] for x in rr) and cnt['confirmed_clean']==sum(x['clean'] is True for x in rr) and cnt['uncertain_clean']==sum(x['clean'] is None for x in rr)
            freshrows=[x for x in runs if x['model']==m and x['origin']=='fresh'];oldrows=read(q2/'device-runs.json');cost=cs['fresh_subset_cost'][m]
            assert cost['n']==len(freshrows) and abs(cost['fresh_higher_seconds']-sum(x['done']['elapsed_ms'] for x in freshrows)/1000)<1e-8
            assert abs(cost['historical_baseline_seconds']-sum(next(x['done']['elapsed_ms'] for x in oldrows if x['model']==m and x['case']==r['case']) for r in freshrows)/1000)<1e-8
        for role,device in cf['devices'].items():
            a=cp['artifacts']['tinybrainbot'][role];assert device['firmware']=='0.9.0' and device['model_ready'] and not device['worker_busy'] and device['model_id']==a['model_id'] and device['artifact_id']==a['artifact_id']
        latest['cap_v3']={'fresh_quality_outputs':43,'reused_eos_outputs':5,'new_physical_streams':46,'higher_evaluations':48,'old_prefixes_verified':48,'paired_arithmetic_verified':True,'restored_tiny_recorded':True,'scope':'Recorded integrity/arithmetic; not independent semantic re-rating.'}
    return {'passed':True,'files_hashed':len(hashes),'representation_relationships':len(representations),
            'historical_public_protocol_pairs':len(protocols),'relative_markdown_links':links,
            'figure_source_relationships':figure_dependencies,
            'matched_quality_outputs':64,'matched_timing_packages':32,'tinybrainbot_quality_outputs':n,
            'tinybrainbot_timing_repetitions':len(latency),'model_or_device_runs':0,
            'latest':latest,
            'tables':{'matched_quality':counts,'matched_timing':matched_timing,'tinybrainbot_quality':s['counts'],
                      'tinybrainbot_p4_latency_seconds':latency}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('snapshot',type=pathlib.Path,nargs='?',default=pathlib.Path(__file__).resolve().parents[1]);parser.add_argument('--output',type=pathlib.Path)
    args=parser.parse_args();result=verify(args.snapshot)
    if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='tables'}))
