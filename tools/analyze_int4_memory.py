"""Offline measured microbenchmark audit, summary and figure."""
import pathlib,json,hashlib,statistics,subprocess
from plot_matched_models import Canvas,MUTED
ROOT=pathlib.Path(__file__).resolve().parents[1];DATA=ROOT/'data/int4-memory-2026-10-30'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def main():
 p=read(DATA/'protocol.json');host=read(DATA/'host-check.json');runs=read(DATA/'runs.json');final=read(DATA/'final.json')
 assert len(runs)==12 and final['complete_runs']==12 and final['queued']==final['running']==0 and final['configured']
 for n,digest in p['source_sha256'].items():assert sha(ROOT/n)==digest
 expected=[(b,r) for r in range(6) for b in (['coordinator','worker'] if r%2==0 else ['worker','coordinator'])]
 assert [(x['board'],x['run']) for x in runs]==expected
 names=['read_internal_small','read_psram_small','read_psram_large','unpack_internal','unpack_psram_stream','matrix_internal','matrix_psram_small','matrix_psram_stream']
 for run in runs:
  assert run['valid'] and run['core']==1 and run['matrix_reference']==host['matrix']
  assert run['scan_small_reference']==host['scan_small'] and run['scan_large_reference']==host['scan_large'] and run['unpack_reference']==host['unpack']
  assert [x['mode'] for x in run['measurements']]==names[run['run']:]+names[:run['run']]
  for x in run['measurements']:
   assert x['timed_us']>0
   calls=8 if x['mode']=='read_psram_large' else 42;assert x['calls']==calls
   assert x['logical_bytes']==calls*(1048576 if calls==8 else 24576)
   if x['mode'].startswith('matrix'):assert x['float_checksum']==host['matrix']*calls
   else:
    key='unpack' if x['mode'].startswith('unpack') else 'scan_large' if calls==8 else 'scan_small'
    assert x['uint_checksum']==(host[key]*calls)&0xffffffff
 result={}
 for board in ['coordinator','worker']:
  result[board]={}
  for name in names:
   rs=[next(x for x in run['measurements'] if x['mode']==name) for run in runs if run['board']==board and run['run']>0]
   ms=[r['timed_us']/1000 for r in rs];mb=[r['logical_bytes']*1e6/r['timed_us']/1048576 for r in rs]
   result[board][name]={'n':5,'median_ms':statistics.median(ms),'range_ms':[min(ms),max(ms)],'median_logical_MiB_per_s':statistics.median(mb)}
  a=result[board]['matrix_internal']['median_ms'];b=result[board]['matrix_psram_stream']['median_ms']
  result[board]['matrix_stream_over_internal_ratio']=b/a
  s=final['devices'][board];assert s['firmware']=='0.7.0' and s['model_ready'] and not s['worker_busy'] and not s['ota_pending']
 write(DATA/'summary.json',{'boards':result,'primary_mode_samples':80,'warmup_mode_samples':16,'scope':'Synthetic single-core scratch kernels; separate workloads, not additive inference decomposition. Logical throughput is not physical bandwidth.','cache_L2_configured_bytes':131072,'configured_CPU_MHz':360,'configured_PSRAM_MHz':200})
 lines=['# INT4 arithmetic and memory access on both ESP32-P4s','','30 October2026. Completed local diagnostic study; both nodes restored to firmware0.7.0/TinyBrainBot.','','## Methods and acceptance','','Protocol committed in2e2f6aa before measurements; LAN trial helper committed ind089d48. Diagnostic firmware0.8.0 adds an authenticated, maintenance-guarded endpoint. Model weights are unchanged. Single CPU core1,24KiB internal/PSRAM buffers,1MiB PSRAM streaming footprint,64x768 tile4 INT4 matrix, internal FP32 input, scale1. The same256-byte repeating pattern and vector are used for each placement. Timing sums bounded chunks and excludes explicit yields between chunks; interruptions inside chunks remain. Run0 is warmup, runs1–5 analyzed, mode order rotated and board order alternated.','','Compiled diagnostic C results match independent Python arithmetic for memory sums, signed nibble unpacking and matrix output. All96 measured mode records match those checksums on actual hardware;80 records enter the primary analysis. No inference timings or host speed are substituted. The output checksum is124 per matrix call,5208 per42-call batch. The pattern is synthetic and the benchmark has specialized fixed4-bit code; it is not an exact production-kernel timing.','','| Kernel | Coordinator median ms | Worker median ms |','|---|---:|---:|']
 for n in names:lines.append(f"| {n} | {result['coordinator'][n]['median_ms']:.3f} | {result['worker'][n]['median_ms']:.3f} |")
 lines+=['','## Interpretation','','Small-buffer reads achieve about317–321MiB/s from PSRAM versus333–338MiB/s internally; a1MiB sequential PSRAM scan achieves about99MiB/s. These are logical checksum-loop throughputs, not physical bus bandwidth. The configured L2 is128KiB, so1MiB exceeds its capacity; no explicit cold-cache flush or hardware counter proves coldness. Internal/small PSRAM modes can benefit from cache.','','The same matrix takes about68ms in the internal/small-buffer cases and75ms while rotating through PSRAM tiles: a roughly10–11% streaming penalty in this synthetic single-core test. Unpacking alone takes about41ms internally and48ms with streaming PSRAM. Packing/bit operations and FP32 accumulation are therefore material diagnostic work; raw memory-read time alone cannot explain the matrix interval. However these loops differ in load width, instruction mix and cache behavior: subtracting their times would not measure pure arithmetic.','','Next useful controlled optimization: compare a production-compatible INT4 unpack/dot implementation against the existing scalar/tile4 path with identical output IDs/logits, separately across internal and streaming buffers, before a new end-to-end model trial. These data do not predict a dual-core inference speedup or establish isolated PSRAM stall time. No energy/thermal/physical clock measurements; configured CPU360MHz and PSRAM200MHz retained.','','## Restoration and reproduction','','Firmware0.8.0 and restored0.7.0 both passed a distributed four-token native-reference control. Both final0.7.0 nodes retain the genuine TinyBrainBot identities and roles, no pending OTA, configured cluster and zero queued/running jobs. Private signed/provisioned app images and keys remain excluded from Git. No partition/model/wiring change, new downloads or online upload.','','All per-board raw JSON, checksums, original protocol, deployment hashes and final status are in [the data directory](data/int4-memory-2026-10-30/). Run `python tools/analyze_int4_memory.py` for offline validation/summary/figure. `tools/run_int4_memory_trial.py` is a real-device action requiring the intended idle nodes and retained private rollback; it refuses an existing private run directory. The archived protocol is fixed; choose a separately versioned fresh run for replication.','','![Measured kernels and placements](figures/int4-memory-2026-10-30.png)']
 (ROOT/'docs/research/int4-memory-2026-10-30.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 c=Canvas(1160,'INT4 computation and memory: measured separately','Two real P4s | diagnostic0.8.0 → restored0.7.0 | single core1 | five measured repetitions after warmup')
 labels={'read_internal_small':'Read internal24KiB','read_psram_small':'Read PSRAM24KiB','read_psram_large':'Read PSRAM1MiB','unpack_internal':'Unpack internal','unpack_psram_stream':'Unpack streaming PSRAM','matrix_internal':'Matrix internal','matrix_psram_small':'Matrix small PSRAM','matrix_psram_stream':'Matrix streaming PSRAM'}
 for i,n in enumerate(names):
  y=175+i*89;c.text(48,y,labels[n],24,weight='bold')
  for j,(board,color) in enumerate([('coordinator','#247da4'),('worker','#178576')]):
   r=result[board][n];yy=y-22+j*30;w=r['median_ms']/90*850;c.rect(465,yy,w,23,color,3);c.text(1505,yy+19,f"{r['median_ms']:.3f} ms",21,anchor='end')
 c.rect(48,925,1504,145,'#dce9f2');c.text(72,966,'Blue: coordinator. Green: worker. Each workload matches its independent reference on both boards.',25,weight='bold')
 c.text(72,1008,'Matrix streaming penalty ~10–11% here; single-core synthetic data, not an end-to-end model speedup.',23,MUTED)
 c.text(72,1047,'Different loops measure different workloads. Do not subtract read time to claim pure arithmetic or bus bandwidth.',21,MUTED)
 c.text(48,1120,'Read1MiB batch:8 scans; all other batches:42 calls. Timed spans exclude explicit yields. Compare within each workload.',21,MUTED)
 stem=ROOT/'docs/figures/int4-memory-2026-10-30';stem.with_suffix('.svg').write_text('\n'.join(c.s+['</svg>'])+'\n',encoding='utf-8')
 runtime=pathlib.Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node';code='require('+json.dumps(str(runtime/'node_modules/sharp'))+')(process.argv[1]).png().toFile(process.argv[2]).catch(e=>{console.error(e);process.exit(1)})'
 subprocess.run([str(runtime/'bin/node.exe'),'-e',code,str(stem.with_suffix('.svg')),str(stem.with_suffix('.png'))],check=True,capture_output=True)
 write(stem.with_suffix('.json'),{'source_sha256':{str(x.relative_to(ROOT)).replace('\\','/'):sha(x) for x in [DATA/'protocol.json',DATA/'runs.json',DATA/'summary.json',pathlib.Path(__file__)]},'scope':'Observed single-core diagnostic medians, no global hardware bandwidth or model speedup claim'})
 write(DATA/'audit.json',{'passed':True,'raw_mode_samples':96,'primary_mode_samples':80,'boards':2,'host_arithmetic_check_passed':True,'all_device_checksums_exact':True,'restored0_7_and_tinybrainbot':True,'source_sha256':{x.name:sha(x) for x in DATA.glob('*.json') if x.name!='audit.json'}})
 print('PASS96 exact mode checks,80 primary samples, both boards restored; report and figure generated')
if __name__=='__main__':main()
