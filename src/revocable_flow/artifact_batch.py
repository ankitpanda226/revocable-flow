"""Research-only artifact batches: one owner-bound invocation, never auto-resume.

No durable Git backend or privileged credential is used. Loss of an artifact
quarantines the authorized scope rather than permitting duplicate execution.
"""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256,sha1
import json
import math
import os
from pathlib import Path
import shutil
import time
from unittest.mock import Mock

from .continuation_checkpoint import verify_checkpoint,plan_range,single_request_plan
from .chained_recovery import file_hashes
from .four_request_bridge import require
from .free_tier_campaign import CONFIG,MODEL
from .compatibility_probe import PARAMETERS
from .providers import GoogleProvider
from .recovery import recovery_transport
from .runner import plan_run,execute_plan,_write,_read,_digest
from .protocol import BENCHMARK_HASH,build_messages,score_output,parse_output,make_raw_record
from .artifact_safety import TOKEN_PATTERN,_secret_material,_inspect_json
from .schema import ValidationError,parse_json

SCOPE='configs/flash_lite_artifact_batch_014_023_v1.json'
WORKFLOW='.github/workflows/flash-lite-artifact-batch.yml'
FLAGS=('batch_approved','key_project_binding_confirmed','free_tier_no_paid_billing_confirmed',
       'quota_review_confirmed','all_provider_budget_review_confirmed')


def safe(value):
    text=json.dumps(value)
    require(not TOKEN_PATTERN.search(text) and not any(v in text for v in _secret_material()),'credential-like artifact rejected')
    _inspect_json(value)


def prepare(source,run_id,*,scope=SCOPE,config=CONFIG,pin=None,predecessor_scope=None):
    kwargs={'config':config}
    if pin is not None:kwargs['pin']=pin
    if predecessor_scope is not None:kwargs['predecessor_scope']=predecessor_scope
    checkpoint,schedule=verify_checkpoint(source,**kwargs)
    planned=plan_range(checkpoint,schedule,'post_update',14,23,approved_for_offline_planning=True)
    policy=parse_json(Path(scope).read_text())
    require(policy['version']=='flash-lite-artifact-batch-v1' and type(policy['live_execution_enabled']) is bool and
        policy['requests']==planned['requests'] and policy['model']==MODEL and policy['parameters']==PARAMETERS and
        policy['maximum_new_requests']==10 and policy['max_attempts_per_identity']==1 and
        policy['automatic_retries']==policy['followup_dispatches']==0 and policy['later_phases_enabled'] is False and
        policy['minimum_dispatch_interval_seconds']==12 and policy['maximum_total_research_budget_usd']==4 and
        policy['provider']=='google' and policy['condition']=='post_update' and policy['maximum_authorized_paid_cost_usd']==0 and
        policy['authorization_path']=='checkpoints/authorizations/post_update_014_023.json' and
        policy['source_manifest_hash']==checkpoint['manifest_hash'],'artifact batch scope changed')
    attempted={_digest(r['identity']) for r in checkpoint['ledger']}
    require(not any(_digest(r['identity']) in attempted for r in planned['requests']),'attempted identity selected')
    base=plan_run(config,run_id=run_id,provider='google',model=MODEL,condition='post_update',max_provider_requests=10,max_attempts_per_request=1)
    require(base.config['models']==[] and base.manifest['generation_parameters']==PARAMETERS,'broader protocol enabled/changed')
    floor=sum(len(json.dumps(GoogleProvider().payload(build_messages(base.scenarios[i-1],'post_update'),MODEL,PARAMETERS)).encode())+512 for i in range(14,24))
    archived=parse_json(Path(policy['predecessor_archive_summary']).read_text())
    require(archived['batch_manifest_hash']==checkpoint['manifest_hash'] and archived['cumulative_ledger_hash']==_digest(checkpoint['ledger']) and
        archived['scientific_file_tree_hash']==_digest(file_hashes(source)) and
        archived['terminal_identities']==[{'request_key':r['request_key'],'identity':r['identity'],'status':r['status'],'primary_parse_status':r['primary_parse_status']} for r in checkpoint['ledger']],
        'archival checkpoint mismatch')
    return {'archival_summary':archived,'source':Path(source),'source_hashes':file_hashes(source),'checkpoint':checkpoint,'planned':planned,
            'base':base,'policy':policy,'headroom_floor':floor}


def authorization(prepared,evidence,context,*,check_age=True):
    # Evidence is obtained via read-only GitHub API by the trusted workflow.
    # Never accept a mutable/updated/reused authorization path.
    record=evidence['record'];safe(record)
    archived=prepared['archival_summary']
    if check_age:
        require(archived['owner_verified_two_independent_archive_copies'] is True and len(set(archived['archive_references']))>=2,
            'owner must verify two independent predecessor archives before generation')
    require(evidence['path']==prepared['policy']['authorization_path'] and len(evidence['file_history'])==1 and
        evidence['authorization_commit']==evidence['file_history'][0] and
        isinstance(evidence['authorization_commit'],str) and len(evidence['authorization_commit'])==40,
        'authorization must have one immutable introduction')
    data=evidence['record_bytes_utf8'].encode()
    require(parse_json(data.decode())==record and sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==evidence['blob_sha'],
            'authorization content/hash mismatch')
    require(set(context)=={'repository','run_id','run_attempt','job_id','runner_id','execution_commit','invocation_nonce'} and
        context['repository']=='ankitpanda226/revocable-flow' and
        all(type(context[k]) is int and context[k]>0 for k in ('run_id','job_id')) and type(context['runner_id']) is int and context['runner_id']>=0,'invalid service context')
    require(record['version']=='flash-lite-invocation-authorization-v1' and
        record['scope_hash']==_digest(prepared['planned']['requests']) and
        record['predecessor_manifest_hash']==prepared['checkpoint']['manifest_hash'] and
        record['workflow_path']==WORKFLOW and record['binding']==context and type(context['run_attempt']) is int and context['run_attempt']==1 and
        context['execution_commit']==prepared['base'].manifest['commit'] and
        prepared['base'].manifest['run_id']==f"gh-artifact-{context['run_id']}-1" and
        isinstance(context['invocation_nonce'],str) and len(context['invocation_nonce'])>=32,
        'authorization is not bound to this one run/job/invocation')
    approval=record['fresh_review'];require(set(approval)==set(FLAGS)|{'reviewed_spend_usd','available_rpm_requests','available_rpd_requests','available_tpm_tokens'},'fresh review missing/extra')
    require(all(approval[f] is True for f in FLAGS),'fresh owner review required')
    spend=approval['reviewed_spend_usd'];require(type(spend) in (int,float) and math.isfinite(spend) and 0<=spend<4,'unknown/exhausted spending budget')
    for field,minimum,maximum in (('available_rpm_requests',10,15),('available_rpd_requests',10,500),('available_tpm_tokens',prepared['headroom_floor'],250000)):
        require(type(approval[field]) is int and minimum<=approval[field]<=maximum,'fresh shared quota insufficient')
    require(type(record['approved_at_epoch']) in (int,float) and math.isfinite(record['approved_at_epoch']),'invalid approval time')
    if check_age:require(0<=time.time()-record['approved_at_epoch']<=300,'owner review is stale/future dated')
    return approval


def _snapshot(root,batch_id,ledger,parent):
    body={'ledger':deepcopy(ledger),'parent_snapshot_hash':parent}
    digest=_digest(body);_write(root,f'ledgers/{batch_id}/{digest}.json',body);return digest


def run(prepared,evidence,context,*,transport=None,simulation=False,sleep=time.sleep,clock=time.monotonic,crash_hook=lambda point,index:None):
    if simulation is True:require(isinstance(transport,Mock),'offline simulation requires mock transport')
    else:require(prepared['policy']['live_execution_enabled'] is True,'artifact batch live execution disabled')
    approval=authorization(prepared,evidence,context)
    require(prepared['base'].manifest['git_dirty'] is False and bool(os.environ.get('GOOGLE_API_KEY')),'clean code and credential required')
    root=prepared['base'].root;batch_id=prepared['base'].manifest['run_id']
    # Exclusive process marker. Never resume even on the same runner.
    _write(root,f'batches/{batch_id}/invocation.started.json',{'context':context,'authorization_commit':evidence['authorization_commit']})
    ledger=deepcopy(prepared['checkpoint']['ledger']);parent=_snapshot(root,batch_id,ledger,None)
    manifest={'version':'flash-lite-artifact-batch-v1','run_id':batch_id,'context':context,'owner_approval_evidence':evidence,
              'predecessor_manifest_hash':prepared['checkpoint']['manifest_hash'],'predecessor_file_hashes':prepared['source_hashes'],
              'predecessor_archive_attestation':deepcopy(prepared['archival_summary']),
              'predecessor_ledger':deepcopy(ledger),'requests':prepared['planned']['requests'],'parameters':PARAMETERS,
              'benchmark_hash':BENCHMARK_HASH,'maximum_new_requests':10,'automatic_retries':0,'later_phases_enabled':False}
    manifest['manifest_hash']=_digest(manifest);_write(root,f'batches/{batch_id}/manifest.json',manifest)
    calls=0;seen=set();observations=[];last=None;total=0;stop=None
    try:
        for request in prepared['planned']['requests']:
            require(file_hashes(prepared['source'])==prepared['source_hashes'],'predecessor changed')
            if total+prepared['headroom_floor']/10>approval['available_tpm_tokens']:stop='quota_exhausted';break
            if last is not None:sleep(max(0,12-(clock()-last)))
            index=request['execution_index'];plan=single_request_plan(prepared,index,approval,kind='artifact_single_request_v1')
            sub_id=plan.manifest['run_id'];key=request['request_key'];wire=[]
            def bounded(url,headers,payload):
                nonlocal calls,last,parent
                require(calls<10 and index not in seen and url==GoogleProvider().endpoint_for(MODEL) and
                    payload==GoogleProvider().payload(plan.manifest['prompt_catalog'][0]['messages'],MODEL,PARAMETERS),'duplicate/out-of-scope transport')
                seen.add(index);calls+=1;last=clock();wire.append({'execution_index':index,'http_status':None,'payload_sha256':sha256(json.dumps(payload).encode()).hexdigest()})
                observations.append(wire[0]);crash_hook('during_transport',index)
                reply=(transport or recovery_transport)(url,headers,payload);wire[0]['http_status']=reply.status;return reply
            class CapturingGoogle(GoogleProvider):
                def generate(self,*args,**kwargs):
                    nonlocal parent
                    started_path=f'raw/{sub_id}/{key}/attempt-01.started.json'
                    started=_read(root,started_path)
                    entry=deepcopy(request);entry.update(status='ambiguous_claimed_never_redispatch',source_run_id=sub_id,
                        source_manifest_hash=plan.manifest['manifest_hash'])
                    ledger.append(entry);parent=_snapshot(root,batch_id,ledger,parent)
                    crash_hook('after_claim_before_call',index)
                    response=super().generate(*args,**kwargs)
                    # Allowlisted adapter fields only; exclude arbitrary HTTP bodies/headers.
                    capture={'request_key':key,'provider_response':asdict(response),'http_status':wire[0]['http_status'] if wire else None}
                    safe(capture);_write(root,f'batches/{batch_id}/captures/{index:03d}.json',capture)
                    crash_hook('after_response_before_score',index);return response
            summary=execute_plan(plan,execute_live=True,resume=False,adapters={'google':CapturingGoogle(transport=bounded)})
            raw_path=f'raw/{sub_id}/{key}/attempt-01.response.json';raw=_read(root,raw_path)
            error=raw.get('provider_error')
            entry=ledger[-1];entry.update(status=('ambiguous_transport_never_redispatch' if error and error.get('http_status') is None else
                'terminal_provider_failure' if error else 'terminal_completed'),raw_record_path=raw_path,
                raw_record_canonical_hash=_digest(raw),primary_parse_status=raw['parse_status'])
            parsed_path=f'parsed/{sub_id}/{key}.json'
            if (root/parsed_path).exists():entry.update(primary_score_record_path=parsed_path,primary_score=_read(root,parsed_path)['score'])
            parent=_snapshot(root,batch_id,ledger,parent);crash_hook('after_result',index)
            if error or not wire or wire[0]['http_status']!=200:stop='provider_failure_or_ambiguous_transport';break
            tokens=raw.get('usage',{}).get('totalTokenCount')
            if raw['reported_model']!=MODEL or type(tokens) is not int or tokens<0:stop='unverified_model_or_usage';break
            total+=tokens
            if total>approval['available_tpm_tokens']:stop='quota_exhausted';break
    except BaseException:
        stop='runner_interruption_or_validation_failure';raise
    finally:
        audit={'manifest_hash':manifest['manifest_hash'],'observations':observations,'provider_calls_entered':calls,
               'automatic_retries':0,'followup_dispatches':0,'stop_reason':stop,
               'unattempted_request_keys':[r['request_key'] for r in prepared['planned']['requests'] if r['request_key'] not in {e['request_key'] for e in ledger}],
               'final_snapshot_hash':parent,'recorded_total_tokens':total}
        _write(root,f'batches/{batch_id}/audit.json',audit)
        _write(root,f'batches/{batch_id}/campaign-ledger.json',{'manifest_hash':manifest['manifest_hash'],'ledger':ledger,'final_snapshot_hash':parent})
    require(file_hashes(prepared['source'])==prepared['source_hashes'],'original records changed')
    return {'root':root,'batch_id':batch_id,'audit':audit}


def seal(prepared,root,batch_id,destination):
    """Inspect, reproduce scores and copy exact predecessor/new bytes exclusively."""
    root=Path(root);destination=Path(destination)
    require(not destination.exists() and not any(p.is_symlink() for p in (destination,*destination.parents)),'new nonsymlink archive required')
    require(file_hashes(prepared['source'])==prepared['source_hashes'],'source hash mismatch')
    m=_read(root,f'batches/{batch_id}/manifest.json');unsigned=deepcopy(m);mh=unsigned.pop('manifest_hash')
    require(_digest(unsigned)==mh and m['predecessor_file_hashes']==prepared['source_hashes'] and
        m['predecessor_ledger']==prepared['checkpoint']['ledger'] and m['requests']==prepared['planned']['requests'],'batch manifest mismatch')
    authorization(prepared,m['owner_approval_evidence'],m['context'],check_age=False)
    ledger=_read(root,f'batches/{batch_id}/campaign-ledger.json')['ledger'];audit=_read(root,f'batches/{batch_id}/audit.json')
    require(ledger[:13]==m['predecessor_ledger'] and len({_digest(e['identity']) for e in ledger})==len(ledger) and
        [e['request_key'] for e in ledger[13:]]==[r['request_key'] for r in m['requests'][:len(ledger)-13]],'duplicate/non-prefix ledger')
    require(audit['manifest_hash']==mh and audit['provider_calls_entered']==len(audit['observations'])<=10 and
        audit['automatic_retries']==audit['followup_dispatches']==0 and
        len({o['execution_index'] for o in audit['observations']})==len(audit['observations']),'dispatch audit inconsistent')
    snapshots={p.stem:parse_json(p.read_text()) for p in (root/f'ledgers/{batch_id}').glob('*.json')}
    parent=audit['final_snapshot_hash'];seen=set();last_ledger=ledger
    while parent is not None:
        require(parent in snapshots and parent not in seen and _digest(snapshots[parent])==parent,'ledger history missing/altered/cyclic')
        seen.add(parent);body=snapshots[parent];require(body['ledger']==last_ledger,'ledger snapshot mismatch')
        parent=body['parent_snapshot_hash']
        if parent is not None:
            previous=snapshots.get(parent,{}).get('ledger');current=body['ledger']
            require(isinstance(previous,list) and current[:13]==m['predecessor_ledger'] and previous[:13]==m['predecessor_ledger'],
                'predecessor ledger rewritten in snapshot')
            if len(current)==len(previous)+1:
                require(current[:-1]==previous and current[-1]['status']=='ambiguous_claimed_never_redispatch',
                    'invalid claim append transition')
            else:
                require(len(current)==len(previous) and current[:-1]==previous[:-1] and
                    previous[-1]['status']=='ambiguous_claimed_never_redispatch' and
                    current[-1]['identity']==previous[-1]['identity'] and current[-1]['request_key']==previous[-1]['request_key'],
                    'invalid terminal transition')
            last_ledger=previous
    require(seen==set(snapshots) and last_ledger==prepared['checkpoint']['ledger'],'unlinked ledger snapshots')
    paths=set(p.relative_to(root).as_posix() for p in (root/f'batches/{batch_id}').rglob('*') if p.is_file())
    paths.update(p.relative_to(root).as_posix() for p in (root/f'ledgers/{batch_id}').glob('*.json'))
    for entry in ledger[13:]:
        rid=entry['source_run_id'];key=entry['request_key'];index=entry['execution_index']
        requested=next((r for r in m['requests'] if r['request_key']==key),None)
        require(requested is not None and all(entry.get(k)==v for k,v in requested.items()),'ledger identity changed')
        sm=_read(root,f'manifests/{rid}.json');u=deepcopy(sm);sh=u.pop('manifest_hash');require(_digest(u)==sh==entry['source_manifest_hash'],'single-request manifest hash mismatch')
        expected=single_request_plan(prepared,index,m['owner_approval_evidence']['record']['fresh_review'],kind='artifact_single_request_v1').manifest
        expected['python_version']=sm['python_version'];expected.pop('manifest_hash')
        require(_digest(expected)==sh,'single-request manifest does not reproduce')
        started_path=f'raw/{rid}/{key}/attempt-01.started.json';started=_read(root,started_path)
        require(started['messages']==build_messages(prepared['base'].scenarios[index-1],'post_update') and started['attempt']==1 and
            started['manifest_hash']==sh,'started identity/prompt mismatch')
        paths.update((f'manifests/{rid}.json',started_path))
        for name,expected_bytes in ((sm['benchmark_artifact'],prepared['base'].benchmark_bytes),
                                    (sm['benchmark_metadata_artifact'],prepared['base'].metadata_bytes)):
            require((root/name).read_bytes()==expected_bytes,'copied frozen benchmark changed');paths.add(name)
        paths.update(p.relative_to(root).as_posix() for p in (root/f'parsed/{rid}').glob('analysis_index.json'))
        paths.update(p.relative_to(root).as_posix() for p in (root/f'summaries/{rid}').glob('completion-*.json'))
        response=root/f'raw/{rid}/{key}/attempt-01.response.json'
        if not response.exists():require(entry['status']=='ambiguous_claimed_never_redispatch','missing response not quarantined');continue
        raw=parse_json(response.read_text());require((entry.get('raw_record_canonical_hash')==_digest(raw)) or
            (entry['status']=='ambiguous_claimed_never_redispatch' and 'raw_record_canonical_hash' not in entry),'response changed')
        capture_path=f'batches/{batch_id}/captures/{index:03d}.json'
        require((root/capture_path).exists(),'available response lacks original capture')
        capture=_read(root,capture_path);meta=capture['provider_response']
        require(capture['request_key']==key and raw['requested_model']==MODEL and raw['provider']=='google' and
            raw['attempt']==1 and raw['manifest_hash']==sh and raw['parameters']==PARAMETERS and
            raw['raw_output']==meta['raw_output'],'raw identity/model output changed')
        for field in ('requested_model','reported_model','latency_ms','request_id','usage','finish_reason',
                      'requested_parameters','effective_parameters','unsupported_parameters','structured_output_enforced'):
            require(raw[field]==meta[field],'captured metadata changed')
        matches=[o for o in audit['observations'] if o['execution_index']==index]
        require(len(matches)==1 and matches[0]['http_status']==capture['http_status'] and matches[0]['payload_sha256']==
            sha256(json.dumps(GoogleProvider().payload(started['messages'],MODEL,PARAMETERS)).encode()).hexdigest(),'wire audit mismatch')
        paths.add(response.relative_to(root).as_posix());parsed_path=f'parsed/{rid}/{key}.json'
        if raw['provider_error']:require(not (root/parsed_path).exists(),'provider failure has privacy score')
        else:
            scenario=prepared['base'].scenarios[index-1]
            reproduced=make_raw_record(scenario=scenario,raw_output=raw['raw_output'],execution_index=index,provider='google',
                model=MODEL,timestamp=raw['timestamp'],condition='post_update',parameters=PARAMETERS,
                latency_ms=raw['latency_ms'],request_id=raw['request_id'])
            require(all(raw.get(k)==v for k,v in reproduced.items()),'raw strict parsing/metadata mismatch')
            score=asdict(score_output(scenario,'post_update',parse_output(raw['raw_output'],scenario)))
            if (root/parsed_path).exists():
                require(_read(root,parsed_path)=={'request_key':key,'manifest_hash':sh,'raw_hash':_digest(raw),'score':score},'strict score/hash changed')
                require(entry.get('primary_score')==score or entry['status']=='ambiguous_claimed_never_redispatch',
                    'cumulative strict score mismatch')
                paths.add(parsed_path)
            else:require(entry['status']=='ambiguous_claimed_never_redispatch','successful response lacks strict score')
    for name,files in (('source',prepared['source_hashes']),('batch',{p:None for p in paths})):
        original=prepared['source'] if name=='source' else root
        for relative in files:
            p=original/relative;require(not any(v.is_symlink() for v in (p,*p.parents)),'artifact symlink')
            data=p.read_bytes();text=data.decode();values=[parse_json(line) for line in text.splitlines()] if p.suffix=='.jsonl' else [parse_json(text)]
            for value in values:safe(value)
            target=destination/name/relative;target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(data)
    hashes=file_hashes(destination)
    receipt={'version':'flash-lite-artifact-seal-v1','batch_manifest_hash':mh,'authorization_commit':m['owner_approval_evidence']['authorization_commit'],
             'file_hashes':hashes,'file_tree_hash':_digest(hashes),'cumulative_ledger_hash':_digest(ledger),
             'verified_prior_terminal_attempts':13,'known_new_started_identities':len(ledger)-13,
             'complete':audit['stop_reason'] is None and len(ledger)==23 and all(e['status']=='terminal_completed' for e in ledger),
             'reserved_scope_hash':_digest(m['requests']),'run_id':m['context']['run_id'],'invocation_nonce':m['context']['invocation_nonce']}
    _write(destination,'seal.json',receipt);return receipt


def verify_sealed(prepared,artifact,expected_tree_hash):
    """Offline promotion gate: partial/ambiguous bundles never authorize a next batch."""
    artifact=Path(artifact);receipt=parse_json((artifact/'seal.json').read_text())
    files=file_hashes(artifact);files.pop('seal.json')
    require(files==receipt['file_hashes'] and _digest(files)==receipt['file_tree_hash']==expected_tree_hash,
            'sealed artifact changed/missing/extra')
    require(receipt['complete'] is True,'partial/ambiguous predecessor blocks continuation')
    require(file_hashes(artifact/'source')==prepared['source_hashes'],'inherited records changed')
    with __import__('tempfile').TemporaryDirectory() as d:
        reproduced=seal(prepared,artifact/'batch',prepared['base'].manifest['run_id'],Path(d)/'reproduced')
        require(reproduced==receipt,'seal/provenance does not reproduce')
    ledger=_read(artifact/'batch',f"batches/{prepared['base'].manifest['run_id']}/campaign-ledger.json")['ledger']
    require(len(ledger)==23 and all(e['status']=='terminal_completed' for e in ledger),'incomplete/ambiguous ledger')
    return ledger


def archival_summary(artifact,zip_path,expected_tree_hash):
    """Small human-reviewed receipt; hashes do not substitute for retaining raw ZIPs."""
    artifact=Path(artifact);receipt=parse_json((artifact/'seal.json').read_text())
    require(receipt['file_tree_hash']==expected_tree_hash,'archive reference mismatch')
    import zipfile
    with zipfile.ZipFile(zip_path) as z:
        entries=z.infolist();require(len(entries)<=2000 and sum(i.file_size for i in entries)<=20_000_000,'archive exceeds bound')
        names={};expected=file_hashes(artifact)
        for i in entries:
            if i.is_dir():continue
            require(i.filename in expected and i.filename not in names and not i.flag_bits&1,'unexpected archive entry')
            names[i.filename]=sha256(z.read(i)).hexdigest()
        require(names==expected,'ZIP does not match sealed scientific tree')
    ledger=_read(artifact/'batch',f"batches/gh-artifact-{receipt['run_id']}-1/campaign-ledger.json")['ledger']
    return {'version':'flash-lite-human-archive-checkpoint-v1','run_id':receipt['run_id'],
        'batch_manifest_hash':receipt['batch_manifest_hash'],'file_tree_hash':expected_tree_hash,
        'zip_sha256':sha256(Path(zip_path).read_bytes()).hexdigest(),
        'seal_sha256':sha256((artifact/'seal.json').read_bytes()).hexdigest(),
        'cumulative_ledger_hash':receipt['cumulative_ledger_hash'],'complete':receipt['complete'],
        'known_new_started_identities':receipt['known_new_started_identities'],
        'reserved_scope_hash':receipt['reserved_scope_hash'],'authorization_commit':receipt['authorization_commit'],
        'terminal_identities':[{'request_key':r['request_key'],'identity':r['identity'],'status':r['status'],
            'primary_parse_status':r.get('primary_parse_status','unknown')} for r in ledger],
        'owner_verified_two_independent_archive_copies':False,'archive_references':[],
        'archival_copies_verified_by_owner':False}
