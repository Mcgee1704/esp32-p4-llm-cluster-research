"""Client for the P4-owned dispatcher. The PC never selects a job's worker."""
import argparse
import http.client
import json
import time
from lan_client import ROOT, lan_address

class APIError(RuntimeError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(f'HTTP {status}: {message}')

class Dispatcher:
    def __init__(self, host):
        self.host = lan_address(host)
        self.key = (ROOT/'.local/lan-key.txt').read_text().strip()

    def request(self, method, path, body=None):
        conn = http.client.HTTPConnection(self.host, 8081, timeout=15)
        try:
            conn.request(method, path, None if body is None else json.dumps(body),
                         {'X-Cluster-Key': self.key, 'Content-Type': 'application/json'})
            response = conn.getresponse()
            raw = response.read(1024*1024)
            if response.status not in (200, 202):
                raise APIError(response.status, raw.decode('utf-8', 'replace'))
            return json.loads(raw)
        finally:
            conn.close()

    def submit(self, prompt, tokens=24):
        return self.request('POST', '/api/jobs', {'prompt': prompt, 'tokens': tokens})

    def wait(self, ids, timeout=360, poll=.2):
        deadline = time.monotonic()+timeout
        results = {}
        while len(results) < len(ids):
            for job_id in ids:
                if job_id in results:
                    continue
                job = self.request('GET', '/api/jobs/'+job_id)
                if job['state'] in ('done', 'failed', 'cancelled'):
                    results[job_id] = job
            if len(results) < len(ids):
                if time.monotonic() >= deadline:
                    raise TimeoutError('Polling timed out; accepted jobs may still be active')
                time.sleep(poll)
        return [results[job_id] for job_id in ids]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('host', type=lan_address)
    p.add_argument('action', choices=['status', 'configure', 'generate', 'job', 'cancel'])
    p.add_argument('--peer', default='')
    p.add_argument('--prompt', default='Once upon a time')
    p.add_argument('--tokens', type=int, default=24)
    p.add_argument('--id')
    a = p.parse_args();client = Dispatcher(a.host)
    if a.action == 'status': result = client.request('GET', '/api/cluster')
    elif a.action == 'configure':
        result = client.request('POST', '/api/cluster', {'peer': lan_address(a.peer) if a.peer else ''})
    elif a.action == 'generate':
        accepted = client.submit(a.prompt, a.tokens)
        print('Accepted '+accepted['id'], flush=True)
        result = client.wait([accepted['id']])[0]
    else:
        if not a.id:p.error('--id required')
        result = client.request('DELETE' if a.action == 'cancel' else 'GET', '/api/jobs/'+a.id)
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
