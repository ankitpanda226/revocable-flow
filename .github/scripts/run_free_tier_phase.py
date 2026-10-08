"""Explicit manual phase entry point; evidence/budget/history gates precede dispatch."""
import os
from pathlib import Path
from revocable_flow.free_tier_campaign import execute_stage

if __name__=='__main__':
    try:
        history=Path(os.environ['RUNNER_TEMP'])/'flash-lite-history' if os.environ.get('PRIOR_RUN_ID') else None
        plan,summary=execute_stage(os.environ['PHASE'],os.environ['RUN_ID'],history=history,
            reviewed_spend=float(os.environ['REVIEWED_SPEND_USD']),approved=os.environ.get('BUDGET_APPROVED')=='true',
            expected_previous_commit=os.environ.get('PRIOR_COMMIT'))
        print({'planned':summary['planned'],'completed':summary['completed'],
               'attempted':summary['attempted_provider_requests'],'provider_stop_reason':summary['provider_stop_reason'],
               'unattempted':len(summary['unattempted_requests'])})
        raise SystemExit(0 if summary['complete'] else 1)
    except (ValueError,OSError,KeyError,TypeError):
        raise SystemExit('Free-tier phase stopped or refused; inspect safe artifacts. No automatic replay authorized.') from None
