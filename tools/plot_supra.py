"""English, standalone research figures from local Supra records only."""
import json
import statistics as stats
from plot_matched_models import Canvas,OUT
from pack_supra import ROOT
DATA=ROOT/'docs/research/data'
C50='#247ca3';C100='#8557a6';WORK='#278375';OTHER='#b78437';MUTED='#586c7d'


def read(model,name):return json.loads((DATA/(model+'-2026-10-29')/name).read_text('utf-8'))


def architecture():
    c=Canvas(1130,'Two P4s, one larger language model','Real model shards | 32 MiB PSRAM per board | Layer split 4 + 8 | Context 256')
    c.rect(48,135,1504,100)
    c.text(72,173,'Browser / local client → master queue → one distributed request at a time',27,weight='bold')
    c.text(72,211,'Ethernet carries inference; USB-C supplies power. No board-to-board USB link is used.',22,MUTED)
    c.rect(48,270,660,430);c.rect(892,270,660,430)
    c.text(76,314,'P4 COORDINATOR',28,C50,'bold');c.text(920,314,'P4 LAYER WORKER',28,WORK,'bold')
    for y,text in [(363,'Full byte-BPE tokenizer + tied embedding'),(406,'Early transformer layers 0–3'),(578,'Final norm + full-vocabulary output'),(627,'Greedy next token / stop at EOS')]:c.text(76,y,text,24)
    for y,text in [(363,'Later transformer layers 4–11'),(406,'Own weights + own layer KV caches'),(578,'Returns the updated activation'),(627,'No tokenizer, embedding or output table')]:c.text(920,y,text,24)
    c.arrow(708,451,892,451,C50);c.arrow(892,528,708,528,WORK)
    c.text(800,434,'activation',20,MUTED,anchor='middle');c.text(800,563,'FP32 vector',20,MUTED,anchor='middle')
    c.text(800,476,'512 / 768',20,MUTED,anchor='middle');c.text(800,504,'values',20,MUTED,anchor='middle')
    c.text(76,674,'Embedding/output stays on the coordinator.',20,MUTED)
    c.text(920,674,'Sequential dependency for every prompt/output token.',20,MUTED)
    c.rect(48,730,1504,294)
    c.text(72,772,'Resident and flash capacity',28,weight='bold')
    c.text(72,810,'Model',22,MUTED);c.text(455,810,'Coordinator expanded',22,MUTED);c.text(835,810,'Worker expanded',22,MUTED);c.text(1190,810,'Flash files',22,MUTED)
    for row,(model,label,color) in enumerate([('supra50','Supra 51.79M',C50),('supra100','Supra 100.68M',C100)]):
        a=read(model,'model-artifacts.json');y=855+row*54
        c.text(72,y,label,25,color,'bold');c.text(455,y,f"{a['coordinator']['bytes']/1e6:.2f} MB",25);c.text(835,y,f"{a['worker']['bytes']/1e6:.2f} MB",25)
        text='15.17 / 11.99 MB raw' if model=='supra50' else '19.76 / 20.07 MB zlib'
        c.text(1190,y,text,22,color)
    c.text(72,964,'FP32 KV at context 256: 2.10 MB coordinator + 4.19 MB worker; runtime allocations are additional.',22,MUTED)
    c.text(48,1071,'Lossless zlib changes stored size only. Model identity and INT4 values are unchanged after cold-load.',22,MUTED)
    c.text(48,1104,'This increases model capacity. A second board does not remove the sequential token/layer dependency.',22,MUTED)
    c.save('supra-model-parallel-setup',[DATA/(m+'-2026-10-29')/'model-artifacts.json' for m in ['supra50','supra100']])


def measurements():
    models=[('supra50','Supra 51.79M',C50),('supra100','Supra 100.68M',C100)]
    c=Canvas(1210,'More parameters fit. Useful quality still needs work.','Two real P4s | Greedy row-INT4 | Story S2, 16 output tokens | Three descriptive timing repetitions')
    c.rect(48,137,1504,468);c.text(72,181,'Wall-time decomposition · median run',28,weight='bold')
    totals=[];summary={}
    for model,label,color in models:
        runs=read(model,'timing.json');total=stats.median(r['elapsed_ms'] for r in runs)/1000;totals.append(total)
        selected=sorted(runs,key=lambda r:r['elapsed_ms'])[len(runs)//2]
        master=selected['profile']['master_compute_ms']/1000
        worker=selected['profile']['worker_compute_ms']/1000
        summary[model]={'decomposition':'components from median-wall-time run','elapsed_seconds':total,'range_seconds':[min(r['elapsed_ms'] for r in runs)/1000,max(r['elapsed_ms'] for r in runs)/1000],
                        'master_compute_seconds':master,'worker_compute_seconds':worker,'remaining_seconds':max(0,total-master-worker),
                        'prompt_tokens':runs[0]['prompt_tokens'],'decode_tokens_per_second':stats.median((r['output_tokens']-1)*1000/(r['elapsed_ms']-r['ttft_ms']) for r in runs)}
    scale=1170/max(totals)
    for i,(model,label,color) in enumerate(models):
        r=summary[model];y=235+i*145;c.text(72,y,label,25,color,'bold')
        c.text(400,y,f"{r['prompt_tokens']} prompt tokens · {r['elapsed_seconds']:.2f} s total · {r['decode_tokens_per_second']:.3f} decode tok/s",24)
        x=72
        for key,col in [('master_compute_seconds',color),('worker_compute_seconds',WORK),('remaining_seconds',OTHER)]:
            w=r[key]*scale;c.rect(x,y+20,w,38,col,0);x+=w
        c.text(72,y+90,f"Range {r['range_seconds'][0]:.3f}–{r['range_seconds'][1]:.3f} s; three runs, fixed model order",21,MUTED)
    c.rect(72,545,22,18,C50,0);c.text(105,562,'coordinator compute',21,MUTED)
    c.rect(475,545,22,18,WORK,0);c.text(508,562,'worker compute',21,MUTED)
    c.rect(840,545,22,18,OTHER,0);c.text(873,562,'remaining wall time',21,MUTED)
    c.rect(48,635,735,375);c.text(72,678,'Free PSRAM after study',27,weight='bold')
    c.text(72,711,'32 MiB per board; result buffers remain allocated',20,MUTED)
    for i,(model,label,color) in enumerate(models):
        memory=read(model,'device-memory.json')
        for j,role in enumerate(['coordinator','worker']):
            y=752+i*108+j*43;v=memory[role]['free_psram']/1048576
            c.text(72,y,f'{label} {role}',20,color);c.rect(445,y-17,250,19,'#e4ebf0',0);c.rect(445,y-17,v/32*250,19,color,0);c.text(710,y,f'{v:.2f}',19)
    c.text(72,981,'Values are MiB. Flash compression saves no runtime RAM.',20,MUTED)
    c.rect(813,635,739,375);c.text(837,678,'Quantization can erase a correct answer',26,weight='bold')
    c.text(837,719,'100M · exact author ChatML bicycle question',21,MUTED)
    c.text(837,766,'Host: F16 source / FP32 compute:',22,C100,'bold');c.text(837,805,'“A standard bicycle has 2 wheels…”',25)
    c.text(837,854,'Row-INT4 / both real P4s:',22,OTHER,'bold');c.text(837,893,'“around 2.5-3.5 wheels…”',25)
    c.text(837,944,'P4 INT4 matches its quantized host reference.',21,MUTED)
    c.text(837,981,'Larger-model execution ≠ reliable factual answers.',21,MUTED)
    c.text(48,1064,'Latency includes prefill. Decode rate excludes prefill using first-token time; final bookkeeping remains included.',22,MUTED)
    c.text(48,1101,'Tokenizers differ; S2 uses 20 prompt tokens in both. No single-P4 speedup baseline or global quality ranking.',22,MUTED)
    c.text(48,1138,'Primary 50M timing: firmware 0.6.0; 100M: 0.6.1. Lossless-loading control confirms identical 50M output.',22,MUTED)
    sources=[DATA/(m+'-2026-10-29')/name for m in ['supra50','supra100'] for name in ['timing.json','device-memory.json','host-generations.json','source-controls.json']]
    c.save('supra-capacity-latency-quality',sources)
    (DATA/'supra-summary-2026-10-29.json').write_text(json.dumps(summary,indent=2)+'\n','utf-8')


if __name__=='__main__':
    architecture()
    if all((DATA/(m+'-2026-10-29')/'timing.json').exists() for m in ['supra50','supra100']):measurements()
