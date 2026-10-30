import compare_p4_models as c
p,commit=c.frozen();refs=c.read(c.DATA/'host-references.json')
assert c.sha(c.ROOT/'tools/continue_p4_compare.py')==c.read(c.DATA/'continuation.json')['script_sha256']
q=c.read(c.DATA/'quality-runs.json');t=c.read(c.DATA/'timing-runs.json');controls=c.read(c.DATA/'controls.json')
assert len(q)==12 and len(t)==2 and len(controls)==1
for name in ['final.json','restored-states.json','phase2-states.json']:
 path=c.DATA/name
 if path.exists():path.rename(c.DATA/('failed-attempt-'+name))
failed=None
def switch(model,label):
 c.switch(model,p,label)
 x=c.Dispatcher(c.MASTER).request('POST','/api/cluster',{'peer':c.PEER})
 assert x['configured'] and x['mode']=='sharded'
try:
 for phase in [2,3,4]:
  step=p['schedule'][phase-1];m=step['model'];label='phase'+str(phase);switch(m,label)
  if step['quality']:
   for case in p['cases']:
    q.append(c.infer(m,case,m+'-'+case['id'],p,refs));c.write(c.DATA/'quality-runs.json',q)
  controls.append(c.infer(m,p['benchmarks'][0],label+'-warmup',p,refs,4));c.write(c.DATA/'controls.json',controls)
  for block in step['blocks']:
   for case in (p['benchmarks'] if block!=2 else list(reversed(p['benchmarks']))):
    row=c.infer(m,case,f'{m}-block{block}-{case["id"]}',p,refs);row.update(block=block,phase=phase);t.append(row);c.write(c.DATA/'timing-runs.json',t)
 c.write(c.DATA/'timing-summary.json',c.paired_summary(t))
except BaseException as e:
 failed=str(e);c.write(c.DATA/'continuation-error.json',{'error':failed});raise
finally:
 switch('tinybrainbot','restored');row=c.infer('tinybrainbot',p['benchmarks'][0],'restoration-control',p,refs,4)
 states={r:c.status(h) for r,h in [('coordinator',c.MASTER),('worker',c.PEER)]};x=c.idle(c.Dispatcher(c.MASTER))
 c.write(c.LOCAL/'final.json',states);c.write(c.DATA/'final.json',{'completed':failed is None,'failure':failed,'devices':{r:c.sanitized(s) for r,s in states.items()},'restoration_control':row,'queued':x['queued'],'running':x['running'],'mode':x['mode']})
