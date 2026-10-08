"""Prospective manual stages, immutable history and quota stops; disabled pending evidence."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
import math
from pathlib import Path

from .artifact_safety import stage_archive
from .chained_recovery import file_hashes
from .protocol import BENCHMARK_HASH, make_raw_record, parse_output, score_output
from .recovery import recovery_transport
from .providers import GoogleProvider
from .runner import _digest, _read, _write, execute_plan, plan_run
from .schema import ValidationError

MODEL='gemini-3.5-flash-lite'
CONFIG='configs/free_tier_pilot_v1.yaml'
POLICY='configs/free_tier_policy_v1.json'
PHASES={'connectivity':('post_update',[1]),'small_pilot':('post_update',list(range(2,6))),
        'remaining_post':('post_update',list(range(6,41))),'paired_pre':('pre_update',list(range(1,41)))}


def readiness(policy_path=POLICY, config_path=CONFIG):
    policy=json.loads(Path(policy_path).read_text())
    if policy.get('planned_requests') != 80 or any(policy['phases'].get(name) != {
            'condition':condition,'execution_indices':indices,'maximum_requests':len(indices)}
            for name,(condition,indices) in PHASES.items()):
        raise ValidationError('phase policy mismatch')
    if policy['model_id']!=MODEL or policy['provider']!='google' or policy['budget']['maximum_total_usd']!=4:
        raise ValidationError('candidate/budget identity mismatch')
    for k in ('execution_enabled','free_tier_verified','available_to_key_verified','generate_content_verified',
              'json_output_verified','parameter_support_verified'):
        if policy.get(k) is not True:
            raise ValidationError('candidate evidence unresolved; execution disabled')
    if policy['budget']['account_free_tier_eligibility_verified'] is not True:
        raise ValidationError('account billing/free-tier eligibility unresolved')
    if policy['controls']['further_live_implementation_review_required'] is not False:
        raise ValidationError('live implementation review unresolved')
    for name,digest in (('diagnostic_file','diagnostic_sha256'),('official_pricing_file','official_pricing_sha256'),
                        ('parameter_support_file','parameter_support_sha256'),('account_tier_file','account_tier_sha256')):
        if not policy['evidence'].get(name) or sha256(Path(policy['evidence'][name]).read_bytes()).hexdigest()!=policy['evidence'].get(digest):
            raise ValidationError('saved verification evidence missing or changed')
    diagnostic=json.loads(Path(policy['evidence']['diagnostic_file']).read_text())
    if (diagnostic.get('status')!='success' or diagnostic.get('requested_model')!='models/'+MODEL
            or diagnostic.get('target_listed') is not True or diagnostic.get('target_supports_generateContent') is not True
            or not any(m.get('name')=='models/'+MODEL and 'generateContent' in m.get('supported_methods',[])
                       for m in diagnostic.get('models',[]))):
        raise ValidationError('diagnostic does not prove candidate account availability')
    probe=plan_run(config_path,provider='google',model=MODEL)
    if probe.manifest['enabled_models']!=1 or probe.manifest['expected_request_count']!=80:
        raise ValidationError('candidate matrix is not enabled/compatible')
    observation=policy['evidence'].get('availability_verification',{})
    if (not observation.get('verification_date') or not observation.get('github_actions_run_url','')
            or not observation['github_actions_run_url'].startswith('https://github.com/ankitpanda226/revocable-flow/actions/runs/')):
        raise ValidationError('diagnostic observation date/run reference missing')
    parameters=json.loads(Path(policy['evidence']['parameter_support_file']).read_text())
    if (parameters.get('model_id')!=MODEL or not parameters.get('documentation_source')
            or not parameters.get('verification_date')
            or parameters.get('parameter_support')!=probe.manifest['model_matrix'][0]['parameter_support']):
        raise ValidationError('candidate-specific parameter evidence mismatch')
    tier=json.loads(Path(policy['evidence']['account_tier_file']).read_text())
    if (tier.get('tier')!='Free' or tier.get('model_id')!=MODEL or not tier.get('project_reference')
            or not tier.get('verification_date') or not tier.get('verification_basis')):
        raise ValidationError('project-specific Free-tier evidence missing')
    return policy


def stage_plan(phase,run_id,*,config=CONFIG):
    if phase not in PHASES: raise ValidationError('unknown campaign phase')
    condition,indices=PHASES[phase]
    plan=plan_run(config,run_id=run_id,provider='google',model=MODEL,max_provider_requests=80,max_attempts_per_request=1)
    m=plan.manifest
    m['requests']=[r for r in m['requests'] if r['condition']==condition and r['execution_index'] in indices]
    if len(m['requests'])!=len(indices): raise ValidationError('candidate unresolved or phase scope invalid')
    m['prompt_catalog']=[p for p in m['prompt_catalog'] if p['condition']==condition and p['execution_index'] in indices]
    m.update(expected_request_count=len(indices),expected_if_all_selected_enabled=len(indices),conditions=[condition],
             primary_complete_design=False,pilot_phase=phase,campaign_version='flash-lite-v1',
             execution_limits={'max_provider_requests':len(indices),'max_attempts_per_request':1,
                              'stop_on_http_statuses':[429],'stop_after_consecutive_http_503':2,'stop_on_ambiguous':True})
    m.pop('manifest_hash');m['manifest_hash']=_digest(m)
    return plan


def validate_history(history,phase,*,config=CONFIG):
    expected_phases=list(PHASES)[:list(PHASES).index(phase)]
    if not expected_phases:
        if history is not None: raise ValidationError('connectivity must start a new reviewed campaign')
        return {}
    if history is None: raise ValidationError('prior complete stages required')
    root=Path(history)
    manifests=list((root/'manifests').glob('*.json'))
    if len(manifests)!=len(expected_phases):raise ValidationError('history stage count mismatch')
    found={}
    for path in manifests:
        m=_read(root,path.relative_to(root).as_posix());current=deepcopy(m);digest=current.pop('manifest_hash')
        if _digest(current)!=digest or m['pilot_phase'] in found:raise ValidationError('history hash/duplicate phase mismatch')
        found[m['pilot_phase']]=m
    if set(found)!=set(expected_phases):raise ValidationError('history phase mismatch')
    cumulative={}
    for prior_phase in expected_phases:
        m=found[prior_phase];run_id=m['run_id'];expected=stage_plan(prior_phase,run_id,config=config).manifest
        for key in ('commit','git_dirty','python_version','manifest_hash','campaign_history_hashes','budget_review','pilot_policy_hash','pilot_policy_bytes_utf8'):
            expected.pop(key,None)
        actual=deepcopy(m)
        if actual.get('git_dirty') is not False or not actual.get('commit'):raise ValidationError('history execution provenance invalid')
        if sha256(m.get('pilot_policy_bytes_utf8','').encode()).hexdigest()!=m.get('pilot_policy_hash'):
            raise ValidationError('history policy bytes/hash mismatch')
        for key in ('commit','git_dirty','python_version','manifest_hash','campaign_history_hashes','budget_review','pilot_policy_hash','pilot_policy_bytes_utf8'):
            actual.pop(key,None)
        if actual!=expected or m.get('campaign_history_hashes')!=cumulative:
            raise ValidationError('history experiment/ancestor chain mismatch')
        prior_plan=stage_plan(prior_phase,run_id,config=config)
        if ((root/m['benchmark_artifact']).read_bytes()!=prior_plan.benchmark_bytes
                or (root/m['benchmark_metadata_artifact']).read_bytes()!=prior_plan.metadata_bytes):
            raise ValidationError('history benchmark copy mismatch')
        summary_files=list((root/f'summaries/{run_id}').glob('completion-*.json'))
        if len(summary_files)!=1:raise ValidationError('history completion missing/ambiguous')
        summary=_read(root,summary_files[0].relative_to(root).as_posix())
        if (summary.get('manifest_hash')!=m['manifest_hash'] or summary.get('complete') is not True
                or summary.get('completed')!=m['expected_request_count'] or summary.get('ambiguous_attempts')
                or summary.get('infrastructure_missing') or summary.get('unattempted_requests')
                or summary.get('attempted_provider_requests')!=m['expected_request_count']):
            raise ValidationError('prior phase incomplete/ambiguous; no automatic replay')
        for r in m['requests']:
            key=r['request_key'];prefix=f'raw/{run_id}/{key}/attempt-01'
            started=_read(root,prefix+'.started.json');record=_read(root,prefix+'.response.json')
            prompt=next(p for p in m['prompt_catalog'] if p['execution_index']==r['execution_index'])
            if any(started.get(k)!=v for k,v in {**r,'attempt':1,'manifest_hash':m['manifest_hash'],'messages':prompt['messages']}.items()):
                raise ValidationError('history request provenance mismatch')
            if record.get('provider_error') is not None or record.get('manifest_hash')!=m['manifest_hash'] or record.get('requested_model')!=MODEL:
                raise ValidationError('history model/provenance mismatch')
            support=m['model_matrix'][0]['parameter_support']
            effective={k:v for k,v in r['parameters'].items() if support[k]=='supported'}
            unsupported=sorted(k for k in r['parameters'] if support[k]!='supported')
            if record.get('requested_parameters')!=r['parameters'] or record.get('effective_parameters')!=effective or record.get('unsupported_parameters')!=unsupported:
                raise ValidationError('history requested/effective parameter mismatch')
            scenario=prior_plan.scenarios[r['execution_index']-1]
            reproduced=make_raw_record(scenario=scenario,raw_output=record['raw_output'],execution_index=r['execution_index'],
                provider='google',model=MODEL,timestamp=record['timestamp'],condition=r['condition'],parameters=record['parameters'],
                latency_ms=record['latency_ms'],request_id=record['request_id'])
            if any(record.get(k)!=v for k,v in reproduced.items()):raise ValidationError('history raw metadata mismatch')
            parsed=parse_output(record['raw_output'],scenario)
            saved={'request_key':key,'manifest_hash':m['manifest_hash'],'raw_hash':_digest(record),'score':asdict(score_output(scenario,r['condition'],parsed))}
            if _read(root,f'parsed/{run_id}/{key}.json')!=saved:raise ValidationError('history saved score mismatch')
        paths={f'manifests/{run_id}.json':path for path in manifests if path.name==run_id+'.json'}
        for section in ('raw','parsed','summaries'):
            paths.update({p.relative_to(root).as_posix():p for p in (root/section/run_id).rglob('*') if p.is_file()})
        allowed={f'manifests/{run_id}.json',m['benchmark_artifact'],m['benchmark_metadata_artifact'],
                 f'parsed/{run_id}/analysis_index.json',f'summaries/{run_id}/dispatch-audit.json',
                 summary_files[0].relative_to(root).as_posix()}
        for request in m['requests']:
            key=request['request_key']
            allowed.update(f'raw/{run_id}/{key}/attempt-01.{kind}.json' for kind in ('started','response'))
            allowed.add(f'parsed/{run_id}/{key}.json')
        if set(paths)!=allowed or summary_files[0].name!=f'completion-{_digest(summary)[:16]}.json':
            raise ValidationError('unexpected history claims/files')
        expected_index=[{'execution_index':i,'scenario_id':s.scenario_id,'family_id':s.family_id,
                         'expected_action':s.expected_action.value,'pre_update_expected_action':s.pre_update_expected_action.value}
                        for i,s in enumerate(prior_plan.scenarios,1)]
        if _read(root,f'parsed/{run_id}/analysis_index.json')!=expected_index:
            raise ValidationError('history analysis mapping mismatch')
        audit={'manifest_hash':m['manifest_hash'],'maximum_new_requests':len(m['requests']),
               'attempted':len(m['requests']),'phase':prior_phase,'campaign_history_hashes':cumulative}
        if _read(root,f'summaries/{run_id}/dispatch-audit.json')!=audit:
            raise ValidationError('history dispatch audit mismatch')
        cumulative.update({name:sha256(p.read_bytes()).hexdigest() for name,p in paths.items()})
    if file_hashes(root)!=cumulative:raise ValidationError('unexpected history files or claims')
    return cumulative


def execute_stage(phase,run_id,*,history=None,reviewed_spend=None,approved=False,config=CONFIG,policy=POLICY,adapters=None,expected_previous_commit=None):
    readiness(policy,config)
    if approved is not True or type(reviewed_spend) not in (int,float) or not math.isfinite(reviewed_spend) or not 0<=reviewed_spend<4:
        raise ValidationError('explicit stage approval and verified cumulative spend below $4 required')
    plan=stage_plan(phase,run_id,config=config)
    ancestors=validate_history(history,phase,config=config)
    policy_bytes=Path(policy).read_text()
    if history is not None:
        previous_phase=list(PHASES)[list(PHASES).index(phase)-1]
        prior_manifests=[_read(Path(history),p.relative_to(Path(history)).as_posix()) for p in (Path(history)/'manifests').glob('*.json')]
        immediate=next(m for m in prior_manifests if m['pilot_phase']==previous_phase)
        if not expected_previous_commit or immediate['commit']!=expected_previous_commit:
            raise ValidationError('previous manifest commit differs from verified GitHub run')
        for path in (Path(history)/'manifests').glob('*.json'):
            prior=_read(Path(history),path.relative_to(Path(history)).as_posix())
            if prior['pilot_policy_hash']!=sha256(policy_bytes.encode()).hexdigest():
                raise ValidationError('campaign policy changed between stages')
    plan.manifest.update(campaign_history_hashes=ancestors,budget_review={'reviewed_cumulative_spend_usd':reviewed_spend,'maximum_total_usd':4,
                        'price_guarantee':False,'estimated_stage_cost_usd':None},
                         pilot_policy_hash=sha256(policy_bytes.encode()).hexdigest(),pilot_policy_bytes_utf8=policy_bytes)
    plan.manifest.pop('manifest_hash');plan.manifest['manifest_hash']=_digest(plan.manifest)
    summary=execute_plan(plan,execute_live=True,adapters=adapters or {'google':GoogleProvider(transport=recovery_transport)})
    _write(plan.root,f'summaries/{run_id}/dispatch-audit.json',{'manifest_hash':plan.manifest['manifest_hash'],
           'maximum_new_requests':len(plan.manifest['requests']),'attempted':summary['attempted_provider_requests'],
           'phase':phase,'campaign_history_hashes':ancestors})
    return plan,summary


def stage_campaign(history,results,run_id,destination):
    results=Path(results);destination=Path(destination)
    m=_read(results,f'manifests/{run_id}.json')
    if destination.exists():raise ValidationError('campaign archive exists')
    if history is not None:
        if file_hashes(history)!=m['campaign_history_hashes']:raise ValidationError('history changed after dispatch')
        for path in (Path(history)/'manifests').glob('*.json'):
            prior=_read(Path(history),path.relative_to(Path(history)).as_posix())
            # Each run copied into a distinct scratch archive, then combined using exclusive writes.
            import tempfile
            with tempfile.TemporaryDirectory() as scratch:
                staged=Path(scratch)/'safe'
                stage_archive(history,prior['run_id'],staged,pilot_phase=prior['pilot_phase'])
                for p in staged.rglob('*'):
                    if p.is_file():
                        target=destination/p.relative_to(staged);target.parent.mkdir(parents=True,exist_ok=True)
                        with target.open('xb') as stream:stream.write(p.read_bytes())
    import tempfile
    with tempfile.TemporaryDirectory() as scratch:
        staged=Path(scratch)/'safe';stage_archive(results,run_id,staged,pilot_phase=m['pilot_phase'])
        for p in staged.rglob('*'):
            if p.is_file():
                target=destination/p.relative_to(staged);target.parent.mkdir(parents=True,exist_ok=True)
                with target.open('xb') as stream:stream.write(p.read_bytes())
