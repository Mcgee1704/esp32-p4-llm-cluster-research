"""Offline recorded-data audit and review sealing; never calls a model/device."""
import argparse,hashlib,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/'data/quality-v2-2026-10-30'
PRIVATE=ROOT/'.local/quality-v2-2026-10-30'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,x):p.write_bytes((json.dumps(x,indent=2)+'\n').encode('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def protocol():
 p=read(DATA/'protocol.json');public=DATA/'protocol.public.sha256';marker=public if public.exists() else DATA/'protocol.sha256'
 assert marker.read_text().strip()==sha(DATA/'protocol.json')
 return p
def stream(path,ref):
 items=[json.loads(line) for line in path.read_bytes().splitlines()]
 assert items and sum(x.get('done') is True for x in items)==1 and items[-1].get('done') and not items[-1].get('error')
 assert [x['token'] for x in items if 'token' in x]==ref['tokens']
 raw=b''.join(bytes.fromhex(x['bytes_hex']) for x in items if 'bytes_hex' in x)
 assert raw.decode('utf-8','replace')==ref['text'] and items[-1]['eos']==ref['eos']
 assert items[-1]['output_tokens']==len(ref['tokens']) and items[-1]['prompt_tokens']==len(ref['prompt_tokens'])
 assert items[-1]['boards']==2 and items[-1]['kernel']['mode']=='tile4'
 assert items[-1]['kernel']['owner_core_mask']==2 and items[-1]['kernel']['helper_core_mask']==1
 return items[-1]
def audit_recorded():
 p=protocol();h=read(DATA/'host-receipt.json');refs=read(DATA/'host-references.json')
 assert h['protocol_sha256']==sha(DATA/'protocol.json') and h['references_sha256']==sha(DATA/'host-references.json')
 assert h['sources']==p['sources'] and h['new_quality_generations']==48 and h['known_controls_equal']==2 and h['archived_dll_preserved']
 rows=read(DATA/'device-runs.json');controls=read(DATA/'controls.json');final=read(DATA/'final.json')
 assert [(x['model'],x['case']) for x in rows]==[(m,c) for m in ['tinybrainbot','supra'] for c in p['case_order']]
 assert len(rows)==48 and [x['model'] for x in controls]==['tinybrainbot','supra']
 assert final['completed'] and final['failure'] is None and final['queued']==final['running']==0 and final['mode']=='sharded'
 allrows=rows+controls+[final['restoration_control']];paths=[]
 for x in allrows:
  path=DATA/x['file'];assert path not in paths;paths.append(path);assert stream(path,refs[x['model']][x['case']])==x['done']
 assert len(paths)==51
 for label,m in [('tinybrainbot-loaded','tinybrainbot'),('tinybrainbot-tested','tinybrainbot'),('supra-loaded','supra'),('supra-tested','supra'),('restored','tinybrainbot')]:
  states=read(DATA/(label+'-states.json'))
  for role,s in states.items():
   a=p['artifacts'][m][role]
   assert s['firmware']=='0.9.0' and s['model_ready'] and not s['worker_busy'] and not s['ota_pending']
   assert s['model_id']==a['model_id'] and s['artifact_id']==a['artifact_id'] and s['context']==256 and s['quant_bits']==4
 for role,s in final['devices'].items():
  assert s['model_id']==p['artifacts']['tinybrainbot'][role]['model_id'] and s['artifact_id']==p['artifacts']['tinybrainbot'][role]['artifact_id']
  assert s['firmware']=='0.9.0' and s['model_ready'] and not s['worker_busy'] and not s['ota_pending']
 return p,rows,refs,paths
def validate_ratings():
 p=protocol();masked=read(DATA/'masked-responses.json');r=read(DATA/'masked-ratings.json')
 assert masked['protocol_sha256']==sha(DATA/'protocol.json') and masked['mask_commitment_sha256']==p['mask_commitment_sha256']
 assert r['masked_responses_sha256']==sha(DATA/'masked-responses.json') and r['protocol_sha256']==sha(DATA/'protocol.json')
 assert len(masked['rows'])==24 and len(r['rows'])==48
 assert {(x['case'],x['label']) for x in r['rows']}=={(c['id'],lab) for c in p['cases'] for lab in ['A','B']}
 for c in p['cases']:
  mr=next(x for x in masked['rows'] if x['case']==c['id']);assert mr['category']==c['category'] and mr['user']==c['user'] and mr['expected']==c['expected']
  for label in ['A','B']:
   row=next(x for x in r['rows'] if x['case']==c['id'] and x['label']==label);assert isinstance(row['note'],str) and row['note'].strip()
   if c['category']=='exact':
    assert type(row['exact']) is bool and row['exact']==(mr['outputs'][label]['text'].strip()==c['expected'])
   elif c['category']=='story':
    assert all(type(row[k]) is bool for k in ['topic','coherent','resolution','two_sentences'])
   else:
    assert type(row['core']) is bool and (row['clean'] is None or type(row['clean']) is bool)
    assert row['clean'] is not True or row['core']
 return p,masked,r
def unblind():
 p,masked,r=validate_ratings();assert not (DATA/'unblinding.json').exists()
 path=(DATA/'masked-ratings.json').relative_to(ROOT).as_posix();commit=subprocess.check_output(['git','log','--format=%H','-1','--',path],cwd=ROOT).decode().strip()
 assert commit and subprocess.check_output(['git','show',commit+':'+path],cwd=ROOT)==(DATA/'masked-ratings.json').read_bytes()
 mpath=(DATA/'masked-responses.json').relative_to(ROOT).as_posix();assert subprocess.check_output(['git','show',commit+':'+mpath],cwd=ROOT)==(DATA/'masked-responses.json').read_bytes()
 upath=(DATA/'unblinding.json').relative_to(ROOT).as_posix();check=subprocess.run(['git','cat-file','-e',commit+':'+upath],cwd=ROOT,capture_output=True);assert check.returncode!=0
 key=read(PRIVATE/'mask-key.json');assert sha(PRIVATE/'mask-key.json')==p['mask_commitment_sha256']
 write(DATA/'unblinding.json',{'mapping':key,'mapping_sha256':sha(PRIVATE/'mask-key.json'),'ratings_commit':commit,'ratings_sha256':sha(DATA/'masked-ratings.json'),'masked_responses_sha256':sha(DATA/'masked-responses.json'),'scope':'Unsealed only after committed masked ratings; same author, not independent/fully blind.'})
 print('Unblinding receipt written after committed masked ratings.',flush=True)
def analyze():
 p,raw,refs,paths=audit_recorded();_,masked,r=validate_ratings();u=read(DATA/'unblinding.json')
 mapping=u['mapping'];canonical=(json.dumps(mapping,indent=2)+'\n').encode('utf-8');assert hashlib.sha256(canonical).hexdigest()==u['mapping_sha256']==p['mask_commitment_sha256']
 assert set(mapping['labels'])=={c['id'] for c in p['cases']}
 assert all(set(v)=={'A','B'} and set(v.values())=={'tinybrainbot','supra'} for v in mapping['labels'].values())
 assert sum(v['A']=='tinybrainbot' for v in mapping['labels'].values())==12
 assert u['ratings_sha256']==sha(DATA/'masked-ratings.json') and u['masked_responses_sha256']==sha(DATA/'masked-responses.json')
 resolved=[]
 for row in r['rows']:
  m=mapping['labels'][row['case']][row['label']];c=next(c for c in p['cases'] if c['id']==row['case']);mr=next(x for x in masked['rows'] if x['case']==row['case'])
  assert mr['outputs'][row['label']]['text']==refs[m][row['case']]['text'] and mr['outputs'][row['label']]['eos']==refs[m][row['case']]['eos']
  expected_cap=len(refs[m][row['case']]['tokens'])==c['limit'] and not refs[m][row['case']]['eos'];assert mr['outputs'][row['label']]['cap_reached']==expected_cap
  resolved.append({**row,'model':m,'category':c['category'],'subgroup':c.get('subgroup'),'eos':refs[m][row['case']]['eos'],'cap_reached':expected_cap,'output_tokens':len(refs[m][row['case']]['tokens'])})
 counts={};paired={}
 for cat in ['facts','reasoning','exact','grounded','uncertainty','story']:
  counts[cat]={}
  for m in ['tinybrainbot','supra']:
   rr=[x for x in resolved if x['model']==m and x['category']==cat];assert len(rr)==4;d={'n':4,'eos':sum(x['eos'] for x in rr),'cap_reached':sum(x['cap_reached'] for x in rr)}
   if cat=='exact':d['exact']=sum(x['exact'] for x in rr)
   elif cat=='story':
    d.update({k:sum(x[k] for x in rr) for k in ['topic','coherent','resolution','two_sentences']});d['strict_completion']=sum(all(x[k] for k in ['topic','coherent','resolution','two_sentences']) for x in rr)
   else:
    d.update(core=sum(x['core'] for x in rr),confirmed_clean=sum(x['clean'] is True for x in rr),uncertain_clean=sum(x['clean'] is None for x in rr))
    if cat=='uncertainty':d['subgroups']={g:{'n':2,'core':sum(x['core'] for x in rr if x['subgroup']==g),'confirmed_clean':sum(x['clean'] is True for x in rr if x['subgroup']==g)} for g in ['unanswerable','answerable']}
   counts[cat][m]=d
  def success(x):return x['exact'] if cat=='exact' else all(x[k] for k in ['topic','coherent','resolution','two_sentences']) if cat=='story' else x['clean']
  pairs=[]
  for c in [c for c in p['cases'] if c['category']==cat]:pairs.append(tuple(success(next(x for x in resolved if x['case']==c['id'] and x['model']==m)) for m in ['tinybrainbot','supra']))
  paired[cat]={'both_success':sum(a is True and b is True for a,b in pairs),'tiny_only':sum(a is True and b is False for a,b in pairs),'supra_only':sum(a is False and b is True for a,b in pairs),'neither':sum(a is False and b is False for a,b in pairs),'uncertain_pair':sum(a is None or b is None for a,b in pairs)}
 write(DATA/'reviewed-results.json',resolved);write(DATA/'summary.json',{'counts':counts,'paired_cases':paired,'new_cases':24,'new_quality_outputs':48,'actual_streams_checked':51,'reused_quality_outputs':0,'masking':'Model-label-masked same-author review, not independent or completely blind; ratings committed before unsealing.','ratings_commit':u['ratings_commit'],'scope':'Constructed English cases; n=4/category, no pooled ranking, significance or matched-work speed claim.','restored_tinybrainbot':True})
 write(DATA/'record-audit.json',{'passed':True,'actual_streams_checked':51,'quality_outputs_checked':48,'masked_rating_rows':48,'source_sha256':{x.relative_to(ROOT).as_posix():sha(x) for x in [DATA/'protocol.json',DATA/'host-receipt.json',DATA/'host-references.json',DATA/'masked-responses.json',DATA/'masked-ratings.json',DATA/'unblinding.json',DATA/'summary.json',DATA/'reviewed-results.json',DATA/'final.json',pathlib.Path(__file__),*paths]}})
 print(json.dumps({'passed':True,'actual_streams':51,'quality_outputs':48,'categories':counts}),flush=True)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('stage',choices=['audit_recorded','validate_ratings','unblind','analyze']);args=a.parse_args();globals()[args.stage]()
