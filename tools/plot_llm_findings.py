"""Local, data-backed SVG/PNG findings diagram; no network or device access."""
import hashlib
import json
import pathlib
import subprocess
from html import escape

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/figures'
BLUE='#287bb6';ORANGE='#bc651b';INK='#182e40';MUTED='#526779'


def main():
    source={
        'sft_quality':'data/quality-v1-2026-10-29/summary.json',
        'sft_export':'data/textmodel-sft-2026-10-29/export.json',
        'tinytalk_review':'data/tinytalk2-host-2026-10-29/manual-review.json',
        'tinytalk_export':'data/gptneo-p4-2026-10-29/export.json',
        'tinytalk_cluster':'data/gptneo-p4-2026-10-29/completed-study/summary.json',
        'memory_failure':'data/gptneo-p4-2026-10-29/failed-allocation-measured.json',
    }
    data={k:json.loads((ROOT/p).read_text(encoding='utf-8')) for k,p in source.items()}
    sft=data['sft_quality']['sft'];notes=data['tinytalk_review']['notes'];cluster=data['tinytalk_cluster']
    a=[len(sft['questions_first_answer_correct']),len(sft['questions_fully_fulfilled']),len(sft['instructions_fulfilled'])]
    b=[sum(notes[q]['first_fact_correct'] for q in ['Q1','Q2','Q3']),
       sum(notes[q]['requested_format_fulfilled'] for q in ['Q1','Q2','Q3']),
       sum(notes[q]['requested_format_fulfilled'] for q in ['I1','I2','I3'])]
    assert a==[0,0,0] and b==[2,1,0]
    sizes=[data['sft_export']['bytes']/1e6,data['tinytalk_export']['bytes']/1e6]
    assert sizes==[15.836365,21.380448]
    local=cluster['local_pair_median_ms']/1000;pair=cluster['cluster_pair_median_ms']/1000
    factor=cluster['paired_throughput_factor_median']
    s=['<svg xmlns="http://www.w3.org/2000/svg" width="1520" height="1400" viewBox="0 0 1520 1400" role="img" aria-labelledby="title desc">',
       '<title id="title">TinyStories/SFT und TinyTalk-2: Erkenntnisse unserer P4-Versuche</title>',
       '<desc id="desc">Gemeinsame Fragen: Fakten 0 von 3 gegen 2 von 3, Frage mit Format 0 gegen 1, Anweisungen beide 0. Dateigrößen 15,84 gegen 21,38 MB. TinyTalk-Cluster: 10,73 gegen 5,61 Sekunden, 1,92-facher Durchsatz. Kleine explorative Stichproben mit verschiedenen Promptvorlagen.</desc>',
       '<style>text{font-family:"Segoe UI",Arial,sans-serif;fill:#182e40} .small{fill:#526779} .axis{stroke:#dbe3e9;stroke-width:1} </style>',
       '<rect width="1520" height="1400" fill="#f1f5f8"/>']
    def text(x,y,value,size=22,color=INK,weight='normal',anchor='start'):
        s.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" style="fill:{color}">{escape(value)}</text>')
    def rect(x,y,w,h,fill,r=0,opacity=1):s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" opacity="{opacity}"/>')
    def line(x1,y1,x2,y2,dash=False):s.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="axis"'+(' stroke-dasharray="6 5"' if dash else '')+'/>')
    def dot(x,y,color):s.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>')
    def number(value,digits=2):return f'{value:.{digits}f}'.replace('.',',')
    text(48,65,'Zwei kleine Sprachmodelle. Was haben wir gelernt?',40,weight='bold')
    text(48,105,'ESP32-P4 · eigene Messungen und Textprüfungen · Stand 29.10.2026',23,MUTED)
    dot(56,153,BLUE);text(72,160,'TinyStories / SFT',24,weight='bold')
    text(298,160,'Llama · englische Geschichten',21,MUTED)
    dot(814,153,ORANGE);text(830,160,'TinyTalk-2',24,weight='bold')
    text(1002,160,'GPT-Neo · kurze englische Dialoge',21,MUTED)
    for x,y in [(44,200),(776,200),(44,728),(776,728)]:rect(x,y,700,500 if y==200 else 476,'#ffffff',18)

    text(72,243,'Gemeinsame Aufgaben',28,weight='bold')
    text(72,274,'3 gleiche Fragen + 3 gleiche Anweisungen',21,MUTED)
    dot(80,306,BLUE);text(94,313,'SFT',18)
    dot(170,306,ORANGE);text(184,313,'TinyTalk-2',18)
    left=340;width=310
    for tick in range(4):
        x=left+width*tick/3;line(x,335,x,632);text(x,655,str(tick),18,MUTED,anchor='middle')
    labels=[['Faktisch richtige','Antwort'],['Frage UND Format','vollständig erfüllt'],['Anweisung','vollständig erfüllt']]
    for i,(av,bv) in enumerate(zip(a,b)):
        y=365+i*103
        text(72,y,labels[i][0],22);text(72,y+27,labels[i][1],22)
        for value,color,dy in [(av,BLUE,-16),(bv,ORANGE,16)]:
            by=y+dy;w=width*value/3
            if value:rect(left,by-10,w,18,color,3)
            else:dot(left,by-1,color)
            text(left+w+12,by+6,f'{value}/3',22,weight='bold')
    text(72,680,'Explorativ · kleine Stichprobe · andere Promptvorlagen',18,MUTED)

    text(804,243,'Platzbedarf pro Board',28,weight='bold')
    text(804,274,'INT8-Datei mit Tokenizer · Flashlimit: 24 MiB',21,MUTED)
    start=804;span=600;limit=24*1024*1024/1e6
    for y,name,value,color in [(333,'TinyStories / SFT',sizes[0],BLUE),(433,'TinyTalk-2',sizes[1],ORANGE)]:
        text(start,y,name,24,weight='bold');text(1410,y,number(value)+' MB',28,weight='bold',anchor='end')
        rect(start,y+19,span*value/limit,32,color,4)
    line(start+span,310,start+span,504,True)
    for tick in [0,10,20,limit]:
        x=start+span*tick/limit
        text(x,529,(number(tick) if tick==limit else str(tick))+(' MB' if tick==limit else ''),18,MUTED,anchor='end' if tick==limit else 'middle')
    text(804,576,'Vollständiges Modell auf jedem Board.',21)
    text(804,615,'PSRAM-Engpass: 20,45-MB-Block &lt; 21,38 MB'.replace('&lt;','<'),21)
    text(804,644,'Neustart vor dem Laden löst diesen Engpass.',21)
    text(804,680,'Mehr Knoten bündeln bisher keinen Modellspeicher.',18,MUTED)

    text(72,771,'Was die Modelle können',28,weight='bold')
    dot(80,817,BLUE);text(96,826,'TinyStories / SFT',25,weight='bold')
    text(72,865,'Schwerpunkt: englische Geschichten.',22)
    text(72,895,'Passendes Ende bei 2 von 4 Geschichten;',22)
    text(72,925,'die Themen wurden nur teilweise erfüllt.',22)
    dot(80,976,ORANGE);text(96,985,'TinyTalk-2',25,weight='bold')
    text(72,1024,'Kurze Dialoge und einfache Fragen.',22)
    text(72,1054,'Kontextname im Einzeltest korrekt erinnert.',22)
    text(72,1084,'INT8-Fehler: „Ein Fahrrad hat vier Räder.“',22)
    text(72,1150,'Geschichtenaufgaben waren unterschiedlich.',19,MUTED)
    text(72,1178,'Daraus folgt kein fairer Geschichten-Sieger.',19,MUTED)

    text(804,771,'Clusterwirkung: TinyTalk-2',28,weight='bold')
    text(804,802,'Zwei unabhängige Anfragen · gleiche Tokens / EOS',20,MUTED)
    for y,label,value,opacity in [(849,'Master allein',local,.42),(942,'Beide Boards',pair,1)]:
        text(804,y,label,24,weight='bold');text(1410,y,number(value)+' s',28,weight='bold',anchor='end')
        rect(804,y+16,600*value/12,30,ORANGE,4,opacity)
    for tick in [0,4,8,12]:text(804+600*tick/12,1014,str(tick)+(' s' if tick==12 else ''),18,MUTED,anchor='end' if tick==12 else 'middle')
    text(804,1069,number(factor)+'× Durchsatz',36,weight='bold')
    text(804,1102,'4 gepaarte Blöcke · 16 Aufträge',21,MUTED)
    text(804,1150,'Kein Geschwindigkeitsvergleich mit SFT:',19,MUTED)
    text(804,1178,'Dessen Zeitversuch hatte andere Prompts.',19,MUTED)

    text(48,1256,'Gemeinsame Erkenntnis',27,weight='bold')
    text(48,1296,'Parallelität erhöht den Durchsatz. Mehr Modellbytes garantieren keine besseren Antworten.',24)
    text(48,1331,'Kein Nachweis für einen verlässlichen allgemeinen oder deutschen Assistenten.',23,MUTED)
    text(48,1375,'Daten: Textqualität V1 · TinyTalk-Hostprüfung · GPT-Neo-P4-Studie. SFT = 0rn0/llama2-15m-tinystories-sft.',16,MUTED)
    s.append('</svg>');OUT.mkdir(parents=True,exist_ok=True)
    stem=OUT/'llm-erkenntnisse-2026-10-29';stem.with_suffix('.svg').write_text('\n'.join(s)+'\n',encoding='utf-8')
    metadata={'comparison':['TinyStories/SFT','TinyTalk-2 row INT8'],'common_tasks':{'SFT':a,'TinyTalk-2':b},
              'artifact_MB':sizes,'tinytalk_master_pair_seconds':local,'tinytalk_cluster_pair_seconds':pair,
              'paired_throughput_factor':factor,'limitations':['Small exploratory unblinded review; different prompt wrappers','No matched SFT timing baseline in this comparison','Story tasks differ'],
              'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in source.values()}}
    stem.with_suffix('.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    runtime=pathlib.Path('[USER_HOME]/.cache/codex-runtimes/codex-primary-runtime/dependencies/node')
    code='const sharp=require('+json.dumps(str(runtime/'node_modules/sharp'))+');sharp(process.argv[1]).png().toFile(process.argv[2]).catch(e=>{console.error(e);process.exit(1)})'
    subprocess.run([str(runtime/'bin/node.exe'),'-e',code,str(stem.with_suffix('.svg')),str(stem.with_suffix('.png'))],check=True)
    print(json.dumps({'figure':str(stem.with_suffix('.png')),'quality_counts':[a,b],'speedup':factor}))


if __name__=='__main__':main()
