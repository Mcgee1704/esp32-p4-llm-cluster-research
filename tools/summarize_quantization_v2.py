"""Derived offline results and explicitly hypothetical grouped-layout budgets."""
from supra_quantization_study import OUT,ROOT,read,write,sha


def main():
    names=['row','s32','a64','gptq'];v={n:read(OUT/('validation-'+n+'.json')) for n in names}
    q=read(OUT/'quality-summary.json');candidates=read(OUT/'candidates.json')
    old=ROOT/'data/supra100-2026-10-29'
    old_artifacts=read(old/'model-artifacts.json');memory=read(old/'device-memory.json')
    tokenizer_bytes=old_artifacts['coordinator']['tokenizer_bytes'];budgets={}
    for name,candidate in candidates['variants'].items():
        sizes=candidate['matrix_bytes'];co=256+tokenizer_bytes+sum(b for key,b in sizes.items() if not key.startswith('model.layers.') or int(key.split('.')[2])<4)
        wo=256+sum(b for key,b in sizes.items() if key.startswith('model.layers.') and int(key.split('.')[2])>=4)
        budgets[name]={'proposed_coordinator_raw_bytes':co,'proposed_worker_raw_bytes':wo,
            'proposed_full_raw_bytes':co+wo-256,
            'estimated_residual_using_prior_poststudy_free_psram':{
                'coordinator':memory['coordinator']['free_psram']-(co-old_artifacts['coordinator']['bytes']),
                'worker':memory['worker']['free_psram']-(wo-old_artifacts['worker']['bytes'])}}
    summary={'scope':'Offline host only. Selected candidate rejected before C implementation or any P4 write.',
        'validation':{n:{k:v[n][k] for k in ['positions','mean_kl_nats','top1_agreement']} for n in names},
        'gptq_kl_reduction_percent_vs_row':100*(1-v['gptq']['mean_kl_nats']/v['row']['mean_kl_nats']),
        'gptq_top1_increase_percentage_points':100*(v['gptq']['top1_agreement']-v['row']['top1_agreement']),
        'screen_counts':q['counts'],'manual_first_claim_counts':read(OUT/'manual-review.json')['counts_of_16'],
        'device_admitted':False,'device_gate':'Not evaluated; earlier frozen quality gate failed.',
        'quantization_metadata_bits_per_matrix_weight_excluding_descriptors':{'tied_embedding_symmetric_group32':4.5,'transformer_affine_group64':4.375},
        'hypothetical_layout_budgets':budgets,
        'budget_limits':'Byte arithmetic for proposed 128-byte header + 128-byte metadata + 16-byte matrix descriptors; not actual P4 artifacts. Residual estimates subtract artifact growth from prior measured poststudy free PSRAM and omit any new kernel/runtime overhead or fragmentation. No compression, C allocation or device admission proof.',
        'input_sha256':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in [OUT/'quality-summary.json',OUT/'candidates.json',old/'device-memory.json',old/'model-artifacts.json',ROOT/'tools/summarize_quantization_v2.py']}}
    write(OUT/'summary.json',summary);print('Summary written; no C/P4 candidate admitted')


if __name__=='__main__':main()
