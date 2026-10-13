// Read-only guard, independent of numerical run ordering. Missing history stops.
module.exports=async function({github,context}) {
 const {owner,repo}=context.repo;
 if(owner!=='ankitpanda226'||repo!=='revocable-flow') throw new Error('Repository mismatch');
 const runs=await github.paginate(github.rest.actions.listWorkflowRuns,{owner,repo,
   workflow_id:'flash-lite-artifact-batch.yml',branch:'main',per_page:100});
 for(const run of runs){
  if(String(run.id)===String(context.runId)) continue;
  if(run.status!=='completed'||run.run_attempt!==1) throw new Error('Overlapping or ambiguous workflow');
  const jobs=await github.paginate(github.rest.actions.listJobsForWorkflowRunAttempt,
    {owner,repo,run_id:run.id,attempt_number:1,per_page:100});
  if(jobs.length!==1||['cancelled','timed_out'].includes(jobs[0].conclusion)) throw new Error('Incomplete job history');
  const steps=(jobs[0].steps||[]).filter(s=>s.name==='Execute owner-bound frozen 014–023');
  if(steps.length!==1||steps[0].status!=='completed') throw new Error('Missing or ambiguous execution history');
  if(steps[0].conclusion!=='skipped') throw new Error('Scope already entered execution; never redispatch');
 }
};
