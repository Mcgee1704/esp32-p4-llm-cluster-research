"""Aggregate local controlled LAN experiments; preserve per-run differences."""
import csv
import hashlib
import json
import pathlib
import statistics
from lan_client import ROOT


def main():
    base = ROOT/'data/lan-raw-2026-10-29'
    output = ROOT/'.local/lan-analysis'
    output.mkdir(parents=True, exist_ok=True)
    stages = [('0.1.1', 'instrumented-baseline'), ('0.1.2', 'nodelay'), ('0.1.3', 'nodelay-reuse')]
    reference = json.loads((ROOT/'data/initial-two-board-2026-10-29/runs.json').read_text())[0]['tokens']
    rows, summary, manifest = [], {}, {}
    for version, folder in stages:
        runs_path = base/folder/'runs.json'
        runs = json.loads(runs_path.read_text())
        assert len(runs) == 6
        manifest[str(runs_path.relative_to(ROOT))] = hashlib.sha256(runs_path.read_bytes()).hexdigest()
        for run in runs:
            assert run['tokens'] == reference and run['output_tokens'] == 24 and not run.get('error')
            profile = run['profile']
            assert profile['rpc_calls'] == profile['worker_reports']
            raw = base/folder/f"{run['repetition']}-{run['mode']}.ndjson"
            manifest[str(raw.relative_to(ROOT))] = hashlib.sha256(raw.read_bytes()).hexdigest()
            rows.append({'firmware': version, 'mode': run['mode'], 'repetition': run['repetition'],
                         'elapsed_ms': run['elapsed_ms'], 'ttft_ms': run['ttft_ms'], **profile,
                         'rpc_overhead_ms': profile['rpc_total_ms']-profile['worker_compute_ms']})
        stage = {}
        for mode in ('solo', 'pair'):
            data = [r for r in rows if r['firmware'] == version and r['mode'] == mode]
            stage[mode] = {key: statistics.median(r[key] for r in data) for key in data[0] if key not in ('firmware','mode','repetition')}
            stage[mode]['elapsed_range_ms'] = [min(r['elapsed_ms'] for r in data), max(r['elapsed_ms'] for r in data)]
        stage['pair_extra_percent'] = 100*(stage['pair']['elapsed_ms']/stage['solo']['elapsed_ms']-1)
        summary[version] = stage
        image = base/f'p4_tinystories-{version}.bin'
        # Historical firmware images contain a private key and are not distributed.
        if image.exists():
            manifest[str(image.relative_to(ROOT))] = hashlib.sha256(image.read_bytes()).hexdigest()
    old, final = summary['0.1.1']['pair'], summary['0.1.3']['pair']
    summary['comparison'] = {'elapsed_reduction_percent': 100*(1-final['elapsed_ms']/old['elapsed_ms']),
        'rpc_overhead_reduction_percent': 100*(1-final['rpc_overhead_ms']/old['rpc_overhead_ms']),
        'nodelay_to_reuse_reduction_percent': 100*(1-final['elapsed_ms']/summary['0.1.2']['pair']['elapsed_ms']),
        'all_18_runs_match_original_tokens': True}
    with (output/'runs.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    (output/'sha256-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
