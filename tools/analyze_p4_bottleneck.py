"""Offline decomposition of retained P4 timing profiles; no device calls."""
import statistics
from p4_compare_results import DATA,ROOT,read,write,sha
from plot_matched_models import Canvas,MUTED
from plot_p4_compare import save


def main():
    rows=read(DATA/'timing-runs.json');assert len(rows)==12
    detail=[];groups={}
    for r in rows:
        d=r['done'];p=d['profile'];total=d['elapsed_ms'];a=p['master_compute_ms'];b=p['worker_compute_ms'];rpc=p['rpc_total_ms']
        assert 0<a+b<=total and rpc>=b and d['output_tokens']==16 and not d['eos']
        detail.append({'model':r['model'],'case':r['case'],'block':r['block'],'total_ms':total,'coordinator_execution_ms':a,
            'worker_execution_ms':b,'outside_execution_ms':total-a-b,'rpc_outside_worker_ms':rpc-b,
            'execution_percent':100*(a+b)/total,'conditional_zero_residual_factor':total/(a+b),
            'coordinator_output_head_ms':d['kernel']['finish_ms']})
    for m in ['tinybrainbot','supra']:
        for case in ['B1','B2']:
            rs=[r for r in detail if r['model']==m and r['case']==case];assert len(rs)==3
            groups[m+'-'+case]={k:statistics.median(r[k] for r in rs) for k in rs[0] if k not in ['model','case','block']}
    source={n:sha(DATA/n) for n in ['protocol.json','timing-runs.json','timing-summary.json']}
    write(DATA/'bottleneck-analysis.json',{'classification':'Post-hoc descriptive profile analysis; no new hardware experiment',
        'groups':groups,'runs':detail,'source_sha256':source,
        'semantics':'Execution spans include arithmetic, memory stalls, scheduled pauses and synchronization. RPC total includes worker execution. Residual is not a packet-measured network duration.',
        'bound':'Zero-residual factor holds execution spans fixed and unrealistically removes ALL remaining time. It is a conditional accounting bound, not an attainable LAN prediction.'})
    c=Canvas(1110,'Where the two-P4 time goes','Retained 12 capped timing runs | 16 output tokens | Same firmware 0.7.0 | Offline profile analysis')
    colors=['#27799b','#198577','#bd8a3d'];x0=440;width=830;maximum=60
    for i,key in enumerate(['tinybrainbot-B1','tinybrainbot-B2','supra-B1','supra-B2']):
        rs=[r for r in detail if r['model']+'-'+r['case']==key];r=sorted(rs,key=lambda r:r['total_ms'])[1];y=180+i*145
        c.text(48,y,key.replace('tinybrainbot','TinyBrainBot').replace('supra','Supra2'),25,weight='bold')
        x=x0
        for name,color in zip(['coordinator_execution_ms','worker_execution_ms','outside_execution_ms'],colors):
            w=r[name]/1000/maximum*width;c.rect(x,y-26,w,36,color,2);x+=w
        c.text(1490,y+2,f"{r['total_ms']/1000:.3f} s",25,anchor='end')
        c.text(x0,y+49,f"Local execution {groups[key]['execution_percent']:.3f}% | Outside spans {groups[key]['outside_execution_ms']/1000:.3f} s median",22,MUTED)
    for i,(label,color) in enumerate(zip(['Coordinator execution','Worker execution','Outside both spans'],colors)):
        x=48+i*510;c.rect(x,750,24,24,color,3);c.text(x+38,772,label,23)
    c.rect(48,815,1504,150,'#dce9f2');c.text(72,859,'RPC waiting is mostly remote execution, not pure network loss.',28,weight='bold')
    c.text(72,902,'Execution includes memory access, pauses and synchronization. These profiles do not isolate arithmetic or bandwidth.',22,MUTED)
    c.text(72,943,'Bars use the median-total run; captions use medians across three runs. The residual is not packet-captured LAN time.',21,MUTED)
    c.text(48,1018,'Next useful experiment: isolate local INT4 matrix execution and memory access before changing LAN transport.',24,weight='bold')
    c.text(48,1065,'Removing all residual time would save under 1% here if execution spans stayed fixed. This is not a guaranteed speedup.',21,MUTED)
    save(c,'matched-p4-bottleneck',['bottleneck-analysis.json','timing-runs.json'])
    meta=ROOT/'docs/figures/matched-p4-bottleneck-2026-10-30.json';v=read(meta);v['source_sha256']['tools/analyze_p4_bottleneck.py']=sha(ROOT/'tools/analyze_p4_bottleneck.py');write(meta,v)
    print('PASS 12 profile decompositions; RPC overlap excluded; four three-run medians')


if __name__=='__main__':main()
