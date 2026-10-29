"""Standalone scientific SVG/PNG figures from local JSON; no online resources."""
import json
import pathlib
import shutil
import subprocess
from html import escape
from matched_models import ROOT, DATA, MODELS, sha, write

OUT = ROOT / 'docs/figures'
INK = '#193347'
MUTED = '#586c7d'
COLORS = {'sft': '#3378ad', 'story8': '#7653a8', 'talk1': '#168476', 'talk2': '#c06a27'}
LABELS = {'sft': 'TinyStories-15M SFT', 'story8': 'TinyStories-Instruct-8M', 'talk1': 'TinyTalk 1', 'talk2': 'TinyTalk-2'}


class Canvas:
    def __init__(self, height, title, subtitle):
        self.height = height
        self.s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="{height}" viewBox="0 0 1600 {height}" role="img">',
                  '<title>' + escape(title) + '</title>',
                  '<style>text{font-family:"Segoe UI",Arial,sans-serif}line{stroke:#d8e2e9;stroke-width:2}</style>']
        self.rect(0, 0, 1600, height, '#eff4f8')
        self.text(48, 62, title, 36, weight='bold')
        self.text(48, 101, subtitle, 21, MUTED)

    def text(self, x, y, text, size=23, color=INK, weight='normal', anchor='start'):
        self.s.append(f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{escape(str(text))}</text>')

    def rect(self, x, y, w, h, fill='white', radius=14):
        self.s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}"/>')

    def line(self, x, y, x2, y2, color='#d8e2e9', width=2):
        self.s.append(f'<path d="M{x} {y} L{x2} {y2}" stroke="{color}" stroke-width="{width}" fill="none"/>')

    def arrow(self, x, y, x2, y2, color='#3378ad'):
        self.line(x, y, x2, y2, color, 4)
        if x == x2:
            step = 1 if y2 > y else -1
            self.s.append(f'<path d="M{x2-8} {y2-13*step} L{x2} {y2} L{x2+8} {y2-13*step}" stroke="{color}" stroke-width="4" fill="none"/>')
        else:
            step = 1 if x2 > x else -1
            self.s.append(f'<path d="M{x2-13*step} {y2-8} L{x2} {y2} L{x2-13*step} {y2+8}" stroke="{color}" stroke-width="4" fill="none"/>')

    def save(self, label, sources):
        OUT.mkdir(exist_ok=True)
        stem = OUT / (label + '-2026-10-29')
        stem.with_suffix('.svg').write_text('\n'.join(self.s + ['</svg>']) + '\n', encoding='utf-8')
        runtime = pathlib.Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
        node = str(runtime / 'bin/node.exe') if (runtime / 'bin/node.exe').exists() else shutil.which('node')
        sharp = str(runtime / 'node_modules/sharp') if (runtime / 'node_modules/sharp').exists() else 'sharp'
        code = 'const sharp=require(' + json.dumps(sharp) + ');sharp(process.argv[1]).png().toFile(process.argv[2]).catch(e=>{console.error(e);process.exit(1)})'
        subprocess.run([node, '-e', code, str(stem.with_suffix('.svg')), str(stem.with_suffix('.png'))], check=True, capture_output=True)
        write(stem.with_suffix('.json'), {'title': label, 'date': '2026-10-29', 'width': 1600, 'height': self.height,
            'source_sha256': {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p) for p in sources},
            'notes': 'Static, English, local figure. No online resources. Descriptive medians/ranges and manual review, not confidence intervals or independent quality ratings.'})
        print('FIGURE', stem.name)


def quality():
    q = json.loads((DATA / 'quality-summary.json').read_text())['counts']
    exports = json.loads((DATA / 'exports.json').read_text())
    c = Canvas(1250, 'Same tasks. Four small English models.', '29 October 2026 | Identical prompt bytes, greedy row-INT8, context 256 | Exploratory manual review')
    for i, key in enumerate(MODELS):
        x = 48 + i * 380
        c.rect(x, 130, 364, 100)
        c.text(x + 16, 164, LABELS[key], 22, COLORS[key], 'bold')
        count = exports[key].get('actual_parameters')
        c.text(x + 16, 200, f'{count/1e6:.2f}M actual parameters' if count else 'Llama architecture; story SFT', 20, MUTED)
    c.rect(48, 250, 735, 430)
    c.text(72, 291, 'Elementary factual answers', 27, weight='bold')
    c.text(72, 323, 'Correct first substantive answer / six questions', 20, MUTED)
    for i, key in enumerate(MODELS):
        y = 364 + i * 72
        c.text(72, y, LABELS[key], 20, COLORS[key], 'bold')
        c.rect(72, y + 12, 560, 18, '#e4ebf0', 7)
        value = q[key]['first_fact_correct_of_6']
        if value:
            c.rect(72, y + 12, 560 * value / 6, 18, COLORS[key], 7)
        c.text(658, y + 30, f'{value}/6', 25, COLORS[key], 'bold')
    c.text(72, 654, 'TinyTalk-2 still claims that a bicycle has four wheels.', 19, MUTED)
    c.rect(803, 250, 749, 430)
    c.text(827, 291, 'Storage on every board', 27, weight='bold')
    c.text(827, 323, 'Packed artifact with full tokenizer | decimal MB', 20, MUTED)
    for i, key in enumerate(MODELS):
        y = 364 + i * 72
        size = exports[key]['artifact_bytes'] / 1e6
        c.text(827, y, LABELS[key], 20, COLORS[key], 'bold')
        c.rect(827, y + 12, 560, 18, '#e4ebf0', 7)
        c.rect(827, y + 12, 560 * size / (24 * 1024**2 / 1e6), 18, COLORS[key], 7)
        c.text(1404, y + 30, f'{size:.2f}', 24, COLORS[key], 'bold')
    c.text(827, 654, '24 MiB partition = 25.17 MB. No pooled model memory.', 19, MUTED)
    c.rect(48, 700, 1504, 370)
    c.text(72, 742, 'Stories and instructions: inspect separate criteria', 28, weight='bold')
    headers = [('Model', 72), ('Full story topic', 580), ('No material contradiction', 815), ('Visible resolution', 1110), ('Instructions', 1355)]
    for text, x in headers:
        c.text(x, 787, text, 18, MUTED, 'bold')
    for i, key in enumerate(MODELS):
        y = 830 + 48 * i
        c.text(72, y, LABELS[key], 22, COLORS[key], 'bold')
        for x, name, total in [(625, 'story_full_topic_of_4', 4), (925, 'story_no_material_contradiction_of_4', 4),
                               (1175, 'story_visible_resolution_of_4', 4), (1410, 'instructions_of_3', 3)]:
            c.text(x, y, f'{q[key][name]}/{total}', 24, COLORS[key], 'bold', 'middle')
    c.text(72, 1025, 'Four story prefixes; three instructions. TinyTalk 1 gets a generous literal pass for the rain question; sentence status is debatable.', 18, MUTED)
    c.text(72, 1051, 'Visible resolution and EOS are different. A capped story can have a resolution. See full texts and scoring notes.', 18, MUTED)
    c.rect(48, 1092, 1504, 104, '#dce9f2')
    c.text(72, 1131, 'Training objective matters. Extra model bytes do not ensure reliable instructions.', 27, weight='bold')
    c.text(72, 1168, 'TinyTalk 1 vs 2 also changes size and training data; these results do not isolate either cause.', 22, MUTED)
    c.text(48, 1230, 'One deterministic output per model/task; same unblinded reviewer; possible training overlap. No general or German assistant qualification.', 18, MUTED)
    c.save('matched-model-quality', [DATA / n for n in ['quality-summary.json', 'manual-review.json', 'exports.json', 'protocol.json']])


def performance():
    path = DATA / 'hardware/summary.json'
    if not path.exists():
        return
    summary = json.loads(path.read_text())
    batches = json.loads((DATA / 'hardware/batches.json').read_text())
    direct = json.loads((DATA / 'hardware/direct.json').read_text())
    final = json.loads((DATA / 'hardware/final-state.json').read_text())
    assert len(direct) == 64 and len(batches) == 32 and final['study_completed']
    c = Canvas(1160, 'One P4 or two: matched workload, measured throughput', 'Firmware 0.5.5 | tile4 on both CPU cores | Four paired AB/BA blocks per model | Same two story prefixes')
    c.rect(48, 130, 1504, 570)
    c.text(72, 172, 'Full two-request package time', 29, weight='bold')
    c.text(72, 206, 'Median with observed min-max whiskers; queue, prompt processing and transport included', 21, MUTED)
    largest = max(r['elapsed_ms'] / 1000 for r in batches)
    maximum = max(5, int(largest / 5 + 1) * 5)
    x0, width = 470, 815
    for tick in range(0, maximum + 1, 5):
        x = x0 + tick / maximum * width
        c.line(x, 233, x, 624)
        c.text(x, 656, tick, 19, MUTED, anchor='middle')
    c.text(x0 + width, 685, 'seconds (lower is faster)', 19, MUTED, anchor='end')
    for i, key in enumerate(MODELS):
        y = 264 + i * 94
        s = summary[key]
        c.text(72, y + 8, LABELS[key], 22, COLORS[key], 'bold')
        c.text(72, y + 39, f'{s["paired_throughput_factor_median"]:.2f}x paired throughput', 19, MUTED)
        for j, mode in enumerate(['local', 'cluster']):
            yy = y - 13 + j * 34
            values = [r['elapsed_ms'] / 1000 for r in batches if r['model'] == key and r['mode'] == mode]
            value = s['local_package_median_ms' if mode == 'local' else 'cluster_package_median_ms'] / 1000
            c.rect(x0, yy, value / maximum * width, 23, '#b9c8d4' if mode == 'local' else COLORS[key], 4)
            lo, hi = min(values) / maximum * width + x0, max(values) / maximum * width + x0
            c.line(lo, yy + 11, hi, yy + 11, INK)
            c.line(lo, yy + 5, lo, yy + 17, INK)
            c.line(hi, yy + 5, hi, yy + 17, INK)
            c.text(1320, yy + 20, f'{value:.2f} s ' + ('one P4' if mode == 'local' else 'two P4s'), 21, MUTED if mode == 'local' else COLORS[key])
    c.rect(48, 720, 1504, 285)
    c.text(72, 761, 'Two-board output rate on this workload', 28, weight='bold')
    for i, key in enumerate(MODELS):
        x = 72 + i * 370
        s = summary[key]
        c.text(x, 804, LABELS[key], 21, COLORS[key], 'bold')
        c.text(x, 850, f'{s["cluster_tokens_per_s_median"]:.2f} tokens/s', 32, COLORS[key], 'bold')
        c.text(x, 889, f'{s["cluster_characters_per_s_median"]:.2f} characters/s', 27, weight='bold')
        c.text(x, 929, f'{s["actual_output_tokens_per_package"]} tokens per package', 19, MUTED)
        c.text(x, 959, f'{s["actual_unicode_characters_per_package"]} Unicode characters', 19, MUTED)
    c.text(48, 1045, 'Matched input text is not equal computational work: tokenizers, prompt lengths and generated contents differ.', 21, MUTED)
    c.text(48, 1080, 'Characters/s reduces tokenizer-unit bias, but is not a quality-adjusted speed score. Repeats measure this fixed workload.', 20, MUTED)
    c.text(48, 1123, '64 direct quality cases + 64 dispatched timing jobs; all model-specific token/text/EOS references match. No third-node or energy claim.', 19, MUTED)
    c.save('matched-model-performance', [path, DATA / 'hardware/batches.json', DATA / 'hardware/final-state.json', DATA / 'protocol.json'])


def topology():
    c = Canvas(1110, 'Experimental setup: two P4 nodes, independent requests', 'Actual software/data paths for this study | Model weights are replicated on both boards | No cloud inference')
    c.rect(48, 135, 435, 385)
    c.text(72, 178, 'Local computer', 30, weight='bold')
    for i, t in enumerate(['Pinned data-only model assets', 'C runtime + NumPy numerical checks', 'Frozen prompts and greedy references', 'LAN client: submit and record only', 'Full outputs, profiles and figures']):
        c.text(72, 228 + 51 * i, t, 21, MUTED)
    c.text(72, 495, 'The PC does not select the worker.', 20, INK, 'bold')
    c.arrow(500, 306, 676, 306)
    c.text(511, 276, 'HTTP :8081', 21, MUTED)
    c.text(511, 346, 'two jobs', 21, MUTED)
    c.rect(695, 135, 850, 385)
    c.text(720, 178, 'Node 1 / master', 30, COLORS['sft'], 'bold')
    c.text(720, 219, 'Master-owned dispatcher / queue', 24, weight='bold')
    c.text(720, 258, 'Assigns independent generation jobs to free lanes', 23, MUTED)
    c.rect(722, 287, 790, 92, '#e4eef7')
    c.text(742, 324, 'Local inference owner  +  helper on the other HP core', 23)
    c.text(742, 360, 'Full model + own FP32 KV cache for this request', 22, MUTED)
    c.text(720, 424, '32 MiB PSRAM | 24 MiB model partition in 32 MiB flash', 23)
    c.text(720, 465, 'Firmware 0.5.5 | four-row tile4 | context 256', 23, MUTED)
    c.arrow(1115, 537, 1115, 650, COLORS['talk1'])
    c.text(1140, 576, 'Ethernet network', 23, MUTED)
    c.text(1140, 612, 'HTTP :80 | job 2', 23, MUTED)
    c.rect(695, 668, 850, 263)
    c.text(720, 711, 'Node 2 / peer', 30, COLORS['talk1'], 'bold')
    c.text(720, 752, 'Own inference owner + helper; same complete checkpoint', 23)
    c.text(720, 793, 'Own FP32 KV cache | 32 MiB PSRAM | tile4', 23, MUTED)
    c.text(720, 838, 'One P4 mode: master executes both requests in sequence.', 22)
    c.text(720, 880, 'Two P4 mode: one independent request on each board.', 22, COLORS['talk1'], 'bold')
    c.rect(48, 550, 620, 381)
    c.text(72, 594, 'Controlled study sequence', 28, weight='bold')
    steps = ['1  Freeze assets, 16 tasks and scoring rules', '2  Check host logits, tokenizer and outputs', '3  Run all 16 tasks on the peer for each model', '4  Match master model; run four paired blocks', '5  Restore TinyTalk-2 and peer configuration']
    for i, t in enumerate(steps):
        c.text(72, 647 + 52 * i, t, 22, MUTED)
    c.rect(48, 955, 1497, 105, '#dce9f2')
    c.text(72, 996, 'Two full models, two output streams. This increases throughput, not pooled model capacity.', 26, weight='bold')
    c.text(72, 1033, 'SD persistence, a third board, PoE/backfeed behaviour and permanent board-to-board USB are not measured here.', 22, MUTED)
    c.text(48, 1090, 'Schematic, not a wiring or electrical qualification. Network-switch topology and power draw were not independently measured.', 18, MUTED)
    c.save('matched-model-setup', [DATA / 'protocol.json', ROOT / 'docs/research/gptneo-p4-2026-10-29.md'])


if __name__ == '__main__':
    quality()
    topology()
    performance()
