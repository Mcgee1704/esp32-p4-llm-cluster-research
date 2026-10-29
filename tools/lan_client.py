"""Local-only CLI for the P4 HTTP API. No DNS, redirects or public IPs."""
import argparse
import codecs
import http.client
import ipaddress
import json
import pathlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
NETWORKS=tuple(ipaddress.ip_network(x) for x in ['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','169.254.0.0/16','127.0.0.0/8'])

def lan_address(value):
    address=ipaddress.IPv4Address(value)
    if not any(address in network for network in NETWORKS):
        raise ValueError('Only literal local/private IPv4 addresses are allowed')
    return str(address)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('host',type=lan_address)
    p.add_argument('action',choices=['status','generate','model','firmware'])
    p.add_argument('--key-file',type=pathlib.Path,default=ROOT/'.local/lan-key.txt')
    p.add_argument('--file',type=pathlib.Path)
    p.add_argument('--prompt',default='Once upon a time')
    p.add_argument('--tokens',type=int,default=24)
    p.add_argument('--peer',type=lan_address,default=None)
    a=p.parse_args();key=a.key_file.read_text(encoding='utf-8').strip()
    conn=http.client.HTTPConnection(a.host,timeout=180)
    headers={'X-Cluster-Key':key,'Content-Type':'application/octet-stream'}
    try:
        if a.action=='status':conn.request('GET','/api/status',headers=headers)
        elif a.action=='generate':
            headers['Content-Type']='application/json'
            body=json.dumps({'prompt':a.prompt,'tokens':a.tokens,'peer':a.peer or ''}).encode()
            conn.request('POST','/api/generate',body,headers)
        else:
            if not a.file:p.error('--file is required for uploads')
            conn.putrequest('POST','/api/'+a.action)
            for k,v in headers.items():conn.putheader(k,v)
            conn.putheader('Content-Length',a.file.stat().st_size);conn.endheaders()
            with a.file.open('rb') as f:
                while chunk:=f.read(65536):conn.send(chunk)
        response=conn.getresponse()
        if response.status!=200:raise RuntimeError(f'HTTP {response.status}: '+response.read(4096).decode('utf-8','replace'))
        if a.action=='generate':
            decoder=codecs.getincrementaldecoder('utf-8')('replace')
            for raw in response:
                item=json.loads(raw)
                if 'bytes_hex' in item:print(decoder.decode(bytes.fromhex(item['bytes_hex'])),end='',flush=True)
                if item.get('done'):
                    print(decoder.decode(b'',final=True));print(json.dumps(item,indent=2))
                    if item.get('error'):raise RuntimeError(item['error'])
        else:print(response.read().decode('utf-8','replace'))
    finally:conn.close()

if __name__=='__main__':main()
