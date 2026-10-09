"""Isolated one-attempt wire compatibility probe; no pilot model is enabled."""
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path

from .artifact_safety import stage_archive
from .free_tier_campaign import CONFIG, MODEL
from .protocol import BENCHMARK_HASH
from .providers import GoogleProvider
from .recovery import recovery_transport
from .runner import _digest, _write, execute_plan, plan_run
from .schema import ValidationError

PARAMETERS = {'temperature': 0, 'top_p': 1, 'max_output_tokens': 512, 'seed': 20261007}


def authorize(approval):
    required={'one_request_approved','key_project_binding_confirmed','free_tier_no_paid_billing_confirmed',
              'quota_review_confirmed','all_provider_budget_review_confirmed','reviewed_spend_usd'}
    if not isinstance(approval,dict) or set(approval)!=required:
        raise ValidationError('authorization fields missing or unexpected')
    if any(approval[k] is not True for k in required-{'reviewed_spend_usd'}):
        raise ValidationError('explicit one-request/project/tier/quota/budget approval required')
    spend=approval['reviewed_spend_usd']
    if type(spend) not in (int,float) or not math.isfinite(spend) or not 0<=spend<4:
        raise ValidationError('reviewed actual all-provider spending below $4 required')


def prepare(run_id,approval,*,config=CONFIG):
    authorize(approval)
    plan=plan_run(config,run_id=run_id,provider='google',model=MODEL,condition='post_update',
                  scenario_limit=1,max_provider_requests=1,max_attempts_per_request=1)
    m=plan.manifest
    if (plan.config['execution']['repetitions']!=1 or m['generation_parameters']!=PARAMETERS
            or m['benchmark']['hash']!=BENCHMARK_HASH or len(m['prompt_catalog'])!=1
            or len(m['model_matrix'])!=1 or m['model_matrix'][0]['model_id']!=MODEL
            or plan.config['models'] or m['model_matrix'][0]['status']!='disabled'):
        raise ValidationError('frozen isolated probe configuration mismatch')
    original=deepcopy(m['model_matrix'][0])
    # A scoped wire trial permits transmitting fields under test, not a verified
    # capability declaration. Original disabled configuration bytes stay recorded.
    m['model_matrix']=deepcopy(m['model_matrix'])
    entry=m['model_matrix'][0]
    entry.update(status='enabled',parameter_support={k:'supported' for k in PARAMETERS},
                 notes='Wire fields permitted only for an explicitly authorized one-request compatibility trial; exact-model support unverified.')
    prompt=m['prompt_catalog'][0]
    request={'request_key':'model-01/post_update/001','execution_index':1,'condition':'post_update',
             'provider':'google','model':MODEL,'model_index':1,'parameters':PARAMETERS.copy(),'prompt_hash':prompt['prompt_hash']}
    m.update(requests=[request],enabled_models=1,expected_request_count=1,
             experiment_kind='isolated_flash_lite_compatibility_v1',
             compatibility_probe={'original_disabled_model':original,'exact_model_support':'unverified_under_test',
                                  'scope':'one_request_only_not_campaign_enablement','owner_approvals':approval,
                                  'maximum_total_research_budget_usd':4,'dollar_spending_guarantee':False,
                                  'maximum_authorized_paid_cost_usd':0},
             provider_checks=[{'provider':'google','model':MODEL,'wire_trial_only':True,
                               'requested_parameters':PARAMETERS.copy(),'effective_parameters':PARAMETERS.copy(),
                               'unsupported_parameters':[]}])
    m.pop('manifest_hash');m['manifest_hash']=_digest(m)
    if (plan.root/f'manifests/{run_id}.json').exists() or any((plan.root/section/run_id).exists()
            for section in ('raw','parsed','summaries')):
        raise ValidationError('probe ID already claimed; no resume or overwrite')
    return plan


def run(run_id,approval,*,config=CONFIG,transport=None):
    plan=prepare(run_id,approval,config=config)
    observed={'provider_calls_entered':0,'http_status':None,'transport_exception_type':None}
    expected=GoogleProvider().payload(plan.manifest['prompt_catalog'][0]['messages'],MODEL,PARAMETERS)

    def bounded(url,headers,payload):
        if observed['provider_calls_entered'] or url!=GoogleProvider().endpoint_for(MODEL) or payload!=expected:
            raise ValidationError('one-call exact payload boundary violated')
        observed['provider_calls_entered']=1
        try:
            reply=(transport or recovery_transport)(url,headers,payload)
            observed['http_status']=reply.status
            return reply
        except Exception as exc:
            observed['transport_exception_type']=type(exc).__name__
            raise

    summary=None
    try:
        summary=execute_plan(plan,execute_live=True,resume=False,adapters={'google':GoogleProvider(transport=bounded)})
    finally:
        # Preserve sanitized HTTP observation even if raw persistence/normalization
        # fails. A process kill can still leave only the original started claim.
        if (plan.root/f'manifests/{run_id}.json').exists():
            attempts=len(list((plan.root/f'raw/{run_id}').rglob('*.started.json')))
            audit={**observed,'manifest_hash':plan.manifest['manifest_hash'],'maximum_new_requests':1,
                   'attempted':attempts,'maximum_attempts':1,
                   'payload_sha256':sha256(json.dumps(expected).encode()).hexdigest(),
                   'transport_outcome_uncertain':observed['provider_calls_entered']==1 and observed['http_status'] is None,
                   'runner_terminated_normally':summary is not None,
                   'automatic_retries':0,'followup_workflow_dispatches':0}
            _write(plan.root,f'summaries/{run_id}/dispatch-audit.json',audit)
    return plan,summary,audit


def archive(results,run_id,destination):
    return stage_archive(results,run_id,destination,compatibility=True)
