"""Offline evidence audit: no weights, native library, network or device access."""
import hashlib
import json
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/tinybrainbot-p4-2026-10-29'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def check_raw(raw, reference):
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    tokens = [r['token'] for r in rows if 'token' in r]
    text = b''.join(bytes.fromhex(r['bytes_hex']) for r in rows if 'token' in r).decode('utf-8')
    done = [r for r in rows if r.get('done')]
    assert len(done) == 1 and rows[-1] == done[0]
    d = done[0]
    assert tokens == reference['tokens'] and text == reference['text']
    assert d['eos'] is reference['eos'] and d['output_tokens'] == len(tokens)
    assert d['prompt_tokens'] == len(reference['prompt_tokens']) and d['boards'] == 2
    assert d['elapsed_ms'] > 0 and d['ttft_ms'] > 0
    return d


def main():
    p = read(DATA / 'protocol.json'); amendment = read(DATA / 'host-amendment.json')
    host = read(DATA / 'host-report.json'); install = read(DATA / 'installation-protocol.json')
    assert amendment['original_protocol_sha256'] == sha(DATA / 'protocol.json')
    assert amendment['source_correction_patch_sha256'] == sha(DATA / 'source-correction.patch')
    assert amendment['retained_generations_sha256'] == sha(DATA / 'host-generations.json')
    assert amendment['native_code_and_data_sections_identical'] is True
    for section, record in amendment['before_sections'].items():
        if section != '.buildid':
            assert record == amendment['after_sections'][section]
    assert amendment['final_code_sha256'] == host['code_sha256']
    for path, digest in host['code_sha256'].items():
        assert sha(ROOT / path) == digest, path
    assert install['trial_script_sha256'] == sha(ROOT / 'tools/tinybrainbot_p4_trial.py')
    assert install['host_report_sha256'] == sha(DATA / 'host-report.json')
    assert install['artifact_report_sha256'] == sha(DATA / 'model-artifacts.json')
    assert type(host['complete_generations']) is int and host['complete_generations'] == 30
    assert host['input_probes'] == 5031 and host['unicode_scalars_normalized'] == 1112063
    assert host['all_tokens_text_eos_equal'] and host['full_shard_kernel_logits_identical']
    assert host['context_boundary_checked'] and host['sequential_KV_positions_per_role'] == 256
    prior = ROOT / 'data/tinybrainbot-local-2026-10-29/answers-tinybrainbot-int4.json'
    assert p['prior_answer_sha256'] == sha(prior)
    old = {x['id']: x for x in read(prior)}
    generations = read(DATA / 'host-generations.json')
    assert len(generations) == 30
    for row in generations:
        for key in ['tokens', 'text', 'eos']:
            assert row[key] == old[row['case']][key]
    build = read(DATA / 'build-receipt.json')
    assert build['source_sha256'] == host['code_sha256'] and build['tests_passed'] == 81
    assert build['private_image_sha256'] == install['firmware_sha256']
    assert build['image_bytes'] == install['firmware_bytes'] == 806800
    artifacts = read(DATA / 'model-artifacts.json')
    for role in ['coordinator', 'worker']:
        assert artifacts[role] == p['artifacts'][role]
        assert artifacts[role]['compressed_bytes'] <= 24 * 1024**2
        assert artifacts[role]['model_id'] == install['new_model_id']
    assert artifacts['coordinator']['tokenizer_bytes'] == 1662968
    assert artifacts['worker']['tokenizer_bytes'] == 0
    refs = read(DATA / 'hardware-references.json'); checked = 0
    runs = read(DATA / 'p4-runs.json'); assert [r['case'] for r in runs] == p['hardware_cases']
    for r in runs:
        assert r['tokens_text_eos_equal'] is True
        assert check_raw((DATA / (r['case'] + '-p4.ndjson')).read_text(), refs[r['case']]) == r['done']
        checked += 1
    pair = read(DATA / 'dispatcher-pair.json'); assert len(pair) == 2
    for r, case in zip(pair, p['dispatch_cases']):
        assert r['state'] == 'done' and not r['error']
        check_raw(r['raw_ndjson'], refs[case]); checked += 1
    assert pair[1]['started_ms'] >= pair[0]['finished_ms'], 'Sharded jobs must use one lane'
    assert check_raw((DATA / 'U01-p4.ndjson').read_text(), refs['U01']) == read(DATA / 'unicode-control.json')
    checked += 1
    check_raw((DATA / 'same-image-ota-control.ndjson').read_text(), refs['T13']); checked += 1
    controls = read(DATA / 'firmware-controls.json'); assert len(controls) == 2
    for c in controls:
        assert c['old_two_board_control_equal'] is True
        assert check_raw((DATA / ('supra-control-after-' + c['updated'] + '-ota.ndjson')).read_text(), install['old_control']) == c['control']
    timing = read(DATA / 'timing.json'); assert len(timing) == 3
    for d in timing:
        assert d['boards'] == 2 and d['eos'] is True and d['output_tokens'] == 3 and d['prompt_tokens'] == 16
    latency = [x['elapsed_ms'] / 1000 for x in timing]
    long_host = read(DATA / 'long-input-host.json'); rejection = read(DATA / 'long-input-rejection.json')
    assert long_host['reference_token_count'] == long_host['native_host_token_count'] == 258 and long_host['exact_ids_equal']
    assert rejection['http'] == 400 and rejection['boot_and_model_unchanged'] is True
    assert rejection['input_token_count'] == 258  # Reference count; NOT read back from device.
    final = read(DATA / 'final.json')
    assert final['coordinator_boot_changed'] and final['same_image_ota_control_equal']
    assert final['cluster_mode'] == 'sharded' and final['queued'] == final['running'] == 0
    stages = {'cold_load': {x['role']: x['state'] for x in read(DATA / 'installation.json')},
              'after_study': read(DATA / 'device-memory-before-ota.json'),
              'after_encoder_stress': {'coordinator': rejection['after']}, 'final': final['devices']}
    for states in stages.values():
        for role, s in states.items():
            assert s['firmware'] == '0.7.0' and s['model_ready'] and s['model_id'] == install['new_model_id']
            assert s['artifact_id'] == artifacts[role]['artifact_id'] and s['role'] == (1 if role == 'coordinator' else 2)
            assert s['tokenizer'] == ('metaspace_bpe' if role == 'coordinator' else 'none')
            assert s['free_psram'] >= 512 * 1024 and not s['worker_busy'] and not s['ota_pending']
    for label in ['tinybrainbot-p4-setup', 'tinybrainbot-p4-acceptance']:
        metadata = read(ROOT / 'docs/figures' / (label + '-2026-10-29.json'))
        for path, digest in metadata['source_sha256'].items():
            assert sha(ROOT / path) == digest, path
    write(DATA / 'device-summary.json', {
        'new_model_generations_verified_at_runtime': 13,
        'new_model_complete_raw_records_offline_verified': checked,
        'timing_done_records': 3,
        'timing_raw_scope': 'Only done records retained for three timing repeats; exact equality asserted by frozen trial at runtime. Ten other new-model outputs retain complete raw token/byte/EOS records.',
        'old_model_firmware_controls_raw_verified': 2,
        'timing': {'case': 'T13', 'prompt_tokens': 16, 'output_tokens': 3, 'eos': True, 'repetitions': 3,
                   'seconds': latency, 'median_seconds': statistics.median(latency), 'min_seconds': min(latency), 'max_seconds': max(latency)},
        'long_input_device_observation': 'HTTP400; boot/model unchanged. Encoded count258 is host/reference evidence only.',
        'memory_stages': stages, 'scope': 'Two real P4s, one sharded lane. Correctness/fit and descriptive latency, no controlled model speedup or new quality ranking.'})
    sources = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(DATA.iterdir())
               if p.is_file() and p.name not in ['record-audit.json']}
    sources['tools/verify_tinybrainbot_p4.py'] = sha(pathlib.Path(__file__))
    write(DATA / 'record-audit.json', {'checks_passed': True, 'complete_raw_records_verified': checked + 2,
        'new_model_raw_records_verified': checked, 'host_complete_generations_checked': 30,
        'timing_done_records_checked': 3, 'source_sha256': sources,
        'scope': 'Offline records/source checks; no new inference, hardware or full-logit measurement.'})
    print('PASS 30 host continuations; 10 new + 2 old complete device streams; 3 timing receipts; flash/memory/OTA; source/amendment hashes')


if __name__ == '__main__':
    main()
