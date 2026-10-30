"""Standalone English acceptance figures from offline records. No network."""
from plot_matched_models import Canvas, INK, MUTED
from verify_tinybrainbot_p4 import ROOT, DATA, read, sha, write

BLUE = '#286b9b'
GREEN = '#168476'


def save(c, label, names):
    sources = [DATA / n for n in names] + [ROOT / 'tools/plot_tinybrainbot_p4.py']
    c.save(label, sources)
    meta = ROOT / 'docs/figures' / (label + '-2026-10-29.json')
    d = read(meta)
    d['notes'] = 'Local English figure. Real two-P4 acceptance; latency is descriptive, n=3, no confidence interval or controlled speedup. Host equivalence is not answer correctness. Configured clocks are not physical measurements.'
    write(meta, d)


def setup():
    a = read(DATA / 'model-artifacts.json'); f = read(DATA / 'final.json')
    c = Canvas(1050, 'TinyBrainBot-100M: one model across two P4s',
               'Real devices | Firmware 0.7.0 | row INT4 + FP32 scales/KV | Context 256 | 29 October 2026')
    c.rect(48, 135, 1504, 110)
    c.text(800, 178, 'Local LAN client / master dispatcher', 28, weight='bold', anchor='middle')
    c.text(800, 216, 'Two submitted requests queue for ONE distributed inference lane', 23, MUTED, anchor='middle')
    c.arrow(480, 245, 480, 305)
    for i, (role, title, layers, detail) in enumerate([
        ('coordinator', 'P4 coordinator', 'Embedding + layers 0-3 + output head', 'Real SPBP Metaspace/BPE tokenizer'),
        ('worker', 'P4 worker', 'Layers 4-11 + local KV cache', 'No embedding table or tokenizer')]):
        x = 48 + i * 800
        c.rect(x, 310, 704, 355)
        c.text(x + 26, 358, title, 30, BLUE if not i else GREEN, 'bold')
        for y, text in [(407, layers), (450, detail), (493, '32 MiB PSRAM + 32 MiB flash per board'),
                        (536, f"Stored model: {a[role]['compressed_bytes']/1e6:.2f} MB / 24 MiB partition"),
                        (579, f"Final free PSRAM: {f['devices'][role]['free_psram']/1e6:.2f} MB"),
                        (627, 'tile4 matrix path uses both CPU cores')]:
            c.text(x + 26, y, text, 22, MUTED if y in [493, 627] else INK)
    c.arrow(752, 410, 848, 410)
    c.arrow(848, 565, 752, 565, GREEN)
    c.text(800, 386, 'LAN', 20, BLUE, 'bold', 'middle')
    c.text(800, 600, 'return', 18, GREEN, anchor='middle')
    c.rect(48, 697, 1504, 147, '#dce9f2')
    c.text(73, 738, '768 FP32 hidden values per direction: 3,072 payload bytes / forward RPC', 27, weight='bold')
    c.text(73, 781, 'Layer phases are sequential; this split expands model capacity. It does not double request throughput.', 23, MUTED)
    c.text(73, 819, 'TCP framing, profiling and prefill/control calls add traffic. No packet-capture or energy measurement.', 21, MUTED)
    c.text(48, 904, 'Actual wiring: LAN without PoE; each board powered by USB-C from the computer. No inter-board USB.', 23, weight='bold')
    c.text(48, 949, 'No SD used. No partition changes. Configured clocks unchanged: CPU 360 MHz, PSRAM 200 MHz.', 23, MUTED)
    c.text(48, 1002, 'Source, original model weights, private authenticated firmware images and rollback packages remain local.', 21, MUTED)
    save(c, 'tinybrainbot-p4-setup', ['model-artifacts.json', 'final.json', 'protocol.json', 'build-receipt.json'])


def results():
    s = read(DATA / 'device-summary.json'); a = read(DATA / 'model-artifacts.json'); cold = s['memory_stages']['cold_load']
    c = Canvas(1170, 'TinyBrainBot fits; the real tokenizer preserves the reference',
               'Two ESP32-P4s | Technical acceptance, not a new model-quality ranking | 29 October 2026')
    c.rect(48, 135, 735, 360)
    c.text(72, 181, 'Compressed flash occupancy', 28, weight='bold')
    c.text(72, 218, '24 MiB model partition per board', 22, MUTED)
    for i, role in enumerate(['coordinator', 'worker']):
        y = 266 + i * 105; n = a[role]['compressed_bytes']
        c.text(72, y, role.capitalize(), 22, BLUE if not i else GREEN, 'bold')
        c.rect(72, y + 16, 540, 24, '#e4ebf0', 6)
        c.rect(72, y + 16, 540 * n / (24 * 1024**2), 24, BLUE if not i else GREEN, 6)
        c.text(642, y + 38, f'{n/1e6:.2f} MB', 22)
    c.text(72, 471, 'Expanded: 26.80 MB coordinator / 25.44 MB worker', 21, MUTED)
    c.rect(803, 135, 749, 360)
    c.text(827, 181, 'Observed residual PSRAM', 28, weight='bold')
    c.text(827, 218, 'Cold model load; free bytes, decimal MB', 22, MUTED)
    for i, role in enumerate(['coordinator', 'worker']):
        y = 270 + i * 100
        c.text(827, y, role.capitalize(), 23, BLUE if not i else GREEN, 'bold')
        c.text(1465, y, f"{cold[role]['free_psram']/1e6:.3f} MB", 29, weight='bold', anchor='end')
        c.text(827, y + 37, f"Boot low-water: {cold[role]['min_free_psram']/1e6:.3f} MB", 21, MUTED)
    c.text(827, 471, 'Both exceed the fixed 0.524 MB admission floor.', 21, MUTED)
    c.rect(48, 520, 1504, 263)
    c.text(72, 566, 'Different evidence boundaries', 28, weight='bold')
    for y, text in [(612, 'HOST: 30/30 complete prior INT4 answers unchanged; 5,031 input probes; 64,000 piece decodes.'),
                    (654, 'P4: 10/10 new-model complete streams offline rechecked; 3 timing receipts pass trial assertions.'),
                    (696, 'UPDATE: two old-Supra compatibility controls; TinyBrainBot same-image LAN OTA + cold-load control.'),
                    (741, 'STRESS: 1,024-byte input rejected HTTP400; boot/model preserved. Count258 comes from host/reference.')]:
        c.text(72, y, text, 22, MUTED)
    c.rect(48, 806, 1504, 224, '#dce9f2')
    t = s['timing']
    c.text(72, 850, 'Fixed T13 latency: 16 prompt tokens, 3 output tokens, EOS', 28, weight='bold')
    c.text(72, 899, f"Median {t['median_seconds']:.3f} s | Observed {t['min_seconds']:.3f}-{t['max_seconds']:.3f} s | n = 3", 27, BLUE, 'bold')
    c.text(72, 946, 'Includes prompt processing, communication and stop detection. No controlled speedup baseline.', 23, MUTED)
    c.text(72, 992, 'Variable output lengths prevent a fair cross-model ranking from these acceptance-case durations.', 22, MUTED)
    c.text(48, 1080, 'Exact agreement also preserves wrong answers: e.g. bicycle = four wheels. Correct transport is not factual accuracy.', 23, weight='bold')
    c.text(48, 1130, 'Small prespecified device subset; host logit checks are not device full-logit checks. No energy or general assistant claim.', 21, MUTED)
    save(c, 'tinybrainbot-p4-acceptance', ['device-summary.json', 'host-report.json', 'model-artifacts.json'])


if __name__ == '__main__':
    setup(); results()
