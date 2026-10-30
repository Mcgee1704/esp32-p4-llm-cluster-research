"""Bounded follow-up: group-64 INT4 on host only, after the row-INT4 failure."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import json
from pack_supra import ROOT,np,load_source,tokenizer
from supra_source_controls import generate
from check_supra_native import write


def main():
    directory=ROOT/'.local/models/supra100-2c90ade6ab47';out=ROOT/'data/supra100-group64-2026-10-29'
    out.mkdir(exist_ok=False);prior=ROOT/'data/supra100-2026-10-29'
    protocol=json.loads((prior/'protocol.json').read_text('utf-8'));cases=[next(c for c in protocol['cases'] if c['id']==name) for name in ['N2','N4','N6','N7']]
    write(out/'protocol.json',{'scope':'Exploratory host-only follow-up selected after a row-INT4 bicycle regression; not part of the primary frozen study',
                             'cases':cases,'group_columns':64,'scale_precision':'FP32','context':256,'generation':'greedy, cap 16, source EOS 2/6',
                             'device_implementation':'Absent; hypothetical byte budget is not a P4 result'})
    c=json.loads((directory/'config.json').read_text('utf-8'));t,_=load_source(directory);vocab,*_=tokenizer(directory)
    q={};sizes={};error={'row_int4':0.,'group64_int4':0.};matrix_count=0
    for name,w in t.items():
        if w.ndim==2:
            assert w.shape[1]%64==0
            groups=w.reshape(w.shape[0],-1,64);scale=np.max(np.abs(groups),axis=2)/np.float32(7);scale[scale==0]=1
            q[name]=(np.clip(np.rint(groups/scale[:,:,None]),-7,7)*scale[:,:,None]).reshape(w.shape)
            sizes[name]=w.size//2+scale.size*4;matrix_count+=w.size
            rs=np.max(np.abs(w),axis=1)/np.float32(7);rs[rs==0]=1
            row=np.clip(np.rint(w/rs[:,None]),-7,7)*rs[:,None]
            error['row_int4']+=float(np.sum((row-w).astype('float64')**2))
            error['group64_int4']+=float(np.sum((q[name]-w).astype('float64')**2))
        else:q[name]=w;sizes[name]=w.size*4
    write(out/'weight-error.json',{'matrix_parameters':matrix_count,'weight_rmse':{k:(v/matrix_count)**.5 for k,v in error.items()},'scope':'Weight reconstruction only. Lower RMSE does not establish better generated answers.'})
    refs={r['case']:r for r in json.loads((prior/'host-generations.json').read_text('utf-8'))};rows=[]
    for case in cases:
        result=generate(c,q,refs[case['id']]['prompt_tokens'],16,vocab);rows.append({'case':case['id'],**result})
        write(out/'host-generations.json',rows);print(case['id'],ascii(result['text']),flush=True)
    coordinator=256+875268+sum(n for name,n in sizes.items() if not name.startswith('model.layers.') or int(name.split('.')[2])<4)
    worker=256+sum(n for name,n in sizes.items() if name.startswith('model.layers.') and int(name.split('.')[2])>=4)
    write(out/'hypothetical-budget.json',{'coordinator_expanded_bytes':coordinator,'worker_expanded_bytes':worker,'coordinator_KV_bytes':2097152,'worker_KV_bytes':4194304,
                                         'excludes':'Network, heap fragmentation, dispatcher buffers and runtime; no compressed flash artifact or C/device kernel exists for group64'})


if __name__=='__main__':main()
