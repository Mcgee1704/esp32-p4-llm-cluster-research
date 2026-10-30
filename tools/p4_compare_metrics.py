"""Pure paired descriptive analysis; tokenizers and output work stay explicit."""
import statistics


def rates(done):
    elapsed=done['elapsed_ms'];first=done['ttft_ms'];n=done['output_tokens']
    if elapsed<=0 or not 0<=first<=elapsed or type(n) is not int or n<0:
        raise ValueError('Invalid timing or token count')
    return {'total_output_tokens_per_s':n*1000/elapsed,
            'decode_proxy_tokens_per_s':(n-1)*1000/(elapsed-first)
            if not done['eos'] and n>1 and elapsed>first else None}


def paired_summary(rows):
    expected={(model,case,block) for model in ['tinybrainbot','supra']
              for case in ['B1','B2'] for block in [1,2,3]}
    indexed={(r['model'],r['case'],r['block']):r['done'] for r in rows}
    if len(indexed)!=len(rows) or set(indexed)!=expected:
        raise ValueError('Missing, duplicate or unexpected paired measurement')
    result={}
    for case in ['B1','B2']:
        models={};matched=True
        for model in ['tinybrainbot','supra']:
            ds=[indexed[model,case,b] for b in [1,2,3]]
            if len({d['prompt_tokens'] for d in ds})!=1:
                raise ValueError('Prompt length changed inside a fixed model/case')
            elapsed=[d['elapsed_ms']/1000 for d in ds];first=[d['ttft_ms']/1000 for d in ds]
            proxies=[rates(d)['decode_proxy_tokens_per_s'] for d in ds]
            matched &= all(d['output_tokens']==16 and d['eos'] is False for d in ds)
            models[model]={'prompt_tokens':ds[0]['prompt_tokens'],
                'output_tokens':[d['output_tokens'] for d in ds],'eos':[d['eos'] for d in ds],
                'total_seconds':elapsed,'total_median_seconds':statistics.median(elapsed),
                'total_range_seconds':[min(elapsed),max(elapsed)],'ttft_median_seconds':statistics.median(first),
                'decode_proxy_median_tokens_per_s':statistics.median(proxies) if all(x is not None for x in proxies) else None}
        ratios=[indexed['supra',case,b]['elapsed_ms']/indexed['tinybrainbot',case,b]['elapsed_ms'] for b in [1,2,3]]
        result[case]={'paired_blocks':3,'matched_capped_outputs':matched,'models':models,
            'supra_over_tiny_total_median':statistics.median(ratios) if matched else None,
            'scope':'Same raw prompt bytes and cap; different vocabularies/output texts and potentially different input-token counts. Deployed-system latency, not isolated arithmetic.'}
    return result
