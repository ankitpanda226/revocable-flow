// Read-only GitHub workflow-history gate. Never contacts a model provider.
module.exports = async function ({github, context, core, phase, priorRunId}) {
  const phases = ['connectivity', 'small_pilot', 'remaining_post', 'paired_pre'];
  const expected = phases.indexOf(phase);
  if (expected < 0) throw new Error('Unknown phase');
  const {owner, repo} = context.repo;
  const current = BigInt(context.runId);
  const runs = await github.paginate(github.rest.actions.listWorkflowRuns, {
    owner, repo, workflow_id: 'free-tier-pilot.yml', branch: 'main', per_page: 100
  });
  const attempted = [];
  for (const run of runs) {
    if (BigInt(run.id) >= current) continue;
    if (run.status !== 'completed') throw new Error('Earlier dispatch not completed');
    if (run.run_attempt !== 1) throw new Error('Earlier rerun requires manual review');
    const jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRunAttempt, {
      owner, repo, run_id: run.id, attempt_number: 1, per_page: 100
    });
    if (!jobs.length || jobs.some(job => ['cancelled','timed_out'].includes(job.conclusion))) {
      throw new Error('Earlier dispatch has ambiguous job history');
    }
    const executionSteps = jobs.flatMap(job => (job.steps || []).filter(step =>
      step.name === 'Run only explicitly selected bounded phase'));
    if (executionSteps.some(step => step.status !== 'completed' && step.status !== 'pending')) {
      throw new Error('Earlier execution step has an ambiguous outcome');
    }
    const started = jobs.some(job => (job.steps || []).some(step =>
      step.name === 'Run only explicitly selected bounded phase' && step.status === 'completed' &&
      step.conclusion !== 'skipped'));
    if (started) attempted.push(run);
  }
  // Any failed/ambiguous stage occupies its slot: never restart a fresh campaign.
  attempted.sort((a,b) => a.id < b.id ? -1 : 1);
  if (attempted.length !== expected) throw new Error('Duplicate, missing or ambiguous prior stage');
  if (!expected) {
    if (priorRunId) throw new Error('First phase cannot have a predecessor');
    return;
  }
  const prior = attempted[attempted.length - 1];
  if (String(prior.id) !== priorRunId || prior.path !== '.github/workflows/free-tier-pilot.yml' ||
      prior.event !== 'workflow_dispatch' || prior.head_branch !== 'main' ||
      prior.conclusion !== 'success' || !/^[0-9a-f]{40}$/.test(prior.head_sha)) {
    throw new Error('Immediate prior stage is not a verified successful manual pilot');
  }
  core.setOutput('commit', prior.head_sha);
};
