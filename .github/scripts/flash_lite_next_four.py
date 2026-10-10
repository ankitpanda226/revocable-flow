"""Explicit check/run/archive entrypoints for a fixed, non-resumable batch."""
import argparse
import os
from pathlib import Path
from revocable_flow.four_request_bridge import prepare, run, archive
from revocable_flow.four_request_bridge import SCOPE, CONTINUATION_SCOPE


def approvals():
    flags=('four_requests_approved','key_project_binding_confirmed','free_tier_no_paid_billing_confirmed',
           'quota_review_confirmed','all_provider_budget_review_confirmed')
    result={name:os.environ.get(name.upper())=='true' for name in flags}
    result['reviewed_spend_usd']=float(os.environ.get('REVIEWED_SPEND_USD',''))
    for name in ('available_rpm_requests','available_rpd_requests','available_tpm_tokens'):
        result[name]=int(os.environ.get(name.upper(),''))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=('check','run','archive'))
    parser.add_argument('--execute-live',action='store_true')
    parser.add_argument('--scope',choices=('002-005','006-009'),default='002-005')
    args=parser.parse_args()
    try:
        source=Path(os.environ['RUNNER_TEMP'])/'four-source'
        run_id=os.environ['RUN_ID']
        scope=CONTINUATION_SCOPE if args.scope=='006-009' else SCOPE
        if args.command=='check':
            plan=prepare(source,run_id,approvals(),scope=scope)
            if plan.manifest['git_dirty'] is not False or not plan.manifest['commit']:
                raise ValueError('clean committed checkout required')
            print('Verified source; next four post-update identities only; no request executed.')
            print({'execution_indices':[r['execution_index'] for r in plan.manifest['requests']],
                   'quota_headroom_floor':plan.manifest['quota_review']['conservative_byte_based_headroom_floor']})
        elif args.command=='run':
            if not args.execute_live:raise ValueError('explicit live flag required')
            _,summary=run(source,run_id,approvals(),scope=scope)
            print({'attempted':summary['attempted_provider_requests'],'completed':summary['completed']})
            raise SystemExit(0 if summary['complete'] else 1)
        else:
            archive(source,'results',run_id,Path(os.environ['RUNNER_TEMP'])/'four-upload')
            with Path(os.environ['GITHUB_OUTPUT']).open('a',encoding='utf-8') as f:f.write('safe=true\n')
            print('Inspected original and batch artifacts prepared without rewriting primary records.')
    except (ValueError,OSError,KeyError,TypeError,RecursionError):
        raise SystemExit('Fixed-four preparation refused/stopped; no retry or follow-up authorized.') from None
