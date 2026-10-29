"""Static byte accounting for the current P4LM INT8 runtime, not an admission guarantee."""
import json
import pathlib

ROOT=pathlib.Path(__file__).resolve().parents[1]

def budget(c,tokenizer_bytes):
    d,h,n,v,ctx,heads,kv=(c[k] for k in ['dim','hidden','layers','vocab','context','heads','kv_heads'])
    if min(d,h,n,v,ctx,heads,kv)<=0 or d%heads or heads%kv:raise ValueError('Invalid dimensions')
    kd=d*kv//heads
    layer=8*d+2*d*(d+4)+2*kd*(d+4)+2*h*(d+4)+d*(h+4)
    weights=v*(d+4)+n*layer+4*d
    artifact=128+weights+tokenizer_bytes
    work=4*(4*d+2*h)
    buffers=work+4*heads*ctx+4*v+8*n*ctx*kd
    # P4 pointers 4 bytes; token pointers + scores + sorted entries + strings.
    tokenizer_runtime=17*v+tokenizer_bytes
    base=artifact+buffers+tokenizer_runtime
    reserve=2*1024*1024
    return {'weights_bytes':weights,'artifact_bytes':artifact,'kv_bytes':8*n*ctx*kd,
            'psram_base_bytes':base,'internal_work_payload_bytes':work,
            'planning_reserve_bytes':reserve,'psram_including_reserve_bytes':base+reserve,
            'flash_partition_bytes':24*1024*1024,'psram_bytes':32*1024*1024,
            'flash_fits':artifact<=24*1024*1024,'psram_fits_with_reserve':base+reserve<=32*1024*1024,
            'notes':'Excludes allocator alignment, internal state/stacks and exact network peaks; 2 MiB is a planning assumption. Work bank duplicated for comparisons.'}

def main():
    manifest=json.loads((ROOT/'data/baseline-model-manifest.json').read_text(encoding='utf-8'))
    actual=budget(manifest['dimensions'],manifest['tokenizer_bytes'])
    assert actual['artifact_bytes']==manifest['bytes'] and actual['weights_bytes']==manifest['weights_bytes']
    cases={'actual_stories15M':actual}
    for ctx in [64,128,512]:
        c={**manifest['dimensions'],'context':ctx};cases[f'same_model_context_{ctx}']=budget(c,manifest['tokenizer_bytes'])
    c={**manifest['dimensions'],'layers':12}
    cases['hypothetical_12_layers_no_checkpoint_available']=budget(c,manifest['tokenizer_bytes'])
    print(json.dumps({'format':'P4LM0001 row INT8','cases':cases,'capacity_scales_with_current_board_count':False},indent=2))

if __name__=='__main__':main()
