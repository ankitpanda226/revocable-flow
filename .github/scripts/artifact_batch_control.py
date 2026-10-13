"""Read-only GitHub authorization polling; no credential/resource provisioning."""
from pathlib import Path
from hashlib import sha1
import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.error

from revocable_flow import artifact_batch as batch
from revocable_flow.recovery import NoRedirect
from revocable_flow.schema import ValidationError,parse_json
from revocable_flow.runner import _write,_digest

PREFIX='/repos/ankitpanda226/revocable-flow'

def get(path):
    if not path.startswith(PREFIX+'/'):raise ValidationError('unexpected GitHub read destination')
    key=os.environ.get('GITHUB_TOKEN')
    if not key:raise ValidationError('read-only GitHub token unavailable')
    request=urllib.request.Request('https://api.github.com'+path,method='GET',headers={
        'Authorization':'Bearer '+key,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=30) as response:
            data=response.read(2_000_001)
            if len(data)>2_000_000:raise ValidationError('oversized GitHub read')
            return parse_json(data.decode())
    except urllib.error.HTTPError as e:
        if e.code==404:return None
        raise ValidationError('GitHub read failed; no dispatch') from None
    except Exception:raise ValidationError('GitHub read uncertain; no dispatch') from None


def wait_for_owner(prepared,*,read=get,sleep=time.sleep,now=time.monotonic):
    import base64
    require=batch.require;run_id=int(os.environ['GITHUB_RUN_ID'])
    require(os.environ['GITHUB_RUN_ATTEMPT']=='1' and os.environ['GITHUB_REF']=='refs/heads/main' and
        os.environ['GITHUB_EVENT_NAME']=='workflow_dispatch','unsupported workflow context')
    info=read(PREFIX+f'/actions/runs/{run_id}');require(info and info['head_sha']==os.environ['GITHUB_SHA'] and
        info['path']==batch.WORKFLOW and info['run_attempt']==1 and info['id']==run_id and
        info['head_branch']=='main' and info['event']=='workflow_dispatch','service run mismatch')
    jobs=read(PREFIX+f'/actions/runs/{run_id}/attempts/1/jobs?per_page=100')
    require(jobs and jobs.get('total_count')==1 and len(jobs['jobs'])==1,'job history ambiguous')
    job=jobs['jobs'][0];require(job['name']=='artifact_batch' and job['status']=='in_progress' and type(job['runner_id']) is int and job['runner_id']>=0 and job['run_id']==run_id,'runner binding unavailable')
    context={'repository':'ankitpanda226/revocable-flow','run_id':run_id,'run_attempt':1,'job_id':job['id'],
             'runner_id':job['runner_id'],'execution_commit':os.environ['GITHUB_SHA'],'invocation_nonce':uuid.uuid4().hex+uuid.uuid4().hex}
    _write(prepared['base'].root,f"batches/{prepared['base'].manifest['run_id']}/invocation.initialized.json",context)
    template={'version':'flash-lite-invocation-authorization-v1','workflow_path':batch.WORKFLOW,'binding':context,
        'scope_hash':_digest(prepared['planned']['requests']),'predecessor_manifest_hash':prepared['checkpoint']['manifest_hash'],
        'approved_at_epoch':'FILL_WITH_CURRENT_UNIX_TIME','fresh_review':{**{f:False for f in batch.FLAGS},
        'reviewed_spend_usd':None,'available_rpm_requests':None,'available_rpd_requests':None,'available_tpm_tokens':None}}
    print('Owner action: create this authorization ONCE in main at '+prepared['policy']['authorization_path'],flush=True)
    print(json.dumps(template,indent=2),flush=True)
    deadline=now()+600
    while now()<deadline:
        content=read(PREFIX+'/contents/'+prepared['policy']['authorization_path']+'?ref=main')
        if content is not None:
            require(content.get('type')=='file' and content.get('encoding')=='base64','authorization content unavailable')
            data=base64.b64decode(''.join(content['content'].split()),validate=True).decode()
            history=read(PREFIX+'/commits?path='+prepared['policy']['authorization_path']+'&sha=main&per_page=100')
            require(isinstance(history,list) and len(history)==1,'authorization file modified/reused')
            evidence={'record':parse_json(data),'record_bytes_utf8':data,'blob_sha':content['sha'],
                'authorization_commit':history[0]['sha'],'file_history':[h['sha'] for h in history],
                'path':prepared['policy']['authorization_path']}
            batch.authorization(prepared,evidence,context);return evidence,context
        sleep(15)
    raise ValidationError('owner authorization unavailable; zero generation allowed')


if __name__=='__main__':
    try:
        command=sys.argv[1];source=Path(os.environ['RUNNER_TEMP'])/'artifact-source'
        run_id=f"gh-artifact-{int(os.environ['GITHUB_RUN_ID'])}-1";prepared=batch.prepare(source,run_id)
        if command=='check':print(json.dumps({'live_enabled':prepared['policy']['live_execution_enabled'],
            'exact_requests':prepared['planned']['requests'],'quota_floor':prepared['headroom_floor']}))
        elif command=='execute':
            batch.require(prepared['policy']['live_execution_enabled'] is True,'live execution disabled')
            evidence,context=wait_for_owner(prepared)
            result=batch.run(prepared,evidence,context)
            print(json.dumps(result['audit']));raise SystemExit(1 if result['audit']['stop_reason'] else 0)
        elif command=='seal':
            batch.seal(prepared,prepared['base'].root,run_id,Path(os.environ['RUNNER_TEMP'])/'artifact-upload')
            with Path(os.environ['GITHUB_OUTPUT']).open('a') as f:f.write('safe=true\n')
        else:raise ValidationError('unknown command')
    except (ValidationError,OSError,ValueError,KeyError,TypeError):
        raise SystemExit('Artifact batch stopped/quarantined; no retries or redispatch authorized.') from None
