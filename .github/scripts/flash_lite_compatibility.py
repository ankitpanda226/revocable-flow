"""Manual preflight/run/archive entrypoints; no implicit execution or retry."""
import argparse
import os
from pathlib import Path
from revocable_flow.compatibility_probe import prepare, run, archive


def approvals():
    names=('one_request_approved','key_project_binding_confirmed','free_tier_no_paid_billing_confirmed',
           'quota_review_confirmed','all_provider_budget_review_confirmed')
    result={name:os.environ.get(name.upper())=='true' for name in names}
    result['reviewed_spend_usd']=float(os.environ.get('REVIEWED_SPEND_USD',''))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=('check','run','archive'))
    parser.add_argument('--execute-live',action='store_true')
    args=parser.parse_args()
    try:
        run_id=os.environ['RUN_ID']
        if args.command=='check':
            plan=prepare(run_id,approvals())
            if plan.manifest['git_dirty'] is not False or not plan.manifest['commit']:
                raise ValueError('clean committed checkout required')
            print('Preflight passed: one Google compatibility request, one attempt; no request executed.')
        elif args.command=='run':
            if not args.execute_live:raise ValueError('explicit live flag required')
            _,summary,audit=run(run_id,approvals())
            print({'attempted':summary['attempted_provider_requests'],'completed':summary['completed'],
                   'http_status':audit['http_status'],'transport_outcome_uncertain':audit['transport_outcome_uncertain']})
            raise SystemExit(0 if summary['complete'] else 1)
        else:
            archive('results',run_id,Path(os.environ['RUNNER_TEMP'])/'compatibility-upload')
            with Path(os.environ['GITHUB_OUTPUT']).open('a',encoding='utf-8') as f:f.write('safe=true\n')
            print('Inspected compatibility artifacts prepared.')
    except (ValueError,OSError,KeyError,TypeError,RecursionError):
        raise SystemExit('Compatibility test refused/stopped; inspect safe artifacts. No automatic retry authorized.') from None
