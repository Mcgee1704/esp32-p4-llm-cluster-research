"""Offline audit, rating seal and paired output-cap analysis. No model/device calls."""
import argparse,hashlib,json,pathlib,subprocess
from quality_v2_results import read,write,sha,stream
import quality_v2_results as baseline_results
ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/'data/quality-cap-v3-2026-10-30'
BASE=ROOT/'data/quality-v2-2026-10-30'
PRIVATE=ROOT/'.local/quality-cap-v3-2026-10-30'
MODELS=['tinybrainbot','supra']
CATS=['facts','reasoning','exact','grounded','uncertainty','story']

def protocol():
 p=read(DATA/'protocol.json');marker=DATA/'protocol.sha256';assert marker.read_text().strip()==sha(DATA/'protocol.json')
 return p

def audit():
 p=protocol();baseline_results.audit_recorded()
 assert all(sha(BASE/n)==v for n,v in p['baseline_sha256'].items())
 b=read(BASE/'protocol.json');low=read(BASE/'host-references.json');refs=read(DATA/'host-references.json');h=read(DATA/'host-receipt.json')
 assert p['inputs']==b['inputs'] and p['case_order']==b['case_order'] and p['artifacts']==b['artifacts']
 assert h['protocol_sha256']==sha(DATA/'protocol.json') and h['references_sha256']==sha(DATA/'host-references.json') and h['sources']==p['sources']
 assert h['new_references']==48 and h['old_prefixes_equal']==48 and h['old_eos_answers_fully_equal']==5 and h['known_controls_equal']==2 and h['archived_dll_preserved']
 for c,bc in zip(p['cases'],b['cases']):
  assert {k:v for k,v in c.items() if k not in ['limit','baseline_limit']}=={k:v for k,v in bc.items() if k!='limit'}
  assert c['limit']==2*c['baseline_limit']==2*bc['limit']
  for m in MODELS:
   r=refs[m][c['id']];l=low[m][c['id']];assert r['prompt_tokens']==l['prompt_tokens']==p['inputs'][m][c['id']]['tokens']
   assert len(r['tokens'])<=c['limit'] and len(r['prompt_tokens'])+c['limit']-1<=256 and r['tokens'][:len(l['tokens'])]==l['tokens']
   if l['eos']:assert r==l
 rows=read(DATA/'device-runs.json');controls=read(DATA/'controls.json');final=read(DATA/'final.json');paths=[]
 assert len(rows)==48 and [(x['model'],x['case']) for x in rows]==[(m,c) for m in MODELS for c in p['case_order']]
 assert [x['model'] for x in controls]==MODELS and final['completed'] and final['failure'] is None and final['queued']==final['running']==0 and final['mode']=='sharded'
 reuse={(x['model'],x['case']) for x in p['reused_eos']};assert len(reuse)==5
 for row in rows+controls+[final['restoration_control']]:
  reused=row['origin']=='reused-baseline-eos';m,cid=row['model'],row['case']
  assert reused==((m,cid) in reuse)
  if not reused:assert row['origin']=='fresh'
  path=(BASE if reused else DATA)/row['file'];assert path not in paths;paths.append(path)
  assert stream(path,refs[m][cid])==row['done']
  if reused:assert sha(path)==row['baseline_file_sha256'] and refs[m][cid]['eos']
  elif cid!='W':
   pieces=[x for x in (json.loads(line) for line in path.read_bytes().splitlines()) if 'token' in x];l=low[m][cid]
   assert [x['token'] for x in pieces[:len(l['tokens'])]]==l['tokens']
   assert b''.join(bytes.fromhex(x['bytes_hex']) for x in pieces[:len(l['tokens'])]).decode('utf-8','replace')==l['text']
 assert len(paths)==51 and sum(x['origin']=='fresh' for x in rows)==43 and sum(x['origin']=='reused-baseline-eos' for x in rows)==5
 for label,m in [('tinybrainbot-loaded','tinybrainbot'),('tinybrainbot-tested','tinybrainbot'),('supra-loaded','supra'),('supra-tested','supra'),('restored','tinybrainbot')]:
  states=read(DATA/(label+'-states.json'))
  for role,s in states.items():
   a=p['artifacts'][m][role];assert s['firmware']=='0.9.0' and s['model_ready'] and not s['worker_busy'] and not s['ota_pending']
   assert s['model_id']==a['model_id'] and s['artifact_id']==a['artifact_id'] and s['context']==256 and s['quant_bits']==4 and s['first_layer']==(0 if role=='coordinator' else 4) and s['end_layer']==(4 if role=='coordinator' else 12)
 for role,s in final['devices'].items():
  a=p['artifacts']['tinybrainbot'][role];assert s['model_id']==a['model_id'] and s['artifact_id']==a['artifact_id'] and s['firmware']=='0.9.0' and s['model_ready'] and not s['worker_busy'] and not s['ota_pending']
 return p,refs,low,rows,paths

def validate():
 p=protocol();masked=read(DATA/'masked-responses.json');ratings=read(DATA/'masked-ratings.json')
 assert masked['protocol_sha256']==ratings['protocol_sha256']==sha(DATA/'protocol.json') and masked['mask_commitment_sha256']==p['mask_commitment_sha256']
 assert ratings['masked_responses_sha256']==sha(DATA/'masked-responses.json') and len(masked['rows'])==24 and len(ratings['rows'])==48
 assert {(x['case'],x['label']) for x in ratings['rows']}=={(c['id'],lab) for c in p['cases'] for lab in ['A','B']}
 for c in p['cases']:
  mr=next(x for x in masked['rows'] if x['case']==c['id']);assert all(mr[k]==c[{'case':'id'}.get(k,k)] for k in ['case','category','user','expected','limit'])
  for lab in ['A','B']:
   r=next(x for x in ratings['rows'] if x['case']==c['id'] and x['label']==lab);assert isinstance(r['note'],str) and r['note'].strip()
   if c['category']=='exact':assert type(r['exact']) is bool and r['exact']==(mr['outputs'][lab]['text'].strip()==c['expected'])
   elif c['category']=='story':assert all(type(r[k]) is bool for k in ['topic','coherent','resolution','two_sentences'])
   else:assert type(r['core']) is bool and (r['clean'] is None or type(r['clean']) is bool) and (r['clean'] is not True or r['core'])
 return p,masked,ratings

def unblind():
 p,masked,ratings=validate();assert not (DATA/'unblinding.json').exists()
 rel=(DATA/'masked-ratings.json').relative_to(ROOT).as_posix();commit=subprocess.check_output(['git','log','-1','--format=%H','--',rel],cwd=ROOT).decode().strip()
 assert commit and subprocess.check_output(['git','show',commit+':'+rel],cwd=ROOT)==(DATA/'masked-ratings.json').read_bytes()
 rel2=(DATA/'masked-responses.json').relative_to(ROOT).as_posix();assert subprocess.check_output(['git','show',commit+':'+rel2],cwd=ROOT)==(DATA/'masked-responses.json').read_bytes()
 assert subprocess.run(['git','cat-file','-e',commit+':'+(DATA/'unblinding.json').relative_to(ROOT).as_posix()],cwd=ROOT,capture_output=True).returncode!=0
 mapping=read(PRIVATE/'mask-key.json');assert sha(PRIVATE/'mask-key.json')==p['mask_commitment_sha256']
 write(DATA/'unblinding.json',{'mapping':mapping,'mapping_sha256':p['mask_commitment_sha256'],'ratings_commit':commit,'ratings_sha256':sha(DATA/'masked-ratings.json'),'masked_responses_sha256':sha(DATA/'masked-responses.json'),'scope':'Higher-cap ratings committed before new mapping disclosure. Same author knows prior answers/ratings; not independent or fully blind.'})
 print('Committed higher-cap ratings verified; mapping unsealed.',flush=True)

def success(r,cat):return r['exact'] if cat=='exact' else all(r[k] for k in ['topic','coherent','resolution','two_sentences']) if cat=='story' else r['clean']
def counts(rows,cat):
 d={'n':len(rows)}
 if cat=='exact':d['exact']=sum(x['exact'] for x in rows)
 elif cat=='story':
  d.update({k:sum(x[k] for x in rows) for k in ['topic','coherent','resolution','two_sentences']});d['strict_completion']=sum(success(x,cat) for x in rows)
 else:
  d.update(core=sum(x['core'] for x in rows),confirmed_clean=sum(x['clean'] is True for x in rows),uncertain_clean=sum(x['clean'] is None for x in rows))
  if cat=='uncertainty' and len(rows)==4:d['subgroups']={g:counts([x for x in rows if x['subgroup']==g],cat) for g in ['unanswerable','answerable']}
 return d

def analyze():
 p,refs,low,raw,paths=audit();_,masked,ratings=validate();u=read(DATA/'unblinding.json');mapping=u['mapping'];old=read(BASE/'reviewed-results.json')
 assert hashlib.sha256((json.dumps(mapping,indent=2)+'\n').encode()).hexdigest()==u['mapping_sha256']==p['mask_commitment_sha256']
 assert set(mapping['labels'])=={c['id'] for c in p['cases']} and all(set(v)=={'A','B'} and set(v.values())==set(MODELS) for v in mapping['labels'].values()) and sum(v['A']=='tinybrainbot' for v in mapping['labels'].values())==12
 assert u['ratings_sha256']==sha(DATA/'masked-ratings.json') and u['masked_responses_sha256']==sha(DATA/'masked-responses.json')
 resolved=[];pairs=[]
 for rr in ratings['rows']:
  m=mapping['labels'][rr['case']][rr['label']];c=next(c for c in p['cases'] if c['id']==rr['case']);r=refs[m][c['id']];l=low[m][c['id']];mr=next(x for x in masked['rows'] if x['case']==c['id'])['outputs'][rr['label']]
  assert mr=={'text':r['text'],'eos':r['eos'],'cap_reached':len(r['tokens'])==c['limit'] and not r['eos']}
  oldrow=next(x for x in old if x['case']==c['id'] and x['model']==m);origin=next(x['origin'] for x in raw if x['case']==c['id'] and x['model']==m)
  row={**rr,'model':m,'category':c['category'],'subgroup':c.get('subgroup'),'eos':r['eos'],'cap_reached':mr['cap_reached'],'output_tokens':len(r['tokens']),'baseline_output_tokens':len(l['tokens']),'added_tokens':len(r['tokens'])-len(l['tokens']),'origin':origin};resolved.append(row)
  if origin=='reused-baseline-eos':
   keys=['exact'] if c['category']=='exact' else ['core','clean']
   assert all(row[k]==oldrow[k] for k in keys),'Identical EOS output received inconsistent rubric judgments: '+c['id']
  before,after=success(oldrow,c['category']),success(row,c['category'])
  def label(x):return 'success' if x is True else 'failure' if x is False else 'uncertain'
  pairs.append({'model':m,'case':c['id'],'category':c['category'],'baseline_success':before,'higher_success':after,'transition':label(before)+'_to_'+label(after),'baseline_rating':oldrow,'higher_rating':row,'higher_origin':origin})
 out={}
 for m in MODELS:
  out[m]={}
  for cat in CATS:
   ll=[x for x in old if x['model']==m and x['category']==cat];hh=[x for x in resolved if x['model']==m and x['category']==cat];pp=[x for x in pairs if x['model']==m and x['category']==cat]
   assert len(ll)==len(hh)==len(pp)==4
   transitions={a+'_to_'+b:sum(x['transition']==a+'_to_'+b for x in pp) for a in ['success','failure','uncertain'] for b in ['success','failure','uncertain']}
   out[m][cat]={'baseline':counts(ll,cat),'higher':counts(hh,cat),'transitions':transitions,'newly_confirmed':sum(x['baseline_success'] is not True and x['higher_success'] is True for x in pp),'lost_confirmed':sum(x['baseline_success'] is True and x['higher_success'] is not True for x in pp)}
 summary={'categories':out,'fresh_quality_outputs':43,'reused_eos_outputs':5,'new_physical_streams':46,'quality_evaluations':48,'old_prefixes_equal':48,'ratings_commit':u['ratings_commit'],'restored_tinybrainbot':True,'tokens':{m:{'baseline':sum(len(v['tokens']) for k,v in low[m].items() if k!='W'),'higher':sum(len(v['tokens']) for k,v in refs[m].items() if k!='W'),'cap_reached':sum(x['cap_reached'] for x in resolved if x['model']==m),'eos':sum(x['eos'] for x in resolved if x['model']==m)} for m in MODELS},'scope':'Paired descriptive cap sensitivity on known questions and greedy prefixes; no pooled ranking, independent review, significance or equal-work speed claim.'}
 oldraw=read(BASE/'device-runs.json');summary['fresh_subset_cost']={}
 for m in MODELS:
  rr=[x for x in raw if x['model']==m and x['origin']=='fresh'];oo=[next(x for x in oldraw if x['model']==m and x['case']==r['case']) for r in rr]
  summary['fresh_subset_cost'][m]={'n':len(rr),'historical_baseline_seconds':sum(x['done']['elapsed_ms'] for x in oo)/1000,'fresh_higher_seconds':sum(x['done']['elapsed_ms'] for x in rr)/1000,'baseline_output_tokens':sum(x['done']['output_tokens'] for x in oo),'higher_output_tokens':sum(x['done']['output_tokens'] for x in rr),'scope':'Same formerly capped cases; historical baseline versus fresh higher-cap elapsed sums, unequal output work, fixed model order. Reused EOS timings excluded. Not a kernel-speed or randomized timing study.'}
 write(DATA/'reviewed-results.json',resolved);write(DATA/'paired-results.json',pairs);write(DATA/'summary.json',summary)
 files=[DATA/n for n in ['protocol.json','host-receipt.json','host-references.json','masked-responses.json','masked-ratings.json','unblinding.json','summary.json','paired-results.json','reviewed-results.json','final.json']]+paths+[pathlib.Path(__file__)]
 write(DATA/'record-audit.json',{'passed':True,'new_physical_streams':46,'reused_eos_streams':5,'total_streams_checked':51,'old_prefixes_checked':48,'rating_rows':48,'source_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in files}})
 print(json.dumps({'passed':True,'new_physical_streams':46,'reused_eos':5,'tokens':summary['tokens'],'categories':out}),flush=True)

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('stage',choices=['audit','validate','unblind','analyze']);globals()[a.parse_args().stage]()
