# Single-request chained Gemini recovery

The original sanity run and first recovery are validated before preparing a final request for **original execution index 2 only**. The existing two-request workflow is unchanged. Use the recovery CLI's new `--from-recovery` option with a `source/` + `recovery/` bundle, not the original sanity archive alone.

Validation checks both manifest self-hashes, source commit and file-hash lineage, exact frozen experiment inputs, benchmark copies, started/terminal response pairs, analysis indices, saved scoring, completion summaries and the first recovery's dispatch audit. The accepted history has original 503s for 1/2, original success for 3, first-recovery success for 1 and a terminal retryable 503 for 2. Extra/missing records, ambiguous claims, altered inputs, expired provenance, a successful latest index 2 or unexpired Retry-After prevent dispatch. A wrong answer is never retried to improve its score; a valid terminal success is preserved regardless of correctness.

The linked new manifest selects only `model-02/post_update/002`, records ancestor hashes, prior trial dispatch counts {1:2,2:2,3:1}, and next_trial_attempt=3. The full three-scenario mapping is retained for the existing runner's execution_index-1 scorer lookup; no trial is renumbered. Maximum one new call, one attempt, no automatic retry, no redirect, no model/provider fallback. Existing adapter, parser, scoring and frozen configuration are reused. This is the third dispatch for original scenario 2 and does not exceed the frozen three-attempt limit. Further chained recoveries are not accepted as a source.

The archive `gemini-chained-recovery-results` preserves unchanged `source/` and `recovery/` trees plus separate `chained_recovery/` records and dispatch audit. Ancestor bytes are rechecked before safe upload. Credential checks reject unsafe content rather than alter raw records. Existing destinations/run identities are rejected; a crash after claiming dispatch is ambiguous and not automatically repeated. Artifact retention is 30 days; download to durable research storage promptly.

## Manual workflow, after separate live authorization

1. Check cumulative all-provider spend against the $4 total budget and confirm this source has not already received a chained recovery. Pricing/free-tier eligibility and actual remaining spend are not established by these artifacts. One request is not a dollar-denominated guarantee.
2. Open repository Actions and select **Gemini single-request chained recovery**.
3. Choose Run workflow on main, source_run_id **37825597229**, source_attempt **1**.
4. Acknowledge the budget/history review only after completing it and separately authorizing the call. Dispatch once.
5. Download gemini-chained-recovery-results and inspect every ancestor and new response. Do not rerun or create a second invocation automatically.

The manual workflow verifies source GitHub metadata for gemini-recovery.yml, then downloads only the existing gemini-recovery-results artifact. It runs offline tests and benchmark validation before preflight/dispatch. Budget approval defaults false. Workflow reruns are blocked, and concurrent invocations for the source are queued. A separate new manual dispatch remains possible: concurrency is not a permanent deduplication or billing ledger. The owner must review prior runs to prevent repeated index 2 calls across invocations. Successful indices 1 and 3 are excluded from every chained dispatch plan.

This implementation was tested with mocks only. Publication does not authorize or execute a live call. See [artifact validation](reports/gemini_chained_recovery_validation.md).
