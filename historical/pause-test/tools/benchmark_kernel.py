"""Controlled local-LAN kernel comparison; save every response, never retry jobs."""
import argparse
import datetime
import hashlib
import http.client
import json
import pathlib
import statistics
import time
from lan_client import ROOT, lan_address

PROMPTS = ['Once upon a time', 'One day, a little girl']

def request(host, method, path, body=None, timeout=180):
    c = http.client.HTTPConnection(lan_address(host), timeout=timeout)
    try:
        headers = {'X-Cluster-Key': (ROOT/'.local/lan-key.txt').read_text().strip(), 'Content-Type': 'application/json'}
        c.request(method, path, None if body is None else json.dumps(body), headers)
        r = c.getresponse()
        raw = r.read()
        if r.status != 200:
            raise RuntimeError(f'HTTP {r.status}: {raw[:300]!r}')
        return raw
    finally:
        c.close()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('host', type=lan_address)
    p.add_argument('output', type=pathlib.Path)
    p.add_argument('--kernels', nargs='+', choices=['default','legacy','paced','dual'], required=True)
    p.add_argument('--repeats', type=int, default=3)
    a = p.parse_args()
    if not 1 <= a.repeats <= 10: p.error('repeats must be 1..10')
    a.output.mkdir(parents=True, exist_ok=False)
    reference = {}
    previous = json.loads((ROOT/'data/parallel-2026-10-29/batches.json').read_text())
    for j in previous[0]['jobs']: reference[j['prompt']] = j['tokens']
    before = json.loads(request(a.host, 'GET', '/api/status'))
    assert before['model_ready'] and not before['worker_busy'] and not before['ota_pending'], before
    metadata = {'host':a.host,'kernels':a.kernels,'repeats':a.repeats,'prompts':PROMPTS,
                'tokens':24,'date_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'status_before':before}
    (a.output/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    runs = []
    for block in range(a.repeats+1):
        order = a.kernels if block % 2 else list(reversed(a.kernels))
        for kernel in order:
            for prompt_index, prompt in enumerate(PROMPTS if block else PROMPTS[:1]):
                count = 24 if block else 4
                body = {'prompt':prompt,'tokens':count,'peer':''}
                if kernel != 'default': body['kernel'] = kernel
                start = time.perf_counter()
                raw = request(a.host,'POST','/api/generate',body)
                elapsed = (time.perf_counter()-start)*1000
                (a.output/f'{block}-{kernel}-{prompt_index}.ndjson').write_bytes(raw)
                items = [json.loads(line) for line in raw.splitlines()]
                ids = [x['token'] for x in items if 'token' in x]
                done = items[-1]
                assert done.get('done') and not done.get('error') and done['boards']==1, done
                assert len(ids)==done['output_tokens']==count and ids==reference[prompt][:count], ids
                if kernel != 'default': assert done['kernel']['mode']==kernel, done
                run = {'block':block,'warmup':block==0,'variant':kernel,'prompt':prompt,
                       'tokens':ids,'client_elapsed_ms':elapsed,**done}
                runs.append(run)
                (a.output/'runs.json').write_text(json.dumps(runs,indent=2)+'\n')
                print(f'{block} {kernel} {prompt_index}: {done["elapsed_ms"]:.3f} ms, TTFT {done["ttft_ms"]:.3f} ms, identical tokens',flush=True)
    after = json.loads(request(a.host,'GET','/api/status'))
    assert after['model_id']==before['model_id'] and after['firmware']==before['firmware']
    assert after['model_ready'] and not after['ota_pending'] and not after['worker_busy']
    if 'boot_id' in before: assert before['boot_id']==after['boot_id'], 'Board restarted during experiment'
    summary = {'status_after':after,'all_tokens_identical':True,'variants':{}}
    for kernel in a.kernels:
        data = [r for r in runs if not r['warmup'] and r['variant']==kernel]
        summary['variants'][kernel] = {'elapsed_ms_median':statistics.median(r['elapsed_ms'] for r in data),
            'elapsed_ms_range':[min(r['elapsed_ms'] for r in data),max(r['elapsed_ms'] for r in data)],
            'ttft_ms_median':statistics.median(r['ttft_ms'] for r in data),'jobs':len(data)}
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)

if __name__ == '__main__': main()
