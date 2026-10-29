"""Local-only, counterbalanced serial/parallel P4 throughput experiment."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import datetime
import hashlib
import http.client
import json
import pathlib
import statistics
import threading
import time
from lan_client import ROOT, lan_address

PROMPTS = {'A': 'Once upon a time', 'B': 'One day, a little girl'}
ORDERS = [('serial', 'parallel'), ('parallel', 'serial'),
          ('parallel', 'serial'), ('serial', 'parallel')]


def batch_metrics(jobs, elapsed_ms):
    if not jobs or elapsed_ms <= 0 or any(
        not 0 <= j['start_ms'] <= j['end_ms'] <= elapsed_ms for j in jobs
    ):
        raise ValueError('Invalid batch timeline')
    return {'elapsed_ms': elapsed_ms, 'output_tokens': sum(len(j['tokens']) for j in jobs),
            'tokens_per_second': sum(len(j['tokens']) for j in jobs)*1000/elapsed_ms,
            'overlap_ms': max(0, min(j['end_ms'] for j in jobs)-max(j['start_ms'] for j in jobs)),
            'start_skew_ms': max(j['start_ms'] for j in jobs)-min(j['start_ms'] for j in jobs),
            'mean_completion_ms': statistics.mean(j['end_ms'] for j in jobs),
            'mean_request_ms': statistics.mean(j['end_ms']-j['start_ms'] for j in jobs)}


def status(host, headers):
    conn = http.client.HTTPConnection(host, timeout=15)
    try:
        conn.request('GET', '/api/status', headers=headers)
        response = conn.getresponse()
        data = json.loads(response.read())
        assert response.status == 200 and data['model_ready'] and not data['worker_busy'] and not data['ota_pending'], data
        return data
    finally:
        conn.close()


def generate(host, job, headers, origin, raw_path, barrier=None):
    if barrier:
        barrier.wait(timeout=10)
    started = time.perf_counter_ns()
    conn = http.client.HTTPConnection(host, timeout=180)
    items, arrivals = [], []
    try:
        conn.request('POST', '/api/generate', json.dumps({'prompt': PROMPTS[job], 'tokens': 24, 'peer': ''}), headers)
        response = conn.getresponse()
        with raw_path.open('wb') as f:
            for raw in response:
                arrived = time.perf_counter_ns()
                f.write(raw); f.flush()
                if response.status == 200:
                    item = json.loads(raw); items.append(item)
                    if 'token' in item:
                        arrivals.append((arrived-origin)/1e6)
        assert response.status == 200, (host, response.status, raw_path)
    finally:
        conn.close()
    ended = time.perf_counter_ns()
    tokens = [item['token'] for item in items if 'token' in item]
    done = items[-1]
    assert done.get('done') and not done.get('error'), done
    assert done['boards'] == 1 and done['output_tokens'] == len(tokens) == 24, done
    assert done['profile']['rpc_calls'] == 0, done
    return {'host': host, 'job': job, 'prompt': PROMPTS[job], 'tokens': tokens,
            'text': b''.join(bytes.fromhex(item['bytes_hex']) for item in items if 'bytes_hex' in item).decode('utf-8'),
            'start_ms': (started-origin)/1e6, 'end_ms': (ended-origin)/1e6,
            'token_arrivals_ms': arrivals, 'firmware_metrics': done}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('board1', type=lan_address)
    p.add_argument('board2', type=lan_address)
    p.add_argument('output', type=pathlib.Path)
    a = p.parse_args()
    if a.board1 == a.board2:
        p.error('Two distinct boards are required')
    a.output.mkdir(parents=True, exist_ok=False)
    headers = {'X-Cluster-Key': (ROOT/'.local/lan-key.txt').read_text().strip(), 'Content-Type': 'application/json'}
    hosts = [a.board1, a.board2]
    before = {host: status(host, headers) for host in hosts}
    assert before[hosts[0]]['model_id'] == before[hosts[1]]['model_id']
    assert all(s['firmware'] == '0.1.3' for s in before.values())
    metadata = {'date_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'prompts': PROMPTS,
                'tokens_per_job': 24, 'orders': ORDERS, 'status_before': before,
                'script_sha256': hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}
    (a.output/'metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
    batches, reference = [], {}
    for block, order in enumerate(ORDERS, 1):
        for mode in order:
            origin = time.perf_counter_ns()
            if mode == 'serial':
                assigned = hosts[(block-1) % 2]
                jobs = [generate(assigned, job, headers, origin, a.output/f'{block}-{mode}-{job}.ndjson') for job in PROMPTS]
            else:
                barrier = threading.Barrier(2)
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [executor.submit(generate, hosts[((block-1)+i) % 2], job, headers, origin,
                                               a.output/f'{block}-{mode}-{job}.ndjson', barrier)
                               for i, job in enumerate(PROMPTS)]
                    jobs = [f.result() for f in futures]
            elapsed = (time.perf_counter_ns()-origin)/1e6
            metrics = batch_metrics(jobs, elapsed)
            events = sorted((arrival, j['job']) for j in jobs for arrival in j['token_arrivals_ms'])
            switches = sum(left[1] != right[1] for left, right in zip(events, events[1:]))
            batch = {'block': block, 'mode': mode, **metrics, 'token_stream_switches': switches, 'jobs': jobs}
            batches.append(batch)
            (a.output/'batches.json').write_text(json.dumps(batches, indent=2)+'\n')
            for j in jobs:
                reference.setdefault(j['job'], j['tokens'])
                assert j['tokens'] == reference[j['job']], 'Token mismatch; raw data retained'
            if mode == 'parallel':
                assert metrics['overlap_ms'] > 0 and metrics['start_skew_ms'] < 500
                assert switches > 1, 'No interleaved streamed-token evidence'
            after = {host: status(host, headers) for host in hosts}
            assert all(after[h]['model_id'] == before[h]['model_id'] and after[h]['firmware'] == before[h]['firmware'] for h in hosts)
            (a.output/'status-after.json').write_text(json.dumps(after, indent=2)+'\n')
            print(f"Block {block} {mode}: {elapsed/1000:.3f} s, {metrics['tokens_per_second']:.3f} tokens/s, overlap {metrics['overlap_ms']/1000:.3f} s, stream switches {switches}", flush=True)
    summary = {'blocks': 4, 'jobs_per_batch': 2, 'tokens_per_batch': 48, 'all_token_sequences_match': True}
    for mode in ('serial', 'parallel'):
        selected = [b for b in batches if b['mode'] == mode]
        summary[mode] = {key: statistics.median(b[key] for b in selected) for key in
                         ('elapsed_ms', 'tokens_per_second', 'overlap_ms', 'start_skew_ms', 'mean_completion_ms', 'mean_request_ms')}
        summary[mode]['elapsed_range_ms'] = [min(b['elapsed_ms'] for b in selected), max(b['elapsed_ms'] for b in selected)]
    ratios = [next(b['elapsed_ms'] for b in batches if b['block'] == block and b['mode'] == 'serial') /
              next(b['elapsed_ms'] for b in batches if b['block'] == block and b['mode'] == 'parallel') for block in range(1, 5)]
    summary['paired_speedups'] = ratios
    summary['median_paired_speedup'] = statistics.median(ratios)
    summary['efficiency_vs_ideal_two'] = statistics.median(ratios)/2
    summary['practical_gain_target_met'] = min(ratios) > 1.5
    summary['date_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (a.output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    with (a.output/'batches.csv').open('w', encoding='utf-8', newline='') as f:
        fields = [k for k in batches[0] if k != 'jobs']
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
        writer.writerows({k: b[k] for k in fields} for b in batches)
    with (a.output/'jobs.csv').open('w', encoding='utf-8', newline='') as f:
        fields = ['block', 'mode', 'job', 'host', 'start_ms', 'end_ms', 'first_token_ms', 'firmware_elapsed_ms', 'firmware_ttft_ms']
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
        for b in batches:
            for j in b['jobs']:
                writer.writerow({'block': b['block'], 'mode': b['mode'], 'job': j['job'], 'host': j['host'],
                                 'start_ms': j['start_ms'], 'end_ms': j['end_ms'], 'first_token_ms': j['token_arrivals_ms'][0],
                                 'firmware_elapsed_ms': j['firmware_metrics']['elapsed_ms'], 'firmware_ttft_ms': j['firmware_metrics']['ttft_ms']})
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
