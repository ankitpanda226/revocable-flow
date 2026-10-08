"""One final, opt-in request from a validated original + first-recovery chain."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import re

from .artifact_safety import stage_archive
from .protocol import make_raw_record, parse_output, score_output
from .recovery import prepare
from .runner import RunPlan, _digest, _read, plan_run
from .schema import ValidationError


def file_hashes(root):
    root = Path(root)
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValidationError("source symlinks forbidden")
    hashes = {}
    for p in root.rglob('*'):
        if p.is_symlink():
            raise ValidationError("source symlinks forbidden")
        if p.is_file():
            hashes[p.relative_to(root).as_posix()] = sha256(p.read_bytes()).hexdigest()
    return hashes


def preserve_bundle(source, source_id, destination):
    """Copy approved ancestor files exclusively; no content executed or normalized."""
    source, destination = Path(source), Path(destination)
    if not re.fullmatch(r"gh-gemini-recovery-[1-9][0-9]*-1", source_id):
        raise ValidationError("source must be a first recovery")
    if destination.exists():
        raise ValidationError("preserved destination already exists")
    first = _read(source/'recovery', f'manifests/{source_id}.json')
    stage_archive(source/'source', first['recovery']['source_run_id'], destination/'source')
    stage_archive(source/'recovery', source_id, destination/'recovery', recovery=True)


def _validate_layout(root, manifest, successful_indices, *, audit=False):
    run_id = manifest['run_id']
    summaries = list((root/f'summaries/{run_id}').glob('completion-*.json'))
    if len(summaries) != 1:
        raise ValidationError('ambiguous completion history')
    expected = {f'manifests/{run_id}.json',manifest['benchmark_artifact'],
                manifest['benchmark_metadata_artifact'],f'parsed/{run_id}/analysis_index.json',
                summaries[0].relative_to(root).as_posix()}
    if audit:
        expected.add(f'summaries/{run_id}/dispatch-audit.json')
    for r in manifest['requests']:
        key = r['request_key']
        expected.update(f'raw/{run_id}/{key}/attempt-01.{kind}.json' for kind in ('started','response'))
        if r['execution_index'] in successful_indices:
            expected.add(f'parsed/{run_id}/{key}.json')
    if set(file_hashes(root)) != expected:
        raise ValidationError('unexpected, missing or ambiguous attempt files')


def _validate_response(root, manifest, request, scenario, *, success):
    run_id, key = manifest['run_id'], request['request_key']
    prefix = f'raw/{run_id}/{key}/attempt-01'
    started = _read(root, prefix+'.started.json')
    record = _read(root, prefix+'.response.json')
    prompt = next(p for p in manifest['prompt_catalog'] if p['execution_index'] == request['execution_index'])
    expected_started = {**request, 'attempt': 1, 'manifest_hash': manifest['manifest_hash'], 'messages': prompt['messages']}
    if any(started.get(k) != v for k,v in expected_started.items()):
        raise ValidationError('first recovery started provenance mismatch')
    expected = {'provider':'google', 'requested_model':'gemini-3.8-flash', 'condition':'post_update',
                'attempt':1, 'manifest_hash':manifest['manifest_hash'], 'messages':prompt['messages'],
                'execution_index':request['execution_index'], 'prompt_hash':request['prompt_hash'],
                'requested_parameters':request['parameters'],
                'effective_parameters':manifest['provider_checks'][0]['effective_parameters'],
                'benchmark_hash':manifest['benchmark']['hash'], 'benchmark_version':'0.2',
                'benchmark_commit':manifest['benchmark']['commit']}
    if any(record.get(k) != v for k,v in expected.items()):
        raise ValidationError('first recovery response provenance mismatch')
    parsed_path = f'parsed/{run_id}/{key}.json'
    if success:
        parsed = parse_output(record['raw_output'], scenario)
        if record.get('provider_error') is not None or not parsed.valid:
            raise ValidationError('first recovery index 1 must have a valid terminal model response')
        reproduced = make_raw_record(scenario=scenario, raw_output=record['raw_output'],
            execution_index=request['execution_index'], provider='google', model=request['model'],
            timestamp=record['timestamp'], condition='post_update', parameters=record['parameters'],
            latency_ms=record['latency_ms'], request_id=record['request_id'],
            unsupported_parameters=tuple(k for k in record['unsupported_parameters'] if k in {'temperature','top_p'}))
        if any(record.get(k) != v for k,v in reproduced.items()):
            raise ValidationError('successful response parse metadata mismatch')
        saved = {'request_key':key, 'manifest_hash':manifest['manifest_hash'], 'raw_hash':_digest(record),
                 'score':asdict(score_output(scenario,'post_update',parsed))}
        if _read(root, parsed_path) != saved:
            raise ValidationError('successful response scoring mismatch')
    else:
        error = record.get('provider_error') or {}
        if (record.get('parse_status') != 'provider_error' or error.get('category') != 'http_error'
                or error.get('http_status') != 503 or error.get('retryable') is not True
                or record.get('raw_output') is not None or record.get('parsed_output') is not None
                or (root/parsed_path).exists()):
            raise ValidationError('index 2 is not a confirmed HTTP 503 failure')
        delay = error.get('retry_after_seconds') or 0
        age = (datetime.now(timezone.utc)-datetime.fromisoformat(record['timestamp'])).total_seconds()
        if delay > age:
            raise ValidationError('provider Retry-After has not expired')


def prepare_chained(source, source_id, source_commit, run_id, *, config='configs/pilot_eval.yaml'):
    source = Path(source)
    if not re.fullmatch(r'gh-gemini-recovery-[1-9][0-9]*-1', source_id):
        raise ValidationError('only first-recovery artifacts are accepted')
    if not isinstance(source_commit,str) or not re.fullmatch(r'[0-9a-f]{40}',source_commit):
        raise ValidationError('invalid first-recovery commit')
    first = _read(source/'recovery', f'manifests/{source_id}.json')
    identity = deepcopy(first); digest = identity.pop('manifest_hash')
    if _digest(identity) != digest or first['commit'] != source_commit or first['git_dirty'] is not False:
        raise ValidationError('first-recovery manifest hash/commit mismatch')
    lineage = first['recovery']
    original = _read(source/'source',f"manifests/{lineage['source_run_id']}.json")
    _validate_layout(source/'source',original,{3})
    _validate_layout(source/'recovery',first,{1},audit=True)
    # Reuse complete original validation and reproduce the expected first-recovery plan.
    expected_plan = prepare(source/'source', lineage['source_run_id'], lineage['source_commit'], source_id, config=config)
    expected = deepcopy(expected_plan.manifest)
    for field in ('commit','git_dirty','python_version','manifest_hash'):
        identity.pop(field,None); expected.pop(field,None)
    if identity != expected or file_hashes(source/'source') != lineage['source_file_hashes']:
        raise ValidationError('original-to-first-recovery chain mismatch')
    first_root = source/'recovery'
    if ((first_root/first['benchmark_artifact']).read_bytes() != expected_plan.benchmark_bytes
            or (first_root/first['benchmark_metadata_artifact']).read_bytes() != expected_plan.metadata_bytes):
        raise ValidationError('first-recovery benchmark copies mismatch')
    for request in first['requests']:
        _validate_response(first_root,first,request,expected_plan.scenarios[request['execution_index']-1],
                           success=request['execution_index']==1)
    summaries = list((first_root/f'summaries/{source_id}').glob('completion-*.json'))
    expected_summary = {'manifest_hash':digest,'planned':2,'completed':1,
        'infrastructure_missing':[first['requests'][1]['request_key']], 'ambiguous_attempts':[],
        'complete':False,'primary_complete_design':False,'attempted_provider_requests':2,
        'execution_limits':first['execution_limits']}
    if len(summaries)!=1 or _read(first_root,str(summaries[0].relative_to(first_root)))!=expected_summary or summaries[0].name!=f'completion-{_digest(expected_summary)[:16]}.json':
        raise ValidationError('first-recovery completion history mismatch')
    audit = {'manifest_hash':digest,'source_manifest_hash':lineage['source_manifest_hash'],
             'maximum_new_requests':2,'new_requests_attempted':2,'retry_indices':[1,2],'preserved_index':3}
    if _read(first_root,f'summaries/{source_id}/dispatch-audit.json') != audit:
        raise ValidationError('first-recovery dispatch audit mismatch')
    expected_index = [{"execution_index":i,"scenario_id":s.scenario_id,"family_id":s.family_id,
                       "expected_action":s.expected_action.value,"pre_update_expected_action":s.pre_update_expected_action.value}
                      for i,s in enumerate(expected_plan.scenarios,1)]
    if _read(first_root,f'parsed/{source_id}/analysis_index.json') != expected_index:
        raise ValidationError('first-recovery analysis mapping mismatch')
    fresh = plan_run(config,run_id=run_id,provider='google',model='gemini-3.8-flash',
                     condition='post_update',scenario_limit=3,max_provider_requests=3,max_attempts_per_request=1)
    if fresh.config['retry']['max_attempts'] != 3:
        raise ValidationError('third trial dispatch must fit frozen attempt limit')
    m=fresh.manifest
    m.update(requests=[m['requests'][1]],prompt_catalog=[m['prompt_catalog'][1]],
             expected_request_count=1,expected_if_all_selected_enabled=1,selected_execution_indices=[2],
             execution_limits={'max_provider_requests':1,'max_attempts_per_request':1},
             recovery={'source_run_id':source_id,'source_commit':source_commit,'source_manifest_hash':digest,
                 'original_run_id':lineage['source_run_id'],'original_commit':lineage['source_commit'],
                 'original_manifest_hash':lineage['source_manifest_hash'],'source_file_hashes':file_hashes(source),
                 'retry_indices':[2],'preserved_indices':[1,3],'source_failure_status':503,'maximum_new_requests':1,
                 'prior_trial_attempts':{'1':2,'2':2,'3':1},'next_trial_attempt':3})
    m.pop('manifest_hash'); m['manifest_hash']=_digest(m)
    if (fresh.root/f'manifests/{run_id}.json').exists():
        raise ValidationError('chained recovery exists; replay forbidden')
    # Keep all three scenarios for existing runner's execution_index-1 scorer lookup.
    return RunPlan(m,fresh.scenarios,fresh.root,fresh.config,fresh.benchmark_bytes,fresh.metadata_bytes)


def stage_chained_upload(preserved, source_id, results, run_id, destination):
    manifest = _read(Path(results),f'manifests/{run_id}.json')
    if file_hashes(preserved) != manifest['recovery']['source_file_hashes']:
        raise ValidationError('ancestor artifacts changed')
    preserve_bundle(preserved,source_id,Path(destination))
    stage_archive(results,run_id,Path(destination)/'chained_recovery',chained=True)
