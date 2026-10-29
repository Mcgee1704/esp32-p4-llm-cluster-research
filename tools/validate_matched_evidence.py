"""Check stored experiment joins, raw outputs, clocks and restoration offline."""
import hashlib
import json
import pathlib
import re
import statistics

from matched_models import DATA, MODELS, ROOT, sha, write
from gptneo_p4_trial import verify


def main():
    p = json.loads((DATA / 'protocol.json').read_text())
    assert sha(DATA / 'protocol.json') == (DATA / 'protocol.sha256').read_text().strip()
    cases = {r['id']: r for r in p['cases']}
    expected_keys = {(m, c) for m in MODELS for c in cases}
    rows = json.loads((DATA / 'host.json').read_text())
    assert len(rows) == 64 and {(r['model'], r['case']) for r in rows} == expected_keys
    refs = {(r['model'], r['case']): r for r in rows}
    review = json.loads((DATA / 'manual-review.json').read_text())
    assert review['source_sha256'] == sha(DATA / 'host.json')
    assert len(review['rows']) == 64 and {(r['model'], r['case']) for r in review['rows']} == expected_keys
    h = DATA / 'hardware'
    hp = json.loads((h / 'protocol.json').read_text())
    assert hp['parent_protocol_sha256'] == sha(DATA / 'protocol.json')
    assert hp['host_references_sha256'] == sha(DATA / 'host.json')
    direct = json.loads((h / 'direct.json').read_text())
    assert len(direct) == 64 and {(r['model'], r['case']) for r in direct} == expected_keys
    for row in direct:
        key, case = row['model'], row['case']
        result = verify((h / f'{key}-{case}.ndjson').read_bytes(), refs[key, case])
        assert result == {k: v for k, v in row.items() if k not in ['model', 'case', 'token_text_EOS_match']}
        assert row['kernel']['mode'] == 'tile4'
        assert row['kernel']['owner_core_mask'] == 2 and row['kernel']['helper_core_mask'] == 1
    for name in ['node-1', 'node-2']:
        verify((h / ('initial-control-' + name + '.ndjson')).read_bytes(), refs['talk2', 'Q1'])
    batches = json.loads((h / 'batches.json').read_text())
    assert len(batches) == 32
    for row in batches:
        key, block, mode = row['model'], row['block'], row['mode']
        jobs = json.loads((h / f'{key}-block-{block}-{mode}.json').read_text())
        assert len(jobs) == 2 and all(j['state'] == 'done' for j in jobs)
        actual_tokens, actual_chars = 0, 0
        for case, job in zip(['S1', 'S2'], jobs):
            ref = hp['benchmark_references'][key][case]
            done = verify(job['raw_ndjson'].encode(), ref)
            actual_tokens += done['output_tokens']
            actual_chars += len(ref['text'])
        assert actual_tokens == row['output_tokens'] and actual_chars == row['output_unicode_characters']
        elapsed = max(j['finished_ms'] for j in jobs) - min(j['created_ms'] for j in jobs)
        assert elapsed == row['elapsed_ms']
        assert abs(actual_tokens * 1000 / elapsed - row['output_tokens_per_s']) < 1e-10
        assert abs(actual_chars * 1000 / elapsed - row['output_characters_per_s']) < 1e-10
        targets = {j['target'] for j in jobs}
        assert 'local' in targets and len(targets) == (2 if mode == 'cluster' else 1)
        if mode == 'cluster':
            assert min(j['finished_ms'] for j in jobs) > max(j['started_ms'] for j in jobs)
    summary = json.loads((h / 'summary.json').read_text())
    for key in MODELS:
        pair = [r for r in batches if r['model'] == key]
        assert [(r['block'], r['mode']) for r in pair] == [(b, m) for b in range(1, 5) for m in (['local', 'cluster'] if b % 2 else ['cluster', 'local'])]
        loc = [r['elapsed_ms'] for r in pair if r['mode'] == 'local']
        cluster = [r['elapsed_ms'] for r in pair if r['mode'] == 'cluster']
        assert statistics.median(loc) == summary[key]['local_package_median_ms']
        assert statistics.median(cluster) == summary[key]['cluster_package_median_ms']
        assert statistics.median(a / b for a, b in zip(loc, cluster)) == summary[key]['paired_throughput_factor_median']
    final = json.loads((h / 'final-state.json').read_text())
    assert final['study_completed'] and final['peer_configured'] and final['queued'] == final['running'] == 0
    assert all(r['model_id'] == p['models']['talk2']['model_id'] and r['model_ready'] and not r['worker_busy'] and not r['restart_pending'] and not r['ota_pending'] for r in final['devices'].values())
    log = (ROOT / '.local/matched-tests-final.log').read_text('utf-8-sig')
    count = re.search(r'Ran (\d+) tests', log)
    assert count and re.search(r'^OK\s*$', log, re.M) and 'FAILED' not in log
    checks = json.loads((DATA / 'numerical-checks.json').read_text())
    assert len(checks) == 3 and all(c['maximum_absolute_error'] < .002 and c['argmax_equal'] and c['all_vocab_pieces_equal'] and c['all_16_prompt_encodings_equal'] for c in checks)
    write(DATA / 'validation.json', {
        'passed': True, 'unit_tests': int(count[1]), 'native_build': 'passed after device study released the DLL',
        'quality_outputs_checked': 64, 'direct_hardware_generations_checked': 64,
        'dispatched_hardware_jobs_checked': 64, 'initial_hardware_controls_checked': 2,
        'raw_clock_package_recalculations': 32, 'paired_blocks_per_model': 4,
        'model_specific_tokens_text_EOS_equal': True, 'dual_core_profile_checks': 64,
        'numerical_full_logit_vectors': 9, 'tokenizer_prompt_checks': 48,
        'restored_tinytalk2_both_and_peer_configured': True, 'no_queued_running_jobs': True,
        'earlier_environment_failure': 'Native rebuild while the long study process mapped tinyllm.dll returned permission denied; module inspection confirmed it was loaded. Original measured DLL preserved locally, hash matched frozen hardware protocol. Build deferred until process completion.',
        'publication_checker_correction': 'PNG text inspection loads Pillow pixels; CRC verification now occurs before reopening/loading metadata. Four tests cover preserved pixels/provenance, text metadata rejection, ICC rejection and binary destination restriction.',
        'new_model_asset_download_bytes': sum(f['bytes'] for r in json.loads((DATA / 'downloads.json').read_text()) for f in r['files']),
        'online_upload_performed_during_study': False,
        'limits': ['No independent quality evaluator, held-out/general-assistant test, independent Transformers execution, energy measurement or third physical node',
                   'Fixed model order; four timing repeats measure one fixed pair of prompts',
                   'TinyTalk 1 rain fragment counted generously under frozen literal rule; see review-revisions.json'],
        'source_sha256': {n: sha(DATA / n) for n in ['protocol.json', 'host.json', 'manual-review.json', 'quality-summary.json', 'hardware/protocol.json', 'hardware/direct.json', 'hardware/batches.json', 'hardware/summary.json', 'hardware/final-state.json']}})
    manifest = {p.relative_to(DATA).as_posix(): sha(p) for p in sorted(DATA.rglob('*')) if p.is_file() and p.name != 'sha256-manifest.json'}
    write(DATA / 'sha256-manifest.json', manifest)
    print(json.dumps({'passed': True, 'tests': int(count[1]), 'real_inferences_checked': 130, 'files_hashed': len(manifest)}))


if __name__ == '__main__':
    main()
