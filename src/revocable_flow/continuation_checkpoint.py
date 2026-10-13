"""Offline verification and range planning using the existing frozen runner.

There is deliberately no live executor or remote persistence implementation here.
Any live continuation requires a separately reviewed execution/approval protocol.
"""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import tempfile

from .four_request_bridge import bridge, prepare, archive, require, NEXT_SCOPE
from .chained_recovery import file_hashes
from .compatibility_probe import PARAMETERS
from .free_tier_campaign import CONFIG, MODEL, PHASES
from .protocol import BENCHMARK_HASH, build_messages, make_raw_record, parse_output, score_output
from .providers import GoogleProvider
from .runner import _digest, _read, _write, RunPlan
from .schema import ValidationError

PIN='configs/flash_lite_continuation_checkpoint_v1.json'


def verify_checkpoint(source, *, pin=PIN, config=CONFIG, predecessor_scope=NEXT_SCOPE):
    """Check pinned scientific bytes and reproduce the entire 13-attempt chain."""
    source=Path(source);pin=json.loads(Path(pin).read_text());hashes=file_hashes(source)
    require(pin['version']=='flash-lite-continuation-offline-v1' and pin['live_execution_enabled'] is False,
            'offline checkpoint gate changed')
    require(pin['benchmark_hash']==BENCHMARK_HASH and pin['model']==MODEL and
            pin['generation_parameters']==PARAMETERS,'frozen checkpoint settings changed')
    require(hashes==pin['scientific_file_hashes'],'checkpoint bytes missing/extra/changed')
    prior,schedule=bridge(source/'source',config=config,scope=predecessor_scope)
    root=source/'batch';rid=pin['run_id'];m=_read(root,f'manifests/{rid}.json')
    unsigned=deepcopy(m);mh=unsigned.pop('manifest_hash')
    require(_digest(unsigned)==mh==pin['manifest_hash'] and m['commit']==pin['commit'] and
            m['run_id']==rid and m['git_dirty'] is False and m['provenance_bridge']==prior,
            'checkpoint manifest/provenance changed')
    expected=prepare(source/'source',rid,m['owner_approvals'],config=config,scope=predecessor_scope,
                     _source_validation=True).manifest
    for key in ('commit','git_dirty','python_version'):expected[key]=m[key]
    expected.pop('manifest_hash');require(_digest(expected)==mh,'checkpoint manifest does not reproduce')
    with tempfile.TemporaryDirectory() as scratch:
        archive(source/'source',root,rid,Path(scratch)/'verified')
    ledger=_read(root,f'summaries/{rid}/campaign-ledger.json')['ledger']
    require(len(ledger)==13 and len({_digest(r['identity']) for r in ledger})==13 and
            [r['execution_index'] for r in ledger]==list(range(1,14)) and
            all(r['status']=='terminal_completed' for r in ledger),'duplicate/ambiguous/nonterminal checkpoint')
    audit=_read(root,f'summaries/{rid}/dispatch-audit.json')
    require(audit['manifest_hash']==mh and audit['bridge_hash']==prior['bridge_hash'] and
            audit['maximum_new_requests']==audit['provider_calls_entered']==4 and
            audit['automatic_retries']==audit['followup_workflow_dispatches']==0 and
            audit['runner_terminated_normally'] is True and
            [o['execution_index'] for o in audit['observations']]==[10,11,12,13] and
            all(o['http_status']==200 and o['transport_exception_type'] is None and
                o['requested_model']==MODEL for o in audit['observations']), 'checkpoint dispatch audit changed')
    paths=list((root/f'summaries/{rid}').glob('completion-*.json'))
    require(len(paths)==1,'checkpoint completion ambiguous')
    summary=_read(root,paths[0].relative_to(root).as_posix())
    require(paths[0].name==f'completion-{_digest(summary)[:16]}.json' and summary['manifest_hash']==mh and
            summary['complete'] is True and summary['completed']==summary['attempted_provider_requests']==4 and
            not summary['ambiguous_attempts'] and not summary['infrastructure_missing'] and
            not summary['unattempted_requests'],'checkpoint incomplete')
    require(len(list(source.rglob('*.started.json')))==len(list(source.rglob('*.response.json')))==13,
            'checkpoint attempt count mismatch')
    cases=[]
    for entry in ledger:
        index=entry['execution_index'];scenario=schedule.scenarios[index-1]
        rid=entry['source_run_id'];key=entry['request_key']
        paths=list(source.rglob(f'raw/{rid}/{key}/attempt-01.response.json'))
        require(len(paths)==1,'ambiguous response location')
        record_root=paths[0].parents[5];raw=_read(record_root,paths[0].relative_to(record_root).as_posix())
        parsed=_read(record_root,f'parsed/{rid}/{key}.json')
        started=_read(record_root,f'raw/{rid}/{key}/attempt-01.started.json')
        messages=build_messages(scenario,'post_update')
        require(entry['identity']=={'provider':'google','model':MODEL,'scenario_id':scenario.scenario_id,
                'condition':'post_update','repetition':1} and
                _digest(messages)==entry['prompt_hash']==raw['prompt_hash'] and started['messages']==messages and
                started['attempt']==raw['attempt']==1 and
                started['manifest_hash']==raw['manifest_hash']==parsed['manifest_hash']==entry['source_manifest_hash'],
                'attempt identity/prompt/hash mismatch')
        require(raw['provider_error'] is None and raw['requested_model']==raw['reported_model']==MODEL and
                raw['requested_parameters']==raw['effective_parameters']==raw['parameters']==PARAMETERS and
                raw['unsupported_parameters']==[],'response model/parameters changed')
        reproduced=make_raw_record(scenario=scenario,raw_output=raw['raw_output'],execution_index=index,
            provider='google',model=MODEL,timestamp=raw['timestamp'],condition='post_update',parameters=PARAMETERS,
            latency_ms=raw['latency_ms'],request_id=raw['request_id'])
        require(all(raw.get(k)==v for k,v in reproduced.items()),'response does not reproduce')
        primary=asdict(score_output(scenario,'post_update',parse_output(raw['raw_output'],scenario)))
        require(_digest(raw)==entry['raw_record_canonical_hash']==parsed['raw_hash'] and parsed['score']==primary,
                'primary score/raw hash changed')
        if not primary['valid']:
            require(all(primary[k] is None for k in ('privacy_violation','over_refusal','stale_leak')),
                    'invalid output has imputed privacy outcome')
        if index>=10:
            wire=sha256(json.dumps(GoogleProvider().payload(messages,MODEL,PARAMETERS)).encode()).hexdigest()
            require(audit['observations'][index-10]['payload_sha256']==wire,'outbound payload hash changed')
        cases.append({'execution_index':index,'request_key':key,'score':primary})
    require(file_hashes(source)==hashes,'checkpoint altered during verification')
    return {'manifest_hash':mh,'ledger':deepcopy(ledger),'scientific_file_hashes':hashes,'cases':cases},schedule


def plan_range(checkpoint,schedule,condition,start,end, *, approved_for_offline_planning=False):
    """Plan the next consecutive frozen range; cannot authorize generation."""
    require(approved_for_offline_planning is True,'explicit offline range approval required')
    require(condition in ('post_update','pre_update') and type(start) is int and type(end) is int and
            1<=start<=end<=40 and end-start+1<=20,'invalid range or offline batch cap exceeded')
    ledger=checkpoint['ledger'];seen=set()
    for entry in ledger:
        identity=_digest(entry['identity']);require(identity not in seen,'duplicate checkpoint identity')
        require(entry['status']=='terminal_completed','nonterminal/uncertain checkpoint requires review')
        seen.add(identity)
    remaining=[]
    for phase_condition,indices in PHASES.values():
        for index in indices:
            scenario=schedule.scenarios[index-1]
            identity={'provider':'google','model':MODEL,'scenario_id':scenario.scenario_id,
                      'condition':phase_condition,'repetition':1}
            if _digest(identity) not in seen:
                remaining.append({'identity':identity,'execution_index':index,
                    'request_key':f'model-01/{phase_condition}/{index:03d}',
                    'prompt_hash':_digest(build_messages(scenario,phase_condition))})
    selected=remaining[:end-start+1]
    require([r['execution_index'] for r in selected]==list(range(start,end+1)) and
            all(r['identity']['condition']==condition for r in selected),'range is not the next frozen unattempted prefix')
    plan={'version':'flash-lite-continuation-offline-v1','live_execution_enabled':False,
          'source_manifest_hash':checkpoint['manifest_hash'],'source_file_hashes':checkpoint['scientific_file_hashes'],
          'prior_ledger_hash':_digest(ledger),'prior_terminal_attempts':len(ledger),'requests':selected,
          'maximum_new_requests':len(selected),'maximum_attempts_per_identity':1,'automatic_retries':0,
          'followup_dispatches':0,'later_phases_enabled':False,'benchmark_hash':BENCHMARK_HASH,
          'model':MODEL,'parameters':deepcopy(PARAMETERS),'maximum_total_research_budget_usd':4,
          'dollar_guarantee_from_request_cap':False,'required_before_any_live_execution':[
              'separate exact-plan approval','fresh key-project binding','fresh Free tier/no paid billing',
              'fresh shared RPM/TPM/RPD headroom','reconciled actual all-provider spending below $4',
              'durable remote claim/result journal implementation and crash tests']}
    plan['plan_hash']=_digest(plan);return plan


def single_request_plan(prepared,index,approval,*,kind="durable_flash_lite_single_request_v1"):
    base=prepared['base'];rid=base.manifest['run_id']+f'-i{index:03d}'
    require(len(rid)<=64,'run ID too long')
    scenario=base.scenarios[index-1];messages=build_messages(scenario,'post_update')
    m=deepcopy(base.manifest);m.update(run_id=rid,benchmark_artifact=f'parsed/{rid}/benchmark.jsonl',
        benchmark_metadata_artifact=f'parsed/{rid}/benchmark_metadata.json',
        experiment_kind=kind,primary_complete_design=False,
        expected_request_count=1,expected_if_all_selected_enabled=1,enabled_models=1,
        owner_approvals=deepcopy(approval),durable_scope_hash=_digest(prepared['planned']['requests']),
        source_manifest_hash=prepared['checkpoint']['manifest_hash'],
        prompt_catalog=[{'execution_index':index,'condition':'post_update','messages':messages,'prompt_hash':_digest(messages)}],
        requests=[{'request_key':f'model-01/post_update/{index:03d}','execution_index':index,'condition':'post_update',
                   'provider':'google','model':MODEL,'model_index':1,'parameters':PARAMETERS.copy(),'prompt_hash':_digest(messages)}],
        execution_limits={'max_provider_requests':1,'max_attempts_per_request':1,'stop_on_http_statuses':[429,500,502,503,504],
                          'stop_after_consecutive_http_503':1,'stop_on_ambiguous':True,'stop_on_unconfirmed_transport':True})
    m['model_matrix'][0].update(status='enabled',parameter_support={p:'supported' for p in PARAMETERS},
                               notes='Isolated journal-claimed request; broader matrix unchanged.')
    if kind=='artifact_single_request_v1':
        m['authorization_scope_hash']=m.pop('durable_scope_hash')
        m['model_matrix'][0]['notes']='Owner-bound artifact request; broader matrix unchanged.'
    m.pop('manifest_hash');m['manifest_hash']=_digest(m)
    return RunPlan(m,base.scenarios,base.root,base.config,base.benchmark_bytes,base.metadata_bytes)


def claim_disposition(identity, *, claim=None, terminal_record=None):
    """Offline state-machine specification, not a durable storage implementation.

    A create-only durable claim precedes a call. Its existence always forbids
    redispatch, even when no response was durably published before a crash.
    """
    if claim is None:
        require(terminal_record is None,'orphan terminal record; execution blocked')
        return 'unclaimed_requires_fresh_approval_and_atomic_remote_claim'
    require(claim['identity']==identity and claim['identity_hash']==_digest(identity),'claim identity mismatch')
    if terminal_record is None:return 'claimed_unknown_never_redispatch'
    require(terminal_record['claim_hash']==_digest(claim),'terminal provenance mismatch')
    return 'terminal_never_redispatch'


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Offline checkpoint verification and planning; zero generation calls.')
    parser.add_argument('--source',required=True);parser.add_argument('--condition',choices=('post_update','pre_update'),required=True)
    parser.add_argument('--start',type=int,required=True);parser.add_argument('--end',type=int,required=True)
    parser.add_argument('--approve-offline-plan',action='store_true');parser.add_argument('--output',required=True)
    args=parser.parse_args()
    try:
        checkpoint,schedule=verify_checkpoint(args.source)
        planned=plan_range(checkpoint,schedule,args.condition,args.start,args.end,
                           approved_for_offline_planning=args.approve_offline_plan)
        output=Path(args.output);_write(output.parent,output.name,planned)
        print(json.dumps({'offline_only':True,'prior_terminal_attempts':len(checkpoint['ledger']),
                          'planned_requests':len(planned['requests']),'plan_hash':planned['plan_hash']}))
    except (ValidationError,OSError,KeyError,TypeError,ValueError):
        raise SystemExit('Offline checkpoint/range verification failed; no generation is available.') from None
