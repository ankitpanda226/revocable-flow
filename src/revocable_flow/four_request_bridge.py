"""Immutable source-to-ledger bridge and fixed four-request manual scope."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
import math
import os
from pathlib import Path

from .artifact_safety import stage_archive
from .chained_recovery import file_hashes
from .compatibility_probe import PARAMETERS, authorize
from .free_tier_campaign import CONFIG, MODEL, PHASES, POLICY
from .loader import load_scenarios
from .protocol import BENCHMARK_HASH, build_messages, make_raw_record, parse_output, score_output
from .providers import GoogleProvider
from .recovery import recovery_transport
from .runner import _digest, _read, _write, execute_plan, plan_run
from .schema import ValidationError

SCOPE='configs/flash_lite_next_four_v1.json'
CONTINUATION_SCOPE='configs/flash_lite_requests_006_009_v1.json'
NEXT_SCOPE='configs/flash_lite_requests_010_013_v1.json'


def require(ok,message):
    if not ok:raise ValidationError(message)


def load_scope(path=SCOPE):
    s=json.loads(Path(path).read_text())
    versions={'flash-lite-next-four-v1':[2,3,4,5],'flash-lite-next-four-v2':[6,7,8,9],
              'flash-lite-next-four-v3':[10,11,12,13]}
    require(s['version'] in versions,'unsupported fixed scope')
    second=s['version']!='flash-lite-next-four-v1'
    require((s['provider'],s['model'],s['phase'],s['condition'],s['execution_indices'],
             s['maximum_new_requests'],s['max_attempts_per_request'],s['maximum_total_research_budget_usd'],
             s['next_phases_enabled'])==('google',MODEL,'remaining_post_slice' if second else 'small_pilot',
                                        'post_update',versions[s['version']],4,1,4,False),
            'four-request scope changed')
    require(s['version'] in versions and s['maximum_authorized_paid_cost_usd']==0,
            'scope version or paid-spending gate changed')
    return s


def bridge(source,*,config=CONFIG,scope=SCOPE):
    source=Path(source);pin=load_scope(scope);source_hashes=file_hashes(source)
    require(source_hashes==pin['source_file_hashes'],'source missing/extra/changed files')
    if pin['version']!='flash-lite-next-four-v1':
        return continuation_bridge(source,pin,config=config)
    m=_read(source,f"manifests/{pin['source_run_id']}.json");identity=deepcopy(m);digest=identity.pop('manifest_hash')
    require(_digest(identity)==digest==pin['source_manifest_hash'],'source manifest hash mismatch')
    require(m['run_id']==pin['source_run_id'] and m['commit']==pin['source_commit'] and m['git_dirty'] is False,
            'source execution identity mismatch')
    require(sha256(Path(config).read_bytes()).hexdigest()==m['config_hash']==pin['source_config_hash'],
            'configuration changed since source')
    require(m['config_bytes_utf8'].encode()==Path(config).read_bytes() and json.loads(m['config_bytes_utf8'])==m['configuration'],
            'source config bytes mismatch')
    require(m['expected_request_count']==1 and len(m['requests'])==1 and
            m['execution_limits']=={'max_provider_requests':1,'max_attempts_per_request':1} and
            m['experiment_kind']=='isolated_flash_lite_compatibility_v1','source is not one isolated trial')
    authorize(m['compatibility_probe']['owner_approvals'])
    schedule=plan_run(config,provider='google',model=MODEL)
    require(schedule.config['models']==[] and schedule.manifest['model_matrix'][0]['status']=='disabled',
            'broader pilot must remain disabled')
    require(schedule.config['execution']['repetitions']==1 and schedule.manifest['generation_parameters']==PARAMETERS,
            'frozen generation settings changed')
    source_request=m['requests'][0];key=source_request['request_key'];run_id=m['run_id']
    require(source_request['provider']=='google' and source_request['model']==MODEL and
            source_request['execution_index']==1 and source_request['condition']=='post_update' and
            key=='model-01/post_update/001' and source_request['parameters']==PARAMETERS,'source request mismatch')
    scenario=schedule.scenarios[0];messages=build_messages(scenario,'post_update')
    require(m['scenario_order']==[{'execution_index':1,'scenario_id':scenario.scenario_id}] and
            m['prompt_catalog']==[{'execution_index':1,'condition':'post_update','messages':messages,'prompt_hash':_digest(messages)}]
            and source_request['prompt_hash']==_digest(messages),'source scenario/prompt mapping mismatch')
    require((source/m['benchmark_artifact']).read_bytes()==schedule.benchmark_bytes and
            sha256(schedule.benchmark_bytes).hexdigest()==BENCHMARK_HASH and
            (source/m['benchmark_metadata_artifact']).read_bytes()==schedule.metadata_bytes,'frozen benchmark copy mismatch')
    started=_read(source,f'raw/{run_id}/{key}/attempt-01.started.json')
    require(all(started.get(k)==v for k,v in {**source_request,'attempt':1,'manifest_hash':digest,'messages':messages}.items()),
            'source started request mismatch')
    raw_path=f'raw/{run_id}/{key}/attempt-01.response.json';raw=_read(source,raw_path)
    require(raw.get('provider_error') is None and raw['attempt']==1 and raw['manifest_hash']==digest and
            raw['requested_model']==raw['reported_model']==MODEL and raw['unsupported_parameters']==[] and
            raw['requested_parameters']==raw['effective_parameters']==raw['parameters']==PARAMETERS,'source terminal response mismatch')
    reproduced=make_raw_record(scenario=scenario,raw_output=raw['raw_output'],execution_index=1,provider='google',model=MODEL,
        timestamp=raw['timestamp'],condition='post_update',parameters=PARAMETERS,latency_ms=raw['latency_ms'],request_id=raw['request_id'])
    require(all(raw.get(k)==v for k,v in reproduced.items()),'source raw/parse mismatch')
    score=asdict(score_output(scenario,'post_update',parse_output(raw['raw_output'],scenario)))
    parsed_path=f'parsed/{run_id}/{key}.json';parsed=_read(source,parsed_path)
    require(parsed=={'request_key':key,'manifest_hash':digest,'raw_hash':_digest(raw),'score':score},'source score/hash mismatch')
    completion_paths=list((source/f'summaries/{run_id}').glob('completion-*.json'))
    require(len(completion_paths)==1,'source completion missing/ambiguous')
    completion=_read(source,completion_paths[0].relative_to(source).as_posix())
    require(completion_paths[0].name==f'completion-{_digest(completion)[:16]}.json' and
            completion['manifest_hash']==digest and completion['complete'] is True and completion['completed']==1 and
            completion['attempted_provider_requests']==1 and not completion['ambiguous_attempts'] and
            not completion['infrastructure_missing'],'source attempt not terminal')
    audit=_read(source,f'summaries/{run_id}/dispatch-audit.json')
    body=json.dumps(GoogleProvider().payload(messages,MODEL,PARAMETERS)).encode()
    require(audit['manifest_hash']==digest and audit['provider_calls_entered']==1 and audit['attempted']==1 and
            audit['http_status']==200 and audit['automatic_retries']==0 and audit['followup_workflow_dispatches']==0 and
            audit['transport_outcome_uncertain'] is False and audit['payload_sha256']==sha256(body).hexdigest(),
            'source dispatch audit mismatch')
    ledger=[{'identity':{'provider':'google','model':MODEL,'scenario_id':scenario.scenario_id,
                       'condition':'post_update','repetition':1},'execution_index':1,'request_key':key,
             'status':'terminal_completed','primary_parse_status':raw['parse_status'],
             'primary_validation_errors':raw['parse_errors'],
             'source_run_id':run_id,'source_manifest_hash':digest,'prompt_hash':_digest(messages),
             'raw_record_path':raw_path,'raw_record_canonical_hash':_digest(raw),
             'raw_text_sha256':sha256(raw['raw_output'].encode()).hexdigest(),
             'primary_score_record_path':parsed_path,'primary_score_record_sha256':source_hashes[parsed_path],
             'primary_score':score}]
    campaign_policy=json.loads(Path(POLICY).read_text())
    require(campaign_policy['execution_enabled'] is False and campaign_policy['phases']['small_pilot']=={
        'condition':PHASES['small_pilot'][0],'execution_indices':PHASES['small_pilot'][1],'maximum_requests':4},
        'frozen schedule or campaign disabled gate changed')
    completed={_digest(item['identity']) for item in ledger};eligible=[]
    for condition,indices in PHASES.values():
        for index in indices:
            s=schedule.scenarios[index-1]
            item={'provider':'google','model':MODEL,'scenario_id':s.scenario_id,'condition':condition,'repetition':1}
            if _digest(item) not in completed:
                eligible.append({'identity':item,'execution_index':index,
                    'request_key':f'model-01/{condition}/{index:03d}','prompt_hash':_digest(build_messages(s,condition))})
    proposed=eligible[:4]
    require(len(proposed)==4 and [r['execution_index'] for r in proposed]==pin['execution_indices'] and
            all(r['identity']['condition']==pin['condition'] for r in proposed),'next eligible schedule mismatch')
    result={'bridge_version':1,'benchmark_hash':BENCHMARK_HASH,'model':MODEL,'condition':'post_update',
            'source_github_run_id':pin['source_github_run_id'],'source_attempt':pin['source_attempt'],
            'source_manifest_hash':digest,'source_file_hashes':source_hashes,'ledger':ledger,
            'next_requests':proposed,'maximum_new_requests':4,'max_attempts_per_request':1,
            'later_phases_enabled':False,'exploratory_analysis_in_primary':False}
    result['bridge_hash']=_digest(result)
    return result,schedule


def continuation_bridge(source,pin,*,config=CONFIG):
    """Recursively validate fixed predecessor chains without rewriting source files."""
    version=2 if pin['version']=='flash-lite-next-four-v2' else 3
    predecessor_scope=SCOPE if version==2 else CONTINUATION_SCOPE
    previous_indices=[2,3,4,5] if version==2 else [6,7,8,9]
    preserved=5 if version==2 else 9
    prior,schedule=bridge(source/'source',config=config,scope=predecessor_scope)
    m=_read(source/'batch',f"manifests/{pin['source_run_id']}.json")
    unsigned=deepcopy(m);digest=unsigned.pop('manifest_hash')
    require(_digest(unsigned)==digest==pin['source_manifest_hash'] and m['commit']==pin['source_commit'] and
            m['git_dirty'] is False and m['provenance_bridge']==prior and
            prior['bridge_hash']==pin['source_bridge_hash'],'previous batch provenance mismatch')
    expected=prepare(source/'source',m['run_id'],m['owner_approvals'],config=config,scope=predecessor_scope,
                     _source_validation=True).manifest
    # Host runtime metadata is evidence, not an experimental setting.
    for key in ('commit','git_dirty','python_version'):expected[key]=m[key]
    expected.pop('manifest_hash')
    require(_digest(expected)==digest,'previous batch manifest does not reproduce')
    import tempfile
    with tempfile.TemporaryDirectory() as scratch:
        archive(source/'source',source/'batch',m['run_id'],Path(scratch)/'verified')
    ledger_record=_read(source/'batch',f"summaries/{m['run_id']}/campaign-ledger.json")
    ledger=ledger_record['ledger']
    require(len(ledger)==preserved and [r['execution_index'] for r in ledger]==list(range(1,preserved+1)) and
            all(r['status']=='terminal_completed' for r in ledger),'uncertain, failed, or duplicate previous attempt')
    audit=_read(source/'batch',f"summaries/{m['run_id']}/dispatch-audit.json")
    require(audit['manifest_hash']==digest and audit['bridge_hash']==prior['bridge_hash'] and
            audit['maximum_new_requests']==4 and audit['provider_calls_entered']==4 and
            audit['automatic_retries']==0 and audit['followup_workflow_dispatches']==0 and
            audit['runner_terminated_normally'] is True and
            [o['execution_index'] for o in audit['observations']]==previous_indices, 'previous dispatch audit mismatch')
    for request,observation in zip(m['requests'],audit['observations']):
        index=request['execution_index'];scenario=schedule.scenarios[index-1]
        messages=build_messages(scenario,'post_update')
        require(observation['http_status']==200 and observation['transport_exception_type'] is None and
                observation['requested_model']==MODEL and observation['payload_sha256']==
                sha256(json.dumps(GoogleProvider().payload(messages,MODEL,PARAMETERS)).encode()).hexdigest(),
                'previous request HTTP/wire audit mismatch')
        raw=_read(source/'batch',f"raw/{m['run_id']}/{request['request_key']}/attempt-01.response.json")
        require(raw['requested_model']==raw['reported_model']==MODEL and raw['unsupported_parameters']==[] and
                raw['requested_parameters']==raw['effective_parameters']==raw['parameters']==PARAMETERS,
                'previous response model/parameter mismatch')
        reproduced=make_raw_record(scenario=scenario,raw_output=raw['raw_output'],execution_index=index,
            provider='google',model=MODEL,timestamp=raw['timestamp'],condition='post_update',parameters=PARAMETERS,
            latency_ms=raw['latency_ms'],request_id=raw['request_id'])
        require(all(raw.get(k)==v for k,v in reproduced.items()),'previous response does not reproduce')
    paths=list((source/'batch'/f"summaries/{m['run_id']}").glob('completion-*.json'))
    require(len(paths)==1,'previous completion missing/ambiguous')
    summary=_read(source/'batch',paths[0].relative_to(source/'batch').as_posix())
    require(paths[0].name==f'completion-{_digest(summary)[:16]}.json' and summary['manifest_hash']==digest and
            summary['complete'] is True and summary['completed']==summary['attempted_provider_requests']==4 and
            not summary['ambiguous_attempts'] and not summary['infrastructure_missing'] and
            not summary['unattempted_requests'],'previous run incomplete/ambiguous')
    attempted={_digest(r['identity']) for r in ledger};eligible=[]
    for condition,indices in PHASES.values():
        for index in indices:
            scenario=schedule.scenarios[index-1]
            identity={'provider':'google','model':MODEL,'scenario_id':scenario.scenario_id,
                      'condition':condition,'repetition':1}
            if _digest(identity) not in attempted:
                eligible.append({'identity':identity,'execution_index':index,
                    'request_key':f'model-01/{condition}/{index:03d}',
                    'prompt_hash':_digest(build_messages(scenario,condition))})
    proposed=eligible[:4]
    require([r['execution_index'] for r in proposed]==pin['execution_indices'] and
            [r['identity']['scenario_id'] for r in proposed]==(['purpose_change-07','consent_revocation-02','purpose_change-03','scope_change-04'] if version==2
                 else ['scope_change-08','scope_change-01','consent_revocation-10','recipient_change-08']) and
            all(r['identity']['condition']=='post_update' for r in proposed),'next frozen identities changed')
    result={'bridge_version':version,'benchmark_hash':BENCHMARK_HASH,'model':MODEL,'condition':'post_update',
        'source_github_run_id':pin['source_github_run_id'],'source_attempt':pin['source_attempt'],
        'source_run_id':m['run_id'],'source_manifest_hash':digest,'source_file_hashes':file_hashes(source),
        'prior_bridge_hash':prior['bridge_hash'],'ledger':deepcopy(ledger),'next_requests':proposed,
        'maximum_new_requests':4,'max_attempts_per_request':1,'later_phases_enabled':False,
        'exploratory_analysis_in_primary':False}
    result['bridge_hash']=_digest(result)
    return result,schedule


def approvals_checked(approval,quota_floor):
    flags={'four_requests_approved','key_project_binding_confirmed','free_tier_no_paid_billing_confirmed',
           'quota_review_confirmed','all_provider_budget_review_confirmed'}
    quota={'available_rpm_requests':15,'available_rpd_requests':500,'available_tpm_tokens':250000}
    require(isinstance(approval,dict) and set(approval)==flags|set(quota)|{'reviewed_spend_usd'},'fresh review fields missing/extra')
    require(all(approval[k] is True for k in flags),'fresh four-request approvals required')
    spend=approval['reviewed_spend_usd']
    require(type(spend) in (int,float) and math.isfinite(spend) and 0<=spend<4,'actual all-provider spending below $4 required')
    for key,upper in quota.items():
        require(type(approval[key]) is int and 0<=approval[key]<=upper,'quota review inconsistent with recorded limits')
    require(approval['available_rpm_requests']>=4 and approval['available_rpd_requests']>=4 and
            approval['available_tpm_tokens']>=quota_floor,'insufficient reviewed quota headroom')


def prepare(source,run_id,approval,*,config=CONFIG,scope=SCOPE,_source_validation=False):
    lineage,schedule=bridge(source,config=config,scope=scope)
    # Re-plan to validate run ID/artifact paths; base configuration stays disabled.
    plan=plan_run(config,run_id=run_id,provider='google',model=MODEL,condition='post_update',
                  max_provider_requests=4,max_attempts_per_request=1)
    m=plan.manifest;indices={r['execution_index'] for r in lineage['next_requests']}
    prompts=[p for p in m['prompt_catalog'] if p['execution_index'] in indices]
    floor=sum(len(json.dumps(GoogleProvider().payload(p['messages'],MODEL,PARAMETERS)).encode()) for p in prompts)+4*512
    approvals_checked(approval,floor)
    m['model_matrix']=deepcopy(m['model_matrix'])
    m['model_matrix'][0].update(status='enabled',parameter_support={k:'supported' for k in PARAMETERS},
        notes='Scoped four-request wire continuation of pinned compatibility trial; no broader pilot enablement or determinism claim.')
    m.update(prompt_catalog=prompts,requests=[{'request_key':r['request_key'],'execution_index':r['execution_index'],
        'condition':'post_update','provider':'google','model':MODEL,'model_index':1,'parameters':PARAMETERS.copy(),
        'prompt_hash':r['prompt_hash']} for r in lineage['next_requests']],expected_request_count=4,
        expected_if_all_selected_enabled=4,enabled_models=1,primary_complete_design=False,
        experiment_kind=f"flash_lite_pinned_next_four_v{lineage['bridge_version']}",provenance_bridge=lineage,
        provider_checks=[{'provider':'google','model':MODEL,'scoped_continuation_only':True,
                          'requested_parameters':PARAMETERS.copy(),'effective_parameters':PARAMETERS.copy(),
                          'unsupported_parameters':[]}],
        owner_approvals=approval,quota_review={'conservative_byte_based_headroom_floor':floor,'token_guarantee':False},
        budget_review={'maximum_total_research_budget_usd':4,'maximum_authorized_paid_cost_usd':0,'dollar_spending_guarantee':False},
        execution_limits={'max_provider_requests':4,'max_attempts_per_request':1,'stop_on_http_statuses':[429],
                          'stop_after_consecutive_http_503':2,'stop_on_ambiguous':True,'stop_on_unconfirmed_transport':True})
    m.pop('manifest_hash');m['manifest_hash']=_digest(m)
    if lineage['bridge_version']>=2:
        m['dispatch_claim_key']=_digest([r['identity'] for r in lineage['next_requests']])
        m.pop('manifest_hash');m['manifest_hash']=_digest(m)
        # Reconstructing an archived manifest is read-only; a historical claim
        # is expected. Live run() always uses the default fresh-dispatch checks.
        require(_source_validation or not (plan.root/f"claims/{m['dispatch_claim_key']}.json").exists(),'four-identity scope already claimed')
        for path in (() if _source_validation else (plan.root/'manifests').glob('*.json')):
            other=_read(plan.root,path.relative_to(plan.root).as_posix())
            require(not any(r.get('provider')=='google' and r.get('model')==MODEL and
                            r.get('condition')=='post_update' and r.get('execution_index') in indices
                            for r in other.get('requests',[])), 'existing/uncertain overlapping experiment')
    require(_source_validation or (not (plan.root/f'manifests/{run_id}.json').exists() and
            not any((plan.root/section/run_id).exists() for section in ('raw','parsed','summaries'))),'batch ID already claimed; no resume')
    return plan


def run(source,run_id,approval,*,config=CONFIG,scope=SCOPE,transport=None):
    plan=prepare(source,run_id,approval,config=config,scope=scope)
    require(plan.manifest['git_dirty'] is False and bool(plan.manifest['commit']), 'clean committed checkout required')
    require(bool(os.environ.get('GOOGLE_API_KEY')), 'Google credential unavailable; no attempt authorized')
    if plan.manifest['provenance_bridge']['bridge_version']>=2:
        claim={'run_id':run_id,'manifest_hash':plan.manifest['manifest_hash'],
               'dispatch_claim_key':plan.manifest['dispatch_claim_key'],
               'identities':[r['identity'] for r in plan.manifest['provenance_bridge']['next_requests']]}
        try:_write(plan.root,f"claims/{plan.manifest['dispatch_claim_key']}.json",claim)
        except FileExistsError:raise ValidationError('overlapping or previously claimed scope; never redispatch') from None
        _write(plan.root,f'summaries/{run_id}/scope-claim.json',claim)
    expected={_digest(GoogleProvider().payload(p['messages'],MODEL,PARAMETERS)):p['execution_index']
              for p in plan.manifest['prompt_catalog']};seen=set();observations=[]
    require(len(expected)==4,'duplicate outbound identities')
    def bounded(url,headers,payload):
        digest=_digest(payload)
        require(url==GoogleProvider().endpoint_for(MODEL) and digest in expected and digest not in seen and len(seen)<4,
                'duplicate/out-of-scope provider dispatch')
        seen.add(digest);observation={'execution_index':expected[digest],'http_status':None,'transport_exception_type':None,
                                    'payload_sha256':sha256(json.dumps(payload).encode()).hexdigest(),
                                    'requested_model':MODEL}
        observations.append(observation)
        try:
            reply=(transport or recovery_transport)(url,headers,payload);observation['http_status']=reply.status;return reply
        except Exception as exc:observation['transport_exception_type']=type(exc).__name__;raise
    summary=None
    try:summary=execute_plan(plan,execute_live=True,resume=False,adapters={'google':GoogleProvider(transport=bounded)})
    finally:
        if (plan.root/f'manifests/{run_id}.json').exists():
            _write(plan.root,f'summaries/{run_id}/dispatch-audit.json',{'manifest_hash':plan.manifest['manifest_hash'],
                'bridge_hash':plan.manifest['provenance_bridge']['bridge_hash'],'maximum_new_requests':4,
                'provider_calls_entered':len(seen),'automatic_retries':0,'followup_workflow_dispatches':0,
                'observations':observations,'runner_terminated_normally':summary is not None})
            ledger=deepcopy(plan.manifest['provenance_bridge']['ledger'])
            for request in plan.manifest['requests']:
                key=request['request_key'];response_path=f'raw/{run_id}/{key}/attempt-01.response.json'
                started_path=f'raw/{run_id}/{key}/attempt-01.started.json'
                item=deepcopy(next(r for r in plan.manifest['provenance_bridge']['next_requests'] if r['request_key']==key))
                item.update(source_run_id=run_id,source_manifest_hash=plan.manifest['manifest_hash'])
                if (plan.root/response_path).exists():
                    response=_read(plan.root,response_path)
                    error=response.get('provider_error')
                    status=('ambiguous_provider_outcome_never_redispatch' if error and error.get('http_status') is None
                            else 'terminal_provider_failure' if error else 'terminal_completed')
                    item.update(status=status,
                                raw_record_path=response_path,raw_record_canonical_hash=_digest(response),
                                primary_parse_status=response['parse_status'])
                elif (plan.root/started_path).exists():item['status']='ambiguous_claimed_never_redispatch'
                else:item['status']='not_attempted'
                ledger.append(item)
            require(len({_digest(r['identity']) for r in ledger})==len(plan.manifest['provenance_bridge']['ledger'])+4,
                    'duplicate campaign ledger identity')
            _write(plan.root,f'summaries/{run_id}/campaign-ledger.json',{'bridge_hash':plan.manifest['provenance_bridge']['bridge_hash'],
                'manifest_hash':plan.manifest['manifest_hash'],'ledger':ledger,'later_phases_enabled':False})
    require(file_hashes(source)==plan.manifest['provenance_bridge']['source_file_hashes'],'source changed during execution')
    return plan,summary


def archive(source,results,run_id,destination):
    root=Path(results);destination=Path(destination)
    m=_read(root,f'manifests/{run_id}.json')
    unsigned=deepcopy(m);digest=unsigned.pop('manifest_hash')
    require(_digest(unsigned)==digest,'batch manifest changed')
    require(file_hashes(source)==m['provenance_bridge']['source_file_hashes'],'source changed before archive')
    ledger_record=_read(root,f'summaries/{run_id}/campaign-ledger.json')
    ledger=ledger_record['ledger']
    preserved=len(m['provenance_bridge']['ledger'])
    if m['provenance_bridge']['bridge_version']>=2:
        claim=_read(root,f'summaries/{run_id}/scope-claim.json')
        require(claim=={'run_id':run_id,'manifest_hash':digest,'dispatch_claim_key':m['dispatch_claim_key'],
                       'identities':[r['identity'] for r in m['provenance_bridge']['next_requests']]} and
                _digest(claim['identities'])==m['dispatch_claim_key'],'scope claim changed')
    require(ledger_record['manifest_hash']==digest and ledger_record['bridge_hash']==m['provenance_bridge']['bridge_hash']
            and len(ledger)==preserved+4 and len({_digest(r['identity']) for r in ledger})==preserved+4 and
            ledger[:preserved]==m['provenance_bridge']['ledger'] and
            [r['identity'] for r in ledger[preserved:]]==[r['identity'] for r in m['provenance_bridge']['next_requests']],
            'campaign ledger changed or duplicate identity')
    benchmark=root/m['benchmark_artifact']
    require(sha256(benchmark.read_bytes()).hexdigest()==BENCHMARK_HASH,'batch benchmark copy changed')
    # The copied benchmark is hash-pinned; require_pilot expects metadata.json
    # beside it, whereas run artifacts preserve benchmark_metadata.json.
    scenarios={s.scenario_id:s for s in load_scenarios(benchmark)}
    for entry in ledger[preserved:]:
        key=entry['request_key'];started=root/f'raw/{run_id}/{key}/attempt-01.started.json'
        response=root/f'raw/{run_id}/{key}/attempt-01.response.json'
        parsed=root/f'parsed/{run_id}/{key}.json'
        request=next(r for r in m['requests'] if r['request_key']==key)
        if entry['status']=='not_attempted':
            require(not started.exists() and not response.exists() and not parsed.exists(),'unattempted identity has records')
            continue
        claim=_read(root,started.relative_to(root).as_posix())
        require(all(claim.get(k)==v for k,v in {**request,'attempt':1,'manifest_hash':digest}.items()) and
                _digest(claim['messages'])==request['prompt_hash'],'batch started claim mismatch')
        if entry['status']=='ambiguous_claimed_never_redispatch':
            require(not response.exists() and not parsed.exists(),'ambiguous claim has unexpected terminal records')
            continue
        record=_read(root,response.relative_to(root).as_posix())
        require(_digest(record)==entry['raw_record_canonical_hash'] and record['manifest_hash']==digest and
                record['attempt']==1 and record['requested_model']==MODEL and record['provider']=='google',
                'batch response hash/identity mismatch')
        if record.get('provider_error'):
            require(not parsed.exists(),'provider failure must not have a model score')
        else:
            scenario=scenarios[entry['identity']['scenario_id']]
            expected=asdict(score_output(scenario,'post_update',parse_output(record['raw_output'],scenario)))
            require(_read(root,parsed.relative_to(root).as_posix())=={'request_key':key,'manifest_hash':digest,
                    'raw_hash':_digest(record),'score':expected},'batch primary score/hash mismatch')
    require(not destination.exists(),'archive exists')
    require(not any(p.is_symlink() for p in (destination,*destination.parents)), 'archive symlinks forbidden')
    # Each archive inspection finishes before any copying; original primary bytes
    # are retained separately and never remapped into fabricated stage records.
    import tempfile
    with tempfile.TemporaryDirectory() as scratch:
        original=Path(scratch)/'source';current=Path(scratch)/'batch'
        if m['provenance_bridge']['bridge_version']>=2:
            archive(Path(source)/'source',Path(source)/'batch',m['provenance_bridge']['source_run_id'],original)
        else:
            stage_archive(source,m['provenance_bridge']['ledger'][0]['source_run_id'],original,compatibility=True)
        stage_archive(root,run_id,current,next_four=True)
        for name,staged in (('source',original),('batch',current)):
            for p in staged.rglob('*'):
                if p.is_file():
                    target=destination/name/p.relative_to(staged);target.parent.mkdir(parents=True,exist_ok=True)
                    with target.open('xb') as f:f.write(p.read_bytes())
