"""Inspect stage and ancestor research files before authorizing upload."""
import os
from pathlib import Path
from revocable_flow.free_tier_campaign import stage_campaign
if __name__=='__main__':
    try:
        history=Path(os.environ['RUNNER_TEMP'])/'flash-lite-history' if os.environ.get('PRIOR_RUN_ID') else None
        stage_campaign(history,'results',os.environ['RUN_ID'],Path(os.environ['RUNNER_TEMP'])/'flash-lite-upload')
        with Path(os.environ['GITHUB_OUTPUT']).open('a',encoding='utf-8') as stream:stream.write('safe=true\n')
        print('Safe stage/ancestor archive prepared.')
    except (ValueError,OSError,KeyError,TypeError,RecursionError):
        raise SystemExit('Safe phase artifact inspection failed; upload not authorized.') from None
