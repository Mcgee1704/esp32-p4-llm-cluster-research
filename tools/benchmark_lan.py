"""Compare real P4 solo/pair runs; keep raw evidence locally, never retry inference."""
import argparse
import datetime
import http.client
import json
import pathlib
import statistics
import time
from lan_client import ROOT, lan_address


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('master', type=lan_address)
    p.add_argument('peer', type=lan_address)
    p.add_argument('output', type=pathlib.Path)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--tokens', type=int, default=24)
    p.add_argument('--require-profile', action='store_true')
    p.add_argument('--require-reuse', action='store_true')
    a = p.parse_args()
    if not 1 <= a.tokens <= 128 or not 1 <= a.repeats <= 20:
        p.error('tokens must be 1..128; repeats 1..20')
    a.output.mkdir(parents=True, exist_ok=False)
    headers = {'X-Cluster-Key': (ROOT/'.local/lan-key.txt').read_text().strip(), 'Content-Type': 'application/json'}
    runs = []
    reference = None
    for repetition in range(a.repeats):
        for mode in ('solo', 'pair'):
            conn = http.client.HTTPConnection(a.master, timeout=180)
            started = time.monotonic()
            try:
                conn.request('POST', '/api/generate', json.dumps({'prompt': 'Once upon a time', 'tokens': a.tokens, 'peer': a.peer if mode == 'pair' else ''}), headers)
                response = conn.getresponse()
                raw = response.read()
                (a.output/f'{repetition+1}-{mode}.ndjson').write_bytes(raw)
                assert response.status == 200, (response.status, raw)
            finally:
                conn.close()
            items = [json.loads(line) for line in raw.splitlines()]
            tokens = [item['token'] for item in items if 'token' in item]
            done = items[-1]
            assert done.get('done') and not done.get('error'), done
            assert done['boards'] == (2 if mode == 'pair' else 1)
            assert len(tokens) == done['output_tokens'] == a.tokens
            if reference is None:
                reference = tokens
            assert reference == tokens, 'Token IDs differ; raw responses saved'
            run = {'mode': mode, 'repetition': repetition+1, 'tokens': tokens, 'client_elapsed_ms': (time.monotonic()-started)*1000, **done}
            runs.append(run)
            (a.output/'runs.json').write_text(json.dumps(runs, indent=2)+'\n')
            if a.require_profile:
                profile = done.get('profile')
                assert profile, 'Firmware does not expose timing profile yet'
                assert profile['master_compute_ms'] > 0
                assert profile['rpc_calls'] == profile['worker_reports']
                assert profile['rpc_total_ms'] >= profile['worker_compute_ms']
                if mode == 'pair':
                    assert profile['worker_compute_ms'] > 0
                    if a.require_reuse:
                        assert profile['connections'] == 1, profile
            print(f"{mode} {repetition+1}: {done['elapsed_ms']:.3f} ms, TTFT {done['ttft_ms']:.3f} ms; tokens identical", flush=True)
            if 'profile' in done:
                print(json.dumps(done['profile']), flush=True)
    statuses = {}
    for host in (a.master, a.peer):
        conn = http.client.HTTPConnection(host, timeout=15)
        try:
            conn.request('GET', '/api/status', headers=headers)
            response = conn.getresponse()
            statuses[host] = json.loads(response.read())
            assert response.status == 200 and statuses[host]['model_ready'] and not statuses[host]['worker_busy']
        finally:
            conn.close()
    assert statuses[a.master]['model_id'] == statuses[a.peer]['model_id']
    summary = {'date_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'master': a.master, 'peer': a.peer, 'prompt': 'Once upon a time', 'output_tokens': a.tokens, 'tokens_identical': True, 'status_after': statuses}
    for mode in ('solo', 'pair'):
        selected = [r for r in runs if r['mode'] == mode]
        summary[mode] = {key: statistics.median(r[key] for r in selected) for key in ('elapsed_ms', 'ttft_ms')}
        summary[mode]['elapsed_range_ms'] = [min(r['elapsed_ms'] for r in selected), max(r['elapsed_ms'] for r in selected)]
        if 'profile' in selected[0]:
            summary[mode]['profile_medians'] = {key: statistics.median(r['profile'][key] for r in selected) for key in selected[0]['profile']}
    summary['pair_extra_percent'] = (summary['pair']['elapsed_ms']/summary['solo']['elapsed_ms']-1)*100
    (a.output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
