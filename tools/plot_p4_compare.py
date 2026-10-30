"""English standalone matched-P4 figures; existing offline renderer only."""
import json
import pathlib
import subprocess
from plot_matched_models import Canvas, INK, MUTED
from p4_compare_results import ROOT,DATA,read,write,sha

COLORS={'tinybrainbot':'#178476','supra':'#7953a6'}
NAMES={'tinybrainbot':'TinyBrainBot','supra':'Supra2-100M'}


def save(c,label,names):
    stem=ROOT/'docs/figures'/(label+'-2026-10-30')
    stem.with_suffix('.svg').write_text('\n'.join(c.s+['</svg>'])+'\n',encoding='utf-8')
    runtime=pathlib.Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
    code='const sharp=require('+json.dumps(str(runtime/'node_modules/sharp'))+');sharp(process.argv[1]).png().toFile(process.argv[2]).catch(e=>{console.error(e);process.exit(1)})'
    subprocess.run([str(runtime/'bin/node.exe'),'-e',code,str(stem.with_suffix('.svg')),str(stem.with_suffix('.png'))],check=True,capture_output=True)
    sources=[DATA/n for n in names]+[ROOT/'tools/plot_p4_compare.py',ROOT/'tools/p4_compare_results.py']
    write(stem.with_suffix('.json'),{'date':'2026-10-30','title':label,'width':1600,'height':c.height,
        'source_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in sources},
        'notes':'Real two-P4 records, same firmware/kernel/quantization. Same unblinded author, small fixed quality sample. Timing n=3 paired blocks; observed ranges, no confidence interval, energy or general ranking claim. Different model vocabularies/content retained.'})
    print('FIGURE',stem.name)


def comparison():
    s=read(DATA/'summary.json');q=s['counts'];runs=read(DATA/'timing-runs.json')
    c=Canvas(1370,'TinyBrainBot and Supra2: the same two P4s',
             'Firmware 0.7.0 | row INT4 | context 256 | 4+8 layers | tile4 / both CPU cores per board | 30 October 2026')
    c.rect(48,135,735,365);c.text(72,178,'Six new factual questions',28,weight='bold')
    c.text(72,214,'First responsive answer / confirmed clean visible response',20,MUTED)
    for i,m in enumerate(['tinybrainbot','supra']):
        y=260+i*98;r=q[m]['facts']
        c.text(72,y,NAMES[m],23,COLORS[m],'bold')
        c.rect(72,y+15,540,15,'#e3ebef',5);c.rect(72,y+15,540*r['first_correct']/6,15,'#adc6d0',5)
        c.rect(72,y+37,540,15,'#e3ebef',5);c.rect(72,y+37,540*r['confirmed_clean']/6,15,COLORS[m],5)
        c.text(636,y+34,f"{r['first_correct']}/6 first",22)
        c.text(636,y+61,f"{r['confirmed_clean']}/6 clean",22,COLORS[m],'bold')
    c.text(72,472,'A correct first sentence can be followed by a false claim.',21,MUTED)
    c.rect(803,135,749,365);c.text(827,178,'Keep the other criteria separate',28,weight='bold')
    c.text(1174,221,'Tiny',21,COLORS['tinybrainbot'],'bold');c.text(1375,221,'Supra',21,COLORS['supra'],'bold')
    for y,label,key,field in [(268,'Exact requested text','exact','correct'),(312,'Given facts: first answer','grounded','first_correct'),
                              (356,'Given facts: clean answer','grounded','confirmed_clean'),(400,'Full requested story topic','story','topic'),(444,'Visible story resolution','story','resolution')]:
        c.text(827,y,label,22)
        for m,x in [('tinybrainbot',1192),('supra',1405)]:c.text(x,y,f"{q[m][key][field]}/{q[m][key]['n']}",24,COLORS[m],'bold','middle')
    c.text(827,478,'Supra context: one additional cleanliness judgment uncertain.',19,MUTED)
    c.rect(48,525,1504,160,'#dce9f2')
    c.text(72,568,'New facts: first-answer counts may tie while response defects differ.',27,weight='bold')
    c.text(72,609,'Tiny: frozen water = pond/lake; ears = sight; one blank answer. Supra: Paris plus a false largest-city claim.',22,MUTED)
    c.text(72,650,'Context G01 is a generous Tiny pass without explicit red; strict colour scoring reduces its grounded total by one.',21,MUTED)
    c.text(48,738,'Shared-prefix speed: equal input lengths and 16 capped output tokens',29,weight='bold')
    maximum=max(r['done']['elapsed_ms']/1000 for r in runs)*1.18
    for j,case in enumerate(['B1','B2']):
        x=48+j*772;t=s['timing'][case]
        c.rect(x,765,732,355)
        c.text(x+22,806,case+' · '+('Once upon a time' if case=='B1' else 'One day, a little girl'),24,weight='bold')
        tokens=[t['models'][m]['prompt_tokens'] for m in ['tinybrainbot','supra']]
        c.text(x+22,840,f'Input tokens: {tokens[0]} / {tokens[1]} | three paired blocks',20,MUTED)
        x0=x+170;width=402
        for i,m in enumerate(['tinybrainbot','supra']):
            y=887+i*79;row=sorted([r for r in runs if r['case']==case and r['model']==m],key=lambda r:r['done']['elapsed_ms'])[1]['done']
            sec=row['elapsed_ms']/1000;first=row['ttft_ms']/1000
            c.text(x+22,y+20,NAMES[m],21,COLORS[m],'bold')
            c.rect(x0,y,sec/maximum*width,27,COLORS[m],4)
            c.rect(x0,y,first/maximum*width,27,'#b7cbd4',4)
            lo,hi=t['models'][m]['total_range_seconds'];c.line(x0+lo/maximum*width,y+13,x0+hi/maximum*width,y+13,INK,3)
            c.text(x+706,y+21,f'{sec:.3f} s',22,anchor='end')
        ratio=t['supra_over_tiny_total_median']
        c.text(x+22,1064,'Paired latency ratio Supra/Tiny: '+(f'{ratio:.3f}' if ratio is not None else 'not admitted'),22,weight='bold')
        c.text(x+22,1101,'Pale: first decision. Colour: remaining interval + close.',19,MUTED)
    c.text(48,1168,'Same prompt bytes, same token counts; different token IDs and generated words. This compares deployed systems.',23,weight='bold')
    c.text(48,1211,'Three observed repeats per prefix/model; min-max whiskers are not confidence intervals. No thermal or energy data.',22,MUTED)
    c.text(48,1254,'Quality-case durations include different EOS lengths: do not reinterpret their totals as equal-work speedups.',22,MUTED)
    c.text(48,1303,'Small fixed set, same unblinded author. No general model ranking. All complete responses and notes are retained.',22,MUTED)
    c.text(48,1348,'No material contradiction is a separate story criterion; an off-topic setting can pass it without fulfilling the task.',20,MUTED)
    save(c,'matched-p4-comparison',['protocol.json','summary.json','manual-review.json','timing-runs.json'])


def setup():
    p=read(DATA/'protocol.json');c=Canvas(1110,'One physical pair. Two models, loaded in turn.',
        'Preregistered protocol 3bf7eb1 | Complete native reference checks for every actual stream | No new firmware build')
    c.rect(48,140,1504,128)
    c.text(800,185,'Same local LAN client → coordinator → worker → coordinator',29,weight='bold',anchor='middle')
    c.text(800,231,'One sharded inference lane; both boards are needed for every request.',24,MUTED,anchor='middle')
    for x,title,lines in [(48,'P4 coordinator',['Embedding / tokenizer / output head','Layers 0-3 + own FP32 KV','32 MiB PSRAM + 32 MiB flash']),
                          (848,'P4 worker',['Layers 4-11 + own FP32 KV','No full embedding table or tokenizer','32 MiB PSRAM + 32 MiB flash'])]:
        c.rect(x,310,704,220);c.text(x+26,357,title,28,weight='bold')
        for i,line in enumerate(lines):c.text(x+26,402+i*45,line,23,MUTED)
    c.arrow(752,392,848,392);c.arrow(848,458,752,458,'#178476')
    c.text(800,370,'LAN',20,anchor='middle')
    c.text(48,581,'Timing order across paired blocks: A→B | B→A | A→B',29,weight='bold')
    for i,(title,lines) in enumerate([
        ('Phase1 · A Tiny',['12 quality cases + warmup','Timing block1']),
        ('Phase2 · B Supra',['12 quality cases + warmup','Timing blocks1 and2']),
        ('Phase3 · A Tiny',['Warmup','Timing blocks2 and3']),
        ('Phase4 · B Supra',['Warmup','Timing block3'])]):
        x=48+i*380;c.rect(x,610,364,155);c.text(x+18,648,title,23,weight='bold')
        for j,line in enumerate(lines):c.text(x+18,692+j*38,line,20,MUTED)
    c.rect(48,800,1504,130,'#dce9f2')
    c.text(72,844,'Restore A TinyBrainBot → four-token control → both ready / queue empty',28,weight='bold')
    c.text(72,888,'41 actual generations: 24 quality + 12 timing + 4 warmups + 1 restoration control. All raw streams kept.',23,MUTED)
    c.text(48,981,'Quality: same user tasks with native author wrappers. Speed: identical raw prefixes, four/six input tokens in both.',22,weight='bold')
    c.text(48,1024,'USB-C supplies each board; Ethernet without PoE. No inter-board USB, SD use, partition or clock change.',22,MUTED)
    c.text(48,1067,'Configured CPU 360 MHz / PSRAM 200 MHz from the retained build, not externally measured. No energy/thermal inference.',21,MUTED)
    save(c,'matched-p4-setup',['protocol.json','final.json','host-receipt.json'])


if __name__=='__main__':comparison();setup()
