"""Local English figures and complete answer browser; no remote assets."""
import json
from html import escape
from plot_matched_models import Canvas,OUT as FIGURES
from supra_quantization_study import OUT,ROOT,read,write

COLORS={'f16':'#65798b','row':'#2876a0','s32':'#168476','a64':'#7653a8','gptq':'#bd6725'}
LABELS={'f16':'F16 source / FP32','row':'Row INT4 (deployed)','s32':'Symmetric group32','a64':'Mixed affine group64','gptq':'GPTQ-inspired (selected)'}
MUTED='#586c7d'


def save(c,name,sources,notes):
    c.save(name,sources)
    path=FIGURES/(name+'-2026-10-29.json');meta=read(path);meta['notes']=notes;write(path,meta)


def results():
    names=['row','s32','a64','gptq'];v={n:read(OUT/('validation-'+n+'.json')) for n in names}
    q=read(OUT/'quality-summary.json');m=read(OUT/'manual-review.json')
    c=Canvas(1250,'Closer to the source. Worse on these answer questions.',
             'Supra2-100M | Author F16 weights | Full vocabulary | Context 256 | Offline host study, not a P4 trial')
    c.rect(48,135,735,470);c.rect(803,135,749,470)
    c.text(72,178,'Validation: full-distribution fidelity',27,weight='bold')
    c.text(72,211,'Mean KL(source || quantized), nats; lower is better',20,MUTED)
    c.text(827,178,'Validation: same most likely token',27,weight='bold')
    c.text(827,211,'201 teacher-forced positions; higher is better',20,MUTED)
    for i,n in enumerate(names):
        y=258+i*79;c.text(72,y,LABELS[n],21,COLORS[n],'bold')
        c.rect(72,y+14,550,22,'#e4ebf0',0);c.rect(72,y+14,550*v[n]['mean_kl_nats']/.4,22,COLORS[n],0)
        c.text(648,y+34,f"{v[n]['mean_kl_nats']:.3f}",24,COLORS[n],'bold')
        c.text(827,y,LABELS[n],21,COLORS[n],'bold')
        c.rect(827,y+14,550,22,'#e4ebf0',0);c.rect(827,y+14,550*v[n]['top1_agreement'],22,COLORS[n],0)
        c.text(1398,y+34,f"{100*v[n]['top1_agreement']:.1f}%",24,COLORS[n],'bold')
    reduction=100*(1-v['gptq']['mean_kl_nats']/v['row']['mean_kl_nats'])
    c.text(72,584,f'{reduction:.1f}% lower KL; selection was frozen before QA.',20,MUTED)
    c.text(827,584,'One fixed calibration: 749 tokens. No confidence intervals.',20,MUTED)
    c.rect(48,630,1504,385)
    c.text(72,675,'Confirmation: new factual questions',28,weight='bold')
    c.text(72,710,'Passes / 16, not general model accuracy. S32/A64 QA was deliberately not run after selection.',21,MUTED)
    for i,n in enumerate(['f16','row','gptq']):
        y=765+i*77;c.text(72,y,LABELS[n],23,COLORS[n],'bold')
        c.rect(400,y-18,620,20,'#e4ebf0',0);c.rect(400,y-18,620*q['counts'][n]['fact']/16,20,COLORS[n],0)
        c.text(1045,y,f"{q['counts'][n]['fact']}/16 frozen screen",22,COLORS[n],'bold')
        c.text(1330,y,f"{m['counts_of_16'][n]}/16 review",22,MUTED)
    c.text(72,975,'All three: 0/4 exact instructions. Review is post-hoc, unblinded and limited to the first relevant claim.',21,MUTED)
    c.rect(48,1040,1504,110,'#f4e0d4')
    c.text(72,1083,'QUALITY GATE FAILED — candidate not installed',29,'#903e25','bold')
    c.text(72,1123,'Both P4s retain firmware 0.6.1 and row-INT4. No new C kernel, device latency or on-device quality result.',22)
    c.text(48,1197,'Lexical screen misses negation and confuses the article “a” with the letter A; manual audit records these errors.',21,MUTED)
    sources=[OUT/('validation-'+n+'.json') for n in names]+[OUT/'quality-summary.json',OUT/'manual-review.json',ROOT/'tools/plot_supra_quantization.py']
    save(c,'supra-quantization-v2-results',sources,'Single deterministic offline study. KL averaged over 201 full-vocabulary positions. Answer counts are small, unblinded and capped at 24 tokens; no confidence intervals, significance or population accuracy claims. Review is post-hoc. No new device execution.')


def setup():
    c=Canvas(1160,'Quantization V2: selection and confirmation stay separate',
             'Frozen English inputs | Existing local weights only | No training, downloads, new dependencies or device writes')
    c.rect(48,140,1504,105);c.text(72,182,'Pinned Supra2-100M author F16 GGUF → independent NumPy / FP32 source oracle',28,weight='bold')
    c.text(72,221,'100.68M parameters · tied embedding/output · Qwen3 · full 32,768-token vocabulary · context 256',22,MUTED)
    for x,title,line1,line2,color in [
        (48,'CALIBRATION','16 documents · 749 tokens','Source activations; no QA',COLORS['s32']),
        (558,'VALIDATION','4 disjoint texts · 201 positions','Full-vocabulary KL / top-1',COLORS['a64']),
        (1068,'CONFIRMATION','16 facts + 4 exact replies','Only after winner is frozen',COLORS['gptq'])]:
        c.arrow(x+240,245,x+240,290,color);c.rect(x,290,484,160)
        c.text(x+22,332,title,24,color,'bold');c.text(x+22,378,line1,22);c.text(x+22,418,line2,21,MUTED)
    c.rect(48,490,994,192);c.text(72,532,'Three fixed 4-bit candidates',27,weight='bold')
    c.text(72,574,'S32: symmetric group32 / F16 scales on every matrix',23,COLORS['s32'])
    c.text(72,613,'A64: tied table S32 + transformer affine group64 / F16 scales / u8 zeros',22,COLORS['a64'])
    c.text(72,652,'GPTQ-inspired: A64 grids + source-activation error compensation',23,COLORS['gptq'])
    c.arrow(290,450,290,490,COLORS['s32']);c.arrow(800,450,800,490,COLORS['a64'])
    c.rect(1068,490,484,192);c.text(1090,532,'Compare F16, row, winner',25,weight='bold')
    c.text(1090,577,'24-token greedy cap; 72 outputs',22);c.text(1090,617,'4 old regressions labelled apart',22)
    c.text(1090,655,'No candidate reselection on QA',21,MUTED)
    c.arrow(1310,450,1310,490,COLORS['gptq'])
    c.rect(48,730,1504,150,'#f4e0d4');c.text(72,774,'Frozen rule: >=10% lower KL + bounded top-1 loss → select → fact screen must not decline',26,weight='bold')
    c.text(72,820,'GPTQ wins validation but scores 4/16 versus row 9/16; admission fails.',25,'#903e25','bold')
    c.text(72,857,'No post-hoc testing of A64/S32 answers to find a more favorable winner.',21,MUTED)
    c.arrow(548,682,548,730,COLORS['a64']);c.arrow(1310,682,1310,730,COLORS['gptq'])
    c.rect(48,930,1504,130);c.text(72,974,'Existing two-P4 deployment remains unchanged',28,weight='bold')
    c.text(72,1013,'Coordinator layers 0–3 ↔ LAN ↔ worker layers 4–11 · firmware 0.6.1 · row-INT4 · status reads only',22)
    c.text(48,1110,'Evidence boundary: host fidelity and answer confirmation completed; grouped C format, P4 allocation and timing not attempted.',21,MUTED)
    save(c,'supra-quantization-v2-protocol',[OUT/'protocol.json',OUT/'selection.json',OUT/'quality-summary.json',ROOT/'tools/plot_supra_quantization.py'],
         'Actual frozen study flow and failed admission gate. Existing P4 layout shown as unchanged context, not as a new hardware trial. The three data uses are separate; no pretraining holdout claim.')


def answers():
    p=read(OUT/'protocol.json');a={n:{r['id']:r for r in read(OUT/('answers-'+n+'.json'))} for n in ['f16','row','gptq']}
    notes={x['id']:x['note'] for key in ['notes','other_cases'] for x in read(OUT/'manual-review.json')[key]}
    html=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
        '<title>Supra quantization V2 — all answers</title><style>body{font:17px/1.55 system-ui,sans-serif;color:#193347;background:#eff4f8;max-width:1500px;margin:35px auto;padding:0 20px}h1{line-height:1.2}article{background:white;border-radius:12px;padding:20px;margin:22px 0}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:22px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.5 ui-monospace,monospace}.note{border-left:4px solid #bd6725;padding:8px 15px;background:#fff2e8}.meta{font-size:14px;color:#586c7d}h3{font-size:18px}summary{cursor:pointer}@media(max-width:900px){.grid{grid-template-columns:1fr}}</style>',
        '<h1>Closer logits do not guarantee better answers.</h1><p>Supra2-100M · author F16 source / FP32 compute · row-INT4 baseline · validation-selected GPTQ-inspired INT4. Greedy generation, full vocabulary, context 256, cap 24 output tokens, native author ChatML, no implicit BOS.</p>',
        '<p class="note"><strong>Quality gate failed. No installation.</strong> Frozen factual screen: F16 4/16, row 9/16, selected 4/16; exact instructions 0/4 each. Post-hoc first-claim review: 5/16, 9/16, 4/16. A correct first claim can be followed by a false statement. Small, unblinded exploratory sample; screen defects are retained and explained. No global quality ranking.</p>',
        '<p>All 72 continuations are below. Known regressions N2/N4/N6/N7 are separate from the 20 new questions. S32 and A64 answers were not generated after selecting the winner.</p>']
    for case in p['quality']+p['known_regressions']:
        label=case.get('user',case['prompt']);html.append('<article><h2>'+escape(case['id']+' · '+case['category'])+'</h2><p>'+escape(label)+'</p><div class="grid">')
        for n in a:
            r=a[n][case['id']];score='not scored (known regression)' if r['screen_pass'] is None else ('screen pass' if r['screen_pass'] else 'screen fail')
            html.append('<section><h3>'+escape(LABELS[n])+'</h3><pre>'+escape(r['text'])+'</pre><p class="meta">'+escape(f"{len(r['tokens'])} output tokens; EOS={r['eos']}; {score}")+'</p><details><summary>Output token IDs</summary><pre>'+escape(json.dumps(r['tokens']))+'</pre></details></section>')
        html.append('</div><p class="note">Review: '+escape(notes[case['id']])+'</p><details><summary>Exact prompt and frozen rule</summary><pre>'+escape(case['prompt'])+'\n'+escape(json.dumps(case.get('rule'),ensure_ascii=True))+'</pre></details></article>')
    html.append('</html>');(OUT/'comparison.html').write_bytes(('\n'.join(html)+'\n').encode('utf-8'))


if __name__=='__main__':results();setup();answers()
