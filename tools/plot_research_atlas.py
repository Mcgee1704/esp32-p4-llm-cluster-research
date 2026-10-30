"""Offline research atlas: retained reports, tables and figures; no device access."""
import hashlib
import json
import pathlib
import re
import subprocess
from html import escape
from plot_matched_models import Canvas, MUTED

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / 'docs/research'
STEM = DOC / 'figures/research-overview-2026-10-30'


def main():
    sources = sorted(DOC.glob('*.md'))
    c = Canvas(1710, 'Two ESP32-P4s: the complete research landscape',
               'Recorded experiments through 30 October 2026 | Separate workloads and evidence levels | Offline synthesis')
    c.rect(48,135,1504,225)
    c.text(72,178,'Model families actually evaluated',28,weight='bold')
    rows = [
        'TinyStories baseline / TinyStories-15M SFT: Llama story generation; early kernel and LAN controls',
        'TinyStories-Instruct-8M / TinyTalk-2: GPT-Neo, 19.70M actual parameters; complete model on each P4',
        'TinyTalk 1: GPT-Neo, 8.28M actual parameters; complete model on each P4',
        'Supra1.5: 51.79M Llama | Supra2: 100.68M Qwen3 | TinyBrainBot: 100.09M Llama; real two-P4 shards']
    for i,line in enumerate(rows): c.text(72,220+i*37,line,21)
    c.text(48,411,'A · Small-model matched trial: replicated models, two independent requests',27,weight='bold')
    c.text(48,448,'Same 16 input texts; row INT8. Facts and story criteria are separate, unblinded judgments.',21,MUTED)
    labels=['TinyStories SFT','Story-Instruct-8M','TinyTalk 1','TinyTalk-2']
    times=[10.733,11.484,5.232,11.479]
    facts=[0,0,0,5];topic=[4,4,1,3]
    c.text(48,492,'Model',21,weight='bold');c.text(420,492,'First facts /6',21,weight='bold')
    c.text(650,492,'Story topic /4',21,weight='bold');c.text(920,492,'Two-request package (s)',21,weight='bold')
    for i,name in enumerate(labels):
        y=535+i*54;c.text(48,y,name,23);c.text(460,y,str(facts[i])+'/6',23)
        c.text(700,y,str(topic[i])+'/4',23)
        c.rect(920,y-22,times[i]/12*420,25,'#3378ad',3);c.text(1360,y,f'{times[i]:.3f}',22)
    c.text(48,765,'B · Larger-model host quality trial: same 20 factual questions, native model framing',27,weight='bold')
    c.text(48,803,'First factual core / confirmed clean full response. Different questions from panels A and C.',21,MUTED)
    for i,(name,first,clean) in enumerate([('Supra2 F16 / FP32',11,5),('TinyBrainBot F16 / FP32',15,14),
                                          ('Supra2 row INT4',7,2),('TinyBrainBot row INT4',12,10)]):
        y=851+i*50;c.text(48,y,name,23)
        c.rect(540,y-23,first/20*590,12,'#aabccc',2)
        c.rect(540,y-8,clean/20*590,12,'#178476',2)
        c.text(1160,y,f'{first}/20 first; {clean}/20 clean',22)
    c.text(48,1061,'Supra INT4 also has two uncertain cleanliness judgments. No pooled score across studies.',21,MUTED)
    c.text(48,1120,'C · Matched real-P4 trial: 100M models, one request uses both boards',27,weight='bold')
    c.text(48,1160,'Row INT4 | firmware 0.7.0 | 4+8 layers | context 256 | 16 output tokens | n=3 per prefix/model',21,MUTED)
    for i,(name,clean,b1,b2) in enumerate([('TinyBrainBot',3,51.191699,55.439542),('Supra2',2,51.412125,55.677356)]):
        y=1216+i*52;c.text(48,y,name,24);c.text(360,y,f'Facts: 3/6 first; {clean}/6 clean',23)
        c.text(940,y,f'B1 {b1:.3f} s | B2 {b2:.3f} s',23)
    c.text(48,1340,'Observed latency difference ~0.43%; three repeats do not establish reliable speed superiority.',22,MUTED)
    c.rect(48,1390,1504,267,'#dce9f2')
    c.text(72,1434,'What the hardware work established',28,weight='bold')
    for i,line in enumerate([
        'Replicated small models: roughly 1.89–2.05x package throughput in the matched trial; no single-answer speedup.',
        'V3 kernel trial: ~1.52x direct speedup from dual to tile4 on each P4, within that earlier fixed workload.',
        'Supra2 quantization V2: source KL improves 76.84%, but fact screen falls 9/16 to 4/16; candidate rejected.',
        'INT4 microbench: streaming matrix ~10–11% slower than internal RAM; synthetic single-core result only.',
        'All reports, retained table values, original comparison figures and data-folder links are in the local atlas.']):
        c.text(72,1478+i*35,line,21)
    STEM.with_suffix('.svg').write_text('\n'.join(c.s+['</svg>'])+'\n',encoding='utf-8')
    runtime=pathlib.Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
    code='require('+json.dumps(str(runtime/'node_modules/sharp'))+')(process.argv[1]).png().toFile(process.argv[2])'
    subprocess.run([str(runtime/'bin/node.exe'),'-e',code,str(STEM.with_suffix('.svg')),str(STEM.with_suffix('.png'))],check=True)
    figures=sorted((DOC/'figures').glob('*.png'))
    parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
           '<title>P4 research atlas</title><style>body{font:16px system-ui;background:#eff4f8;color:#193347;max-width:1500px;margin:32px auto;padding:0 20px}img{width:100%;height:auto}a{color:#185e94}details{padding:14px 0;border-bottom:1px solid #b8cbd8}summary{cursor:pointer;font-weight:650}table{border-collapse:collapse;display:block;overflow:auto}td,th{padding:9px;text-align:left;border-bottom:1px solid #c7d6df}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:24px}input{font:inherit;padding:10px;width:min(90%,600px)}figure{margin:0}figcaption{padding:8px 0}</style>',
           '<h1>Two-P4 research atlas</h1><p>All retained research reports and PNG figures, through 30 October 2026. Observed results, host-only studies, analytical estimates and simulations remain separate. No new inference or hardware measurement.</p>',
           '<img src="figures/'+STEM.name+'.png" alt="Research overview: small models, host quality, matched P4 latency and optimization results">',
           '<h2>All original comparison figures and experimental setups</h2><div class="grid">']
    for p in figures:
        if p.stem==STEM.name: continue
        title=p.stem.replace('-',' ')
        parts.append(f'<figure><a href="figures/{p.name}"><img loading="lazy" src="figures/{p.name}" alt="{escape(title)}"></a><figcaption>{escape(title)}</figcaption></figure>')
    parts+=['</div><h2>Every retained report and its result tables</h2><label for="filter">Filter reports</label><br><input id="filter" type="search" placeholder="TinyBrainBot, kernel, simulation, Supra…">']
    for p in sources:
        text=p.read_text(encoding='utf-8-sig'); title=text.splitlines()[0].lstrip('# ')
        parts.append(f'<details class="report"><summary>{escape(title)}</summary><p><a href="{p.name}">Complete report and evidence links</a> · <a href="data/">All retained data folders</a></p>')
        tables=re.findall(r'(?m)^\|.*(?:\n\|.*)*',text)
        for table in tables:
            parts.append('<table>')
            for row in table.splitlines():
                cells=row.strip().strip('|').split('|')
                if all(re.fullmatch(r'[\s:\-]+',x) for x in cells):continue
                parts.append('<tr>'+''.join('<td>'+escape(x.strip())+'</td>' for x in cells)+'</tr>')
            parts.append('</table>')
        if not tables:parts.append('<p>See the complete report for narrative results, controls and evidence.</p>')
        parts.append('</details>')
    parts+=['<script>document.getElementById("filter").addEventListener("input",function(){for(const r of document.querySelectorAll(".report"))r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase())})</script></html>']
    (DOC/'research-atlas-2026-10-30.html').write_text('\n'.join(parts),encoding='utf-8')
    all_sources=sources+[ROOT/'tools/plot_research_atlas.py']+[p for p in figures if p.stem!=STEM.name]
    receipt={'reports':len(sources),'existing_figures':len(figures)-1,'scope':'All root research reports, all original PNG figures, all Markdown tables; not a pooled benchmark.',
             'sources':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in all_sources}}
    STEM.with_suffix('.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'reports':len(sources),'original_figures':len(figures)-1}))


if __name__=='__main__':main()
