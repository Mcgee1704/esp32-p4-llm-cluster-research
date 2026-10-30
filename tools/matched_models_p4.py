"""Frozen four-model study on two local P4s; restore TinyTalk-2 on completion."""
import argparse
import json
import pathlib
import statistics
import time

from matched_models import DATA, MODELS, ROOT, Native, frozen, sha, write
from gptneo_p4_trial import MASTER, PEER, status, upload, ready, idle, verify
from research_integrity import data_arguments, study_directory
from benchmark_kernel import request
from dispatch_client import Dispatcher


def safe_state(host):
    d = status(host)
    return {k: d.get(k) for k in ['firmware', 'architecture', 'model_id', 'model_ready',
            'default_kernel', 'worker_busy', 'restart_pending', 'ota_pending',
            'free_heap', 'free_psram', 'largest_psram_block']}


def switch(host, key, p):
    old = status(host)
    if old['worker_busy'] or old['restart_pending']:
        raise RuntimeError('Node is busy or restarting')
    identity = p['models'][key]['model_id']
    if old['model_ready'] and old['model_id'] == identity:
        return old
    path = ROOT / MODELS[key]['artifact']
    upload(host, 'model', path)
    return ready(host, identity, old['boot_id'] if path.suffix == '.p4gn' else None)


def run():
    import matched_models
    matched_models.DATA = DATA
    p = frozen()
    out = DATA / 'hardware'
    out.mkdir(exist_ok=False)
    script_hash = sha(pathlib.Path(__file__))
    host_refs = json.loads((DATA / 'host.json').read_text())
    refs = {(r['model'], r['case']): r for r in host_refs}
    benchmark_refs = {}
    for key, m in MODELS.items():
        engine = Native(ROOT / m['artifact'])
        try:
            benchmark_refs[key] = {c['id']: engine.generate(c['prompt'], 24)
                                   for c in p['cases'][:2]}
        finally:
            engine.close()
    write(out / 'protocol.json', {'parent_protocol_sha256': sha(DATA / 'protocol.json'),
          'script_sha256': script_hash, 'host_references_sha256': sha(DATA / 'host.json'),
          'host_runtime_sha256': sha(ROOT / '.local/build/tinyllm.dll'),
          'benchmark_references': benchmark_refs, 'model_order': list(MODELS),
          'timing_units': 'milliseconds from master monotonic clock',
          'no_automatic_inference_retries': True})
    client = Dispatcher(MASTER)
    idle(client)
    initial = {name: safe_state(h) for name, h in [('node-1', MASTER), ('node-2', PEER)]}
    if any(s['firmware'] != '0.5.5' or not s['model_ready'] or s['worker_busy'] or
           s['restart_pending'] or s['ota_pending'] or s['default_kernel'] != 'tile4' or
           s['model_id'] != p['models']['talk2']['model_id'] for s in initial.values()):
        raise RuntimeError('Unexpected starting device state')
    write(out / 'initial-state.json', initial)
    direct = []
    batches = []
    failure = None
    changed = False
    try:
        client.request('POST', '/api/cluster', {'peer': ''})
        changed = True
        for name, h in [('node-1', MASTER), ('node-2', PEER)]:
            case = next(c for c in p['cases'] if c['id'] == 'Q1')
            raw = request(h, 'POST', '/api/generate', {'prompt': case['prompt'], 'tokens': 32})
            (out / ('initial-control-' + name + '.ndjson')).write_bytes(raw)
            verify(raw, refs['talk2', 'Q1'])
        for key in MODELS:
            print('MODEL', key, 'peer installation', flush=True)
            client.request('POST', '/api/cluster', {'peer': ''})
            switch(PEER, key, p)
            for case in p['cases']:
                raw = request(PEER, 'POST', '/api/generate',
                              {'prompt': case['prompt'], 'tokens': case['limit']}, timeout=240)
                (out / f'{key}-{case["id"]}.ndjson').write_bytes(raw)
                done = verify(raw, refs[key, case['id']])
                if done['kernel']['mode'] != 'tile4' or done['kernel']['owner_core_mask'] != 2 or done['kernel']['helper_core_mask'] != 1:
                    raise RuntimeError('Unexpected kernel execution profile')
                direct.append({'model': key, 'case': case['id'], 'token_text_EOS_match': True, **done})
                write(out / 'direct-progress.json', direct)
                print('P4', key, case['id'], done['output_tokens'], round(done['elapsed_ms']), 'ms matched', flush=True)
            print('MODEL', key, 'master installation', flush=True)
            switch(MASTER, key, p)
            write(out / f'{key}-ready.json', {name: safe_state(h) for name, h in [('node-1', MASTER), ('node-2', PEER)]})
            for block in range(1, 5):
                for mode in (['local', 'cluster'] if block % 2 else ['cluster', 'local']):
                    idle(client)
                    client.request('POST', '/api/cluster', {'peer': PEER if mode == 'cluster' else ''})
                    ids = [client.submit(c['prompt'], 24)['id'] for c in p['cases'][:2]]
                    jobs = client.wait(ids, timeout=240)
                    write(out / f'{key}-block-{block}-{mode}.json', jobs)
                    for case, job in zip(p['cases'][:2], jobs):
                        if job['state'] != 'done':
                            raise RuntimeError('Dispatched job failed')
                        verify(job['raw_ndjson'].encode(), benchmark_refs[key][case['id']])
                    targets = {j['target'] for j in jobs}
                    if targets != ({'local', PEER} if mode == 'cluster' else {'local'}):
                        raise RuntimeError('Unexpected worker assignment')
                    elapsed = max(j['finished_ms'] for j in jobs) - min(j['created_ms'] for j in jobs)
                    overlap = max(0, min(j['finished_ms'] for j in jobs) - max(j['started_ms'] for j in jobs))
                    tokens = sum(len(r['tokens']) for r in benchmark_refs[key].values())
                    characters = sum(len(r['text']) for r in benchmark_refs[key].values())
                    batches.append({'model': key, 'block': block, 'mode': mode, 'elapsed_ms': elapsed,
                                    'output_tokens': tokens, 'output_unicode_characters': characters,
                                    'output_tokens_per_s': tokens * 1000 / elapsed,
                                    'output_characters_per_s': characters * 1000 / elapsed,
                                    'job_interval_overlap_ms': overlap, 'all_outputs_match': True})
                    write(out / 'batches.json', batches)
                    print('BATCH', key, block, mode, elapsed, 'ms matched', flush=True)
            write(out / 'direct.json', direct)
        summary = {}
        for key in MODELS:
            rows = [r for r in batches if r['model'] == key]
            loc = [r for r in rows if r['mode'] == 'local']
            cluster = [r for r in rows if r['mode'] == 'cluster']
            summary[key] = {'paired_blocks': 4, 'jobs': 16,
                'local_package_median_ms': statistics.median(r['elapsed_ms'] for r in loc),
                'cluster_package_median_ms': statistics.median(r['elapsed_ms'] for r in cluster),
                'cluster_package_range_ms': [min(r['elapsed_ms'] for r in cluster), max(r['elapsed_ms'] for r in cluster)],
                'paired_throughput_factor_median': statistics.median(a['elapsed_ms'] / b['elapsed_ms'] for a, b in zip(loc, cluster)),
                'cluster_tokens_per_s_median': statistics.median(r['output_tokens_per_s'] for r in cluster),
                'cluster_characters_per_s_median': statistics.median(r['output_characters_per_s'] for r in cluster),
                'actual_output_tokens_per_package': cluster[0]['output_tokens'],
                'actual_unicode_characters_per_package': cluster[0]['output_unicode_characters'],
                'same_tokens_text_EOS_all_jobs': True,
                'all_cluster_intervals_overlap': all(r['job_interval_overlap_ms'] > 0 for r in cluster)}
        write(out / 'summary.json', summary)
    except BaseException as e:
        failure = e
        write(out / 'error.json', {'exception': type(e).__name__, 'message': str(e),
                                   'completed_direct_cases': len(direct), 'completed_packages': len(batches)})
        raise
    finally:
        if changed:
            try:
                idle(client)
                client.request('POST', '/api/cluster', {'peer': ''})
                print('RESTORE TinyTalk-2 on both nodes', flush=True)
                for h in [PEER, MASTER]:
                    switch(h, 'talk2', p)
                client.request('POST', '/api/cluster', {'peer': PEER})
                queue = idle(client)
                write(out / 'final-state.json', {'devices': {name: safe_state(h) for name, h in [('node-1', MASTER), ('node-2', PEER)]},
                      'peer_configured': queue['peer'] == PEER, 'queued': queue['queued'], 'running': queue['running'],
                      'study_completed': failure is None})
            except BaseException as restore:
                write(out / 'restoration-error.json', {'error': str(restore)})
                if failure is None:
                    raise
    print('STUDY COMPLETE: 64 direct cases + 64 dispatched jobs; restored', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); data_arguments(parser)
    args = parser.parse_args(); DATA = study_directory(args, DATA)
    run()
