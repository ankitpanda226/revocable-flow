"""Authorize upload only after inspecting original, first and chained recoveries."""
import os
from pathlib import Path
from revocable_flow.chained_recovery import stage_chained_upload

if __name__ == '__main__':
    try:
        stage_chained_upload(Path(os.environ['RUNNER_TEMP'])/'chained-preserved',os.environ['SOURCE_RUN_ID'],
                             'results',os.environ['RECOVERY_ID'],Path(os.environ['RUNNER_TEMP'])/'chained-upload')
        with Path(os.environ['GITHUB_OUTPUT']).open('a',encoding='utf-8') as stream:
            stream.write('safe=true\n')
        print('Safe chained archive prepared; ancestor bytes unchanged.')
    except (ValueError,OSError,KeyError,TypeError,RecursionError):
        raise SystemExit('Chained artifact inspection failed; upload not authorized.') from None
