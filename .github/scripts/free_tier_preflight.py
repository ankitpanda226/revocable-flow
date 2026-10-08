"""Read-only readiness gate; no provider client is invoked."""
import os
from revocable_flow.free_tier_campaign import readiness, PHASES
from revocable_flow.schema import ValidationError


def check(phase):
    if phase not in PHASES:raise ValidationError('unknown phase')
    return readiness()


if __name__=='__main__':
    try:
        check(os.environ.get('PHASE','connectivity'))
    except (ValueError,OSError,KeyError,TypeError):
        raise SystemExit('Free-tier pilot blocked: candidate/account/parameter/billing evidence unresolved. No provider request was made.') from None
