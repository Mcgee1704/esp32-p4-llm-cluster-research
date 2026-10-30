"""Stage 0.6.1 on existing 50M shards, then prove lossless cold-load on both P4s."""
import hashlib
import json
import shutil
import time
from gptneo_p4_trial import MASTER,PEER,status,upload,idle,verify,Dispatcher
from benchmark_kernel import request
from pack_supra import ROOT
from supra_storage import wrap,unwrap
from check_supra_native import write


def ready(host,expected,boot,artifact):
    deadline=time.monotonic()+180;last=None
    while time.monotonic()<deadline:
        try:
            last=status(host)
            if last['firmware']=='0.6.1' and last['model_ready'] and last['model_id']==expected and last['artifact_id']==artifact and not last['ota_pending'] and not last['restart_pending'] and last['boot_id']!=boot:return last
        except (OSError,RuntimeError,ValueError):pass
        time.sleep(2)
    raise RuntimeError(('Storage control boot failed',host,last))


def main():
    directory=ROOT/'.local/models/supra50-f0566e6be9f1';out=ROOT/'data/supra50-2026-10-29'
    assert (out/'device-memory.json').is_file(),'Finish the uncompressed 50M study first'
    private=ROOT/'.local/supra-p4-2026-10-29';image=private/'p4-0.6.1.bin'
    shutil.copyfile(ROOT/'.local/build/rev1/p4_tinystories.bin',image)
    idle(Dispatcher(MASTER));report=json.loads((directory/'pack-report.json').read_text('utf-8'));records=[]
    for role,host in [('worker',PEER),('coordinator',MASTER)]:
        before=status(host);assert before['model_id']==report[role]['model_id'] and not before['worker_busy']
        upload(host,'firmware',image);after=ready(host,report[role]['model_id'],before['boot_id'],report[role]['artifact_id'])
        records.append({'node':role,'stage':'firmware','status':after});write(private/'storage-controls-private.json',records)
        print(role,'0.6.1 with existing uncompressed shard ready',flush=True)
    for role,host in [('worker',PEER),('coordinator',MASTER)]:
        raw=(directory/('supra-'+role+'.p4qs')).read_bytes();compressed=wrap(raw);assert unwrap(compressed)==raw
        path=directory/('supra-'+role+'.p4zl');path.write_bytes(compressed);before=status(host)
        upload(host,'model',path);after=ready(host,report[role]['model_id'],before['boot_id'],report[role]['artifact_id'])
        assert after['model_stored_bytes']==len(compressed) and after['model_load_requested']==len(raw)
        records.append({'node':role,'stage':'compressed','status':after,'stored_sha256':hashlib.sha256(compressed).hexdigest()});write(private/'storage-controls-private.json',records)
        print(role,'compressed shard cold-loaded with identical identity',len(compressed),'->',len(raw),flush=True)
    client=Dispatcher(MASTER);cluster=idle(client);assert cluster['configured'] and cluster['mode']=='sharded'
    p=json.loads((out/'protocol.json').read_text('utf-8'));case=p['cases'][0];ref=json.loads((out/'host-generations.json').read_text('utf-8'))[0]
    raw=request(MASTER,'POST','/api/generate',{'prompt':case['prompt'],'tokens':case['limit']},timeout=300)
    done=verify(raw,ref);assert done['boards']==2 and not done.get('error')
    (out/'compressed-control.ndjson').write_bytes(raw)
    keys=['firmware','model_ready','model_id','artifact_id','role','first_layer','end_layer','quant_bits','free_psram','model_load_requested','model_stored_bytes','worker_busy','ota_pending']
    write(out/'storage-control.json',{'firmware_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'same_tokens_text_eos':True,'done':done,'nodes':[{**{k:v for k,v in x.items() if k!='status'},'status':{k:x['status'].get(k) for k in keys}} for x in records]})
    print('Both-node compressed 50M generation passed',flush=True)


if __name__=='__main__':main()
